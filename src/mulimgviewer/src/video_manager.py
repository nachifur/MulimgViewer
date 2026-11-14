"""Video decoding, bounded caches, composition scheduling and performance metrics."""
import threading
from pathlib import Path
import ffmpeg, os, time, math, sys
from concurrent.futures import ThreadPoolExecutor, Future, CancelledError
import weakref
import subprocess
from fractions import Fraction
from collections import deque
import numpy as np
import wx
from PIL import Image
from concurrent.futures import wait
from .utils_img import ImgManager
from .video_tools import resolve_video_tools
from .video_timeline import page_count, page_segments, raw_dependencies
from .video_paths import frame_filename
from .resource_monitor import run_video_process
from .pipeline_executor import PipelineWorkers
from .admission_optimizer import AdaptiveAdmissionBudget
from .video_decoder import DecoderBank
from .video_memory import PixelCache, source_resolution
from .custom_pipeline import current_only
from .cache_layout import page_name, write_source_catalog
from .custom_func.contract import active_cache_names
from .playback_pacer import PlaybackPacer, ProductionJob, completion_estimates, refill_guard
from .thread_optimizer import (AdaptiveThreadAllocator, optimize_thread_allocation,
                               available_memory_bytes, stitch_memory_limit,
                               buffer_levels, buffer_priority)
import json
import shutil
import copy


class PerformanceMonitor:
    """Lightweight collector for extraction/stitch/render metrics."""

    def __init__(self, eval_batch_window=5, eval_time_window=0.5):
        self._lock = threading.RLock()
        self.extract_history = deque(maxlen=60)
        self.extract_run_history = deque(maxlen=30)
        self.extract_runs_by_video = {}
        self.resize_history = deque(maxlen=20)
        self.extract_by_video = {}
        self.extract_by_plan = {}
        self.stitch_by_plan = {}
        self.plan_revisions = {}
        self.stitch_history = deque(maxlen=60)
        self.display_history = deque(maxlen=30)
        self.render_history = deque(maxlen=30)
        self.buffer_history = deque(maxlen=60)
        self.eval_batch_window = max(1, int(eval_batch_window))
        self.eval_time_window = max(0.1, float(eval_time_window))
        self.processed_batches = 0
        self.last_eval_batch = 0
        self.last_eval_time = 0.0
        self.last_render_timestamp = None
        self.last_render_batch = None

    def record_extract(self, duration, batches=1, video_idx=0, plan=None):
        if duration is not None and math.isfinite(duration) and duration >= 0 and batches > 0:
            cost = float(duration) / batches
            with self._lock:
                self.extract_run_history.append(float(duration))
                self.extract_runs_by_video.setdefault(video_idx, deque(maxlen=12)).append(float(duration))
                self.extract_history.extend([cost] * min(60, max(1, int(batches))))
                self.extract_by_video.setdefault(video_idx, deque(maxlen=24)).extend(
                    [cost] * min(24, max(1, int(batches))))
                if plan is not None:
                    self.plan_revisions[tuple(plan)] = self.plan_revisions.get(tuple(plan), 0) + 1
                    by_video = self.extract_by_plan.setdefault(tuple(plan), {})
                    by_video.setdefault(video_idx, deque(maxlen=24)).extend(
                        [cost] * min(24, max(1, int(batches))))
                    if len(self.extract_by_plan) > 32:
                        self.extract_by_plan.pop(next(iter(self.extract_by_plan)))

    def buffer_latencies(self):
        """Conservative completion/switch lead times, without GUI filesystem access."""
        def percentile(values):
            values = sorted(list(values)[-12:])
            return values[math.ceil(.9 * len(values)) - 1] if values else 0.
        with self._lock:
            return (percentile(self.extract_run_history), percentile(self.stitch_history),
                    percentile(self.resize_history))

    def service_estimates(self, video=None):
        with self._lock:
            samples = self.stitch_history if video is None else self.extract_runs_by_video.get(video, self.extract_run_history)
            values = list(samples)[-12:]
            # P90 is for early refill warnings, not every job's normal ETA:
            # applying tail latency to every queued job compounds slowdown.
            return sum(values) / len(values) if values else 0.

    def record_stitch(self, duration, plan=None):
        if duration is not None and math.isfinite(duration) and duration >= 0:
            with self._lock:
                self.stitch_history.append(float(duration))
                if plan is not None:
                    self.plan_revisions[tuple(plan)] = self.plan_revisions.get(tuple(plan), 0) + 1
                    self.stitch_by_plan.setdefault(tuple(plan), deque(maxlen=24)).append(float(duration))
                    if len(self.stitch_by_plan) > 32:
                        self.stitch_by_plan.pop(next(iter(self.stitch_by_plan)))

    def record_display(self, duration):
        if duration is not None and math.isfinite(duration) and duration >= 0:
            with self._lock:
                self.display_history.append(float(duration))

    def stage_costs(self, video_indices, cached=False, plan=None):
        """Seconds of work per displayed batch, without playback timer delays."""
        with self._lock:
            if not self.display_history:
                return None
            display = sorted(list(self.display_history)[-12:])
            display_cost = display[int((len(display) - 1) * 0.75)]
            if cached:
                return 0.0, 0.0, display_cost
            extraction = self.extract_by_video if plan is None else self.extract_by_plan.get(tuple(plan), {})
            stitching = self.stitch_history if plan is None else self.stitch_by_plan.get(tuple(plan), ())
            extract_cost = 0.0
            for vid in video_indices:
                samples = extraction.get(vid)
                if not samples:
                    return None
                extract_cost += self._avg(list(samples)[-12:])
            stitch_cost = self._avg(list(stitching)[-12:])
            if stitch_cost is None:
                return None
            return extract_cost, stitch_cost, display_cost

    def record_render_interval(self, interval):
        if interval is not None and math.isfinite(interval) and interval > 0:
            self.render_history.append(float(interval))

    def record_buffer_depth(self, depth):
        if depth is not None and depth >= 0:
            self.buffer_history.append(int(depth))

    def mark_processed_batch(self):
        self.processed_batches += 1

    def should_evaluate(self):
        now = time.perf_counter()
        if self.processed_batches - self.last_eval_batch >= self.eval_batch_window:
            return True
        if now - self.last_eval_time >= self.eval_time_window:
            return True
        return False

    def mark_evaluated(self):
        self.last_eval_batch = self.processed_batches
        self.last_eval_time = time.perf_counter()

    def reset_render_clock(self):
        self.last_render_timestamp = None
        self.last_render_batch = None

    def push_render_event(self, batch=None, direction=1):
        if batch is not None and batch == self.last_render_batch:
            return False
        now = time.perf_counter()
        last = self.last_render_timestamp
        adjacent = (batch is None or self.last_render_batch is None
                    or batch == self.last_render_batch + (1 if direction >= 0 else -1))
        if not adjacent:
            self.render_history.clear()
        if last is not None and adjacent:
            interval = now - last
            if interval > 0:
                self.record_render_interval(interval)
        self.last_render_timestamp = now
        self.last_render_batch = batch
        return True

    def _avg(self, data):
        if not data:
            return None
        values = list(data)
        return sum(values) / len(values)

    def extract_avg(self):
        return self._avg(self.extract_history)

    def stitch_avg(self):
        return self._avg(self.stitch_history)

    def render_min(self):
        if not self.render_history:
            return None
        return min(self.render_history)

    def buffer_min(self):
        if not self.buffer_history:
            return None
        return min(self.buffer_history)

    def get_fps(self):
        """计算渲染 FPS（基于 render_history）"""
        if not self.render_history:
            return 0.0
        intervals = list(self.render_history)
        avg_interval = sum(intervals) / len(intervals)
        return 1.0 / avg_interval if avg_interval > 0 else 0.0

    def get_stitch_fps(self):
        """计算拼接 FPS（基于 stitch_history）"""
        if not self.stitch_history:
            return 0.0
        avg_time = sum(self.stitch_history) / len(self.stitch_history)
        return 1.0 / avg_time if avg_time > 0 else 0.0


