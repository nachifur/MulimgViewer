"""Playback controller methods layered over the generated wx GUI."""
import time, math
import weakref
import wx
from .path_select import on_video_mode_change
import copy


from .video_tools import read_video_file_list


class VideoPlaybackMixin:
    """GUI-thread playback, video mode transitions and asynchronous display callbacks.

    The concrete viewer supplies controls, image navigation and resource policy.
    Workers and disk-cache ownership remain in VideoManager.
    """

    def on_enable_video_mode(self, event):
        prev_video_mode = self.shared_config.video_mode
        self.shared_config.video_mode = self.video_mode.GetValue()
        self._commit_video_settings()
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
        custom = bool(self.ImgManager.layout_params[32])
        key = (repr(self.ImgManager.layout_params), tuple(self.ImgManager.gap_color), repr(self.xy_magnifier), custom,
               vm._cache_context_token(), hash(getattr(self.ImgManager, '_custom_algorithm_registry', None)))
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
                owner._status_display_batch = batch
                owner._apply_pending_index_selection()
                owner.update_status_bar_for_current_page()
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


    def _clear_video_mode_cache(self):
        """Clear every piece of local state owned by video mode.

        Called when leaving video mode for image mode so that stale video
        stitches (in-memory PNG paths and on-disk cache_frames/stitch_cache
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
        # A video list is another parallel source collection. Its outer grid
        # selects streams, rather than multiplying frames inside every stream.
        parallel_sources = len(self.shared_config.video_path) > 1 and not self.parallel_to_sequential.Value
        sequential_layout = (self.shared_config.input_mode in (2, 3)
                             or self.parallel_to_sequential.Value)
        if sequential_layout and not parallel_sources:
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


    def _open_video_file_list(self, path):
        try:
            videos = read_video_file_list(path)
        except (OSError, ValueError, UnicodeError) as error:
            self.SetStatusText_(['Input', '-1', f'Unable to read video list: {error}', '-1'])
            return False
        if not videos:
            self.SetStatusText_(['Input', '-1', 'No valid video files in this list', '-1'])
            return False
        self.shared_config.real_video_path = videos
        self.shared_config.input_mode = 3
        self.shared_config.batch_idx = 0
        self.choice_input_mode.SetSelection(3)
        self._commit_video_settings()
        return bool(self.video_manager.select_video(type=-1))
