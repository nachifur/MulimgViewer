"""Real wx event-loop regressions. Windows tests use an unshown application frame."""
import os
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from concurrent.futures import Future
from functools import partial
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import wx
from PIL import Image
from mulimgviewer.src.main import MulimgViewer
from mulimgviewer.src.utils_img import ImgManager
from mulimgviewer.src.resource_policy import ResourceBudget
from mulimgviewer.src.video_tools import resolve_video_tools


class HiddenViewer(MulimgViewer):
    def check_version(self):
        """Keep network update checks out of the isolated GUI fixture."""
        return None

    def load_configuration(self, *args, **kwargs):
        """Use test settings instead of restoring the developer's session."""
        return None

    def _restore_window_state(self):
        """Keep each test independent of saved desktop geometry."""
        return None


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg executable required')
class VideoGuiAsyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.reclaim_native = patch('mulimgviewer.src.memory_reclaim.release_unused_memory', return_value={})
        self.native_release = self.reclaim_native.start()
        self.addCleanup(self.reclaim_native.stop)
        self.previous = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=80x48:rate=10:duration=8', '-c:v', 'mpeg4',
                        '-y', 'sample.mp4'], check=True, capture_output=True)
        self.frame = HiddenViewer(None, lambda *a, **k: None, lambda *a, **k: None)
        self.frame.Hide()
        cfg = self.frame.shared_config
        cfg.video_mode = True
        cfg.cache_num = 2
        cfg.cache_multiplier = 3
        cfg.batch_idx = 20
        cfg.real_video_path = [str(Path('sample.mp4').resolve())] * 2
        cfg.video_path = [str(Path('cache_frames/a')), str(Path('cache_frames/b'))]
        cfg.video_fps_list = [10.0, 10.0]
        cfg.video_num_list = [80, 80]
        for path in cfg.video_path:
            Path(path).mkdir(parents=True, exist_ok=True)
        self.frame.ImgManager.init(cfg.video_path, type=1, video_mode=True,
                                   video_fps_list=cfg.video_fps_list,
                                   video_num_list=cfg.video_num_list, skip=0)
        self.frame.row_col.ChangeValue('1,2')
        self.frame.cache_save_format.SetSelection(1)  # Pixel-exact regressions use lossless caches.
        self.frame.show_img_init()
        self.frame.ImgManager.set_action_count(20)
        self.frame.video_manager._mark_batch_processed = lambda: None

    def tearDown(self):
        from mulimgviewer.src.export_async import cancel_save
        cancel_save(self.frame)
        pool=getattr(self.frame,'_export_pool',None)
        if pool is not None:pool.shutdown(wait=True,cancel_futures=True)
        self.frame._is_closing = True
        self.frame.play_timer.Stop()
        self.frame._cancel_pending_frame_wait()
        self.frame.image_pipeline.close()
        pipeline = self.frame.image_pipeline
        for pool in (pipeline.coordinator, pipeline.pool, pipeline.display, *pipeline.retired_pools):
            if pool:
                pool.shutdown(wait=True)
        self.frame.resource_monitor.close()
        self.frame.resource_monitor.thread.join(timeout=2)
        self.frame.memory_reclaimer.close()
        self.frame.memory_reclaimer.executor.shutdown(wait=True)
        vm = self.frame.video_manager
        vm._cache_executor.shutdown(wait=True)
        vm.shutdown()
        for pool in (vm.executor, vm.stitch_executor, vm._maintenance_executor, vm._display_executor):
            pool.shutdown(wait=True)
        pipeline.processing.cleanup_future.result(timeout=5)
        self.frame.Destroy()
        self.app.Yield(True)
        os.chdir(self.previous)
        self.temp.cleanup()

    def pump_until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.Yield(True)
            if predicate():
                return
            time.sleep(0.005)
        self.fail('GUI operation did not complete')

    def run_timer_until(self, predicate, timeout=10):
        # wx.Timer needs a running native GUI event loop, not just Yield calls.
        deadline = time.monotonic() + timeout
        completed = []
        def check():
            if predicate():
                completed.append(True)
                self.app.ExitMainLoop()
            elif time.monotonic() >= deadline:
                self.app.ExitMainLoop()
            else:
                wx.CallLater(5, check)
        wx.CallAfter(check)
        self.app.MainLoop()
        self.assertTrue(completed, 'Timed playback did not complete')

    def warm_current_window(self):
        vm = self.frame.video_manager
        vm.update_cache()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20
                        and not vm.cache_update_pending() and not vm._pending_extract
                        and not vm._window_stitches)

    def test_custom_playback_prioritizes_forward_stock_before_unseen_past_pages(self):
        self.frame.show_all_func.SetValue(True);self.frame.show_img_init()
        vm=self.frame.video_manager;cfg=self.frame.shared_config
        vm._render_snapshot=(self.frame.ImgManager.video_stitch_snapshot(),[],False)
        cfg.is_playing=True;cfg.play_direction=1;cfg.batch_idx=20
        vm._window_token='priority';vm._stitch_window=(14,26)
        with patch.object(vm,'_compute_buffer_depth',return_value=0),patch.object(vm,'_run_window_stitch_async',return_value=Future()) as submit:
            vm._queue_window_stitch(19,[],'priority')
            self.assertNotIn(('priority',19),vm._window_stitches)
            vm._queue_window_stitch(21,[],'priority')
            self.assertIn(('priority',21),vm._window_stitches)
            submit.assert_called_once()
        cfg.is_playing=False
        with patch.object(vm,'_run_window_stitch_async',return_value=Future()):
            vm._queue_window_stitch(19,[],'priority')
            self.assertIn(('priority',19),vm._window_stitches)
        cfg.is_playing=False

    def test_custom_streaming_start_and_reverse_produce_real_frames(self):
        self.frame.show_all_func.SetValue(True)
        cfg=self.frame.shared_config;cfg.is_playing=True
        with patch.object(self.frame,'_schedule_next_video_tick'):
            self.frame.refresh(None);self.frame._seek_display_page(21)
            self.pump_until(lambda:getattr(self.frame,'_status_display_batch',None)==20)
            vm=self.frame.video_manager
            self.assertTrue(vm.perf_monitor.extract_run_history)
            self.assertGreater(vm._produced_pages,0)
            self.assertTrue(all(batch>=20 for batch in vm._playback_pacer.pending))
            cfg.play_direction=-1;vm.update_cache()
            self.pump_until(lambda:vm._cached_batch_path(19,validate=False) is not None)
            self.assertTrue(all(batch<=20 for batch in vm._playback_pacer.pending))
            cfg.is_playing=False;self.frame.play_timer.Stop();vm.update_cache()
            self.pump_until(lambda:not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
            radius=cfg.cache_num*cfg.cache_multiplier
            self.assertEqual(sum(vm._cached_batch_path(batch,validate=False) is not None for batch in range(20-radius,21+radius)),2*radius+1)

    def test_original_mosaic_does_not_serialize_borrowed_stitch_lanes(self):
        vm=self.frame.video_manager
        self.frame.shared_config.thread=4
        vm._apply_thread_plan(3,1)
        self.warm_current_window()
        self.assertEqual(vm._stitch_threads,1)
        self.assertEqual(self.frame.image_pipeline.processing.budget.limit,vm._pipeline_workers.total_budget)
        self.assertGreater(self.frame.image_pipeline.processing.budget.limit,1)

    def test_repeated_layout_refreshes_do_not_accumulate_mosaic_versions(self):
        self.warm_current_window()
        vm=self.frame.video_manager
        for gap in (3,5,7):
            self.frame.gap.ChangeValue(f'{gap},{gap},0,0,0,0,0,0')
            self.frame.show_img_init();self.frame.show_img()
            self.warm_current_window()
            cache=self.frame.image_pipeline.processing
            expected=vm._stitch_window[1]-vm._stitch_window[0]+1
            cache.request_prune()
            # Retiring entries is immediate; physical deletion is asynchronous.
            self.pump_until(lambda cache=cache,expected=expected:len(list(cache.directory.glob('result_mosaic_*')))<=expected)
            with cache.lock:self.assertLessEqual(len(cache.entries),expected)
            self.assertLessEqual(len(list(cache.directory.glob('result_mosaic_*'))),expected)

    def test_normal_viewer_close_waits_then_cleans_entire_cache_tree(self):
        self.warm_current_window()
        root=self.frame.video_manager.cache_dir
        self.assertTrue((root/'.work').exists())
        with patch.object(self.frame,'Destroy'),patch('wx.Exit'), \
                patch.object(self.frame,'_save_session_configuration'),patch.object(self.frame,'_save_window_state'):
            self.frame.close(None)
        self.frame._cache_cleanup_future.result(timeout=10)
        self.assertFalse(root.exists())
        # The normal close already shut it down; fixture teardown is idempotent.
        self.frame.video_manager.shutdown=lambda:None

    def test_pixel_accelerator_scales_with_memory_and_shrinks_immediately(self):
        vm=self.frame.video_manager;cfg=self.frame.shared_config
        limits=[]
        for memory in (2*1024**3,6*1024**3,9*1024**3):
            cfg.memory_budget=memory
            vm._configure_video_memory()
            limits.append(vm._pixel_cache.limit)
            self.assertLessEqual(vm._pixel_cache.limit,memory*.08)
            self.assertLessEqual(vm._pixel_cache.limit,1024**3)
        self.assertLess(limits[0],limits[1]);self.assertLess(limits[1],limits[2])
        vm._pixel_cache.put('test',Image.new('RGB',(8,8)))
        cfg.memory_budget=1024
        vm._configure_video_memory()
        self.assertLessEqual(vm._pixel_cache.bytes,vm._pixel_cache.limit)

    def test_selected_magnifier_before_first_page_and_title_geometry_survive_snapshot(self):
        frame=self.frame
        frame.img_resolution.ChangeValue('80,48')
        frame.show_scale.ChangeValue('1,1')
        frame.row_col_img_unit.ChangeValue('3,1')
        frame.title_show.SetValue(True)
        frame.show_magnifer.SetValue(True)
        frame.show_original.SetValue(True)
        frame.xy_magnifier=[[4,4,24,20,1,1,False]]
        frame.color_list=[wx.Colour(255,0,0)]
        frame.show_img_init()
        frame.ImgManager.set_action_count(20)
        self.warm_current_window()
        vm=frame.video_manager
        self.assertTrue(frame.ImgManager.crop_points)
        self.assertGreater(frame.ImgManager.title_max_size[1],0)
        self.assertEqual(frame.ImgManager.title_max_size,vm._batch_render_states[20]['title_max_size'])
        snapshot=frame.ImgManager.video_stitch_snapshot()
        self.assertEqual(snapshot.title_max_size,frame.ImgManager.title_max_size)
        self.assertIsNot(snapshot.title_max_size,frame.ImgManager.title_max_size)
        snapshot.crop_points_process([[4,4,24,20,1,1,False]])
        expected=snapshot.crop_points[0][:4]
        offset=snapshot.title_max_size[1]+snapshot.layout_params[3][5]
        snapshot.crop_points_process([[4,4+offset,24,20+offset,1,1,True]])
        self.assertEqual(snapshot.crop_points[0][:4],expected)

    def test_gui_processes_events_while_real_compositor_waits(self):
        entered, release = threading.Event(), threading.Event()
        heartbeat = []
        original = ImgManager.stitch_images
        def delayed(manager, *args, **kwargs):
            self.assertFalse(wx.IsMainThread(), 'Compositing ran on the GUI thread')
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI did not release compositor')
            return original(manager, *args, **kwargs)
        try:
            with patch.object(ImgManager, 'stitch_images', delayed):
                self.frame.video_manager.update_cache()
                self.assertTrue(entered.wait(3))
                wx.CallAfter(lambda: heartbeat.append('GUI event handled'))
                self.pump_until(lambda: bool(heartbeat))
                self.assertFalse(release.is_set())
                release.set()
                self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20)
            self.assertIsNotNone(self.frame.img_last.GetBitmap())
            self.assertEqual(self.frame.shared_config.batch_idx, 20)
        finally:
            release.set()

    def test_old_png_request_cannot_paint_after_jump(self):
        self.frame.video_manager.update_cache()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20)
        entered, release = threading.Event(), threading.Event()
        vm = self.frame.video_manager
        original = vm._prepare_video_image
        displayed = []
        paint = self.frame.display_bitmap
        def delayed(*args, **kwargs):
            self.assertFalse(wx.IsMainThread(), 'PNG preparation ran on the GUI thread')
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI did not release PNG decoder')
            return original(*args, **kwargs)
        def record(*args, **kwargs):
            self.assertTrue(wx.IsMainThread(), 'Painting ran outside the GUI thread')
            displayed.append(self.frame.shared_config.batch_idx)
            return paint(*args, **kwargs)
        try:
            self.frame._video_display_key = None
            with patch.object(vm, '_prepare_video_image', delayed), patch.object(self.frame, 'display_bitmap', record):
                self.frame.show_img()
                self.assertTrue(entered.wait(3))
                self.frame.shared_config.batch_idx = 24
                vm.update_cache()
                self.frame.show_img()
                self.app.Yield(True)
                self.assertFalse(displayed)
                release.set()
                self.pump_until(lambda: (getattr(self.frame, '_video_display_key', None) or (None,))[0] == 24)
            self.assertEqual(displayed, [24])
        finally:
            release.set()

    def test_cached_frame_displays_while_prefetch_stitch_waits(self):
        vm = self.frame.video_manager
        vm.update_cache()
        self.pump_until(lambda: vm._cached_batch_path(24) is not None
                        and getattr(self.frame, '_video_display_key', (None,))[0] == 20)
        # Drain the initial window before blocking newly requested outer batches.
        self.pump_until(lambda: not vm._pending_extract and not vm._window_stitches)
        entered, release = threading.Event(), threading.Event()
        original = ImgManager.stitch_images
        def delayed(manager, *args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI did not release prefetch stitch')
            return original(manager, *args, **kwargs)
        try:
            with patch.object(ImgManager, 'stitch_images', delayed):
                self.frame.shared_config.batch_idx = 24
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                self.frame.show_img()
                self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 24)
                self.assertFalse(release.is_set())
        finally:
            release.set()

    def test_render_snapshot_does_not_share_mutable_layout(self):
        manager = self.frame.ImgManager
        snapshot = manager.video_stitch_snapshot()
        original_rows = manager.layout_params[0][0]
        snapshot.layout_params[0][0] += 10
        self.assertEqual(manager.layout_params[0][0], original_rows)
        self.assertIs(snapshot.ImgF.manager, snapshot)
        self.assertIs(manager.ImgF.manager, manager)

    def test_interval_field_accepts_one_millisecond_and_rejects_nonfinite(self):
        self.assertIs(self.frame.interval, self.frame.m_textCtrl28)
        for text, expected in [('0.001', 0.001), ('0.0001', 0.001),
                               ('0.0015', 0.002), ('nan', 1.0), ('inf', 1.0)]:
            with self.subTest(text=text):
                self.frame.interval.ChangeValue(text)
                self.frame._commit_video_settings()
                self.assertEqual(self.frame.shared_config.interval, expected)
                self.assertEqual(float(self.frame.interval.GetValue()), expected)

    def test_timer_subtracts_processing_time_and_uses_single_shot(self):
        self.frame.shared_config.is_playing = True
        self.frame.shared_config.interval = 0.02
        self.frame._play_timer_suspended = False
        self.frame._video_tick_started_at = 42.0
        with patch.object(self.frame, 'play_timer') as timer:
            with patch('mulimgviewer.src.main.time.perf_counter', return_value=42.012):
                self.frame._schedule_next_video_tick()
            timer.Start.assert_called_once_with(8, oneShot=True)
            timer.reset_mock()
            with patch('mulimgviewer.src.main.time.perf_counter', return_value=42.03), patch.object(wx, 'CallAfter') as dispatch:
                self.frame._schedule_next_video_tick()
            timer.Start.assert_called_once_with(1, oneShot=True)
            # A native timer yields to paint/input instead of chaining CallAfter.
            dispatch.assert_not_called()

    def test_recommendation_does_not_restart_suspended_playback(self):
        self.frame.shared_config.is_playing = True
        self.frame._play_timer_suspended = True
        with patch.object(self.frame, 'play_timer') as timer:
            self.frame.video_manager._apply_interval_recommendation(0.005)
        timer.Start.assert_not_called()
        self.assertEqual(self.frame.shared_config.interval, 0.005)
        self.assertEqual(self.frame.interval.GetValue(), '0.005')

    def test_auto_writeback_is_not_recommitted_as_manual_interval(self):
        vm = self.frame.video_manager
        self.frame.interval.ChangeValue('0.1')
        self.frame._commit_video_settings()
        self.assertEqual(self.frame.shared_config.manual_interval, 0.1)
        self.frame.shared_config.interval_recommend = 0.3
        vm._apply_interval_recommendation(0.3)
        self.frame._commit_video_settings()  # Refresh or Play must not adopt auto text.
        self.assertEqual(self.frame.shared_config.manual_interval, 0.1)
        self.assertEqual(self.frame.shared_config.interval, 0.3)
        self.frame.shared_config.interval_recommend = 0.05
        vm._apply_interval_recommendation(0.05)
        self.assertEqual(self.frame.shared_config.interval, 0.1)
        self.assertEqual(float(self.frame.interval.GetValue()), 0.1)

    def test_power_mode_rebuilds_real_pools_to_match_budget(self):
        vm = self.frame.video_manager
        for mode, budget in ((4, 6), (1, 2)):
            self.frame.power_mode.SetSelection(mode - 1)
            with patch('mulimgviewer.src.main.resource_budget', return_value=ResourceBudget(mode, budget, None)):
                self.frame._commit_video_settings()
            self.assertEqual(vm.executor._max_workers + vm.stitch_executor._max_workers, budget)
            self.assertFalse(hasattr(self.frame, 'row_col11'))

    def test_maximum_resets_old_trial_and_uses_joint_budget_without_refresh(self):
        self.warm_current_window()
        vm = self.frame.video_manager
        self.frame.cache_multiplier.ChangeValue('3')
        vm.perf_monitor.stage_costs = Mock(return_value=(.72, .24, .5))
        for mode, budget in ((3, 12), (4, 16)):
            old = vm._thread_allocator
            old.trial = dict(source=(1, 1), target=(3, 1), samples=0, baseline=.01)
            self.frame.power_mode.SetSelection(mode - 1)
            with patch('mulimgviewer.src.main.resource_budget',
                       return_value=ResourceBudget(mode, budget, 2 * 1024 ** 3)):
                self.frame.on_power_mode_changed(None)
            self.pump_until(lambda budget=budget: vm._pending_thread_plan is None and
                vm.executor._max_workers + vm.stitch_executor._max_workers == budget)
            self.assertIsNot(vm._thread_allocator, old)
            self.assertTrue(vm._thread_allocator.throughput_first)
            self.assertIsNone(vm._thread_allocator.trial)

    def test_mode_memory_reference_does_not_shrink_after_own_cache_warms(self):
        self.frame.power_mode.SetSelection(2)
        with patch('mulimgviewer.src.main.available_memory_bytes', return_value=8 * 1024 ** 3):
            self.frame._apply_resource_policy()
        performance = self.frame.shared_config.memory_budget
        self.frame.power_mode.SetSelection(3)
        with patch('mulimgviewer.src.main.available_memory_bytes', return_value=1024 ** 3):
            self.frame._apply_resource_policy()
        self.assertEqual(performance, 4 * 1024 ** 3)
        self.assertEqual(self.frame.shared_config.memory_budget, 6 * 1024 ** 3)

    def _set_test_power(self, mode, budget, memory):
        self.frame.power_mode.SetSelection(mode - 1)
        with patch('mulimgviewer.src.main.resource_budget', return_value=ResourceBudget(mode, budget, memory)):
            self.frame.on_power_mode_changed(None)

    def test_video_downgrade_reclaims_off_gui_and_preserves_cache_and_current_pixels(self):
        self.warm_current_window()
        self.frame.cache_multiplier.ChangeValue('3')
        self._set_test_power(4, 12, 2 * 1024 ** 3)
        vm = self.frame.video_manager
        self.pump_until(lambda: vm._pending_thread_plan is None and not vm.cache_update_pending()
                        and not vm._pending_extract and not vm._window_stitches)
        before = list(self.frame.shared_config.cache_img)
        image = self.frame.show_bmp_in_panel
        old_pools = (vm.executor, vm.stitch_executor)
        entered, release = threading.Event(), threading.Event()
        def reclaim(trim):
            self.assertFalse(wx.IsMainThread())
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI failed to release reclamation')
            return {}
        self.native_release.side_effect = reclaim
        try:
            self._set_test_power(1, 2, 128 * 1024 ** 2)
            self.assertTrue(entered.wait(3))
            heartbeat = []
            wx.CallAfter(lambda: heartbeat.append(True))
            self.pump_until(lambda: bool(heartbeat))
            self.assertEqual(vm._extract_threads + vm._stitch_threads, 2)
            self.assertTrue(all(not thread.is_alive() for pool in old_pools for thread in pool._threads))
            self.assertEqual(self.frame.shared_config.cache_img, before)
            self.assertTrue(all(Path(path).exists() for path in before if path))
            self.assertIs(self.frame.show_bmp_in_panel, image)
            self.assertIsNone(vm._display_future)
        finally:
            release.set()
        self.frame.memory_reclaimer.future.result(timeout=3)

    def test_resolved_video_tools_decode_without_inherited_path(self):
        vm = self.frame.video_manager
        # Discover this installation first. CI may use Chocolatey or a system
        # package rather than Conda; explicit absolute overrides model an IDE
        # with no inherited PATH on every supported installation layout.
        tools,_=resolve_video_tools()
        with patch.dict(os.environ, PATH='',FFMPEG_BINARY=tools['ffmpeg'],FFPROBE_BINARY=tools['ffprobe']):
            vm._video_tools, vm._video_tools_env = resolve_video_tools()
            self.assertTrue(Path(vm._video_command('ffmpeg')).is_absolute())
            fps, total = vm._get_meta(self.frame.shared_config.real_video_path[0])
            self.assertAlmostEqual(fps, 10.)
            self.assertEqual(total, 80)
            self.warm_current_window()
            self.assertIsNotNone(self.frame.img_last.GetBitmap())

    def test_image_downgrade_reclaims_after_shrink_and_preserves_thirteen_pages(self):
        self._use_image_input()
        self._set_test_power(4, 12, 2 * 1024 ** 3)
        pipeline = self.frame.image_pipeline
        self.pump_until(lambda: len(pipeline.cache) == 13 and not pipeline.running
                        and pipeline.displayed_key is not None)
        self.assertIsNone(pipeline.display_future)
        before = {batch: entry[0] for batch, entry in pipeline.cache.items()}
        image, old_pool = self.frame.show_bmp_in_panel, pipeline.pool
        self.native_release.reset_mock()
        self._set_test_power(1, 2, 128 * 1024 ** 2)
        self.pump_until(lambda: pipeline.workers == 2 and self.native_release.called)
        self.frame.memory_reclaimer.future.result(timeout=3)
        self.assertTrue(all(not thread.is_alive() for thread in old_pool._threads))
        self.assertEqual({batch: entry[0] for batch, entry in pipeline.cache.items()}, before)
        self.assertTrue(all(Path(path).exists() for path in before.values()))
        self.assertIs(self.frame.show_bmp_in_panel, image)

    def test_playing_downgrade_does_not_force_working_set_trim(self):
        self.warm_current_window()
        self.frame.cache_multiplier.ChangeValue('3')
        self._set_test_power(4, 12, 2 * 1024 ** 3)
        vm = self.frame.video_manager
        self.pump_until(lambda: vm._pending_thread_plan is None and not vm.cache_update_pending())
        self.native_release.reset_mock()
        self.frame.shared_config.is_playing = True
        try:
            self._set_test_power(1, 2, 128 * 1024 ** 2)
            self.pump_until(lambda: self.native_release.called)
            self.frame.memory_reclaimer.future.result(timeout=3)
            self.native_release.assert_called_once_with(False)
        finally:
            self.frame.shared_config.is_playing = False
            self.frame.play_timer.Stop()

    def test_extreme_playback_presents_adjacent_frames_and_records_real_fps(self):
        vm = self.frame.video_manager
        vm.update_cache()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20
                        and not vm._pending_extract and not vm._window_stitches)
        del vm._mark_batch_processed  # Enable the production feedback controller.
        self.frame.interval.ChangeValue('0.001')
        self.frame.cache_multiplier.ChangeValue('3')
        displayed = []
        paint = self.frame.display_bitmap
        def record(*args, **kwargs):
            if self.frame.shared_config.is_playing:
                displayed.append(self.frame.shared_config.batch_idx)
            return paint(*args, **kwargs)
        try:
            with patch.object(self.frame, 'display_bitmap', record):
                self.frame.toggle_play(None)
                self.run_timer_until(lambda: len(displayed) >= 8)
            self.assertEqual(displayed, list(range(21, 21 + len(displayed))))
            self.assertGreater(vm.perf_monitor.get_fps(), 0)
            self.assertEqual(float(self.frame.interval.GetValue()), self.frame.shared_config.interval)
            self.assertGreaterEqual(self.frame.shared_config.interval, 0.001)
        finally:
            self.frame.shared_config.is_playing = False
            self.frame.play_timer.Stop()

    def test_gui_hit_and_performance_checks_do_not_stat_files(self):
        self.warm_current_window()
        vm = self.frame.video_manager
        gui_stats = []
        original = os.path.getsize
        def check(path):
            if wx.IsMainThread():
                gui_stats.append(str(path))
            return original(path)
        self.frame._video_display_key = None
        with patch.object(os.path, 'getsize', check):
            vm.update_cache()
            vm._compute_buffer_depth()
            self.frame.show_img()
            self.pump_until(lambda: (getattr(self.frame, '_video_display_key', None) or (None,))[0] == 20)
        self.assertEqual(gui_stats, [])

    def test_cached_frame_displays_during_blocked_disk_cleanup(self):
        self.warm_current_window()
        entered, release = threading.Event(), threading.Event()
        vm = self.frame.video_manager
        original = Path.unlink
        def slow_unlink(path, *args, **kwargs):
            if path.name == 'page_000015.png':
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('GUI did not release disk cleanup')
            return original(path, *args, **kwargs)
        try:
            with patch.object(Path, 'unlink', slow_unlink):
                self.frame.shared_config.batch_idx = 24
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                self.frame.show_img()
                self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 24)
                self.assertFalse(release.is_set())
        finally:
            release.set()

    def test_layout_invalidation_does_not_wait_for_blocked_disk_scan(self):
        self.warm_current_window()
        entered, release, expired = threading.Event(), threading.Event(), threading.Event()
        vm = self.frame.video_manager
        original = vm._trim_video_window
        def slow_scan():
            self.assertFalse(wx.IsMainThread())
            entered.set()
            if not release.wait(5):expired.set()
            return original()
        try:
            # Block the actual maintenance entry point. Raw readiness no longer
            # rescans every JPEG with getsize before each stitch.
            with patch.object(vm, '_trim_video_window', slow_scan):
                self.frame.shared_config.batch_idx = 24
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                vm._invalidate_stitch_cache()
                vm.update_cache()
                heartbeat = []
                wx.CallAfter(lambda: heartbeat.append(True))
                self.pump_until(lambda: bool(heartbeat))
                self.assertFalse(expired.is_set())
                self.assertFalse(release.is_set())
        finally:
            release.set()

    def test_many_requests_coalesce_to_the_latest_batch(self):
        self.warm_current_window()
        entered, release = threading.Event(), threading.Event()
        vm = self.frame.video_manager
        original = vm._update_cache_worker
        handled = []
        def blocked(serial, config, generation):
            handled.append(config.batch_idx)
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI did not release cache scheduler')
            return original(serial, config, generation)
        try:
            with patch.object(vm, '_update_cache_worker', blocked):
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                for batch in range(21, 61):
                    self.frame.shared_config.batch_idx = batch
                    vm.update_cache()
                release.set()
                self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 60)
            self.assertEqual(handled, [20, 60])
        finally:
            release.set()

    def test_cached_frames_do_not_rebind_or_relayout_placeholder(self):
        self.warm_current_window()
        with patch.object(self.frame.img_last, 'Bind') as bind, patch.object(self.frame.scrolledWindow_img, 'Layout') as layout:
            for _ in range(100):
                self.frame._ensure_img_bindings()
                self.frame._set_placeholder_visible(False)
        bind.assert_not_called()
        layout.assert_not_called()

    def test_video_snapshot_does_not_deepcopy_all_frame_names(self):
        class ReadOnlyNames(list):
            def __deepcopy__(self, memo):
                raise AssertionError('Whole-video filenames were copied')
        manager = self.frame.ImgManager
        manager.name_list = ReadOnlyNames([['frame.jpeg'] * 100000])
        snapshot = manager.video_stitch_snapshot()
        self.assertIs(snapshot.name_list, manager.name_list)
        self.assertIsNot(snapshot.layout_params, manager.layout_params)

    def test_deleted_cached_png_recovers_asynchronously(self):
        self.warm_current_window()
        vm = self.frame.video_manager
        path = Path(vm._cached_batch_path(24, validate=False))
        path.unlink()
        self.frame.shared_config.batch_idx = 24
        self.frame.show_img()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 24)
        self.assertTrue(path.is_file())

    def test_busy_pools_rebalance_in_background_without_blocking_gui(self):
        entered, release = threading.Event(), threading.Event()
        vm = self.frame.video_manager
        original = vm._save_frame
        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release decoding')
            return original(*args, **kwargs)
        try:
            with patch.object(vm, '_save_frame', delayed):
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                vm._request_thread_plan(1, 3)
                heartbeat = []
                wx.CallAfter(lambda: heartbeat.append(True))
                self.pump_until(lambda: bool(heartbeat))
                self.assertFalse(release.is_set())
                self.assertEqual((vm.executor._max_workers, vm.stitch_executor._max_workers), (1, 3))
                release.set()
                self.pump_until(lambda: vm._pending_thread_plan is None
                                and (vm._extract_threads, vm._stitch_threads) == (1, 3))
            self.assertEqual(vm.shared_config.thread_allocation['extract'], 1)
            self.assertEqual(vm.shared_config.thread_allocation['stitch'], 3)
            # Pool publication occurs on a worker; its wx tooltip delivery is
            # a separate queued event and can follow the state change.
            self.pump_until(lambda: self.frame.power_mode.GetToolTip() is not None
                and self.frame.video_manager._extract_threads==1)
            self.assertEqual(self.frame.video_manager._extract_threads,1)
            self.assertIn('Active: Decode:',self.frame.power_mode.GetToolTip().GetTip())
        finally:
            release.set()

    def test_live_rebalance_keeps_running_stitches_and_updates_queued_work(self):
        self.warm_current_window()
        vm = self.frame.video_manager
        preserved = Path(vm._cached_batch_path(20, validate=False))
        original_bytes = preserved.read_bytes()
        for batch in range(22, 27):
            Path(vm._cached_batch_path(batch, validate=False)).unlink()
            self.frame.shared_config.cache_img[batch] = None
        entered, release = threading.Event(), threading.Event()
        calls = []
        original = vm._run_window_stitch_impl
        def compose(batch, sources, token, plan=None, **kwargs):
            calls.append((batch, plan))
            # Borrowed CPU slots may legitimately start 23-25 before the
            # GUI changes quotas. Occupy all four permits so page 26 is
            # demonstrably queued when the new reservation is published.
            if 22 <= batch <= 25:
                if sum(22 <= item[0] <= 25 for item in calls) == 4:
                    entered.set()
                if not release.wait(5):
                    raise TimeoutError('GUI did not release current composition')
            return original(batch, sources, token, plan, **kwargs)
        try:
            with patch.object(vm, '_run_window_stitch_impl', compose):
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                vm._request_thread_plan(2, 2)
                heartbeat = []
                wx.CallAfter(lambda: heartbeat.append(True))
                self.pump_until(lambda: bool(heartbeat))
                release.set()
                self.pump_until(lambda: vm._pending_thread_plan is None and
                    not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
            self.assertTrue(any(batch == 26 and plan == (2, 2) for batch, plan in calls))
            self.assertFalse(any(batch == 26 and plan == (3, 1) for batch, plan in calls))
            self.assertEqual(preserved.read_bytes(), original_bytes)
            self.assertTrue(all(vm._cached_batch_path(batch, validate=False) for batch in range(14, 27)))
        finally:
            release.set()

    def test_power_tooltip_shows_cached_measurements_and_real_playback_fps(self):
        self.frame.resource_monitor.read_snapshot = Mock(return_value=dict(
            cpu=32.5, memory=1.5 * 1024 ** 3, fps=24., available=True))
        self.frame.shared_config.is_playing = True
        try:
            self.frame._show_resource_tooltip()
            text = self.frame.power_mode.GetToolTip().GetTip()
            self.assertIn('Average (10s): CPU 32.5%', text)
            self.assertIn('RAM 1.50 GiB', text)
            self.assertIn('24.0 FPS', text)
            self.assertIn('Decode:', text)
        finally:
            self.frame.shared_config.is_playing = False

    def test_power_tooltip_second_line_counts_actual_save_work_and_hides_finished_work(self):
        from mulimgviewer.src.export_async import ExportControl
        from mulimgviewer.src.custom_pipeline import WorkBudget
        control=ExportControl(threading.Event());budget=WorkBudget();budget.configure(2,1024)
        control.set_budget(budget)
        self.frame._export_control=control;self.frame._export_active=True
        try:
            with control.working(),control.working(),budget.acquire(1):
                self.frame._refresh_power_tooltip()
                lines=self.frame.power_mode.GetToolTip().GetTip().splitlines()
                self.assertEqual(len(lines),4)
                self.assertTrue(lines[1].endswith('| Save: 2'))  # Nested coordinator work counts once.
            self.assertEqual(control.active_count(),0)
            with control.working():
                self.frame._export_active=False
                self.frame._refresh_power_tooltip()
                self.assertTrue(self.frame.power_mode.GetToolTip().GetTip().splitlines()[1].endswith('| Save: 0'))
        finally:self.frame._export_active=False

    def test_paused_save_work_is_excluded_from_active_count(self):
        from mulimgviewer.src.export_async import ExportControl
        control=ExportControl(threading.Event());entered=threading.Event();finished=threading.Event()
        control.toggle();control.on_paused=entered.set
        def work():
            with control.working():control.checkpoint()
            finished.set()
        thread=threading.Thread(target=work);thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(control.active_count(),0)
            control.toggle();self.assertTrue(finished.wait(2))
            self.assertEqual(control.active_count(),0)
        finally:
            control.cancel.set();control.ready.set();thread.join(timeout=2)

    def test_paused_decoder_holding_memory_is_not_reported_as_active_save_work(self):
        from mulimgviewer.src.export_async import ExportControl
        from mulimgviewer.src.custom_pipeline import WorkBudget
        control=ExportControl(threading.Event());budget=WorkBudget();budget.configure(1,1024)
        control.set_budget(budget);entered=threading.Event();control.toggle();control.on_paused=entered.set
        def work():
            from concurrent.futures import CancelledError
            try:
                with budget.acquire(32):control.checkpoint()
            except CancelledError:pass
        thread=threading.Thread(target=work);thread.start()
        try:
            self.assertTrue(entered.wait(2));self.assertEqual(control.active_count(),0)
            self.assertEqual(budget.bytes,32)  # Live decoder pixels still need their memory reservation.
        finally:
            control.cancel.set();control.ready.set();thread.join(timeout=2)
        self.assertEqual(budget.active,0);self.assertEqual(budget.bytes,0)

    def test_power_tooltip_is_concise_and_shows_actual_stage_usage(self):
        cfg=self.frame.shared_config
        cfg.manual_interval=1.;cfg.interval=1.
        group=self.frame.video_manager._pipeline_workers
        with patch.object(group,'total_budget',3), patch.object(
                group,'activity_snapshot',side_effect=AssertionError('No history scan on GUI')), patch.object(
                self.frame.image_pipeline.processing,'snapshot',side_effect=AssertionError('No cache scan on GUI')):
            self.frame._refresh_power_tooltip()
        text=self.frame.power_mode.GetToolTip().GetTip()
        self.assertEqual(len(text.splitlines()),4)
        self.assertIn('(limit: 3)',text)
        self.assertIn('Active: Decode:',text)
        self.assertIn('Process:',text)
        self.assertIn('Stitch:',text)
        self.assertIn('Compose:',text)
        self.assertNotIn('Reserved',text)
        self.assertNotIn('Active slots',text)
        self.assertNotIn('queued',text)
        self.assertNotIn('manual minimum',text)

    def test_final_png_write_remains_charged_to_compose_in_images_and_video(self):
        save=Image.Image.save
        def make_sampler(samples):
            def saving(image,path,*args,**kwargs):
                name=Path(path).name if isinstance(path,(str,Path)) else ''
                if name.startswith(('__image_','__tmp_batch_')):
                    budget=self.frame.image_pipeline.processing.budget
                    with budget.condition:samples.append(budget.active_by_stage[2])
                return save(image,path,*args,**kwargs)
            return saving
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_all_func.SetValue(True)
            self.frame.show_unit.SetValue(False)
            self.frame.show_all_func_layout.ChangeValue('2,1')
            samples=[]
            with patch.object(Image.Image,'save',make_sampler(samples)):
                self.frame.refresh(None)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
                else:self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            self.assertTrue(samples)
            self.assertTrue(all(count>0 for count in samples))

    def test_power_change_preserves_four_stage_shared_admission(self):
        self.frame.show_all_func.SetValue(True)
        self.frame.show_all_func_layout.ChangeValue('2,1')
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        for mode in (0,3):
            self.frame.power_mode.SetSelection(mode)
            self.frame.on_power_mode_changed(None)
            group=self.frame.video_manager._pipeline_workers
            budget=self.frame.image_pipeline.processing.budget
            self.assertIs(budget.reservation.__self__,group)
            self.assertIs(budget.capacity.__self__,group)

    def test_invalid_cache_inputs_preserve_last_valid_values_and_show_inline_error(self):
        self.frame.cache_frames.ChangeValue('3')
        self.frame.cache_multiplier.ChangeValue('2')
        self.frame._commit_video_settings()
        for text in ('0.5', '1.5', '0', '-1', 'NaN', 'inf', 'abc'):
            self.frame.cache_frames.ChangeValue(text)
            self.frame._commit_video_settings()
            self.assertEqual(self.frame.shared_config.cache_num, 3)
            self.assertEqual(self.frame.cache_frames.GetValue(), text)
            self.assertIn('integer >= 1', self.frame.cache_frames.GetToolTip().GetTip())
            self.assertTrue(self.frame._performance_input_errors)
        self.frame.cache_frames.ChangeValue('1')
        self.frame._commit_video_settings()
        self.assertEqual(self.frame.shared_config.cache_num, 1)
        self.assertFalse(self.frame._performance_input_errors)
        self.assertEqual(self.frame.cache_frames.GetBackgroundColour(), self.frame.cache_frames._cache_input_background)
        self.frame.cache_multiplier.ChangeValue('0.5')
        self.frame._commit_video_settings()
        self.assertEqual(self.frame.shared_config.cache_multiplier, 2)
        self.assertTrue(self.frame._performance_input_errors)

    def test_cache_radius_one_plays_with_bounded_raw_readiness_and_three_pngs(self):
        self.frame.cache_frames.ChangeValue('1')
        self.frame.cache_multiplier.ChangeValue('1')
        self.frame._commit_video_settings()
        vm = self.frame.video_manager
        vm.update_cache()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20
                        and not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
        self.assertEqual(vm._stitch_window, (19, 21))
        self.assertEqual(vm._raw_buffer_inventory(1), (0, 0, 1))
        self.assertEqual(len(vm._raw_ready_batches), 6)
        vm._mark_batch_processed = lambda: None
        self.frame.interval.ChangeValue('.05')
        self.frame.toggle_play(None)
        try:
            self.run_timer_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] >= 23)
        finally:
            self.frame.shared_config.is_playing = False
            self.frame.play_timer.Stop()
        self.pump_until(lambda: not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
        self.assertLessEqual(len(vm._raw_ready_batches), 6)

    def test_layout_change_cancels_a_pending_thread_plan(self):
        self.warm_current_window()
        vm = self.frame.video_manager
        # Do not let the coordinator consume the queued request until invalidated.
        entered, release = threading.Event(), threading.Event()
        def block():
            entered.set()
            release.wait(5)
        gate = vm._cache_executor.submit(block)
        try:
            self.assertTrue(entered.wait(2))
            vm._request_thread_plan(1, 3)
            vm._invalidate_stitch_cache()
            release.set()
            gate.result(timeout=3)
            self.pump_until(lambda: not vm._rebalance_queued)
            self.assertIsNone(vm._pending_thread_plan)
            self.assertEqual((vm._extract_threads, vm._stitch_threads), (1, 3))
        finally:
            release.set()

    def test_accurate_layout_budget_replans_before_first_page_is_produced(self):
        cfg=self.frame.shared_config
        cfg.thread=12
        cfg.memory_budget=2*1024**3
        self.frame.video_manager._configure_video_memory()
        vm=self.frame.video_manager
        vm._apply_thread_plan(1,1)
        self.assertEqual(vm._extract_threads+vm._stitch_threads,2)
        entered,release=threading.Event(),threading.Event()
        original=vm._save_frame
        def hold(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise TimeoutError('Test did not release decoder')
            return original(*args,**kwargs)
        try:
            with patch.object(vm,'_save_frame',hold):
                vm.update_cache()
                self.assertTrue(entered.wait(3))
                self.assertGreater(vm._extract_threads+vm._stitch_threads,2)
                self.assertEqual(vm._pipeline_workers.total_budget,12)
                self.assertFalse(getattr(self.frame,'_video_display_key',None))
                release.set()
                self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==20)
        finally:
            release.set()

    def test_24_sources_and_100_tile_layout_use_generic_allocation(self):
        vm = self.frame.video_manager
        cfg = self.frame.shared_config
        sample = str(Path('sample.mp4').resolve())
        for budget in (4, 12):
            with self.subTest(budget=budget):
                cfg.thread = budget
                vm.update_thread_count()
                cfg.cache_num = cfg.cache_multiplier = 1
                cfg.real_video_path = [sample] * 24
                cfg.video_path = [str(Path('cache_frames') / f'budget_{budget}_video_{i}') for i in range(24)]
                cfg.video_num_list = [80] * 24
                cfg.video_fps_list = [10.0] * 24
                for directory in cfg.video_path:
                    Path(directory).mkdir(parents=True, exist_ok=True)
                self.frame.ImgManager.init(cfg.video_path, type=1, video_mode=True,
                                           video_fps_list=cfg.video_fps_list,
                                           video_num_list=cfg.video_num_list, skip=0)
                self.frame.row_col.ChangeValue('10,10')
                self.frame.show_img_init()
                k = max(1, cfg.count_per_action)
                target = max(0, min(2, (80 + k - 1) // k - 1))
                cfg.batch_idx = target
                self.frame.ImgManager.set_action_count(target)
                vm.update_cache()
                self.pump_until(lambda target=target: (getattr(self.frame, '_video_display_key', None) or (None,))[0] == target
                                and (getattr(self.frame, '_video_display_key', None) or (None, None, None))[2] == vm._window_token
                                and not vm.cache_update_pending() and not vm._pending_extract
                                and not vm._window_stitches, timeout=30)
                indices, _ = vm._playback_video_indices()
                costs = vm.perf_monitor.stage_costs(indices, plan=(vm._extract_threads, vm._stitch_threads))
                self.assertIsNotNone(costs)
                cfg.is_playing = True
                try:
                    vm._maybe_evaluate_performance(force=True)
                    recommendation = cfg.thread_allocation_recommend
                    self.assertLessEqual(recommendation['extract'] + recommendation['stitch'], budget)
                    self.assertGreaterEqual(recommendation['extract'], 1)
                    self.assertGreaterEqual(recommendation['stitch'], 1)
                finally:
                    cfg.is_playing = False
                    self.frame.play_timer.Stop()
                self.pump_until(lambda: vm._pending_thread_plan is None)

    def test_budget_display_updates_even_when_pool_sizes_stay_the_same(self):
        vm = self.frame.video_manager
        self.frame.shared_config.thread = 12
        vm._apply_thread_plan(3, 1)
        self.assertEqual(self.frame.shared_config.thread_allocation['budget'], 12)
        original = vm.executor
        self.frame.shared_config.thread = 4
        vm.update_thread_count()
        self.assertIs(vm.executor, original)
        self.assertEqual(self.frame.shared_config.thread_allocation, dict(budget=4, extract=3, stitch=1))

    def test_same_stage_plan_still_refreshes_global_cpu_and_memory_limits(self):
        vm, cfg = self.frame.video_manager, self.frame.shared_config
        cfg.memory_budget = None
        cfg.thread = 4
        vm._apply_thread_plan(3, 1)
        group, pool = vm._pipeline_workers, vm._pipeline_workers.pool
        cfg.thread = 12
        cfg.memory_budget = 2 * 1024**3
        vm._apply_thread_plan(3, 1)
        self.assertIs(group.pool, pool)
        self.assertEqual(group.total_budget, 12)
        self.assertEqual(group.memory_budget, vm._planning_memory_budget())
        self.assertEqual(vm._admission_optimizer.snapshot()['ceiling'], 12)

    def test_explicit_resume_restarts_admission_measurement_without_rebuilding_pool(self):
        self._set_test_power(4,4,2*1024**3)
        vm = self.frame.video_manager
        vm._admission_limit()
        tuner = vm._admission_optimizer
        tuner.limit, tuner.best = 2,4
        tuner.start, tuner.best_period, tuner.frames = 0.,1.,100
        vm._initialize_thread_pools()
        pool=vm._pipeline_workers.pool
        self.assertEqual(vm._pipeline_workers.total_budget,2)
        self.frame.toggle_play(None)
        self.assertTrue(self.frame.shared_config.is_playing)
        self.assertIs(vm._pipeline_workers.pool,pool)
        self.assertEqual(vm._pipeline_workers.total_budget,4)
        self.assertIsNone(tuner.start)
        self.assertIsNone(tuner.best_period)

    def test_stage_plan_change_discards_incomparable_total_concurrency_trial(self):
        vm,cfg=self.frame.video_manager,self.frame.shared_config
        cfg.power_mode,cfg.thread,cfg.memory_budget=4,12,None
        vm._apply_thread_plan(9,3)
        tuner=vm._admission_optimizer
        tuner.limit=tuner.best=6
        tuner.best_period=.1
        tuner.frames=100
        vm._initialize_thread_pools()
        self.assertEqual(vm._pipeline_workers.total_budget,6)
        pool=vm._pipeline_workers.pool
        vm._apply_thread_plan(8,4)
        self.assertIs(vm._pipeline_workers.pool,pool)
        self.assertEqual(vm._pipeline_workers.total_budget,12)
        self.assertEqual(tuner.limit,12)
        self.assertIsNone(tuner.best_period)
        self.assertEqual(tuner.frames,0)

    def _use_image_input(self):
        self.frame.shared_config.video_mode = False
        folders = [Path('images/a'), Path('images/b')]
        for folder in folders:
            folder.mkdir(parents=True)
            for index in range(80):
                Image.new('RGB', (80, 48), (index, 20, 30)).save(folder / f'{index:03}.png')
        self.frame.ImgManager.init([str(p) for p in folders], type=1, video_mode=False)
        self.frame.row_col.ChangeValue('1,2')
        self.frame.cache_frames.ChangeValue('2')
        self.frame.cache_multiplier.ChangeValue('3')
        self.frame._commit_video_settings()
        self.frame.show_img_init()
        self.frame.shared_config.batch_idx = 20
        self.frame.ImgManager.set_action_count(20)

    def test_custom_image_results_are_disk_cached_without_prefetch_exports(self):
        from mulimgviewer.src.custom_func import main as utils_img
        self._use_image_input()
        self.frame.out_path_str=str(Path('output').absolute())
        self.frame.customfunc_choice.SetStringSelection('Image Darkening')
        original=utils_img.main
        threads=[]
        def process(*args,**kwargs):
            threads.append(wx.IsMainThread())
            return original(*args,**kwargs)
        with patch.object(utils_img,'main',process):
            self.frame.show_custom_func.SetValue(True)
            self.frame.on_show_custom_func_changed(None)
            self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
            pipeline=self.frame.image_pipeline
            self.pump_until(lambda:pipeline.displayed_key is not None and len(pipeline.cache)==13 and not pipeline.running)
            self.assertTrue(threads)
            self.assertFalse(any(threads))
            count=len(threads)
            generation=pipeline.generation
            for batch in (21,20):
                self.frame.shared_config.batch_idx=batch
                self.frame.ImgManager.set_action_count(batch)
                self.frame.show_img_init();self.frame.show_img()
                self.pump_until(lambda batch=batch:pipeline.displayed_key is not None and pipeline.displayed_key[1]==batch)
            self.assertEqual(len(threads),count)
            self.assertEqual(pipeline.generation,generation)
            self.assertTrue(Path(pipeline.cache[20][0]).is_file())
        self.assertFalse(Path('output/processing_function').exists())

    def test_show_all_state_returns_from_worker_and_skips_invisible_algorithms(self):
        from mulimgviewer.src.custom_func import main as utils_img
        self._use_image_input()
        self.frame.show_all_func_layout.ChangeValue('4,2')
        original=utils_img.main
        installed=utils_img.get_available_algorithms()
        rows=4
        self.frame.func_layout_vertical.SetValue(False)
        algorithms=[]
        def process(*args,**kwargs):
            self.assertFalse(wx.IsMainThread())
            algorithms.append(kwargs.get('algorithm_type'))
            return original(*args,**kwargs)
        with patch.object(utils_img,'main',process):
            self.frame.show_all_func.SetValue(True)
            self.frame.on_show_all_func_changed(None)
            self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
            self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            manager=self.frame.ImgManager
            self.assertTrue(manager._show_all_func_enabled)
            self.assertEqual(manager._original_row_col,[1,2])
            self.assertEqual(manager._show_all_func_layout,(rows,2))
            self.assertEqual(len(manager.xy_grid),rows*2*2)
            self.assertTrue(algorithms)
            self.assertTrue(all(installed[index]!='Original' for index in algorithms))
            self.assertFalse(self.frame.show_custom_func.GetValue())

    def test_two_row_canvas_hides_original_and_keeps_hidden_algorithms_idle(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        from mulimgviewer.src.custom_func.contract import processing_indices
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_all_func_layout.ChangeValue('2,1')
            self.frame.show_custom_func.SetValue(False)
            self.frame.show_all_func.SetValue(True)
            for show_original in (False,True):
                self.frame.show_unit.SetValue(show_original)
                self.frame.refresh(None)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None
                        and self.frame.image_pipeline.displayed_key[:2]==(self.frame.image_pipeline.generation,self.frame.shared_config.batch_idx))
                manager=self.frame.ImgManager
                self.assertEqual(manager._show_all_func_layout,(2,1))
                self.assertEqual(len(manager.xy_grid),4)
                registry=manager._custom_algorithm_registry
                selected=processing_indices(registry,manager.layout_params)
                self.assertEqual(len(selected),1 if show_original else 2)
                model=IndexCatalog(manager,self.frame.shared_config)
                entries=[model.visual_entry(i) for i in range(model.visual_page_start(20),model.visual_page_start(21))]
                names={entry['algorithm'] for entry in entries}
                self.assertEqual('Original' in names,show_original)
                self.assertEqual(names,({'Original'} if show_original else set())|{registry[i][0] for i in selected})
                cache=self.frame.image_pipeline.processing
                self.assertTrue(list((cache.visible.root/'original'/'stitched').glob('*.png')))

    def test_shrinking_algorithm_canvas_retires_hidden_processing_and_mosaic_caches(self):
        from mulimgviewer.src.custom_func import main as functions
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_custom_func.SetValue(False)
            self.frame.show_all_func.SetValue(True)
            self.frame.show_unit.SetValue(True)
            self.frame.show_all_func_layout.ChangeValue('6,1')
            self.frame.refresh(None)
            vm=self.frame.video_manager;pipeline=self.frame.image_pipeline
            def quiet(pipeline=pipeline,video=video,vm=vm):
                if video:
                    return (getattr(self.frame,'_video_display_key',(None,))[-1]==vm._window_token
                        and not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
                return pipeline.displayed_key is not None and not pipeline.running
            self.pump_until(quiet)
            registry=self.frame.ImgManager._custom_algorithm_registry
            names=[entry[0] for entry in registry if entry[0]!='Original']
            root=pipeline.processing.visible.root
            for name in names:
                self.assertTrue(list((root/name/'processed').rglob('*.png')),name)
                self.assertTrue(list((root/name/'stitched').glob('*.png')),name)
            calls=[];original=functions.main
            def process(calls,original,*args,**kwargs):
                calls.append(kwargs.get('algorithm_type'))
                return original(*args,**kwargs)
            with patch.object(functions,'main',partial(process,calls,original)):
                self.frame.show_unit.SetValue(False)
                self.frame.show_all_func_layout.ChangeValue('2,1')
                self.frame.refresh(None)
                self.pump_until(quiet)
                self.pump_until(lambda names=tuple(names),root=root:all(not (root/name).exists() for name in names[2:]))
            active={'original',*names[:2]}
            self.assertEqual({path.name for path in root.iterdir() if path.is_dir()},active)
            self.assertTrue(all(registry[index][0] in names[:2] for index in calls))
            self.assertTrue(all(entry.get('algorithm') in active for entry in pipeline.processing.entries.values()))
            self.assertEqual(self.frame.ImgManager._show_all_func_layout,(2,1))

    def test_custom_controls_are_generated_names_and_input_is_not_saved(self):
        from mulimgviewer.src.configuration import settings_controls
        from mulimgviewer.src.custom_func.main import get_available_algorithms
        self.assertIs(self.frame.custom_algorithm_input,self.frame.addfunc)
        self.assertTrue(hasattr(self.frame,'delfunc'))
        self.assertNotIn('addfunc',settings_controls(self.frame))
        self.assertEqual(list(self.frame.customfunc_choice.GetStrings()),get_available_algorithms())

    def test_algorithm_checkboxes_wait_for_refresh_in_images_and_video(self):
        self.warm_current_window()
        for video in (True,False):
            if not video:self._use_image_input()
            before=tuple(self.frame.ImgManager.layout_params)
            self.frame.show_all_func.SetValue(True)
            event=wx.CommandEvent(wx.EVT_CHECKBOX.typeId,self.frame.show_all_func.GetId())
            self.frame.show_all_func.GetEventHandler().ProcessEvent(event)
            self.assertTrue(self.frame._custom_settings_dirty)
            self.assertEqual(tuple(self.frame.ImgManager.layout_params),before)
            # Other cache updates/reinitializations must not leak pending settings.
            self.frame.show_img_init()
            self.assertFalse(self.frame.ImgManager.layout_params[38])
            self.frame.refresh(None)
            self.assertFalse(self.frame._custom_settings_dirty)
            self.assertTrue(self.frame.ImgManager.layout_params[38])
            if video:
                self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token
                    and self.frame.ImgManager._show_all_func_enabled)
            else:
                self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            self.frame.show_all_func.SetValue(False)
            self.frame.on_show_all_func_changed(None)
            self.frame.refresh(None)

    def test_index_rejects_stale_algorithm_layout_and_labels_each_pane(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        self._use_image_input()
        before=self.frame._index_context()
        self.frame.show_all_func.SetValue(True)
        self.frame.refresh(None)
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        self.assertNotEqual(before,self.frame._index_context())
        self.assertFalse(self.frame._jump_to_index_item(20,0,before))
        model=IndexCatalog(self.frame.ImgManager,self.frame.shared_config)
        start,end=model.visual_page_start(20),model.visual_page_start(21)
        entries=[model.visual_entry(i) for i in range(start,end)]
        self.assertEqual({entry['algorithm'] for entry in entries},{'Original'}|set(self.frame.customfunc_choice.GetStrings()))
        for entry in entries:self.assertIn(entry['algorithm'],entry['item'])

    def test_auto_cache_refresh_and_unapplied_lossless_export_reject_old_jpeg(self):
        self.frame.cache_save_format.SetSelection(2)
        self.frame.save_format.SetSelection(0)
        self.frame.output_scale.ChangeValue('1,1')
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,0)
        old_token=self.frame.video_manager._window_token
        self.frame.save_format.SetSelection(2)  # Export must resolve this clicked snapshot, even before Refresh.
        output=Path('auto_lossless_export').absolute();output.mkdir()
        self.frame.out_path_str=str(output);self.frame.choice_output.SetSelection(0)
        from mulimgviewer.src.export_async import ExportDecoder
        original=ExportDecoder._save_frame;encodings=[];copied=[]
        def save_frame(decoder,path,first,last,video,config=None):
            encodings.append(config.cache_save_format)
            if decoder.cache is not None:
                cache=decoder.cache
                def checked(*args):
                    result=cache(*args);copied.append(result);return result
                decoder.cache=checked
            return original(decoder,path,first,last,video,config=config)
        with patch.object(ExportDecoder,'_save_frame',save_frame):
            self.frame.save_img(None)
            self.pump_until(lambda:not self.frame._export_active)
        self.assertTrue(encodings);self.assertTrue(all(value==1 for value in encodings))
        self.assertTrue(copied);self.assertFalse(any(copied))
        self.assertIn('success',self.frame.m_statusBar1.GetStatusText(3))
        pdfs=list(output.rglob('*.pdf'));self.assertTrue(pdfs)
        for path in pdfs:self.assertNotIn(b'/DCTDecode',path.read_bytes())
        self.assertEqual(self.frame.video_manager._window_token,old_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,0)
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        self.assertNotEqual(self.frame.video_manager._window_token,old_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,1)
        with Image.open(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx]) as image:
            self.assertEqual(image.format,'PNG')
        self.frame.output_scale.ChangeValue('1,0.5');self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,0)

    def test_jpg_policy_encodes_image_and_video_algorithm_and_composed_caches(self):
        self.frame.cache_save_format.SetSelection(0)
        self.frame.customfunc_choice.SetStringSelection('Image Enhancement')
        self.frame.show_custom_func.SetValue(True)
        self.frame.show_all_func.SetValue(False)
        for video in (True,False):
            with self.subTest(video=video):
                if not video:self._use_image_input()
                self.frame.refresh(None)
                if video:
                    token=self.frame.video_manager._window_token
                    self.pump_until(lambda token=token:getattr(self.frame,'_video_display_key',(None,))[-1]==token)
                    composed=Path(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx])
                else:
                    pipeline=self.frame.image_pipeline
                    self.pump_until(lambda pipeline=pipeline:pipeline.displayed_key is not None
                        and pipeline.displayed_key[:2]==(pipeline.generation,self.frame.shared_config.batch_idx))
                    composed=Path(pipeline.cache[self.frame.shared_config.batch_idx][0])
                stage=self.frame.image_pipeline.processing
                manager=self.frame.ImgManager;batch=self.frame.shared_config.batch_idx
                try:
                    index=next(i for i,entry in enumerate(manager._custom_algorithm_registry) if entry[0]=='Image Enhancement')
                except StopIteration as error:
                    raise AssertionError('Image Enhancement must be installed for this fixture') from error
                # Inspect the current page through its read lease. Public aliases
                # belonging to retired pages may legitimately disappear mid-rglob.
                with stage.lease_export_results(manager,list(manager.flist),batch) as leased:
                    self.assertIn(index,leased)
                    self.assertIn(index,leased['_mosaics'])
                    paths=[composed,*leased[index],leased['_mosaics'][index][0]]
                    for path in paths:
                        self.assertEqual(Path(path).suffix,'.jpeg')
                        with Image.open(path) as image:self.assertEqual(image.format,'JPEG')

    def test_cache_format_refresh_switches_png_and_jpeg_and_exports_lossless_pdf(self):
        self.warm_current_window()
        self.frame.cache_save_format.SetSelection(1)
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token
            and self.frame.ImgManager.flist and all(Path(p).suffix=='.png' for p in self.frame.ImgManager.flist))
        self.assertEqual(self.frame.shared_config.cache_save_format,1)
        with Image.open(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx]) as image:
            self.assertEqual(image.format,'PNG')
        for p in self.frame.ImgManager.flist:
            with Image.open(p) as image:self.assertEqual(image.format,'PNG')
        output=Path('lossless_pdf').absolute();output.mkdir();self.frame.out_path_str=str(output)
        self.frame.choice_output.SetSelection(6);self.frame.save_format.SetSelection(2)
        self.frame.xy_magnifier=[[2,2,12,10,1,1,False]]
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        self.frame.save_img(None)
        self.pump_until(lambda:not self.frame._export_active)
        self.assertIn('success',self.frame.m_statusBar1.GetStatusText(3))
        pdfs=list(output.rglob('*.pdf'));self.assertTrue(pdfs)
        for p in pdfs:self.assertNotIn(b'/DCTDecode',p.read_bytes(),str(p))
        self.frame.cache_save_format.SetSelection(0);self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token
            and self.frame.ImgManager.flist and all(Path(p).suffix=='.jpeg' for p in self.frame.ImgManager.flist))
        composed=Path(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx])
        self.assertEqual(composed.suffix,'.jpeg')
        with Image.open(composed) as image:self.assertEqual(image.format,'JPEG')

    def test_alpha_sliders_refresh_preview_export_snapshot_and_configuration(self):
        from mulimgviewer.src.configuration import settings_controls,control_value,apply_value
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        old_token=self.frame._image_layout_token
        self.frame.foreground_slider.SetValue(96);self.frame.foreground_alpha(None)
        self.frame.background_slider.SetValue(48);self.frame.background_alpha(None)
        self.assertEqual(self.frame.ImgManager.img_alpha,255)
        self.assertEqual(self.frame._image_layout_token,old_token)
        self.frame.refresh(None)
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        self.assertNotEqual(self.frame._image_layout_token,old_token)
        self.assertEqual(self.frame.ImgManager.img_alpha,96)
        self.assertEqual(self.frame.ImgManager.gap_color[3],48)
        path=self.frame.image_pipeline.cache[20][0]
        with Image.open(path) as image:
            alphas=set(image.convert('RGBA').getchannel('A').getdata())
            self.assertIn(96,alphas);self.assertIn(48,alphas)
        controls=settings_controls(self.frame)
        self.assertEqual(control_value('foreground_slider',controls['foreground_slider']),96)
        self.assertEqual(control_value('background_slider',controls['background_slider']),48)
        apply_value('foreground_slider',controls['foreground_slider'],128)
        self.assertEqual(self.frame.foreground_slider.GetValue(),128)
        apply_value('foreground_slider',controls['foreground_slider'],999)
        self.assertEqual(self.frame.foreground_slider.GetValue(),128)
        # Restore staged value before capturing the applied render for export.
        self.frame.foreground_slider.SetValue(96)
        output=Path('alpha_export').absolute();output.mkdir();self.frame.out_path_str=str(output)
        self.frame.save_format.SetSelection(1);self.frame.choice_output.SetSelection(0)
        self.frame.save_img(None)
        self.frame.foreground_slider.SetValue(255);self.frame.refresh(None)
        self.pump_until(lambda:not self.frame._export_active)
        self.assertIn('success',self.frame.m_statusBar1.GetStatusText(3))
        with Image.open(output/'image/composed/page_000021.png') as image:
            self.assertIn(96,set(image.convert('RGBA').getchannel('A').getdata()))

    def test_video_alpha_refresh_changes_cached_mosaic_pixels(self):
        self.warm_current_window();vm=self.frame.video_manager
        old=vm._window_token
        self.frame.foreground_slider.SetValue(96);self.frame.background_slider.SetValue(48)
        self.frame.refresh(None)
        self.pump_until(lambda:vm._window_token is not None and vm._window_token!=old
            and getattr(self.frame,'_video_display_key',(None,))[-1]==vm._window_token)
        path=vm._cached_batch_path(20,validate=False)
        with Image.open(path) as image:
            alphas=set(image.convert('RGBA').getchannel('A').getdata())
            self.assertIn(96,alphas);self.assertIn(48,alphas)
        self.assertEqual(self.frame.ImgManager.img_alpha,96)

    def test_format_refresh_removes_previous_raw_encoding_after_readers_finish(self):
        self.warm_current_window();vm=self.frame.video_manager
        for value,old_extension,new_extension in ((1,'.jpeg','.png'),(0,'.png','.jpeg')):
            self.frame.cache_save_format.SetSelection(value)
            self.frame.refresh(None)
            self.pump_until(lambda new_extension=new_extension:getattr(self.frame,'_video_display_key',(None,))[-1]==vm._window_token
                and self.frame.ImgManager.flist and all(Path(p).suffix==new_extension for p in self.frame.ImgManager.flist))
            self.pump_until(lambda:not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
            self.pump_until(lambda old_extension=old_extension:all(not list(Path(folder).glob('*'+old_extension)) for folder in self.frame.shared_config.video_path))
            self.assertTrue(all(list(Path(folder).glob('*'+new_extension)) for folder in self.frame.shared_config.video_path))

    def test_save_format_new_gui_order_and_actual_extensions(self):
        self.assertEqual(list(self.frame.save_format.GetStrings()),['jpg','png','pdf'])
        self.assertEqual(self.frame.save_format.GetSelection(),0)
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        for selection,suffix in ((0,'.jpg'),(1,'.png'),(2,'.pdf')):
            output=Path(f'format_{selection}').absolute();output.mkdir()
            self.frame.out_path_str=str(output)
            self.frame.save_format.SetSelection(selection);self.frame.choice_output.SetSelection(0)
            self.frame.save_img(None)
            self.pump_until(lambda:not self.frame._export_active)
            self.assertIn('success',self.frame.m_statusBar1.GetStatusText(3))
            path=output/'image/composed'/('page_000021'+suffix)
            self.assertTrue(path.is_file(),self.frame.m_statusBar1.GetStatusText(3))
            self.assertFalse([p for p in output.rglob('*') if p.suffix in ('.png','.jpg','.pdf') and p.suffix!=suffix])

    def test_auto_window_fit_is_manual_refresh_only_and_uses_new_image_size(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        self.frame.SetSize((1400,900));self.app.Yield(True)
        old_size=tuple(self.frame.img_size)
        self.frame.auto_layout_check.SetValue(True)
        with patch.object(self.frame,'auto_layout',wraps=self.frame.auto_layout) as layout:
            self.app.Yield(True)
            self.assertFalse([c for c in layout.call_args_list if c.kwargs.get('fit_image')])
            self.frame.show_scale.ChangeValue('.5,.5');self.frame.refresh(None)
            self.pump_until(lambda:any(c.kwargs.get('fit_image') for c in layout.call_args_list))
            fits=[c.kwargs['fit_image'] for c in layout.call_args_list if c.kwargs.get('fit_image')]
            self.assertEqual(fits,[tuple(self.frame.img_size)])
            self.assertNotEqual(fits[0],old_size)
            screen=wx.Display.GetFromWindow(self.frame)
            area=wx.Display(0 if screen==wx.NOT_FOUND else screen).GetClientArea()
            size=self.frame.GetSize()
            self.assertLessEqual(size.width,area.width);self.assertLessEqual(size.height,area.height)
            self.assertLess(size.width,1400)
            self.assertIsNone(self.frame._auto_fit_pending)
            self.frame._seek_display_page(22)
            self.pump_until(lambda:getattr(self.frame,'_status_display_batch',None)==21)
            self.assertEqual(len([c for c in layout.call_args_list if c.kwargs.get('fit_image')]),1)
            # Cached same-page Refresh still fits, even without a new bitmap.
            self.frame.refresh(None)
            self.pump_until(lambda:len([c for c in layout.call_args_list if c.kwargs.get('fit_image')])==2)
            self.frame.auto_layout_check.SetValue(False)
            self.frame.refresh(None)
            self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            self.assertEqual(len([c for c in layout.call_args_list if c.kwargs.get('fit_image')]),2)

    def test_video_auto_window_fit_waits_for_refreshed_frame(self):
        self.warm_current_window()
        self.frame.auto_layout_check.SetValue(True)
        with patch.object(self.frame,'auto_layout',wraps=self.frame.auto_layout) as layout:
            self.frame.show_scale.ChangeValue('.5,.5');self.frame.refresh(None)
            self.pump_until(lambda:any(c.kwargs.get('fit_image') for c in layout.call_args_list))
            fits=[c.kwargs['fit_image'] for c in layout.call_args_list if c.kwargs.get('fit_image')]
            self.assertEqual(fits,[tuple(self.frame.img_size)])
            self.frame._seek_display_page(22)
            self.pump_until(lambda:getattr(self.frame,'_status_display_batch',None)==21)
            self.assertEqual(len([c for c in layout.call_args_list if c.kwargs.get('fit_image')]),1)

    def test_explicit_auto_layout_call_retains_original_checkbox_behavior(self):
        native_set_size=self.frame.SetSize
        for constrained in (False,True):
            with self.subTest(constrained_desktop=constrained):
                def set_size(size,constrained=constrained):
                    # Model the native limit observed on Actions as well as
                    # testing the actual desktop. Do not change OS resolution.
                    rectangle=isinstance(size,wx.Rect)
                    width,height=size.GetSize() if rectangle else size
                    if constrained:width,height=min(width,1044),min(height,788)
                    native_set_size(wx.Rect(size.x,size.y,width,height) if rectangle else (width,height))
                with patch.object(self.frame,'SetSize',side_effect=set_size):
                    self.frame.img_size=(300,200)
                    self.frame.SetSize((1400,900))
                    self.frame.auto_layout_check.SetValue(True)
                    self.frame.auto_layout()
                    screen=wx.Display.GetFromWindow(self.frame)
                    area=wx.Display(0 if screen==wx.NOT_FOUND else screen).GetClientArea()
                    self.assertEqual(self.frame.GetSize(),wx.Size(min(1000,area.width),min(600,area.height)))
                    self.frame.SetSize((1400,900))
                    # Preserve the accepted size even if the native window
                    # manager capped the original 1400x900 request.
                    accepted_size=wx.Size(self.frame.GetSize())
                    if constrained:
                        self.assertLessEqual(accepted_size.width,1044)
                        self.assertLessEqual(accepted_size.height,788)
                    self.frame.auto_layout(frame_resize=True)
                    self.assertEqual(self.frame.GetSize(),accepted_size)
                    self.frame.auto_layout_check.SetValue(False)
                    self.frame.auto_layout()
                    self.assertEqual(self.frame.GetSize(),accepted_size)

    def test_auto_window_fit_clamps_to_monitor_work_area(self):
        self.frame.auto_layout_check.SetValue(True)
        self.frame.auto_layout(fit_image=(100000,100000))
        screen=wx.Display.GetFromWindow(self.frame)
        area=wx.Display(0 if screen==wx.NOT_FOUND else screen).GetClientArea()
        actual=self.frame.GetRect()
        self.assertEqual(actual.GetSize(),area.GetSize())
        self.assertGreaterEqual(actual.x,area.x);self.assertGreaterEqual(actual.y,area.y)
        self.assertLessEqual(actual.GetRight(),area.GetRight());self.assertLessEqual(actual.GetBottom(),area.GetBottom())

    def test_superseded_auto_window_fit_does_not_resize_new_context(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        self.frame.auto_layout_check.SetValue(True)
        self.frame._auto_fit_serial=1
        self.frame._auto_fit_pending=(1,self.frame._auto_fit_context())
        self.frame._consume_auto_window_fit((900,500))
        self.frame._auto_fit_serial=2
        with patch.object(self.frame,'auto_layout',wraps=self.frame.auto_layout) as layout:
            self.app.Yield(True)
            self.assertFalse([c for c in layout.call_args_list if c.kwargs.get('fit_image')])

    def test_esc_pauses_save_and_save_button_resumes_without_blocking_gui(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        output=Path('paused_export').absolute();output.mkdir();self.frame.out_path_str=str(output)
        entered=threading.Event();release=threading.Event();completed=[]
        def save(job,**kwargs):
            entered.set();release.wait(5)
            job._export_checkpoint();completed.append(True)
            job.SetStatusText_(['Save','-1','Save success!','-1'])
        def press():
            event=wx.CommandEvent(wx.EVT_MENU.typeId,self.frame.menu_pause_tasks.GetId())
            self.frame.GetEventHandler().ProcessEvent(event)
        self.assertEqual(self.frame.parse_hotkey(self.frame.hotkeys['pause_tasks']),(wx.ACCEL_NORMAL,wx.WXK_ESCAPE))
        try:
            with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
                self.frame.save_img(None);self.assertTrue(entered.wait(1))
                # The frame hook still works when text editing disables accelerators.
                self.frame.SetAcceleratorTable(wx.NullAcceleratorTable)
                from types import SimpleNamespace
                key=SimpleNamespace(ControlDown=lambda:False,AltDown=lambda:False,ShiftDown=lambda:False,
                    GetKeyCode=lambda:wx.WXK_ESCAPE,Skip=lambda:self.fail('Save pause key was not consumed'))
                self.frame._save_pause_key(key);release.set()
                self.pump_until(lambda:self.frame._export_status=='Save: paused')
                self.frame._save_pause_key(key)  # Repeated Esc must keep the task paused.
                press()  # The menu action has the same one-way pause semantics.
                self.assertTrue(self.frame._export_control.paused)
                self.assertFalse(self.frame._export_cancel_event.is_set())
                self.assertNotIn('F8',self.frame.hotkeys.values())
                heartbeat=[];wx.CallAfter(lambda:heartbeat.append(True));self.pump_until(lambda:heartbeat)
                self.assertFalse(completed);self.assertTrue(self.frame._export_active)
                self.assertTrue(self.frame.save_butoon.IsEnabled())
                self.frame.save_img(None)  # Save resumes the paused task, rather than creating another.
                self.pump_until(lambda:not self.frame._export_active)
                self.assertEqual(completed,[True])
                self.assertEqual(self.frame._export_status,'Save: success')
        finally:release.set()

    def test_esc_pauses_video_and_play_button_resumes_from_current_page(self):
        from types import SimpleNamespace
        self.warm_current_window()
        self.frame.interval.ChangeValue('1')
        self.frame.toggle_play(None)
        self.assertTrue(self.frame.shared_config.is_playing)
        page=self.frame.shared_config.batch_idx
        key=SimpleNamespace(ControlDown=lambda:False,AltDown=lambda:False,ShiftDown=lambda:False,
            GetKeyCode=lambda:wx.WXK_ESCAPE,Skip=lambda:self.fail('Playback pause key was not consumed'))
        self.frame._save_pause_key(key)
        self.assertFalse(self.frame.shared_config.is_playing)
        self.assertFalse(self.frame.play_timer.IsRunning())
        self.frame.pause_tasks(None)
        self.assertFalse(self.frame.shared_config.is_playing)
        self.assertEqual(self.frame.shared_config.batch_idx,page)
        self.frame.toggle_play(None)
        self.assertTrue(self.frame.shared_config.is_playing)
        self.assertEqual(self.frame.shared_config.batch_idx,page)
        self.frame.toggle_play(None)

    def test_escape_pauses_simultaneous_save_and_playback_with_independent_resume(self):
        self.warm_current_window()
        root=Path('simultaneous_pause').absolute();root.mkdir();self.frame.out_path_str=str(root)
        self.frame.interval.ChangeValue('1');self.frame.toggle_play(None)
        entered=threading.Event();release=threading.Event()
        def save(job,**kwargs):
            entered.set();release.wait(5);job._export_checkpoint()
            job.SetStatusText_(['Save','-1','Save success!','-1'])
        try:
            with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
                self.frame.save_img(None);self.assertTrue(entered.wait(1))
                self.frame.pause_tasks(None);release.set()
                self.pump_until(lambda:self.frame._export_status=='Save: paused')
                self.assertFalse(self.frame.shared_config.is_playing)
                self.assertTrue(self.frame._export_control.paused)
                self.frame.toggle_play(None)
                self.assertTrue(self.frame.shared_config.is_playing)
                self.assertTrue(self.frame._export_control.paused)
                self.frame.pause_tasks(None)
                self.frame.save_img(None)
                self.pump_until(lambda:not self.frame._export_active)
                self.assertEqual(self.frame._export_status,'Save: success')
                self.assertFalse(self.frame.shared_config.is_playing)
        finally:release.set()

    def test_cancelling_paused_export_wakes_waiters(self):
        from mulimgviewer.src.export_async import cancel_save,toggle_save_pause
        output=Path('paused_cancel').absolute();output.mkdir();self.frame.out_path_str=str(output)
        entered=threading.Event();release=threading.Event()
        def save(job,**kwargs):
            entered.set();release.wait(5);job._export_checkpoint()
        try:
            with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
                self.frame.save_img(None);self.assertTrue(entered.wait(1))
                toggle_save_pause(self.frame);release.set()
                self.pump_until(lambda:self.frame._export_status=='Save: paused')
                self.frame.cancel_save_task(None)  # Explicit cancellation remains available from its menu.
                self.pump_until(lambda:not self.frame._export_active)
                self.assertEqual(self.frame._export_status,'Save: cancelled')
                self.assertFalse(self.frame._export_pool._shutdown)
                self.assertTrue(self.frame.save_butoon.IsEnabled())
        finally:release.set()

    def test_cancelled_bulk_save_resumes_unfinished_pages_but_changed_parameters_restart(self):
        # This case asserts the exact one-worker bookmark; parallel admission is
        # covered separately and may finish later pages before cancellation.
        self.frame.shared_config.thread=1
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None
            and not self.frame.image_pipeline.running)
        self.frame.ImgManager.max_action_num=3
        self.frame.shared_config.thread=1
        output=Path('resumable_export').absolute();output.mkdir();self.frame.out_path_str=str(output)
        self.frame.auto_save_all.SetValue(True);self.frame.choice_output.SetSelection(0)
        self.frame.save_format.SetSelection(1)
        from mulimgviewer.src import export_controller as controller
        original=controller.export_page
        def run(cancel):
            pages=[]
            def export(manager,*args,**kwargs):
                result=original(manager,*args,**kwargs);pages.append(manager.action_count)
                if cancel and len(pages)==1:self.frame._export_cancel_event.set()
                return result
            with patch.object(controller,'export_page',side_effect=export):
                self.frame.save_img(None)
                self.pump_until(lambda:not self.frame._export_active and self.frame._export_future.done())
            return pages
        self.assertEqual(run(True),[0])
        self.assertEqual(self.frame._export_resume_state['completed'],1)
        self.assertEqual(run(False),[1,2])
        self.assertEqual(self.frame._export_status,'Save: success')
        self.assertEqual(run(True),[0])  # A completed job starts fresh on the next Save.
        self.frame.save_format.SetSelection(0)
        self.assertEqual(run(False),[0,1,2])  # Changed format invalidates the old bookmark.
        self.assertTrue(list(output.rglob('*.jpg')))
        self.assertEqual(run(True),[0])
        Image.effect_noise((80,48),30).convert('RGB').save(Path('images/a/000.png'))
        self.assertEqual(run(False),[0,1,2])  # Changed input bytes also invalidate continuation.

    def test_background_save_keeps_gui_responsive_and_freezes_settings(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        output=Path('async_output').absolute();output.mkdir();self.frame.out_path_str=str(output)
        entered=threading.Event();release=threading.Event();captured=[]
        def save(job,**kwargs):
            captured.append(job)
            entered.set();release.wait(5)
            job._export_progress(.5)
            job.SetStatusText_(['Save','-1','Save success!','-1'])
        try:
            with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
                self.frame.save_img(None)
                self.assertTrue(entered.wait(1))
                future=self.frame._export_future
                self.assertFalse(self.frame.save_butoon.IsEnabled())
                heartbeat=[];wx.CallAfter(lambda:heartbeat.append(True))
                self.pump_until(lambda:heartbeat)
                self.frame.output_scale.ChangeValue('2,2')
                self.frame.save_img(None)
                self.assertIs(self.frame._export_future,future)
                self.assertEqual(captured[0].ImgManager.layout_params[5],[1.,1.])
                self.assertTrue(captured[0].ImgManager.flist)
                self.frame.SetStatusText_(['-1','-1','-1','Output: changed'])
                self.assertIn('Saving',self.frame.m_statusBar1.GetStatusText(3))
                release.set()
                self.pump_until(lambda:not self.frame._export_active)
                self.assertEqual(self.frame.m_statusBar1.GetStatusText(3),'Save: success')
                self.assertTrue(self.frame.save_butoon.IsEnabled())
        finally:release.set()

    def test_background_save_cancels_without_success_when_closing(self):
        from concurrent.futures import CancelledError
        from mulimgviewer.src.export_async import cancel_save
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        output=Path('cancel_output').absolute();output.mkdir();self.frame.out_path_str=str(output)
        entered=threading.Event()
        def save(job,**kwargs):
            entered.set()
            while not job._export_cancelled():time.sleep(.005)
            raise CancelledError()
        with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
            self.frame.save_img(None);self.assertTrue(entered.wait(1))
            cancel_save(self.frame)
            self.pump_until(lambda:not self.frame._export_active)
            self.assertEqual(self.frame.m_statusBar1.GetStatusText(3),'Save: cancelled')
            self.assertFalse(list(output.rglob('*.png')))

    def test_window_close_waits_for_export_before_cache_removal_without_blocking_gui(self):
        from concurrent.futures import CancelledError
        self.warm_current_window()
        output=Path('close_export').absolute();output.mkdir();self.frame.out_path_str=str(output)
        entered=threading.Event();release=threading.Event()
        def save(job,**kwargs):
            entered.set();release.wait(5);raise CancelledError()
        try:
            with patch('mulimgviewer.src.export_async.save_viewer',side_effect=save):
                self.frame.save_img(None);self.assertTrue(entered.wait(1))
                root=self.frame.video_manager.cache_dir
                with patch.object(self.frame,'Destroy'),patch('wx.Exit'),patch.object(self.frame,'_save_session_configuration'),patch.object(self.frame,'_save_window_state'):
                    self.frame.close(None)
                self.assertTrue(self.frame._export_cancel_event.is_set())
                self.assertFalse(self.frame._cache_cleanup_future.done())
                self.assertTrue(root.exists())
                heartbeat=[];wx.CallAfter(lambda:heartbeat.append(True))
                self.pump_until(lambda:heartbeat)
                release.set()
                self.frame._cache_cleanup_future.result(timeout=10)
                self.assertFalse(root.exists())
                self.frame.video_manager.shutdown=lambda:None
        finally:release.set()

    def test_font_color_is_applied_to_preview_export_and_configuration(self):
        from mulimgviewer.src.configuration import control_value
        self._use_image_input()
        self.frame.font_color.SetColour(wx.Colour(230,30,70))
        self.frame.show_img_init();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        manager=self.frame.ImgManager
        self.assertEqual(manager.layout_params[17][13][:3],[230,30,70])
        work=manager.video_stitch_snapshot()
        work.stitch_images(1,[],flist=manager.flist)
        self.assertEqual(work.text_color.lower(),'#e61e46')
        self.assertEqual(control_value('font_color',self.frame.font_color)[:3],[230,30,70])
        work.clear_cache()

    def test_save_uses_applied_settings_output_scale_and_keeps_live_manager(self):
        import copy
        self._use_image_input()
        self.frame.show_scale.ChangeValue('.5,.5')
        self.frame.output_scale.ChangeValue('1,1')
        self.frame.show_img_init();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        manager=self.frame.ImgManager
        params=copy.deepcopy(manager.layout_params);pixels=manager.img
        self.frame.show_custom_func.SetValue(True)
        self.frame.on_show_custom_func_changed(None)
        root=Path('export_private').absolute();root.mkdir()
        self.frame.out_path_str=str(root);self.frame.choice_output.SetSelection(0);self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not getattr(self.frame,'_export_active',False))
        self.assertEqual(manager.layout_params,params)
        self.assertIs(manager.img,pixels)
        self.assertFalse((root/'image/algorithms/Gaussian Blur').exists())
        with Image.open(root/'image/composed/page_000021.png') as image:
            self.assertGreater(image.width,pixels.width)

    def test_single_algorithm_keeps_default_original_but_not_other_algorithms(self):
        self._use_image_input()
        self.frame.show_unit.SetValue(False)
        self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
        self.frame.show_custom_func.SetValue(True)
        self.frame.on_show_custom_func_changed(None)
        self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
        pipeline=self.frame.image_pipeline
        self.pump_until(lambda:pipeline.displayed_key is not None and not pipeline.running)
        root=pipeline.processing.visible.root
        self.assertTrue((root/'Gaussian Blur'/'stitched'/'page_000021.png').is_file())
        self.assertTrue((root/'original'/'stitched'/'page_000021.png').is_file())
        self.assertFalse((root/'Image Darkening').exists())

    def test_algorithm_canvas_retains_blank_row_without_background_cropping(self):
        from mulimgviewer.src.custom_func.main import get_available_algorithms
        algorithm_count=1+sum(name!='Original' for name in get_available_algorithms())
        canvas_rows=algorithm_count+1
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_all_func_layout.ChangeValue(f'{canvas_rows},1')
            self.frame.show_unit.SetValue(True)
            self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            self.frame.colourPicker_gap.SetColour(wx.Colour(35,65,95,255))
            self.frame.colour_change(None)
            for mode,panes in (('original',1),('all',canvas_rows),('single',canvas_rows)):
                color={'original':(35,65,95,255),'all':(45,75,105,255),'single':(55,85,115,255)}[mode]
                self.frame.colourPicker_gap.SetColour(wx.Colour(*color))
                self.frame.colour_change(None)
                self.frame.show_custom_func.SetValue(mode=='single')
                self.frame.show_all_func.SetValue(mode=='all')
                self.frame.refresh(None)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
                manager=self.frame.ImgManager
                image=manager.img
                bitmap=self.frame.img_last.GetBitmap()
                self.assertEqual((bitmap.GetWidth(),bitmap.GetHeight()),image.size)
                self.assertEqual(self.frame._last_display_logical_size,image.size)
                if mode=='original':base=image.size
                else:
                    self.assertEqual(image.size,(base[0],base[1]*panes))
                    occupied=algorithm_count if mode=='all' else 2
                    empty=image.crop((0,base[1]*occupied,image.width,image.height))
                    self.assertEqual(empty.getextrema(),tuple((c,c) for c in color))
                    self.assertEqual(len(manager._blank_img_ids),(panes-occupied)*2)
                # The synchronous fallback must retain the same canvas as well.
                self.frame.display_bitmap(True,image)
                self.assertEqual(self.frame._last_display_logical_size,image.size)

    def test_single_algorithm_grid_leaves_unused_panes_blank_in_images_and_video(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_unit.SetValue(True)
            self.frame.show_custom_func.SetValue(True)
            self.frame.show_all_func.SetValue(False)
            self.frame.show_all_func_layout.ChangeValue('2,2')
            self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            for vertical in (False,True):
                self.frame.func_layout_vertical.SetValue(vertical)
                self.frame.refresh(None)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token
                        and getattr(self.frame.ImgManager,'_show_all_func_layout',None)==(2,2))
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
                manager=self.frame.ImgManager
                self.assertFalse(manager.layout_params[38])
                self.assertEqual(manager._show_all_func_layout,(2,2))
                self.assertEqual(len(manager._blank_img_ids),4)
                self.assertEqual(manager._status_source_slots,(0,1,0,1,-1,-1,-1,-1))
                image=manager.img
                self.assertNotEqual(image.crop((0,0,image.width//2,image.height//2)).getextrema(),
                    tuple((c,c) for c in manager.gap_color))
                # Both unused panes contain only background, no old algorithm pixels.
                for row,col in (((0,1),(1,1)) if vertical else ((1,0),(1,1))):
                    pane=image.crop((col*image.width//2,row*image.height//2,
                        (col+1)*image.width//2,(row+1)*image.height//2))
                    self.assertEqual(pane.getextrema(),tuple((c,c) for c in manager.gap_color))
                model=IndexCatalog(manager,self.frame.shared_config)
                entries=[model.visual_entry(i) for i in range(model.visual_page_start(20),model.visual_page_start(21))]
                self.assertEqual({item['algorithm'] for item in entries},{'Original','Gaussian Blur'})

    def test_outer_layout_reuses_per_algorithm_mosaic_cache(self):
        self._use_image_input()
        self.frame.show_all_func.SetValue(True)
        self.frame.on_show_all_func_changed(None)
        self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
        pipeline=self.frame.image_pipeline;cache=pipeline.processing
        self.pump_until(lambda:pipeline.displayed_key is not None and len(pipeline.cache)==13 and not pipeline.running)
        for name in ('original','Gaussian Blur','Image Darkening','Image Enhancement'):
            self.assertTrue((cache.visible.root/name/'stitched'/'page_000021.png').is_file())
        count=cache.mosaic_stage.completed;processed=cache.misses
        self.frame.func_layout_vertical.SetValue(not self.frame.func_layout_vertical.GetValue())
        self.frame._custom_settings_changed()
        self.pump_until(lambda:pipeline.displayed_key is not None and len(pipeline.cache)==13 and not pipeline.running)
        self.assertEqual(cache.mosaic_stage.completed,count)
        self.assertEqual(cache.misses,processed)
        self.frame.show_custom_func.SetValue(True)
        self.frame.on_show_custom_func_changed(None)
        self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
        self.pump_until(lambda:pipeline.displayed_key is not None and not pipeline.running)
        chosen=self.frame.customfunc_choice.GetStringSelection()
        expected='original' if chosen=='Original' else chosen
        self.pump_until(lambda:{p.name for p in cache.visible.root.iterdir() if p.is_dir()}=={expected,'original'})
        self.assertEqual({p.name for p in cache.visible.root.iterdir() if p.is_dir()},{expected,'original'})

    def test_layered_image_file_list_export_has_consistent_page_names(self):
        self._use_image_input()
        listing=Path('inputs.txt');listing.write_text('images/a/000.png\nimages/b/001.png\n',encoding='utf-8')
        self.frame.show_all_func.SetValue(True)
        self.assertTrue(self.frame._open_image_file_list(str(listing)))
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        output=Path('export').absolute();output.mkdir()
        self.frame.out_path_str=str(output)
        self.frame.choice_output.SetSelection(2)
        self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not getattr(self.frame,'_export_active',False))
        root=output/'image'
        self.assertTrue((root/'composed'/'page_000001.png').is_file())
        for name in ('original','Gaussian Blur','Image Darkening','Image Enhancement'):
            self.assertTrue((root/'algorithms'/name/'stitch_images'/'page_000001.png').is_file(),name)
        self.assertTrue((root/'sources'/'source_001'/'source.json').is_file())

    def test_layered_video_export_uses_sources_and_shared_page_names(self):
        self.warm_current_window()
        output=Path('export').absolute();output.mkdir()
        self.frame.out_path_str=str(output)
        self.frame.choice_output.SetSelection(2);self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not getattr(self.frame,'_export_active',False))
        root=output/'video'
        self.assertTrue((root/'composed'/'page_000021.png').is_file(),self.frame.m_statusBar1.GetStatusText(3))
        self.assertTrue((root/'algorithms'/'original'/'stitch_images'/'page_000021.png').is_file())
        self.assertTrue((root/'sources'/'source_001'/'source.json').is_file())
        selected=root/'algorithms'/'original'/'select_images'
        self.assertEqual({p.name for p in selected.iterdir()},{'source_001','source_002'})

    def test_bulk_export_decoder_reuses_session_and_matches_exact_ffmpeg_frames(self):
        import copy
        from mulimgviewer.src.export_async import ExportDecoder
        from mulimgviewer.src.video_decoder import av
        if av is None:self.skipTest('Optional PyAV is unavailable')
        from types import SimpleNamespace
        native=ExportDecoder(lambda:False,decoder_budget=64*1024**2)
        fallback=ExportDecoder(lambda:False)
        path=str(Path('sample.mp4').resolve());fallback.bank.disabled.add(path)
        config=SimpleNamespace(video_fps_list=[10.],skip_frames=1,cache_save_format=1,video_path=['native_export'])
        Path(config.video_path[0]).mkdir()
        try:
            native._save_frame(path,0,2,0,config=config)
            native._save_frame(path,3,5,0,config=config)
            session=native.bank.sessions[path]
            self.assertEqual(session.opens,1)
            self.assertEqual(session.decoded,11)
            reference=copy.copy(config);reference.video_path=['ffmpeg_export'];Path(reference.video_path[0]).mkdir()
            fallback._save_frame(path,0,5,0,config=reference)
            for index in range(6):
                name=native._filename_converter(index,0,config)
                with Image.open(Path(config.video_path[0])/name) as image,Image.open(Path(reference.video_path[0])/name) as expected:
                    self.assertEqual(image.format,'PNG')
                    self.assertEqual(image.tobytes(),expected.tobytes())
        finally:native.close();fallback.close()
        self.assertTrue(native.bank.closed)
        self.assertTrue(all(session.container is None for session in native.bank.sessions.values()))

    def test_video_save_all_ignores_move_checkbox_for_raw_and_custom_outputs(self):
        self.frame.move_file.SetValue(True)
        self.frame.show_all_func.SetValue(True)
        self.frame.show_all_func_layout.ChangeValue('3,1')
        self.frame.refresh(None)
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
        self.assertTrue(self.frame.move_file.Value)
        self.assertFalse(self.frame.ImgManager.layout_params[11])
        cached=list(self.frame.ImgManager.flist)
        originals=list(self.frame.shared_config.real_video_path)
        self.frame.ImgManager.max_action_num=2
        root=Path('video_move_ignored').absolute();root.mkdir();self.frame.out_path_str=str(root)
        self.frame.auto_save_all.SetValue(True);self.frame.choice_output.SetSelection(2)
        self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not self.frame._export_active and self.frame._export_future.done())
        self.assertEqual(self.frame._export_status,'Save: success')
        self.assertTrue(all(Path(path).is_file() for path in originals+cached))
        self.assertTrue(self.frame.move_file.Value)
        folders=list((root/'video/algorithms').iterdir())
        self.assertGreaterEqual(len(folders),2)
        for folder in folders:self.assertTrue(list((folder/'select_images').rglob('*.png')))

    def test_video_file_list_save_all_decodes_virtual_frames_without_mutating_playback(self):
        listing=Path('export_videos.txt')
        listing.write_text('sample.mp4\nsample.mp4\n',encoding='utf-8')
        self.assertTrue(self.frame._open_video_file_list(listing))
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==0)
        manager=self.frame.ImgManager
        manager.max_action_num=2
        manager.set_action_count(20)
        original_paths=list(self.frame.shared_config.video_path)
        original_action=manager.action_count
        root=Path('export_virtual').absolute();root.mkdir()
        self.frame.out_path_str=str(root)
        self.frame.auto_save_all.SetValue(True)
        self.frame.choice_output.SetSelection(0)
        self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not getattr(self.frame,'_export_active',False))
        self.assertIn('success',self.frame.m_statusBar1.GetStatusText(3))
        self.assertEqual(manager.action_count,original_action)
        self.assertEqual(self.frame.shared_config.video_path,original_paths)
        for page in (1,2):self.assertTrue((root/f'video/composed/page_{page:06d}.png').exists())

    def test_custom_video_failure_is_visible_and_does_not_discard_raw_readiness(self):
        from mulimgviewer.src.custom_func import main as functions
        with patch.object(functions,'main',side_effect=RuntimeError('test model failure')):
            self.frame.show_custom_func.SetValue(True)
            self.frame.on_show_custom_func_changed(None)
            self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
            self.pump_until(lambda:'test model failure' in self.frame.m_statusBar1.GetStatusText(2))
            self.assertTrue(self.frame.video_manager._raw_ready_batches)

    def test_ten_custom_algorithms_render_through_gui_with_one_blank_slot(self):
        from mulimgviewer.src.custom_func.runtime import AlgorithmSession
        self._use_image_input()
        self.frame.show_all_func.SetValue(True)
        self.frame.show_all_func_layout.ChangeValue('3,4')
        self.frame.show_img_init()
        registry=tuple((f'Algorithm {index}',f'/fake/{index}/main.py',
            'def main(images, output, names): return [image.copy() for image in images]',
            json.dumps(dict(device='cpu'))) for index in range(10))
        manager=self.frame.ImgManager
        manager._custom_algorithm_registry=registry
        manager._custom_algorithm_session=AlgorithmSession(registry)
        self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        self.assertEqual(len(manager.xy_grid),24)
        self.assertEqual(len(manager._blank_img_ids),2)
        self.assertEqual(set(manager._status_source_slots),{-1,0,1})
        self.assertGreaterEqual(self.frame.image_pipeline.processing.snapshot()['misses'],10)
        from mulimgviewer.src.index_catalog import IndexCatalog
        catalog=IndexCatalog(manager,self.frame.shared_config)
        first=catalog.visual_page_start(20);last=catalog.visual_page_start(21)
        entries=[catalog.visual_entry(index) for index in range(first,last)]
        actual=[entry.get('raw_path',entry['path']) for entry in entries]
        self.assertTrue(all(Path(entry['path']).is_file() for entry in entries))
        self.assertEqual(sum(entry.get('processed',False) for entry in entries),20)
        expected=[str(Path(manager.flist[manager._status_source_slots[slot]]).absolute())
                  for xy,slot in sorted(zip(manager.xy_grid,manager.xy_grids_id_list),key=lambda value:(value[0][1],value[0][0]))
                  if manager._status_source_slots[slot]>=0]
        self.assertEqual(actual,expected)

    def test_show_all_nested_layout_keeps_every_source_and_custom_video_is_cached(self):
        from mulimgviewer.src.custom_func import main as utils_img
        original=utils_img.main
        rows=4
        self.frame.func_layout_vertical.SetValue(False)
        calls=[]
        def process(*args,**kwargs):
            calls.append(wx.IsMainThread())
            return original(*args,**kwargs)
        self.frame.show_all_func_layout.ChangeValue('4,2')
        self.frame.row_col_one_img.ChangeValue('2,2')
        self.frame.shared_config.batch_idx=5
        self.frame.ImgManager.set_action_count(5)
        with patch.object(utils_img,'main',process):
            self.frame.show_all_func.SetValue(True)
            self.frame.on_show_all_func_changed(None)
            self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
            vm=self.frame.video_manager
            self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==5
                and not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
            manager=self.frame.ImgManager
            self.assertTrue(manager._show_all_func_enabled)
            self.assertEqual(len(manager.xy_grid),rows*2*8)
            self.assertEqual(set(manager._status_source_slots)-{-1},set(range(8)))
            self.assertEqual(len(manager._blank_img_ids),(rows*2-(1+sum(name!='Original' for name in utils_img.get_available_algorithms())))*8)
            self.assertTrue(calls);self.assertFalse(any(calls))
            count=len(calls)
            self.frame.show_img()
            self.app.Yield(True)
            self.assertEqual(len(calls),count)
            self.assertTrue(Path(self.frame._video_cached_batch_path(5)).is_file())

    def test_image_status_click_identifies_folder_without_scanning_or_mutating_page(self):
        self._use_image_input()
        self.frame.show_img()
        self.pump_until(lambda: self.frame.image_pipeline.displayed_key is not None)
        manager = self.frame.ImgManager
        grid = list(manager.xy_grids_id_list).index(1)
        x, y = manager.xy_grid[grid]
        event = Mock()
        event.GetPosition.return_value = (int(x)+1, int(y)+1)
        for control in (self.frame.magnifier, self.frame.rotation, self.frame.flip, self.frame.select_img_box):
            control.SetValue(False)
        page = manager.action_count
        with patch('os.listdir', side_effect=AssertionError('status scanned a folder')), \
                patch.object(manager, 'get_flist', side_effect=AssertionError('status changed page')):
            self.frame.img_left_click(event)
        text = self.frame.m_statusBar1.GetStatusText(1)
        self.assertIn('Image 21/80 | Folder 2/2', text)
        self.assertIn('Parallel manual', self.frame.m_statusBar1.GetStatusText(2))
        self.assertIn(str(Path('images/b/020.png')), self.frame._status_field_tooltips[2])
        self.assertEqual(manager.action_count, page)
        snapshot = manager.video_stitch_snapshot()
        self.assertIs(snapshot._status_source_index, manager._status_source_index)
        for width in (600, 1200):
            self.frame.m_statusBar1.SetClientSize((width, 24))
            self.frame._fit_status_fields()
            self.assertEqual(sum(self.frame._status_widths), self.frame.m_statusBar1.GetClientSize().width)
            self.assertTrue(all(value > 0 for value in self.frame._status_widths))

    def test_visual_index_matches_actual_nested_layout_positions(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        self._use_image_input()
        for sequential,vertical0,vertical1 in ((False,False,False),(True,False,False),
                                             (True,True,False),(True,False,True),(True,True,True)):
            self.frame.parallel_sequential.SetValue(sequential)
            self.frame.row_col.ChangeValue('2,2')
            self.frame.row_col_one_img.ChangeValue('2,2')
            self.frame.img_vertical.SetValue(vertical0)
            self.frame.one_img_vertical.SetValue(vertical1)
            self.frame.show_img_init()
            self.frame.shared_config.batch_idx=0
            self.frame.ImgManager.set_action_count(0)
            self.frame.show_img()
            pipeline=self.frame.image_pipeline
            self.pump_until(lambda pipeline=pipeline:pipeline.displayed_key is not None
                and pipeline.displayed_key[:2]==(pipeline.generation,0))
            model=self.frame.ImgManager
            expected=[str(Path(model.flist[slot]).absolute()) for xy,slot in
                      sorted(zip(model.xy_grid,model.xy_grids_id_list),key=lambda item:(item[0][1],item[0][0]))]
            catalog=IndexCatalog(model,self.frame.shared_config,sequential)
            first=catalog.visual_page_start(0);last=catalog.visual_page_start(1)
            actual=[catalog.visual_entry(index)['path'] for index in range(first,last)]
            self.assertEqual(actual,expected,(sequential,vertical0,vertical1))

    def test_video_visual_index_matches_actual_frame_paths_with_serial_switch(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        cfg=self.frame.shared_config
        for serial,outer,batch in ((False,'2,2',5),(True,'2,3',3)):
            self.frame.parallel_to_sequential.SetValue(serial)
            self.frame.parallel_sequential.SetValue(not serial)
            self.frame.row_col.ChangeValue(outer)
            self.frame.row_col_one_img.ChangeValue('2,2')
            self.frame.img_vertical.SetValue(True)
            self.frame.one_img_vertical.SetValue(True)
            self.frame._commit_video_settings()
            self.frame.ImgManager.init(cfg.video_path,type=1,parallel_to_sequential=serial,
                video_mode=True,video_fps_list=cfg.video_fps_list,video_num_list=cfg.video_num_list)
            self.frame.show_img_init()
            cfg.batch_idx=batch;self.frame.ImgManager.set_action_count(batch)
            self.frame.video_manager.update_cache();self.frame.show_img()
            token=self.frame.video_manager._window_token
            self.pump_until(lambda batch=batch,token=token:getattr(self.frame,'_video_display_key',(None,))[0]==batch
                and getattr(self.frame,'_video_display_key',(None,))[-1]==token)
            model=self.frame.ImgManager
            expected=[str(Path(model.flist[slot]).absolute()) for xy,slot in
                      sorted(zip(model.xy_grid,model.xy_grids_id_list),key=lambda item:(item[0][1],item[0][0]))]
            catalog=IndexCatalog(model,cfg,not serial)
            actual=[catalog.visual_entry(i)['path'] for i in
                    range(catalog.visual_page_start(batch),catalog.visual_page_start(batch+1))]
            self.assertEqual(actual,expected,serial)

    def _open_hidden_index(self):
        from mulimgviewer.src.index_table import IndexTable
        class HiddenIndex(IndexTable):
            def Show(self, show=True):
                return super().Show(False)
        with patch('mulimgviewer.src.main.IndexTable',HiddenIndex):
            self.frame.index_table_gui(None)
        self.frame.indextablegui._choose_view(2)
        self.frame.indextablegui.change_view(None)
        return self.frame.indextablegui

    def _click_main_source(self, slot):
        manager=self.frame.ImgManager
        grid=list(manager.xy_grids_id_list).index(slot)
        x,y=manager.xy_grid[grid]
        event=Mock();event.GetPosition.return_value=(int(x)+1,int(y)+1)
        for field in (self.frame.magnifier,self.frame.rotation,self.frame.flip,self.frame.select_img_box):
            field.SetValue(False)
        self.frame.img_left_click(event)
        return tuple(self.frame.m_statusBar1.GetStatusText(i) for i in range(3))

    def test_custom_index_paths_and_round_trip_follow_panes_in_sparse_layout(self):
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.row_col.ChangeValue('1,3')  # Two inputs, one empty source slot.
            self.frame.show_all_func_layout.ChangeValue('2,3')
            self.frame.show_unit.SetValue(True)
            self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            for all_algorithms,vertical in ((False,False),(True,False),(True,True)):
                self.frame.show_custom_func.SetValue(not all_algorithms)
                self.frame.show_all_func.SetValue(all_algorithms)
                self.frame.func_layout_vertical.SetValue(vertical)
                self.frame.refresh(None)
                self.frame._seek_display_page(21)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_status_display_batch',None)==20 and getattr(self.frame,'_video_display_key',(None,))[-1]==self.frame.video_manager._window_token)
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
                index=self._open_hidden_index()
                try:
                    first,last=index.catalog.visual_page_start(20),index.catalog.visual_page_start(21)
                    order=self.frame._display_grid_order()
                    self.assertEqual(last-first,len(order))
                    for rank,grid in enumerate(order):
                        entry=index.catalog.visual_entry(first+rank)
                        self.assertTrue(Path(entry['path']).is_file(),(entry,self.frame.ImgManager.flist,self.frame.shared_config.count_per_action))
                        if entry['algorithm']=='Original' and not entry['algorithm_path']:
                            self.assertFalse(entry['processed'])  # Built-in raw fallback needs no plugin file.
                        else:
                            self.assertTrue(Path(entry['algorithm_path']).is_file(),entry)
                        if entry.get('processed'):
                            self.assertIn('processed',Path(entry['path']).parts)
                            self.assertEqual(Path(entry['path']).parent.name,'frames')
                            self.assertFalse(any(part.startswith('page_') for part in Path(entry['path']).parts))
                        x,y=self.frame.ImgManager.xy_grid[grid]
                        event=Mock();event.GetPosition.return_value=(int(x)+1,int(y)+1)
                        for field in (self.frame.magnifier,self.frame.rotation,self.frame.flip,self.frame.select_img_box):field.SetValue(False)
                        self.frame.img_left_click(event)
                        self.assertEqual(self.frame._index_location()['rank'],rank)
                        index.locate_main_image(None)
                        self.assertEqual(index.index_table.GetFirstSelected(),first+rank)
                        self.assertEqual(index._selected_entry['path'],entry['path'])
                        self.assertIn(entry['algorithm_path'],index.path_details.GetValue())
                        index._select_index(first+rank);index.jump_selected(None)
                        self.assertEqual(self.frame._status_selected_grid,grid)
                    # Uncached future rows still resolve to the right algorithm path.
                    future=index.catalog.visual_page_start(60)
                    candidate=next(i for i in range(future,index.catalog.visual_page_start(61))
                        if index.catalog.visual_entry(i).get('processed'))
                    entry=index.catalog.visual_entry(candidate)
                    # Returning from the previous jump retires the remote page
                    # immediately; physical window cleanup runs in the background.
                    self.pump_until(lambda entry=entry:not Path(entry['path']).exists())
                    self.assertFalse(Path(entry['path']).exists())
                    if video:
                        found,limited=index.catalog.search(entry['path'],2,lambda:False)
                        self.assertIn(candidate,found)
                        self.assertFalse(limited)
                    index._select_index(candidate);index.jump_selected(None)
                    self.pump_until(lambda:self.frame._status_display_batch==60)
                    self.assertTrue(Path(entry['path']).exists())
                    index.locate_main_image(None)
                    self.assertEqual(index.index_table.GetFirstSelected(),candidate)
                    # Restore the test page before the next algorithm mode.
                    self.frame._seek_display_page(21)
                    self.pump_until(lambda:self.frame._status_display_batch==20)
                finally:
                    index.Close();index._workers.shutdown(wait=True)

    def test_index_locates_image_click_and_falls_back_after_page_changes(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        index=self._open_hidden_index()
        try:
            # No actual click yet: always select the displayed page's first row.
            index.locate_main_image(None)
            first=index.catalog.visual_page_start(20)
            self.assertEqual(index.index_table.GetFirstSelected(),first)
            self._click_main_source(1)
            event=wx.CommandEvent(wx.EVT_BUTTON.typeId,index.locate_main_button.GetId())
            event.SetEventObject(index.locate_main_button)
            index.locate_main_button.GetEventHandler().ProcessEvent(event)
            self.assertEqual(index.index_table.GetFirstSelected(),first+1)
            self.frame._seek_display_page(22)
            self.pump_until(lambda:self.frame._status_display_batch==21)
            index.locate_main_image(None)
            self.assertEqual(index.index_table.GetFirstSelected(),index.catalog.visual_page_start(21))
            self.assertEqual(self.frame._index_location()['rank'],0)
        finally:
            index.Close();index._workers.shutdown(wait=True)

    def test_index_image_jump_updates_status_after_uncached_page_is_painted(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        index=self._open_hidden_index()
        try:
            target=index.catalog.visual_page_start(40)+1
            index._select_index(target)
            event=wx.CommandEvent(wx.EVT_BUTTON.typeId,index.jump_button.GetId())
            event.SetEventObject(index.jump_button)
            index.jump_button.GetEventHandler().ProcessEvent(event)
            self.assertEqual(self.frame._status_display_batch,20)
            self.pump_until(lambda:self.frame._status_display_batch==40)
            after=tuple(self.frame.m_statusBar1.GetStatusText(i) for i in range(3))
            self.assertIn('Folder 2/2',after[1])
            self.assertEqual(after,self._click_main_source(1))
            index.locate_main_image(None)
            self.assertEqual(index.index_table.GetFirstSelected(),target)
        finally:
            index.Close();index._workers.shutdown(wait=True)

    def test_index_video_jump_and_same_page_selection_match_mouse_status(self):
        self.warm_current_window();self.frame.show_img()
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==20)
        index=self._open_hidden_index()
        try:
            target=index.catalog.visual_page_start(35)+1
            index._select_index(target);index.jump_selected(None)
            self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==35)
            after=tuple(self.frame.m_statusBar1.GetStatusText(i) for i in range(3))
            self.assertIn('Video 2/2',after[1])
            self.assertEqual(after,self._click_main_source(1))
            index._select_index(index.catalog.visual_page_start(35));index.jump_selected(None)
            self.assertIn('Video 1/2',self.frame.m_statusBar1.GetStatusText(1))
            index.locate_main_image(None)
            self.assertEqual(index.index_table.GetFirstSelected(),index.catalog.visual_page_start(35))
        finally:
            index.Close();index._workers.shutdown(wait=True)

    def test_index_jump_rejects_stale_layout_snapshot(self):
        self._use_image_input();self.frame.show_img()
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        index=self._open_hidden_index()
        try:
            index._select_index(index.catalog.visual_page_start(20)+1)
            self.frame.row_col.ChangeValue('2,1')
            self.frame.show_img_init()
            index.jump_selected(None)
            self.assertIn('Refresh',index.match_label.GetLabel())
            self.assertIsNone(getattr(self.frame,'_pending_index_selection',None))
        finally:
            index.Close();index._workers.shutdown(wait=True)

    def test_navigation_is_one_based_and_clamps_invalid_values(self):
        with patch.object(self.frame, 'show_img'), patch.object(self.frame.video_manager, 'update_cache'):
            self.frame._seek_display_page(1)
            self.assertEqual(self.frame.shared_config.batch_idx, 0)
            self.assertEqual(self.frame.slider_img.GetValue(), 1)
            self.frame.slider_value.ChangeValue('80')
            self.frame.slider_value_change(None)
            self.assertEqual(self.frame.shared_config.batch_idx, 79)
            self.assertEqual(self.frame.slider_value_max.GetLabel(), '80')
            self.frame._seek_display_page(9999)
            self.assertEqual(self.frame.slider_value.GetValue(), '80')
            self.frame._seek_display_page(0)
            self.assertEqual(self.frame.shared_config.batch_idx, 0)
            self.frame._seek_display_page('invalid')
            self.assertEqual(self.frame.slider_value.GetValue(), '1')

    def test_serial_video_boundary_page_and_following_page_have_no_gaps(self):
        cfg = self.frame.shared_config
        self.frame.parallel_to_sequential.SetValue(True)
        self.frame.row_col.ChangeValue('1,3')
        self.frame._commit_video_settings()
        self.frame.ImgManager.init(cfg.video_path, type=1, parallel_to_sequential=True,
            video_mode=True, video_fps_list=cfg.video_fps_list, video_num_list=cfg.video_num_list)
        self.frame.show_img_init()
        self.assertEqual(cfg.count_per_action, 3)
        cfg.batch_idx = 26
        self.frame.ImgManager.set_action_count(26)
        self.frame.video_manager.update_cache()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 26)
        self.assertEqual(self.frame.ImgManager._status_video_sources, ((0,78),(0,79),(1,0)))
        self.assertEqual(self.frame.slider_value.GetValue(), '27')
        self.assertEqual(self.frame.slider_img.GetValue(), 27)
        cfg.batch_idx = 27
        self.frame.show_img()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 27)
        self.assertEqual(self.frame.ImgManager._status_video_sources, ((1,1),(1,2),(1,3)))
        cfg.batch_idx = 26
        self.frame.show_img()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 26)
        self.assertEqual(self.frame.ImgManager._status_video_sources, ((0,78),(0,79),(1,0)))

    def test_video_file_list_loads_videos_and_status_identifies_second_source(self):
        listing = Path('videos.txt')
        listing.write_text('sample.mp4\nsample.mp4\n', encoding='utf-8')
        self.assertTrue(self.frame._open_video_file_list(listing))
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 0)
        manager = self.frame.ImgManager
        grid = list(manager.xy_grids_id_list).index(1)
        self.frame.update_status_bar_for_current_page(grid)
        self.assertIn('Video 2/2', self.frame.m_statusBar1.GetStatusText(1))
        self.assertIn('Image File List', self.frame.m_statusBar1.GetStatusText(2))
        self.assertTrue(self.frame.shared_config.video_mode)
        self.assertEqual(self.frame.shared_config.status_input_mode, 3)

    def test_image_file_list_renders_titles_and_preserves_loaded_input_label(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        self._use_image_input()
        listing=Path('images.txt')
        listing.write_text('"images/a/000.png"\n images/b/001.png \n',encoding='utf-8-sig')
        self.frame.title_auto.SetValue(True)
        self.frame.title_show.SetValue(True)
        self.assertTrue(self.frame._open_image_file_list(str(listing)))
        self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
        model=IndexCatalog(self.frame.ImgManager,self.frame.shared_config,True)
        self.assertEqual((model.input_mode,model.order),('Image File List','sequential'))
        self.assertEqual(self.frame.ImgManager.title_setting[2:7],[False,True,True,True,False])
        self.assertEqual(len(self.frame.ImgManager.flist),2)
        self.frame.update_status_bar_for_current_page(0)
        self.assertIn('Image File List',self.frame.m_statusBar1.GetStatusText(2))

    def test_invalid_image_list_keeps_previous_manager_and_input(self):
        self._use_image_input()
        previous=self.frame.ImgManager
        paths=list(previous.path_list)
        listing=Path('empty.csv');listing.write_text('',encoding='utf-8')
        self.assertFalse(self.frame._open_image_file_list(str(listing)))
        self.assertIs(self.frame.ImgManager,previous)
        self.assertEqual(list(previous.path_list),paths)
        self.assertFalse(self.frame._open_image_file_list('missing.txt'))
        self.assertEqual(list(previous.path_list),paths)

    def test_changed_image_list_ignores_inactive_parallel_to_sequential_option(self):
        self._use_image_input()
        listing=Path('images.txt')
        listing.write_text('images/a/000.png\n',encoding='utf-8')
        self.assertTrue(self.frame._open_image_file_list(str(listing)))
        self.frame.shared_config.parallel_to_sequential=True
        self.frame.parallel_to_sequential.SetValue(True)
        listing.write_text('images/b/001.png\nimages/a/002.png\n',encoding='utf-8')
        self.frame.show_img_init()
        manager=self.frame.ImgManager
        self.assertFalse(manager.parallel_to_sequential)
        self.assertEqual(manager.img_num,2)
        self.assertEqual(manager.path_list,[str(Path('images/b/001.png').absolute()),
                                            str(Path('images/a/002.png').absolute())])
    def test_video_file_list_auto_title_fields_match_folder_route_in_all_orders(self):
        from mulimgviewer.src.display_modes import auto_title_fields
        listing=Path('videos.txt');listing.write_text('sample.mp4\nsample.mp4\n',encoding='utf-8')
        self.frame.title_auto.SetValue(True)
        self.assertTrue(self.frame._open_video_file_list(listing))
        self.pump_until(lambda:getattr(self.frame,'_video_display_key',(None,))[0]==0)
        for serial,sequential in ((False,False),(True,False),(False,True)):
            self.frame.parallel_to_sequential.SetValue(serial)
            self.frame.parallel_sequential.SetValue(sequential)
            actual=self.frame.set_img_layout()[17][2:7]
            self.assertEqual(actual,auto_title_fields(0,True,2,serial,sequential))

    def test_video_status_click_uses_painted_batch_and_real_source(self):
        self.warm_current_window()
        self.frame.show_img()
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 20)
        manager = self.frame.ImgManager
        grid = list(manager.xy_grids_id_list).index(1)
        x, y = manager.xy_grid[grid]
        event = Mock()
        event.GetPosition.return_value = (int(x)+1, int(y)+1)
        for control in (self.frame.magnifier, self.frame.rotation, self.frame.flip, self.frame.select_img_box):
            control.SetValue(False)
        # A new requested batch must not change the identity of pixels still on screen.
        self.frame.shared_config.batch_idx = 24
        self.frame.img_left_click(event)
        text = self.frame.m_statusBar1.GetStatusText(1)
        self.assertIn('Page 21/80', text)
        self.assertIn('Frame 21/80 | Video 2/2', text)
        self.assertIn('sample.mp4', self.frame.m_statusBar1.GetStatusText(2))
        self.assertNotIn('cache_frames', self.frame.m_statusBar1.GetStatusText(2))
        self.assertIn('00:00:02.000', self.frame._status_field_tooltips[1])

    def test_image_composition_and_cached_display_never_block_gui(self):
        self._use_image_input()
        entered, release = threading.Event(), threading.Event()
        original = ImgManager.stitch_images
        def blocked(manager, *args, **kwargs):
            self.assertFalse(wx.IsMainThread())
            entered.set()
            if not release.wait(5):
                raise TimeoutError('GUI did not release image compositor')
            return original(manager, *args, **kwargs)
        try:
            with patch.object(ImgManager, 'stitch_images', blocked):
                self.frame.show_img()
                self.assertTrue(entered.wait(3))
                heartbeat = []
                wx.CallAfter(lambda: heartbeat.append(True))
                self.pump_until(lambda: bool(heartbeat))
                release.set()
                self.pump_until(lambda: self.frame.image_pipeline.displayed_key is not None)
            pipeline = self.frame.image_pipeline
            self.pump_until(lambda: set(pipeline.cache) == set(range(14, 27)) and not pipeline.running)
            self.assertEqual(pipeline.directory, self.frame.video_manager.disk_cache_dir)
            self.assertEqual(self.frame.ImgManager.action_count, 20)
            self.assertEqual(len(self.frame.ImgManager.flist), 2)
            self.assertEqual(self.frame.shared_config.thread_allocation['extract'], 0)
            original_open = Image.open
            def checked_open(*args, **kwargs):
                self.assertFalse(wx.IsMainThread(), 'PNG loading ran on GUI thread')
                return original_open(*args, **kwargs)
            with patch.object(Image, 'open', checked_open):
                self.frame.shared_config.batch_idx = 21
                self.frame.show_img()
                self.pump_until(lambda: pipeline.displayed_key[1] == 21)
            self.assertEqual(self.frame.ImgManager.action_count, 21)
            self.assertTrue(all('021.png' in p for p in self.frame.ImgManager.flist))
        finally:
            release.set()

    def test_image_cache_radius_commit_and_outer_cleanup_are_global(self):
        self._use_image_input()
        self.frame.show_img()
        pipeline = self.frame.image_pipeline
        self.pump_until(lambda: len(pipeline.cache) == 13 and not pipeline.running)
        self.frame.shared_config.batch_idx = 24
        self.frame.show_img()
        self.pump_until(lambda: set(pipeline.cache) == set(range(18, 31)) and not pipeline.running)
        self.assertEqual(len(list(pipeline.directory.glob('page_*.png'))), 13)
        self.frame.cache_frames.ChangeValue('1')
        self.frame.cache_multiplier.ChangeValue('2')
        self.frame.on_cache_num_change(None)
        self.pump_until(lambda: set(pipeline.cache) == set(range(22, 27)) and not pipeline.running)
        self.pump_until(lambda: len(list(pipeline.directory.glob('page_*.png'))) == 5)

    def test_global_settings_save_load_and_legacy_configuration(self):
        source = Path(__file__).resolve().parents[2] / 'src/mulimgviewer/configs/userdef_config.json'
        configuration = json.loads(source.read_text(encoding='utf-8'))
        target = Path('configuration')
        target.mkdir()
        path = target / 'userdef_config.json'
        (target / 'config_schema.json').write_text('{"roles_version": 2}', encoding='utf-8')
        configuration['output'].update(power_mode=4, cache_frames='3', cache_multiplier='2')
        path.write_text(json.dumps(configuration), encoding='utf-8')
        with patch('mulimgviewer.src.configuration_controller.get_resource_path', return_value=str(target)):
            MulimgViewer.load_configuration(self.frame, None)
            self.assertEqual(self.frame.shared_config.power_mode, 4)
            self.assertEqual(self.frame.shared_config.cache_num, 3)
            self.assertEqual(self.frame.shared_config.cache_multiplier, 2)
            self.frame.save_configuration(None)
            saved = json.loads(path.read_text(encoding='utf-8'))['output']
            self.assertEqual(saved['power_mode'], 4)
            self.assertEqual(saved['cache_frames'], '3')
            self.frame.cache_frames.ChangeValue('0.5')
            self.frame.cache_multiplier.ChangeValue('1.5')
            self.frame.save_configuration(None)
            saved = json.loads(path.read_text(encoding='utf-8'))['output']
            self.assertEqual(saved['cache_frames'], '3')
            self.assertEqual(saved['cache_multiplier'], '2')
            for key in ('power_mode', 'cache_frames', 'cache_multiplier'):
                configuration['output'].pop(key, None)
            path.write_text(json.dumps(configuration), encoding='utf-8')
            MulimgViewer.load_configuration(self.frame, None)
            self.assertEqual(self.frame.shared_config.power_mode, 2)
            self.assertEqual(self.frame.shared_config.cache_num, 2)
            self.assertEqual(self.frame.shared_config.cache_multiplier, 1)

    def test_image_dense_layout_and_file_list_invalidate_old_pages(self):
        self._use_image_input()
        self.frame.show_img()
        pipeline = self.frame.image_pipeline
        self.pump_until(lambda: pipeline.displayed_key is not None)
        old_generation = pipeline.generation
        self.frame.ImgManager.init('images/a', type=2, video_mode=False)
        self.frame.row_col.ChangeValue('10,10')
        self.frame.show_img_init()
        self.frame.show_img()
        self.pump_until(lambda: pipeline.displayed_key is not None
                        and pipeline.displayed_key[0] != old_generation)
        self.assertEqual(self.frame.shared_config.batch_idx, 0)
        self.assertEqual(len(self.frame.ImgManager.flist), 80)
        self.assertEqual(pipeline.workers, 1)  # Only one logical page exists.
        old_generation = pipeline.generation
        listing = Path('images.txt')
        listing.write_text('\n'.join(str(p.resolve()) for p in sorted(Path('images/a').glob('*.png'))),
                           encoding='utf-8')
        self.frame.ImgManager.init(str(listing), type=3, video_mode=False)
        self.frame.row_col.ChangeValue('1,1')
        self.frame.show_img_init()
        self.frame.show_img()
        self.pump_until(lambda: pipeline.displayed_key is not None
                        and pipeline.displayed_key[0] != old_generation)
        self.assertEqual(len(self.frame.ImgManager.flist), 1)
        self.assertEqual(self.frame.ImgManager.type, 3)

    def test_image_playback_does_not_skip_pages_while_waiting(self):
        self._use_image_input()
        self.frame.show_img()
        self.pump_until(lambda: self.frame.image_pipeline.displayed_key is not None)
        displayed = []
        original = self.frame.display_bitmap
        def paint(*args, **kwargs):
            if self.frame.shared_config.is_playing:
                displayed.append(self.frame.shared_config.batch_idx)
            return original(*args, **kwargs)
        self.frame.display_bitmap = paint
        self.frame.interval.ChangeValue('0.05')
        self.frame.toggle_play(None)
        try:
            self.run_timer_until(lambda: len(displayed) >= 4)
            self.assertEqual(displayed[:4], [21, 22, 23, 24])
        finally:
            self.frame.shared_config.is_playing = False
            self.frame.play_timer.Stop()

    def test_cancel_directory_does_not_initialize_or_reset_existing_input(self):
        self.frame.shared_config.video_mode = False
        previous_manager = self.frame.ImgManager
        for fresh in (True, False):
            for mode in (0, 1):
                with self.subTest(fresh=fresh, mode=mode):
                    manager = ImgManager() if fresh else previous_manager
                    self.frame.ImgManager = manager
                    self.frame.shared_config.batch_idx = 17
                    self.frame.shared_config.input_mode = 2
                    self.frame.choice_input_mode.SetSelection(mode)
                    with patch.object(wx, 'DirDialog') as dialog, patch.object(manager, 'init') as initialize, patch.object(self.frame, 'show_img_init') as layout, patch.object(self.frame, 'show_img') as show:
                        dialog.return_value.ShowModal.return_value = wx.ID_CANCEL
                        self.frame.open_all_img(None)
                        initialize.assert_not_called()
                        layout.assert_not_called()
                        show.assert_not_called()
                        dialog.return_value.Destroy.assert_called_once()
                    self.assertEqual(self.frame.shared_config.batch_idx, 17)
                    self.assertEqual(self.frame.shared_config.input_mode, 2)
                    self.assertEqual(manager.type, None if fresh else 1)
        self.frame._shutdown_image_stitch_executor()

    def test_layout_before_input_selection_is_a_safe_noop(self):
        self.frame.ImgManager = ImgManager()
        self.frame.shared_config.video_mode = False
        with patch.object(self.frame, 'set_img_layout') as layout:
            self.frame.show_img_init()
        layout.assert_not_called()

    def test_image_directory_can_open_after_initial_cancellation(self):
        self.frame.shared_config.video_mode = False
        self.frame.ImgManager = ImgManager()
        directory = Path('images').resolve()
        directory.mkdir()
        Image.new('RGB', (32, 32), 'red').save(directory / 'frame.png')
        try:
            with patch.object(wx, 'DirDialog') as dialog:
                dialog.return_value.ShowModal.return_value = wx.ID_CANCEL
                self.frame.one_dir_mul_img(None)
                dialog.return_value.ShowModal.return_value = wx.ID_OK
                dialog.return_value.GetPath.return_value = str(directory)
                self.frame.one_dir_mul_img(None)
            self.assertEqual(self.frame.ImgManager.type, 2)
            self.assertGreater(self.frame.ImgManager.img_num, 0)
        finally:
            self.frame._shutdown_image_stitch_executor()


if __name__ == '__main__':
    unittest.main()