class VideoManager:
    def __init__(self, owner, shared_config=None, ImgManager=None):
        self._owner = weakref.ref(owner)
        self.shared_config = shared_config
        self.ImgManager = ImgManager
        self.cache_dir = Path("cache_frames")
        # 新增：磁盘缓存目录
        self.disk_cache_dir = self.cache_dir / "composed"
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)
        # 新增：图像模式磁盘缓存目录
        self.image_disk_cache_dir = self.disk_cache_dir
        self.custom_disk_cache_dir = self.cache_dir / 'algorithms'
        self.image_disk_cache_dir.mkdir(parents=True, exist_ok=True)
        self.perf_monitor = PerformanceMonitor()
        self._playback_pacer = PlaybackPacer()
        self._admission_optimizer = AdaptiveAdmissionBudget()
        self._produced_pages = 0
        self._pacing_model_period = None
        self._pacing_notification_pending = False
        self.executor = None
        self.stitch_executor = None
        self._stitch_lock = threading.Lock()
        self._meta_cache = {}
        self._video_dimensions = {}
        self._fast_seek_paths = {}
        self._pending_extract = {}
        self._raw_batch_futures = {}
        self._pixel_cache = PixelCache()
        self._decoder_bank = DecoderBank()
        self._configure_video_memory()
        self._cache_guard = threading.RLock()
        self._raw_io_locks = {}
        self._cache_io_lock = threading.RLock()
        self._cache_request_lock = threading.Lock()
        self._cache_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-schedule')
        self._cache_update_future = None
        self._cache_request = None
        self._cache_request_serial = 0
        self._worker_context = threading.local()
        self._window_token = None
        self._raw_windows = {}
        self._raw_ready_batches = set()
        self._stitch_window = (0, -1)
        self._window_stitches = {}
        self._maintenance_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-cleanup")
        self._display_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-display")
        self._cleanup_future = None
        self._display_future = None
        self._display_serial = 0
        self._render_snapshot = None
        self._batch_render_states = {}
        self._pending_stitch_async = 0
        self._pending_lock = threading.Lock()
        self._last_batch = None
        # ★ 拼接缓存上下文指纹: 记录"已拼接批次是按什么参数生成的"。
        #   只有这些参数变化时, 已拼接的批次才会失效; 回退/跳页不影响, 可以直接复用缓存。
        self._cache_context = None
        self._cache_context_initialized = False
        self._total_threads = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        # Initial thread allocation for frame splitting/merging: at least one thread for each
        default_extract = max(1, self._total_threads - 1)
        default_stitch = max(1, self._total_threads - default_extract)
        self._extract_threads = default_extract
        self._stitch_threads = default_stitch
        self._success_streak = 0
        self._failure_streak = 0
        self._cooldown_deadline = 0.0
        self._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
        self._pending_thread_plan = None
        self._rebalance_queued = False
        self._reported_extract_threads = False
        self._reported_stitch_threads = False
        self._initialize_thread_pools()
        self._last_thread_resize = time.perf_counter()


    def _get_disk_cache_path(self, batch_idx):
        """生成磁盘缓存文件路径"""
        return self.disk_cache_dir / page_name(batch_idx)

    def _save_image_to_disk(self, pil_img, batch_idx):
        """将PIL图像保存到磁盘，返回文件路径"""
        if pil_img is None:
            return None
        try:
            cache_path = self._get_disk_cache_path(batch_idx)
            pil_img.save(str(cache_path), format='PNG', compress_level=1)  # 快速压缩
            return str(cache_path)
        except Exception as ex:
            self._debug_video(f"[DiskCache] save failed batch={batch_idx} error={ex}")
            return None

    def _cleanup_disk_cache_out_of_window(self, window_start, window_end):
        """清理窗口外的磁盘缓存"""
        if not self.disk_cache_dir.exists():
            return
        try:
            for cache_file in self.disk_cache_dir.glob("page_*.png"):
                try:
                    idx = int(cache_file.stem.split('_')[1])-1
                    if idx < window_start or idx > window_end:
                        cache_file.unlink()
                        if 0 <= idx < len(self.shared_config.cache_img):
                            self.shared_config.cache_img[idx] = None
                except Exception:
                    pass
        except Exception as ex:
            self._debug_video(f"[DiskCache] cleanup failed error={ex}")

    # ========== 拼接缓存上下文 / 复用 ==========

    def _cache_context_token(self, config=None):
        """拼接缓存上下文指纹。

        这里只包含"会改变某个 batch 拼接成什么图"的参数:
        视频列表、每视频帧数、每批帧数、并行转串行、抽帧步长。
        布局(放大框/行列/间距等)由 show_img_init() 的 layout_token 单独负责作废。
        """
        config = self.shared_config if config is None else config
        try:
            video_path = tuple(str(p) for p in (getattr(config, "video_path", []) or []))
        except Exception:
            video_path = ()
        try:
            video_num = tuple(int(x or 0) for x in (getattr(config, "video_num_list", []) or []))
        except Exception:
            video_num = ()
        return (
            video_path,
            video_num,
            int(getattr(config, "count_per_action", 1) or 1),
            bool(getattr(config, "parallel_to_sequential", False)),
            int(getattr(config, "skip_frames", 0) or 0),
        )

    def _cache_context_changed(self):
        """拼接上下文是否变化。变化时旧的拼接结果全部作废。"""
        token = self._cache_context_token()
        if not self._cache_context_initialized:
            # 第一次: 只记录指纹, 不作废(缓存本来就是空的)
            self._cache_context = token
            self._cache_context_initialized = True
            return False
        if self._cache_context == token:
            return False
        self._cache_context = token
        self._invalidate_stitch_cache()
        return True

    def _invalidate_stitch_cache(self):
        """作废所有已拼接的批次(内存 + 磁盘)。"""
        with self._cache_guard:
            self._invalidate_stitch_cache_locked()

    def _invalidate_stitch_cache_locked(self):
        self._window_generation = getattr(self, "_window_generation", 0) + 1
        self._window_token = None
        self._raw_ready_batches = set()
        for future in self._raw_batch_futures.values():
            future.cancel()
        self._raw_batch_futures.clear()
        self._pixel_cache.clear()
        self.shared_config.cache_img = []
        self._display_serial += 1
        self._render_snapshot = None
        self._batch_render_states.clear()
        self.perf_monitor = PerformanceMonitor()
        self._playback_pacer.reset()
        self._pacing_model_period = None
        self._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
        self._optimizer_seen = {}
        self._pending_thread_plan = None
        self._schedule_video_cleanup()

    def _cached_batch_path(self, global_idx, validate=True):
        """取已拼接批次的缓存路径; 缓存无效(为空 / 磁盘文件已被清理)时返回 None。

        磁盘缓存会按窗口清理, 所以内存里记下的路径可能已经指向不存在的文件,
        这种情况必须当作"没有缓存"处理, 否则会出现 Load cache failed。
        """
        cache = getattr(self.shared_config, "cache_img", None)
        if not cache:
            return None
        try:
            if global_idx < 0 or global_idx >= len(cache):
                return None
        except Exception:
            return None
        entry = cache[global_idx]
        if not entry:
            return None
        if not validate:
            return entry
        if isinstance(entry, str):
            try:
                if os.path.exists(entry) and os.path.getsize(entry) > 0:
                    return entry
            except Exception:
                pass
            # 文件已被清理 → 缓存失效
            try:
                cache[global_idx] = None
            except Exception:
                pass
            return None
        return entry

    def _display_cache_ready(self, local_b, base_global, radius, max_batch):
        """窗口 [b-R, b+R] 内的批次是否都已经有可用的拼接缓存。

        ★ 必须检查"整个窗口"(前方 + 历史), 不能只看"前方 + 上一批":
          - 缓存窗口会随当前位置移动, 尾部的批次会被磁盘清理删掉;
          - 以前只检查 [b, b+R] 和 b-1, 于是回退到"尾部已被清理"的位置时
            被误判成"已就绪" -> update_cache 直接短路返回 -> 缺失的那一张
            永远补不回来 (磁盘上就是少一张的样子)。

        全都就绪 -> 这一步不需要做任何缓存维护, 直接显示即可 (见 update_cache 里的短路)。
        只要有一段是冷的, 就老老实实走完整流程。
        """
        try:
            local_b = int(local_b)
            radius = max(1, int(radius))
            max_batch = int(max_batch)
        except Exception:
            return False
        if local_b < 0 or local_b >= max_batch:
            return False

        parallel_to_seq = bool(getattr(self.shared_config, "parallel_to_sequential", False))

        def _global(t):
            return (int(base_global) + t) if parallel_to_seq else t

        # ★ 整个窗口 [b-R, b+R] 都要有缓存才算就绪 (尾部历史也要检查)。
        look_start = max(0, local_b - radius)
        look_end = min(local_b + radius, max_batch - 1)
        if look_end < look_start:
            return False
        for t in range(look_start, look_end + 1):
            if self._cached_batch_path(_global(t)) is None:
                return False
        return True

    def _ui(self):
        return self._owner()

    def _set_video_message(self, message):
        try:
            self.shared_config.video_last_message = str(message or "")
        except Exception:
            pass

    def _set_video_status(self, message):
        msg = str(message or "")
        self._set_video_message(msg)
        if msg:
            print(f"[VideoStatus] {msg}")
        ui = self._ui()
        if ui:
            try:
                values = ["-1", "-1", f"***{msg}***", "-1"]
                if wx.IsMainThread():
                    ui.SetStatusText_(values)
                else:
                    wx.CallAfter(ui.SetStatusText_, values)
            except Exception:
                pass

    def _clear_video_status(self):
        self._set_video_message("")

    def _raw_io_lock(self, video_idx, config=None):
        config = self.shared_config if config is None else config
        directory = os.path.normcase(os.path.abspath(config.video_path[video_idx]))
        with self._cache_guard:
            lock = self._raw_io_locks.get(directory)
            if lock is None:
                lock = self._raw_io_locks[directory] = threading.RLock()
            return lock

    def _configure_video_memory(self):
        budget = getattr(self.shared_config, 'memory_budget', None)
        # Optional accelerators are SMALL byte caps, never the whole outer
        # window. Disk-backed originals/PNGs remain authoritative.
        self._pixel_cache.configure(min(1024 * 1024**2, int(budget * .08)) if budget else 0)
        self._decoder_bank.configure(min(1024 * 1024**2, int(budget * .20)) if budget else 64 * 1024**2)
        maintenance = getattr(self, '_maintenance_executor', None)
        if maintenance is not None and not getattr(self, '_closed', False):
            maintenance.submit(self._decoder_bank.trim)

    def _initialize_thread_pools(self):
        group = getattr(self, '_pipeline_workers', None)
        if group is None:
            group = self._pipeline_workers = PipelineWorkers(self._extract_threads, self._stitch_threads)
            self.executor, self.stitch_executor = group.stages
        output, inputs = self._estimated_stitch_pixels()
        group.configure(self._extract_threads, self._stitch_threads, self._planning_memory_budget(),
                        (self._decoder_working_set(), max(64 * 1024**2, 16*output + 9*inputs)),
                        total_budget=self._admission_limit())
        self._publish_thread_allocation()

    def _admission_limit(self):
        cfg = self.shared_config
        indices, _ = self._playback_video_indices()
        budget = max(2, int(cfg.thread))
        # Single-video native decode parallelism is already tuned separately.
        # Probe only producer concurrency; never change playback timing here.
        return self._admission_optimizer.configure(
            # Never compare total-concurrency trials across different stage
            # reservations: that changes the experiment and invalidates its
            # incumbent. Stage tuning settles before total-cap probing resumes.
            budget, (self._pacing_context(), tuple(indices),
                     self._extract_threads, self._stitch_threads),
            enabled=cfg.video_mode and cfg.power_mode >= 3 and len(indices) >= 2 and budget >= 4,
            warmup=max(8, 2*int(cfg.cache_num)*int(cfg.cache_multiplier)+1))

    def _maybe_tune_admission(self):
        cfg = self.shared_config
        if not cfg.video_mode or not cfg.is_playing:
            return
        self._admission_limit()
        with self._cache_guard:
            produced = self._produced_pages
        manual = getattr(cfg, 'manual_interval', None)
        changed = self._admission_optimizer.observe(
            time.perf_counter(), produced, self._compute_buffer_depth(),
            target_buffer=max(1, int(cfg.cache_num)),
            manual_limited=manual is not None and cfg.interval <= max(.001,manual)*1.05)
        if changed is not None:
            self._initialize_thread_pools()

    def _publish_thread_allocation(self):
        self.shared_config.thread_allocation = dict(
            budget=max(2, int(self.shared_config.thread)),
            extract=self._extract_threads, stitch=self._stitch_threads)
        ui = self._ui()
        if ui is not None and hasattr(ui, 'power_mode') and self.shared_config.video_mode:
            def show_allocation():
                owner = self._ui()
                if owner is not None and not getattr(owner, '_is_closing', False):
                    owner._refresh_power_tooltip()
            if wx.IsMainThread():
                show_allocation()
            else:
                wx.CallAfter(show_allocation)
        if getattr(self.shared_config, 'debug_thread', False):
            print(f"[ThreadAllocation] {self.shared_config.thread_allocation}")

    def _reset_for_new_selection(self):
        with self._cache_guard:
            self._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
            self._optimizer_seen = {}
            self._pending_thread_plan = None
            self._window_token = None
            self._render_snapshot = None
            self._batch_render_states.clear()
            self._display_serial += 1
            self._window_generation = getattr(self, "_window_generation", 0) + 1
            self._raw_windows = {}
            self._raw_ready_batches = set()
            self._stitch_window = (0, -1)
            for future in list(self._window_stitches.values()):
                future.cancel()
        monitor = getattr(self, "perf_monitor", None)
        if monitor is not None:
            self.perf_monitor = PerformanceMonitor(monitor.eval_batch_window, monitor.eval_time_window)
        else:
            self.perf_monitor = PerformanceMonitor()

        base_count = 1
        self.shared_config.cache_img = []
        self.shared_config.batch_idx = 0
        self.shared_config.interval_recommend = None
        self.shared_config.count_per_action = base_count
        self.shared_config.video_last_message = ""

        self._last_batch = None
        self._meta_cache.clear()
        self._video_dimensions.clear()
        self._fast_seek_paths.clear()
        # 新选的视频: 拼接上下文重新开始, 不再沿用上一批视频的指纹
        self._cache_context = None
        self._cache_context_initialized = False

        with self._cache_guard:
            for fut in list(self._pending_extract.values()):
                fut.cancel()
            self._pending_extract.clear()
            self._pending_stitch_async = 0

        self.perf_monitor.reset_render_clock()
        self._initialize_thread_pools()

        if hasattr(self, "ImgManager") and self.ImgManager:
            try:
                self.ImgManager.set_action_count(0)
            except Exception:
                pass
            if hasattr(self.ImgManager, "set_count_per_action"):
                try:
                    self.ImgManager.set_count_per_action(base_count)
                except Exception:
                    pass
            if hasattr(self.ImgManager, "flist"):
                self.ImgManager.flist = []
            if hasattr(self.ImgManager, "_flist_groups"):
                self.ImgManager._flist_groups = None

    def _apply_thread_plan(self, extract_threads, stitch_threads):
        with self._cache_guard:
            self._apply_thread_plan_locked(extract_threads, stitch_threads)

    def _apply_thread_plan_locked(self, extract_threads, stitch_threads):
        total_budget = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        extract_threads = max(1, int(extract_threads))
        stitch_threads = max(1, int(stitch_threads))
        snapshot=getattr(self,'_render_snapshot',None)
        if snapshot is not None:
            params=snapshot[0].layout_params
            processing=len(params)>38 and (snapshot[2] or params[38])
            if processing and total_budget>=3 and stitch_threads<2 and extract_threads>1:
                extract_threads-=1;stitch_threads+=1
        memory = getattr(self.shared_config, 'memory_budget', None)
        if memory is not None:
            extract_threads = min(extract_threads, self._extract_memory_limit())
            stitch_threads = min(stitch_threads, self._stitch_thread_limit(stitch_threads, extract_threads))
        if extract_threads + stitch_threads > total_budget:
            overflow = extract_threads + stitch_threads - total_budget
            # Prioritize reclamation from threads with a higher count
            if extract_threads >= stitch_threads:
                extract_threads = max(1, extract_threads - overflow)
            else:
                stitch_threads = max(1, stitch_threads - overflow)
        # If the budget is still exceeded, implement further mandatory cuts (in extreme cases)
        if extract_threads + stitch_threads > total_budget:
            stitch_threads = max(1, total_budget - extract_threads)
            if extract_threads + stitch_threads > total_budget:
                extract_threads = max(1, total_budget - stitch_threads)

        if extract_threads == self._extract_threads and stitch_threads == self._stitch_threads:
            # Equal stage reservations do not imply an unchanged global CPU,
            # memory or admission-search budget after a power-mode switch.
            self._initialize_thread_pools()
            return

        previous = (self._extract_threads, self._stitch_threads)
        self._extract_threads = extract_threads
        self._stitch_threads = stitch_threads
        self._initialize_thread_pools()
        self._last_thread_resize = time.perf_counter()
        allocator = getattr(self, '_thread_allocator', None)
        if allocator is not None:
            allocator.applied(previous, (extract_threads, stitch_threads))
        self._success_streak = 0
        self._failure_streak = 0

    def _enforce_thread_budget(self):
        total_budget = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        self._total_threads = total_budget
        extract_threads, stitch_threads = self._extract_threads, self._stitch_threads
        current_total = extract_threads + stitch_threads

        if current_total > total_budget:
            # Due to budget cuts, we need to reduce the number of threads.
            excess = current_total - total_budget
            if extract_threads > stitch_threads:
                extract_threads = max(1, extract_threads - excess)
            else:
                stitch_threads = max(1, stitch_threads - excess)
        elif current_total < total_budget:
            # Increase the budget, prioritizing the addition of frame-splitting threads
            available = total_budget - current_total
            extract_threads += available

        if getattr(self.shared_config, 'memory_budget', None) is not None:
            # Seed a joint feasible plan, rather than giving all new lanes to
            # decoders and clipping composition to one afterwards.
            indices, total = self._playback_video_indices()
            costs = self.perf_monitor.stage_costs(indices)
            work = costs[:2] if costs is not None else (max(1, len(indices)), 1.0)
            output, inputs = self._estimated_stitch_pixels()
            composition = max(64 * 1024 ** 2, 16 * output + 9 * inputs)
            span = min(max(1, total), 2 * self.shared_config.cache_num * self.shared_config.cache_multiplier + 1)
            plan = optimize_thread_allocation(total_budget, *work, 0.0,
                max_extract_tasks=max(1, len(indices)) * (5 if self.shared_config.cache_multiplier > 1 else 3),
                max_stitch_tasks=span, current=(self._extract_threads, self._stitch_threads),
                prefer_capacity=True, memory_budget=self._planning_memory_budget(),
                extract_memory=self._decoder_working_set(), stitch_memory=composition)
            extract_threads, stitch_threads = plan.extract, plan.stitch

        if (extract_threads, stitch_threads) == (self._extract_threads, self._stitch_threads):
            self._apply_thread_plan(extract_threads, stitch_threads)
            return
        busy = bool(self._pending_extract or self._window_stitches or self.cache_update_pending())
        if busy and getattr(self, '_cache_executor', None) is not None:
            self._request_thread_plan(extract_threads, stitch_threads)
        else:
            self._apply_thread_plan(extract_threads, stitch_threads)

    def _request_thread_plan(self, extract, stitch):
        # Existing tasks retain their permits until finished. New admissions
        # immediately follow the new stage quotas and shared total budget.
        # There is no cancel/drain/rebuild barrier on the cache coordinator.
        with self._cache_guard:
            if getattr(self, '_closed', False):
                return
            self._pending_thread_plan = None
            self._rebalance_queued = False
            self._apply_thread_plan(extract, stitch)
            self._cooldown_deadline = time.perf_counter() + 2.0

    def _rebalance_thread_pools(self):
        # Compatibility with old queued coordinator callbacks.
        self._pending_thread_plan = None
        self._rebalance_queued = False

    def _apply_interval_recommendation(self, recommended, reschedule=True):
        ui = self._ui()
        try:
            if not math.isfinite(recommended):
                return
            recommended = max(0.001, math.ceil(recommended * 1000 - 1e-9) / 1000.0)
            manual = getattr(self.shared_config, 'manual_interval', None)
            if manual is not None:
                recommended = max(recommended, manual)
            field = getattr(ui, 'interval', None) if ui else None
            if field is not None and field.HasFocus():
                return
            current = float(getattr(self.shared_config, "interval", recommended) or recommended)
            if abs(current - recommended) < 1e-9:
                return
            self.shared_config.interval = recommended
            if ui:
                if field is not None:
                    field.ChangeValue(f"{recommended:.3f}")
                if (reschedule and getattr(ui.shared_config, "is_playing", False)
                        and not getattr(ui, '_play_timer_suspended', False)):
                    ui._schedule_next_video_tick()
        except Exception as exc:
            pass

    def _compute_buffer_depth(self):
        cache = getattr(self.shared_config, "cache_img", [])
        if not cache:
            return 0
        current = int(getattr(self.shared_config, "batch_idx", 0))
        depth = 0
        direction = 1 if int(getattr(self.shared_config, 'play_direction', 1)) >= 0 else -1
        for idx in range(current + direction, len(cache) if direction > 0 else -1, direction):
            if not cache[idx]:
                break
            depth += 1
        return depth

    def _record_buffer_depth(self):
        depth = self._compute_buffer_depth()
        self.perf_monitor.record_buffer_depth(depth)

    @staticmethod
    def _video_batch_sources(batch, cfg):
        return raw_dependencies(cfg.video_num_list, cfg.count_per_action, batch,
                                cfg.parallel_to_sequential)

    def _raw_buffer_inventory(self, stitched_depth):
        """Unused raw pages AFTER the contiguous PNG frontier; state-only on GUI."""
        if not hasattr(self, '_raw_ready_batches'):
            return None
        cfg = self.shared_config
        current = int(cfg.batch_idx)
        direction = 1 if int(cfg.play_direction) >= 0 else -1
        with self._cache_guard:
            lo, hi = self._stitch_window
            if not lo <= current <= hi:
                return None
            ready = set(self._raw_ready_batches)
        capacity = hi - current if direction > 0 else current - lo
        raw_capacity = max(0, capacity - stitched_depth)
        raw = 0
        for distance in range(stitched_depth + 1, capacity + 1):
            batch = current + direction * distance
            sources = self._video_batch_sources(batch, cfg)
            if not sources or not all(source in ready for source in sources):
                break
            raw += 1
        return raw, raw_capacity, capacity

    def _mark_raw_batch_ready(self, vid, local, token, ready):
        with self._cache_guard:
            if token != self._window_token:
                return
            k = max(1, int(self.shared_config.count_per_action))
            start, end = self._batch_range(int(self.shared_config.video_num_list[vid]), k, local)
            lo, hi = self._raw_windows.get(vid, (0, 0))
            ready = ready and lo <= start and end < hi
            if ready:
                self._raw_ready_batches.add((vid, local))
            else:
                self._raw_ready_batches.discard((vid, local))

    def _mark_batch_processed(self):
        self.perf_monitor.mark_processed_batch()
        self._record_buffer_depth()
        self._maybe_tune_admission()
        self._maybe_evaluate_performance()
        self._refresh_playback_interval()

    def _pacing_context(self, token=None, config=None):
        config = self.shared_config if config is None else config
        return (self._window_token if token is None else token,
                1 if int(config.play_direction) >= 0 else -1)

    def _next_stitch_eta(self, batch, now):
        """Estimate the first missing PNG using in-memory queue/dependency state."""
        with self._cache_guard:
            raw = list(dict.fromkeys(f for f in self._pending_extract.values() if not f.done()))
            stitched = [f for f in self._window_stitches.values() if not f.done()]
            target = self._window_stitches.get((self._window_token, batch))
        if target is None:
            return None
        raw_default, stitch_default, _ = self.perf_monitor.buffer_latencies()
        def describe(future, default):
            timing = dict(getattr(future, 'video_timing', {}))
            return ProductionJob(future, timing.get('queued_at', now), timing.get('started_at'),
                timing.get('expected_seconds') or max(.001, default),
                tuple(getattr(dep, 'video_parent', dep) for dep in getattr(future, 'video_dependencies', ())))
        inputs = completion_estimates([describe(f, raw_default) for f in raw], self._extract_threads, now)
        snapshot=getattr(self,'_render_snapshot',None)
        params=snapshot[0].layout_params if snapshot is not None else ()
        pacer=getattr(self,'_playback_pacer',None)
        supply=pacer.supply_period(now) if pacer is not None else None
        if len(params)>38 and (params[32] or params[38]) and supply is not None:
            # Parent wall time includes algorithm/device/permit waits. Treating
            # it as a fresh CPU duration for every parent double-counted those
            # waits. Forecast multi-stage output from measured completions.
            cfg=self.shared_config;direction=1 if int(cfg.play_direction)>=0 else -1
            with self._cache_guard:
                rank=sum(0<direction*(getattr(f,'video_batch',batch)-int(cfg.batch_idx))<=direction*(batch-int(cfg.batch_idx))
                         and self._cached_batch_path(getattr(f,'video_batch',batch),validate=False) is None for f in stitched)
            raw_eta=max((inputs.get(getattr(dep,'video_parent',dep),0.) for dep in getattr(target,'video_dependencies',())),default=0.)
            return max(raw_eta,supply*max(1,rank))
        outputs = completion_estimates([describe(f, stitch_default) for f in stitched], self._stitch_threads, now, inputs)
        return outputs.get(target)

    def _refresh_playback_interval(self, model_period=None, reschedule=True):
        cfg = self.shared_config
        pacer = getattr(self, '_playback_pacer', None)
        if pacer is None or not cfg.video_mode or not cfg.is_playing:
            return
        if model_period is not None:
            self._pacing_model_period = model_period
        _, total = self._playback_video_indices()
        direction = 1 if int(cfg.play_direction) >= 0 else -1
        remaining = max(0, total - 1 - int(cfg.batch_idx) if direction > 0 else int(cfg.batch_idx))
        depth = min(remaining, self._compute_buffer_depth())
        with self.perf_monitor._lock:
            display = sorted(list(self.perf_monitor.display_history)[-12:])
        display_cost = display[int((len(display)-1)*.75)] if display else .001
        now = time.perf_counter()
        eta = self._next_stitch_eta(int(cfg.batch_idx) + direction * (depth+1), now) if remaining > depth else None
        fallback = self._pacing_model_period or max(display_cost,
            self.perf_monitor.service_estimates() / max(1, self._stitch_threads))
        with self._cache_guard:
            producing=bool(self._pending_extract) or bool(getattr(self,'_pending_stitch_async',0))
        interval, details = pacer.recommend(self._pacing_context(), now, depth,
            max(1, int(cfg.cache_num)), remaining, cfg.manual_interval, display_cost, fallback, eta,production_active=producing)
        cfg.interval_recommend = max(.001, math.ceil(interval * 1000 - 1e-9) / 1000.)
        cfg.interval_prediction = details
        self._apply_interval_recommendation(cfg.interval_recommend, reschedule=reschedule)

    def _playback_video_indices(self):
        cfg = self.shared_config
        total = page_count(cfg.video_num_list, cfg.count_per_action, cfg.parallel_to_sequential)
        segments = page_segments(cfg.video_num_list, cfg.count_per_action,
                                 int(cfg.batch_idx), cfg.parallel_to_sequential)
        return list(dict.fromkeys(video for video, first, stop in segments)), total

    def _decoder_working_set(self):
        dimensions = getattr(self, '_video_dimensions', {})
        pixels = max((int(w) * int(h) for w, h in dimensions.values()), default=1920 * 1080)
        return max(64 * 1024 ** 2, pixels * 32)

    def _planning_memory_budget(self):
        memory = getattr(self.shared_config, 'memory_budget', None)
        if memory is None:
            return None
        available = available_memory_bytes()
        # Mode fractions already reserve RAM for GUI/system. Do not apply the
        # old fixed 50% reserve again, which effectively erased Maximum's gain.
        memory = max(1, memory - getattr(getattr(self, '_pixel_cache', None), 'limit', 0) - getattr(getattr(self, '_decoder_bank', None), 'limit', 0))
        return min(memory, int(available * .9)) if available is not None else memory

    def _extract_memory_limit(self):
        memory = self._planning_memory_budget()
        if memory is None:
            return max(1, int(self.shared_config.thread) - 1)
        output, inputs = self._estimated_stitch_pixels()
        # Reserve a full composition before decoder lanes, including a dense
        # layout's decoded inputs, rather than reserving only a fixed 64 MiB.
        composition = max(64 * 1024 ** 2, 16 * output + 9 * inputs)
        return max(1, (memory - composition) // self._decoder_working_set())

    def _estimated_stitch_pixels(self):
        ui = self._ui()
        size = getattr(ui, 'img_size', None) if ui is not None else None
        dimensions = getattr(self, '_video_dimensions', {})
        areas = [int(dimensions.get(str(path), (0, 0))[0]) * int(dimensions.get(str(path), (0, 0))[1])
                 for path in self.shared_config.real_video_path]
        pixels = sum(areas) * max(1, int(self.shared_config.count_per_action))
        snapshot = getattr(self, '_render_snapshot', None)
        lazy = snapshot is not None and not snapshot[2] and not (len(snapshot[0].layout_params)>38 and snapshot[0].layout_params[38])
        valid_size = size is not None and len(size) == 2 and min(size) > 0
        output = int(size[0])*int(size[1]) if valid_size else pixels
        if lazy:
            # [-1,-1] is the initial GUI placeholder, NOT a one-pixel canvas.
            # A previous layout's measured size is also not evidence for the
            # new layout. Use geometry until a page from THIS context paints.
            pixels = max(areas, default=0)
            display_key = getattr(ui, '_video_display_key', None)
            same_layout = display_key is not None and getattr(self,'_window_token',None) is not None and display_key[-1] == self._window_token
            if not valid_size or not same_layout:
                params = snapshot[0].layout_params
                resolution = params[6]
                slots = max(1, len(areas)*int(self.shared_config.count_per_action))
                grid_slots = 1
                for grid in params[:3]:
                    if isinstance(grid,(list,tuple)) and len(grid)==2:
                        grid_slots *= max(1,int(grid[0]))*max(1,int(grid[1]))
                slots = max(slots,grid_slots)
                if len(params) > 39 and params[38]:
                    rows, cols = map(int, params[39].split(','))
                    slots *= max(1,rows)*max(1,cols)
                known=[dimensions[str(path)] for path in self.shared_config.real_video_path if str(path) in dimensions]
                if known and len(resolution)==2:
                    # Canvas memory depends on DISPLAY geometry. Treating
                    # automatic resolution as full-size tiles ignored scale
                    # and could reserve gigabytes for a small preview, forcing
                    # every power mode down to a single stitch lane.
                    width=max(value[0] for value in known)
                    height=max(value[1] for value in known)
                    if min(resolution)>0:width,height=resolution
                    elif resolution[0]>0:height=height*resolution[0]/min(value[0] for value in known);width=resolution[0]
                    elif resolution[1]>0:width=width*resolution[1]/min(value[1] for value in known);height=resolution[1]
                    scale=params[4] if len(params)>4 and params[4] is not None else (1,1)
                    gap=max([0]+[float(value) for value in params[3]]) if params[3] is not None else 0
                    title=params[17] if len(params)>17 else None
                    extra=2*float(title[8]) if title is not None and title[1] else 0
                    width=max(1,width*scale[0])+2*gap
                    height=max(1,height*scale[1])+2*gap+extra
                    output=math.ceil(width*height*slots*4)
                else:
                    output = max(areas,default=0)*slots*4
        return output, pixels or output

    def _stitch_thread_limit(self, maximum, extract_threads=None):
        output, pixels = self._estimated_stitch_pixels()
        memory = self._planning_memory_budget()
        available = available_memory_bytes()
        if memory is not None:
            memory = max(1, memory - (extract_threads or self._extract_threads) * self._decoder_working_set())
            available = memory * 2
        return stitch_memory_limit(output, pixels or output, available, maximum)

    def _maybe_evaluate_performance(self, force=False):
        """Seek the fastest measured pipeline rate, excluding pacing/wait time."""
        cfg = self.shared_config
        monitor = self.perf_monitor
        if not cfg.video_mode or not cfg.is_playing:
            return
        depth = self._compute_buffer_depth()
        inner = max(1, int(cfg.cache_num))
        play_direction = 1 if int(cfg.play_direction) >= 0 else -1
        pressure = [f for f in self._window_stitches.values() if not f.done()
                    and (getattr(f, 'video_batch', int(cfg.batch_idx)) - int(cfg.batch_idx)) * play_direction >= 0]
        ready_pressure = sum(not getattr(f, 'video_waiting_for_extract', False) for f in pressure)
        urgent_pressure = depth < inner and ready_pressure > self._stitch_threads
        inventory = self._raw_buffer_inventory(depth)
        stitched_thresholds = raw_thresholds = None
        priority = None
        if inventory is not None:
            raw_depth, raw_capacity, capacity = inventory
            raw_latency, stitch_latency, switch_latency = monitor.buffer_latencies()
            stitched_thresholds = buffer_levels(inner, capacity, cfg.interval, stitch_latency, switch_latency)
            raw_thresholds = buffer_levels(inner, raw_capacity, cfg.interval, raw_latency, switch_latency)
            previous = getattr(getattr(self, '_thread_allocator', None), 'buffer_priority', None)
            priority = buffer_priority(depth, raw_depth, stitched_thresholds, raw_thresholds, previous)
            urgent_pressure = ((priority == 'stitch' and ready_pressure > self._stitch_threads)
                               or (priority == 'raw' and len(set(self._pending_extract.values())) > self._extract_threads))
        if not force and not urgent_pressure and not monitor.should_evaluate():
            return
        if len(monitor.display_history) < (1 if force or urgent_pressure else 3):
            return
        indices, total = self._playback_video_indices()
        direction = 1 if int(cfg.play_direction) >= 0 else -1
        remaining = (total - 1 - int(cfg.batch_idx)) if direction > 0 else int(cfg.batch_idx)
        depth = self._compute_buffer_depth()
        cached = remaining >= 0 and depth >= remaining
        current = (self._extract_threads, self._stitch_threads)
        fresh_costs = monitor.stage_costs(indices, cached=cached, plan=current)
        costs = fresh_costs or monitor.stage_costs(indices, cached=cached)
        if costs is None:
            return
        monitor.mark_evaluated()
        extract_work, stitch_work, display_cost = costs
        budget = max(2, int(cfg.thread))
        extract_threads, stitch_threads = self._extract_threads, self._stitch_threads
        inner = max(1, int(cfg.cache_num))
        multiplier = max(1, int(getattr(cfg, 'cache_multiplier', 1)))
        span = max(1, min(total - 1, int(cfg.batch_idx) + inner * multiplier)
                   - max(0, int(cfg.batch_idx) - inner * multiplier) + 1)
        window = getattr(self, '_stitch_window', (0, -1))
        if window[0] <= int(cfg.batch_idx) <= window[1]:
            span = window[1] - window[0] + 1
        if not cached:
            # Joint solver considers other extraction counts; do not constrain
            # it to RAM left over by the CURRENT, possibly oversized decoder pool.
            span = self._stitch_thread_limit(span, extract_threads=1)
        extract_cap = max(1, len(indices)) * (5 if multiplier > 1 else 3)
        extract_cap = min(extract_cap, self._extract_memory_limit())
        # Configured workers beyond available work/memory do not add capacity.
        model_costs = (extract_work * extract_threads / min(extract_threads, extract_cap),
                       stitch_work * stitch_threads / min(stitch_threads, span), display_cost)

        actual_period = max(model_costs[0] / extract_threads, model_costs[1] / stitch_threads, display_cost)
        if not cached:
            profile = tuple(indices)
            if profile != getattr(self, '_thread_profile', profile):
                self._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
                self._optimizer_seen = {}
            self._thread_profile = profile
            allocator = getattr(self, '_thread_allocator', None)
            if allocator is None:
                allocator = self._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
            revisions = getattr(monitor, 'plan_revisions', {})
            revision = revisions.get(current, (len(monitor.extract_history), len(monitor.stitch_history)))
            seen = getattr(self, '_optimizer_seen', {})
            stamp = (id(monitor), current, profile)
            usable = fresh_costs is not None or not revisions
            if usable and seen.get(stamp) != revision:
                allocator.observe(current, *model_costs)
                seen[stamp] = revision
                self._optimizer_seen = seen
            pending_stitches = [f for f in self._window_stitches.values()
                if (getattr(f, 'video_batch', int(cfg.batch_idx)) - int(cfg.batch_idx)) * direction >= 0]
            waiting = sum(not f.done() and getattr(f, 'video_waiting_for_extract', False) for f in pending_stitches)
            ready = sum(not f.done() and not getattr(f, 'video_waiting_for_extract', False) for f in pending_stitches)
            output, inputs = self._estimated_stitch_pixels()
            owner = self._ui()
            resource_monitor = getattr(owner, 'resource_monitor', None) if owner is not None else None
            resource_stats = resource_monitor.read_snapshot() if resource_monitor is not None else {}
            cpu_usage = resource_stats.get('cpu')
            cpu_target = min(100., budget / max(1, os.cpu_count() or 1) * 100)
            cpu_headroom = cpu_usage is not None and cpu_usage < cpu_target * .85
            proposal = allocator.recommend(budget, model_costs, current, extract_cap, span,
                                             allow_probe=usable and depth >= min(inner, max(1, remaining)),
                                             extract_backlog=len(set(self._pending_extract.values())),
                                             stitch_waiting=waiting, stitch_ready=ready,
                                             buffer_depth=depth, buffer_target=inner,
                                             memory_budget=self._planning_memory_budget(),
                                             extract_memory=self._decoder_working_set(),
                                             stitch_memory=max(64 * 1024 ** 2, 16 * output + 9 * inputs),
                                             raw_buffer_depth=inventory[0] if inventory is not None else None,
                                             stitched_levels=stitched_thresholds, raw_levels=raw_thresholds,
                                             cpu_headroom=cpu_headroom, power_mode=getattr(cfg, 'power_mode', 2))
            self.shared_config.thread_allocation_recommend = {
                'extract': proposal.extract, 'stitch': proposal.stitch,
                'estimated_period': proposal.period, 'reason': proposal.reason,
                'stitch_task_limit': span,
                'raw_buffer': inventory[0] if inventory is not None else None,
                'stitched_buffer': depth,
                'stitched_levels': stitched_thresholds,
                'raw_levels': raw_thresholds,
                'cpu_headroom': cpu_headroom,
            }
            busy = bool(self._pending_extract or self._window_stitches or self.cache_update_pending())
            now = time.perf_counter()
            urgent = proposal.reason in ('downstream-starved', 'ready-backlog', 'upstream-starved', 'capacity',
                                         'stitch-buffer-low', 'raw-buffer-low')
            may_apply = usable or proposal.reason in ('downstream-starved', 'ready-backlog',
                                                     'stitch-buffer-low', 'raw-buffer-low', 'ready-capacity')
            critical = (stitched_thresholds is not None and priority == 'stitch' and depth <= stitched_thresholds.critical
                        or raw_thresholds is not None and priority == 'raw' and inventory[0] <= raw_thresholds.critical)
            stable = (now - getattr(self, '_last_thread_resize', 0.0) >= (.1 if critical else .25) if urgent
                      else now >= self._cooldown_deadline and depth >= min(inner, max(1, remaining)))
            if ((proposal.extract, proposal.stitch) != current and may_apply
                    and getattr(self, '_pending_thread_plan', None) is None
                    and stable):
                if busy:
                    self._request_thread_plan(proposal.extract, proposal.stitch)
                else:
                    self._apply_thread_plan(proposal.extract, proposal.stitch)
                    self._cooldown_deadline = now + 2.0
                    actual_period = max(proposal.period, display_cost)

        if getattr(self, '_playback_pacer', None) is not None:
            self._refresh_playback_interval(actual_period)
            return
        # Compatibility for model-only, headless owners without the live pacer.
        target = max(0.001, math.ceil(actual_period * 1.02 * 1000 - 1e-9) / 1000.0)
        cfg.interval_recommend = target
        # Speed up when production has at least one future frame ready. An empty
        # queue can slow playback, but must not trigger an unverified speed-up.
        if target < float(cfg.interval) and remaining > 0 and depth == 0:
            return
        self._apply_interval_recommendation(target)

    def _debug_video(self, message):
        if getattr(self.shared_config, "debug_video", False):
            print(message)

    def calc_max_extractable_frames_single(self, video_path):
        '''Using FFmpeg to retrieve video information, replacing cv2.VideoCapture'''
        step = self.shared_config.skip_frames + 1
        fps, total = self._get_meta(video_path)
        viewable = max(1, (total + step - 1) // step) if total > 0 else 1
        self.shared_config.video_fps_list.append(fps)
        self.shared_config.video_num_list.append(viewable)

    def _video_command(self, name):
        return getattr(self, '_video_tools', {}).get(name, name)

    def _video_process_options(self):
        return dict(env=getattr(self, '_video_tools_env', None),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def _probe_json(self, args, what="ffprobe"):
        '''Run ffprobe and parse its JSON output.

        ffprobe writes UTF-8. On a Chinese-locale Windows the default text codec
        is cp936(GBK), so letting subprocess decode it raises UnicodeDecodeError
        inside its reader thread, which leaves stdout as None and used to
        surface as a bogus "no video stream found".
        '''
        cp = run_video_process(
            [self._video_command('ffprobe'), "-v", "error"] + [str(a) for a in args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **self._video_process_options(),
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"{what} failed (code={cp.returncode}): {(cp.stderr or '').strip()}"
            )
        try:
            return json.loads(cp.stdout or "{}")
        except Exception as ex:
            raise RuntimeError(f"{what} json parse failed: {ex}")

    def _get_meta(self, video_path):
        '''How to get the FPS and total frame count of a video using FFmpeg'''
        if video_path in self._meta_cache:
            return self._meta_cache[video_path]

        p = None
        probe_fn = getattr(ffmpeg, "probe", None)
        if callable(probe_fn):
            try:
                p = probe_fn(str(video_path))
            except Exception as ex:
                self._debug_video(f"[Metadata] ffmpeg.probe failed: {ex}")

        if not p:
            p = self._probe_json(
                [
                    "-print_format", "json",
                    "-show_streams",
                    "-show_format",
                    str(video_path),
                ],
                what="ffprobe",
            )

        streams = p.get("streams", []) if isinstance(p, dict) else []
        vs = next((s for s in streams if s.get('codec_type') == 'video'), None)
        if vs is None:
            raise RuntimeError("no video stream found")
        self._video_dimensions[str(video_path)] = (int(vs.get('width') or 0), int(vs.get('height') or 0))

        rate = vs.get('avg_frame_rate') or vs.get('r_frame_rate') or '0/1'
        fps = float(Fraction(rate)) if rate not in ('0/0', '0/1', None, '') else 0.0

        total = 0
        nb = vs.get('nb_frames')
        try:
            if nb is not None:
                total = int(nb)
        except Exception:
            total = 0

        if total <= 0:
            tags = vs.get("tags", {}) or {}
            for key in ("NUMBER_OF_FRAMES", "NUMBER_OF_FRAMES-eng", "number_of_frames"):
                value = tags.get(key)
                if value:
                    try:
                        total = int(value)
                        break
                    except Exception:
                        pass

        if total <= 0:
            try:
                cp = run_video_process(
                    [
                        self._video_command('ffprobe'),
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-count_frames",
                        "-show_entries", "stream=nb_read_frames",
                        "-of", "default=nw=1:nk=1",
                        str(video_path),
                    ],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    **self._video_process_options(),
                )
                probe_txt = (cp.stdout or "").strip().splitlines()
                if probe_txt:
                    total = int(probe_txt[-1].strip())
            except Exception:
                pass

        dur = float(vs.get('duration') or p.get('format', {}).get('duration') or 0)
        if total <= 0 and fps > 0 and dur > 0:
            total = int(round(dur * fps))

        if fps <= 0 and total > 0 and dur > 0:
            fps = total / dur

        if total <= 0:
            # At least allow the first frame to be rendered to prevent the UI from remaining in a permanent "Waiting" state
            total = 1

        # Seeking by timestamp is reliable for ordinary CFR streams whose
        # reported frame rates and duration agree. Keep uncertain streams on
        # the absolute-frame path below.
        try:
            average_rate = Fraction(vs.get('avg_frame_rate') or '0/1')
            nominal_rate = Fraction(vs.get('r_frame_rate') or '0/1')
            reported_frames = int(vs.get('nb_frames') or 0)
            stream_duration = float(vs.get('duration') or 0)
            stream_start = float(vs.get('start_time') or 0)
            self._fast_seek_paths[str(video_path)] = (
                average_rate > 0
                and average_rate == nominal_rate
                and reported_frames > 0
                and stream_duration > 0
                and abs(stream_start) < 0.001
                and abs(reported_frames / fps - stream_duration) <= max(0.1, 2 / fps)
            )
        except (TypeError, ValueError, ZeroDivisionError):
            self._fast_seek_paths[str(video_path)] = False

        self._meta_cache[video_path] = (fps, total)
        return self._meta_cache[video_path]

    def init_video_frame_cache(self):
        with self._cache_io_lock:
            return self._init_video_frame_cache_locked()

    def _init_video_frame_cache_locked(self):
        '''Initialize video cache directories (folders only).'''
        video_paths = self.shared_config.real_video_path
        output_list = []

        for source_index, video_path in enumerate(video_paths):
            video_path = Path(video_path)
            out_dir = self.cache_dir / "sources" / "video" / f"source_{source_index+1:03d}" / "frames"
            out_dir.mkdir(parents=True, exist_ok=True)
            # Clean stale cache to avoid reading old frames when names/settings change
            try:
                for name in os.listdir(out_dir):
                    if name.endswith(".jpeg") or name.startswith("__tmp_"):
                        p = out_dir / name
                        if p.is_file():
                            p.unlink()
            except Exception as ex:
                self._debug_video(f"[CacheDir] cleanup failed {out_dir}: {ex}")
            output_list.append(str(out_dir))
        self.shared_config.video_path = output_list

    def update_thread_count(self, frame_num=-1):
        '''
        Adjust the thread budget so extract/stitch threads do not exceed user settings.
        '''
        try:
            new_total = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        except Exception:
            new_total = 2
        self._total_threads = new_total
        self._enforce_thread_budget()

        # Immediately print the new thread allocation
        if getattr(self.shared_config, "debug_thread", False):
            print(f"[ThreadUpdate] total_budget={self._total_threads}, extract={self._extract_threads}, stitch={self._stitch_threads}")

    def update_cache(self):
        """Capture GUI inputs and coalesce requests; never scan files on the GUI."""
        if (getattr(self, '_closed', False) or not self.shared_config.video_mode
                or not self.shared_config.video_path):
            return
        self._cache_context_changed()
        ui = self._ui()
        if (ui is not None and hasattr(ui, '_capture_video_render_snapshot')
                and self.shared_config.video_num_list and self.shared_config.video_fps_list):
            ui._capture_video_render_snapshot()
        config = copy.copy(self.shared_config)
        for name in ('video_path', 'real_video_path', 'video_num_list', 'video_fps_list'):
            setattr(config, name, tuple(getattr(config, name)))
        self._enqueue_cache_config(config)

    def _enqueue_cache_config(self, config, only_if_empty=False):
        """Worker-safe rescheduling after queued work yields to a new plan."""
        with self._cache_request_lock:
            if only_if_empty and self._cache_request is not None:
                return
            self._cache_request_serial += 1
            self._cache_request = (self._cache_request_serial, config,
                                   getattr(self, '_window_generation', 0))
            if self._cache_update_future is None or self._cache_update_future.done():
                def drain():
                    while True:
                        if getattr(self, '_pending_thread_plan', None) is not None:
                            self._rebalance_thread_pools()
                        with self._cache_request_lock:
                            request = self._cache_request
                            self._cache_request = None
                            if request is None or getattr(self, '_closed', False):
                                self._cache_update_future = None
                                return
                        try:
                            self._update_cache_worker(*request)
                        except Exception as ex:
                            self._set_video_status(f'Video cache update failed: {ex}')
                self._cache_update_future = self._cache_executor.submit(drain)

    def cache_update_pending(self):
        future = getattr(self, '_cache_update_future', None)
        return future is not None and not future.done()

    def _update_cache_worker(self, serial, cfg, generation):
        """Prioritize the inner window; batch-prefetch and retain the outer window.

        No decoding, stitching, image loading or cleanup blocks the caller.
        Each contiguous missing run reuses one decoder lease. Per-batch
        completion handles release stitches before the entire run finishes.
        """
        if getattr(self, '_closed', False) or not cfg.video_mode or not cfg.video_path:
            return
        if not cfg.video_num_list or not cfg.video_fps_list:
            for path in cfg.real_video_path:
                self.calc_max_extractable_frames_single(path)
            ui = self._ui()
            if ui is not None and hasattr(ui, '_rebuild_video_cache_and_show'):
                wx.CallAfter(ui._rebuild_video_cache_and_show)
            return
        output, inputs = self._estimated_stitch_pixels()
        geometry = (int(self.shared_config.thread),self.shared_config.memory_budget,output,inputs)
        if geometry != getattr(self,'_admission_geometry',None):
            self._admission_geometry = geometry
            snapshot=getattr(self,'_render_snapshot',None)
            params=snapshot[0].layout_params if snapshot is not None else ()
            processing=len(params)>38 and (snapshot[2] or params[38])
            if processing or self._extract_threads+self._stitch_threads < int(self.shared_config.thread):
                # The initial policy may have been seeded before the GUI's
                # layout snapshot existed. Replan NOW, not after first paint.
                self._enforce_thread_budget()
        self._initialize_thread_pools()
        k = max(1, int(cfg.count_per_action))
        inner = max(1, int(cfg.cache_num))
        multiplier = max(1, int(getattr(cfg, "cache_multiplier", 1)))
        outer = inner * multiplier
        counts = [(int(n) + k - 1) // k for n in cfg.video_num_list]
        sequential = bool(cfg.parallel_to_sequential)
        total = page_count(cfg.video_num_list, k, sequential)
        if total <= 0:
            return
        b = max(0, min(int(cfg.batch_idx), total - 1))
        lo, hi = max(0, b - outer), min(total - 1, b + outer)

        def sources(batch):
            return self._video_batch_sources(batch, cfg)

        with self._cache_guard:
            if (serial != self._cache_request_serial or generation != getattr(self, '_window_generation', 0)
                    or self._cache_context_token(cfg) != self._cache_context_token()):
                return
            cfg.cache_img = self.shared_config.cache_img
            token = (self._cache_context_token(cfg), generation)
            # For multiplier >= 2, refill when either expandable edge is at
            # most cache_num batches away (including equality).
            # Moving the outer boundary at every step would still launch one
            # decoder per new edge frame, defeating the purpose of batching.
            old_lo, old_hi = self._stitch_window
            guard = inner
            if cfg.is_playing and multiplier >= 2:
                lead = self._playback_pacer.first_ready_delay()
                supply = self._playback_pacer.supply_period()
                if lead is not None:
                    capacity_period = self._pacing_model_period or float(cfg.interval)
                    if supply is not None:
                        capacity_period = min(supply, capacity_period)
                    period = max(cfg.manual_interval or .001, capacity_period)
                    guard = refill_guard(inner, multiplier, period, lead)
                if self._decoder_bank.available:
                    # Persistent codecs have no per-refill process startup.
                    # Refill while the INNER edge is still R pages from the
                    # outer edge, instead of waiting for the center to get R
                    # pages away. Keep at least one new page per move.
                    guard = min(outer-1, max(guard, 2*inner))
            near_edge = multiplier >= 2 and (
                (old_lo > 0 and b - old_lo <= guard)
                or (old_hi < total - 1 and old_hi - b <= guard)
            )
            if (token == self._window_token and outer == getattr(self, "_outer_radius", None)
                    and not near_edge
                    and old_lo <= max(0, b - inner)
                    and min(total - 1, b + inner) <= old_hi):
                lo, hi = old_lo, old_hi
            self._outer_radius = outer
            if token != self._window_token:
                for future in set(self._pending_extract.values()):
                    future.cancel()
                self._pending_extract.clear()
                self._window_token = token
            self._stitch_window = (lo, hi)
            for old_batch in list(self._batch_render_states):
                if not lo <= old_batch <= hi:
                    self._batch_render_states.pop(old_batch, None)
            for (old_token, batch), future in list(self._window_stitches.items()):
                if old_token != token or not lo <= batch <= hi:
                    future.cancel()
            self._raw_windows = {}
            for batch in range(lo, hi + 1):
                for vid, local in sources(batch):
                    start, end = self._batch_range(int(cfg.video_num_list[vid]), k, local)
                    old = self._raw_windows.get(vid, (start, end + 1))
                    self._raw_windows[vid] = (min(old[0], start), max(old[1], end + 1))
            self._raw_ready_batches = {(vid, local) for vid, local in self._raw_ready_batches
                if vid in self._raw_windows
                and self._raw_windows[vid][0] <= local * k
                and min((local + 1) * k, int(cfg.video_num_list[vid])) <= self._raw_windows[vid][1]}
            if len(cfg.cache_img) <= hi:
                cfg.cache_img.extend([None] * (hi + 1 - len(cfg.cache_img)))
            if old_lo != lo or old_hi != hi:
                self._schedule_video_cleanup()

        ui=self._ui()
        processing=getattr(getattr(ui,'image_pipeline',None),'processing',None)
        if processing is not None:
            processing.set_window('video',('video',tuple(cfg.real_video_path),cfg.skip_frames),(lo,hi),b,
                active_cache_names(self._render_snapshot[0]) if self._render_snapshot is not None else None)
            processing._prune()
        snapshot=getattr(self,'_render_snapshot',None)
        catalog_key=(tuple(cfg.real_video_path),cfg.parallel_to_sequential,bool(snapshot and snapshot[0].layout_params[22]))
        if snapshot is not None and catalog_key!=getattr(self,'_source_catalog_key',None):
            self._source_catalog_key=catalog_key
            write_source_catalog(snapshot[0],self.cache_dir,split_media=True)
        allowed_pixels = {str(self._get_disk_cache_path(batch)) for batch in range(lo, hi+1)}
        for vid, (first, last) in self._raw_windows.items():
            allowed_pixels.update(os.path.join(cfg.video_path[vid], self._filename_converter(i, vid, cfg))
                                  for i in range(first, last))
        self._pixel_cache.prune(allowed_pixels)
        # The GUI displays the previous frame while the requested one is prepared.
        direction = -1 if int(getattr(cfg, 'play_direction', 1)) < 0 else 1
        # Registration and PNG publication share the same state lock. A PNG
        # finishing between the missing scan and request must not leave a
        # phantom pending page that makes full-cache idle look like production.
        with self._cache_guard:
            wanted = [batch for batch in range(lo, hi+1)
                      if direction*(batch-b)>=0 and self._cached_batch_path(batch, validate=False) is None]
            self._playback_pacer.request(self._pacing_context(token, cfg), wanted, (lo, hi),
                                         b, direction, time.perf_counter())
        streaming = cfg.is_playing and self._decoder_bank.available
        if not streaming and self._cached_batch_path(b, validate=False) is None:
            for vid, local in sources(b):
                self._queue_extract_run(vid, local, local, token, cfg)
            self._queue_window_stitch(b, sources(b), token)

        direction = -1 if int(getattr(cfg, "play_direction", 1)) < 0 else 1
        # Playback prioritizes forward supply before reverse prefetch.
        stages = []
        ranges = ((1, inner), (inner + 1, max(b-lo, hi-b)))
        ordering = ([(sign, first, last) for sign in (direction, -direction) for first, last in ranges]
                    if cfg.is_playing else
                    [(sign, first, last) for first, last in ranges for sign in (direction, -direction)])
        for sign, first, last in ordering:
            stages.append([b + sign * d for d in range(first, last + 1)
                           if lo <= b + sign * d <= hi])
        if streaming:
            stages = [[b] + [b + direction*d for d in range(1, max(b-lo, hi-b)+1)
                              if lo <= b + direction*d <= hi],
                      [b - direction*d for d in range(1, max(b-lo, hi-b)+1)
                       if lo <= b - direction*d <= hi]]
        for batches in stages:
            if serial != self._cache_request_serial or token != self._window_token:
                return
            needed = [t for t in batches if self._cached_batch_path(t, validate=False) is None]
            runs = {}
            for batch in needed:
                for vid, local in sources(batch):
                    runs.setdefault(vid, []).append(local)
            for vid, locals_ in runs.items():
                self._queue_extract_run(vid, min(locals_), max(locals_), token, cfg)
            for batch in needed:
                self._queue_window_stitch(batch, sources(batch), token)
        self._last_batch = b
        ui = self._ui()
        if (ui is not None and hasattr(ui, '_video_frame_ready')
                and serial == self._cache_request_serial and int(self.shared_config.batch_idx) == b
                and self._cached_batch_path(b, validate=False) is not None):
            wx.CallAfter(ui._video_frame_ready, b, token)

    def _trim_video_window(self):
        """Scan and mutate files on workers; state locks never span file I/O."""
        with self._cache_guard:
            token = self._window_token
            window = self._stitch_window
            raw_windows = dict(self._raw_windows)
            config = copy.copy(self.shared_config)
            generation = getattr(self, '_window_generation', 0)
            paths = tuple(config.video_path)
        def current():
            return (token == self._window_token and generation == getattr(self, '_window_generation', 0)
                    and paths == tuple(self.shared_config.video_path))
        self._decoder_bank.trim(set(str(p) for p in config.real_video_path))
        for path in self.disk_cache_dir.glob("page_*.png"):
            try:
                idx = int(path.stem.split('_')[1])-1
                with self._cache_io_lock:
                    with self._cache_guard:
                        if not current() or window != self._stitch_window:
                            return
                        cache = self.shared_config.cache_img
                        remove = not window[0] <= idx <= window[1] or idx >= len(cache) or cache[idx] != str(path)
                    if remove:
                        path.unlink()
                        with self._cache_guard:
                            if cache is self.shared_config.cache_img and idx < len(cache):
                                cache[idx] = None
            except (OSError, ValueError):
                pass
        for vid, directory in enumerate(config.video_path):
            start, end = raw_windows.get(vid, (0, 0))
            names = {self._filename_converter(i, vid, config) for i in range(start, end)}
            for path in Path(directory).glob("*.jpeg"):
                if path.name.startswith("__tmp_") or path.name in names:
                    continue
                with self._raw_io_lock(vid, config):
                    with self._cache_guard:
                        if not current() or raw_windows != self._raw_windows:
                            return
                    try:
                        path.unlink()
                    except OSError:
                        pass

        # Retire obsolete directories quickly, then delete them without holding
        # the state lock. Both resolved targets must remain inside cache_dir.
        reserved_paths = [Path(p) for p in config.video_path]
        reserved_paths.extend(self._shared_cache_directories())
        # Active directories need no filesystem canonicalization on every
        # refill. Unknown candidates still receive ALL resolved-path safety
        # checks before any rename/delete, including aliases/junctions.
        reserved_names = {os.path.normcase(os.path.abspath(p)) for p in reserved_paths}
        try:
            directories = [p for p in self.cache_dir.iterdir()
                           if os.path.normcase(os.path.abspath(p)) not in reserved_names]
        except OSError:
            return
        if not directories:
            self._cleanup_source_folders(config.video_path,current)
            return
        root = self.cache_dir.resolve()
        reserved = {p.resolve() for p in reserved_paths}
        for directory in directories:
            if not directory.is_dir() or directory.resolve().parent != root:
                continue
            if directory.resolve() in reserved:
                continue
            retired = self.cache_dir / f"__discard_{os.getpid()}_{time.time_ns()}"
            if retired.resolve().parent != root:
                continue
            with self._cache_io_lock:
                with self._cache_guard:
                    if not current():
                        return
                try:
                    directory.rename(retired)
                except OSError:
                    continue
                if not current():
                    if not directory.exists():
                        retired.rename(directory)
                    return
            shutil.rmtree(str(retired), ignore_errors=True)
        if current():self._cleanup_source_folders(config.video_path,current)

    def _cleanup_source_folders(self, paths, valid=lambda:True):
        source_root=self.cache_dir/'sources'/'video'
        active={os.path.normcase(os.path.abspath(Path(p).parent)) for p in paths}
        if not source_root.exists():return
        for directory in source_root.iterdir():
            if os.path.normcase(os.path.abspath(directory)) in active:continue
            if (directory/'frames').is_dir() and directory.resolve().parent==source_root.resolve():
                retired=self.cache_dir/f'__discard_source_{os.getpid()}_{time.time_ns()}'
                if retired.resolve().parent!=self.cache_dir.resolve():continue
                with self._cache_io_lock:
                    if not valid() or tuple(paths)!=tuple(self.shared_config.video_path):return
                    try:directory.rename(retired)
                    except OSError:continue
                shutil.rmtree(str(retired),ignore_errors=True)

    def _schedule_video_cleanup(self):
        with self._cache_guard:
            if getattr(self, '_closed', False):
                return
            self._cleanup_revision = getattr(self, "_cleanup_revision", 0) + 1
            if self._cleanup_future is None or self._cleanup_future.done():
                def drain():
                    while True:
                        with self._cache_guard:
                            revision = self._cleanup_revision
                        self._trim_video_window()
                        with self._cache_guard:
                            if revision == self._cleanup_revision:
                                self._cleanup_future = None
                                return
                self._cleanup_future = self._maintenance_executor.submit(drain)

    def _queue_extract_run(self, vid, first, last, token, config=None):
        """Coalesce unknown neighboring batches and publish each batch early."""
        futures = []
        config = self.shared_config if config is None else config
        k = max(1, int(config.count_per_action))
        n = int(config.video_num_list[vid])
        with self._cache_guard:
            ready = set(self._raw_ready_batches)
            pending_keys = set(self._pending_extract)
        missing = {}
        for local in range(first, last + 1):
            key = (vid,local)
            if key in ready:
                missing[local] = False
            elif key in pending_keys:
                missing[local] = None  # Pending is NOT proof that pixels exist.
            else:
                start, end = self._batch_range(n, k, local)
                missing[local] = bool(self._list_missing_range(vid, start, end, config))
        with self._cache_guard:
            if token != self._window_token:
                return []
            for local, is_missing in missing.items():
                if is_missing is not None:
                    self._mark_raw_batch_ready(vid, local, token, not is_missing)
            run = []

            def submit():
                if not run:
                    return
                keys = tuple((vid, t) for t in run)
                batch_futures = {key: Future() for key in keys}
                self._raw_batch_futures.update(batch_futures)
                worker_plan = (self._extract_threads, self._stitch_threads)
                timing = dict(queued_at=time.perf_counter(), started_at=None,
                              expected_seconds=self.perf_monitor.service_estimates(vid))
                start = run[0] * k
                end = min(n - 1, (run[-1] + 1) * k - 1)
                path = config.real_video_path[vid]
                streams = 1 if config.parallel_to_sequential else max(1,len(config.real_video_path))
                native_threads = max(1,self._extract_threads//streams) if self._decoder_bank.available else 1

                def extract():
                    timing['started_at'] = time.perf_counter()
                    worker_plan = (self._extract_threads, self._stitch_threads)
                    self._worker_context.token = token
                    self._worker_context.plan = worker_plan
                    try:
                        with self._cache_guard:
                            keep_start, keep_end = self._raw_windows.get(vid, (0, 0))
                            active_start, active_end = max(start, keep_start), min(end, keep_end - 1)
                        self._worker_context.native_threads = getattr(future,'pipeline_cpu_cost',1)
                        if token == self._window_token and active_start <= active_end:
                            self._save_frame(path, active_start, active_end, vid, config=config)
                            for _, local in keys:
                                self._publish_raw_ready(vid, local, token, config)
                    finally:
                        # Window/context changes already request a coalesced
                        # cleanup. Every frame publication checks that window;
                        # do not rescan 100 directories after EACH decoder run.
                        del self._worker_context.token
                        del self._worker_context.plan
                        del self._worker_context.native_threads

                future = self.executor.submit(extract, resource_key=vid, cpu_cost=native_threads)
                future.video_timing = timing
                for key in keys:
                    self._raw_batch_futures[key].video_parent = future
                for key in keys:
                    self._pending_extract[key] = future
                futures.append(future)

                def done(completed):
                    with self._cache_guard:
                        for key in keys:
                            if self._pending_extract.get(key) is completed:
                                self._pending_extract.pop(key, None)
                        for key, handle in batch_futures.items():
                            if self._raw_batch_futures.get(key) is handle:
                                self._raw_batch_futures.pop(key, None)
                        for frame_future in batch_futures.values():
                            if frame_future is not None and not frame_future.done():
                                if completed.cancelled():
                                    frame_future.cancel()
                                else:
                                    frame_future.set_result(False)
                future.add_done_callback(done)
                run.clear()

            for local in range(first, last + 1):
                pending = self._pending_extract.get((vid, local))
                if pending is not None or not missing[local]:
                    submit()
                    if pending is not None:
                        futures.append(pending)
                else:
                    run.append(local)
            submit()
        return futures

    def _run_window_stitch(self,batch,sources,token,plan=None):
        return self._run_window_stitch_impl(batch,sources,token,plan)

    def _run_window_stitch_impl(self, batch, sources, token, plan=None, _processed=None, _processing_seconds=0, _composition_budget=None, _mosaic_output=None):
        with self._cache_guard:
            lo, hi = self._stitch_window
            if token != self._window_token or not lo <= batch <= hi:
                return
            if self._cached_batch_path(batch, validate=False) is not None:
                return
            # Do not publish incomplete multi-video composites after decode failure.
            config = copy.copy(self.shared_config)
            snapshot = self._render_snapshot
            single = config.parallel_to_sequential or len(config.video_path) == 1
        k = max(1, int(config.count_per_action))
        for vid, local in sources:
            start, end = self._batch_range(int(config.video_num_list[vid]), k, local)
            with self._cache_guard:
                known_ready = (vid, local) in self._raw_ready_batches
            missing = [] if known_ready else self._list_missing_range(vid, start, end, config)
            self._mark_raw_batch_ready(vid, local, token, not missing)
            if missing:
                return
        raw_groups = [self._collect_batch_frame_paths(vid, local, config) for vid, local in sources]
        frames = {}
        for (vid, local), group in zip(sources, raw_groups):
            first, last = self._batch_range(int(config.video_num_list[vid]), k, local)
            frames.update({(vid, first+offset): path for offset, path in enumerate(group)})
        segments = page_segments(config.video_num_list, k, batch, config.parallel_to_sequential)
        display_sources = [(vid, index) for vid, first, stop in segments for index in range(first, stop)]
        groups = ([[frames[(vid, index)] for index in range(first, stop)] for vid, first, stop in segments]
                  if snapshot is not None else raw_groups)
        ui = self._ui()
        processing = getattr(getattr(ui, 'image_pipeline', None), 'processing', None)
        if processing is not None:processing.pixel_cache=self._pixel_cache
        if snapshot is not None and processing is not None and _processed is None:
            template = snapshot[0]
            params = template.layout_params
            if len(params)>38 and getattr(template,'_custom_algorithm_registry',None) is not None:
                epoch=('video',tuple(config.real_video_path),config.skip_frames)
                # Original-only pages have one compute task per admitted
                # parent stitch. PipelineWorkers already charges that lane
                # and its memory, including borrowed idle decoder lanes.
                # Applying the stitch reservation again here serialized all
                # borrowed pages when the reservation was only one.
                custom=bool(params[32] or params[38])
                downstream=self._pipeline_workers.total_budget
                processing.configure(downstream,self._planning_memory_budget(),
                    capacity=self._pipeline_workers.downstream_capacity if custom else None)
                processing.set_window('video',epoch,self._stitch_window,int(config.batch_idx),active_cache_names(template))
                flist=[path for group in groups for path in group]
                def cancelled():return getattr(self,'_closed',False) or token!=self._window_token
                processing_started=time.perf_counter()
                with processing.mosaic_stage.plan(template,flist,batch,'video',epoch,snapshot[1],cancelled) as mosaic_plan:
                    with processing.prepare(template,flist,batch,'video',epoch,cancelled,on_ready=mosaic_plan.ready) as results:
                        output=mosaic_plan.compose(results)
                        delay=time.perf_counter()-processing_started
                        return self._run_window_stitch_impl(batch,sources,token,plan=plan,_processed=results,
                            _processing_seconds=delay,_mosaic_output=output)
        # No cache guard spans pixel processing or PNG compression.
        started = time.perf_counter()
        if snapshot is None:
            # Compatibility for headless owners providing a pure compose method.
            ui = self._ui()
            pil_img, flag = ui.compose_current_frame(batch, flist=groups[0] if single else groups)
            state = {}
        elif _mosaic_output is None:
            template, points, custom = snapshot
            manager = template.video_stitch_snapshot()
            if _processed is not None:manager._custom_results=_processed
            manager._video_lazy_frames = _processed is not None or (not custom and not (len(template.layout_params) > 38 and template.layout_params[38]))
            manager._video_pixel_provider = self._pixel_cache.get
            working = self._planning_memory_budget()
            if _processed is not None:
                manager._video_memory_budget=_composition_budget
            elif working is not None:
                _, inputs = self._estimated_stitch_pixels()
                per_page = min(working, self._pipeline_workers.costs[1])
                manager._custom_memory_budget = per_page
                if not manager._video_lazy_frames and inputs*9 >= per_page:
                    self._set_video_status('Video layout/custom processing exceeds the memory budget; reduce layout or preview size')
                    return
                manager._video_memory_budget = max(1, per_page - inputs*9)
            manager.set_action_count(batch)
            flist = [path for group in groups for path in group] if single else groups
            if custom:
                manager.layout_params[32] = True
                manager.stitch_images(0, copy.deepcopy(points), flist=flist)
                manager.layout_params[32] = False
            flag = manager.stitch_images(0, copy.deepcopy(points), flist=flist)
            pil_img = manager.show_stitch_img_and_customfunc_img(custom) if flag == 0 else None
            state = {name: getattr(manager, name) for name in (
                'xy_grid', 'xy_grids_id_list', 'crop_points', 'img_resolution_origin',
                'img_resolution_show', 'gap_color', 'title_setting', 'title_max_size', 'pdf_title_layers',
                '_last_title_layout', 'flist', '_flist_groups', '_status_source_slots',
                '_show_all_func_enabled', '_show_all_func_layout', '_original_row_col',
                '_show_all_func_expanded_row_col', '_func_layout_vertical', '_blank_img_ids',
            ) if hasattr(manager, name)}
        else:
            pil_img,state=_mosaic_output
            flag=0
        if snapshot is not None:
            state['_status_video_sources'] = tuple(display_sources)
            state['_status_video_paths'] = tuple(config.real_video_path)
            state['_status_video_counts'] = tuple(config.video_num_list)
            state['_status_video_fps'] = tuple(config.video_fps_list)
            state['_status_video_step'] = max(1, int(config.skip_frames)+1)
            state['_status_input_mode'] = getattr(config, 'status_input_mode', 0)
        if pil_img is None or flag != 0:
            with self._cache_guard:
                if token == self._window_token:
                    self._raw_ready_batches.difference_update(sources)
            self._set_video_status(f"Video stitch failed: batch={batch}, flag={flag}")
            return
        temporary = self.disk_cache_dir / f"__tmp_batch_{batch}_{threading.get_ident()}_{time.time_ns()}.png"
        try:
            pil_img.save(str(temporary), format='PNG', compress_level=1)
            with self._cache_io_lock:
                with self._cache_guard:
                    lo, hi = self._stitch_window
                    if token != self._window_token or not lo <= batch <= hi:
                        return
                destination = self._get_disk_cache_path(batch)
                os.replace(str(temporary), str(destination))
                with self._cache_guard:
                    lo, hi = self._stitch_window
                    valid = token == self._window_token and lo <= batch <= hi
                    if valid:
                        pixels=pil_img if isinstance(pil_img,Image.Image) else self._pixel_cache.get(str(pil_img.path))
                        if pixels is not None:self._pixel_cache.put(str(destination),pixels,priority=True)
                        self.shared_config.cache_img[batch] = str(destination)
                        self._batch_render_states[batch] = state
                        for old_batch in list(self._batch_render_states):
                            if not lo <= old_batch <= hi:
                                self._batch_render_states.pop(old_batch, None)
                        self._produced_pages += 1
                        self.perf_monitor.record_stitch(time.perf_counter() - started + _processing_seconds, plan=plan)
                        self._playback_pacer.publish(self._pacing_context(token, config), batch,
                                                     time.perf_counter(), max(2,min(4,(int(config.cache_num)+1)//2)))
                if not valid:
                    destination.unlink()
                    return
            ui = self._ui()
            if (ui is not None and hasattr(ui, '_video_buffer_changed')
                    and self.shared_config.is_playing):
                with self._cache_guard:
                    notify_pacing = not self._pacing_notification_pending
                    self._pacing_notification_pending = True
                if notify_pacing:
                    wx.CallAfter(ui._video_buffer_changed, token)
            if (ui is not None and hasattr(ui, "_video_frame_ready")
                    and int(self.shared_config.batch_idx) == batch):
                wx.CallAfter(ui._video_frame_ready, batch, token)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    def _defer_custom_past(self,batch):
        snapshot=getattr(self,'_render_snapshot',None)
        if snapshot is None or not self.shared_config.is_playing:return False
        params=snapshot[0].layout_params
        direction=1 if int(self.shared_config.play_direction)>=0 else -1
        # Already displayed past pages stay cached. Unvisited past pages are
        # filled when paused, or become priority work on a direction change.
        return len(params)>38 and (params[32] or params[38]) and direction*(batch-int(self.shared_config.batch_idx))<0

    def _queue_window_stitch(self, batch, sources, token):
        snapshot=getattr(self,'_render_snapshot',None)
        if snapshot is not None and current_only(snapshot[0]) and batch!=int(self.shared_config.batch_idx):return
        if self._defer_custom_past(batch):return
        # A completion handle tracks both dependency waiting and actual execution.
        # Waiting batches never occupy a stitch executor worker.
        with self._cache_guard:
            lo, hi = self._stitch_window
            if getattr(self, '_closed', False) or token != self._window_token or not lo <= batch <= hi:
                return
            key = (token, batch)
            if key in self._window_stitches:
                return
            dependencies = {self._raw_batch_futures.get((vid, local), self._pending_extract.get((vid, local)))
                            for vid, local in sources if (vid, local) not in self._raw_ready_batches}
            dependencies.discard(None)
            completion = Future()
            completion.video_batch = batch
            completion.video_dependencies = tuple(dependencies)
            timing = dict(queued_at=time.perf_counter(), started_at=None,
                          expected_seconds=self.perf_monitor.service_estimates())
            completion.video_timing = timing
            completion.video_waiting_for_extract = bool(dependencies)
            self._window_stitches[key] = completion
            with self._pending_lock:
                self._pending_stitch_async += 1
            remaining = set(dependencies)
            dispatched = [False]

        def done(completed):
            with self._cache_guard:
                if self._window_stitches.get(key) is completed:
                    self._window_stitches.pop(key, None)
            with self._pending_lock:
                self._pending_stitch_async = max(0, self._pending_stitch_async - 1)
        completion.add_done_callback(done)

        def ready(dependency=None):
            with self._cache_guard:
                if dependency is not None:
                    remaining.discard(dependency)
                if completion.done() or remaining or dispatched[0]:
                    return
                dispatched[0] = True
                completion.video_waiting_for_extract = False
                lo, hi = self._stitch_window
                if getattr(self, '_closed', False) or token != self._window_token or not lo <= batch <= hi:
                    completion.cancel()
                    return
                if any(f.cancelled() or f.exception() is not None for f in dependencies):
                    completion.cancel()
                    return
                worker_plan = (self._extract_threads, self._stitch_threads)
                timing['queued_at'] = time.perf_counter()
                timing['expected_seconds'] = self.perf_monitor.service_estimates()
                def stitch():
                    if not completion.set_running_or_notify_cancel():
                        return
                    if self._defer_custom_past(batch):
                        completion.set_result(None)
                        return
                    timing['started_at'] = time.perf_counter()
                    worker_plan = (self._extract_threads, self._stitch_threads)
                    try:
                        self._run_window_stitch(batch, sources, token, worker_plan)
                    except Exception as ex:
                        # A user/cleanup tool may remove source JPEGs after
                        # readiness was published. Retry must revalidate them,
                        # not trust a stale ready bit forever.
                        snapshot=getattr(self,'_render_snapshot',None)
                        params=snapshot[0].layout_params if snapshot is not None else ()
                        custom_active=len(params)>38 and (snapshot[2] or params[38])
                        if not isinstance(ex, MemoryError) and (not custom_active or isinstance(ex,FileNotFoundError)):
                            with self._cache_guard:
                                if token == self._window_token:
                                    self._raw_ready_batches.difference_update(sources)
                        completion.set_exception(ex)
                        self._debug_video(f"[WindowStitch] batch={batch}: {ex}")
                        if not isinstance(ex, CancelledError):
                            self._set_video_status(f'Video pipeline failed: {ex}')
                    else:
                        completion.set_result(None)
                try:
                    self.stitch_executor.submit(stitch)
                except RuntimeError as ex:
                    completion.set_exception(ex)
        for dependency in dependencies:
            dependency.add_done_callback(ready)
        ready()

    def _prepare_video_image(self, path, gap_color):
        """Decode the complete layout and create RGBA bytes off the GUI thread."""
        cached = self._pixel_cache.get(str(path))
        if cached is None:
            with Image.open(path) as opened:
                original = opened.convert('RGBA')
        else:
            original = cached.convert('RGBA')
        # Background-colored slots belong to the configured layout. Cropping
        # them loses blank algorithm panes and invalidates hit-test coordinates.
        return original, original, original.tobytes()

    def shutdown(self):
        """Invalidate callbacks and stop accepting work without waiting on the GUI."""
        with self._cache_guard:
            self._window_token = None
            self._display_serial += 1
            self._closed = True
        self._decoder_bank.configure(0)
        self._maintenance_executor.submit(self._decoder_bank.close)
        kwargs = {'wait': False}
        if sys.version_info >= (3, 9):
            kwargs['cancel_futures'] = True
        for pool in (self._cache_executor, self.executor, self.stitch_executor, self._maintenance_executor, self._display_executor):
            if pool is not None:
                pool.shutdown(wait=False) if pool is self._maintenance_executor else pool.shutdown(**kwargs)

    def _ensure_batch_extracted(self, video_idx: int, local_b: int, wait: bool = True):
        n = self.shared_config.video_num_list[video_idx]
        k = max(1, int(self.shared_config.count_per_action))
        cs, ce = self._batch_range(n, k, local_b)
        if cs is None or ce is None:
            self._set_video_status(
                f"Video extract range invalid: video={video_idx}, local_batch={local_b}, n={n}, k={k}"
            )
            return (None, None)

        key = (video_idx, local_b)

        with self._pending_lock:
            pending = self._pending_extract.get(key)

        if pending:
            if wait:
                pending.result()
                with self._pending_lock:
                    if self._pending_extract.get(key) is pending:
                        self._pending_extract.pop(key, None)
            else:
                return pending

        miss = self._list_missing_range(video_idx, cs, ce)
        if len(miss) > 0:
            frame_names = [self._filename_converter(idx, video_idx) for idx in miss]
            thread_count = getattr(self.executor, "_max_workers", 0)
            if thread_count and not self._reported_extract_threads:
                if getattr(self.shared_config, "debug_thread", False):
                    print(f"Extract thread count: {thread_count}")
                self._reported_extract_threads = True
            if wait:
                fut = self.executor.submit(
                    self._save_frame,
                    self.shared_config.real_video_path[video_idx],
                    cs, ce, video_idx
                )
                fut.result()
                self._debug_video(
                    f"[Extract] done video={video_idx} batch={local_b} frames={frame_names} threads={thread_count}"
                )
            else:
                fut = self.executor.submit(
                    self._save_frame,
                    self.shared_config.real_video_path[video_idx],
                    cs, ce, video_idx
                )
                with self._pending_lock:
                    self._pending_extract[key] = fut

                def _cleanup(fut_done, key=key, names=frame_names, self_ref=weakref.ref(self)):
                    self_obj = self_ref()
                    if not self_obj:
                        return
                    with self_obj._pending_lock:
                        if self_obj._pending_extract.get(key) is fut_done:
                            self_obj._pending_extract.pop(key, None)
                    self_obj._debug_video(
                        f"[Extract] done video={video_idx} batch={local_b} frames={names}"
                    )

                fut.add_done_callback(_cleanup)
                return fut
        else:
            frame_names = [self._filename_converter(idx, video_idx) for idx in range(cs, ce + 1)]
            if wait:
                self._debug_video(
                    f"[Extract] already cached video={video_idx} batch={local_b} frames={frame_names}"
                )

        return (cs, ce)

    def _cleanup_out_of_range_cache(self, video_idx, keep_start_idx, keep_end_idx):
        '''Delete cached files outside the keep range.'''
        cache_dir = self.shared_config.video_path[video_idx]
        if not os.path.isdir(cache_dir):
            return

        if keep_start_idx is None or keep_end_idx is None:
            return
        keep_start_idx = max(0, keep_start_idx)
        keep_end_idx = max(keep_start_idx, keep_end_idx)

        keep_names = set()
        for logical_idx in range(keep_start_idx, keep_end_idx):
            filename = self._filename_converter(logical_idx, video_idx)
            keep_names.add(filename)

        deleted = kept = 0
        for filename in os.listdir(cache_dir):
            if filename.startswith("__tmp_"):
                continue
            if filename not in keep_names:
                try:
                    os.remove(os.path.join(cache_dir, filename))
                    deleted += 1
                except Exception as ex:
                    self._debug_video(f"[_cleanup_out_of_range_cache] delete failed {filename}: {ex}")
            else:
                kept += 1
        self._cleanup_dead_directories()

    def _shared_cache_directories(self):
        """Stage-owned roots; raw-frame cleanup must never retire these."""
        return (self.disk_cache_dir,self.image_disk_cache_dir,self.custom_disk_cache_dir,
                self.cache_dir/"sources",self.cache_dir/".work")

    def _cleanup_dead_directories(self):
        """Delete directories that are no longer in the current video_path list."""
        root=self.cache_dir.resolve()
        reserved={Path(p).resolve() for p in list(self.shared_config.video_path)+list(self._shared_cache_directories())}
        try:
            directories=list(self.cache_dir.iterdir())
        except FileNotFoundError:
            return
        for item in directories:
            target=item.resolve()
            if item.is_dir() and target.parent==root and target not in reserved:
                shutil.rmtree(str(target),ignore_errors=True)
        self._cleanup_source_folders(self.shared_config.video_path)

    def _filename_converter(self, input_value, video_idx, config=None):
        '''Bidirectional conversion: logical index <-> timestamp/frame filename.'''
        config = config if config is not None else self.shared_config
        if isinstance(input_value, int):
            return frame_filename(input_value, config.video_fps_list[video_idx], config.skip_frames+1)

        else:
            if 's_frame_' in input_value:
                parts = input_value.split('s_frame_')
                sec_str = parts[0]

                fps = float(self.shared_config.video_fps_list[video_idx] or 0)
                fps_safe = fps if fps > 0 else 1.0
                step = self.shared_config.skip_frames + 1

                time_seconds = float(sec_str)
                logical_idx = round(time_seconds * fps_safe / step)

                return logical_idx
            else:
                return int(input_value.split('.')[0])

    def _publish_raw_ready(self, vid, local, token, config):
        k = max(1, int(config.count_per_action))
        start, end = self._batch_range(int(config.video_num_list[vid]), k, local)
        if self._list_missing_range(vid, start, end, config):
            return
        self._mark_raw_batch_ready(vid, local, token, True)
        with self._cache_guard:
            future = self._raw_batch_futures.get((vid, local)) if token == self._window_token else None
            if future is not None and not future.done():
                future.set_result(True)

    def _preview_resize_target(self,vid,index,config,image):
        """Precompute the exact display resize while full pixels are available.

        Disk originals remain full resolution. Only a byte-bounded optional
        preview is retained, shared by all later layout reads of this frame.
        """
        snapshot=self._render_snapshot
        if snapshot is None:return None
        manager=snapshot[0];params=manager.layout_params
        mode=getattr(manager,'img_stitch_mode',0)
        if mode==1:return None  # crop is not a resize operation
        if min(params[6])>0:resolution=params[6]
        elif mode==2:resolution=image.size
        else:
            k=max(1,int(config.count_per_action))
            page=((sum(config.video_num_list[:vid])+index)//k if config.parallel_to_sequential else index//k)
            segments=page_segments(config.video_num_list,k,page,config.parallel_to_sequential)
            sizes=[]
            for source,begin,end in segments:
                dimensions=(image.size if source==vid else self._video_dimensions.get(str(config.real_video_path[source])))
                if dimensions is None:return None
                sizes.extend([dimensions]*(end-begin))
            if not sizes:return None
            resolution=source_resolution(sizes,params[6],mode)
        return tuple(max(1,int(v*scale)) for v,scale in zip(resolution,params[4]))

    def _decode_incremental(self, path, first, last, vid, config):
        bank = self._decoder_bank
        if getattr(self,'_closed',False):
            return True
        if not bank.available or str(path) in bank.disabled:
            return False
        token = getattr(self._worker_context, 'token', None)
        if token is not None and token != self._window_token:
            return True
        missing = set(self._list_missing_range(vid, first, last, config))
        if not missing:
            return True
        started = time.perf_counter()
        k, step = max(1, int(config.count_per_action)), max(1, int(config.skip_frames)+1)
        dimensions = self._video_dimensions.get(str(path), (1920, 1080))
        def cancelled():
            if getattr(self, '_closed', False) or (token is not None and token != self._window_token):
                return True
            lo, hi = self._raw_windows.get(vid, (first, last+1))
            return token is not None and (hi <= first or lo > last)
        try:
            with bank.lease(path, float(config.video_fps_list[vid]),
                            self._fast_seek_paths.get(str(path), False), dimensions[0]*dimensions[1],
                            getattr(self._worker_context,'native_threads',1)) as decoder:
                for physical, image in decoder.frames(min(missing)*step, max(missing)*step, step, cancelled, buffer_images=True):
                    index = physical // step
                    if index not in missing:
                        continue
                    with self._cache_guard:
                        lo, hi = self._raw_windows.get(vid, (first, last+1))
                        if token is not None and (token != self._window_token or not lo <= index < hi):
                            continue
                    destination = os.path.join(config.video_path[vid], self._filename_converter(index, vid, config))
                    temporary = os.path.join(config.video_path[vid], '__tmp_native_%s_%s.jpeg' %
                                             (threading.get_ident(), time.time_ns()))
                    try:
                        image.save(temporary, format='JPEG', quality=90)
                        preview, preview_key = None, None
                        target=self._preview_resize_target(vid,index,config,image)
                        if target is not None:
                            if target[0]*target[1]*4 <= self._pixel_cache.limit:
                                preview = image.resize(target, Image.BICUBIC) if target != image.size else image
                                preview_key = ('preview', destination, target, int(Image.BICUBIC))
                        with self._raw_io_lock(vid, config):
                            with self._cache_guard:
                                lo, hi = self._raw_windows.get(vid, (first, last+1))
                                valid = token is None or (token == self._window_token and lo <= index < hi)
                            if valid:
                                # Filesystem/antivirus latency must never hold
                                # the state lock used by the GUI or other videos.
                                os.replace(temporary, destination)
                                with self._cache_guard:
                                    lo, hi = self._raw_windows.get(vid, (first,last+1))
                                    valid = token is None or (token == self._window_token and lo <= index < hi)
                                    if valid:
                                        self._pixel_cache.put(destination, image)
                                        if preview is not None:
                                            self._pixel_cache.put(preview_key, preview, owner=destination, priority=True)
                                if not valid:
                                    os.remove(destination)
                        if valid and (index == int(config.video_num_list[vid])-1 or (index+1) % k == 0):
                            self._publish_raw_ready(vid, index//k, token, config)
                    finally:
                        try:
                            os.remove(temporary)
                        except OSError:
                            pass
            lo, hi = self._raw_windows.get(vid, (first, last+1)) if token is not None else (first, last+1)
            if not cancelled() and self._list_missing_range(vid, max(first,lo), min(last,hi-1), config):
                raise RuntimeError('Native decoder did not produce all requested ordinal frames')
            self.perf_monitor.record_extract(time.perf_counter()-started, len({i//k for i in missing}), vid,
                                            plan=getattr(self._worker_context, 'plan', None))
            return True
        except Exception as ex:
            if cancelled():
                return True
            bank.disabled.add(str(path))
            self._debug_video('Native decode fallback: %s: %s' % (path, ex))
            return False

    def _save_frame(self, video_path, frame_start, frame_end, video_idx, max_retries=1, config=None):
        '''Decode incrementally when available, otherwise use the exact FFmpeg fallback.'''
        config = config if config is not None else copy.copy(self.shared_config)
        if self._decode_incremental(video_path, frame_start, frame_end, video_idx, config):
            return
        config = config if config is not None else copy.copy(self.shared_config)
        token = getattr(self._worker_context, "token", None)
        if token is not None and token != self._window_token:
            return
        step = config.skip_frames + 1
        start_time = time.perf_counter()
        cache_dir = config.video_path[video_idx]
        filename_for = lambda idx: self._filename_converter(idx, video_idx, config)
        #b4 修改  去掉这个缩放耦合，让抽帧永远保持原始分辨率
        #target_size = 256
        #enable_debug_scale = bool(getattr(self.shared_config, "debug_video", False))
        last_error = None
        owned_tmp_prefixes = []
        fast_seek = self._fast_seek_paths.get(str(video_path), False)
        has_ffmpeg_input = callable(getattr(ffmpeg, "input", None))

        def list_missing(a, b):
            if token is not None:
                with self._cache_guard:
                    if token != self._window_token:
                        return []
                    lo, hi = self._raw_windows.get(video_idx, (a, b+1))
                a, b = max(a,lo), min(b,hi-1)
            miss = []
            for idx in range(a, b + 1):
                dst = os.path.join(cache_dir, filename_for(idx))
                try:
                    if (not os.path.exists(dst)) or os.path.getsize(dst) == 0:
                        miss.append(idx)
                except Exception:
                    miss.append(idx)
            return miss

        def chunks(seq):
            if not seq: return []
            run = [seq[0]]; out = []
            for x in seq[1:]:
                if x == run[-1] + 1: run.append(x)
                else: out.append((run[0], run[-1])); run = [x]
            out.append((run[0], run[-1]))
            return out

        def extract_ranges(ranges, allow_fast_seek=True):
            nonlocal last_error
            for s, e in ranges:
                if token is not None and token != self._window_token:
                    return
                if fast_seek and allow_fast_seek:
                    fps = float(config.video_fps_list[video_idx])
                    suffix = f"{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"
                    tmp_prefix = f"__tmp_{video_idx}_{suffix}_"
                    owned_tmp_prefixes.append(tmp_prefix)
                    tmp_tpl = os.path.join(cache_dir, f"{tmp_prefix}%d.jpeg")
                    cmd = [
                        self._video_command('ffmpeg'), "-hide_banner", "-loglevel", "error",
                        "-threads", "1", "-ss", f"{s * step / fps:.9f}",
                        "-i", str(video_path), "-map", "0:v:0",
                    ]
                    if step > 1:
                        cmd.extend(["-vf", f"select=not(mod(n\\,{step}))"])
                    cmd.extend([
                        "-vsync", "0", "-frames:v", str(e - s + 1),
                        "-threads:v", "1",
                        "-q:v", "6", "-start_number", str(s), "-y", tmp_tpl,
                    ])
                    try:
                        cp = run_video_process(
                            cmd, capture_output=True, encoding="utf-8",
                            errors="replace", check=False,
                            **self._video_process_options(),
                        )
                        if cp.returncode != 0:
                            last_error = (cp.stderr or cp.stdout or "").strip() or f"ffmpeg exit code {cp.returncode}"
                    except Exception as ex:
                        last_error = str(ex)
                if not (fast_seek and allow_fast_seek):
                    physical_frames = []
                    for logical_idx in range(s, e + 1):
                        physical_frame = logical_idx * step
                        physical_frames.append(physical_frame)
                    if not physical_frames:
                        continue

                    if len(physical_frames) == 1:
                        sel = f'eq(n,{physical_frames[0]})'
                    else:
                        frame_conditions = [f'eq(n,{pf})' for pf in physical_frames]
                        sel = '+'.join(frame_conditions)

                    suffix = f"{os.getpid()}_{threading.get_ident()}_{time.time_ns()}"
                    tmp_prefix = f'__tmp_{video_idx}_{suffix}_'
                    owned_tmp_prefixes.append(tmp_prefix)
                    tmp_tpl = os.path.join(cache_dir, f'__tmp_{video_idx}_{suffix}_%d.jpeg')

                    try:
                        # stream = (
                        #     ffmpeg
                        #     .input(str(video_path))
                        #     .filter('select', sel)
                        # )
                        # if enable_debug_scale:
                        #     stream = stream.filter('scale', target_size, -1, force_original_aspect_ratio='decrease')

                        #b4 修改

                        stream = None
                        if has_ffmpeg_input:
                            stream = ffmpeg.input(str(video_path), threads=1).filter('select', sel)

                        if has_ffmpeg_input:
                            cmd = (
                                stream
                                .output(tmp_tpl, vsync='vfr', vframes=e - s + 1, threads=1, **{'q:v': 6}, start_number=s)
                                .global_args('-threads', '1', '-hide_banner', '-loglevel', 'error')
                                .overwrite_output()
                                .compile(cmd=self._video_command('ffmpeg'))
                            )
                            cp = run_video_process(cmd, capture_output=True, encoding='utf-8',
                                                errors='replace', check=False,
                                                **self._video_process_options())
                            if cp.returncode:
                                last_error = cp.stderr or cp.stdout
                        else:
                            # Keep absolute frame indexing even without ffmpeg-python.
                            cmd = [
                                self._video_command('ffmpeg'), '-hide_banner', '-loglevel', 'error',
                                '-threads', '1', '-i', str(video_path), '-map', '0:v:0',
                                '-vf', 'select=' + sel.replace(',', r'\,'),
                                '-vsync', '0', '-frames:v', str(e - s + 1),
                                '-threads:v', '1',
                                '-q:v', '6', '-start_number', str(s), '-y', tmp_tpl,
                            ]
                            cp = run_video_process(cmd, capture_output=True, encoding='utf-8', errors='replace', check=False,
                                                **self._video_process_options())
                            if cp.returncode:
                                last_error = cp.stderr or cp.stdout
                    except Exception as ex:
                        stderr = getattr(ex, 'stderr', None)
                        last_error = stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes) else str(ex)
                        self._debug_video(f"[Extract] error: ffmpeg processing failed, reason={ex}")
                tmp_map = {}
                try:
                    for name in os.listdir(cache_dir):
                        if not (name.startswith(tmp_prefix) and name.endswith('.jpeg')):
                            continue
                        num_txt = name[len(tmp_prefix):-5]
                        try:
                            num = int(num_txt)
                        except Exception:
                            continue
                        tmp_map[num] = os.path.join(cache_dir, name)
                except Exception:
                    tmp_map = {}
                sorted_candidates = [tmp_map[key] for key in sorted(tmp_map.keys())]
                used = set()
                for idx in range(s, e + 1):
                    src = tmp_map.get(idx)
                    if src in used:
                        src = None
                    if src is None:
                        for candidate in sorted_candidates:
                            if candidate not in used:
                                src = candidate
                                break
                    if not src or (not os.path.exists(src)):
                        continue
                    used.add(src)
                    if os.path.getsize(src) == 0:
                        try:
                            os.remove(src)
                        except Exception:
                            pass
                        continue
                    dst = os.path.join(cache_dir, filename_for(idx))
                    try:
                        with self._raw_io_lock(video_idx, config):
                            with self._cache_guard:
                                keep_start, keep_end = self._raw_windows.get(video_idx, (0, 0))
                                valid = token is None or (token == self._window_token and keep_start <= idx < keep_end)
                            if valid:
                                os.replace(src, dst)
                                with self._cache_guard:
                                    keep_start, keep_end = self._raw_windows.get(video_idx, (0, 0))
                                    valid = token is None or (token == self._window_token and keep_start <= idx < keep_end)
                                if not valid:
                                    os.remove(dst)
                            else:
                                os.remove(src)
                    except Exception:
                        try:
                            os.remove(src)
                        except Exception:
                            pass

        missing = list_missing(frame_start, frame_end)
        k = max(1, int(config.count_per_action))
        requested_batches = len({idx // k for idx in missing})
        if missing:
            extract_ranges(chunks(missing))

        attempt = 0
        while attempt < max_retries:
            if token is not None and token != self._window_token:
                break
            missing = list_missing(frame_start, frame_end)
            if not missing:
                break
            # If timestamp seeking did not produce every requested frame,
            # retry with the original absolute-frame selection.
            extract_ranges(chunks(missing), allow_fast_seek=False)
            attempt += 1

        missing = list_missing(frame_start, frame_end)
        if missing and (token is None or token == self._window_token):
            detail = f"video={video_idx}, miss={missing[:5]}"
            if last_error:
                detail = f"{detail}, err={last_error}"
            self._debug_video(f"[Extract] final failure {detail}")
            self._set_video_status(f"Video extract failed: {detail}")

        try:
            for name in os.listdir(cache_dir):
                if name.endswith('.jpeg') and any(name.startswith(prefix) for prefix in owned_tmp_prefixes):
                    try: os.remove(os.path.join(cache_dir, name))
                    except: pass
        except Exception:
            pass

        if token is not None:
            # Reuse the final missing-frame scan already performed above;
            # publishing readiness must not add per-frame filesystem scans.
            missing_batches = {idx // k for idx in missing}
            for local in range(frame_start // k, frame_end // k + 1):
                start, end = self._batch_range(int(config.video_num_list[video_idx]), k, local)
                if frame_start <= start and end <= frame_end:
                    self._mark_raw_batch_ready(video_idx, local, token, local not in missing_batches)

        if requested_batches and (token is None or token == self._window_token):
            self.perf_monitor.record_extract(time.perf_counter() - start_time,
                                             requested_batches, video_idx,
                                             plan=getattr(self._worker_context, 'plan', None))

    def collect_video_paths(self, dlg, selection_type):
        '''Collect video file paths for different selection modes.'''
        video_paths = []
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return video_paths

            if selection_type == 1:
                selected_path = dlg.GetPath()
                for root, dirs, files in os.walk(selected_path):
                    for file in files:
                        if file.lower().endswith(('.mp4', '.avi', '.mov')):
                            video_paths.append(os.path.join(root, file))

            elif selection_type == 0:
                selected_path = dlg.GetPath()
                if selected_path.lower().endswith(('.mp4', '.avi', '.mov')):
                    video_paths.append(selected_path)
            elif selection_type == 2:
                video_paths = dlg.GetPaths()
        finally:
            dlg.Destroy()
        return video_paths

    def select_video(self, type=0):
        '''Shared initialization flow across selection modes.'''
        self.flag = 0
        self.shared_config.video_fps_list = []
        self.shared_config.video_num_list = []
        wildcard = "Video files (*.mp4;*.avi;*.mov)|*.mp4;*.avi;*.mov"
        if type == 1:
            dlg = wx.DirDialog(None, "Select folder containing videos", style=wx.DD_DEFAULT_STYLE)
        elif type == 0:
            dlg = wx.FileDialog(None, "Choose video file", "", "",
                                wildcard, wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if type == -1:
            pass
        else:
            self.shared_config.real_video_path = self.collect_video_paths(dlg, type)
        try:
            self._video_tools, self._video_tools_env = resolve_video_tools()
        except (OSError, ValueError) as ex:
            self._set_video_status(f"Error: {ex}")
            self.shared_config.video_path = []
            return []
        self.shared_config.status_input_mode = (3 if self.shared_config.input_mode == 3
                                                else {0: 0, 1: 1, -1: 2}.get(type, 2))
        self._reset_for_new_selection()
        self.init_video_frame_cache()
        if self.shared_config.video_path == []:
            return []

        if (not self.shared_config.video_fps_list) or (not self.shared_config.video_num_list):
            for vp in self.shared_config.real_video_path:
                try:
                    self.calc_max_extractable_frames_single(vp)
                except Exception as ex:
                    self.shared_config.video_fps_list.append(0.0)
                    self.shared_config.video_num_list.append(0)
                    self._set_video_status(f"Video meta failed: {Path(vp).name}: {ex}")

        if not any(int(x or 0) > 0 for x in self.shared_config.video_num_list):
            self._set_video_status("Video meta invalid: no decodable frames")
            self.shared_config.video_path = []
            return []

        if len(self.shared_config.video_path) == 1:
            self.ImgManager.init(
                self.shared_config.video_path[0],
                type=2,
                parallel_to_sequential=self.shared_config.parallel_to_sequential,
                video_mode=self.shared_config.video_mode,
                video_fps_list=self.shared_config.video_fps_list,
                video_num_list=self.shared_config.video_num_list,
                skip=self.shared_config.skip_frames,
            )
        else:
            self.ImgManager.init(
                self.shared_config.video_path,
                type=1,
                parallel_to_sequential=self.shared_config.parallel_to_sequential,
                video_mode=self.shared_config.video_mode,
                video_fps_list=self.shared_config.video_fps_list,
                video_num_list=self.shared_config.video_num_list,
                skip=self.shared_config.skip_frames,
            )

        ui = self._ui()
        if ui:
            try:
                ui._sync_video_count_per_action()
            except Exception:
                pass

        self.current_batch_idx = 0
        self.update_cache()
        self.flag = 1
        if type == -1:
            ui = self._ui()
            if ui:
                # ★ 顺序很重要：show_img_init() 会因布局变化清空视频缓存，
                #   所以必须先重建布局，再重新抽帧+拼接，最后显示。
                #   否则 show_img() 拿到的 cache_img 是空的，只会停在 "Waiting for batch 0"。
                wx.CallAfter(ui.show_img_init)
                self.ImgManager.set_action_count(0)
                wx.CallAfter(ui._rebuild_video_cache_and_show)
                if hasattr(ui, "_reset_image_view_origin"):
                    wx.CallAfter(ui._reset_image_view_origin)
        return self.shared_config.real_video_path

    def _collect_batch_frame_paths(self, video_idx: int, batch_idx: int, config=None):
        config = self.shared_config if config is None else config
        if video_idx >= len(getattr(config, "video_path", [])):
            return []
        n = int(config.video_num_list[video_idx]) if video_idx < len(config.video_num_list) else 0
        k = max(1, int(getattr(config, "count_per_action", 1)))
        if n <= 0:
            return []
        max_batch = (n + k - 1) // k if n > 0 else 0
        if max_batch <= 0:
            return []
        clamped_idx = batch_idx if batch_idx < max_batch else (max_batch - 1)
        cs, ce = self._batch_range(n, k, clamped_idx)
        if cs is None or ce is None or cs > ce:
            return []

        v_dir = config.video_path[video_idx]
        with self._cache_guard:
            known_ready = (video_idx, clamped_idx) in self._raw_ready_batches
        if known_ready:
            return [os.path.join(v_dir, self._filename_converter(idx, video_idx, config)) for idx in range(cs,ce+1)]
        frames = []
        with self._raw_io_lock(video_idx, config):
            for idx in range(cs, ce + 1):
                fn = self._filename_converter(idx, video_idx, config)
                p = os.path.join(v_dir, fn)
                if os.path.exists(p):
                    frames.append(p)
        return frames

    def _should_schedule_stitch(self, global_idx: int):
        # ★ 用 _cached_batch_path 判断: 缓存为空、或磁盘文件已被窗口清理掉, 才需要拼接。
        #   直接看 cache_img[idx] is None 会把"路径已失效"的条目当成已缓存, 导致再也不拼接。
        return self._cached_batch_path(global_idx) is None

    def _post_extract_stitch(self, video_idx: int, local_b: int, global_b: int, fut: Future):
        if fut.cancelled():
            return
        try:
            fut.result()
        except Exception:
            return
        if self._should_schedule_stitch(global_b):
            self._schedule_stitch(video_idx, local_b, global_b)

    def _schedule_stitch(self, video_idx: int, local_b: int, global_b: int):
        if not self._should_schedule_stitch(global_b):
            return

        def _task():
            try:
                if self._should_schedule_stitch(global_b):
                    self._stitch_batch(video_idx, local_b, global_b)
            finally:
                with self._pending_lock:
                    self._pending_stitch_async = max(0, self._pending_stitch_async - 1)

        with self._pending_lock:
            self._pending_stitch_async += 1
        stitch_threads = getattr(self.stitch_executor, "_max_workers", 0)
        if stitch_threads and not self._reported_stitch_threads:
            if getattr(self.shared_config, "debug_thread", False):
                print(f"Stitch thread count: {stitch_threads}")
            self._reported_stitch_threads = True
        self.stitch_executor.submit(_task)

    #b2 在 VideoManager 类中添加新方法
    def _schedule_extract_stitch_multi(self, global_b: int, vid_max_batches: list):
        """异步提取 global_b 批次的所有视频帧，然后拼接。"""
        if not self._should_schedule_stitch(global_b):
            return

        def _task():
            try:
                # 在 stitch worker 线程内依次等待各视频帧提取完成
                for vid, _max_b in vid_max_batches:
                    self._ensure_batch_extracted(vid, global_b, wait=True)
                # 仍需拼接则执行
                if self._should_schedule_stitch(global_b):
                    self._stitch_batch_multi(global_b)
            except Exception as ex:
                self._debug_video(f"[StitchMulti] async error batch={global_b} error={ex}")
            finally:
                with self._pending_lock:
                    self._pending_stitch_async = max(0, self._pending_stitch_async - 1)

        with self._pending_lock:
            self._pending_stitch_async += 1
        self.stitch_executor.submit(_task)

    def _schedule_stitch_multi(self, global_b: int, extract_futs: list):
        """
        Schedule async multi-video stitching for batch global_b.
        extract_futs: list of Future objects for in-progress extractions.Waits for all futures to finish, then calls _stitch_batch_multi.
        """
        if not self._should_schedule_stitch(global_b):
            return

        def _task():
            try:
                # Wait for all pending extraction futures before stitching
                for fut in extract_futs:
                    try:
                        fut.result()
                    except Exception:
                        pass
                # Only stitch if cache slot is still empty
                if self._should_schedule_stitch(global_b):
                    self._stitch_batch_multi(global_b)
            except Exception as ex:
                self._debug_video(f"[StitchMulti] async error batch={global_b} error={ex}")
            finally:
                with self._pending_lock:
                    self._pending_stitch_async = max(0, self._pending_stitch_async - 1)

        with self._pending_lock:
            self._pending_stitch_async += 1
        self.stitch_executor.submit(_task)

    def _stitch_batch_multi(self, global_b: int):
        ui = self._ui()
        if not ui:
            self._debug_video("[Stitch] skipped: UI not found")
            return
        if len(getattr(ui.ImgManager, "layout_params", [])) <= 32:
            ui.show_img_init()

        video_paths = getattr(self.shared_config, "video_path", [])
        if not video_paths:
            return

        flist_groups = []
        has_available = False
        for video_idx in range(len(video_paths)):
            frames = self._collect_batch_frame_paths(video_idx, global_b)
            if frames:
                has_available = True
            flist_groups.append(frames)

        if not has_available:
            self._debug_video(f"[Stitch] skipped: batch={global_b} no available frames across all videos")
            self._set_video_status(f"Video frames not ready: batch={global_b}")
            return

        need = global_b + 1 - len(self.shared_config.cache_img)
        if need > 0:
            self.shared_config.cache_img.extend([None] * need)

        with self._stitch_lock:
            old_cnt = ui.ImgManager.action_count
            ui.ImgManager.set_action_count(global_b)
            pil_img, flag = ui.compose_current_frame(global_b, flist=flist_groups)
            ui.ImgManager.set_action_count(old_cnt)

        if (pil_img is None or flag != 0):
            fallback = self._open_first_frame_from_nested(flist_groups)
            if fallback is not None:
                pil_img = fallback
                flag = 0
                self._debug_video(f"[Stitch] fallback: show first frame directly batch={global_b}")

        # **关键修改：保存到磁盘而不是内存**
        if pil_img is not None and flag == 0:
            # **关键修改：保存到磁盘**
            disk_path = self._save_image_to_disk(pil_img, global_b)
            if disk_path:
                self.shared_config.cache_img[global_b] = disk_path
            else:
                self.shared_config.cache_img[global_b] = None
        else:
            self.shared_config.cache_img[global_b] = None

        ok = self.shared_config.cache_img[global_b] is not None
        if not ok:
            self._set_video_status(f"Video stitch empty: video={video_idx}, batch={global_b}, flag={flag}")
        self._debug_video(
            f"[Stitch] done thread={threading.current_thread().name} video={video_idx} batch={global_b} success={ok}"
        )

    def _stitch_batch(self, video_idx: int, local_b: int, global_b: int):
        ui = self._ui()
        if not ui:
            self._debug_video("[Stitch] skipped: UI not found")
            return
        video_paths = getattr(self.shared_config, "video_path", [])
        if len(video_paths) > 1 and not getattr(self.shared_config, "parallel_to_sequential", False):
            return
        if len(getattr(ui.ImgManager, "layout_params", [])) <= 32:
            ui.show_img_init()
        n = int(self.shared_config.video_num_list[video_idx])
        k = max(1, int(self.shared_config.count_per_action))
        cs, ce = self._batch_range(n, k, local_b)
        if cs is None or ce is None or cs > ce:
            self._debug_video(f"[Stitch] skipped: video={video_idx} batch={local_b}")
            self._set_video_status(f"Video batch invalid: video={video_idx}, local_batch={local_b}, n={n}, k={k}")
            return

        flist = self._collect_batch_frame_paths(video_idx, local_b)

        if not flist:
            self._debug_video(
                f"[Stitch] skipped: video={video_idx} batch={local_b} no available frames"
            )
            self._set_video_status(f"Video frames not ready: video={video_idx}, batch={global_b}")
            return

        stitch_threads = getattr(self.stitch_executor, "_max_workers", 0)
        need = global_b + 1 - len(self.shared_config.cache_img)
        if need > 0:
            self.shared_config.cache_img.extend([None] * need)

        try:
            with self._stitch_lock:
                old_cnt = ui.ImgManager.action_count
                ui.ImgManager.set_action_count(global_b)
                pil_img, flag = ui.compose_current_frame(global_b, flist=flist if flist else None)
                ui.ImgManager.set_action_count(old_cnt)
        except Exception as ex:
            self._debug_video(f"[Stitch] exception video={video_idx} batch={global_b} error={ex}")
            self._set_video_status(f"Video stitch failed: {ex}")
            return

        if (pil_img is None or flag != 0):
            fallback = self._open_first_frame(flist)
            if fallback is not None:
                pil_img = fallback
                flag = 0
                self._debug_video(f"[Stitch] fallback: show first frame directly video={video_idx} batch={global_b}")

        if pil_img is not None and flag == 0:
            disk_path = self._save_image_to_disk(pil_img, global_b)
            if disk_path:
                self.shared_config.cache_img[global_b] = disk_path  # 存储路径而非对象
            else:
                self.shared_config.cache_img[global_b] = None
        else:
            self.shared_config.cache_img[global_b] = None

        ok = self.shared_config.cache_img[global_b] is not None
        if not ok:
            self._set_video_status(f"Video stitch empty: video={video_idx}, batch={global_b}, flag={flag}")
        self._debug_video(
            f"[Stitch] done thread={threading.current_thread().name} video={video_idx} batch={global_b} success={ok}"
        )


    def _open_first_frame(self, flist):
        if not flist:
            return None
        for p in flist:
            if not p:
                continue
            try:
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    return Image.open(p).convert("RGB")
            except Exception:
                continue
        return None

    def _open_first_frame_from_nested(self, flist_groups):
        if not flist_groups:
            return None
        for group in flist_groups:
            img = self._open_first_frame(group)
            if img is not None:
                return img
        return None

    def _batch_range(self, n, k, b):
        """Return the logical frame range [start, end] for batch b (inclusive). Invalid -> (None, None)."""
        if n <= 0 or k <= 0 or b < 0:
            return (None, None)
        start = b * k
        if start >= n:
            return (None, None)
        end = min(n - 1, start + k - 1)
        return (start, end)

    def _list_missing_range(self, video_idx, a, b, config=None):
        if a is None or b is None or a > b:
            return []
        config = self.shared_config if config is None else config
        cache_dir = os.path.abspath(config.video_path[video_idx])
        miss = []
        with self._raw_io_lock(video_idx, config):
            for idx in range(a, b + 1):
                filename = self._filename_converter(idx, video_idx, config)
                path = os.path.join(cache_dir, filename)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                if size <= 0:
                    miss.append(idx)
        return miss

