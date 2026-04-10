import platform
import threading
from pathlib import Path
import ffmpeg,os,time,math
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
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
import json
import shutil
import copy


class PerformanceMonitor:
    """Lightweight collector for extraction/stitch/render metrics."""

    def __init__(self, eval_batch_window=15, eval_time_window=10.0):
        self.extract_history = deque(maxlen=60)
        self.stitch_history = deque(maxlen=60)
        self.render_history = deque(maxlen=30)
        self.buffer_history = deque(maxlen=60)
        self.eval_batch_window = max(1, int(eval_batch_window))
        self.eval_time_window = max(1.0, float(eval_time_window))
        self.processed_batches = 0
        self.last_eval_batch = 0
        self.last_eval_time = 0.0
        self.last_render_timestamp = None

    def record_extract(self, duration):
        if duration is not None and duration >= 0:
            self.extract_history.append(float(duration))

    def record_stitch(self, duration):
        if duration is not None and duration >= 0:
            self.stitch_history.append(float(duration))

    def record_render_interval(self, interval):
        if interval is not None and interval > 0:
            self.render_history.append(float(interval))

    def record_buffer_depth(self, depth):
        if depth is not None and depth >= 0:
            self.buffer_history.append(int(depth))

    def mark_processed_batch(self):
        self.processed_batches += 1

    def should_evaluate(self):
        now = time.time()
        if self.processed_batches - self.last_eval_batch >= self.eval_batch_window:
            return True
        if now - self.last_eval_time >= self.eval_time_window:
            return True
        return False

    def mark_evaluated(self):
        self.last_eval_batch = self.processed_batches
        self.last_eval_time = time.time()

    def reset_render_clock(self):
        self.last_render_timestamp = None

    def push_render_event(self):
        now = time.time()
        last = self.last_render_timestamp
        if last is not None:
            interval = now - last
            if interval > 0:
                self.record_render_interval(interval)
        self.last_render_timestamp = now

    def _avg(self, data):
        if not data:
            return None
        return sum(data) / len(data)

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

class SharedConfig:
    def __init__(self):
        '''Variables shared by MulimgViewer and VideoManager.'''
        self.cache_num = 2 #Number of caches
        self.skip_frames = 0 #Number of frames to skip
        self.thread = 4 #Number of threads
        self.video_mode = False #Video mode
        self.interval = 1.0 #Playback interval
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
        self.debug_video = False #Video mode debug output
        self.debug_image = False #Image mode debug output
        self.debug_thread = False #Thread debug output
        self.interval_recommend = None #Playback interval recommendation
        self.video_last_message = "" # Most recent video error/diagnostic information

