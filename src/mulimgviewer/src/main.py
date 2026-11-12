import platform
import threading
from pathlib import Path
import ffmpeg, os, time, math, sys
from concurrent.futures import ThreadPoolExecutor, Future
import atexit
import weakref
import signal
import re
import subprocess
from fractions import Fraction
from collections import deque

import numpy as np
import wx
from PIL import Image
from ..gui.main_gui import MulimgViewerGui
from .path_select import on_video_mode_change
from concurrent.futures import wait, ALL_COMPLETED
from functools import partial

from .. import __version__ as VERSION
from .about import About
from .index_table import IndexTable
from .custom_func.main import get_available_algorithms
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
from .resource_policy import resource_budget, positive_cache_integer
from .image_pipeline import ImagePipeline
from .memory_reclaim import MemoryReclaimer
from .video_tools import resolve_video_tools
from .resource_monitor import ResourceMonitor, run_video_process
from .pipeline_executor import PipelineWorkers
from .admission_optimizer import AdaptiveAdmissionBudget
from .video_decoder import DecoderBank
from .video_memory import PixelCache
from .playback_pacer import PlaybackPacer, ProductionJob, completion_estimates, refill_guard
from .thread_optimizer import (AdaptiveThreadAllocator, optimize_thread_allocation,
                               available_memory_bytes, stitch_memory_limit, buffer_levels, buffer_priority)
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

class SharedConfig:
    def __init__(self):
        '''Variables shared by MulimgViewer and VideoManager.'''
        self.cache_num = 2 #Number of caches
        self.cache_multiplier = 1 # Outer video cache radius / priority radius
        self.skip_frames = 0 #Number of frames to skip
        self.power_mode = 2 # 1 Eco, 2 Balanced, 3 Performance, 4 Maximum
        self.memory_budget = None # Soft budget for concurrent pixel working sets
        self.thread = 4 # Internal processing budget; populated from power_mode
        self.thread_allocation = None # Actual extract/stitch pool sizes
        self.thread_allocation_recommend = None
        self.video_mode = False #Video mode
        self.interval = 1.0 #Playback interval
        self.manual_interval = None # Last user-entered video interval; auto writes never change it
        self.is_playing = False #Whether currently playing
        self.play_direction = 1 #Playback direction
        self.real_video_path = [] #Actual video paths, ending in mp4
        self.video_path = [] #Video Cache Path
        self.parallel_to_sequential = False #Parallel to sequential
        self.parallel_sequential = False #Parallel to sequential
        self.input_mode = 0 # Input mode
        self.video_fps_list = [] #Video fps
        self.batch_idx = 0 #Current batch index
        self.count_per_action = 1 #Frames processed per action
        self.video_num_list = [] #Maximum frames for each video
        self.current_video_index = 0 #Current video index
        self.last_direction = 0 #Last playback direction
        self.cache_img = [] #Position to store stitched images
        self.image_cache_img = [] #Image mode stitch cache False
        self.image_cache_paths = [] #Image mode cache path list
        self.image_disk_cache_dir = "Video_frames/stitch_cache"
        self.debug_video = False #Video mode debug output
        self.debug_image = False #Image mode debug output
        self.debug_thread = False #Thread debug output
        #self.debug_thread = True
        #self.debug_video = True
        self.interval_recommend = None #Playback interval recommendation
        self.video_last_message = "" # Most recent video error/diagnostic information