class VideoManager:
    def __init__(self, owner, shared_config=None, ImgManager=None):
        self._owner = weakref.ref(owner)
        self.shared_config = shared_config
        self.ImgManager = ImgManager
        self.cache_dir = Path("Video_frames")
        self.perf_monitor = PerformanceMonitor()
        self.executor = None
        self.stitch_executor = None
        self._stitch_lock = threading.Lock()
        self._meta_cache = {}
        self._pending_extract = {}
        self._pending_stitch_async = 0
        self._pending_lock = threading.Lock()
        self._last_batch = None
        self._total_threads = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        # Initial thread allocation for frame splitting/merging: at least one thread for each
        default_extract = max(1, self._total_threads - 1)
        default_stitch = max(1, self._total_threads - default_extract)
        self._extract_threads = default_extract
        self._stitch_threads = default_stitch
        self._success_streak = 0
        self._failure_streak = 0
        self._cooldown_deadline = 0.0
        self._reported_extract_threads = False
        self._reported_stitch_threads = False
        self._ffmpeg_bin = None
        self._ffprobe_bin = None
        self._initialize_thread_pools()

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
                ui.SetStatusText_(["-1", "-1", f"***{msg}***", "-1"])
            except Exception:
                pass

    def _clear_video_status(self):
        self._set_video_message("")

    def _initialize_thread_pools(self):
        if self.executor:
            self.executor.shutdown(wait=False)
        if self.stitch_executor:
            self.stitch_executor.shutdown(wait=False)
        self.executor = ThreadPoolExecutor(max_workers=self._extract_threads)
        self.stitch_executor = ThreadPoolExecutor(max_workers=self._stitch_threads)
        self._reported_extract_threads = False
        self._reported_stitch_threads = False

    def _reset_for_new_selection(self):
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

        with self._pending_lock:
            for fut in self._pending_extract.values():
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
        total_budget = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        extract_threads = max(1, int(extract_threads))
        stitch_threads = max(1, int(stitch_threads))
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
            return

        self._extract_threads = extract_threads
        self._stitch_threads = stitch_threads
        self._initialize_thread_pools()
        self._success_streak = 0
        self._failure_streak = 0

    def _enforce_thread_budget(self):
        total_budget = max(2, int(getattr(self.shared_config, "thread", 2) or 2))
        self._total_threads = total_budget
        current_total = self._extract_threads + self._stitch_threads

        if current_total > total_budget:
            # Due to budget cuts, we need to reduce the number of threads.
            excess = current_total - total_budget
            if self._extract_threads > self._stitch_threads:
                self._extract_threads = max(1, self._extract_threads - excess)
            else:
                self._stitch_threads = max(1, self._stitch_threads - excess)
        elif current_total < total_budget:
            # Increase the budget, prioritizing the addition of frame-splitting threads
            available = total_budget - current_total
            self._extract_threads += available

        self._apply_thread_plan(self._extract_threads, self._stitch_threads)

    def _apply_interval_recommendation(self, recommended):
        ui = self._ui()
        try:
            current = float(getattr(self.shared_config, "interval", recommended) or recommended)
            if abs(current - recommended) <= 1e-3:
                return
            self.shared_config.interval = recommended
            if ui:
                ui.m_textCtrl28.SetValue(f"{recommended:.3f}")
                if getattr(ui.shared_config, "is_playing", False):
                    ui.play_timer.Start(int(recommended * 1000), oneShot=False)
        except Exception as exc:
            pass

    def _compute_buffer_depth(self):
        cache = getattr(self.shared_config, "cache_img", [])
        if not cache:
            return 0
        current = int(getattr(self.shared_config, "batch_idx", 0))
        depth = 0
        for idx in range(current, len(cache)):
            if cache[idx] is None:
                break
            depth += 1
        return depth

    def _record_buffer_depth(self):
        depth = self._compute_buffer_depth()
        self.perf_monitor.record_buffer_depth(depth)

    def _mark_batch_processed(self):
        self.perf_monitor.mark_processed_batch()
        self._record_buffer_depth()
        self._maybe_evaluate_performance()

    def _maybe_evaluate_performance(self):
        if not self.perf_monitor.should_evaluate():
            return

        extract_avg = self.perf_monitor.extract_avg()
        stitch_avg = self.perf_monitor.stitch_avg()
        render_min = self.perf_monitor.render_min()
        buffer_min = self.perf_monitor.buffer_min()
        frame_interval = max(0.1, float(getattr(self.shared_config, "interval", 1.0) or 1.0))

        self.perf_monitor.mark_evaluated()

        if extract_avg is None or stitch_avg is None:
            return

        # Available thread budget
        total_budget = max(2, int(getattr(self.shared_config, "thread", 2) or 2))

        # Current thread configuration
        extract_threads = max(1, self._extract_threads)
        stitch_threads = max(1, self._stitch_threads)

        # Thread demand estimation
        required_extract = math.ceil(extract_avg / frame_interval)
        required_stitch = math.ceil(stitch_avg / frame_interval)

        # Rendering decision: If actual data is available, use the actual minimum value; otherwise, use the estimated value.
        if render_min is not None:
            render_value = render_min
            render_met = render_value <= frame_interval
        else:
            estimated = max(extract_avg / extract_threads, stitch_avg / stitch_threads)
            render_value = estimated
            render_met = estimated <= frame_interval

        # Buffer decision
        cache_target = max(1, int(getattr(self.shared_config, "cache_num", 1)) - 1)
        if cache_target <= 0:
            cache_target = 1
        buffer_ok = (buffer_min is None) or (buffer_min >= cache_target)

        # Thread load estimation (based on the number of pending tasks)
        with self._pending_lock:
            pending_extract = len(self._pending_extract)
            pending_stitch = max(0, self._pending_stitch_async)
        extract_load = (pending_extract + extract_threads) / max(1, extract_threads)
        stitch_load = (pending_stitch + stitch_threads) / max(1, stitch_threads)

        now = time.time()
        cooldown_active = now < self._cooldown_deadline

        success = render_met and buffer_ok and extract_load <= 1.1 and stitch_load <= 1.1
        if success:
            self._success_streak += 1
            self._failure_streak = 0
        else:
            self._failure_streak += 1
            self._success_streak = 0

        # Ensure that the thread budget is not less than the minimum required value
        required_extract = max(1, required_extract)
        required_stitch = max(1, required_stitch)

        # Record the recommended frame interval
        recommended = None
        if total_budget < required_extract + required_stitch:
            best_extract = max(1, total_budget - 1)
            best_stitch = max(1, total_budget - best_extract)
            recommended = max(
                extract_avg / max(1, best_extract),
                stitch_avg / max(1, best_stitch)
            )
        elif not render_met:
            # Even if the thread budget is sufficient, recommendations will still be provided if the actual rendering performance falls short of the target.
            recommended = max(
                render_value,
                extract_avg / max(1, extract_threads),
                stitch_avg / max(1, stitch_threads)
            )

        if recommended is not None:
            recommended = round(max(recommended, frame_interval), 3)
            self.shared_config.interval_recommend = recommended
            self._apply_interval_recommendation(recommended)
        else:
            self.shared_config.interval_recommend = None

        # During the cooling-off period, only recommendations will be updated; no adjustments will be made to the thread.

        if cooldown_active:
            return

        # Multiple failures -> Try adding a thread
        if self._failure_streak >= 2:
            added = False
            if extract_threads < required_extract and extract_threads + stitch_threads < total_budget:
                new_extract = min(required_extract, total_budget - stitch_threads)
                self._apply_thread_plan(new_extract, stitch_threads)
                added = True
            if not added and stitch_threads < required_stitch and self._extract_threads + self._stitch_threads < total_budget:
                new_stitch = min(required_stitch, total_budget - extract_threads)
                self._apply_thread_plan(extract_threads, new_stitch)
                added = True
            if not added and extract_threads + stitch_threads < total_budget:
                # If there is no clear gap, assign 1 lane to the side with higher traffic volume
                if extract_load >= stitch_load and extract_threads + stitch_threads + 1 <= total_budget:
                    self._apply_thread_plan(extract_threads + 1, stitch_threads)
                elif stitch_load > extract_load and extract_threads + stitch_threads + 1 <= total_budget:
                    self._apply_thread_plan(extract_threads, stitch_threads + 1)
            if added or self._failure_streak >= 2:
                self._cooldown_deadline = time.time() + self.perf_monitor.eval_time_window
                self._failure_streak = 0
                self._success_streak = 0
            return

        # Reached the limit multiple times -> Try reducing the number of threads
        if self._success_streak >= 3:
            new_extract = extract_threads
            new_stitch = stitch_threads
            if extract_threads > required_extract and extract_load <= 0.8:
                new_extract = max(required_extract, extract_threads - 1)
            elif stitch_threads > required_stitch and stitch_load <= 0.8:
                new_stitch = max(required_stitch, stitch_threads - 1)

            if new_extract != extract_threads or new_stitch != stitch_threads:
                self._apply_thread_plan(new_extract, new_stitch)
                self._cooldown_deadline = time.time() + self.perf_monitor.eval_time_window
            self._success_streak = 0
            self._failure_streak = 0

    def _debug_video(self, message):
        if getattr(self.shared_config, "debug_video", False):
            print(message)

    def _resolve_binary(self, tool_name):
        if tool_name == "ffmpeg" and self._ffmpeg_bin and os.path.isabs(self._ffmpeg_bin):
            return self._ffmpeg_bin
        if tool_name == "ffprobe" and self._ffprobe_bin and os.path.isabs(self._ffprobe_bin):
            return self._ffprobe_bin

        resolved = shutil.which(tool_name)
        if not resolved:
            raise RuntimeError(f"{tool_name} not found in PATH")

        if tool_name == "ffmpeg":
            self._ffmpeg_bin = resolved
        elif tool_name == "ffprobe":
            self._ffprobe_bin = resolved
        return resolved

    def calc_max_extractable_frames_single(self, video_path):
        '''Using FFmpeg to retrieve video information, replacing cv2.VideoCapture'''
        step = self.shared_config.skip_frames + 1
        fps, total = self._get_meta(video_path)
        viewable = max(1, (total + step - 1) // step) if total > 0 else 1
        self.shared_config.video_fps_list.append(fps)
        self.shared_config.video_num_list.append(viewable)

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
            ffprobe_bin = self._resolve_binary("ffprobe")
            cp = subprocess.run(
                [
                    ffprobe_bin,
                    "-v", "error",
                    "-print_format", "json",
                    "-show_streams",
                    "-show_format",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode != 0:
                raise RuntimeError(f"ffprobe failed (code={cp.returncode}): {cp.stderr.strip()}")
            try:
                p = json.loads(cp.stdout or "{}")
            except Exception as ex:
                raise RuntimeError(f"ffprobe json parse failed: {ex}")

        streams = p.get("streams", []) if isinstance(p, dict) else []
        vs = next((s for s in streams if s.get('codec_type') == 'video'), None)
        if vs is None:
            raise RuntimeError("no video stream found")

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
                ffprobe_bin = self._resolve_binary("ffprobe")
                cp = subprocess.run(
                    [
                        ffprobe_bin,
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-count_frames",
                        "-show_entries", "stream=nb_read_frames",
                        "-of", "default=nw=1:nk=1",
                        str(video_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
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
        if not getattr(self.shared_config, "video_mode", False):
            return
        if not getattr(self.shared_config, "video_path", None):
            self._set_video_status("Video path empty: please reselect input")
            return

        b = int(getattr(self.shared_config, "batch_idx", 0))
        R = max(1, int(getattr(self.shared_config, "cache_num", 1)))
        k = max(1, int(getattr(self.shared_config, "count_per_action", 1)))

        last_batch = getattr(self, "_last_batch", None)
        sequential_forward = (last_batch is not None and b == last_batch + 1)
        force_rebuild_window = not sequential_forward

        if not getattr(self.shared_config, "video_fps_list", []) or not getattr(self.shared_config, "video_num_list", []):
            for vp in getattr(self.shared_config, "real_video_path", []):
                self.calc_max_extractable_frames_single(vp)

        parallel_to_seq = bool(getattr(self.shared_config, "parallel_to_sequential", False))
        video_paths = getattr(self.shared_config, "video_path", [])
        multi_video = (not parallel_to_seq and len(video_paths) > 1)

        if multi_video:
            self._update_cache_multi_video(
                global_batch=b,
                window_radius=R,
                count_per_action=k,
                force_rebuild=force_rebuild_window
            )
            self._last_batch = b
            self._mark_batch_processed()
            return

        base_global = 0
        video_idx = 0
        local_b = 0

        if parallel_to_seq:
            cum = 0
            for i in range(len(self.shared_config.video_path)):
                n_i = int(self.shared_config.video_num_list[i])
                max_b_i = (n_i + k - 1) // k if n_i > 0 else 1
                if b < cum + max_b_i:
                    video_idx = i
                    local_b = b - cum
                    base_global = cum
                    break

            self.current_active_video_idx = video_idx
        else:
            video_idx = 0
            n0 = int(self.shared_config.video_num_list[video_idx])
            max_b_0 = (n0 + k - 1) // k if n0 > 0 else 1
            local_b = b if b < max_b_0 else (max_b_0 - 1)
            base_global = 0

        n = int(self.shared_config.video_num_list[video_idx])
        max_batch = (n + k - 1) // k if n > 0 else 1
        if max_batch <= 0:
            self._set_video_status(f"Video batch invalid: n={n}, k={k}")
            return

        extract_end = min(local_b + R, max_batch - 1)
        stitch_end = min(local_b + max(R - 1, 0), max_batch - 1)
        prev_guard = R
        window_start = max(0, local_b - prev_guard)
        window_end = extract_end
        extract_threads = getattr(self.executor, "_max_workers", 0)
        stitch_threads = getattr(self.stitch_executor, "_max_workers", 0)
        if not hasattr(self.shared_config, "cache_img") or self.shared_config.cache_img is None:
            self.shared_config.cache_img = []
        required_len = (base_global + window_end + 1) if parallel_to_seq else (window_end + 1)
        if len(self.shared_config.cache_img) < required_len:
            self.shared_config.cache_img.extend([None] * (required_len - len(self.shared_config.cache_img)))

        if force_rebuild_window:
            max_clear = stitch_end
            for t in range(window_start, max_clear + 1):
                global_t = (base_global + t) if parallel_to_seq else t
                if 0 <= global_t < len(self.shared_config.cache_img):
                    self.shared_config.cache_img[global_t] = None

        for t in range(window_start, local_b):
            self._ensure_batch_extracted(video_idx, t, wait=True)
            if t <= stitch_end:
                global_t = (base_global + t) if parallel_to_seq else t
                if self.shared_config.cache_img[global_t] is None:
                    self._stitch_batch(video_idx, t, global_t)

        global_local = (base_global + local_b) if parallel_to_seq else local_b
        self._ensure_batch_extracted(video_idx, local_b, wait=True)
        if local_b <= stitch_end:
            if force_rebuild_window or self.shared_config.cache_img[global_local] is None:
                self._stitch_batch(video_idx, local_b, global_local)

        for t in range(local_b + 1, extract_end + 1):
            global_t = (base_global + t) if parallel_to_seq else t
            async_prefetch = (t <= stitch_end)
            wait_for_extract = not async_prefetch
            result = self._ensure_batch_extracted(video_idx, t, wait=wait_for_extract)
            if async_prefetch:
                if self._should_schedule_stitch(global_t):
                    if isinstance(result, Future):
                        result.add_done_callback(partial(self._post_extract_stitch, video_idx, t, global_t))
                    else:
                        self._schedule_stitch(video_idx, t, global_t)

        start_tuple = self._batch_range(n, k, window_start)
        end_tuple = self._batch_range(n, k, window_end)
        keep_start_idx = start_tuple[0] if start_tuple and start_tuple[0] is not None else 0
        keep_end_idx = (end_tuple[1] + 1) if end_tuple and end_tuple[1] is not None else keep_start_idx
        self._cleanup_out_of_range_cache(video_idx, keep_start_idx, keep_end_idx)
        self._debug_video(f"[CacheSchedule] done batch={b} window=[{window_start},{window_end}] extract_threads={extract_threads} stitch_threads={stitch_threads} keep_frame_range=[{keep_start_idx},{keep_end_idx})")

        self._last_batch = b
        self._mark_batch_processed()

    def _update_cache_multi_video(self, global_batch: int, window_radius: int, count_per_action: int, force_rebuild: bool):
        video_paths = getattr(self.shared_config, "video_path", [])
        num_videos = len(video_paths)
        if num_videos == 0:
            return

        max_batches = []
        video_frame_counts = []
        for vid in range(num_videos):
            n = int(self.shared_config.video_num_list[vid]) if vid < len(self.shared_config.video_num_list) else 0
            video_frame_counts.append(n)
            if n > 0:
                max_batches.append((n + count_per_action - 1) // count_per_action)
            else:
                max_batches.append(0)

        global_max_batch = max(max_batches) if max_batches else 0
        if global_max_batch <= 0:
            self._set_video_status("Video batch invalid: no available batches")
            return

        global_b = global_batch if global_batch < global_max_batch else (global_max_batch - 1)
        window_start = max(0, global_b - window_radius)
        window_end = min(global_max_batch - 1, global_b + window_radius)
        if window_end < window_start:
            window_end = window_start

        stitch_limit = min(global_b + max(window_radius - 1, 0), global_max_batch - 1)

        cache = getattr(self.shared_config, "cache_img", None)
        if cache is None:
            self.shared_config.cache_img = cache = []
        if len(cache) <= window_end:
            cache.extend([None] * (window_end + 1 - len(cache)))

        if force_rebuild:
            for t in range(window_start, stitch_limit + 1):
                if t < len(cache):
                    cache[t] = None

        extract_threads = getattr(self.executor, "_max_workers", 0)
        stitch_threads = getattr(self.stitch_executor, "_max_workers", 0)

        for t in range(window_start, window_end + 1):
            for vid, max_b in enumerate(max_batches):
                if max_b <= 0 or t >= max_b:
                    continue
                wait_for_extract = (t <= stitch_limit)
                self._ensure_batch_extracted(vid, t, wait=wait_for_extract)
            if t <= stitch_limit and cache[t] is None:
                self._stitch_batch_multi(t)

        for vid, max_b in enumerate(max_batches):
            if max_b <= 0:
                continue
            local_b = global_b if global_b < max_b else (max_b - 1)
            local_start = max(0, local_b - window_radius)
            local_end = min(max_b - 1, local_b + window_radius)
            if local_end < local_start:
                local_end = local_start
            start_tuple = self._batch_range(video_frame_counts[vid], count_per_action, local_start)
            end_tuple = self._batch_range(video_frame_counts[vid], count_per_action, local_end)
            keep_start_idx = start_tuple[0] if start_tuple and start_tuple[0] is not None else 0
            keep_end_idx = (end_tuple[1] + 1) if end_tuple and end_tuple[1] is not None else keep_start_idx
            self._cleanup_out_of_range_cache(vid, keep_start_idx, keep_end_idx)

        self._debug_video(
            f"[CacheSchedule](multi-video) done batch={global_batch} window=[{window_start},{window_end}] "
            f"extract_threads={extract_threads} stitch_threads={stitch_threads}"
        )

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
        current_video_dirs = set(self.shared_config.video_path)

        for item in self.cache_dir.iterdir():
            if item.is_dir() and str(item) not in current_video_dirs:
                shutil.rmtree(str(item))

    def _filename_converter(self, input_value, video_idx):
        '''Bidirectional conversion: logical index <-> timestamp/frame filename.'''
        if isinstance(input_value, int):
            step = self.shared_config.skip_frames + 1
            phys_idx = input_value * step
            fps = float(self.shared_config.video_fps_list[video_idx] or 0)
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

    def _save_frame(self, video_path, frame_start, frame_end, video_idx, max_retries=1):
        '''Extract and save frames with ffmpeg.'''
        step = self.shared_config.skip_frames + 1
        start_time = time.time()
        cache_dir = self.shared_config.video_path[video_idx]
        target_size = 256
        enable_debug_scale = bool(getattr(self.shared_config, "debug_video", False))
        last_error = None
        has_ffmpeg_input = callable(getattr(ffmpeg, "input", None))

        def list_missing(a, b):
            miss = []
            for idx in range(a, b + 1):
                dst = os.path.join(cache_dir, self._filename_converter(idx, video_idx))
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

        def extract_ranges(ranges):
            nonlocal last_error
            for s, e in ranges:
                if not has_ffmpeg_input:
                    try:
                        ffmpeg_bin = self._resolve_binary("ffmpeg")
                    except Exception as ex:
                        last_error = str(ex)
                        return
                    fps = float(self.shared_config.video_fps_list[video_idx] or 0)
                    fps_safe = fps if fps > 0 else 25.0
                    for idx in range(s, e + 1):
                        dst = os.path.join(cache_dir, self._filename_converter(idx, video_idx))
                        if os.path.exists(dst) and os.path.getsize(dst) > 0:
                            continue
                        physical_frame = idx * step
                        timestamp = physical_frame / fps_safe
                        cmd = [
                            ffmpeg_bin,
                            "-v", "error",
                            "-ss", f"{timestamp:.6f}",
                            "-i", str(video_path),
                            "-frames:v", "1",
                            "-q:v", "6",
                            "-y", dst,
                        ]
                        try:
                            cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
                            if cp.returncode != 0:
                                last_error = (cp.stderr or cp.stdout or "").strip() or f"ffmpeg exit code {cp.returncode}"
                        except Exception as ex:
                            last_error = str(ex)
                    continue

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

                suffix = f"{os.getpid()}_{threading.get_ident()}_{int(time.time()*1000)}"
                tmp_tpl = os.path.join(cache_dir, f'__tmp_{video_idx}_{suffix}_%d.jpeg')

                try:
                    stream = (
                        ffmpeg
                        .input(str(video_path))
                        .filter('select', sel)
                    )
                    if enable_debug_scale:
                        stream = stream.filter('scale', target_size, -1, force_original_aspect_ratio='decrease')

                    (
                        stream
                        .output(tmp_tpl, vsync='vfr', **{'q:v': 6}, start_number=s)
                        .global_args('-threads', '1', '-hide_banner', '-loglevel', 'error')
                        .overwrite_output()
                        .run(quiet=True)
                    )
                except Exception as ex:
                    last_error = str(ex)
                    self._debug_video(f"[Extract] error: ffmpeg processing failed, reason={ex}")
                tmp_prefix = f'__tmp_{video_idx}_{suffix}_'
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
                    dst = os.path.join(cache_dir, self._filename_converter(idx, video_idx))
                    try:
                        os.replace(src, dst)
                    except Exception:
                        try:
                            os.remove(src)
                        except Exception:
                            pass

        missing = list_missing(frame_start, frame_end)
        if missing:
            extract_ranges(chunks(missing))

        attempt = 0
        while attempt < max_retries:
            missing = list_missing(frame_start, frame_end)
            if not missing:
                break
            extract_ranges(chunks(missing))
            attempt += 1

        missing = list_missing(frame_start, frame_end)
        if missing:
            detail = f"video={video_idx}, miss={missing[:5]}"
            if last_error:
                detail = f"{detail}, err={last_error}"
            self._debug_video(f"[Extract] final failure {detail}")
            self._set_video_status(f"Video extract failed: {detail}")

        try:
            for name in os.listdir(cache_dir):
                if name.startswith(f'__tmp_{video_idx}_') and name.endswith('.jpeg'):
                    try: os.remove(os.path.join(cache_dir, name))
                    except Exception: pass
        except Exception:
            pass

        end_time = time.time()
        self.perf_monitor.record_extract(end_time - start_time)

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
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
        if ffmpeg_bin is None or ffprobe_bin is None:
            self._set_video_status("Error: ffmpeg/ffprobe not found in PATH")
            self.shared_config.video_path = []
            return []
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
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
                wx.CallAfter(ui.show_img_init)
                self.ImgManager.set_action_count(0)
                wx.CallAfter(ui.show_img)
                if hasattr(ui, "_reset_image_view_origin"):
                    wx.CallAfter(ui._reset_image_view_origin)
        return self.shared_config.real_video_path

    def _collect_batch_frame_paths(self, video_idx: int, batch_idx: int):
        if video_idx >= len(getattr(self.shared_config, "video_path", [])):
            return []
        n = int(self.shared_config.video_num_list[video_idx]) if video_idx < len(self.shared_config.video_num_list) else 0
        k = max(1, int(getattr(self.shared_config, "count_per_action", 1)))
        if n <= 0:
            return []
        max_batch = (n + k - 1) // k if n > 0 else 0
        if max_batch <= 0:
            return []
        clamped_idx = batch_idx if batch_idx < max_batch else (max_batch - 1)
        cs, ce = self._batch_range(n, k, clamped_idx)
        if cs is None or ce is None or cs > ce:
            return []

        v_dir = self.shared_config.video_path[video_idx]
        frames = []
        for idx in range(cs, ce + 1):
            fn = self._filename_converter(idx, video_idx)
            p = os.path.join(v_dir, fn)
            if os.path.exists(p):
                frames.append(p)
        return frames

    def _should_schedule_stitch(self, global_idx: int):
        cache = getattr(self.shared_config, "cache_img", None)
        if cache is None:
            return False
        if global_idx < 0 or global_idx >= len(cache):
            return False
        return cache[global_idx] is None

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

        if pil_img is not None and flag == 0:
            self.shared_config.cache_img[global_b] = pil_img

        ok = self.shared_config.cache_img[global_b] is not None
        if not ok:
            self._set_video_status(f"Video stitch empty: batch={global_b}, flag={flag}")
        self._debug_video(
            f"[Stitch] done (multi-video) thread={threading.current_thread().name} batch={global_b} success={ok}"
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
            self.shared_config.cache_img[global_b] = pil_img

        ok = self.shared_config.cache_img[global_b] is not None
        if not ok:
            self._set_video_status(f"Video stitch empty: video={video_idx}, batch={global_b}, flag={flag}")
        self._debug_video(
            f"[Stitch] done thread={threading.current_thread().name} video={video_idx} batch={global_b} success={ok} frames={flist}"
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

    def _list_missing_range(self, video_idx, a, b):
        if a is None or b is None or a > b:
            return []
        cache_dir = os.path.abspath(self.shared_config.video_path[video_idx])
        miss = []
        for idx in range(a, b + 1):
            filename = self._filename_converter(idx, video_idx)
            path = os.path.join(cache_dir, filename)
            ok = os.path.exists(path)
            sz = (os.path.getsize(path) if ok else -1)
            if not ok or sz <= 0:
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
        self._image_stitch_lock = threading.Lock()  # Lock for image stitching state
        self.shift_pressed=False
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self._is_closing = False
        self._parallel_switch_dirty = False

        _key_map = {"up": wx.WXK_UP, "down": wx.WXK_DOWN, "left": wx.WXK_LEFT,
                     "right": wx.WXK_RIGHT, "delete": wx.WXK_DELETE}
        for c in "abcdefghijklmnopqrstuvwxyz":
            _key_map[c] = ord(c.upper())
        try:
            _cfg_path = str(Path(get_resource_path(str(Path("configs")))) / "default_config.json")
            with open(_cfg_path, 'r', encoding='utf-8') as f:
                _hk = json.load(f).get('hotkeys', {})
        except Exception:
            _hk = {}
        _actions = {"move_up": self.menu_up, "move_down": self.menu_down,
                     "move_left": self.menu_left, "move_right": self.menu_right,
                     "delete_box": self.menu_delete_box}
        _defaults = {"move_up": "up", "move_down": "down", "move_left": "left",
                      "move_right": "right", "delete_box": "delete"}
        self.acceltbl = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, _key_map[_hk.get(k, _defaults[k]).strip().lower()], m.GetId())
            for k, m in _actions.items()
            if _hk.get(k, _defaults[k]).strip().lower() in _key_map
        ])
        self.SetAcceleratorTable(self.acceltbl)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
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
            except Exception:
                pass
        self.load_configuration( None , config_name="default_config.json")
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_right_click)
        self.custom_algorithms = []
        # self.refresh_algorithm_list()
        self._bind_settings_wheel_guard()

        def _bind_accel_guard_recursive(parent):
            for child in parent.GetChildren():
                if isinstance(child, (wx.TextCtrl, wx.SpinCtrl, wx.SpinCtrlDouble)):
                    child.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                    child.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
                _bind_accel_guard_recursive(child)
        _bind_accel_guard_recursive(self)

    def _rebuild_threads(self, n):
        n = max(int(n), 1)
        vm = self.video_manager

        if getattr(vm, "executor", None):
            vm.executor.shutdown(wait=False)
        vm.executor = ThreadPoolExecutor(max_workers=n)

        desired_stitch = 2 if n >= 2 else 1
        if getattr(vm, "stitch_executor", None):
            if vm.stitch_executor._max_workers != desired_stitch:
                vm.stitch_executor.shutdown(wait=False)
                vm.stitch_executor = ThreadPoolExecutor(max_workers=desired_stitch)
        else:
            vm.stitch_executor = ThreadPoolExecutor(max_workers=desired_stitch)

    def on_cache_num_change(self, event):
        self.shared_config.cache_num = int(self.m_textCtrl30.GetValue() or 2)

    def on_skip_changed(self, event):
        self.shared_config.skip_frames = max(0, int(self.m_textCtrl281.GetValue() or 0))
        self.ImgManager.skip = max(0, int(self.m_textCtrl281.GetValue() or 0))

    def on_thread_change(self, event):
        new_thread_count = int(self.m_textCtrl29.GetValue() or 4)
        old_thread_count = self.shared_config.thread

        # Update only when thread count actually changes
        if new_thread_count != old_thread_count:
            self.shared_config.thread = new_thread_count
            # Immediately refresh thread-pool allocation
            if hasattr(self, 'video_manager'):
                self.video_manager.update_thread_count()

    def on_enable_video_mode(self, event):
        self.shared_config.video_mode = self.m_checkBox66.GetValue()
        on_video_mode_change(self.shared_config.video_mode)

        # Manage the image stitch pool based on mode
        if self.shared_config.video_mode:
            # Entering video mode: release image stitch pool
            self._shutdown_image_stitch_executor()
        else:
            # Entering image mode: initialize image stitch pool
            self._init_image_stitch_executor()

    def on_interval_changed(self, event):
        self.shared_config.interval = float(self.m_textCtrl28.GetValue() or 1.0)

    def toggle_play(self, event):
        self.shared_config.is_playing = not self.shared_config.is_playing

        if self.shared_config.is_playing:
            if getattr(self, "last_direction", 0) == 0:
                self.last_direction = 1
            self.shared_config.play_direction = getattr(self, "last_direction", 1)
        if self.shared_config.is_playing:
            interval = float(self.m_textCtrl28.GetValue() or 1.0)
            self.play_timer.Start(int(interval * 1000), oneShot=False)
            label = "⏸"
        else:
            self.play_timer.Stop()
            label = "▶"

        vm = getattr(self, "video_manager", None)
        if vm:
            vm.perf_monitor.reset_render_clock()
            vm.perf_monitor.render_history.clear()

        self.right_arrow_button1.SetLabel(label)

    def on_play_timer(self, event):
        if self.shared_config.is_playing:
            self._from_timer = True
            if self.shared_config.play_direction >= 0:
                self.next_img(None)  # Forward playback
            else:
                self.last_img(None)  # Reverse playback
            self._from_timer = False

    def parallel_sequential_fc(self, event):
        self.shared_config.parallel_sequential = self.parallel_sequential.GetValue()
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False
            self.shared_config.parallel_to_sequential =False

    def _init_image_stitch_executor(self):
        """Initialize the image-mode stitch pool (fixed single worker)."""
        if self.image_stitch_executor is None:
            self.image_stitch_executor = ThreadPoolExecutor(max_workers=1)

    def _shutdown_image_stitch_executor(self):
        """Shut down the image-mode stitch pool."""
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
            img_mgr = getattr(self, "ImgManager", None)
            if (
                img_mgr
                and getattr(img_mgr, "input_path", None)
                and getattr(img_mgr, "type", None) in (0, 1)
            ):
                try:
                    img_mgr.init(
                        img_mgr.input_path,
                        img_mgr.type,
                        parallel_to_sequential=value,
                        action_count=0,
                        img_count=0,
                        video_mode=False,
                        skip=getattr(img_mgr, "skip", 0),
                    )
                    img_mgr.set_action_count(0)
                    self.shared_config.batch_idx = 0
                    self.shared_config.image_cache_img = []
                    self.shared_config.image_cache_paths = []
                    self.show_img_init()
                    self.show_img()
                except Exception:
                    pass

    def _apply_parallel_switch(self):
        if not getattr(self.shared_config, "video_mode", False):
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
        except Exception:
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
            self.one_dir_mul_img(event)
        elif input_mode == 1:
            self.one_dir_mul_dir_auto(event)
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)
        elif input_mode == 3:
            self.onefilelist()

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=1)
            if not selected:
                return
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                self.ImgManager.init(dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(1)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def close(self, event):
        if self._is_closing:
            return
        self._is_closing = True

        self.play_timer.Stop()
        # Release thread pools
        if hasattr(self, "video_manager"):
            if hasattr(self.video_manager, "executor") and self.video_manager.executor:
                self.video_manager.executor.shutdown(wait=False, cancel_futures=True)
            if hasattr(self.video_manager, "stitch_executor") and self.video_manager.stitch_executor:
                self.video_manager.stitch_executor.shutdown(wait=False, cancel_futures=True)

        # Release the image-mode stitch pool
        self._shutdown_image_stitch_executor()

        self.shared_config.is_playing = False

        if hasattr(self, "video_manager") and hasattr(self.video_manager, "executor"):
            self.video_manager.executor.shutdown(wait=False, cancel_futures=True)

        if hasattr(self, 'show_bmp_in_panel'):
            del self.show_bmp_in_panel
        if hasattr(self, 'ImgManager'):
            if hasattr(self.ImgManager, 'clear_cache'):
                self.ImgManager.clear_cache()
        import gc
        gc.collect()
        cache_base = "Video_frames"
        if os.path.isdir(cache_base):
            shutil.rmtree(cache_base)

        if hasattr(self, "indextablegui") and self.indextablegui:
            self.indextablegui.Destroy()
        if hasattr(self, "aboutgui") and self.aboutgui:
            self.aboutgui.Destroy()

        self.Destroy()
        os._exit(0)

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        try:
            if self.ImgManager.type == 1:
                input_path = self.ImgManager.input_path
            else:
                input_path = None
        except Exception:
            input_path = None
        if self.shared_config.video_mode:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value ,video_manager = self.video_manager,shared_config=self.shared_config)
        else:
            self.UpdateUI(1, input_path, self.parallel_to_sequential.Value)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def last_img(self, event):
        if self.shared_config.video_mode and self.shared_config.is_playing and not getattr(self, "_from_timer", False):
            self.shared_config.play_direction = -1
            self.last_direction = self.shared_config.play_direction  # Keep this existing line for behavior consistency
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
            self.video_manager.update_cache()

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

        max_allowed = int((getattr(self.ImgManager, "max_action_num", 1) or 1) - 1)
        max_idx = max(0, max_allowed)
        clamped = min(target, max_idx)

        # Update state only; image refresh is controlled by refresh()
        self.shared_config.batch_idx = clamped
        self.ImgManager.action_count = clamped
        self.ImgManager.img_count = clamped * self.ImgManager.count_per_action

        # In video mode, prepare cache in the background without rendering
        if getattr(self.shared_config, "video_mode", False):
            self.video_manager.update_cache()

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

        max_allowed = int((getattr(self.ImgManager, "max_action_num", 1) or 1) - 1)
        max_idx = max(0, max_allowed)
        clamped = min(target, max_idx)
        self.shared_config.batch_idx = clamped
        self.ImgManager.action_count = clamped
        self.ImgManager.img_count = clamped * self.ImgManager.count_per_action
        if self.shared_config.video_mode:
            self.video_manager.update_cache()

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
            except Exception:
                pass
            self.ImgManager.layout_params[33] = self.out_path_str
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

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

        if self.ImgManager.img_num != 0:
            self.show_img()
        else:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def _invalidate_render_cache(self):
        """Clear current cache to force restitching (shared by video/image modes)."""
        self.shared_config.image_cache_img = []
        self.shared_config.image_cache_paths = []
        cache = getattr(self.shared_config, "cache_img", None)
        if isinstance(cache, list):
            for i in range(len(cache)):
                cache[i] = None
        self._last_refresh_batch = None
        vm = getattr(self, "video_manager", None)
        if vm is not None and hasattr(vm, "_last_batch"):
            vm._last_batch = None

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=0)
            if not selected:
                return
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Choose input dir", "",
                               wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

            if dlg.ShowModal() == wx.ID_OK:
                self.ImgManager.init(dlg.GetPath(), type=2)
        if self.shared_config.video_mode:
            if self.shared_config.video_path == []:
                return
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])

    def onefilelist(self):
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
            except Exception:
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
        second_txt = self.m_statusBar1.GetStatusText(1)
        second_txt = second_txt.split("/")[0]
        self.m_statusBar1.SetStatusText(second_txt+"/"+str(id)+"-th img", 1)

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
        xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
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
                except Exception:
                    self.SetStatusText_(
                        ["-1",  "Drawing a box need click left mouse button!", "-1", "-1"])

                self._invalidate_render_cache()
                self.refresh(event)
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
            else:
                if self.handle_title_injection(id):
                    pass
                else:
                    self.refresh(event)
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
                    except Exception:
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
        except Exception:
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
                    self.ImgManager.get_img_list()
                    self.show_img()
                    self.SetStatusText("✅ Title updated successfully!")

                    if hasattr(self, 'title_rename_text'):
                        self.title_rename_text.SetValue("")
                    self.SetStatusText_([f"The title has been injected into {current_index+1} images: {new_title}", "-1", "-1", "-1"])
                else:
                    raise Exception("Failed to write EXIF")
            else:
                raise Exception(f"Picture index {actual_img_index} out of range")

        except Exception:
            pass

    def handle_title_injection(self, img_id = None):
        if not hasattr(self, 'title_rename_text'):
            return False
        new_title = self.title_rename_text.GetValue().strip()
        if not new_title:
            return False
        try:
            self.inject_new_title(new_title, img_id)
            return True
        except Exception:
            return False

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

    def show_img_init(self):
        layout_params = self.set_img_layout()
        if not getattr(self.shared_config, "video_mode", False):
            layout_token = repr(layout_params)
            if layout_token != getattr(self, "_image_layout_token", None):
                self._debug_image(f"[ImageCache] reset, previous_batches={len(self.shared_config.image_cache_img)}")
                self.shared_config.image_cache_img = []
                self.shared_config.image_cache_paths = []
                self._image_layout_token = layout_token

        count_per_action = getattr(self.shared_config, "count_per_action", 1)
        if self.shared_config.video_mode:
            synced = self._sync_video_count_per_action()
            if synced is not None:
                count_per_action = synced

        if layout_params:
            self.ImgManager.layout_params = layout_params

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
                             self.title_exif.Value]                     # 11

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
        except Exception:
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
                    self.show_unit.Value ]                  # 36

    def show_img(self):
        self._setup_img_panel()

        # Video mode: always read from cache_img[b]; do not stitch on demand
        if getattr(self.shared_config, "video_mode", False):
            b = int(self.shared_config.batch_idx)

            # If this batch is not stitched yet, wait briefly or stitch synchronously
            if b >= len(self.shared_config.cache_img) or self.shared_config.cache_img[b] is None:
                vm = getattr(self, "video_manager", None)
                if vm:
                    # Wait for async stitching to complete (up to 5 seconds)
                    max_wait = 5.0
                    start = time.time()
                    while (b >= len(self.shared_config.cache_img) or
                           self.shared_config.cache_img[b] is None) and \
                          (time.time() - start < max_wait):
                        time.sleep(0.05)

                    # If still missing, force synchronous stitching for current batch
                    if b >= len(self.shared_config.cache_img) or self.shared_config.cache_img[b] is None:
                        parallel_to_seq = getattr(self.shared_config, "parallel_to_sequential", False)
                        video_paths = getattr(self.shared_config, "video_path", [])

                        if len(video_paths) > 1 and not parallel_to_seq:
                            # Multi-video mode
                            count_per_action = max(1, int(self.shared_config.count_per_action or 1))
                            for i, num in enumerate(self.shared_config.video_num_list):
                                n_i = int(num or 0)
                                max_b_i = (n_i + count_per_action - 1) // count_per_action if n_i > 0 else 0
                                if b < max_b_i:
                                    try:
                                        vm._ensure_batch_extracted(i, b, wait=True)
                                    except Exception as ex:
                                        self.shared_config.video_last_message = f"Video extract failed: {ex}"
                                        self.SetStatusText_(["-1", "-1", f"***Video extract failed: {ex}***", "-1"])
                            vm._stitch_batch_multi(b)
                        elif len(video_paths) == 1 or parallel_to_seq:
                            # Single-video or parallel-to-sequential mode
                            video_idx = 0
                            local_b = b
                            if parallel_to_seq and len(video_paths) > 1:
                                # Compute which video owns the current batch
                                count_per_action = max(1, int(self.shared_config.count_per_action or 1))
                                cum = 0
                                for i, num in enumerate(self.shared_config.video_num_list):
                                    max_b_i = (int(num) + count_per_action - 1) // count_per_action
                                    if b < cum + max_b_i:
                                        video_idx = i
                                        local_b = b - cum
                                        break
                                    cum += max_b_i
                            try:
                                vm._ensure_batch_extracted(video_idx, local_b, wait=True)
                            except Exception as ex:
                                self.shared_config.video_last_message = f"Video extract failed: {ex}"
                                self.SetStatusText_(["-1", "-1", f"***Video extract failed: {ex}***", "-1"])
                            vm._stitch_batch(video_idx, local_b, b)

            if 0 <= b < len(self.shared_config.cache_img) and self.shared_config.cache_img[b] is not None:
                pil_img = self.shared_config.cache_img[b]
                self.shared_config.video_last_message = ""
                if getattr(self.shared_config, "is_playing", False):
                    vm = getattr(self, "video_manager", None)
                    if vm:
                        vm.perf_monitor.push_render_event()
                self.display_bitmap(True, pil_img)
                # Status bar/slider update (helps indicate current position)
                try:
                    max_batches = self.ImgManager.max_action_num
                    if getattr(self.shared_config, "parallel_to_sequential", False):
                        nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None]
                        total = sum(nums)
                        count = max(1, int(getattr(self.shared_config, "count_per_action", 1) or 1))
                        if total > 0:
                            max_batches = (total + count - 1) // count
                            self.ImgManager.max_action_num = max_batches
                    self.slider_img.SetMax(max(0, max_batches - 1))
                    self.slider_img.SetValue(b)
                    self.slider_value.SetValue(str(b))
                    self.slider_value_max.SetLabel(str(max(0, max_batches - 1)))
                except Exception:
                    pass
            else:
                msg = str(getattr(self.shared_config, "video_last_message", "") or "").strip()
                if msg:
                    self.SetStatusText_(["-1", "-1", f"***{msg}***", "-1"])
                    print(f"[VideoStatus] {msg}")
                else:
                    self.SetStatusText_(["-1", "-1", "***Waiting...***", "-1"])

            self.SetStatusText_(["Stitch", "-1", "-1", "-1"])
            self.position = [0, 0]
            self.scrolledWindow_img.Scroll(0, 0)
            wx.CallAfter(self.scrolledWindow_img.Scroll, 0, 0)
            return

        if self.ImgManager.max_action_num > 0:
            current_batch = max(0, min(int(getattr(self.shared_config, "batch_idx", 0)), self.ImgManager.max_action_num - 1))
            self._update_image_cache(current_batch)

            cache_list = self.shared_config.image_cache_img
            path_cache = self.shared_config.image_cache_paths

            self.slider_img.SetMax(self.ImgManager.max_action_num - 1)
            self.slider_img.SetValue(current_batch)
            self.slider_value.SetValue(str(current_batch))
            self.slider_value_max.SetLabel(str(self.ImgManager.max_action_num - 1))

            pil_img = cache_list[current_batch] if current_batch < len(cache_list) else None

            if pil_img is not None:
                self.show_bmp_in_panel = pil_img
                self.img_size = pil_img.size
                self._debug_image(f"[ImageCache] hit batch={current_batch}")
                self.display_bitmap(False, pil_img)

                # Update ImgManager state for UI use
                self.ImgManager.action_count = current_batch
                self.ImgManager.img_count = current_batch * self.ImgManager.count_per_action
                if current_batch < len(path_cache) and path_cache[current_batch] is not None:
                    self.ImgManager.flist = path_cache[current_batch]

                if self.ImgManager.type in (2, 3):
                    try:
                        self.SetStatusText_([
                            "-1",
                            f"{current_batch}/{self.ImgManager.max_action_num-1}",
                            f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / "
                            f"{self.ImgManager.name_list[self.ImgManager.img_count]}"
                            f"-{self.ImgManager.name_list[self.ImgManager.img_count + self.ImgManager.count_per_action - 1]}",
                            "-1",
                        ])
                    except Exception:
                        pass
            else:
                self.SetStatusText_(["-1", "-1", "***Error: no image in this dir!***", "-1"])
        else:
            self.SetStatusText_(["-1", "-1", "***Error: no image in this dir!***", "-1"])

        self.auto_layout()
        self.SetStatusText_(["Stitch", "-1", "-1", "-1"])

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
        max_batch = self.ImgManager.max_action_num - 1
        if max_batch < 0:
            return

        R = max(1, int(getattr(self.shared_config, "cache_num", 1)))
        prev_guard = R
        window_start = max(0, batch_idx - prev_guard)
        window_end = min(max_batch, batch_idx + R - 1)

        cache_list = self.shared_config.image_cache_img
        path_list = self.shared_config.image_cache_paths
        if len(cache_list) <= window_end:
            cache_list.extend([None] * (window_end + 1 - len(cache_list)))
        if len(path_list) <= window_end:
            path_list.extend([None] * (window_end + 1 - len(path_list)))

        orig_action = self.ImgManager.action_count
        orig_img_count = getattr(self.ImgManager, "img_count", 0)
        orig_flist = getattr(self.ImgManager, "flist", None)

        # Ensure the image stitch pool is initialized
        if self.image_stitch_executor is None:
            self._init_image_stitch_executor()

        try:
            # Process current batch synchronously so it's immediately available
            if cache_list[batch_idx] is None:
                flist = self._get_image_flist(batch_idx)
                if flist:
                    self.ImgManager.set_action_count(batch_idx)
                    self.ImgManager.img_count = batch_idx * self.ImgManager.count_per_action
                    pil_img, flag = self.compose_current_frame(batch_idx=batch_idx, flist=flist)
                    if flag == 0:
                        path_list[batch_idx] = flist
                        self._debug_image(f"[ImageCache] sync write batch={batch_idx}")
                    else:
                        cache_list[batch_idx] = None
                        path_list[batch_idx] = None

            # Pre-stitch other batches asynchronously via thread pool
            for t in range(window_start, window_end + 1):
                if t == batch_idx:  # Current batch is already handled
                    continue
                if cache_list[t] is None:
                    self.image_stitch_executor.submit(
                        self._stitch_image_batch, t, cache_list, path_list
                    )

            # Clear cache outside the active window
            for idx in range(len(cache_list)):
                if idx < window_start or idx > window_end:
                    cache_list[idx] = None
                    if idx < len(path_list):
                        path_list[idx] = None
        finally:
            self.ImgManager.action_count = orig_action
            self.ImgManager.img_count = orig_img_count
            if orig_flist is not None:
                self.ImgManager.flist = orig_flist

    def _stitch_image_batch(self, t, cache_list, path_list):
        """Image-stitch task executed in the thread pool."""
        try:
            # Protect ImgManager state access with a lock
            with self._image_stitch_lock:
                flist = self._get_image_flist(t)
                if not flist:
                    cache_list[t] = None
                    path_list[t] = None
                    return

                # Set state and stitch while holding the lock
                self.ImgManager.set_action_count(t)
                self.ImgManager.img_count = t * self.ImgManager.count_per_action
                pil_img, flag = self.compose_current_frame(batch_idx=t, flist=flist)

                if flag != 0:
                    cache_list[t] = None
                    path_list[t] = None
                else:
                    path_list[t] = flist
                    self._debug_image(f"[ImageCache] async write batch={t} thread={threading.current_thread().name}")
        except Exception as e:
            self._debug_image(f"[ImageCache] async stitch failed batch={t} error={e}")
            cache_list[t] = None
            path_list[t] = None

            if orig_flist is not None:
                self.ImgManager.flist = orig_flist

    def compose_current_frame(self, batch_idx=0, flist=None):
        """
        Only generate the stitched result for the current frame; do not touch UI state.
        Returns: (pil_img, flag)
        - pil_img: PIL.Image or None
        - flag: 0 means success; other values follow ImgManager.stitch_images semantics
        """
        if self.show_custom_func.Value:
            self.ImgManager.layout_params[32] = True
            self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier))
            self.ImgManager.layout_params[32] = False

        stitch_start = time.time()
        flag = self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier), flist=flist)
        stitch_duration = time.time() - stitch_start
        if flag != 0:
            return None, flag

        pil_img = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)

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

    def display_bitmap(self, video_mode, pil_img):
        dbg_batch = int(getattr(self.shared_config, "batch_idx", -1))

        if pil_img is None and video_mode:
            cache = getattr(self.shared_config, "cache_img", [])
            b = int(getattr(self.shared_config, "batch_idx", 0))
            if not (0 <= b < len(cache)) or cache[b] is None:
                return
            pil_img = cache[b]

        try:
            if pil_img is not None:
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

        bmp = self.ImgManager.ImgF.PIL2wx(pil_img)
        self._set_placeholder_visible(False)

        if hasattr(self, "img_last") and self.img_last:
            self.img_last.SetBitmap(bmp)
        else:
            self.img_last = wx.StaticBitmap(self.img_panel, bitmap=bmp)
        self._ensure_img_bindings()

        if not hasattr(self, "img_panel_sizer"):
            self.img_panel_sizer = wx.BoxSizer(wx.VERTICAL)
            self.img_panel.SetSizer(self.img_panel_sizer)
        else:
            try:
                self.img_panel_sizer.Clear(False)
            except Exception:
                pass

        self.img_panel_sizer.Add(self.img_last, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP, 0)

        # Key fix: use PIL logical size for layout, not bmp.GetSize() HiDPI physical pixels
        logical_w, logical_h = pil_img.size
        logical_size = wx.Size(int(logical_w), int(logical_h))

        self.img_last.SetPosition((0, 0))
        self.img_last.SetSize(logical_size)
        self.img_last.SetMinSize(logical_size)

        self.img_panel.SetPosition((0, 0))
        self.img_panel.SetSize(logical_size)
        self.img_panel.SetMinSize(logical_size)

        try:
            self.scrolledWindow_img.Freeze()
        except Exception:
            pass

        self.img_panel.Layout()
        self.scrolledWindow_img.Layout()
        self.scrolledWindow_img.SetVirtualSize(logical_size)
        self.scrolledWindow_img.Scroll(0, 0)
        self.position = [0, 0]

        try:
            self.scrolledWindow_img.Thaw()
        except Exception:
            pass

        wx.CallAfter(self.scrolledWindow_img.Scroll, 0, 0)
        self.scrolledWindow_img.Refresh()

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

    def title_auto_fc(self, event):
        titles = [self.title_down_up, self.title_show_parent,
                  self.title_show_name, self.title_show_suffix, self.title_show_prefix, self.title_position, self.title_exif]
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
        data = {
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
        }
        config_path = Path(get_resource_path(str(Path("configs"))))
        config_file_path = str(config_path / "default_config.json")
        with open(config_file_path, 'r', encoding='utf-8') as file:
            full_config = json.load(file)
        full_config['output'] = data
        with open(config_file_path, 'w', encoding='utf-8') as file:
            json.dump(full_config, file, indent=1)

    def load_configuration(self, event, config_name="default_config.json"):
        config_path = Path(get_resource_path(str(Path("configs"))))
        config_file_path = str(config_path / config_name)
        with open(config_file_path, 'r', encoding='utf-8') as file:
            full_config = json.load(file)
            data = full_config.get('output', full_config)
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

    def reset_configuration(self, event):
        json_path = Path(get_resource_path(str(Path("configs"))))
        default_config_path = str(json_path / "default_config.json")
        userdef_config_path = str(json_path / "userdef_config.json")
        self.load_configuration(event, config_name="userdef_config.json")
        shutil.copy(userdef_config_path, default_config_path)

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

        # Check whether the last batch has been reached
        max_batch_idx = self.ImgManager.max_action_num - 1
        if self.shared_config.batch_idx >= max_batch_idx:
            if getattr(self.shared_config, "is_playing", False):
                # Stop playback
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
            self.video_manager.update_cache()

        if getattr(self.ImgManager, "img_count", 0) < int(self.ImgManager.img_num) - 1:
            self.ImgManager.add()

        self.shared_config.batch_idx = min(self.shared_config.batch_idx, self.ImgManager.max_action_num - 1)
        if not self.shared_config.video_mode:
            self.shared_config.batch_idx = min(self.ImgManager.action_count, self.ImgManager.max_action_num - 1)
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
        try:
            if visible:
                self.m_staticText1.Show()
            else:
                self.m_staticText1.Hide()
            self.scrolledWindow_img.GetSizer().Layout()
            self.scrolledWindow_img.Layout()
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
        self.img_last.Bind(wx.EVT_LEFT_DOWN, self.img_left_click)
        self.img_last.Bind(wx.EVT_LEFT_DCLICK, self.img_left_dclick)
        self.img_last.Bind(wx.EVT_MOTION, self.img_left_move)
        self.img_last.Bind(wx.EVT_LEFT_UP, self.img_left_release)
        self.img_last.Bind(wx.EVT_RIGHT_DOWN, self.img_right_click)
        self.img_last.Bind(wx.EVT_MOUSEWHEEL, self.img_wheel)

    def disable_accel(self, event):
        self.SetAcceleratorTable(wx.NullAcceleratorTable)
        event.Skip()

    def enable_accel(self, event):
        self.SetAcceleratorTable(self.acceltbl)
        event.Skip()