class VideoManager:
    def __init__(self, owner, shared_config=None, ImgManager=None):
        self._owner = weakref.ref(owner)
        self.shared_config = shared_config
        self.ImgManager = ImgManager
        self.cache_dir = Path("Video_frames")
        # 新增：磁盘缓存目录
        self.disk_cache_dir = Path("Video_frames") / "stitch_cache"
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)
        # 新增：图像模式磁盘缓存目录
        self.image_disk_cache_dir = self.disk_cache_dir
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
        return self.disk_cache_dir / f"batch_{batch_idx}.png"

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
            for cache_file in self.disk_cache_dir.glob("batch_*.png"):
                try:
                    idx = int(cache_file.stem.split('_')[1])
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
        self._pixel_cache.configure(min(256 * 1024**2, int(budget * .08)) if budget else 0)
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
        k = max(1, int(cfg.count_per_action))
        counts = [(int(n) + k - 1) // k for n in cfg.video_num_list]
        if cfg.parallel_to_sequential:
            base = 0
            for vid, count in enumerate(counts):
                if base <= batch < base + count:
                    return [(vid, batch - base)]
                base += count
            return []
        return [(vid, min(batch, count - 1)) for vid, count in enumerate(counts) if count > 0]

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
        interval, details = pacer.recommend(self._pacing_context(), now, depth,
            max(1, int(cfg.cache_num)), remaining, cfg.manual_interval, display_cost, fallback, eta)
        cfg.interval_recommend = max(.001, math.ceil(interval * 1000 - 1e-9) / 1000.)
        cfg.interval_prediction = details
        self._apply_interval_recommendation(cfg.interval_recommend, reschedule=reschedule)

    def _playback_video_indices(self):
        cfg = self.shared_config
        k = max(1, int(cfg.count_per_action))
        counts = [(int(n) + k - 1) // k for n in cfg.video_num_list]
        batch = int(cfg.batch_idx)
        if cfg.parallel_to_sequential:
            base = 0
            for vid, count in enumerate(counts):
                if base <= batch < base + count:
                    return [vid], sum(counts)
                base += count
            return [], sum(counts)
        return [vid for vid, count in enumerate(counts) if batch < count], max(counts, default=0)

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
                if len(resolution)==2 and min(resolution)>0:
                    output = int(resolution[0])*int(resolution[1])*slots*4
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
        '''Initialize video cache directories (folders only).'''
        video_paths = self.shared_config.real_video_path
        output_list = []

        for video_path in video_paths:
            video_path = Path(video_path)
            cache_name = video_path.stem
            out_dir = self.cache_dir / cache_name
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
            if self._extract_threads+self._stitch_threads < int(self.shared_config.thread):
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
        total = sum(counts) if sequential else max(counts, default=0)
        if total <= 0:
            return
        b = max(0, min(int(cfg.batch_idx), total - 1))
        lo, hi = max(0, b - outer), min(total - 1, b + outer)

        def sources(batch):
            if sequential:
                base = 0
                for vid, count in enumerate(counts):
                    if base <= batch < base + count:
                        return [(vid, batch - base)]
                    base += count
                return []
            # Ended streams keep their final frame, matching the existing viewer.
            return [(vid, min(batch, count - 1)) for vid, count in enumerate(counts) if count > 0]

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
                      if self._cached_batch_path(batch, validate=False) is None]
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
        for path in self.disk_cache_dir.glob("batch_*.png"):
            try:
                idx = int(path.stem.split('_')[1])
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
        root = self.cache_dir.resolve()
        reserved = {Path(p).resolve() for p in config.video_path}
        reserved.update((self.disk_cache_dir.resolve(), self.image_disk_cache_dir.resolve()))
        try:
            directories = list(self.cache_dir.iterdir())
        except OSError:
            return
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

    def _run_window_stitch(self, batch, sources, token, plan=None):
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
        groups = [self._collect_batch_frame_paths(vid, local, config) for vid, local in sources]
        # No cache guard spans pixel processing or PNG compression.
        started = time.perf_counter()
        if snapshot is None:
            # Compatibility for headless owners providing a pure compose method.
            ui = self._ui()
            pil_img, flag = ui.compose_current_frame(batch, flist=groups[0] if single else groups)
            state = {}
        else:
            template, points, custom = snapshot
            manager = template.video_stitch_snapshot()
            manager._video_lazy_frames = not custom and not (len(template.layout_params) > 38 and template.layout_params[38])
            manager._video_pixel_provider = self._pixel_cache.get
            working = self._planning_memory_budget()
            if working is not None:
                _, inputs = self._estimated_stitch_pixels()
                per_page = min(working, self._pipeline_workers.costs[1])
                if not manager._video_lazy_frames and inputs*9 >= per_page:
                    self._set_video_status('Video layout/custom processing exceeds the memory budget; reduce layout or preview size')
                    return
                manager._video_memory_budget = max(1, per_page - inputs*9)
            manager.set_action_count(batch)
            flist = groups[0] if single else groups
            if custom:
                manager.layout_params[32] = True
                manager.stitch_images(0, copy.deepcopy(points), flist=flist)
                manager.layout_params[32] = False
            flag = manager.stitch_images(0, copy.deepcopy(points), flist=flist)
            pil_img = manager.show_stitch_img_and_customfunc_img(custom) if flag == 0 else None
            state = {name: getattr(manager, name) for name in (
                'xy_grid', 'xy_grids_id_list', 'crop_points', 'img_resolution_origin',
                'img_resolution_show', 'gap_color', 'title_setting', 'pdf_title_layers',
                '_last_title_layout', 'flist', '_flist_groups',
            ) if hasattr(manager, name)}
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
                        self._pixel_cache.put(str(destination), pil_img, priority=True)
                        self.shared_config.cache_img[batch] = str(destination)
                        self._batch_render_states[batch] = state
                        for old_batch in list(self._batch_render_states):
                            if not lo <= old_batch <= hi:
                                self._batch_render_states.pop(old_batch, None)
                        self._produced_pages += 1
                        self.perf_monitor.record_stitch(time.perf_counter() - started, plan=plan)
                        self._playback_pacer.publish(self._pacing_context(token, config), batch,
                                                     time.perf_counter(), max(1, int(config.cache_num)))
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

    def _queue_window_stitch(self, batch, sources, token):
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
                    timing['started_at'] = time.perf_counter()
                    worker_plan = (self._extract_threads, self._stitch_threads)
                    try:
                        self._run_window_stitch(batch, sources, token, worker_plan)
                    except Exception as ex:
                        # A user/cleanup tool may remove source JPEGs after
                        # readiness was published. Retry must revalidate them,
                        # not trust a stale ready bit forever.
                        if not isinstance(ex, MemoryError):
                            with self._cache_guard:
                                if token == self._window_token:
                                    self._raw_ready_batches.difference_update(sources)
                        completion.set_exception(ex)
                        self._debug_video(f"[WindowStitch] batch={batch}: {ex}")
                        if isinstance(ex, MemoryError):
                            self._set_video_status(str(ex))
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
        """Decode, trim and create RGBA bytes in a worker, with no wx calls."""
        cached = self._pixel_cache.get(str(path))
        if cached is None:
            with Image.open(path) as opened:
                original = opened.convert('RGBA')
        else:
            original = cached.convert('RGBA')
        image = original
        try:
            arr = np.array(original, dtype=np.uint8)
            bg_rgb = np.array(gap_color[:3], dtype=np.int16)
            content = (np.max(np.abs(arr[:, :, :3].astype(np.int16) - bg_rgb), axis=2) > 6) & (arr[:, :, 3] > 8)
            if np.any(content):
                h, w = content.shape
                ys_thr = np.where(content.sum(axis=1) > max(12, int(w * 0.01)))[0]
                xs_thr = np.where(content.sum(axis=0) > max(12, int(h * 0.01)))[0]
                ys_any = np.where(content.any(axis=1))[0]
                xs_any = np.where(content.any(axis=0))[0]
                if ys_any.size and xs_any.size:
                    y0 = int(ys_thr[0]) if ys_thr.size else int(ys_any[0])
                    x0 = int(xs_thr[0]) if xs_thr.size else int(xs_any[0])
                    image = original.crop((x0, y0, int(xs_any[-1]) + 1, int(ys_any[-1]) + 1))
        except Exception:
            pass
        return original, image, image.tobytes()

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

    def _cleanup_dead_directories(self):
        """Delete directories that are no longer in the current video_path list."""
        current_video_dirs = {Path(p).resolve() for p in self.shared_config.video_path}

        for item in self.cache_dir.iterdir():
            if item.is_dir() and item.resolve() not in current_video_dirs:
                # Never delete the stitch_cache directory itself
                if item.resolve() in (self.disk_cache_dir.resolve(), self.image_disk_cache_dir.resolve()):
                    continue
                shutil.rmtree(str(item))

    def _filename_converter(self, input_value, video_idx, config=None):
        '''Bidirectional conversion: logical index <-> timestamp/frame filename.'''
        config = config if config is not None else self.shared_config
        if isinstance(input_value, int):
            step = config.skip_frames + 1
            phys_idx = input_value * step
            fps = float(config.video_fps_list[video_idx] or 0)
            fps_int = max(1, int(round(fps))) if fps > 0 else 1
            fps_safe = fps if fps > 0 else float(fps_int)

            t = phys_idx / fps_safe
            sec_str = f"{t:.2f}".rstrip("0").rstrip(".") or "0"

            k = (phys_idx % fps_int) + 1

            if k > fps_int:
                k = fps_int
            if k < 1:
                k = 1
            return f"{sec_str}s_frame_{k}.jpeg"

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
                        snapshot = self._render_snapshot
                        if snapshot is not None and not snapshot[2]:
                            target = tuple(int(v) for v in snapshot[0].layout_params[6])
                            if len(target)==2 and min(target)>0 and target[0]*target[1]*4 <= self._pixel_cache.limit:
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

try:
    import winreg
except ImportError:
    winreg = None

from PIL import ImageFont



class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type, default_path=None):
        self.shared_config = SharedConfig()
        super().__init__(parent)
        try:
            img_sizer = self.scrolledWindow_img.GetSizer()
            if isinstance(img_sizer, wx.FlexGridSizer):
                pass
        except Exception:
            pass
        self.create_ImgManager()
        self.video_manager = VideoManager(owner=self,shared_config=self.shared_config,ImgManager=self.ImgManager)
        self.image_stitch_executor = None  # Image-mode stitch thread pool
        self.image_pipeline = ImagePipeline(self.video_manager.disk_cache_dir,
                                            self._image_frame_ready, wx.CallAfter)
        self.memory_reclaimer = MemoryReclaimer()
        owner_ref = weakref.ref(self)
        def metrics_ready():
            def update():
                owner = owner_ref()
                if owner is not None and not getattr(owner, '_is_closing', False):
                    owner._refresh_power_tooltip()
            wx.CallAfter(update)
        self.resource_monitor = ResourceMonitor(notify=metrics_ready)
        self._image_stitch_lock = threading.Lock()  # Lock for image stitching state
        self.shift_pressed=False
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.output_config_path = Path(get_resource_path(str(Path("configs")))) / "default_config.json"
        pos = self.GetPosition()
        size = self.GetSize()
        self._normal_window_pos = (pos[0], pos[1])
        self._normal_window_size = (size[0], size[1])
        self._is_closing = False
        self._parallel_switch_dirty = False

        self.hotkeys = self.get_default_hotkeys()
        try:
            with open(self.output_config_path, "r", encoding="utf-8") as f:
                self.hotkeys = self.normalize_hotkeys(json.load(f).get("hotkeys", {}))
        except Exception:
            pass
        self.apply_hotkeys(self.hotkeys)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.img_name = []
        self.selected_img_id = 0
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 1000
        self.height = 600
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1
        self.color_list = []
        self.box_id = -1
        self.xy_magnifier = []
        self.show_scale_proportion = 0
        self.key_status = {"shift_s": 0, "ctrl": 0, "alt": 0}
        self.indextablegui = None
        self.aboutgui = None
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)
        self.m_statusBar1.SetStatusWidths([-2, -1, -4, -4])
        self.set_title_font()
        self.hidden_flag = 0
        self.button_open_all.SetToolTip("open")
        self.out_path_button.SetToolTip("out path")
        self.save_butoon.SetToolTip("save")
        self.left_arrow_button.SetToolTip("left arrow")
        self.right_arrow_button.SetToolTip("right arrow")
        self.refresh_button.SetToolTip("refresh")
        self.save_config_button.SetToolTip("save_configuration")
        self.magnifier.SetToolTip("magnifier")
        self.rotation.SetToolTip("rotation")
        self.flip.SetToolTip("flip")
        self.load_config_button.SetToolTip("load_configuration")
        self.reset_config_button.SetToolTip("reset_configuration")
        # Different platforms may need to adjust the width of the scrolledWindow_set
        sys_platform = platform.system()
        if sys_platform.find("Windows") >= 0:
            self.width_setting = 300
        elif sys_platform.find("Linux") >= 0:
            self.width_setting = 280
        elif sys_platform.find("Darwin") >= 0:
            self.width_setting = 350
        else:
            self.width_setting = 300
        self.SashPosition = self.width-self.width_setting
        self.m_splitter1.SetSashPosition(self.SashPosition)
        self.split_changing = False
        self.width_setting_ = self.width_setting
        self.play_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_play_timer, self.play_timer)
        self._from_timer = False     # Distinguish timer-triggered actions from user clicks

        # Draw color to box
        self.colourPicker_draw.Bind(
            wx.EVT_COLOURPICKER_CHANGED, self.draw_color_change)

        # Check the software version
        self.myEVT_MY_TEST = wx.NewEventType()
        EVT_MY_TEST = wx.PyEventBinder(self.myEVT_MY_TEST, 1)
        self.Bind(EVT_MY_TEST, self.EVT_MY_TEST_OnHandle)
        self.version = VERSION
        self.check_version()

        # open default path
        if default_path:
            try:
                self.ImgManager.init(default_path, type=2)  # one_dir_mul_img
                self.show_img_init()
                self.ImgManager.set_action_count(0)
                self.show_img()
            except:
                pass
        self._bind_legacy_control_aliases()
        self.load_configuration( None , config_name="default_config.json")
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_right_click)
        self.custom_algorithms = []
        self._bind_compat_events()
        self._bind_settings_wheel_guard()

        def _bind_accel_guard_recursive(parent):
            for child in parent.GetChildren():
                if isinstance(child, (wx.TextCtrl, wx.SpinCtrl, wx.SpinCtrlDouble)):
                    child.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                    child.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
                _bind_accel_guard_recursive(child)
        _bind_accel_guard_recursive(self)
        self._restore_window_state()

    def _bind_legacy_control_aliases(self):
        # Keep older handwritten logic working after GUI control renames.
        alias_map = {
            "title_show_rename": "m_checkBox31",
            "title_rename_text": "m_textCtrl16",
            "custom_algorithm_input": "m_textCtrl15",
            "m_textCtrl28": "interval",
            "m_textCtrl30": "cache_frames",
            "m_textCtrl281": "row_col13",
            "right_arrow_button1": "play",
        }
        for legacy_name, current_name in alias_map.items():
            if not hasattr(self, legacy_name) and hasattr(self, current_name):
                setattr(self, legacy_name, getattr(self, current_name))

    def _bind_compat_events(self):
        self.power_mode.Bind(wx.EVT_ENTER_WINDOW, self._show_thread_pipeline_status)
        self.power_mode.Bind(wx.EVT_CHOICE, self.on_power_mode_changed)
        self.interval.Bind(wx.EVT_TEXT, self._on_interval_text_edited)
        if hasattr(self, "title_exif"):
            self.title_exif.Bind(wx.EVT_CHECKBOX, self.on_title_exif_changed)

        if hasattr(self, "title_rename_text"):
            self.title_rename_text.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
            self.title_rename_text.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
        if hasattr(self, "title_show_rename"):
            self.title_show_rename.Bind(wx.EVT_CHECKBOX, self.title_rename_fc)

        if hasattr(self, "show_all_func"):
            self.show_all_func.Bind(wx.EVT_CHECKBOX, self.on_show_all_func_changed)
        if hasattr(self, "show_custom_func"):
            self.show_custom_func.Bind(wx.EVT_CHECKBOX, self.on_show_custom_func_changed)

        if hasattr(self, "custom_algorithm_input"):
            self.custom_algorithm_input.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
            self.custom_algorithm_input.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
            self.custom_algorithm_input.Bind(wx.EVT_CHAR_HOOK, self._handle_custom_algorithm_key)
        if hasattr(self, "m_button10"):
            self.m_button10.Bind(wx.EVT_BUTTON, self.remove_custom_algorithm)
        if hasattr(self, "play"):
            try:
                self.play.Unbind(wx.EVT_BUTTON)
            except Exception:
                pass
            self.play.Bind(wx.EVT_BUTTON, self.toggle_play)
        for field_name in ("slider_value", "show_all_func_layout"):
            if hasattr(self, field_name):
                field = getattr(self, field_name)
                field.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)

        video_field_handlers = [
            ("interval", self.on_interval_changed),
            ("cache_frames", self.on_cache_num_change),
            ("cache_multiplier", self.on_cache_num_change),
            ("m_textCtrl281", self.on_skip_changed),
        ]
        for field_name, handler in video_field_handlers:
            if hasattr(self, field_name):
                field = getattr(self, field_name)
                field.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, handler)
                # ★ 回车直接提交: 单行 TextCtrl 默认不处理回车, 必须显式加上
                #   TE_PROCESS_ENTER, 否则 EVT_TEXT_ENTER 永远不触发。
                #   有了它, 输入框里按回车就等于"改好了", 不用再点别处失焦。
                try:
                    field.SetStyle(field.GetStyle() | wx.TE_PROCESS_ENTER)
                    field.Bind(wx.EVT_TEXT_ENTER, self.on_video_field_enter)
                except Exception:
                    pass

    def _handle_custom_algorithm_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.add_custom_algorithm(event)
            return
        event.Skip()

    def _rebuild_threads(self, n):
        # Legacy refresh/configuration entry: honor power_mode's shared budget.
        self.video_manager.update_thread_count()

    # ========== 视频设置数值框的提交 ==========
    # ★ 这些框以前只靠 EVT_KILL_FOCUS 才写回 shared_config, 而 refresh() 是直接读
    #   shared_config 的。于是"改了生不生效"完全取决于一个看不见的事件:
    #     - 从菜单/快捷键刷新时输入框不会失焦, 改动被静默丢弃;
    #     - 输入非法内容时 int() 会在事件处理里抛异常, 值悄悄保持旧的, 而输入框
    #       一直显示着你打的字 —— 看上去就是"改了没反应";
    #     - 生效了也没有任何回显, 光标 "|" 一直留在框里, 分不清到底提交没有。
    #   现在统一走 _commit_video_settings(): 读框 -> 校验 -> 归一化 -> 写回框里,
    #   保证输入框显示的永远是当前真正生效的值, refresh() 开头也会主动提交一次。
    def _commit_video_settings(self):
        """把视频设置里的数值输入框提交到 shared_config, 并把框里的文本归一化。"""

        def _read_number(field, default, minimum, integer=True):
            try:
                raw = str(field.GetValue()).strip()
            except Exception:
                raw = ""
            value = default
            if raw:
                try:
                    value = int(float(raw)) if integer else float(raw)
                except (TypeError, ValueError, OverflowError):
                    value = default
            try:
                if not math.isfinite(value):
                    value = default
                value = max(minimum, value)
            except (TypeError, ValueError):
                value = default
            return value

        # ---- 播放间隔 ----
        interval = _read_number(self.interval, 1.0,
                                0.001 if self.shared_config.video_mode else 0.05, integer=False)
        if self.shared_config.video_mode:
            interval = math.ceil(interval * 1000 - 1e-9) / 1000.0
            if (getattr(self, '_interval_user_edited', False)
                    or abs(float(self.shared_config.interval) - interval) > 1e-9):
                self.shared_config.manual_interval = interval
            self._interval_user_edited = False
            manual = self.shared_config.manual_interval
            if manual is not None:
                interval = max(manual, self.shared_config.interval_recommend or 0.0)
        if abs(float(self.shared_config.interval) - interval) > 1e-9:
            self.shared_config.interval = interval
            # 播放中改间隔, 立即重启 timer 让新值生效
            if getattr(self.shared_config, "is_playing", False):
                try:
                    if self.shared_config.video_mode:
                        if not getattr(self, '_play_timer_suspended', False):
                            self._schedule_next_video_tick()
                    else:
                        self.play_timer.Start(max(1, math.ceil(interval * 1000)), oneShot=False)
                except Exception:
                    pass

        # Global performance policy applies to images and videos alike.
        self._apply_resource_policy()

        # ---- Cached Frames (缓存帧数) ----
        invalid_cache_fields = set()
        errors = []
        for field, attribute, label in ((self.cache_frames, 'cache_num', 'Cache frames'),
                                         (self.cache_multiplier, 'cache_multiplier', 'Cache multiplier')):
            if not hasattr(field, '_cache_input_background'):
                field._cache_input_background = field.GetBackgroundColour()
                tip = field.GetToolTip()
                field._cache_input_tip = tip.GetTip() if tip else 'Integer >= 1'
            try:
                value = positive_cache_integer(field.GetValue())
            except ValueError:
                invalid_cache_fields.add(id(field))
                effective = getattr(self.shared_config, attribute)
                message = f'{label}: enter an integer >= 1; current effective value: {effective}'
                errors.append(message)
                field.SetBackgroundColour(wx.Colour(255, 225, 225))
                field.SetToolTip(message)
            else:
                setattr(self.shared_config, attribute, value)
                field.SetBackgroundColour(field._cache_input_background)
                field.SetToolTip(field._cache_input_tip)
            field.Refresh()
        self._performance_input_errors = errors
        if errors:
            self.SetStatusText_(['-1', '-1', '***Invalid parameter: ' + '; '.join(errors) + '***', '-1'])

        # ---- Skip Frame (跳过帧数) ----
        skip = _read_number(self.m_textCtrl281, 0, 0)
        self.shared_config.skip_frames = skip
        self.ImgManager.skip = skip

        # 归一化: 输入框里显示的必须是当前真正生效的值
        for field, value in ((self.interval, self.shared_config.interval),
                              (self.cache_frames, self.shared_config.cache_num),
                              (self.cache_multiplier, self.shared_config.cache_multiplier),
                              (self.m_textCtrl281, self.shared_config.skip_frames)):
            try:
                if id(field) in invalid_cache_fields:
                    continue
                text = str(value)
                if str(field.GetValue()).strip() != text:
                    if field is self.interval:
                        field.ChangeValue(text)
                    else:
                        field.SetValue(text)
            except Exception:
                pass

    def _blur_settings_field(self):
        """刷新/回车提交后, 如果光标还停在设置区的输入框里, 把焦点挪走。

        否则输入框一直闪着 "|" 光标, 看着就像刚才那次修改没提交上去。
        """
        try:
            focus = wx.Window.FindFocus()
        except Exception:
            return
        if focus is None:
            return
        settings = getattr(self, "scrolledWindow_set", None)
        node = focus
        while node is not None:
            if node is settings:
                break
            node = node.GetParent()
        else:
            return
        target = getattr(self, "refresh_button", None)
        if target is None:
            return
        try:
            target.SetFocus()
        except Exception:
            pass

    def on_video_field_enter(self, event):
        """在视频设置的数值框里按回车: 立刻提交, 并把光标收掉。"""
        self._commit_video_settings()
        self._blur_settings_field()
        if event is not None:
            event.Skip()

    def on_cache_num_change(self, event):
        self._commit_video_settings()
        if getattr(self.ImgManager, 'type', None) is not None:
            self.show_img()
        if event is not None:
            event.Skip()

    def on_skip_changed(self, event):
        self._commit_video_settings()
        if event is not None:
            event.Skip()

    def on_thread_change(self, event):
        self._commit_video_settings()
        if event is not None:
            event.Skip()

    def _apply_resource_policy(self):
        mode = self.power_mode.GetSelection() + 1
        key = mode, bool(self.shared_config.video_mode)
        previous_key = getattr(self, '_resource_policy_key', None)
        if key == previous_key:
            return
        # Keep a common reference when comparing modes. Sampling only free RAM
        # again after our own caches warmed could make Maximum's budget smaller.
        if not hasattr(self, '_resource_memory_reference'):
            self._resource_memory_reference = available_memory_bytes()
        policy = resource_budget(mode, self.shared_config.video_mode,
                                 available=self._resource_memory_reference)
        self.shared_config.power_mode = policy.mode
        self.shared_config.thread = policy.workers
        self.shared_config.memory_budget = policy.memory
        self.video_manager._configure_video_memory()
        self._resource_policy_key = key
        self.resource_monitor.reset()
        self.video_manager._playback_pacer.reset()
        self.video_manager._pacing_model_period = None
        if self.shared_config.video_mode:
            with self.video_manager._cache_guard:
                self.video_manager._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
                self.video_manager._optimizer_seen = {}
                self.video_manager._pending_thread_plan = None
                self.video_manager._cooldown_deadline = 0.0
            self.video_manager.update_thread_count()
        self._show_resource_tooltip()
        if previous_key is not None and mode < previous_key[0]:
            self._request_memory_reclaim()
        else:
            self.memory_reclaimer.cancel()

    def _request_memory_reclaim(self):
        """Wait for old work off-GUI, join retired pools, then return free RAM."""
        vm, pipeline = self.video_manager, self.image_pipeline
        with vm._cache_guard:
            old_work = list(set(vm._pending_extract.values()) | set(vm._window_stitches.values()))
        with pipeline.lock:
            old_work.extend(pipeline.running.values())
        owner_ref = weakref.ref(self)
        def ready():
            owner = owner_ref()
            if owner is None or getattr(owner, '_is_closing', False):
                return True
            if any(not future.done() for future in old_work):
                return False
            if (owner.shared_config.video_mode
                    and vm._extract_threads + vm._stitch_threads > owner.shared_config.thread):
                # A concurrent layout invalidation can cancel a queued resize.
                # Reissue the smaller budget without requiring another GUI edit.
                vm.update_thread_count()
                return False
            with vm._cache_guard:
                if vm._pending_thread_plan is not None:
                    return False
            with pipeline.lock:
                if (not owner.shared_config.video_mode and pipeline.window is not None
                        and (pipeline.budget != owner.shared_config.thread
                             or pipeline.memory != owner.shared_config.memory_budget
                             or pipeline.workers != pipeline.desired_workers)):
                    return False
            return True
        def retire():
            vm._pipeline_workers.trim_idle()
            vm._decoder_bank.trim()
            old_work.clear()  # Do not retain Future result/exception pixel buffers.
            with vm._cache_guard:
                pools = getattr(vm, '_retired_pools', [])
                vm._retired_pools = []
            with pipeline.lock:
                pools += pipeline.retired_pools
                pipeline.retired_pools = []
            for pool in pools:
                pool.shutdown(wait=True)
            pools.clear()
        def allow_trim():
            owner = owner_ref()
            if owner is None or getattr(owner, '_is_closing', False) or owner.shared_config.is_playing:
                return False
            with vm._cache_guard:
                video_busy = bool(vm._pending_extract or vm._window_stitches
                                  or getattr(vm, '_display_delivery_pending', False))
            with pipeline.lock:
                return not video_busy and not pipeline.running and pipeline.display_key is None
        self.memory_reclaimer.request(ready, retire, allow_trim)

    def on_power_mode_changed(self, event):
        self._commit_video_settings()
        if getattr(self.ImgManager, 'type', None) is not None:
            if self.shared_config.video_mode:
                self.video_manager.update_cache()
            self.show_img()
        if event is not None:
            event.Skip()

    def _show_resource_tooltip(self):
        if self.shared_config.video_mode:
            self.video_manager._publish_thread_allocation()
        else:
            pipeline = self.image_pipeline
            self.shared_config.thread_allocation = dict(budget=self.shared_config.thread,
                extract=0, stitch=pipeline.workers or pipeline.desired_workers)
            self._refresh_power_tooltip()

    def _refresh_power_tooltip(self):
        if getattr(self, '_is_closing', False):
            return
        cfg = self.shared_config
        if cfg.video_mode:
            vm = self.video_manager
            text = f"Extract: {vm._extract_threads}, stitch: {vm._stitch_threads}; budget: {cfg.thread}"
            pending = vm._pending_thread_plan
            if pending:
                text += f"\nPending: extract {pending[0]}, stitch {pending[1]}"
        else:
            pipeline = self.image_pipeline
            text = f"Stitch: {pipeline.workers or pipeline.desired_workers}; budget: {cfg.thread}"
        monitor = getattr(self, 'resource_monitor', None)
        stats = monitor.read_snapshot() if monitor is not None else {}
        cpu, memory, fps = stats.get('cpu'), stats.get('memory'), stats.get('fps')
        if cpu is None or memory is None:
            text += '\nCPU / RAM avg (10s): sampling...' if stats.get('available', True) else '\nCPU / RAM: unavailable (psutil)'
        else:
            usage = f'{memory / 1024**3:.2f} GiB' if memory >= 1024**3 else f'{memory / 1024**2:.0f} MiB'
            text += f'\nCPU avg (10s): {cpu:.1f}%; RAM avg: {usage}'
        text += ('\nPlayback: paused' if not cfg.is_playing else
                 f'\nPlayback: {fps:.1f} FPS' if fps is not None else '\nPlayback: sampling...')
        tooltip = self.power_mode.GetToolTip()
        if tooltip is None:
            self.power_mode.SetToolTip(text)
        elif tooltip.GetTip() != text:
            tooltip.SetTip(text)

    def on_enable_video_mode(self, event):
        prev_video_mode = self.shared_config.video_mode
        self.shared_config.video_mode = self.m_checkBox33.GetValue()
        self._apply_resource_policy()
        on_video_mode_change(self.shared_config.video_mode)

        # Manage the image stitch pool based on mode
        if self.shared_config.video_mode:
            # Entering video mode: release image stitch pool
            self._shutdown_image_stitch_executor()
        else:
            # Entering image mode: initialize image stitch pool
            self._init_image_stitch_executor()
            # ★ 从视频模式切到图片模式时，主动清理视频模式的本地缓存，
            #   防止陈旧的视频帧 / 路径被图片模式的渲染路径误用，
            #   也能避免误把 video_mode 再切回 True 时显示旧的视频帧。
            if prev_video_mode:
                self._clear_video_mode_cache()

        # ★ 切换模式后自动刷新并显示。
        #   进入视频模式时如果已经选过视频，立即重建缓存并显示首帧；
        #   如果还没选视频，给出明确提示，而不是停在 "Waiting for batch 0"。
        self._auto_refresh_after_mode_switch()

    def _auto_refresh_after_mode_switch(self):
        """模式切换后自动刷新显示。

        进入视频模式时:
        - 已经有选好的视频 -> 重建抽帧/拼接缓存并显示首帧;
        - 还没有选视频     -> 状态栏给出明确提示, 避免一直显示 "Waiting for batch 0"。
        """
        if getattr(self, "_is_closing", False):
            return
        if not getattr(self.shared_config, "video_mode", False):
            return
        try:
            if not getattr(self.shared_config, "real_video_path", None):
                self.SetStatusText_([
                    "-1", "-1",
                    "***Video mode: please select a video input***", "-1"])
                return

            self.shared_config.batch_idx = 0
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            # show_img_init() 会因布局变化清空视频缓存, 这里必须重新抽帧+拼接
            self.video_manager.update_cache()
            self.show_img()
        except Exception as ex:
            if getattr(self.shared_config, "debug_video", False):
                print(f"[VideoMode] auto refresh after mode switch failed: {ex}")

    def _capture_video_render_snapshot(self):
        """Capture wx controls on the GUI thread; workers use a private model."""
        vm = self.video_manager
        if len(self.ImgManager.layout_params) <= 32:
            self.show_img_init()
        custom = bool(self.show_custom_func.GetValue())
        key = (repr(self.ImgManager.layout_params), repr(self.xy_magnifier), custom,
               vm._cache_context_token())
        if vm._render_snapshot is None or key != getattr(vm, '_render_snapshot_key', None):
            vm._render_snapshot = (self.ImgManager.video_stitch_snapshot(),
                                   copy.deepcopy(self.xy_magnifier), custom)
            vm._render_snapshot_key = key

    def _video_frame_ready(self, batch, token):
        if (not getattr(self, '_is_closing', False) and self.shared_config.video_mode
                and self.video_manager._window_token == token
                and int(self.shared_config.batch_idx) == batch):
            self.show_img()

    def _video_buffer_changed(self, token):
        vm = self.video_manager
        with vm._cache_guard:
            vm._pacing_notification_pending = False
        if (not getattr(self, '_is_closing', False) and self.shared_config.video_mode
                and token == vm._window_token):
            vm._refresh_playback_interval()

    def _request_video_display(self, batch, path):
        """Prepare a PNG in a worker; only the latest request may paint."""
        vm = self.video_manager
        token = vm._window_token
        key = (batch, path, token)
        if key == getattr(self, '_video_display_key', None):
            self._resume_play_timer_after_wait()
            return
        if key == getattr(vm, '_display_key', None) and getattr(vm, '_display_delivery_pending', False):
            return
        vm._display_serial += 1
        serial = vm._display_serial
        vm._display_key = key
        vm._display_delivery_pending = True
        if vm._display_future is not None:
            vm._display_future.cancel()
        if self.shared_config.is_playing:
            self._suspend_play_timer_for_wait()
        gap_color = tuple(self.ImgManager.gap_color)
        def prepare():
            started = time.perf_counter()
            pixels = vm._prepare_video_image(path, gap_color)
            return pixels, time.perf_counter() - started
        future = vm._display_executor.submit(prepare)
        vm._display_future = future
        owner_ref = weakref.ref(self)

        def done(completed):
            if completed.cancelled():
                return
            try:
                result, error = completed.result(), None
            except Exception as ex:
                result, error = None, str(ex)
            def deliver():
                if vm._display_future is completed:
                    vm._display_future = None
                owner = owner_ref()
                if (owner is None or getattr(owner, '_is_closing', False)
                        or not owner.shared_config.video_mode
                        or serial != vm._display_serial or token != vm._window_token
                        or int(owner.shared_config.batch_idx) != batch):
                    return
                if error:
                    vm._display_delivery_pending = False
                    with vm._cache_guard:
                        cache = owner.shared_config.cache_img
                        if 0 <= batch < len(cache) and cache[batch] == path:
                            cache[batch] = None
                    owner.SetStatusText_(['-1', '-1', f'***Load cache failed: {error}***', '-1'])
                    vm.update_cache()
                    if owner.shared_config.is_playing:
                        owner._schedule_frame_wait()
                    return
                pixels, load_cost = result
                original, prepared, rgba = pixels
                paint_started = time.perf_counter()
                for name, value in vm._batch_render_states.get(batch, {}).items():
                    setattr(owner.ImgManager, name, value)
                owner.ImgManager.img = original
                owner.show_bmp_in_panel = original
                owner.img_size = original.size
                owner.display_bitmap(True, prepared, prepared_rgba=rgba)
                if owner.shared_config.is_playing:
                    owner.resource_monitor.frame_presented(batch, owner.shared_config.play_direction)
                owner._video_display_key = key
                vm._display_delivery_pending = False
                vm.perf_monitor.record_display(load_cost + time.perf_counter() - paint_started)
                if owner.shared_config.is_playing and vm.perf_monitor.push_render_event(
                        batch, owner.shared_config.play_direction):
                    vm._mark_batch_processed()
                owner._cancel_pending_frame_wait()
                owner._resume_play_timer_after_wait()
            wx.CallAfter(deliver)
        future.add_done_callback(done)

    def _rebuild_video_cache_for_batch(self, batch_idx):
        """安排后台拆帧和拼接；当前批次已经就绪时返回缓存 PNG 路径。

        返回 None 表示无法重建(未选视频 / 抽帧失败 / 拼接失败)。
        """
        vm = getattr(self, "video_manager", None)
        if vm is None:
            return None
        if not getattr(self.shared_config, "video_path", None):
            return None
        if not getattr(self.shared_config, "real_video_path", None):
            return None
        try:
            self.shared_config.batch_idx = int(batch_idx)
            vm.update_cache()
        except Exception as ex:
            if getattr(self.shared_config, "debug_video", False):
                print(f"[VideoMode] rebuild cache failed batch={batch_idx} error={ex}")
            return None

        # ★ 复用已有缓存时统一走 _video_cached_batch_path 做有效性校验
        entry = self._video_cached_batch_path(int(batch_idx))
        if entry:
            return entry
        return None

    def _video_cached_batch_path(self, batch_idx):
        """取视频模式指定批次已拼接好的缓存图路径; 缓存无效时返回 None。"""
        vm = getattr(self, "video_manager", None)
        if vm is None:
            return None
        try:
            return vm._cached_batch_path(int(batch_idx), validate=False)
        except Exception:
            return None

    def _rebuild_video_cache_and_show(self):
        """安排当前批次后台重建，并显示已有画面或等待状态。"""
        if getattr(self, "_is_closing", False):
            return
        if not getattr(self.shared_config, "video_mode", False):
            return
        try:
            self._rebuild_video_cache_for_batch(int(self.shared_config.batch_idx))
            self.show_img()
        except Exception as ex:
            if getattr(self.shared_config, "debug_video", False):
                print(f"[VideoMode] rebuild cache and show failed: {ex}")

    # def on_interval_changed(self, event):
    #     self.shared_config.interval = float(self.interval.GetValue() or 1.0)
    #b1 修改
    def _show_thread_pipeline_status(self, event):
        self._show_resource_tooltip()
        event.Skip()

    def _on_interval_text_edited(self, event):
        self._interval_user_edited = True
        event.Skip()

    def on_interval_changed(self, event):
        # 统一走 _commit_video_settings (读框 -> 校验 -> 归一化 -> 写回)
        self._commit_video_settings()
        event.Skip()

    def toggle_play(self, event):
        self._commit_video_settings()
        self.resource_monitor.reset_playback()
        self.shared_config.is_playing = not self.shared_config.is_playing

        if self.shared_config.is_playing:
            if getattr(self, "last_direction", 0) == 0:
                self.last_direction = 1
            self.shared_config.play_direction = getattr(self, "last_direction", 1)
        if self.shared_config.is_playing:
            self._play_timer_suspended = False
            self._video_tick_started_at = None
            if self.shared_config.video_mode:
                self._schedule_next_video_tick()
            else:
                interval = float(self.interval.GetValue() or 1.0)
                self.play_timer.Start(max(1, math.ceil(interval * 1000)), oneShot=False)
            label = "⏸"
        else:
            self.play_timer.Stop()
            label = "▶"

        vm = getattr(self, "video_manager", None)
        if vm:
            vm.perf_monitor.reset_render_clock()
            vm.perf_monitor.render_history.clear()
            if self.shared_config.is_playing and self.shared_config.video_mode:
                vm._admission_limit()
                vm._admission_optimizer.restart_observation()
                vm._initialize_thread_pools()
                vm._maybe_evaluate_performance(force=True)

        self.right_arrow_button1.SetLabel(label)

    def on_play_timer(self, event):
        if self.shared_config.is_playing:
            if self.shared_config.video_mode:
                if getattr(self, '_play_timer_suspended', False):
                    return
                self.video_manager._refresh_playback_interval(reschedule=False)
                previous_tick = getattr(self, '_video_tick_started_at', None)
                if (previous_tick is not None and time.perf_counter() - previous_tick
                        < self.shared_config.interval - .001):
                    self._schedule_next_video_tick()
                    return
                self._video_tick_started_at = time.perf_counter()
            self._from_timer = True
            try:
                if self.shared_config.play_direction >= 0:
                    self.next_img(None)  # Forward playback
                else:
                    self.last_img(None)  # Reverse playback
            finally:
                self._from_timer = False

    def _schedule_next_video_tick(self):
        """Pace request-to-request, subtracting time already spent on this frame."""
        if (not self.shared_config.is_playing or getattr(self, '_is_closing', False)
                or getattr(self, '_play_timer_suspended', False)):
            return
        started = getattr(self, '_video_tick_started_at', None)
        elapsed = max(0.0, time.perf_counter() - started) if started is not None else 0.0
        delay = max(0.0, float(self.shared_config.interval) - elapsed)
        self._video_timer_generation = getattr(self, '_video_timer_generation', 0) + 1
        # A positive native timer gives paint/input/idle events a chance to run;
        # chaining CallAfter indefinitely can keep the GUI queue continuously busy.
        self.play_timer.Start(min(2147483647, max(1, math.ceil(delay * 1000 - 1e-9))), oneShot=True)

    def _dispatch_video_tick(self, generation):
        if (generation == getattr(self, '_video_timer_generation', None)
                and self.shared_config.video_mode and self.shared_config.is_playing
                and not getattr(self, '_is_closing', False)
                and not getattr(self, '_play_timer_suspended', False)):
            self.on_play_timer(None)

    def parallel_sequential_fc(self, event):
        self.shared_config.parallel_sequential = self.parallel_sequential.GetValue()
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False
            self.shared_config.parallel_to_sequential =False
        if self.shared_config.video_mode:
            self._parallel_switch_dirty = True
        else:
            # ★ 图片模式：不再立刻重建 + 重绘。
            #   这里只把状态标记为"待应用"，等用户手动刷新（⟳ / 菜单 Refresh）时
            #   由 _apply_parallel_switch() 统一重建并显示，避免切换瞬间就重扫目录、重拼接。
            self._parallel_switch_dirty = True
            self._notify_parallel_switch_pending()

    def _notify_parallel_switch_pending(self):
        """提示用户: 并行/串行读取方式已改变, 需要手动刷新后生效。"""
        if getattr(self.shared_config, "video_mode", False):
            return
        try:
            self.SetStatusText_([
                "-1", "-1",
                "***Parallel setting changed, press Refresh to apply***", "-1"])
        except Exception:
            pass

    def _suspend_play_timer_for_wait(self):
        """暂停播放 timer，防止等待拼接期间继续前进/跳帧"""
        if getattr(self, "_play_timer_suspended", False):
            return
        self._play_timer_suspended = True
        self._video_timer_generation = getattr(self, '_video_timer_generation', 0) + 1
        try:
            self.play_timer.Stop()
        except Exception:
            pass

    def _resume_play_timer_after_wait(self):
        """恢复播放 timer"""
        if not getattr(self, "_play_timer_suspended", False):
            return
        self._play_timer_suspended = False
        if getattr(self.shared_config, "is_playing", False):
            try:
                if self.shared_config.video_mode:
                    self._schedule_next_video_tick()
                else:
                    interval_ms = max(1, math.ceil(float(self.shared_config.interval) * 1000))
                    self.play_timer.Start(interval_ms)
            except Exception:
                pass

    def _schedule_frame_wait(self, retry_ms: int = 80):
        """播放时目标批次还没拼接好: 暂停 timer, 轮询等待该帧就绪后再继续播放。

        show_img() 在缓存未命中且正在播放时会走到这里。此前这里直接调用了一个
        并不存在的方法(_schedule_frame_wait), 于是播放时一旦遇到"这一帧还没拼完"
        就抛 AttributeError, 播放直接中断。
        """
        target_batch = int(getattr(self.shared_config, "batch_idx", 0))
        self._suspend_play_timer_for_wait()
        self._schedule_frame_wait_retry(target_batch, retry_ms, attempt=0)

    def _schedule_frame_wait_retry(self, target_batch: int, retry_ms: int = 80, attempt: int = 0):
        """短暂延迟后重新检查目标帧是否就绪，不改变 batch_idx，不跳帧"""
        self._cancel_pending_frame_wait()

        # 等待上限: 约 10 秒仍拼不出来就放弃本次等待, 让播放继续/停下,
        # 避免在拼接一直失败时陷入无限轮询。
        max_attempts = max(1, int(10000 / max(1, retry_ms)))

        def _check():
            self._pending_frame_wait_timer = None
            if not getattr(self.shared_config, "is_playing", False):
                # 播放已被用户暂停/停止: 清掉挂起标记, 免得下次播放时 timer 起不来
                self._play_timer_suspended = False
                return
            if int(self.shared_config.batch_idx) != target_batch:
                # 用户在等待期间手动切换了帧，放弃本次等待
                self._resume_play_timer_after_wait()
                return

            if self._video_cached_batch_path(target_batch) is not None:
                # 目标帧终于就绪，恢复播放并展示
                self.show_img()
            elif attempt >= max_attempts:
                # 等太久了: 恢复 timer, 由下一拍继续尝试, 不再原地卡住播放
                self._resume_play_timer_after_wait()
            else:
                # 仍未就绪，继续轮询等待（不跳帧）
                self._schedule_frame_wait_retry(target_batch, retry_ms, attempt + 1)

        self._pending_frame_wait_timer = wx.CallLater(retry_ms, _check)

    def _cancel_pending_frame_wait(self):
        t = getattr(self, "_pending_frame_wait_timer", None)
        if t is not None:
            try:
                t.Stop()
            except Exception:
                pass
            self._pending_frame_wait_timer = None

    def _init_image_stitch_executor(self):
        """The bounded image pipeline creates its pool lazily in the background."""
        pass

    def _shutdown_image_stitch_executor(self):
        """Shut down the image-mode stitch pool."""
        if hasattr(self, 'image_pipeline'):
            if getattr(self, '_is_closing', False):
                self.image_pipeline.close()
                self.memory_reclaimer.close()
                self.resource_monitor.close()
            else:
                self.image_pipeline.invalidate()
        if self.image_stitch_executor is not None:
            self.image_stitch_executor.shutdown(wait=False)
            self.image_stitch_executor = None

    def parallel_to_sequential_fc(self, event):
        value = self.parallel_to_sequential.GetValue()
        self.shared_config.parallel_to_sequential = value
        if value:
            self.parallel_sequential.Value = False
            self.shared_config.parallel_sequential = False
        if self.shared_config.video_mode:
            self._parallel_switch_dirty = True
        else:
            # ★ 图片模式：同样不在切换瞬间重建 + 重绘，改为标记待应用，
            #   由用户手动刷新时通过 _apply_parallel_switch() 统一处理。
            self._parallel_switch_dirty = True
            self._notify_parallel_switch_pending()

    def _apply_parallel_switch(self):
        """应用 parallel / parallel+sequential 开关的变化。

        视频模式: 重新计算总帧数与每批帧数。
        图片模式: 按新的读取顺序（parallel_to_sequential / parallel_sequential）
                  重新初始化 ImgManager，并清空图片模式的渲染缓存。
        """
        if not getattr(self.shared_config, "video_mode", False):
            self._apply_parallel_switch_image()
            return

        nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None]
        if not nums:
            return

        if self.shared_config.parallel_to_sequential:
            self.ImgManager.img_num = sum(nums)
        else:
            self.ImgManager.img_num = max(nums)

        new_count = self._sync_video_count_per_action()
        if new_count:
            self.shared_config.count_per_action = new_count

        count = max(1, int(self.shared_config.count_per_action or 1))
        img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
        if img_num > 0:
            max_batches = (img_num + count - 1) // count
        else:
            max_batches = 1
        self.ImgManager.max_action_num = max(1, max_batches)

        max_idx = self.ImgManager.max_action_num - 1
        self.shared_config.batch_idx = min(self.shared_config.batch_idx, max(0, max_idx))
        self.ImgManager.action_count = self.shared_config.batch_idx
        self.ImgManager.img_count = self.shared_config.batch_idx * self.ImgManager.count_per_action

        self.shared_config.cache_img = []
        if hasattr(self.video_manager, "_last_batch"):
            self.video_manager._last_batch = None

    def _apply_parallel_switch_image(self):
        """图片模式下应用 parallel / parallel+sequential 的变化。

        手动刷新时调用：按新的读取方式重新初始化 ImgManager，
        并清空图片模式的渲染缓存，让随后的 show_img_init()/show_img()
        按新布局重新拼接显示。
        """
        img_mgr = getattr(self, "ImgManager", None)
        if (
            not img_mgr
            or not getattr(img_mgr, "input_path", None)
            or getattr(img_mgr, "type", None) not in (0, 1)
        ):
            return
        try:
            img_mgr.init(
                img_mgr.input_path,
                img_mgr.type,
                parallel_to_sequential=bool(self.shared_config.parallel_to_sequential),
                action_count=0,
                img_count=0,
                video_mode=False,
                skip=getattr(img_mgr, "skip", 0),
            )
            img_mgr.set_action_count(0)
            self.shared_config.batch_idx = 0
            self.shared_config.image_cache_img = []
            self.shared_config.image_cache_paths = []
        except Exception as ex:
            if getattr(self.shared_config, "debug_image", False):
                print(f"[ImageMode] apply parallel switch failed: {ex}")

    def EVT_MY_TEST_OnHandle(self, event):
        self.about_gui(None, update=True, new_version=event.GetEventArgs())

    def check_version(self):
        t1 = threading.Thread(target=self.run, args=())
        t1.setDaemon(True)
        t1.start()

    def run(self):
        url = "https://api.github.com/repos/nachifur/MulimgViewer/releases/latest"
        try:
            # make request to be an optional depend
            import requests

            resp = requests.get(url)
            resp.encoding = 'UTF-8'
            if resp.status_code == 200:
                output = resp.json()
                # version is "rolling" means that it is run from source code
                if self.version == output["tag_name"] or self.version == "rolling":
                    pass
                else:
                    evt = MyTestEvent(self.myEVT_MY_TEST)
                    evt.SetEventArgs(output["tag_name"])
                    wx.PostEvent(self, evt)
        except:
            pass

    def _get_system_font_display_name(self, font_path):
        try:
            font = ImageFont.truetype(str(font_path), 12)
            family, style = font.getname()
        except Exception:
            return None
        family = family.strip() if family else ""
        style = style.strip() if style else ""
        if not family:
            family = font_path.stem.replace("-", " ").replace("_", " ")
        if style and style.lower() not in ["regular", "normal", "roman"]:
            return f"{family} {style}"
        return family

    def _collect_font_items_from_dirs(self, font_dirs):
        font_items = []
        seen_names = set()
        seen_paths = set()
        valid_suffixes = {".ttf", ".otf", ".ttc"}
        for font_dir in font_dirs:
            font_dir = Path(font_dir)
            if not font_dir.exists():
                continue
            try:
                for font_path in font_dir.rglob("*"):
                    if not font_path.is_file():
                        continue
                    if font_path.suffix.lower() not in valid_suffixes:
                        continue
                    path_str = str(font_path)
                    path_key = path_str.lower()
                    if path_key in seen_paths:
                        continue
                    display_name = self._get_system_font_display_name(font_path)
                    if not display_name:
                        continue
                    name_key = display_name.lower()
                    if name_key in seen_names:
                        continue
                    seen_paths.add(path_key)
                    seen_names.add(name_key)
                    font_items.append((display_name, path_str))
            except Exception:
                continue
        return sorted(font_items, key=lambda item: item[0].lower())


    def set_title_font(self):
        self.title_font.Clear()
        sys_platform = platform.system()
        font_items = []
        if sys_platform.find("Windows") >= 0 and winreg is not None:
            font_dir = Path(r"C:\Windows\Fonts")
            font_enum = wx.FontEnumerator()
            font_names = sorted(set(font_enum.GetFacenames()), key=str.lower)
            registry_fonts = {}
            reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    i = 0
                    while True:
                        try:
                            display_name, font_file, _ = winreg.EnumValue(key, i)
                            i += 1
                            if not isinstance(font_file, str):
                                continue
                            font_path = font_dir / font_file
                            if not font_path.is_file():
                                continue
                            if font_path.suffix.lower() not in [".ttf", ".otf", ".ttc"]:
                                continue
                            clean_name = display_name.replace(" (TrueType)", "").replace(" (OpenType)", "")
                            registry_fonts[clean_name.lower()] = (clean_name, str(font_path))
                        except OSError:
                            break
            except Exception:
                registry_fonts = {}
            for name in font_names:
                item = registry_fonts.get(name.lower())
                if item:
                    font_items.append(item)
        elif sys_platform.find("Linux") >= 0:
            font_dirs = [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
                Path.home() / ".local" / "share" / "fonts",
            ]
            font_items = self._collect_font_items_from_dirs(font_dirs)
        elif sys_platform.find("Darwin") >= 0:
            font_dirs = [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts",
            ]
            font_items = self._collect_font_items_from_dirs(font_dirs)
        if font_items:
            for display_name, _ in font_items:
                self.title_font.Append(display_name)

            self.font_paths = [font_path for _, font_path in font_items]
            self.title_font.SetSelection(0)
            return
        font_path = Path("font") / "using"
        font_path = Path(get_resource_path(str(font_path)))
        files_name = [f.stem for f in font_path.iterdir()]
        files_name = np.sort(np.array(files_name)).tolist()
        for file_name in files_name:
            file_name = file_name.split("_", 1)[1]
            file_name = file_name.replace("-", " ")
            self.title_font.Append(file_name)
        if files_name:
            self.title_font.SetSelection(0)
        font_paths = [str(f) for f in font_path.iterdir()]
        self.font_paths = np.sort(np.array(font_paths)).tolist()

    def frame_resize(self, event):
        if not self.IsMaximized() and not self.IsIconized():
            pos = self.GetPosition()
            size = self.GetSize()
            self._normal_window_pos = (pos[0], pos[1])
            self._normal_window_size = (size[0], size[1])
        self.auto_layout(frame_resize=True)

    def open_all_img(self, event):
        previous_batch = self.shared_config.batch_idx
        previous_input_mode = self.shared_config.input_mode
        input_mode = self.choice_input_mode.GetSelection()
        self.shared_config.batch_idx = 0
        if input_mode == 0:
            self.shared_config.input_mode = 2
        elif input_mode == 1:
            self.shared_config.input_mode = 1
        elif input_mode == 2:
            self.shared_config.input_mode = 1
        else:
            self.shared_config.input_mode = 3
        if input_mode == 0:
            selected = self.one_dir_mul_img(event)
            if selected is False:
                self.shared_config.batch_idx = previous_batch
                self.shared_config.input_mode = previous_input_mode
        elif input_mode == 1:
            selected = self.one_dir_mul_dir_auto(event)
            if selected is False:
                self.shared_config.batch_idx = previous_batch
                self.shared_config.input_mode = previous_input_mode
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)
        elif input_mode == 3:
            self.onefilelist()

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=1)
            if not selected:
                return False
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return False
                self.ImgManager.init(dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
            finally:
                dlg.Destroy()
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        if self.shared_config.video_mode:
            # ★ show_img_init() 会因布局参数变化清空视频缓存，
            #   必须在它之后重新抽帧+拼接, 否则首帧缺失只会显示 "Waiting for batch 0"。
            self.video_manager.update_cache()
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(1)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])
        return True

    def close(self, event):
        if self._is_closing:
            return
        self._is_closing = True
        self._save_window_state()

        # ★ 修复：先停止所有后台任务，避免 rmtree 失败或线程残留
        try:
            self.play_timer.Stop()
        except Exception:
            pass
        # 标记为不再播放，避免 timer 回调中再次启动任务
        try:
            self.shared_config.is_playing = False
        except Exception:
            pass

        # 取消未开始的 pending frame wait，避免回调访问已销毁的窗口
        try:
            if hasattr(self, "_cancel_pending_frame_wait"):
                self._cancel_pending_frame_wait()
        except Exception:
            pass

        # Release thread pools
        if hasattr(self, "video_manager"):
            self.video_manager.shutdown()

        # Release the image-mode stitch pool
        self._shutdown_image_stitch_executor()

        if hasattr(self, 'show_bmp_in_panel'):
            del self.show_bmp_in_panel
        if hasattr(self, 'ImgManager'):
            if hasattr(self.ImgManager, 'clear_cache'):
                self.ImgManager.clear_cache()

        import gc
        gc.collect()

        # ★ 修复：用 try/except 包装 rmtree，避免目录被线程持有时抛出未捕获异常
        cache_base = "Video_frames"
        try:
            if os.path.isdir(cache_base):
                shutil.rmtree(cache_base, ignore_errors=False)
        except Exception:
            # 如果删除失败（线程持有文件句柄等），降级为 ignore_errors
            try:
                shutil.rmtree(cache_base, ignore_errors=True)
            except Exception:
                pass

        if hasattr(self, "indextablegui") and self.indextablegui:
            self.indextablegui.Destroy()
        if hasattr(self, "aboutgui") and self.aboutgui:
            self.aboutgui.Destroy()

        # ★ 修复：Destroy 自身
        try:
            self.Destroy()
        except Exception:
            pass

        # ★ 修复：通知主循环退出，确保程序完全终止
        try:
            wx.Exit()
        except Exception:
            pass

    def _save_window_state(self):
        try:
            if self.IsMaximized():
                x, y = self._normal_window_pos
                w, h = self._normal_window_size
                maximized = True
            else:
                pos = self.GetPosition()
                size = self.GetSize()
                x, y = pos[0], pos[1]
                w, h = size[0], size[1]
                maximized = False
            if self.output_config_path.exists():
                with open(self.output_config_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            else:
                data = {}
            data["window_state"] = {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "maximized": maximized,
            }
            with open(self.output_config_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=1)
        except Exception:
            pass

    def _restore_window_state(self):
        if not self.output_config_path.exists():
            return
        try:
            with open(self.output_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            window_state = data.get("window_state")
            if not isinstance(window_state, dict):
                return
            x = int(window_state["x"])
            y = int(window_state["y"])
            w = int(window_state["w"])
            h = int(window_state["h"])
            maximized = bool(window_state.get("maximized", False))
            self.SetSize((w, h))
            self.SetPosition((x, y))
            self._normal_window_pos = (x, y)
            self._normal_window_size = (w, h)
            if maximized:
                wx.CallAfter(self.Maximize, True)
        except Exception:
            pass

    def get_default_hotkeys(self):
        return {
            "next_img": "CTRL+N",
            "last_img": "CTRL+L",
            "save_img": "CTRL+S",
            "refresh": "CTRL+R",
            "hidden": "CTRL+H",
            "move_up": "UP",
            "move_down": "DOWN",
            "move_left": "LEFT",
            "move_right": "RIGHT",
            "delete_box": "DELETE",
        }

    def parse_hotkey(self, key_name):
        if key_name is None:
            return None
        tokens = [token.strip().upper() for token in str(key_name).split("+") if token.strip()]
        if not tokens:
            return None
        key_token = tokens[-1]
        modifier_tokens = tokens[:-1]
        modifier_map = {
            "CTRL": wx.ACCEL_CTRL,
            "CONTROL": wx.ACCEL_CTRL,
            "ALT": wx.ACCEL_ALT,
            "SHIFT": wx.ACCEL_SHIFT,
        }
        modifiers = wx.ACCEL_NORMAL
        used_modifiers = set()
        for token in modifier_tokens:
            if token not in modifier_map or token in used_modifiers:
                return None
            used_modifiers.add(token)
            modifiers |= modifier_map[token]
        special_keys = {
            "UP": wx.WXK_UP,
            "ARROWUP": wx.WXK_UP,
            "DOWN": wx.WXK_DOWN,
            "ARROWDOWN": wx.WXK_DOWN,
            "LEFT": wx.WXK_LEFT,
            "ARROWLEFT": wx.WXK_LEFT,
            "RIGHT": wx.WXK_RIGHT,
            "ARROWRIGHT": wx.WXK_RIGHT,
            "DELETE": wx.WXK_DELETE,
        }
        if key_token in special_keys:
            keycode = special_keys[key_token]
        elif len(key_token) == 1 and "A" <= key_token <= "Z":
            keycode = ord(key_token)
        else:
            return None
        return modifiers, keycode

    def normalize_hotkeys(self, hotkeys):
        defaults = self.get_default_hotkeys()
        if not isinstance(hotkeys, dict):
            return defaults.copy()
        normalized = defaults.copy()
        for action in defaults:
            value = hotkeys.get(action)
            if isinstance(value, str) and value.strip():
                normalized[action] = value.strip().upper()
        parsed_shortcuts = []
        for key_name in normalized.values():
            parsed = self.parse_hotkey(key_name)
            if parsed is None:
                return defaults.copy()
            parsed_shortcuts.append(parsed)
        if len(parsed_shortcuts) != len(set(parsed_shortcuts)):
            return defaults.copy()
        return normalized

    def get_hotkey_menu_items(self):
        return {
            "next_img": (self.menu_next, "Next"),
            "last_img": (self.menu_last, "Last"),
            "save_img": (self.menu_save, "Save"),
            "refresh": (self.menu_refresh, "Refresh"),
            "hidden": (self.menu_hidden, "Hidden"),
            "move_up": (self.menu_up, "Up"),
            "move_down": (self.menu_down, "Down"),
            "move_left": (self.menu_left, "Left"),
            "move_right": (self.menu_right, "Right"),
            "delete_box": (self.menu_delete_box, "Delete box"),
        }

    def format_hotkey_for_menu(self, key_name):
        tokens = [token.strip().upper() for token in str(key_name).split("+") if token.strip()]
        display_map = {
            "CTRL": "Ctrl",
            "CONTROL": "Ctrl",
            "ALT": "Alt",
            "SHIFT": "Shift",
            "UP": "Up",
            "ARROWUP": "Up",
            "DOWN": "Down",
            "ARROWDOWN": "Down",
            "LEFT": "Left",
            "ARROWLEFT": "Left",
            "RIGHT": "Right",
            "ARROWRIGHT": "Right",
            "DELETE": "Delete",
        }
        return "+".join(display_map.get(token, token.title() if len(token) > 1 else token) for token in tokens)

    def update_hotkey_menu_labels(self):
        for action, (menu_item, base_label) in self.get_hotkey_menu_items().items():
            hotkey_text = self.format_hotkey_for_menu(self.hotkeys[action])
            menu_item.SetItemLabel(f"{base_label}\t{hotkey_text}")

    def apply_hotkeys(self, hotkeys):
        hotkeys = self.normalize_hotkeys(hotkeys)
        entries = []
        for action, (menu_item, _) in self.get_hotkey_menu_items().items():
            parsed = self.parse_hotkey(hotkeys[action])
            if parsed is None:
                continue
            modifiers, keycode = parsed
            entries.append((modifiers, keycode, menu_item.GetId()))
        self.hotkeys = hotkeys
        self.acceltbl = wx.AcceleratorTable(entries)
        self.SetAcceleratorTable(self.acceltbl)
        self.update_hotkey_menu_labels()

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        # ★ 打开 "Parallel manual" 选择窗口时, 路径列表一律为空。
        #   以前这里会把 ImgManager.input_path(当前已打开的目录, 顺序/并行自动模式选中的那个)
        #   或者上一次手动选择的结果传过去, 于是选择框里会出现"这次并没有选"的路径。
        #   用户以为只挑了新目录, 关闭时旧目录却被一起提交,
        #   在图片/视频模式之间来回切换时尤其容易把路径带错。
        #   现在不预填: 列表里看到的就是这次真正要用的路径集合。
        if self.shared_config.video_mode:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value ,video_manager = self.video_manager,shared_config=self.shared_config)
        else:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    #b5
    def last_img(self, event):
        if self.shared_config.video_mode and self.shared_config.is_playing and not getattr(self, "_from_timer", False):
            self.shared_config.play_direction = -1
            self.last_direction = self.shared_config.play_direction
            return
        if (not self.shared_config.video_mode and
                self.shared_config.is_playing and
                not getattr(self, "_from_timer", False)):
            self.shared_config.play_direction = -1
            self.last_direction = -1
            return

        if self.shared_config.batch_idx <= 0:
            if getattr(self.shared_config, "is_playing", False):
                self.shared_config.is_playing = False
                try:
                    self.play_timer.Stop()
                except Exception:
                    pass
                try:
                    self.right_arrow_button1.SetLabel("▶")
                except Exception:
                    pass
                self.shared_config.play_direction = 1
                self.last_direction = 1
            return

        if self.shared_config.video_mode:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = -1
                self.last_direction = self.shared_config.play_direction
            if self.shared_config.batch_idx > 0:
                self.shared_config.batch_idx -= 1

            # CallAfter defers lightweight scheduling on the GUI thread.
            wx.CallAfter(self.video_manager.update_cache)

        if self.shared_config.video_mode:
            if self.ImgManager.img_count != 0:
                self.ImgManager.subtract()
            self.shared_config.batch_idx = max(0, self.shared_config.batch_idx)
        else:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = -1
                self.last_direction = -1
            if self.shared_config.batch_idx > 0:
                self.shared_config.batch_idx -= 1
            if self.ImgManager.img_count != 0:
                self.ImgManager.subtract()
            self.shared_config.batch_idx = max(0, self.ImgManager.action_count)

        if not getattr(self, "_from_timer", False):
            self.show_img_init()

        self.show_img()
        self.SetStatusText_(["Last", "-1", "-1", "-1"])

    def skip_to_n_img(self, event):
        if self.ImgManager.img_num == 0:
            return

        target = int(self.slider_img.GetValue())
        current_val = self.slider_value.GetValue()
        if current_val != str(target):
            self.slider_value.SetValue(str(target))

        if getattr(self.shared_config, "video_mode", False) and getattr(self.shared_config, "parallel_to_sequential", False):
            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None]
            total = sum(nums)
            count = max(1, int(getattr(self.shared_config, "count_per_action", 1) or 1))
            if total > 0:
                self.ImgManager.max_action_num = max(1, (total + count - 1) // count)
        elif getattr(self.shared_config, "video_mode", False):
            # 纯视频模式：重新计算 max_action_num
            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None and int(x) > 0]
            if nums:
                img_num = max(nums)
                count = max(1, int(getattr(self.shared_config, "count_per_action", 1) or 1))
                if img_num % count:
                    max_action_num = int(img_num / count) + 1
                else:
                    max_action_num = int(img_num / count)
                self.ImgManager.max_action_num = max(1, max_action_num)
        else:
            # 图片模式：重新计算 max_action_num
            count = max(1, self.ImgManager.count_per_action)
            img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
            if img_num > 0:
                max_batches = (img_num + count - 1) // count
            else:
                max_batches = 1
            self.ImgManager.max_action_num = max(1, max_batches)

        max_allowed = int((getattr(self.ImgManager, "max_action_num", 1) or 1) - 1)
        max_idx = max(0, max_allowed)
        clamped = min(target, max_idx)

        # Update state only; image refresh is controlled by refresh()
        self.shared_config.batch_idx = clamped
        self.ImgManager.action_count = clamped
        self.ImgManager.img_count = clamped * self.ImgManager.count_per_action

        # ★ 修改：视频模式下，先异步更新缓存，让UI能立即显示已有的缓存
        #   而不是阻塞等待新缓存生成
        if getattr(self.shared_config, "video_mode", False):
            wx.CallAfter(self.video_manager.update_cache)

        # 刷新显示，保留文本框的值
        self.show_img(preserve_text_value=True)

    def slider_value_change(self, event, value=None):
        if self.ImgManager.img_num == 0:
            return

        target_str = str(self.slider_value.GetValue()).strip()
        self.slider_value.SetValue(target_str)

        try:
            target = int(target_str)
        except Exception:
            return

        if getattr(self.shared_config, "video_mode", False) and getattr(self.shared_config, "parallel_to_sequential", False):
            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None]
            total = sum(nums)
            count = max(1, int(getattr(self.shared_config, "count_per_action", 1) or 1))
            if total > 0:
                self.ImgManager.max_action_num = max(1, (total + count - 1) // count)
        elif getattr(self.shared_config, "video_mode", False):
            # 纯视频模式：重新计算 max_action_num
            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None and int(x) > 0]
            if nums:
                img_num = max(nums)
                count = max(1, int(getattr(self.shared_config, "count_per_action", 1) or 1))
                if img_num % count:
                    max_action_num = int(img_num / count) + 1
                else:
                    max_action_num = int(img_num / count)
                self.ImgManager.max_action_num = max(1, max_action_num)
        else:
            # 图片模式：重新计算 max_action_num
            count = max(1, self.ImgManager.count_per_action)
            img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
            if img_num > 0:
                max_batches = (img_num + count - 1) // count
            else:
                max_batches = 1
            self.ImgManager.max_action_num = max(1, max_batches)

        max_allowed = int((getattr(self.ImgManager, "max_action_num", 1) or 1) - 1)
        max_idx = max(0, max_allowed)
        clamped = min(target, max_idx)
        self.shared_config.batch_idx = clamped
        self.ImgManager.action_count = clamped
        self.ImgManager.img_count = clamped * self.ImgManager.count_per_action

        # ★ 修改：视频模式下，先异步更新缓存，让UI能立即显示已有的缓存
        #   而不是阻塞等待新缓存生成
        if self.shared_config.video_mode:
            # 异步更新缓存（不阻塞UI）
            wx.CallAfter(self.video_manager.update_cache)

        # 刷新显示，保留文本框的值
        self.show_img(preserve_text_value=True)

    def save_img(self, event):
        type_ = self.choice_output.GetSelection()
        save_format = self.save_format.GetSelection()
        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 35:
                self.ImgManager.layout_params[35] = save_format
            if len(self.ImgManager.layout_params) > 33:
                self.ImgManager.layout_params[33] = self.out_path_str
        if self.auto_save_all.Value:
            last_count_img = self.ImgManager.action_count
            self.ImgManager.set_action_count(0)
            if self.out_path_str != "" and Path(self.out_path_str).is_dir():
                continue_ = True
            else:
                continue_ = False
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            if continue_:
                for i in range(self.ImgManager.max_action_num):
                    self.SetStatusText_(
                        ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img***", "-1"])
                    self.ImgManager.get_flist()
                    if self.show_custom_func.Value:
                        self.ImgManager.layout_params[32] = True  # customfunc
                        self.ImgManager.save_img(self.out_path_str, type_)
                        self.ImgManager.layout_params[32] = False  # customfunc
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

                    self.ImgManager.add()
                self.ImgManager.set_action_count(last_count_img)
                self.SetStatusText_(
                    ["-1", "-1", "***Finish***", "-1"])
        else:
            try:
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img...***", "-1"])
            except:
                pass
            self.ImgManager.layout_params[33] = self.out_path_str
            # ★ 修复：保存当前页的 flist，因为 save_img 内部会修改 flist
            orig_flist = getattr(self.ImgManager, 'flist', None)
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            # ★ 恢复原始 flist，使 save_stitch_img_and_customfunc_img 使用正确的文件名
            if orig_flist is not None:
                self.ImgManager.flist = orig_flist

            self.ImgManager.save_stitch_img_and_customfunc_img(
                self.out_path_str,
                self.show_custom_func.Value,
                self.show_bmp_in_panel.copy() if hasattr(self, "show_bmp_in_panel") and self.show_bmp_in_panel is not None else None
            )

            if flag == 0:
                self.SetStatusText_(
                    ["Save", str(self.ImgManager.action_count), "Save success!", "-1"])
            elif flag == 1:
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            elif flag == 2:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            elif flag == 3:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", the number of img in sub folders is different***", "-1"])
            elif flag == 4:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: No magnification box, the magnified image can not be saved***", "-1"])
            elif flag == 5:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Save", "-1", "-1", "-1"])

    def refresh(self, event):
        if getattr(self, "_parallel_switch_dirty", False):
            self._apply_parallel_switch()
            self._parallel_switch_dirty = False
        # ★ 先把设置区数值框的内容提交进来, 再往下走。
        #   以前 refresh() 直接读 shared_config, 而数值框只在"失去焦点"时才写回,
        #   所以用菜单/快捷键(Ctrl+R)刷新时, 刚改的 Cached Frames 会被静默丢弃。
        self._commit_video_settings()
        if (not getattr(self.shared_config, "video_mode", False)
            and self.out_path_str == ""
            and ((hasattr(self, "show_custom_func") and self.show_custom_func.GetValue())
                 or (hasattr(self, "show_all_func") and self.show_all_func.GetValue()))):
            self.out_path(None)
            if self.out_path_str == "":
                return
        self.show_img_init()
        if getattr(self.shared_config, "video_mode", False):
            self._last_refresh_batch = None
            vm = getattr(self, "video_manager", None)
            if vm is not None and hasattr(vm, "_last_batch"):
                vm._last_batch = None
        if self.shared_config.video_mode:
            new_thr = int(getattr(self.shared_config, 'thread', 1) or 1)
            last_thr = getattr(self, '_last_thread', None)
            if last_thr != new_thr:
                self._rebuild_threads(new_thr)
                self._last_thread = new_thr

            # ★ 修复：skip_frames 改变后，重新计算 video_num_list
            vm = getattr(self, 'video_manager', None)
            if vm is not None:
                self.shared_config.video_num_list = []
                self.shared_config.video_fps_list = []
                for vp in getattr(self.shared_config, "real_video_path", []):
                    try:
                        vm.calc_max_extractable_frames_single(vp)
                    except Exception:
                        self.shared_config.video_num_list.append(0)
                        self.shared_config.video_fps_list.append(0)
                # ★ 同步更新 ImgManager 内部状态，避免 set_count_per_action 等使用陈旧值
                self.ImgManager.video_num_list = list(self.shared_config.video_num_list)
                self.ImgManager.video_fps_list = list(self.shared_config.video_fps_list)
                self.ImgManager.img_num_list = list(self.shared_config.video_num_list)
                if self.shared_config.parallel_to_sequential:
                    self.ImgManager.img_num = sum(int(x) for x in self.shared_config.video_num_list if x)
                else:
                    self.ImgManager.img_num = max(int(x) for x in self.shared_config.video_num_list if int(x) > 0) if any(int(x) > 0 for x in self.shared_config.video_num_list) else 0

            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None and int(x) > 0]
            if not nums:
                self.ImgManager.max_action_num = 1
                self.shared_config.batch_idx = 0
                self.SetStatusText_(["-1", "-1", "***Error: no valid videos loaded, please reselect input***", "-1"])
                return

            if self.shared_config.parallel_to_sequential:
                img_num = sum(nums)
            else:
                img_num = max(nums)

            count = max(1, int(self.shared_config.count_per_action or 1))
            if img_num % count:
                max_action_num = int(img_num / count) + 1
            else:
                max_action_num = int(img_num / count)

            self.ImgManager.max_action_num = max(1, max_action_num)

            if self.shared_config.batch_idx >= self.ImgManager.max_action_num:
                self.shared_config.batch_idx = self.ImgManager.max_action_num - 1

        if self.shared_config.video_mode:
            current_batch = self.shared_config.batch_idx
            current_count_per_action = self.shared_config.count_per_action

            last_batch = getattr(self, '_last_refresh_batch', None)
            last_count_per_action = getattr(self, '_last_refresh_count_per_action', None)
            if (last_batch != current_batch or
                last_count_per_action != current_count_per_action or
                last_batch is None):
                self.video_manager.update_cache()
                self._last_refresh_batch = current_batch
                self._last_refresh_count_per_action = current_count_per_action
            else:
                pass

            if self.ImgManager.action_count >= self.ImgManager.max_action_num:
                self.ImgManager.action_count = self.ImgManager.max_action_num-1
                self.shared_config.batch_idx = self.ImgManager.action_count

            # 视频模式：读取文本框值并跳转到对应位置
            try:
                target = int(self.slider_value.GetValue().strip())
            except (ValueError, AttributeError):
                target = self.shared_config.batch_idx

            # 限制目标在有效范围内
            max_allowed = max(0, self.ImgManager.max_action_num - 1)
            clamped = min(max(0, target), max_allowed)

            # 更新状态
            self.shared_config.batch_idx = clamped
            self.ImgManager.action_count = clamped

        if self.ImgManager.img_num != 0:
            # 图片模式：读取文本框值并跳转到对应位置
            if not getattr(self.shared_config, "video_mode", False):
                try:
                    target = int(self.slider_value.GetValue().strip())
                except (ValueError, AttributeError):
                    target = self.ImgManager.action_count

                # 重新计算 max_action_num（以防图片数量变化）
                count = max(1, self.ImgManager.count_per_action)
                img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
                if img_num > 0:
                    max_batches = (img_num + count - 1) // count
                else:
                    max_batches = 1
                self.ImgManager.max_action_num = max(1, max_batches)

                # 限制目标在有效范围内
                max_allowed = max(0, self.ImgManager.max_action_num - 1)
                clamped = min(max(0, target), max_allowed)

                # 更新状态
                self.shared_config.batch_idx = clamped
                self.ImgManager.action_count = clamped
                self.ImgManager.img_count = clamped * self.ImgManager.count_per_action

            self.show_img(preserve_text_value=True)
        else:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
        # ★ 刷新完把设置区输入框的光标收掉, 否则框里一直闪着 "|",
        #   看上去就像刚才那次修改没提交成功。
        if getattr(self.shared_config, "video_mode", False):
            self._blur_settings_field()
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def _invalidate_render_cache(self):
        """Clear current cache to force restitching (shared by video/image modes)."""
        self.shared_config.image_cache_img = []
        self.shared_config.image_cache_paths = []
        if hasattr(self, 'image_pipeline'):
            self.image_pipeline.invalidate()
        self._image_reference_resolution_origin = None
        cache = getattr(self.shared_config, "cache_img", None)
        if isinstance(cache, list):
            for i in range(len(cache)):
                cache[i] = None
        self._last_refresh_batch = None
        vm = getattr(self, "video_manager", None)
        if vm is not None:
            vm._invalidate_stitch_cache()
        if vm is not None and hasattr(vm, "_last_batch"):
            vm._last_batch = None

    def _clear_video_mode_cache(self):
        """Clear every piece of local state owned by video mode.

        Called when leaving video mode for image mode so that stale video
        stitches (in-memory PNG paths and on-disk Video_frames/stitch_cache
        files) cannot leak into the image-mode render path or get re-displayed
        if the user toggles video mode back on without a fresh selection.
        """
        vm = getattr(self, "video_manager", None)

        if vm is not None:
            vm._invalidate_stitch_cache()
            vm._decoder_bank.configure(0)
            vm._maintenance_executor.submit(vm._decoder_bank.trim)

        # 1. Clear in-memory stitch cache (list of PNG paths from video mode)
        self.shared_config.cache_img = []

        # 2. Reset video_manager prefetch & metadata state to avoid leaking
        #    pending futures or stale _last_batch markers into the next run.
        if vm is not None:
            if hasattr(vm, "_last_batch"):
                vm._last_batch = None
            if hasattr(vm, "_meta_cache") and isinstance(vm._meta_cache, dict):
                vm._meta_cache.clear()
            try:
                pending_lock = getattr(vm, "_cache_guard", None)
                if pending_lock is not None:
                    with pending_lock:
                        for fut in list(getattr(vm, "_pending_extract", {}).values()):
                            try:
                                fut.cancel()
                            except Exception:
                                pass
                        if hasattr(vm, "_pending_extract"):
                            vm._pending_extract.clear()
                        if hasattr(vm, "_pending_stitch_async"):
                            vm._pending_stitch_async = 0
            except Exception:
                pass
            if hasattr(vm, "perf_monitor"):
                try:
                    vm.perf_monitor.reset_render_clock()
                except Exception:
                    pass

        # 3. Drop video mode path/metadata bookkeeping so a later accidental
        #    re-entry into video mode can't accidentally reuse stale data.
        self.shared_config.real_video_path = []
        self.shared_config.video_path = []
        self.shared_config.video_num_list = []
        self.shared_config.video_fps_list = []
        self.shared_config.batch_idx = 0
        self.shared_config.video_last_message = ""
        self.shared_config.interval_recommend = None
        self.shared_config.current_video_index = 0
        self.last_direction = 0

        # 4. Reset layout-rebuild token so layout-driven cache invalidation
        #    still fires on the first image-mode refresh after the switch.
        self._last_refresh_batch = None
        self._last_thread = None
        # Also clear the deferred "parallel switch" marker – it is only meant
        # to apply while still inside video mode and would otherwise linger
        # in the image-mode path on the next refresh().
        self._parallel_switch_dirty = False

        # The existing generation-aware maintenance worker removes obsolete
        # video PNGs/JPEG directories. It preserves the shared stitch directory
        # and never makes a mode-switch GUI handler scan or delete files.
        if vm is not None:
            vm._schedule_video_cleanup()

        if getattr(self.shared_config, "debug_video", False):
            print("[VideoMode] cleared local cache on video->image transition")

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=0)
            if not selected:
                return False
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Choose input dir", "",
                               wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return False
                self.ImgManager.init(dlg.GetPath(), type=2)
            finally:
                dlg.Destroy()
        if self.shared_config.video_mode:
            if self.shared_config.video_path == []:
                return
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        if self.shared_config.video_mode:
            # ★ show_img_init() 会因布局参数变化清空视频缓存，
            #   必须在它之后重新抽帧+拼接, 否则首帧缺失只会显示 "Waiting for batch 0"。
            self.video_manager.update_cache()
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])
        return True

    def onefilelist(self, event=None):
        self.SetStatusText_(["Choose the File List", "", "", "-1"])
        # Initialize the image stitch pool
        self._init_image_stitch_executor()

        wildcard = "List file (*.txt; *.csv)|*.txt; *.csv|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), type=3)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(3)
        self.SetStatusText_(["Choose the File List", "-1", "-1", "-1"])

    def input_flist_parallel_manual(self, event):
        # Initialize the image stitch pool
        self._init_image_stitch_executor()

        wildcard = "List file (*.txt;)|*.txt;|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            with open(dlg.GetPath(), "r") as f:
                input_path = f.read().split('\n')
            self.ImgManager.init(
                input_path[0:-1], type=1, parallel_to_sequential=self.parallel_to_sequential.Value)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(2)

    def save_flist_parallel_manual(self, event):
        if self.out_path_str == "":
            self.SetStatusText_(
                ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
        else:
            try:
                np.savetxt(Path(self.out_path_str)/"input_flist_parallel_manual.txt",
                           self.ImgManager.input_path, fmt='%s')
            except:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select parallel manual***", "-1"])
            else:
                self.SetStatusText_(
                    ["-1", "-1", "Save" + str(Path(self.out_path_str)/"input_flist_parallel_manual.txt")+" success!", "-1"])

    def out_path(self, event):
        dlg = wx.DirDialog(None, "Choose output dir", "",
                        wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.out_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.out_path_str, 3)

        dlg.Destroy()

    def colour_change(self, event):
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def background_alpha(self, event):
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_alpha = self.background_slider.GetValue()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def foreground_alpha(self, event):
        self.ImgManager.img_alpha = self.foreground_slider.GetValue()

    def delete_box(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                self.xy_magnifier.pop(self.box_id)
                self._invalidate_render_cache()
                self.refresh(event)
                self.SetStatusText_(
                    ["delete "+str(self.box_id)+"-th box",  "-1", "-1", "-1"])
        else:
            self.xy_magnifier = []
            self._invalidate_render_cache()
            self.refresh(event)
            self.SetStatusText_(["delete all box",  "-1", "-1", "-1"])
        if len(self.xy_magnifier)==0:
            self.box_position.SetSelection(0)

    def up_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y-speed
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[1] > 0:
                self.position[1] -= speed
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Up",  "-1", "-1", "-1"])

    def down_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y+speed
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if (self.position[1]-1)*self.Uint[1] < size[1]:
                self.position[1] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[1])
        self.SetStatusText_(["Down",  "-1", "-1", "-1"])

    def right_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+speed
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if (self.position[0]-1)*self.Uint[0] < size[0]:
                self.position[0] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[0])
        self.SetStatusText_(["Right",  "-1", "-1", "-1"])

    def left_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x-speed
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[0] > 0:
                self.position[0] -= speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.m_statusBar1.SetStatusText(texts[i], i)

    def update_status_bar_for_current_page(self, clicked_img_id=None):
        try:
            if getattr(self.shared_config, "video_mode", False):
                page_num = int(getattr(self.shared_config, "batch_idx", 0))
                total_pages = max(0, int(getattr(self.ImgManager, "max_action_num", 1)) - 1)
                self.m_statusBar1.SetStatusText(f"{page_num}-th/{total_pages} frame batch", 1)
                return

            page_num = self.ImgManager.action_count if hasattr(self.ImgManager, 'action_count') else 0
            if self.ImgManager.type == 2:
                total_imgs = self.ImgManager.img_num
                img_index = self.ImgManager.action_count * self.ImgManager.count_per_action
                if clicked_img_id is not None:
                    img_index = img_index + clicked_img_id
                status_text = f"{img_index}-th/{total_imgs} img 0-th/1 dir"

            elif self.ImgManager.type in [0, 1]:
                total_dirs = self.ImgManager.get_dir_num() if hasattr(self.ImgManager, 'get_dir_num') else 0
                target_img_id = clicked_img_id if clicked_img_id is not None else 0
                current_paths = getattr(self, "current_page_img_paths", [])
                img_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
                if self.parallel_sequential.Value:
                    if current_paths and target_img_id < len(current_paths):
                        current_file_path = current_paths[target_img_id]
                        current_dir = os.path.dirname(current_file_path)
                        try:
                            files_in_folder = sorted([
                                os.path.join(current_dir, f)
                                for f in os.listdir(current_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            img_count_in_folder = len(files_in_folder)
                            pos_in_folder = files_in_folder.index(current_file_path) if current_file_path in files_in_folder else 0
                            all_dirs = sorted(set(os.path.dirname(p) for p in getattr(self.ImgManager, "flist", [])))
                            dir_index = all_dirs.index(current_dir) if current_dir in all_dirs else page_num
                        except Exception:
                            pos_in_folder = 0
                            dir_index = page_num
                            img_count_in_folder = self.ImgManager.layout_params[1][0] * self.ImgManager.layout_params[1][1]
                    else:
                        pos_in_folder = 0
                        dir_index = page_num
                        img_count_in_folder = self.ImgManager.layout_params[1][0] * self.ImgManager.layout_params[1][1]
                    status_text = f"{pos_in_folder}-th/{img_count_in_folder} img {dir_index}-th/{total_dirs} dir"

                elif self.parallel_to_sequential.Value:
                    if current_paths and target_img_id < len(current_paths):
                        current_file_path = current_paths[target_img_id]
                        current_dir = os.path.dirname(current_file_path)
                        old_action_count = self.ImgManager.action_count
                        old_flist = getattr(self.ImgManager, "flist", None)
                        all_dirs_set = set()
                        for i in range(self.ImgManager.max_action_num):
                            try:
                                self.ImgManager.set_action_count(i)
                                self.ImgManager.get_flist()
                                all_dirs_set.update(os.path.dirname(p) for p in self.ImgManager.flist)
                            except Exception:
                                pass
                        self.ImgManager.set_action_count(old_action_count)
                        if old_flist is not None:
                            self.ImgManager.flist = old_flist
                        all_dirs = sorted(all_dirs_set)
                        total_dirs = len(all_dirs)
                        dir_index = all_dirs.index(current_dir) if current_dir in all_dirs else 0
                        try:
                            files_in_folder = sorted([
                                os.path.join(current_dir, f)
                                for f in os.listdir(current_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            img_count_in_folder = len(files_in_folder)
                            pos_in_folder = files_in_folder.index(current_file_path) if current_file_path in files_in_folder else 0
                        except Exception:
                            pos_in_folder = 0
                            img_count_in_folder = 0
                        status_text = f"{pos_in_folder}-th/{img_count_in_folder} img {dir_index}-th/{total_dirs} dir"
                    else:
                        try:
                            self.ImgManager.get_flist()
                            first_file_path = self.ImgManager.flist[0]
                            first_dir = os.path.dirname(first_file_path)
                            files_in_folder = sorted([
                                os.path.join(first_dir, f)
                                for f in os.listdir(first_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            pos_in_folder = files_in_folder.index(first_file_path) if first_file_path in files_in_folder else 0
                            img_count_in_folder = len(files_in_folder)
                        except Exception:
                            pos_in_folder = 0
                            img_count_in_folder = 0
                        status_text = f"{pos_in_folder}-th/{img_count_in_folder} img {page_num}-th/{total_dirs} dir"

                else:
                    if clicked_img_id is not None and hasattr(self.ImgManager, 'flist') and clicked_img_id < len(self.ImgManager.flist):
                        clicked_img_path = self.ImgManager.flist[clicked_img_id]
                        clicked_dir = os.path.dirname(clicked_img_path)
                        all_dirs = sorted(set(os.path.dirname(p) for p in self.ImgManager.flist))
                        dir_index = all_dirs.index(clicked_dir) if clicked_dir in all_dirs else page_num
                        try:
                            folder_images = sorted([
                                os.path.join(clicked_dir, f)
                                for f in os.listdir(clicked_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            img_count_in_folder = len(folder_images)
                            pos_in_folder = folder_images.index(clicked_img_path) if clicked_img_path in folder_images else 0
                        except Exception:
                            img_count_in_folder = 1
                            pos_in_folder = 0
                        status_text = f"{pos_in_folder}-th/{img_count_in_folder} img {dir_index}-th/{total_dirs} dir"
                    else:
                        total_pages = getattr(self.ImgManager, "max_action_num", 0)
                        status_text = f"{page_num}-th/{total_pages} img 0-th/{total_dirs} dir"

            elif self.ImgManager.type == 3:
                target_img_id = clicked_img_id if clicked_img_id is not None else 0
                img_index = self.ImgManager.action_count * self.ImgManager.count_per_action + target_img_id
                total_imgs = len(self.ImgManager.path_list) if hasattr(self.ImgManager, 'path_list') else 0
                status_text = f"{img_index}-th/{total_imgs} img 0-th/0 dir"
            else:
                status_text = "0-th/0 img 0-th/0 dir"

            self.m_statusBar1.SetStatusText(status_text, 1)
        except Exception:
            self.m_statusBar1.SetStatusText("0-th/0 img 0-th/0 dir", 1)

    def img_left_click(self, event):

        if self.magnifier.Value:
            x_0, y_0 = event.GetPosition()
            self.x_0 = x_0
            self.y_0 = y_0
            self.x = x_0
            self.y = y_0

        if self.select_img_box.Value:
            # select box
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([x, y])
            xy_grid = self.ImgManager.xy_grid[id]
            x = x-xy_grid[0]
            y = y-xy_grid[1]
            x_y_array = []
            for i in range(len(self.ImgManager.crop_points)):
                x_y_array.append(self.get_center_box(
                    self.ImgManager.crop_points[i][0:4]))
            x_y_array = np.array(x_y_array)
            dist = (x_y_array[:, 0]-x)**2+(x_y_array[:, 1]-y)**2
            self.box_id = np.array(dist).argmin()
            str_ = str(self.box_id)
            self.SetStatusText_(["Select "+str_+"-th box",  "-1", "-1", "-1"])

            self.start_flag = 0
        else:
            # magnifier
            if self.magnifier.Value:
                self.start_flag = 1
            else:
                self.start_flag = 0

            if self.magnifier.Value:
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])

        # rotation
        if self.rotation.Value:
            x, y = event.GetPosition()
            self.ImgManager.rotate(
                self.get_img_id_from_point([x, y], img=True))
            self.refresh(event)

            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])

        # flip
        if self.flip.Value:
            x, y = event.GetPosition()
            self.ImgManager.flip(self.get_img_id_from_point(
                [x, y], img=True), FLIP_TOP_BOTTOM=False)
            # self.ImgManager.flip(self.get_img_id_from_point(
            #     [x, y], img=True), FLIP_TOP_BOTTOM=self.checkBox_orientation.Value)
            self.refresh(event)

            self.SetStatusText_(["Flip", "-1", "-1", "-1"])

        # focus img
        if self.indextablegui or self.aboutgui:
            pass
        else:
            self.img_panel.Children[0].SetFocus()

        # show dir_id
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        self.selected_img_id = id
        self.update_status_bar_for_current_page(id)

    def img_left_dclick(self, event):
        if self.select_img_box.Value:
            pass
        else:
            self.start_flag = 0
            self.xy_magnifier = []
            self.color_list = []
            self.box_position.SetSelection(0)
            self._invalidate_render_cache()

    def img_left_move(self, event):
        # https://stackoverflow.com/questions/57342753/how-to-select-a-rectangle-of-the-screen-to-capture-by-dragging-mouse-on-transpar
        if self.magnifier.Value != False and self.start_flag == 1:
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            xy_limit = np.array(xy_grid) + \
                np.array(self.ImgManager.img_resolution_show)

            if self.x_0 < xy_limit[0] and self.y_0 < xy_limit[1]:

                if x < xy_limit[0] and y < xy_limit[1]:
                    self.x = x
                    self.y = y
                elif x > xy_limit[0] and y > xy_limit[1]:
                    self.x = xy_limit[0]
                    self.y = xy_limit[1]
                elif x > xy_limit[0]:
                    self.x = xy_limit[0]
                    self.y = y
                elif y > xy_limit[1]:
                    self.x = x
                    self.y = xy_limit[1]

        # show mouse position
        if not hasattr(self, "show_bmp_in_panel") or self.show_bmp_in_panel is None:
            return
        if not hasattr(self.ImgManager, "xy_grid") or len(getattr(self.ImgManager, "xy_grid", [])) == 0:
            return
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        try:
            w, h = self.show_bmp_in_panel.size
            px = max(0, min(int(x), max(0, w - 1)))
            py = max(0, min(int(y), max(0, h - 1)))
            RGBA = self.show_bmp_in_panel.getpixel((px, py))
        except Exception:
            RGBA = (-1, -1, -1, -1)
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        self.m_statusBar1.SetStatusText(str(x)+","+str(y)+"/"+str(RGBA), 0)

    def img_left_release(self, event):
        if self.magnifier.Value != False:
            self.start_flag = 0

            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            x = self.x-xy_grid[0]
            y = self.y-xy_grid[1]
            x_0 = self.x_0 - xy_grid[0]
            y_0 = self.y_0 - xy_grid[1]

            width = np.abs(x-x_0)
            height = np.abs(y-y_0)
            if width > 5 and height > 5:
                self.xy_magnifier = []
                self.color_list.append(self.colourPicker_draw.GetColour())

                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.ImgManager.ImgF.sort_box_point(
                    [x_0, y_0, x, y], show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                self.xy_magnifier.append(
                    points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                self._invalidate_render_cache()
                self.refresh(event)

    def img_right_click(self, event):
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:
            xy_grid_array = np.array(self.ImgManager.xy_grid)
            xy_cur = np.array([[x, y]])
            xy_cur = np.repeat(xy_cur, xy_grid_array.shape[0], axis=0)
            res_ = xy_cur - xy_grid_array
            id_list = []
            for i in range(xy_grid_array.shape[0]):
                if res_[i][0] >= 0 and res_[i][1] >= 0:
                    id_list.append(i)
                else:
                    id_list.append(0)
            actual_grid_id = max(id_list)
            xy_grid = self.ImgManager.xy_grid[actual_grid_id]
        else:
            xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        menu_triggered = getattr(event, 'menu_triggered', False)

        if not menu_triggered:
            self.on_right_click(event)
            return

        if self.select_img_box.Value:
            # move box
            if self.box_id != -1:
                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.move_box_point(x, y, show_scale)
                self.xy_magnifier[self.box_id] = points+show_scale+[
                    self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]]
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            # new box
            if self.magnifier.Value:
                self.color_list.append(self.colourPicker_draw.GetColour())
                try:
                    show_scale = self.show_scale.GetLineText(0).split(',')
                    show_scale = [float(x) for x in show_scale]
                    points = self.move_box_point(x, y, show_scale)
                    self.xy_magnifier.append(
                        points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                except:
                    self.SetStatusText_(
                        ["-1",  "Drawing a box need click left mouse button!", "-1", "-1"])

                self._invalidate_render_cache()
                self.refresh(event)
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        self.on_right_click(event)

    def on_right_click(self, event):
        # Right-click Menu​
        menu = wx.Menu()
        refresh_id = wx.Window.NewControlId()
        menu.Append(refresh_id, "🔄 refresh")
        menu.Bind(wx.EVT_MENU, self.refresh, id=refresh_id)

        prev_id = wx.Window.NewControlId()
        menu.Append(prev_id, "⬅️ Previous Page")
        menu.Bind(wx.EVT_MENU, self.last_img, id=prev_id)

        next_id = wx.Window.NewControlId()
        menu.Append(next_id, "➡️ Next Page")
        menu.Bind(wx.EVT_MENU, self.next_img, id=next_id)

        save_single_id = wx.Window.NewControlId()
        menu.Append(save_single_id, "💾 Save")
        def save_current_page(evt):
            # Default Save
            self.save_img(evt)
        menu.Bind(wx.EVT_MENU, save_current_page, id=save_single_id)

        if (self.ImgManager.type == 0 or self.ImgManager.type == 1) and (self.parallel_sequential.Value):
            save_column_id = wx.Window.NewControlId()
            menu.Append(save_column_id, "📄 save(only select current location)")
            def save_selected_column(evt):
                # save current location images in all folders
                if not self.out_path_str:
                    self.out_path(evt)
                    if not self.out_path_str:
                        return
                x, y = event.GetPosition()
                clicked_grid_id = self.get_img_id_from_point([x, y])
                # Retrieve ID information
                if hasattr(self, 'current_page_img_paths') and clicked_grid_id < len(self.current_page_img_paths):
                    target_path = self.current_page_img_paths[clicked_grid_id]
                else:
                    actual_img_index = self.ImgManager.xy_grids_id_list[clicked_grid_id] \
                        if hasattr(self.ImgManager, 'xy_grids_id_list') and clicked_grid_id < len(self.ImgManager.xy_grids_id_list) \
                        else clicked_grid_id

                    if not hasattr(self.ImgManager, 'flist') or actual_img_index >= len(self.ImgManager.flist):
                        self.SetStatusText_(["Cannot get clicked image", "-1", "-1", "-1"])
                        return
                    target_path = self.ImgManager.flist[actual_img_index]
                if not target_path or not os.path.exists(target_path):
                    self.SetStatusText_(["Invalid image path", "-1", "-1", "-1"])
                    return
                target_name = os.path.basename(target_path)
                type_ = self.choice_output.GetSelection()
                if self.show_custom_func.Value:
                    self.ImgManager.layout_params[32] = True
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.layout_params[32] = False
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

                # Call the default save function
                select_folder = os.path.join(self.out_path_str, "select_images")
                # override it with the new folder selection logic
                if os.path.exists(select_folder):
                    shutil.rmtree(select_folder)
                os.makedirs(select_folder, exist_ok=True)
                all_dirs = sorted(set(os.path.dirname(p) for p in self.ImgManager.flist))
                success_count = 0
                for folder_path in all_dirs:
                    if not os.path.exists(folder_path):
                        continue
                    try:
                        target_file = os.path.join(folder_path, target_name)
                        if os.path.exists(target_file) and os.path.isfile(target_file):
                            folder_name = os.path.basename(folder_path)
                            sub_dir = os.path.join(select_folder, folder_name)
                            os.makedirs(sub_dir, exist_ok=True)
                            shutil.copy2(target_file, os.path.join(sub_dir, target_name))
                            success_count += 1
                    except:
                        pass
                status_msg = f"Save completed! select_images updated with {success_count} images (clicked: {target_name})" \
                    if success_count > 0 \
                    else f"Save completed, but no matching images found for {target_name}"
                self.SetStatusText_([status_msg, "-1", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, save_selected_column, id=save_column_id)

        if self.magnifier.Value:
            new_box_id = wx.Window.NewControlId()
            menu.Append(new_box_id, "🔍 Create zoom box here")

            def create_magnifier_box(evt):
                event.menu_triggered = True
                x, y = event.GetPosition()
                id = self.get_img_id_from_point([x, y])
                xy_grid = self.ImgManager.xy_grid[id]
                x = x-xy_grid[0]
                y = y-xy_grid[1]

                if self.magnifier.Value:
                    self.color_list.append(self.colourPicker_draw.GetColour())
                    try:
                        show_scale = self.show_scale.GetLineText(0).split(',')
                        show_scale = [float(x) for x in show_scale]
                        if len(self.xy_magnifier) == 0:
                            default_size = 50
                            points = self.ImgManager.ImgF.sort_box_point(
                                [x-default_size//2, y-default_size//2, x+default_size//2, y+default_size//2],
                                show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        else:
                            points = self.move_box_point(x, y, show_scale)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        self._invalidate_render_cache()
                        self.refresh(evt)
                        self.SetStatusText_(["Create a zoom box", "-1", "-1", "-1"])
                    except Exception as e:
                        self.SetStatusText_(["-1", f"Failed to create zoom box: {str(e)}", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, create_magnifier_box, id=new_box_id)

        if len(self.xy_magnifier) > 0:
            clear_all_id = wx.Window.NewControlId()
            menu.Append(clear_all_id, "🗑️ Clear all zoom boxes")
            menu.Bind(wx.EVT_MENU, self.img_left_dclick, id=clear_all_id)

        if self.select_img_box.Value:
            box_menu = wx.Menu()

            if self.box_id != -1:
                move_box_id = wx.Window.NewControlId()
                box_menu.Append(move_box_id, f"Move box {self.box_id} to this position")

                def move_box_to_position(evt):
                    event.menu_triggered = True
                    self.img_right_click(event)
                    self._invalidate_render_cache()
                    self.refresh(evt)
                    self.SetStatusText_([f"Move box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, move_box_to_position, id=move_box_id)
                delete_box_id = wx.Window.NewControlId()
                box_menu.Append(delete_box_id, f"Delete box {self.box_id}")
                def delete_specific_box(evt):
                    if self.select_img_box.Value and self.box_id != -1:
                        self.xy_magnifier.pop(self.box_id)
                        if len(self.xy_magnifier) == 0:
                            self.box_position.SetSelection(0)
                        self._invalidate_render_cache()
                        self.refresh(evt)
                        self.SetStatusText_([f"Delete box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, delete_specific_box, id=delete_box_id)
            menu.AppendSubMenu(box_menu, f"Selection box" + (f" ({self.box_id})" if self.box_id != -1 else ""))

        if hasattr(self, 'title_rename_text'):
            new_title = self.title_rename_text.GetValue().strip()
            if new_title:
                inject_title_id = wx.Window.NewControlId()
                display_title = new_title[:20] + "..." if len(new_title) > 20 else new_title
                menu.Append(inject_title_id, f"📝 Inject title: {display_title}")
                def inject_title_directly(evt):
                    x, y = event.GetPosition()
                    id = self.get_img_id_from_point([x, y])
                    success = self.handle_title_injection(id)
                    if success:
                        self.SetStatusText_(["Title injected successfully", "-1", "-1", "-1"])
                    else:
                        self.SetStatusText_(["Failed to inject title", "-1", "-1", "-1"])
                menu.Bind(wx.EVT_MENU, inject_title_directly, id=inject_title_id)
                menu.AppendSeparator()
        try:
            mouse_screen_pos = wx.GetMousePosition()
            client_pos = self.ScreenToClient(mouse_screen_pos)
        except:
            client_pos = wx.Point(100, 100)

        self.PopupMenu(menu, client_pos)
        menu.Destroy()

    #--exif--
    def on_title_exif_changed(self, event):
        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 17:
                self.ImgManager.layout_params[17][11] = self.title_exif.Value
                self.ImgManager.load_exif_display_config(force_reload=True)

    def inject_new_title(self, new_title, img_id=None):
        try:
            if img_id is not None:
                current_index = img_id
            else:
                current_index = getattr(self, 'selected_img_id', self.ImgManager.action_count)
            if hasattr(self.ImgManager, 'xy_grids_id_list') and current_index < len(self.ImgManager.xy_grids_id_list):
                actual_img_index = self.ImgManager.xy_grids_id_list[current_index]
            else:
                actual_img_index = current_index
            if actual_img_index < len(self.ImgManager.flist):
                img_path = self.ImgManager.flist[actual_img_index]
                success = self.ImgManager.update_image_exif_37510(img_path, new_title)
                if success:
                    self._invalidate_render_cache()
                    self.refresh(None)
                    self.SetStatusText("✅ Title updated successfully!")

                    if hasattr(self, 'title_rename_text'):
                        self.title_rename_text.SetValue("")
                    self.SetStatusText_([f"The title has been injected into {current_index+1} images: {new_title}", "-1", "-1", "-1"])
                    return True
                else:
                    raise Exception("Failed to write EXIF")
            else:
                raise Exception(f"Picture index {actual_img_index} out of range")

        except Exception as exc:
            self.SetStatusText_([f"Inject title failed: {exc}", "-1", "-1", "-1"])
            return False

    def handle_title_injection(self, img_id = None):
        if not hasattr(self, 'title_rename_text'):
            return False
        new_title = self.title_rename_text.GetValue().strip()
        if not new_title:
            return False
        return bool(self.inject_new_title(new_title, img_id))

    def move_box_point(self, x, y, show_scale):
        x_0, y_0, x_1, y_1 = self.xy_magnifier[0][0:4]
        show_scale_old = self.xy_magnifier[0][4:6]
        scale = [show_scale[0]/show_scale_old[0],
                 show_scale[1]/show_scale_old[1]]
        x_0 = int(x_0*scale[0])
        x_1 = int(x_1*scale[0])
        y_0 = int(y_0*scale[1])
        y_1 = int(y_1*scale[1])
        x_center_old, y_center_old = self.get_center_box(
            [x_0, y_0, x_1, y_1])
        delta_x = x-x_center_old
        delta_y = y-y_center_old
        return self.ImgManager.ImgF.sort_box_point([x_0+delta_x, y_0+delta_y, x_1+delta_x, y_1+delta_y], self.ImgManager.img_resolution_origin, show_scale)

    def get_center_box(self, box, more=False):
        x_0, y_0, x_1, y_1 = box
        width = abs(x_0-x_1)
        height = abs(y_0-y_1)
        x_center_old = x_0+int((width)/2)
        y_center_old = y_0+int((height)/2)
        if more:
            return [x_center_old, y_center_old, width, height]
        else:
            return [x_center_old, y_center_old]

    def img_wheel(self, event):
        # https://wxpython.org/Phoenix/docs/html/wx.MouseEvent.html

        # zoom
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value and self.key_status["ctrl"] == 1:
            if event.GetWheelDelta() >= 120:
                speed = self.get_speed(name="scale")
                self.adjust_show_scale_proportion()  # adjust show_scale_proportion
                # set show_scale
                if event.GetWheelRotation() > 0:
                    self.show_scale_proportion = self.show_scale_proportion+speed
                else:
                    self.show_scale_proportion = self.show_scale_proportion-speed
                if self.show_scale_proportion > 0:
                    show_scale = [1*(1+self.show_scale_proportion),
                                  1*(1+self.show_scale_proportion)]
                elif self.show_scale_proportion < 0:
                    show_scale = [1/(1-self.show_scale_proportion),
                                  1/(1-self.show_scale_proportion)]
                else:
                    show_scale = [1, 1]
                self.show_scale.Value = str(
                    round(show_scale[0], 2))+","+str(round(show_scale[1], 2))

                self.refresh(event)
            else:
                pass
        else:
            pass

        # move
        if self.shift_pressed:
            if event.GetWheelRotation()>0:
                self.left_img(event)
            else:
                self.right_img(event)
        if self.key_status["ctrl"] == 0 and event.GetWheelDelta() >= 120:
            if event.WheelAxis == 0 and self.shift_pressed == 0:
                if event.GetWheelRotation() > 0:
                    self.up_img(event)
                else:
                    self.down_img(event)
            else:
                if event.GetWheelRotation() > 0:
                    self.left_img(event)
                else:
                    self.right_img(event)

    def adjust_show_scale_proportion(self):
        # check "cur_scale", and adjust "self.show_scale_proportion"
        cur_scale = self.show_scale.GetLineText(0).split(',')
        cur_scale = [float(x) for x in cur_scale]
        if self.show_scale_proportion > 0:
            if cur_scale[0] == round(1*(1+self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        elif self.show_scale_proportion < 0:
            if cur_scale[0] == round(1/(1-self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        else:
            self.show_scale_proportion = 0

    def key_down_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 0:
                self.key_status["ctrl"] = 1
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = True
            # Check whether Shift and 'S' are pressed together
        elif event.GetKeyCode() == ord('S'):
            if self.shift_pressed == True:
                # React when Shift + S is pressed
                if self.key_status["shift_s"] == 0:
                    self.key_status["shift_s"] = 1
                elif self.key_status["shift_s"] == 1:
                    self.key_status["shift_s"] = 0
        event.Skip()

    def key_up_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 1:
                self.key_status["ctrl"] = 0
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = False
        event.Skip()

    def get_speed(self, name="pixel"):
        if name == "pixel":
            if self.key_status["shift_s"] == 1:
                speed = 5
            else:
                speed = 1
        elif name == "scale":
            if self.key_status["shift_s"] == 1:
                speed = 0.5
            else:
                speed = 0.1
        else:
            speed = None
        return speed

    def magnifier_fc(self, event):
        self.start_flag = 0
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def rotation_fc(self, event):
        i_cur = 1
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_POINT_RIGHT))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def flip_fc(self, event):
        i_cur = 2
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            flip_cursor_path = Path(get_resource_path(str(Path("images"))))
            flip_cursor_path = str(flip_cursor_path/"flip_cursor.png")
            self.SetCursor(
                wx.Cursor((wx.Image(flip_cursor_path, wx.BITMAP_TYPE_PNG))))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Flip", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def _list_file_signature(self):
        """图片列表文件(type 3)的内容指纹: 路径 + 字节数 + 修改时间。

        列表文件是用户在外部用编辑器改的, 同一个路径对应的内容随时可能变,
        所以"要不要作废缓存"不能只看路径, 必须带上内容指纹。
        """
        img_mgr = getattr(self, "ImgManager", None)
        if img_mgr is None or getattr(img_mgr, "type", None) != 3:
            return None
        try:
            list_path = Path(str(getattr(img_mgr, "input_path", "")))
            if not list_path.is_file():
                return None
            stat = list_path.stat()
            return (str(list_path), int(stat.st_size), int(stat.st_mtime_ns))
        except Exception:
            return None

    def _reload_list_file_if_changed(self):
        """列表文件在外部被改过 -> 重新读取一遍, 并返回当前指纹。

        场景: 用 "Image File List" 打开 1.txt, 之后在外部改了 1.txt 里的图片路径,
        再重新选择同一个 1.txt (或者直接按刷新) —— 页面必须显示新路径的图片。

        以前 ImgManager 只在第一次 init 时读一次列表, 之后即使重新选择同一个文件
        也不会重读; 再叠加上拼接结果被缓存住, 于是页面看上去"完全没变化"。
        这里用文件指纹(大小+修改时间)判断内容是否变化, 变了就重读。
        """
        signature = self._list_file_signature()
        if signature is None:
            return None
        last = getattr(self, "_list_file_last_signature", None)
        self._list_file_last_signature = signature
        if last is None or last == signature:
            # 第一次拿到指纹(刚 init 完) 或者 文件内容没变 -> 不需要重读
            return signature
        try:
            self.ImgManager.init(
                self.ImgManager.input_path,
                type=3,
                parallel_to_sequential=bool(
                    getattr(self.shared_config, "parallel_to_sequential", False)),
            )
            self.ImgManager.set_action_count(0)
            self.shared_config.batch_idx = 0
            self._debug_image(
                f"[ImageList] list file changed, reloaded: {self.ImgManager.input_path}")
        except Exception as ex:
            if getattr(self.shared_config, "debug_image", False):
                print(f"[ImageList] reload list file failed: {ex}")
        return signature

    def show_img_init(self):
        if getattr(self.ImgManager, 'type', None) is None:
            return
        # ★ 图片模式下待应用的 parallel / parallel+sequential 切换在这里统一生效。
        #   勾选开关时不做任何重建（避免切换瞬间就重扫目录 + 重拼接），
        #   而是在下一次真正重绘之前（手动刷新 / 翻页 / 放大框变化等）才应用，
        #   保证数据模型与界面开关始终一致，不会出现 count_per_action 与 flist 错位。
        if (getattr(self, "_parallel_switch_dirty", False)
                and not getattr(self.shared_config, "video_mode", False)):
            self._parallel_switch_dirty = False
            self._apply_parallel_switch_image()

        # ★ 列表文件(type 3)可能在外部被改过: 先比指纹, 变了就重新读取一遍。
        #   这一步放在 set_img_layout() 之前, 保证后面的布局/批数计算用的是最新列表。
        list_signature = self._reload_list_file_if_changed()

        layout_params = self.set_img_layout()
        # ★ 修复：图片模式 + 视频模式 都要在 layout 变化时清空缓存与磁盘缓存文件
        vm = getattr(self, "video_manager", None)
        layout_token = repr(layout_params)
        if not getattr(self.shared_config, "video_mode", False):
            # ★ 缓存 token 里带上列表文件的内容指纹:
            #   以前 token 只有 (布局, 类型, 输入路径), 同一个 1.txt 改内容再重新选择时
            #   token 不变 -> 内存缓存和磁盘 PNG 都不作废 -> 页面还是旧的拼接图。
            image_token = (layout_token, getattr(self.ImgManager, "type", None),
                           repr(getattr(self.ImgManager, "input_path", None)),
                           list_signature)
            if image_token != getattr(self, "_image_layout_token", None):
                with self._image_stitch_lock:
                    self._debug_image(f"[ImageCache] reset, previous_batches={len(self.shared_config.image_cache_img)}")
                    # 清空内存缓存
                    self.shared_config.image_cache_img = []
                    self.shared_config.image_cache_paths = []
                    self._image_layout_token = image_token
                    # Invalidation is state-only; scanning/deleting PNGs stays
                    # on the image coordinator, never under a GUI-held lock.
                    self.image_pipeline.invalidate()
        else:
            # 视频模式：layout 参数变化时清空 cache_img 与磁盘缓存，
            # 避免旧尺寸的拼接帧被后续 show_img/update_cache 错误复用
            if layout_token != getattr(self, "_video_layout_token", None):
                try:
                    if vm is not None:
                        vm._invalidate_stitch_cache()
                    elif not hasattr(self.shared_config, "cache_img") or self.shared_config.cache_img is None:
                        self.shared_config.cache_img = []
                    else:
                        for i in range(len(self.shared_config.cache_img)):
                            self.shared_config.cache_img[i] = None
                except Exception:
                    pass
                # 强制 video_manager 在下次 update_cache 中重建窗口
                self._video_layout_token = layout_token
                try:
                    self._last_refresh_batch = None
                    if vm is not None and hasattr(vm, "_last_batch"):
                        vm._last_batch = None
                except Exception:
                    pass

        count_per_action = getattr(self.shared_config, "count_per_action", 1)
        if self.shared_config.video_mode:
            synced = self._sync_video_count_per_action()
            if synced is not None:
                count_per_action = synced

        if layout_params:
            self.ImgManager.layout_params = layout_params
            self.ImgManager._show_all_func_expanded_row_col = None
            self._image_reference_resolution_origin = None

            # Key: skip generic recompute in video mode to avoid resetting count_per_action back to 1
            if not self.shared_config.video_mode:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    if self.parallel_to_sequential.Value:
                        count_per_action = (
                            layout_params[0][0] * layout_params[0][1] *
                            layout_params[1][0] * layout_params[1][1]
                        )
                    else:
                        if self.parallel_sequential.Value:
                            count_per_action = layout_params[1][0] * layout_params[1][1]
                        else:
                            count_per_action = 1
                elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                    count_per_action = (
                        layout_params[0][0] * layout_params[0][1] *
                        layout_params[1][0] * layout_params[1][1]
                    )

            self.ImgManager.set_count_per_action(count_per_action)

        self.shared_config.count_per_action = count_per_action

    def _sync_video_count_per_action(self):
        if not getattr(self.shared_config, "video_mode", False):
            return None
        try:
            row_col_str = self.row_col.GetLineText(0)
            row_col = [int(x.strip()) for x in row_col_str.split(',') if x.strip()]
            if len(row_col) != 2:
                return None
        except Exception:
            return None

        try:
            one_img_str = self.row_col_one_img.GetValue().replace('，', ',')
            r, c = [int(x.strip()) for x in one_img_str.split(',') if x.strip()]
        except Exception:
            return None

        one_img_product = max(1, r * c)
        if self.shared_config.input_mode in (2, 3) or (self.shared_config.input_mode in (0, 1) and self.parallel_to_sequential.Value):
            count_per_action = row_col[0] * row_col[1] * one_img_product
        else:
            count_per_action = one_img_product

        count_per_action = max(1, int(count_per_action))
        self.shared_config.count_per_action = count_per_action
        try:
            self.ImgManager.set_count_per_action(count_per_action)
        except Exception:
            pass
        return count_per_action

    def set_img_layout(self):

        try:
            row_col = self.row_col.GetLineText(0).split(',')
            row_col = [int(x) for x in row_col]

            row_col_one_img = self.row_col_one_img.GetLineText(0).split(',')
            row_col_one_img = [int(x) for x in row_col_one_img]

            if row_col_one_img[0] == -1 and row_col_one_img[1] == -1:
                row_col_one_img= [1,1]
                row_col = self.ImgManager.layout_advice()
                self.row_col.SetValue(str(row_col[0])+","+str(row_col[1]))

            row_col_img_unit = self.row_col_img_unit.GetLineText(0).split(',')
            row_col_img_unit = [int(x) for x in row_col_img_unit]

            magnifer_row_col = self.magnifer_row_col.GetLineText(0).split(',')
            magnifer_row_col = [int(x) for x in magnifer_row_col]

            gap = self.gap.GetLineText(0).split(',')
            gap = [int(x) for x in gap]

            show_scale = self.show_scale.GetLineText(0).split(',')
            show_scale = [float(x) for x in show_scale]

            output_scale = self.output_scale.GetLineText(0).split(',')
            output_scale = [float(x) for x in output_scale]

            img_resolution = self.img_resolution.GetLineText(0).split(',')
            img_resolution = [int(x) for x in img_resolution]

            magnifer_resolution = self.magnifer_resolution.GetLineText(
                0).split(',')
            magnifer_resolution = [int(x) for x in magnifer_resolution]

            magnifier_show_scale = self.magnifier_show_scale.GetLineText(
                0).split(',')
            magnifier_show_scale = [float(x) for x in magnifier_show_scale]

            magnifier_out_scale = self.magnifier_out_scale.GetLineText(
                0).split(',')
            magnifier_out_scale = [float(x) for x in magnifier_out_scale]

            if self.checkBox_auto_draw_color.Value:
                # 10 colors built into the software
                color_list = [
                    wx.Colour(217, 26, 42, int(85/100*255)),
                    wx.Colour(147, 81, 166, int(65/100*255)),
                    wx.Colour(85, 166, 73, int(65/100*255)),
                    wx.Colour(242, 229, 48, int(95/100*255)),
                    wx.Colour(242, 116, 5, int(95/100*255)),
                    wx.Colour(242, 201, 224, int(95/100*255)),
                    wx.Colour(36, 132, 191, int(75/100*255)),
                    wx.Colour(65, 166, 90, int(65/100*255)),
                    wx.Colour(214, 242, 206, int(95/100*255)),
                    wx.Colour(242, 163, 94, int(95/100*255))]
                num_box = len(self.xy_magnifier)
                if num_box <= len(color_list):
                    self.color_list = color_list[0:num_box]
                else:
                    self.color_list = color_list + \
                        color_list[0:num_box-len(color_list)]

            color = self.color_list

            line_width = self.line_width.GetLineText(0).split(',')
            line_width = [int(x) for x in line_width]

            title_setting = [self.title_auto.Value,                     # 0
                             self.title_show.Value,                     # 1
                             self.title_down_up.Value,                  # 2
                             self.title_show_parent.Value,              # 3
                             self.title_show_prefix.Value,              # 4
                             self.title_show_name.Value,                # 5
                             self.title_show_suffix.Value,              # 6
                             self.title_font.GetSelection(),            # 7
                             self.title_font_size.Value,                # 8
                             self.font_paths,                           # 9
                             self.title_position.GetSelection(),        # 10
                             self.title_exif.Value,                     # 11
                             self.title_show_rename.Value]              # 12

            if title_setting[0]:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    # one_dir_mul_dir_auto / one_dir_mul_dir_manual
                    if self.parallel_sequential.Value or self.parallel_to_sequential.Value:
                        title_setting[2:7] = [False, True, True, True, False]
                    else:
                        if self.shared_config.video_mode:
                            title_setting[2:7] = [False, False, True, True, False]
                        else:
                            title_setting[2:7] = [False, True, True, False, False]

                elif self.ImgManager.type == 2:
                    # one_dir_mul_img
                    title_setting[2:7] = [False, False, True, True, False]
                elif self.ImgManager.type == 3:
                    # read file list from a list file
                    title_setting[2:7] = [False, True, True, True, False]
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [row_col,                                # 0
                    row_col_one_img,                        # 1
                    row_col_img_unit,                       # 2
                    gap,                                    # 3
                    show_scale,                             # 4
                    output_scale,                           # 5
                    img_resolution,                         # 6
                    1 if self.magnifier.Value else 0,       # 7
                    magnifier_show_scale,                   # 8
                    color,                                  # 9
                    line_width,                             # 10
                    self.move_file.Value,                   # 11
                    self.keep_magnifer_size.Value,          # 12
                    self.image_interp.GetSelection(),       # 13
                    self.show_box.Value,                    # 14
                    self.show_box_in_crop.Value,            # 15
                    self.show_original.Value,               # 16
                    title_setting,                          # 17
                    self.show_magnifer.Value,               # 18
                    self.parallel_to_sequential.Value,      # 19
                    self.one_img.Value,                     # 20
                    self.box_position.GetSelection(),       # 21
                    self.parallel_sequential.Value,         # 22
                    self.auto_save_all.Value,               # 23
                    self.img_vertical.Value,                # 24
                    self.one_img_vertical.Value,            # 25
                    self.img_unit_vertical.Value,           # 26
                    self.magnifer_vertical.Value,           # 27
                    magnifer_resolution,                    # 28
                    magnifer_row_col,                       # 29
                    self.onetitle.Value,                    # 30
                    magnifier_out_scale,                    # 31
                    self.show_custom_func.Value,            # 32
                    self.out_path_str,                      # 33
                    self.Magnifier_format.GetSelection(),   # 34
                    self.save_format.GetSelection(),        # 35
                    self.show_unit.Value,                   # 36
                    self.customfunc_choice.GetSelection(),  # 37
                    self.show_all_func.Value,               # 38
                    self.show_all_func_layout.Value,        # 39
                    self.func_layout_vertical.Value ]       # 40

    def show_img(self, preserve_text_value=False):
        self._setup_img_panel()

        # ========== 视频模式 ==========
        if getattr(self.shared_config, "video_mode", False):
            b = int(self.shared_config.batch_idx)

            # 从磁盘加载图像（cache_entry 现在是文件路径字符串）
            # ★ 走 _video_cached_batch_path: 磁盘缓存按窗口清理过, 内存里记下的路径
            #   可能已经失效, 这里统一判定为"无缓存", 交给下面的重建流程, 避免 Load cache failed。
            cache_entry = self._video_cached_batch_path(b)

            # 当前批次未就绪且暂停时，安排后台重建；完成回调负责显示。
            #   典型场景：从图片模式切到视频模式、或刚选完视频时，
            #   show_img_init() 会因布局参数变化清空视频缓存，
            #   导致首帧缺失而一直停在 "Waiting for batch N"，必须手动刷新才恢复。
            if cache_entry is None and not getattr(self.shared_config, "is_playing", False):
                cache_entry = self._rebuild_video_cache_for_batch(b)

            if cache_entry is not None:
                # cache_entry 是文件路径字符串
                try:
                    self.shared_config.video_last_message = ""
                    self._request_video_display(b, cache_entry)

                    # 更新状态栏（保留 FPS 计算逻辑，但不显示）
                    self.SetStatusText_([
                        str(b),
                        str(self.ImgManager.max_action_num - 1),
                        "",
                        "-1"
                    ])

                    # 更新滑块
                    if hasattr(self, "slider_img") and self.slider_img:
                        try:
                            max_val = max(0, self.ImgManager.max_action_num - 1)
                            self.slider_img.SetMax(max_val)
                            self.slider_img.SetValue(b)
                        except Exception:
                            pass

                    # 更新页数文本框
                    if hasattr(self, "slider_value") and self.slider_value:
                        try:
                            self.slider_value.SetValue(str(b))
                        except Exception:
                            pass
                    if hasattr(self, "slider_value_max") and self.slider_value_max:
                        try:
                            self.slider_value_max.SetLabel(str(max(0, self.ImgManager.max_action_num - 1)))
                        except Exception:
                            pass

                    self._cancel_pending_frame_wait()

                except Exception as ex:
                    self.SetStatusText_(["-1", "-1", f"***Load cache failed: {ex}***", "-1"])
            else:
                # 缓存未就绪
                msg = getattr(self.shared_config, "video_last_message", "")
                if not msg:
                    msg = f"Waiting for batch {b}..."

                self.SetStatusText_([str(b), str(self.ImgManager.max_action_num - 1), msg, "-1"])

                # 更新滑块
                if hasattr(self, "slider_img") and self.slider_img:
                    try:
                        max_val = max(0, self.ImgManager.max_action_num - 1)
                        self.slider_img.SetMax(max_val)
                        self.slider_img.SetValue(b)
                    except Exception:
                        pass

                # 更新页数文本框
                if hasattr(self, "slider_value") and self.slider_value:
                    try:
                        self.slider_value.SetValue(str(b))
                    except Exception:
                        pass
                if hasattr(self, "slider_value_max") and self.slider_value_max:
                    try:
                        self.slider_value_max.SetLabel(str(max(0, self.ImgManager.max_action_num - 1)))
                    except Exception:
                        pass

                # 如果是播放模式，调度等待回调
                if getattr(self.shared_config, "is_playing", False):
                    self._schedule_frame_wait()

            # 清除可能残留的 "frame batch" 文本（第1列）
            self.m_statusBar1.SetStatusText("", 1)
            return

        # ========== 图片模式：后台拼接、磁盘缓存、后台准备显示 ==========
        if self.ImgManager.max_action_num > 0:
            current_batch = max(0, min(int(getattr(self.shared_config, "batch_idx", 0)),
                                       self.ImgManager.max_action_num - 1))
            self.shared_config.batch_idx = current_batch

            # 更新滑块位置、最大值和文本框
            if hasattr(self, "slider_img") and self.slider_img:
                try:
                    max_val = max(0, self.ImgManager.max_action_num - 1)
                    self.slider_img.SetMax(max_val)
                    if self.slider_img.GetValue() != current_batch:
                        self.slider_img.SetValue(current_batch)
                except Exception:
                    pass
            # 只在不需要保留文本框值时才更新
            if hasattr(self, "slider_value") and self.slider_value and not preserve_text_value:
                try:
                    self.slider_value.SetValue(str(current_batch))
                except Exception:
                    pass
            if hasattr(self, "slider_value_max") and self.slider_value_max:
                try:
                    self.slider_value_max.SetLabel(str(max(0, self.ImgManager.max_action_num - 1)))
                except Exception:
                    pass

            # 更新图片缓存
            self._update_image_cache(current_batch)

            if self.shared_config.is_playing:
                self._suspend_play_timer_for_wait()
            if not self.image_pipeline.prepare_display(current_batch, self._deliver_image_frame):
                self.SetStatusText_([str(current_batch),
                    str(self.ImgManager.max_action_num - 1),
                    f"Waiting for batch {current_batch}...", "-1"])
            elif self.image_pipeline.displayed_key is not None:
                if self.image_pipeline.displayed_key[1] == current_batch:
                    self._resume_play_timer_after_wait()
        else:
            # 无图像数据
            self.SetStatusText_(["-1", "-1", "No images", "-1"])

    def _get_image_flist(self, batch_idx: int):
        count = max(1, self.ImgManager.count_per_action)
        orig_action = self.ImgManager.action_count
        orig_img_count = getattr(self.ImgManager, "img_count", 0)
        orig_flist = getattr(self.ImgManager, "flist", None)

        try:
            self.ImgManager.action_count = batch_idx
            self.ImgManager.img_count = batch_idx * count
            flist = self.ImgManager.get_flist()
            return list(flist) if flist else []
        finally:
            self.ImgManager.action_count = orig_action
            self.ImgManager.img_count = orig_img_count
            if orig_flist is not None:
                self.ImgManager.flist = orig_flist

    def _update_image_cache(self, batch_idx: int):
        if self.ImgManager.max_action_num <= 0:
            return
        self._apply_resource_policy()
        # Snapshot GUI inputs once per render context. Each batch then clones
        # this template without copying dataset filenames or touching live state.
        context = (getattr(self, '_image_layout_token', None),
                   id(self.shared_config.image_cache_img),
                   id(self.ImgManager.name_list), id(self.ImgManager.path_list),
                   repr(self.xy_magnifier), bool(self.show_custom_func.GetValue()))
        if context != getattr(self, '_image_snapshot_key', None):
            self._image_snapshot_key = context
            self._image_snapshot = self.ImgManager.video_stitch_snapshot()
        self.image_pipeline.request(self._image_snapshot, copy.deepcopy(self.xy_magnifier),
            self.show_custom_func.GetValue(), context, batch_idx,
            self.ImgManager.max_action_num, self.shared_config.cache_num,
            self.shared_config.cache_multiplier, self.shared_config.thread,
            self.shared_config.memory_budget, self.shared_config.play_direction)

    def _image_frame_ready(self, batch, generation, error=None):
        if (getattr(self, '_is_closing', False) or self.shared_config.video_mode
                or generation != self.image_pipeline.generation
                or batch != int(self.shared_config.batch_idx)):
            return
        self._show_resource_tooltip()
        if error:
            self.SetStatusText_(['-1', '-1', f'***{error}***', '-1'])
            self._resume_play_timer_after_wait()
            return
        self.image_pipeline.prepare_display(batch, self._deliver_image_frame)

    def _deliver_image_frame(self, batch, generation, pixels, state, error):
        if (getattr(self, '_is_closing', False) or self.shared_config.video_mode
                or generation != self.image_pipeline.generation
                or batch != int(self.shared_config.batch_idx)):
            return
        if error:
            self.SetStatusText_(['-1', '-1', f'***Load cache failed: {error}***', '-1'])
            return
        image, rgba = pixels
        for name, value in state.items():
            setattr(self.ImgManager, name, value)
        self.ImgManager.img = image
        self.ImgManager.action_count = batch
        self.ImgManager.img_count = batch * self.ImgManager.count_per_action
        self.current_page_img_paths = copy.deepcopy(state.get('flist', []))
        self.show_bmp_in_panel, self.img_size = image, image.size
        self.display_bitmap(False, image, prepared_rgba=rgba)
        if self.shared_config.is_playing:
            self.resource_monitor.frame_presented(batch, self.shared_config.play_direction)
        self.update_status_bar_for_current_page()
        self._show_resource_tooltip()
        self._resume_play_timer_after_wait()

    def _compact_row_col_for_count(self, count):
        if count <= 1:
            return [1, 1]
        row = int(math.sqrt(count))
        while row > 1 and count % row != 0:
            row -= 1
        col = int(math.ceil(count / row))
        return [min(row, col), max(row, col)]

    def _calc_reference_resolution_origin(self, flist):
        widths = []
        heights = []
        for path in flist:
            try:
                with Image.open(path) as img:
                    widths.append(img.size[0])
                    heights.append(img.size[1])
            except Exception:
                pass
        if not widths or not heights:
            return None

        widths = np.sort(widths)
        heights = np.sort(heights)
        if self.ImgManager.img_stitch_mode == 2:
            width = max(widths)
            height = max(heights)
        elif self.ImgManager.img_stitch_mode == 1:
            width = np.min(widths)
            height = np.min(heights)
        else:
            if len(widths) > 3:
                width = np.mean(widths[1:-1])
                height = np.mean(heights[1:-1])
            else:
                width = np.mean(widths)
                height = np.mean(heights)
        return [int(width), int(height)]

    def compose_current_frame(self, batch_idx=0, flist=None):
        """
        Only generate the stitched result for the current frame; do not touch UI state.
        Returns: (pil_img, flag)
        - pil_img: PIL.Image or None
        - flag: 0 means success; other values follow ImgManager.stitch_images semantics
        """
        original_row_col = None
        original_resolution_setting = None
        full_capacity = None
        try:
            if flist is not None and not getattr(self.shared_config, "video_mode", False):
                row_col = self.ImgManager.layout_params[0]
                row_col_one_img = self.ImgManager.layout_params[1]
                one_img_capacity = max(1, row_col_one_img[0] * row_col_one_img[1])
                full_capacity = max(1, row_col[0] * row_col[1] * one_img_capacity)
                # 【修复】禁用自动压缩：原本当 len(flist) < full_capacity 时会强制用最小包围盒
                # 改写 RowCol（例如 3 张图 + RowCol=2,2 → 被改成 [1,3]），
                # 导致用户在 parallel manual / 末尾 batch 等场景无法使用自己设置的布局。
                # 这里直接关闭该压缩逻辑，UI 上设的 RowCol 永远生效。
                if False and 0 < len(flist) < full_capacity:
                    original_row_col = row_col.copy()
                    compact_count = int(math.ceil(len(flist) / one_img_capacity))
                    self.ImgManager.layout_params[0] = self._compact_row_col_for_count(compact_count)
                    self.ImgManager._show_all_func_expanded_row_col = None

                    resolution_setting = self.ImgManager.layout_params[6]
                    if -1 in resolution_setting:
                        reference_resolution = getattr(self, "_image_reference_resolution_origin", None)
                        if reference_resolution is None:
                            reference_flist = self._get_image_flist(0)
                            if len(reference_flist) >= full_capacity:
                                reference_resolution = self._calc_reference_resolution_origin(
                                    reference_flist[:full_capacity])
                        if reference_resolution is not None:
                            original_resolution_setting = resolution_setting.copy()
                            self.ImgManager.layout_params[6] = reference_resolution

            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True
                self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier), flist=flist)
                self.ImgManager.layout_params[32] = False

            stitch_start = time.time()
            flag = self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier), flist=flist)
            stitch_duration = time.time() - stitch_start
            if flag != 0:
                return None, flag

            pil_img = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)
            if (flist is not None and full_capacity is not None
                    and len(flist) >= full_capacity and -1 in self.ImgManager.layout_params[6]):
                self._image_reference_resolution_origin = self.ImgManager.img_resolution_origin.copy()
        finally:
            if original_resolution_setting is not None:
                self.ImgManager.layout_params[6] = original_resolution_setting
            if original_row_col is not None:
                self.ImgManager.layout_params[0] = original_row_col
                self.ImgManager._show_all_func_expanded_row_col = None

        self.show_bmp_in_panel = pil_img
        self.img_size = pil_img.size

        video_mode = getattr(self.shared_config, "video_mode", False)
        cache_list = self.shared_config.cache_img if video_mode else self.shared_config.image_cache_img
        path_cache = self.shared_config.image_cache_paths if not video_mode else None
        need = batch_idx + 1 - len(cache_list)
        if need > 0:
            cache_list.extend([None] * need)
            if path_cache is not None:
                path_cache.extend([None] * need)
        cache_list[batch_idx] = pil_img

        if not video_mode:
            store_list = flist if flist is not None else getattr(self.ImgManager, "flist", None)
            if path_cache is not None:
                path_cache[batch_idx] = list(store_list) if store_list else None

        if video_mode:
            vm = getattr(self, "video_manager", None)
            if vm and pil_img is not None:
                vm.perf_monitor.record_stitch(stitch_duration)

        return pil_img, 0

    #b3 修改3：display_bitmap —— 移除 Thaw 后多余的 Refresh，以及视频播放时跳过重复 layout
    # def display_bitmap(self, video_mode, pil_img):
    #     dbg_batch = int(getattr(self.shared_config, "batch_idx", -1))
    #
    #     if pil_img is None and video_mode:
    #         cache = getattr(self.shared_config, "cache_img", [])
    #         b = int(getattr(self.shared_config, "batch_idx", 0))
    #         if not (0 <= b < len(cache)) or cache[b] is None:
    #             return
    #         pil_img = cache[b]
    #
    #     try:
    #         if video_mode and pil_img is not None:
    #             arr = np.array(pil_img.convert("RGBA"), dtype=np.uint8)
    #
    #             bg_rgb = np.array(self.ImgManager.gap_color[:3], dtype=np.int16)
    #             rgb = arr[:, :, :3].astype(np.int16)
    #             alpha = arr[:, :, 3].astype(np.int16)
    #
    #             tol = 6
    #             alpha_min = 8
    #
    #             diff = np.max(np.abs(rgb - bg_rgb), axis=2)
    #             content = (diff > tol) & (alpha > alpha_min)
    #
    #             if np.any(content):
    #                 h, w = content.shape
    #                 row_hits = content.sum(axis=1)
    #                 col_hits = content.sum(axis=0)
    #
    #                 row_thr = max(12, int(w * 0.01))
    #                 col_thr = max(12, int(h * 0.01))
    #
    #                 ys_thr = np.where(row_hits > row_thr)[0]
    #                 xs_thr = np.where(col_hits > col_thr)[0]
    #
    #                 ys_any = np.where(content.any(axis=1))[0]
    #                 xs_any = np.where(content.any(axis=0))[0]
    #
    #                 if ys_any.size > 0 and xs_any.size > 0:
    #                     y0 = int(ys_thr[0]) if ys_thr.size > 0 else int(ys_any[0])
    #                     x0 = int(xs_thr[0]) if xs_thr.size > 0 else int(xs_any[0])
    #
    #                     y1 = int(ys_any[-1]) + 1
    #                     x1 = int(xs_any[-1]) + 1
    #
    #                     arr = arr[y0:y1, x0:x1]
    #                     pil_img = Image.fromarray(arr, mode="RGBA")
    #     except Exception:
    #         pass
    #
    #     bmp = self.ImgManager.ImgF.PIL2wx(pil_img)
    #     self._set_placeholder_visible(False)
    #
    #     if hasattr(self, "img_last") and self.img_last:
    #         self.img_last.SetBitmap(bmp)
    #     else:
    #         self.img_last = wx.StaticBitmap(self.img_panel, bitmap=bmp)
    #     self._ensure_img_bindings()
    #
    #     if not hasattr(self, "img_panel_sizer"):
    #         self.img_panel_sizer = wx.BoxSizer(wx.VERTICAL)
    #         self.img_panel.SetSizer(self.img_panel_sizer)
    #     else:
    #         try:
    #             self.img_panel_sizer.Clear(False)
    #         except Exception:
    #             pass
    #
    #     self.img_panel_sizer.Add(self.img_last, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP, 0)
    #
    #     # Key fix: use PIL logical size for layout, not bmp.GetSize() HiDPI physical pixels
    #     logical_w, logical_h = pil_img.size
    #     logical_size = wx.Size(int(logical_w), int(logical_h))
    #
    #     self.img_last.SetPosition((0, 0))
    #     self.img_last.SetSize(logical_size)
    #     self.img_last.SetMinSize(logical_size)
    #
    #     self.img_panel.SetPosition((0, 0))
    #     self.img_panel.SetSize(logical_size)
    #     self.img_panel.SetMinSize(logical_size)
    #
    #     try:
    #         self.scrolledWindow_img.Freeze()
    #     except Exception:
    #         pass
    #
    #     self.img_panel.Layout()
    #     self.scrolledWindow_img.Layout()
    #     self.scrolledWindow_img.SetVirtualSize(logical_size)
    #     self.scrolledWindow_img.Scroll(0, 0)
    #     self.position = [0, 0]
    #
    #     try:
    #         self.scrolledWindow_img.Thaw()
    #     except Exception:
    #         pass
    #
    #     wx.CallAfter(self.scrolledWindow_img.Scroll, 0, 0)
    #     self.scrolledWindow_img.Refresh()

    def display_bitmap(self, video_mode, pil_img, prepared_rgba=None):
        dbg_batch = int(getattr(self.shared_config, "batch_idx", -1))

        if pil_img is None and video_mode:
            cache = getattr(self.shared_config, "cache_img", [])
            b = int(getattr(self.shared_config, "batch_idx", 0))
            if not (0 <= b < len(cache)) or cache[b] is None:
                return
            pil_img = cache[b]

        try:
            if video_mode and pil_img is not None and prepared_rgba is None:
                arr = np.array(pil_img.convert("RGBA"), dtype=np.uint8)
                bg_rgb = np.array(self.ImgManager.gap_color[:3], dtype=np.int16)
                rgb = arr[:, :, :3].astype(np.int16)
                alpha = arr[:, :, 3].astype(np.int16)
                tol = 6
                alpha_min = 8
                diff = np.max(np.abs(rgb - bg_rgb), axis=2)
                content = (diff > tol) & (alpha > alpha_min)
                if np.any(content):
                    h, w = content.shape
                    row_hits = content.sum(axis=1)
                    col_hits = content.sum(axis=0)
                    row_thr = max(12, int(w * 0.01))
                    col_thr = max(12, int(h * 0.01))
                    ys_thr = np.where(row_hits > row_thr)[0]
                    xs_thr = np.where(col_hits > col_thr)[0]
                    ys_any = np.where(content.any(axis=1))[0]
                    xs_any = np.where(content.any(axis=0))[0]
                    if ys_any.size > 0 and xs_any.size > 0:
                        y0 = int(ys_thr[0]) if ys_thr.size > 0 else int(ys_any[0])
                        x0 = int(xs_thr[0]) if xs_thr.size > 0 else int(xs_any[0])
                        y1 = int(ys_any[-1]) + 1
                        x1 = int(xs_any[-1]) + 1
                        arr = arr[y0:y1, x0:x1]
                        pil_img = Image.fromarray(arr, mode="RGBA")
        except Exception:
            pass

        logical_w, logical_h = pil_img.size
        logical_size = wx.Size(int(logical_w), int(logical_h))

        # ★ 判断尺寸是否变化，不变则跳过整个 sizer/layout 重建
        last_size = getattr(self, "_last_display_logical_size", None)
        size_changed = (last_size != logical_size)
        self._last_display_logical_size = logical_size

        # ★ Freeze 必须在一切 layout 操作之前，否则无效
        bmp = (wx.Bitmap.FromBufferRGBA(logical_w, logical_h, prepared_rgba)
               if prepared_rgba is not None else self.ImgManager.ImgF.PIL2wx(pil_img))
        frozen = False
        try:
            if size_changed:
                self.scrolledWindow_img.Freeze()
                frozen = True
        except Exception:
            pass

        self._set_placeholder_visible(False)

        if hasattr(self, "img_last") and self.img_last:
            self.img_last.SetBitmap(bmp)
        else:
            self.img_last = wx.StaticBitmap(self.img_panel, bitmap=bmp)
            size_changed = True  # 新控件必须走一次完整 layout
        self._ensure_img_bindings()

        if size_changed:
            # 只在尺寸变化时才重建 sizer 和 layout
            if not hasattr(self, "img_panel_sizer"):
                self.img_panel_sizer = wx.BoxSizer(wx.VERTICAL)
                self.img_panel.SetSizer(self.img_panel_sizer)
            else:
                try:
                    self.img_panel_sizer.Clear(False)
                except Exception:
                    pass
            self.img_panel_sizer.Add(self.img_last, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP, 0)

            self.img_last.SetPosition((0, 0))
            self.img_last.SetSize(logical_size)
            self.img_last.SetMinSize(logical_size)

            self.img_panel.SetPosition((0, 0))
            self.img_panel.SetSize(logical_size)
            self.img_panel.SetMinSize(logical_size)

            self.img_panel.Layout()
            self.scrolledWindow_img.Layout()
            self.scrolledWindow_img.SetVirtualSize(logical_size)
            self.scrolledWindow_img.Scroll(0, 0)

        self.position = [0, 0]

        try:
            if frozen:
                self.scrolledWindow_img.Thaw()
        except Exception:
            pass
        # ★ 删除 Refresh()：Thaw() 本身触发延迟重绘，再调 Refresh() 造成第二次绘制
        # ★ 删除 CallAfter(Scroll, 0,0)：show_img 里已有此调用，不需要在这里重复

    def auto_layout(self, frame_resize=False):
        displays = (wx.Display(i) for i in range(wx.Display.GetCount()))
        displays_list = [display for display in displays]
        sizes = [display.GetGeometry().GetSize() for display in displays_list]
        screen_id = wx.Display.GetFromWindow(self)
        self.displaySize = sizes[screen_id]

        if self.hidden_flag == 1:
            offset_hight_img_show = 50
        else:
            offset_hight_img_show = 0

        if self.auto_layout_check.Value and (not frame_resize):
            if self.img_size[0] < self.width:
                if self.img_size[0]+self.width_setting+40 < self.width:
                    w = self.width
                else:
                    w = self.img_size[0]+self.width_setting+40
            elif self.img_size[0]+self.width_setting+40 > self.displaySize[0]:
                w = self.displaySize[0]
            else:
                w = self.img_size[0]+self.width_setting+40

            if self.img_size[1] < self.height:
                if self.img_size[1]+200 < self.height:
                    h = self.height
                else:
                    h = self.img_size[1]+200
                    if self.hidden_flag == 1:
                        h = h-50
            elif self.img_size[1]+200 > self.displaySize[1]:
                h = self.displaySize[1]
            else:
                h = self.img_size[1]+200
                if self.hidden_flag == 1:
                    h = h-50

            self.Size = wx.Size((w, h))

        if self.hidden_flag == 1:
            self.m_splitter1.SashPosition = self.Size[0]

        self.init_min_size()

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0]-self.width_setting, self.Size[1]-150+offset_hight_img_show)))

        # issue: You need to change the window size, then the scrollbar starts to display.
        if not getattr(self.shared_config, "video_mode", False):
            self.scrolledWindow_img.FitInside()
        self.scrolledWindow_set.FitInside()

        self.Layout()
        self.Refresh()

    def init_min_size(self):
        self.scrolledWindow_set.SetMinSize(
            wx.Size((50, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((50, self.Size[1]-150)))

    def split_sash_pos_changing(self, event):

        self.init_min_size()
        self.split_changing = True

    def split_sash_pos_changed(self, event):
        self.SashPosition = self.m_splitter1.SashPosition

        if self.split_changing:
            self.width_setting = self.Size[0]-self.SashPosition

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0] - self.width_setting, self.Size[1]-150)))

        self.split_changing = False

    def about_gui(self, event, update=False, new_version=None):
        self.aboutgui = About(self, self.version,
                              update=update, new_version=new_version)
        self.aboutgui.Show(True)

    def index_table_gui(self, event):
        if self.ImgManager.img_num != 0:
            if self.ImgManager.dataset_mode and self.out_path_str == "":
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
            else:
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt saving...", "-1"])
                if self.ImgManager.type == 3:
                    self.indextablegui = IndexTable(
                        None, self.ImgManager.path_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                else:
                    self.indextablegui = IndexTable(
                        None, self.ImgManager.name_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt save in "+self.out_path_str, "-1"])
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])

    def _debug_image(self, message):
        if getattr(self.shared_config, "debug_image", False):
            print(message)

    def create_ImgManager(self):
        self.ImgManager = ImgManager()
        self.colour_change([])
        return self.ImgManager

    def change_img_stitch_mode(self, event):
        self.ImgManager.img_stitch_mode = self.choice_normalized_size.GetSelection()

    def get_img_id_from_point(self, xy, img=False):
        # get img_id from grid points
        xy_grid = np.array(self.ImgManager.xy_grid)
        xy_cur = np.array([xy])
        xy_cur = np.repeat(xy_cur, xy_grid.shape[0], axis=0)
        res_ = xy_cur - xy_grid
        id_list = []
        for i in range(xy_grid.shape[0]):
            if res_[i][0] >= 0 and res_[i][1] >= 0:
                id_list.append(i)
            else:
                id_list.append(0)
        if img:
            return self.ImgManager.xy_grids_id_list[max(id_list)]
        else:
            return max(id_list)

    def title_down_up_fc(self, event):
        if self.title_down_up.Value:
            self.title_down_up.SetLabel('Up  ')
        else:
            self.title_down_up.SetLabel('Down')

    def title_rename_fc(self, event):
        if hasattr(self.ImgManager, 'layout_params') and len(self.ImgManager.layout_params) > 17:
            if len(self.ImgManager.layout_params[17]) > 12:
                self.ImgManager.layout_params[17][12] = self.title_show_rename.Value

    def title_auto_fc(self, event):
        titles = [self.title_down_up, self.title_show_parent,
                  self.title_show_name, self.title_show_suffix, self.title_show_prefix,
                  self.title_position, self.title_exif, self.m_checkBox31, self.m_textCtrl16]
        if self.title_auto.Value:
            for title in titles:
                title.Enabled = False
        else:
            for title in titles:
                title.Enabled = True

    def select_img_box_func(self, event):
        if self.select_img_box.Value:
            self.box_id = -1
        event.Skip()

    def draw_color_change(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                if self.checkBox_auto_draw_color.Value:
                    self.checkBox_auto_draw_color.Value = False
                self.color_list[self.box_id] = self.colourPicker_draw.GetColour()
                self._invalidate_render_cache()
                self.refresh(event)
        event.Skip()

    def hidden(self, event):
        if self.hidden_flag == 0:
            self.Sizer.Hide(self.m_panel1)
            self.scrolledWindow_set.Sizer.Hide(self.m_panel4)

            self.width_setting_ = self.width_setting
            self.width_setting = 0

            self.hidden_flag = 1
        else:
            self.Sizer.Show(self.m_panel1)
            self.scrolledWindow_set.Sizer.Show(self.m_panel4)

            self.width_setting = self.width_setting_

            self.hidden_flag = 0

        # issue: You need to change the window size, then the scrollbar starts to display.
        self.scrolledWindow_set.FitInside()
        self.auto_layout()

    def _bind_settings_wheel_guard(self):
        # Controls that should handle the wheel event.
        swallow_types = (wx.Choice, wx.ComboBox, wx.SpinCtrl, wx.SpinCtrlDouble)

        # Reroute wheel events back to the settings scrolled window.
        def reroute_wheel(event):
            clone = event.Clone()
            clone.SetEventObject(self.scrolledWindow_set)
            clone.ResumePropagation(wx.EVENT_PROPAGATE_MAX)
            self.scrolledWindow_set.GetEventHandler().ProcessEvent(clone)

        # Recursively bind wheel rerouting on relevant child controls.
        def walk(win):
            for child in win.GetChildren():
                if isinstance(child, swallow_types):
                    child.Bind(wx.EVT_MOUSEWHEEL, reroute_wheel)
                if child.GetChildren():
                    walk(child)

        walk(self.scrolledWindow_set)

    def save_configuration(self, event):
        self._commit_video_settings()
        data = {
            'power_mode': self.power_mode.GetSelection() + 1,
            'cache_frames': str(self.shared_config.cache_num),
            'cache_multiplier': str(self.shared_config.cache_multiplier),
            'row_col': self.row_col.GetLineText(0),
            'row_col_one_img': self.row_col_one_img.GetLineText(0),
            'show_scale': self.show_scale.GetLineText(0),
            'row_col_img_unit': self.row_col_img_unit.GetLineText(0),
            'gap': self.gap.GetLineText(0),
            'magnifer_row_col': self.magnifer_row_col.GetLineText(0),
            'output_scale': self.output_scale.GetLineText(0),
            'img_resolution': self.img_resolution.GetLineText(0),
            'magnifer_resolution': self.magnifer_resolution.GetLineText(0),
            'magnifier_show_scale': self.magnifier_show_scale.GetLineText(0),
            'line_width': self.line_width.GetLineText(0),
            'magnifier_out_scale': self.magnifier_out_scale.GetLineText(0),
            'title_font_size': self.title_font_size.GetLineText(0),
            'box_position': self.box_position.GetSelection(),
            'choice_normalized_size': self.choice_normalized_size.GetSelection(),
            'choice_output': self.choice_output.GetSelection(),
            'image_interp': self.image_interp.GetSelection(),
            'Magnifier_format': self.Magnifier_format.GetSelection(),
            'title_font': self.title_font.GetSelection(),
            'parallel_sequential': self.parallel_sequential.GetValue(),
            'parallel_to_sequential': self.parallel_to_sequential.GetValue(),
            'auto_save_all': self.auto_save_all.GetValue(),
            'move_file': self.move_file.GetValue(),
            'img_vertical': self.img_vertical.GetValue(),
            'one_img_vertical': self.one_img_vertical.GetValue(),
            'img_unit_vertical': self.img_unit_vertical.GetValue(),
            'magnifer_vertical': self.magnifer_vertical.GetValue(),
            'show_original': self.show_original.GetValue(),
            'show_magnifer': self.show_magnifer.GetValue(),
            'title_show': self.title_show.GetValue(),
            'auto_layout_check': self.auto_layout_check.GetValue(),
            'one_img': self.one_img.GetValue(),
            'onetitle': self.onetitle.GetValue(),
            'show_custom_func': self.show_custom_func.GetValue(),
            'show_box': self.show_box.GetValue(),
            'show_box_in_crop': self.show_box_in_crop.GetValue(),
            'select_img_box': self.select_img_box.GetValue(),
            'title_auto': self.title_auto.GetValue(),
            'title_exif': self.title_exif.GetValue(),
            'title_show_parent': self.title_show_parent.GetValue(),
            'title_show_prefix': self.title_show_prefix.GetValue(),
            'title_show_name': self.title_show_name.GetValue(),
            'title_show_suffix': self.title_show_suffix.GetValue(),
            'title_down_up': self.title_down_up.GetValue(),
            'save_format': self.save_format.GetSelection(),
            'title_show_rename': self.title_show_rename.GetValue(),
            'customfunc_choice': self.customfunc_choice.GetSelection(),
            'show_all_func': self.show_all_func.GetValue(),
            'show_all_func_layout': self.show_all_func_layout.GetValue(),
            'func_layout_vertical': self.func_layout_vertical.GetValue(),
        }
        config_path = Path(get_resource_path(str(Path("configs"))))
        config_file_path = str(config_path / "default_config.json")
        with open(config_file_path, 'r', encoding='utf-8') as file:
            full_config = json.load(file)
        full_config['output'] = data
        full_config['hotkeys'] = self.hotkeys
        with open(config_file_path, 'w', encoding='utf-8') as file:
            json.dump(full_config, file, indent=1)

    def load_configuration(self, event, config_name="default_config.json"):
        config_path = Path(get_resource_path(str(Path("configs"))))
        config_file_path = str(config_path / config_name)
        with open(config_file_path, 'r', encoding='utf-8') as file:
            full_config = json.load(file)
            data = full_config.get('output', full_config)
            # Old configurations without the new global settings use defaults.
            try:
                mode = max(1, min(4, int(data.get('power_mode', 2))))
            except (TypeError, ValueError):
                mode = 2
            self.power_mode.SetSelection(mode - 1)
            self.cache_frames.ChangeValue(str(data.get('cache_frames', data.get('row_col12', 2))))
            self.cache_multiplier.ChangeValue(str(data.get('cache_multiplier', 1)))
            self._commit_video_settings()
            self.row_col.SetValue(data['row_col'])
            self.row_col_one_img.SetValue(data['row_col_one_img'])
            self.show_scale.SetValue(data['show_scale'])
            self.row_col_img_unit.SetValue(data['row_col_img_unit'])
            self.gap.SetValue(data['gap'])
            self.magnifer_row_col.SetValue(data['magnifer_row_col'])
            self.output_scale.SetValue(data['output_scale'])
            self.img_resolution.SetValue(data['img_resolution'])
            self.magnifer_resolution.SetValue(data['magnifer_resolution'])
            self.magnifier_show_scale.SetValue(data['magnifier_show_scale'])
            self.line_width.SetValue(data['line_width'])
            self.magnifier_out_scale.SetValue(data['magnifier_out_scale'])
            self.title_font_size.SetValue(data['title_font_size'])
            self.box_position.SetSelection(data['box_position'])
            self.choice_normalized_size.SetSelection(data['choice_normalized_size'])
            self.choice_output.SetSelection(data['choice_output'])
            self.image_interp.SetSelection(data['image_interp'])
            self.Magnifier_format.SetSelection(data['Magnifier_format'])
            self.title_font.SetSelection(data['title_font'])
            self.parallel_sequential.SetValue(data['parallel_sequential'])
            self.parallel_to_sequential.SetValue(data['parallel_to_sequential'])
            self.auto_save_all.SetValue(data['auto_save_all'])
            self.move_file.SetValue(data['move_file'])
            self.img_vertical.SetValue(data['img_vertical'])
            self.one_img_vertical.SetValue(data['one_img_vertical'])
            self.img_unit_vertical.SetValue(data['img_unit_vertical'])
            self.magnifer_vertical.SetValue(data['magnifer_vertical'])
            self.show_original.SetValue(data['show_original'])
            self.show_magnifer.SetValue(data['show_magnifer'])
            self.title_show.SetValue(data['title_show'])
            self.auto_layout_check.SetValue(data['auto_layout_check'])
            self.one_img.SetValue(data['one_img'])
            self.onetitle.SetValue(data['onetitle'])
            self.show_custom_func.SetValue(data['show_custom_func']) #customfunc?
            self.show_box.SetValue(data['show_box'])
            self.show_box_in_crop.SetValue(data['show_box_in_crop'])
            self.select_img_box.SetValue(data['select_img_box'])
            self.title_auto.SetValue(data['title_auto'])
            self.title_exif.SetValue(data['title_exif'])
            self.title_show_parent.SetValue(data['title_show_parent'])
            self.title_show_prefix.SetValue(data['title_show_prefix'])
            self.title_show_name.SetValue(data['title_show_name'])
            self.title_show_suffix.SetValue(data['title_show_suffix'])
            self.title_down_up.SetValue(data['title_down_up'])
            self.save_format.SetSelection(data['save_format'])
            self.title_show_rename.SetValue(data.get('title_show_rename', False))
            self.ImgManager.load_exif_display_config(force_reload=True)
            self.customfunc_choice.SetSelection(data.get('customfunc_choice', 0))
            self.show_all_func.SetValue(data.get('show_all_func', False))
            self.show_all_func_layout.SetValue(data.get('show_all_func_layout', "2,2"))
            self.func_layout_vertical.SetValue(data.get('func_layout_vertical', False))
        self.apply_hotkeys(full_config.get('hotkeys', data.get('hotkeys', {})))

    def reset_configuration(self, event):
        json_path = Path(get_resource_path(str(Path("configs"))))
        default_config_path = str(json_path / "default_config.json")
        userdef_config_path = str(json_path / "userdef_config.json")
        self.load_configuration(event, config_name="userdef_config.json")
        shutil.copy(userdef_config_path, default_config_path)

    def add_custom_algorithm(self, event):
        algorithm_path = self.custom_algorithm_input.GetValue().strip()
        if not algorithm_path:
            event.Skip() if hasattr(event, "Skip") else None
            return

        source_path = Path(algorithm_path)
        if not source_path.exists():
            wx.MessageBox(f"Path does not exist: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
            return
        if not source_path.is_dir():
            wx.MessageBox(f"Path must be a folder: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
            return
        if not (source_path / "main.py").exists():
            wx.MessageBox(f"main.py file missing in algorithm folder: {algorithm_path}", "File Missing", wx.OK | wx.ICON_ERROR)
            return

        algorithm_name = source_path.name
        existing = [self.customfunc_choice.GetString(i) for i in range(self.customfunc_choice.GetCount())]
        if algorithm_name in existing:
            wx.MessageBox(f"Algorithm '{algorithm_name}' already exists!", "Duplicate Algorithm", wx.OK | wx.ICON_WARNING)
            return

        try:
            self.copy_algorithm_from_path(source_path, algorithm_name)
            self._clear_custom_algorithm_modules()
            self.refresh_algorithm_list()
            available_algorithms = get_available_algorithms()
            if algorithm_name in available_algorithms:
                self.customfunc_choice.SetSelection(available_algorithms.index(algorithm_name))
            self.custom_algorithm_input.SetValue("")
            self.Layout()
            wx.MessageBox(f"Algorithm '{algorithm_name}' added successfully!", "Add Success", wx.OK | wx.ICON_INFORMATION)
        except Exception as exc:
            wx.MessageBox(f"Failed to add algorithm: {exc}", "Add Failed", wx.OK | wx.ICON_ERROR)

    def copy_algorithm_from_path(self, source_path, algorithm_name):
        target_folder = Path(__file__).parent / "custom_func" / algorithm_name
        if target_folder.exists():
            shutil.rmtree(str(target_folder))
        shutil.copytree(str(source_path), str(target_folder))

    def _clear_custom_algorithm_modules(self):
        for module_name in (
            "mulimgviewer.src.custom_func.main",
            "custom_func.main",
            ".custom_func.main",
        ):
            if module_name in sys.modules:
                del sys.modules[module_name]

    def remove_custom_algorithm(self, event):
        selected_index = self.customfunc_choice.GetSelection()
        if selected_index == wx.NOT_FOUND:
            wx.MessageBox("Please select an algorithm to remove first!", "No Algorithm Selected", wx.OK | wx.ICON_WARNING)
            return

        selected_algorithm = self.customfunc_choice.GetString(selected_index)
        dlg = wx.MessageDialog(
            self,
            f"Are you sure you want to remove algorithm '{selected_algorithm}'?",
            "Confirm Removal",
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if dlg.ShowModal() == wx.ID_YES:
            try:
                self.remove_custom_algorithm_folder(selected_algorithm)
                self._clear_custom_algorithm_modules()
                self.refresh_algorithm_list()
                wx.MessageBox(f"Algorithm '{selected_algorithm}' removed successfully!", "Remove Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as exc:
                wx.MessageBox(f"Failed to remove algorithm: {exc}", "Remove Failed", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def remove_custom_algorithm_folder(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        if algorithm_folder.exists():
            shutil.rmtree(str(algorithm_folder))

    def create_custom_algorithm_template(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        desktop_algorithm_folder = Path.home() / "Desktop" / algorithm_name
        if desktop_algorithm_folder.exists() and (desktop_algorithm_folder / "main.py").exists():
            try:
                if algorithm_folder.exists():
                    shutil.rmtree(str(algorithm_folder))
                shutil.copytree(str(desktop_algorithm_folder), str(algorithm_folder))
                return
            except Exception:
                pass
        if not algorithm_folder.exists():
            os.makedirs(str(algorithm_folder))
        template_content = f"""'''
{algorithm_name} Algorithm
Custom algorithm - Implement your image processing logic here
'''
from PIL import Image
from pathlib import Path
import os

def custom_process_img(img):
    \"\"\"
    Custom image processing function
    input: image(pillow)
    output: image(pillow)

    Implement your image processing algorithm here
    Examples:
    - img = img.convert('L')  # Convert to grayscale
    - img = img.transpose(Image.FLIP_LEFT_RIGHT)  # Horizontal flip
    \"\"\"
    return img

def main(img_list, save_path, name_list=None, algorithm_name="{algorithm_name}"):
    \"\"\"
    Batch process image list
    \"\"\"
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        save_path = Path(save_path) / "processing_function" / algorithm_name
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        img = custom_process_img(img)

        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list) and i < len(name_list):
                img_path = save_path / name_list[i]
            else:
                img_path = save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
"""
        template_path = algorithm_folder / "main.py"
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template_content)

    def refresh_algorithm_list(self):
        try:
            self._clear_custom_algorithm_modules()
            available_algorithms = get_available_algorithms()
            current_selection = self.customfunc_choice.GetSelection()
            current_algorithm = ""
            if current_selection != wx.NOT_FOUND:
                current_algorithm = self.customfunc_choice.GetString(current_selection)
            self.customfunc_choice.Clear()
            for algorithm in available_algorithms:
                self.customfunc_choice.Append(algorithm)
            if current_algorithm and current_algorithm in available_algorithms:
                self.customfunc_choice.SetSelection(available_algorithms.index(current_algorithm))
            elif available_algorithms:
                self.customfunc_choice.SetSelection(0)
        except Exception:
            pass

    def on_show_all_func_changed(self, event):
        if self.show_all_func.GetValue():
            self.show_custom_func.SetValue(False)
        self._invalidate_render_cache()

    def on_show_custom_func_changed(self, event):
        if self.show_custom_func.GetValue():
            self.show_all_func.SetValue(False)
        self._invalidate_render_cache()

    #b3 修改1：next_img 和 last_img —— timer 播放时跳过 show_img_init    b5
    def next_img(self, event):
        if self.shared_config.video_mode and self.shared_config.is_playing and not getattr(self, "_from_timer", False):
            self.shared_config.play_direction = 1
            self.last_direction = self.shared_config.play_direction
            return
        if (not self.shared_config.video_mode and
                self.shared_config.is_playing and
                not getattr(self, "_from_timer", False)):
            self.shared_config.play_direction = 1
            self.last_direction = 1
            return

        max_batch_idx = self.ImgManager.max_action_num - 1
        if self.shared_config.batch_idx >= max_batch_idx:
            if getattr(self.shared_config, "is_playing", False):
                self.shared_config.is_playing = False
                try:
                    self.play_timer.Stop()
                except Exception:
                    pass
                try:
                    self.right_arrow_button1.SetLabel("▶")
                except Exception:
                    pass
                self.shared_config.play_direction = 1
                self.last_direction = 1
            return

        if self.shared_config.video_mode:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = 1
            self.last_direction = self.shared_config.play_direction
            if self.shared_config.batch_idx < int(self.ImgManager.img_num) - 1:
                self.shared_config.batch_idx += 1

            # ★ 修改：异步更新缓存，让UI立即响应而不是阻塞
            wx.CallAfter(self.video_manager.update_cache)

        if getattr(self.ImgManager, "img_count", 0) < int(self.ImgManager.img_num) - 1:
            self.ImgManager.add()

        self.shared_config.batch_idx = min(self.shared_config.batch_idx, self.ImgManager.max_action_num - 1)
        if not self.shared_config.video_mode:
            self.shared_config.batch_idx = min(self.ImgManager.action_count, self.ImgManager.max_action_num - 1)

        if not getattr(self, "_from_timer", False):
            self.show_img_init()

        self.show_img()
        self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def _setup_img_panel(self):
        # Prevent white-background flicker during repaint
        if getattr(self, "_img_panel_ready", False):
            return
        pnl = self.img_panel
        pnl.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        pnl.SetDoubleBuffered(True)
        pnl.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self._img_panel_ready = True

    def _set_placeholder_visible(self, visible: bool):
        if not hasattr(self, "m_staticText1") or not self.m_staticText1:
            return
        if getattr(self, '_placeholder_visible', None) == bool(visible):
            return
        try:
            if visible:
                self.m_staticText1.Show()
            else:
                self.m_staticText1.Hide()
            self.scrolledWindow_img.GetSizer().Layout()
            self.scrolledWindow_img.Layout()
            self._placeholder_visible = bool(visible)
        except Exception:
            pass

    def _reset_image_view_origin(self):
        try:
            self.position = [0, 0]
            self.scrolledWindow_img.Scroll(0, 0)
        except Exception:
            pass

    def _ensure_img_bindings(self):
        if not getattr(self, "img_last", None):
            return
        if getattr(self, '_img_bindings_target', None) is self.img_last:
            return
        self.img_last.Bind(wx.EVT_LEFT_DOWN, self.img_left_click)
        self.img_last.Bind(wx.EVT_LEFT_DCLICK, self.img_left_dclick)
        self.img_last.Bind(wx.EVT_MOTION, self.img_left_move)
        self.img_last.Bind(wx.EVT_LEFT_UP, self.img_left_release)
        self.img_last.Bind(wx.EVT_RIGHT_DOWN, self.img_right_click)
        self.img_last.Bind(wx.EVT_MOUSEWHEEL, self.img_wheel)
        self.img_last.Bind(wx.EVT_KEY_DOWN, self.key_down_detect)
        self.img_last.Bind(wx.EVT_KEY_UP, self.key_up_detect)
        self._img_bindings_target = self.img_last

    def disable_accel(self, event):
        self.SetAcceleratorTable(wx.NullAcceleratorTable)
        event.Skip()

    def enable_accel(self, event):
        self.SetAcceleratorTable(self.acceltbl)
        event.Skip()
