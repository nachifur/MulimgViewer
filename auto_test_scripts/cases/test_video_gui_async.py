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
from mulimgviewer.src.layout_gaps import gap_pair


class HiddenViewer(MulimgViewer):
    @staticmethod
    def check_version():
        """Keep network update checks out of the isolated GUI fixture."""
        return None

    @staticmethod
    def load_configuration(*_args, **_kwargs):
        """Use test settings instead of restoring the developer's session."""
        return None

    @staticmethod
    def _restore_window_state():
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

    def video_page_ready(self):
        """Wait for the current page after asynchronous cache invalidation."""
        return self.frame.video_manager.is_display_current(getattr(self.frame,'_video_display_key',None))

    def test_video_readiness_requires_a_painted_page(self):
        vm=self.frame.video_manager
        with patch.object(self.frame,'_video_display_key',None,create=True), \
                patch.object(vm,'_window_token',None):
            self.assertFalse(self.video_page_ready())

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
        # This fixture starts on page 20 with neighbors on both sides.
        # Refresh can repaint the same page with a new layout generation;
        # the single-page first paint precedes the actual prefetch window.
        self.pump_until(lambda: self.video_page_ready() and vm.shared_config.batch_idx == 20
                        and vm._stitch_window[0] < 20 < vm._stitch_window[1]
                        and not vm.cache_update_pending() and not vm._pending_extract
                        and not vm._window_stitches)

    def test_large_window_opens_after_first_bitmap_is_installed(self):
        frame = self.frame
        cfg, vm = frame.shared_config, frame.video_manager
        cfg.cache_num, cfg.cache_multiplier = 8, 10
        with patch.object(frame, '_request_video_display') as display:
            vm.update_cache()
            self.pump_until(lambda: display.called)
            self.assertEqual(vm._stitch_window, (20, 20))
            self.assertEqual(set(vm._batch_render_states), {20})
        frame.show_img()
        self.pump_until(lambda: self.video_page_ready() and vm._stitch_window == (0, 79))

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

    def test_original_streaming_refills_reverse_stock_after_pause(self):
        self.frame.show_all_func.SetValue(False)
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
        offset=snapshot.title_max_size[1]+gap_pair(snapshot.layout_params[3], 'unit')[1]
        snapshot.crop_points_process([[4,4+offset,24,20+offset,1,1,True]])
        self.assertEqual(snapshot.crop_points[0][:4],expected)

    def test_middle_bottom_magnifier_is_centered_for_video_image_and_custom_panes(self):
        frame=self.frame
        for video in (True,False):
            if not video:self._use_image_input()
            for custom in (False,True):
                with self.subTest(video=video,custom=custom):
                    frame.img_resolution.ChangeValue('80,48')
                    frame.show_scale.ChangeValue('1,1')
                    frame.row_col_img_unit.ChangeValue('2,1')
                    frame.gap.ChangeValue('0,0,0,0,0,0,0,0')
                    frame.magnifier_show_scale.ChangeValue('1,1')
                    frame.magnifer_row_col.ChangeValue('1,1')
                    frame.box_position.SetSelection(0)
                    frame.title_show.SetValue(False)
                    frame.show_original.SetValue(True)
                    frame.show_magnifer.SetValue(True)
                    frame.show_box.SetValue(False)
                    frame.show_box_in_crop.SetValue(False)
                    frame.show_custom_func.SetValue(custom)
                    frame.show_all_func.SetValue(False)
                    frame.colourPicker_gap.SetColour(wx.Colour(255,255,255))
                    frame.xy_magnifier=[[4,4,24,14,1,1,False]]
                    frame.color_list=[wx.Colour(255,0,0)]
                    frame.refresh(None)
                    if video:self.pump_until(self.video_page_ready)
                    else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and
                        frame.image_pipeline.displayed_key[:2]==(frame.image_pipeline.generation,frame.shared_config.batch_idx))
                    image=frame.show_bmp_in_panel
                    # A 20-wide crop below an 80-wide original starts at x=30.
                    self.assertEqual(image.getpixel((0,53))[:3],(255,255,255))
                    self.assertNotEqual(image.getpixel((40,53))[:3],(255,255,255))
                    self.assertEqual(image.getpixel((79,53))[:3],(255,255,255))

    def test_all_box_positions_use_identical_image_and_video_render_geometry(self):
        import copy
        frame=self.frame
        for name,value in dict(row_col='1,1',row_col_one_img='1,1',row_col_img_unit='2,1',
                img_resolution='80,48',show_scale='1,1',output_scale='1,1',
                magnifier_show_scale='1,1',magnifier_out_scale='1,1',magnifer_row_col='1,1').items():
            getattr(frame,name).ChangeValue(value)
        frame.title_show.SetValue(False)
        frame.show_original.SetValue(True);frame.show_magnifer.SetValue(True)
        frame.show_box.SetValue(False);frame.show_box_in_crop.SetValue(False)
        frame.show_custom_func.SetValue(False);frame.show_all_func.SetValue(False)
        frame.xy_magnifier=[[4,4,24,14,1,1,False]]
        frame.color_list=[wx.Colour(255,0,0)]
        source=Path('geometry.png')
        Image.new('RGB',(80,48),(20,80,160)).save(source)
        params=frame.set_img_layout()
        for position in range(5):
            for mode in (0,1):
                results=[]
                for video in (False,True):
                    manager=frame.ImgManager.video_stitch_snapshot()
                    manager.layout_params=copy.deepcopy(params)
                    manager.layout_params[21]=position;manager.video_mode=video
                    manager._video_lazy_frames=True
                    self.assertEqual(manager.stitch_images(mode,[[4,4,24,14,1,1,False]],flist=[str(source)]),0)
                    results.append((manager.img.size,manager.img.tobytes()))
                with self.subTest(position=position,render_mode=mode):self.assertEqual(*results)

    def test_hidden_content_is_a_background_page_and_recovers_when_magnifier_is_added(self):
        frame=self.frame
        for video in (True,False):
            if not video:self._use_image_input()
            frame.row_col_img_unit.ChangeValue('3,1')
            frame.img_resolution.ChangeValue('80,48')
            frame.show_scale.ChangeValue('1,1')
            frame.gap.ChangeValue('0,0,0,0,0,0,0,0')
            frame.colourPicker_gap.SetColour(wx.Colour(20,30,40))
            frame.show_original.SetValue(False)
            frame.show_magnifer.SetValue(True)
            frame.title_show.SetValue(False)
            frame.show_custom_func.SetValue(False);frame.show_all_func.SetValue(False)
            frame.xy_magnifier=[]
            frame.refresh(None)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and
                frame.image_pipeline.displayed_key[:2]==(frame.image_pipeline.generation,frame.shared_config.batch_idx))
            image=frame.show_bmp_in_panel
            self.assertEqual(image.size,(160,48))
            self.assertEqual(image.getextrema(),((20,20),(30,30),(40,40),(255,255)))
            self.assertEqual(len(frame.ImgManager.xy_grids_id_list),0)
            frame.xy_magnifier=[[4,4,24,14,1,1,False]]
            frame.color_list=[wx.Colour(255,0,0)]
            frame.refresh(None)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and
                frame.image_pipeline.displayed_key[:2]==(frame.image_pipeline.generation,frame.shared_config.batch_idx))
            self.assertGreater(len(frame.ImgManager.xy_grids_id_list),0)

    def test_titles_render_without_original_or_magnifier_in_image_and_video_modes(self):
        frame=self.frame
        for video in (True,False):
            if not video:self._use_image_input()
            for one_title in (False,True):
                with self.subTest(video=video,one_title=one_title):
                    frame.img_resolution.ChangeValue('80,48');frame.show_scale.ChangeValue('1,1')
                    frame.row_col_img_unit.ChangeValue('3,1')
                    frame.gap.ChangeValue('0,0,0,0,0,0,0,0')
                    frame.show_original.SetValue(False);frame.show_magnifer.SetValue(False)
                    frame.title_show.SetValue(True);frame.onetitle.SetValue(one_title)
                    frame.title_font_size.ChangeValue('12')
                    frame.colourPicker_gap.SetColour(wx.Colour(255,255,255))
                    frame.font_color.SetColour(wx.Colour(0,0,0))
                    frame.show_custom_func.SetValue(False);frame.show_all_func.SetValue(False)
                    frame.xy_magnifier=[]
                    frame.refresh(None)
                    if video:self.pump_until(self.video_page_ready)
                    else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and
                        frame.image_pipeline.displayed_key[:2]==(frame.image_pipeline.generation,frame.shared_config.batch_idx))
                    image=frame.show_bmp_in_panel
                    self.assertGreater(min(image.size),0)
                    self.assertGreater(frame.ImgManager.title_max_size[1],0)
                    self.assertGreater(len(frame.ImgManager.xy_grids_id_list),0)
                    extrema=image.convert('RGB').getextrema()
                    self.assertTrue(any(low<high for low,high in extrema),'Title text must be visible on the background')
                    export=frame.ImgManager.video_stitch_snapshot()
                    export._video_lazy_frames=True
                    with patch.object(export,'img_preprocessing',side_effect=AssertionError('Title-only pages must not decode source pixels')):
                        self.assertEqual(export.stitch_images(1,[],flist=list(frame.ImgManager.flist)),0)
                    self.assertGreater(min(export.img.size),0)

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

    def test_cache_jpg_quality_can_differ_from_export_then_follow_again(self):
        from PIL.JpegImagePlugin import get_sampling
        frame=self.frame;frame.cache_save_format.SetSelection(0)
        frame.cache_quality_follow_save.SetValue(False)
        frame.cache_jpg_quality.SetValue(25);frame.save_quality.SetValue(95)
        frame.show_img_init();self.warm_current_window()
        cfg=frame.shared_config;vm=frame.video_manager
        path=Path(cfg.video_path[0])/vm._filename_converter(20,0)
        with Image.open(path) as image:low=sum(image.quantization[0])
        self.assertEqual(cfg.save_quality,25)
        self.assertEqual(frame.ImgManager.cache_jpeg_quality,25)
        self.assertEqual(frame.ImgManager.layout_params[42],95)
        frame.cache_quality_follow_save.SetValue(True)
        frame.show_img_init();self.warm_current_window()
        with Image.open(path) as image:
            self.assertEqual(get_sampling(image),0)
            self.assertLess(sum(image.quantization[0]),low)
        self.assertEqual(cfg.save_quality,95)

    def test_jpeg_quality_applies_on_refresh_and_is_captured_in_snapshot(self):
        frame=self.frame
        frame.save_quality.SetValue(73)
        self.assertEqual(frame.shared_config.save_quality,100)
        frame.show_img_init()
        self.assertEqual(frame.shared_config.save_quality,73)
        self.assertEqual(frame.ImgManager.layout_params[42],73)
        snapshot=frame.ImgManager.video_stitch_snapshot()
        frame.save_quality.SetValue(25)
        self.assertEqual(snapshot.layout_params[42],73)
        self.assertEqual(frame.shared_config.save_quality,73)

    def test_jpeg_quality_refresh_rebuilds_raw_video_frames(self):
        from PIL.JpegImagePlugin import get_sampling
        frame=self.frame;frame.cache_save_format.SetSelection(0)
        tables=[]
        for quality in (25,95):
            frame.save_quality.SetValue(quality);frame.show_img_init()
            self.warm_current_window()
            cfg=frame.shared_config
            path=Path(cfg.video_path[0])/frame.video_manager._filename_converter(20,0)
            with Image.open(path) as image:
                self.assertEqual(get_sampling(image),0)
                tables.append(sum(image.quantization[0]))
        self.assertGreater(tables[0],tables[1])

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

    def test_paused_over_budget_releases_idle_accelerators_and_can_resume_from_disk(self):
        self.warm_current_window()
        frame = self.frame
        vm = frame.video_manager
        config = frame.shared_config
        bitmap = frame.show_bmp_in_panel
        pages = list(config.cache_img)
        frame.resource_monitor.close()
        frame.resource_monitor.thread.join(timeout=3)
        config.memory_budget = 512 * 1024**2
        vm._configure_video_memory()
        rss = config.memory_budget + 256 * 1024**2
        self.assertTrue(vm._pixel_cache.put('idle-test', Image.new('RGB', (32, 32))))
        with patch.object(frame.resource_monitor, 'read_snapshot', return_value={'memory_now': rss}):
            frame._check_idle_memory_pressure()
            with frame.memory_reclaimer.lock:
                frame.memory_reclaimer.idle_since -= 11.
            frame._check_idle_memory_pressure()
            frame.memory_reclaimer.future.result(timeout=5)
        self.native_release.assert_called_with(trim_working_set=True)
        self.assertEqual(vm._decoder_bank.idle_bytes, 0)
        self.assertIsNone(vm._pixel_cache.get('idle-test'))
        self.assertIs(frame.show_bmp_in_panel, bitmap)
        self.assertTrue(all(Path(path).is_file() for path in pages if path))
        frame._seek_display_page(22)
        self.pump_until(lambda: getattr(frame, '_status_display_batch', None) == 21)

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

    def test_rapid_next_during_frame_publication_displays_latest_page_without_decode_failure(self):
        self.warm_current_window()
        vm=self.frame.video_manager
        if not vm._decoder_bank.available:self.skipTest('PyAV required')
        entered,release=threading.Event(),threading.Event()
        gate=threading.Lock();claimed=[];statuses=[]
        original=vm._store_decoded_frame;disabled=set(vm._decoder_bank.disabled)
        def delayed(index,*args):
            with gate:
                hold=index>=27 and not claimed
                if hold:claimed.append(index)
            if hold:
                entered.set()
                if not release.wait(10):raise TimeoutError('GUI did not release superseded frame publication')
            return original(index,*args)
        try:
            with patch.object(vm,'_store_decoded_frame',side_effect=delayed), \
                    patch.object(vm,'_set_video_status',side_effect=statuses.append):
                for _ in range(6):
                    self.frame.next_img(None)
                    self.app.Yield(True)
                self.pump_until(entered.is_set)
                while self.frame.shared_config.batch_idx<60:
                    self.frame.next_img(None)
                    self.app.Yield(True)
                self.assertEqual(self.frame.shared_config.batch_idx,60)
                heartbeat=[];wx.CallAfter(lambda:heartbeat.append(True))
                self.pump_until(lambda:bool(heartbeat))
                release.set()
                self.pump_until(lambda:self.video_page_ready() and self.frame._status_display_batch==60,timeout=20)
            self.assertFalse([text for text in statuses if 'failed' in text.lower()],statuses)
            self.assertEqual(vm._decoder_bank.disabled,disabled)
        finally:release.set()

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
        original = vm._publish_stitched_page
        def compose(batch, sources, token, plan, *args):
            calls.append((batch, plan))
            # Borrowed CPU slots may legitimately start 23-25 before the
            # GUI changes quotas. Occupy all four permits so page 26 is
            # demonstrably queued when the new reservation is published.
            if 22 <= batch <= 25:
                if sum(22 <= item[0] <= 25 for item in calls) == 4:
                    entered.set()
                if not release.wait(5):
                    raise TimeoutError('GUI did not release current composition')
            return original(batch, sources, token, plan, *args)
        try:
            with patch.object(vm, '_publish_stitched_page', compose):
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

    def test_play_after_uncached_seek_waits_for_requested_page_before_advancing(self):
        self.warm_current_window()
        cfg = self.frame.shared_config
        try:
            with patch.object(self.frame.video_manager,'update_cache'), patch.object(
                    self.frame,'_schedule_next_video_tick') as schedule:
                self.frame.slider_value_change(None,value=51)
                self.assertEqual(cfg.batch_idx,50)
                self.frame.toggle_play(None)
                self.assertTrue(self.frame._play_timer_suspended)
                schedule.assert_not_called()
                self.frame.on_play_timer(None)
                self.assertEqual(cfg.batch_idx,50)
        finally:
            cfg.is_playing = False
            self.frame.play_timer.Stop()
            self.frame._cancel_pending_frame_wait()

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

    def test_image_power_tooltip_shows_final_cache_supply_on_fourth_line(self):
        cfg = self.frame.shared_config
        old_mode, old_playing = cfg.video_mode, cfg.is_playing
        pacer = self.frame.image_pipeline.supply_pacer
        try:
            cfg.video_mode = False
            cfg.is_playing = True
            with patch.object(pacer, 'supply_period', return_value=.125):
                self.frame._refresh_power_tooltip()
                lines = self.frame.power_mode.GetToolTip().GetTip().splitlines()
                self.assertEqual(len(lines), 4)
                self.assertIn('Supply: 8.00 FPS', lines[3])
            with patch.object(pacer, 'supply_period', return_value=None):
                self.frame._refresh_power_tooltip()
                self.assertIn('Supply: sampling...', self.frame.power_mode.GetToolTip().GetTip())
            cfg.is_playing = False
            self.frame._refresh_power_tooltip()
            self.assertNotIn('Supply:', self.frame.power_mode.GetToolTip().GetTip())
        finally:
            cfg.video_mode, cfg.is_playing = old_mode, old_playing

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
            self.frame.show_original_panel.SetValue(False)
            self.frame.show_all_func_layout.ChangeValue('2,1')
            samples=[]
            with patch.object(Image.Image,'save',make_sampler(samples)):
                self.frame.refresh(None)
                if video:
                    self.pump_until(self.video_page_ready)
                else:self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            self.assertTrue(samples)
            self.assertTrue(all(count>0 for count in samples))

    def test_power_change_preserves_four_stage_shared_admission(self):
        self.frame.show_all_func.SetValue(True)
        self.frame.show_all_func_layout.ChangeValue('2,1')
        self.frame.refresh(None)
        self.pump_until(self.video_page_ready)
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

    def test_full_scale_video_canvas_can_exceed_soft_budget_without_rescaling(self):
        self.frame.row_col.ChangeValue('4,6')
        self.frame.row_col_one_img.ChangeValue('1,1')
        self.frame.row_col_img_unit.ChangeValue('3,1')
        self.frame.img_resolution.ChangeValue('1280,720')
        self.frame.show_scale.ChangeValue('1,1')
        self.frame.show_custom_func.SetValue(False)
        self.frame.show_all_func.SetValue(False)
        self.frame.title_show.SetValue(True)
        self.frame.title_font_size.ChangeValue('20')
        self._set_test_power(4,4,96*1024**2)
        self.frame.refresh(None)
        self.pump_until(self.video_page_ready,timeout=25)
        width,height=self.frame.img_size
        self.assertGreaterEqual(width,6*1280)
        self.assertGreaterEqual(height,4*720)
        self.assertLess(height,4*1000,'Unused image-unit cells must not become full-height images')
        self.assertEqual(list(self.frame.ImgManager.layout_params[4]),[1,1])
        self.assertGreater(width*height*16,self.frame.shared_config.memory_budget)
        self.assertTrue(Path(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx]).is_file())

    def test_native_bitmap_access_failure_falls_back_to_tiles_without_losing_geometry(self):
        from mulimgviewer.src.display_canvas import TiledImageCanvas
        image=Image.new('RGBA',(160,96),(20,40,60,128))
        with patch.object(wx.Bitmap,'FromBufferRGBA',side_effect=RuntimeError('Failed to gain raw access to bitmap data.')):
            self.frame.display_bitmap(False,image,prepared_rgba=image.tobytes())
        canvas=self.frame.img_last
        self.assertIsInstance(canvas,TiledImageCanvas)
        self.assertEqual(canvas.image.size,image.size)
        self.assertIs(self.frame._img_bindings_target,canvas)
        bitmap=canvas._tile(0,0)
        pixels=bitmap.ConvertToImage()
        self.assertEqual((pixels.GetWidth(),pixels.GetHeight()),image.size)
        self.assertEqual(pixels.GetAlpha(0,0),128)
        self.frame.display_bitmap(False,image)
        self.assertIsInstance(self.frame.img_last,wx.StaticBitmap)
        self.assertIs(self.frame._img_bindings_target,self.frame.img_last)

    def test_large_display_skips_full_native_bitmap_and_bounds_native_tile_cache(self):
        from mulimgviewer.src.display_canvas import TiledImageCanvas
        from mulimgviewer.src.video_memory import rgba_display
        source=Image.new('RGBA',(9000,80),(20,40,60,255))
        image,data=rgba_display(source)
        source.close()
        self.assertIsNone(data,'Wide canvases must not retain a full RGBA byte copy')
        with patch.object(self.frame.ImgManager.ImgF,'PIL2wx',side_effect=AssertionError('No full native bitmap')):
            self.frame.display_bitmap(False,image,prepared_rgba=data)
        canvas=self.frame.img_last
        self.assertIsInstance(canvas,TiledImageCanvas)
        self.assertEqual(canvas.image.size,(9000,80))
        canvas.cache_limit=512*80*4*2
        for x in range(0,image.width,512):canvas._tile(x,0)
        self.assertLessEqual(canvas.tile_bytes,canvas.cache_limit)
        self.assertLessEqual(len(canvas.tiles),2)

    def test_tiled_canvas_scroll_paints_only_visible_full_resolution_tiles(self):
        from mulimgviewer.src.display_canvas import TiledImageCanvas
        window=wx.Frame(None,size=(320,180))
        viewport=wx.ScrolledWindow(window)
        viewport.SetScrollRate(1,1)
        source=Image.new('RGBA',(9000,80),(20,40,60,255))
        canvas=TiledImageCanvas(viewport,viewport,source)
        canvas.SetSize(source.size);viewport.SetVirtualSize(source.size)
        try:
            window.Show();window.Raise();self.app.Yield(True)
            canvas.tiles.clear();canvas.tile_bytes=0
            viewport.Scroll(8192,0);canvas.Refresh(False);canvas.Update()
            self.pump_until(lambda:(8192,0) in canvas.tiles)
            self.assertGreaterEqual(canvas.visible_rect().x,8192)
            self.assertLessEqual(len(canvas.tiles),2,'Scrolling must not render every intervening tile')
            self.assertLessEqual(canvas.tile_bytes,canvas.cache_limit)
        finally:window.Destroy();self.app.Yield(True)


    def test_viewport_canvas_paints_beyond_native_window_limit_and_preserves_mouse_coordinates(self):
        from mulimgviewer.src.display_canvas import TiledImageCanvas
        window=wx.Frame(None,size=(320,180))
        viewport=wx.ScrolledWindow(window);viewport.SetScrollRate(1,1)
        source=Image.new('RGBA',(49232,80),(20,40,60,255))
        canvas=TiledImageCanvas(viewport,viewport,source)
        viewport.SetVirtualSize(source.size)
        try:
            window.Show();self.app.Yield(True);canvas._sync_viewport()
            canvas.Update();self.pump_until(lambda:bool(canvas.tiles))
            self.assertLessEqual(canvas.Size.width,viewport.ClientSize.width)
            viewport.Scroll(45000,0)
            viewport.Refresh();viewport.Update()
            self.pump_until(lambda:any(x>=44000 for x,y in canvas.tiles))
            self.assertEqual(canvas.Position,(0,0))
            received=[]
            canvas.bind_image_mouse(wx.EVT_LEFT_DOWN,lambda event:received.append(tuple(event.GetPosition())))
            event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition((21,13))
            canvas.GetEventHandler().ProcessEvent(event)
            self.assertEqual(received,[(45021,13)])
            self.assertLessEqual(canvas.tile_bytes,canvas.cache_limit)
        finally:
            window.Destroy();self.app.Yield(True);source.close()

    def test_main_switches_between_viewport_and_regular_image_without_clipping(self):
        from mulimgviewer.src.display_canvas import TiledImageCanvas
        with Image.new('RGBA',(49232,80),'red') as image:
            self.frame.display_bitmap(False,image)
            canvas=self.frame.img_last
            self.assertIsInstance(canvas,TiledImageCanvas)
            self.assertTrue(canvas.viewport_backed)
            self.assertIs(canvas.GetParent(),self.frame.scrolledWindow_img)
            self.assertFalse(self.frame.img_panel.IsShown())
            self.frame.Show();self.app.Yield(True)
            self.frame.auto_layout(frame_resize=True)
            self.app.Yield(True)
            self.assertGreaterEqual(self.frame.scrolledWindow_img.GetVirtualSize().width,image.width)
            with Image.new('RGBA',(80,48),'blue') as small:
                self.frame.display_bitmap(False,small)
                self.assertIsInstance(self.frame.img_last,wx.StaticBitmap)
                self.assertTrue(self.frame.img_panel.IsShown())
                self.assertIs(self.frame.img_last.GetParent(),self.frame.img_panel)

    def test_stale_or_cancelled_display_does_not_latch_future_requests(self):
        vm=self.frame.video_manager;cfg=self.frame.shared_config
        first,second=Future(),Future()
        with patch.object(vm._display_executor,'submit',side_effect=[first,second]) as submit:
            self.frame._request_video_display(20,'cached-page')
            cfg.batch_idx=21
            image=Image.new('RGBA',(80,48),'blue')
            first.set_result(((image,image,None),.001))
            self.pump_until(lambda:vm._display_future is None)
            self.assertFalse(vm._display_delivery_pending)
            cfg.batch_idx=20
            self.frame._request_video_display(20,'cached-page')
            self.assertEqual(submit.call_count,2)
            second.cancel()
            self.pump_until(lambda:vm._display_future is None)
            self.assertFalse(vm._display_delivery_pending)
            image.close()

    def test_return_to_painted_page_supersedes_pending_load_without_cancelling_newer_request(self):
        vm=self.frame.video_manager;cfg=self.frame.shared_config;token=vm._window_token
        self.frame._video_display_key=(21,'painted',token)
        first,second=Future(),Future();first.set_running_or_notify_cancel()
        with patch.object(vm._display_executor,'submit',side_effect=[first,second]) as submit:
            self.frame._request_video_display(20,'cached-page')
            cfg.batch_idx=21;self.frame._request_video_display(21,'painted')
            self.assertFalse(vm._display_delivery_pending)
            cfg.batch_idx=20;self.frame._request_video_display(20,'cached-page')
            self.assertEqual(submit.call_count,2)
            image=Image.new('RGBA',(80,48),'blue')
            first.set_result(((image,image,None),.001))
            self.app.Yield(True)
            self.assertTrue(vm._display_delivery_pending,'Old completion must not clear a newer request')
            second.cancel();self.pump_until(lambda:vm._display_future is None)
            image.close()

    def test_status_first_field_hover_shows_raw_and_display_sizes_in_image_and_video_modes(self):
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_custom_func.SetValue(True)
            self.frame.show_all_func.SetValue(False)
            self.frame.refresh(None)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
            frame=self.frame;manager=frame.ImgManager
            self.assertEqual(len(manager._status_source_images),len(manager.flist))
            size,mode=manager._status_source_images[0]
            self.assertGreater(min(size),0)
            event=Mock()
            bar=frame.main_status_bar
            event.GetPosition.return_value=bar.GetFieldRect(0).GetPosition()+wx.Point(1,1)
            with patch('PIL.Image.open',side_effect=AssertionError('Hover must not decode')):
                frame._on_status_bar_hover(event)
            tip=bar.GetToolTip().GetTip()
            self.assertIn(f'{size[0]} x {size[1]} {mode}',tip)
            width,height=frame.img_size
            self.assertIn(f'Page mosaic: {width} x {height} RGBA',tip)
            event.Skip.assert_called_once()

    def test_two_row_canvas_hides_original_and_keeps_hidden_algorithms_idle(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        from mulimgviewer.src.custom_func.contract import processing_indices
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_all_func_layout.ChangeValue('2,1')
            self.frame.show_custom_func.SetValue(False)
            self.frame.show_all_func.SetValue(True)
            for show_original in (False,True):
                self.frame.show_original_panel.SetValue(show_original)
                self.frame.refresh(None)
                if video:
                    self.pump_until(self.video_page_ready)
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
                self.assertTrue(list((cache.visible.root/'original'/'stitched'/'frames').glob('*.png')))

    def test_shrinking_algorithm_canvas_retires_hidden_processing_and_mosaic_caches(self):
        from mulimgviewer.src.custom_func import main as functions
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_custom_func.SetValue(False)
            self.frame.show_all_func.SetValue(True)
            self.frame.show_original_panel.SetValue(True)
            self.frame.show_all_func_layout.ChangeValue('6,1')
            self.frame.refresh(None)
            vm=self.frame.video_manager;pipeline=self.frame.image_pipeline
            def quiet(pipeline=pipeline,video=video,vm=vm):
                if video:
                    return (self.video_page_ready()
                        and not vm.cache_update_pending() and not vm._pending_extract and not vm._window_stitches)
                return pipeline.displayed_key is not None and not pipeline.running
            self.pump_until(quiet)
            registry=self.frame.ImgManager._custom_algorithm_registry
            names=[entry[0] for entry in registry if entry[0]!='Original']
            root=pipeline.processing.visible.root
            for name in names:
                self.assertTrue(list((root/name/'processed').rglob('*.png')),name)
                self.assertTrue(list((root/name/'stitched'/'frames').glob('*.png')),name)
            calls=[];original=functions.main
            def process(calls,original,*args,**kwargs):
                calls.append(kwargs.get('algorithm_type'))
                return original(*args,**kwargs)
            with patch.object(functions,'main',partial(process,calls,original)):
                self.frame.show_original_panel.SetValue(False)
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
                self.pump_until(lambda:self.video_page_ready()
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
        self.pump_until(self.video_page_ready)
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
        self.assertIn('success',self.frame.main_status_bar.GetStatusText(3))
        pdfs=list(output.rglob('*.pdf'));self.assertTrue(pdfs)
        for path in pdfs:self.assertNotIn(b'/DCTDecode',path.read_bytes())
        self.assertEqual(self.frame.video_manager._window_token,old_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,0)
        self.frame.refresh(None)
        self.pump_until(self.video_page_ready)
        self.assertNotEqual(self.frame.video_manager._window_token,old_token)
        self.assertEqual(self.frame.shared_config.cache_save_format,1)
        with Image.open(self.frame.shared_config.cache_img[self.frame.shared_config.batch_idx]) as image:
            self.assertEqual(image.format,'PNG')
        self.frame.output_scale.ChangeValue('1,0.5');self.frame.refresh(None)
        self.pump_until(self.video_page_ready)
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
                    self.pump_until(self.video_page_ready)
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
        self.pump_until(lambda:self.video_page_ready()
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
        self.pump_until(self.video_page_ready)
        self.frame.save_img(None)
        self.pump_until(lambda:not self.frame._export_active)
        self.assertIn('success',self.frame.main_status_bar.GetStatusText(3))
        pdfs=list(output.rglob('*.pdf'));self.assertTrue(pdfs)
        for p in pdfs:self.assertNotIn(b'/DCTDecode',p.read_bytes(),str(p))
        self.frame.cache_save_format.SetSelection(0);self.frame.refresh(None)
        self.pump_until(lambda:self.video_page_ready()
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
        self.assertIn('success',self.frame.main_status_bar.GetStatusText(3))
        with Image.open(output/'image/composed/page_000021.png') as image:
            self.assertIn(96,set(image.convert('RGBA').getchannel('A').getdata()))

    def test_video_alpha_refresh_changes_cached_mosaic_pixels(self):
        self.warm_current_window();vm=self.frame.video_manager
        old=vm._window_token
        self.frame.foreground_slider.SetValue(96);self.frame.background_slider.SetValue(48)
        self.frame.refresh(None)
        self.pump_until(lambda:vm._window_token is not None and vm._window_token!=old
            and self.video_page_ready())
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
            self.pump_until(lambda new_extension=new_extension:self.video_page_ready()
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
            self.assertIn('success',self.frame.main_status_bar.GetStatusText(3))
            path=output/'image/composed'/('page_000021'+suffix)
            self.assertTrue(path.is_file(),self.frame.main_status_bar.GetStatusText(3))
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
        from mulimgviewer.src.export_async import toggle_save_pause
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
        self.frame.png_compression.SetSelection(0);self.frame.pdf_compression.SetSelection(1)
        self.frame.save_quality.SetValue(63)
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
                self.frame.png_compression.SetSelection(2);self.frame.pdf_compression.SetSelection(0)
                self.frame.save_quality.SetValue(12)
                self.frame.save_img(None)
                self.assertIs(self.frame._export_future,future)
                self.assertEqual(captured[0].ImgManager.layout_params[5],[1.,1.])
                self.assertEqual(captured[0].ImgManager.png_compression_level,1)
                self.assertEqual(captured[0].ImgManager.pdf_compression,1)
                self.assertEqual(captured[0].ImgManager.layout_params[42],63)
                self.assertTrue(captured[0].ImgManager.flist)
                self.frame.SetStatusText_(['-1','-1','-1','Output: changed'])
                self.assertIn('Saving',self.frame.main_status_bar.GetStatusText(3))
                release.set()
                self.pump_until(lambda:not self.frame._export_active)
                self.assertEqual(self.frame.main_status_bar.GetStatusText(3),'Save: success')
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
            self.assertEqual(self.frame.main_status_bar.GetStatusText(3),'Save: cancelled')
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
        self.frame.show_original_panel.SetValue(False)
        self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
        self.frame.show_custom_func.SetValue(True)
        self.frame.on_show_custom_func_changed(None)
        self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
        pipeline=self.frame.image_pipeline
        self.pump_until(lambda:pipeline.displayed_key is not None and not pipeline.running)
        root=pipeline.processing.visible.root
        self.assertTrue((root/'Gaussian Blur'/'stitched'/'frames'/'page_000021.png').is_file())
        self.assertTrue((root/'original'/'stitched'/'frames'/'page_000021.png').is_file())
        self.assertFalse((root/'Image Darkening').exists())

    def test_algorithm_canvas_retains_blank_row_without_background_cropping(self):
        from mulimgviewer.src.custom_func.main import get_available_algorithms
        algorithm_count=1+sum(name!='Original' for name in get_available_algorithms())
        canvas_rows=algorithm_count+1
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_all_func_layout.ChangeValue(f'{canvas_rows},1')
            self.frame.show_original_panel.SetValue(True)
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
                    self.pump_until(self.video_page_ready)
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
                manager=self.frame.ImgManager
                image=manager.img
                bitmap=self.frame.img_last.GetBitmap()
                self.assertEqual((bitmap.GetWidth(),bitmap.GetHeight()),image.size)
                self.assertEqual(self.frame._last_display_logical_size,image.size)
                if mode=='original':base=image.size
                else:
                    gap_y=manager.layout_params[3][1]
                    self.assertEqual(image.size,(base[0],base[1]*panes+gap_y*(panes-1)))
                    occupied=algorithm_count if mode=='all' else 2
                    empty=image.crop((0,(base[1]+gap_y)*occupied,image.width,image.height))
                    self.assertEqual(empty.getextrema(),tuple((c,c) for c in color))
                    self.assertEqual(len(manager._blank_img_ids),(panes-occupied)*2)
                # The synchronous fallback must retain the same canvas as well.
                self.frame.display_bitmap(True,image)
                self.assertEqual(self.frame._last_display_logical_size,image.size)

    def test_single_algorithm_grid_leaves_unused_panes_blank_in_images_and_video(self):
        from mulimgviewer.src.index_catalog import IndexCatalog
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.show_original_panel.SetValue(True)
            self.frame.show_custom_func.SetValue(True)
            self.frame.show_all_func.SetValue(False)
            self.frame.show_all_func_layout.ChangeValue('2,2')
            self.frame.gap.ChangeValue('10,7,10,10,5,5,3,3,2,2')
            self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            for vertical in (False,True):
                self.frame.func_layout_vertical.SetValue(vertical)
                self.frame.refresh(None)
                if video:
                    self.pump_until(lambda:self.video_page_ready()
                        and getattr(self.frame.ImgManager,'_show_all_func_layout',None)==(2,2))
                else:
                    self.pump_until(lambda:self.frame.image_pipeline.displayed_key is not None)
                manager=self.frame.ImgManager
                self.assertFalse(manager.layout_params[38])
                self.assertEqual(manager._show_all_func_layout,(2,2))
                self.assertEqual(len(manager._blank_img_ids),4)
                self.assertEqual(manager._status_source_slots,(0,1,0,1,-1,-1,-1,-1))
                image=manager.img
                pane_width=(image.width-10)//2
                pane_height=(image.height-7)//2
                background=tuple((c,c) for c in manager.gap_color)
                # Non-square spacing must survive both asynchronous pipelines,
                # including blank panes and either algorithm ordering.
                self.assertEqual(image.crop((pane_width,0,pane_width+10,image.height)).getextrema(),background)
                self.assertEqual(image.crop((0,pane_height,image.width,pane_height+7)).getextrema(),background)
                first,second=manager.xy_grid[0],manager.xy_grid[2]
                self.assertEqual(tuple(second-first),
                    (0,pane_height+7) if vertical else (pane_width+10,0))
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
            self.assertTrue((cache.visible.root/name/'stitched'/'frames'/'page_000021.png').is_file())
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
        self.assertTrue((root/'sources'/'a'/'source.json').is_file())

    def test_layered_video_export_uses_sources_and_shared_page_names(self):
        self.warm_current_window()
        output=Path('export').absolute();output.mkdir()
        self.frame.out_path_str=str(output)
        self.frame.choice_output.SetSelection(2);self.frame.save_format.SetSelection(1)
        self.frame.save_img(None)
        self.pump_until(lambda:not getattr(self.frame,'_export_active',False))
        root=output/'video'
        self.assertTrue((root/'composed'/'page_000021.png').is_file(),self.frame.main_status_bar.GetStatusText(3))
        self.assertTrue((root/'algorithms'/'original'/'stitch_images'/'page_000021.png').is_file())
        self.assertTrue((root/'sources'/'sample'/'source.json').is_file())
        selected=root/'algorithms'/'original'/'select_images'
        self.assertEqual({p.name for p in selected.iterdir()},{'sample','sample_002'})

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
        self.pump_until(self.video_page_ready)
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
        self.assertIn('success',self.frame.main_status_bar.GetStatusText(3))
        self.assertEqual(manager.action_count,original_action)
        self.assertEqual(self.frame.shared_config.video_path,original_paths)
        for page in (1,2):self.assertTrue((root/f'video/composed/page_{page:06d}.png').exists())

    def test_custom_video_failure_is_visible_and_does_not_discard_raw_readiness(self):
        from mulimgviewer.src.custom_func import main as functions
        with patch.object(functions,'main',side_effect=RuntimeError('test model failure')):
            self.frame.show_custom_func.SetValue(True)
            self.frame.on_show_custom_func_changed(None)
            self.frame._custom_settings_changed()  # Explicit application for this pipeline test.
            self.pump_until(lambda:'test model failure' in self.frame.main_status_bar.GetStatusText(2))
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
        self.frame.parallel_sequential.SetValue(True)
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
        text = self.frame.main_status_bar.GetStatusText(1)
        self.assertIn('Image 21/80 | Folder 2/2', text)
        self.assertIn('Parallel manual', self.frame.main_status_bar.GetStatusText(2))
        self.assertIn(str(Path('images/b/020.png')), self.frame._status_field_tooltips[2])
        self.assertEqual(manager.action_count, page)
        snapshot = manager.video_stitch_snapshot()
        self.assertIs(snapshot._status_source_index, manager._status_source_index)
        for width in (600, 1200):
            self.frame.main_status_bar.SetClientSize((width, 24))
            self.frame._fit_status_fields()
            self.assertEqual(sum(self.frame._status_widths), self.frame.main_status_bar.GetClientSize().width)
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
            vm=self.frame.video_manager
            # Deliberately queue the scheduling worker. This used to make
            # the test capture None as its expected display token on CI.
            scheduler=getattr(vm,'_cache_executor')
            scheduler.submit(lambda:None).result(timeout=5)
            entered,release=threading.Event(),threading.Event()
            def hold_scheduler():
                entered.set()
                release.wait(5)
            blocked=scheduler.submit(hold_scheduler)
            try:
                self.assertTrue(entered.wait(2))
                vm.update_cache();self.frame.show_img()
                self.assertIsNone(getattr(vm,'_window_token'))
                token=(getattr(vm,'_cache_context_token')(),getattr(vm,'_window_generation'))
            finally:
                release.set()
                blocked.result(timeout=2)
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
        return tuple(self.frame.main_status_bar.GetStatusText(i) for i in range(3))

    def test_selected_box_counter_appends_to_second_status_field_in_image_and_video(self):
        frame=self.frame
        for video in (True,False):
            if not video:self._use_image_input()
            frame.img_resolution.ChangeValue('80,48');frame.show_scale.ChangeValue('1,1')
            frame.row_col_img_unit.ChangeValue('3,1')
            frame.title_show.SetValue(False)
            frame.show_original.SetValue(True);frame.show_magnifer.SetValue(True)
            frame.show_custom_func.SetValue(True);frame.show_all_func.SetValue(False)
            frame.xy_magnifier=[[4,4,24,16,1,1,False],[40,25,70,43,1,1,False]]
            frame.color_list=[wx.Colour(255,0,0),wx.Colour(0,0,255)]
            for control in (frame.magnifier,frame.rotation,frame.flip):control.SetValue(False)
            frame.select_img_box.SetValue(True)
            frame.refresh(None)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
            grid=frame._display_grid_order()[-1]  # Also exercise a processed pane.
            x,y=frame.ImgManager.xy_grid[grid]
            event=Mock();event.GetPosition.return_value=(int(x)+14,int(y)+10)
            frame.img_left_click(event)
            self.assertTrue(frame.main_status_bar.GetStatusText(1).endswith(' | Box 1/2'))
            event.GetPosition.return_value=(int(x)+55,int(y)+34)
            frame.img_left_click(event)
            self.assertEqual(frame.box_id,1)
            text=frame.main_status_bar.GetStatusText(1)
            self.assertTrue(text.endswith(' | Box 2/2'),text)
            self.assertIn('Page ',text)
            self.assertIn('Video' if video else 'Folder',text)
            self.assertIn('Box 2/2',frame._status_field_tooltips[1])
            frame.update_status_bar_for_current_page()
            self.assertEqual(frame.main_status_bar.GetStatusText(1),text)
            frame.select_img_box.SetValue(False)
            frame.update_status_bar_for_current_page()
            self.assertNotIn('Box ',frame.main_status_bar.GetStatusText(1))

    def test_select_image_context_menu_exports_clicked_algorithm_cell_in_image_and_video(self):
        from mulimgviewer.src.export_controller import source_slot
        from mulimgviewer.src.custom_func.contract import processing_indices
        for video in (True,False):
            if not video:self._use_image_input()
            for mode in ('original','single','all'):
                with self.subTest(video=video,custom=mode):
                    frame=self.frame
                    destination=Path(f'context_selection_{video}_{mode}').absolute();destination.mkdir()
                    frame.out_path_str=str(destination)
                    frame.auto_save_all.SetValue(True)
                    frame.choice_output.SetSelection(6)
                    frame.save_format.SetSelection(1)
                    frame.magnifier.SetValue(False)
                    frame.show_original_panel.SetValue(True)
                    frame.customfunc_choice.SetStringSelection('Gaussian Blur')
                    frame.show_custom_func.SetValue(mode=='single')
                    frame.show_all_func.SetValue(mode=='all')
                    frame.refresh(None)
                    if video:self.pump_until(self.video_page_ready)
                    else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
                    manager=frame.ImgManager
                    grid=next(i for i in reversed(range(len(manager.xy_grids_id_list))) if source_slot(manager,i)==1)
                    x,y=map(int,manager.xy_grid[grid])
                    event=Mock();event.GetPosition.return_value=(x+1,y+1)
                    def choose(menu,*args):
                        item=menu.FindItemByPosition(4)
                        self.assertEqual(item.GetItemLabel(),'Select image')
                        command=wx.CommandEvent(wx.EVT_MENU.typeId,item.GetId())
                        command.SetEventObject(menu)
                        self.assertTrue(menu.ProcessEvent(command))
                    with patch.object(frame,'PopupMenu',side_effect=choose):
                        frame.on_right_click(event)
                    self.pump_until(lambda:not getattr(frame,'_export_active',False)
                        and frame._export_future.done(),timeout=20)
                    self.assertEqual(frame._export_status,'Save: success')
                    self.assertEqual(frame._status_selected_grid,grid)
                    root=destination/('video' if video else 'image')
                    names={'original'}|{manager._custom_algorithm_registry[index][0]
                        for index in processing_indices(manager._custom_algorithm_registry,manager.layout_params)}
                    self.assertEqual({path.name for path in (root/'algorithms').iterdir()},names)
                    for name in names:
                        self.assertEqual(len(list((root/'algorithms'/name/'select_images').rglob('*.png'))),2)
                    self.assertFalse((root/'composed').exists())
                    self.assertFalse(list(root.rglob('stitch_images')))
                    # Left-click + output 2:select must produce identical files.
                    normal=destination.with_name(destination.name+'_button');normal.mkdir()
                    frame.out_path_str=str(normal);frame.auto_save_all.SetValue(False)
                    frame.choice_output.SetSelection(1);frame.img_left_click(event)
                    frame.save_img(None)
                    self.pump_until(lambda:not frame._export_active and frame._export_future.done(),timeout=20)
                    self.assertEqual(frame._export_status,'Save: success')
                    expected={str(p.relative_to(destination)):p.read_bytes() for p in destination.rglob('*.png')}
                    actual={str(p.relative_to(normal)):p.read_bytes() for p in normal.rglob('*.png')}
                    self.assertEqual(actual,expected)

            frame.select_img_box.SetValue(True)
            frame.xy_magnifier=[]
            frame.img_left_click(event)  # Empty/stale box lists must not call argmin.
            self.assertEqual(frame.box_id,-1)
            self.assertNotIn('Box ',frame.main_status_bar.GetStatusText(1))

    def test_image_file_list_button_and_context_select_export_only_clicked_entry(self):
        self._use_image_input();frame=self.frame
        listing=Path('parallel-image-list.txt').absolute()
        entries=[Path('images/a/000.png').absolute(),Path('images/a/001.png').absolute(),Path('images/b/000.png').absolute()]
        listing.write_text('\n'.join(map(str,entries)),encoding='utf-8')
        frame.ImgManager.init(str(listing),type=3)
        frame.row_col.ChangeValue('1,3');frame.row_col_one_img.ChangeValue('1,1')
        frame.show_custom_func.SetValue(True);frame.customfunc_choice.SetStringSelection('Gaussian Blur')
        frame.show_all_func.SetValue(False);frame.magnifier.SetValue(False)
        frame.auto_save_all.SetValue(False);frame.save_format.SetSelection(1)
        frame.shared_config.batch_idx=0;frame.slider_value.ChangeValue('1')
        frame.refresh(None)
        self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
        self.assertEqual(frame.ImgManager.flist,list(map(str,entries)))
        x,y=map(int,frame.ImgManager.xy_grid[1])
        event=Mock();event.GetPosition.return_value=(x+1,y+1)
        results=[]
        for context in (False,True):
            destination=Path(f'list_pick_{context}').absolute();destination.mkdir()
            frame.out_path_str=str(destination)
            if context:
                frame.choice_output.SetSelection(0)
                def choose(menu,*args):
                    item=menu.FindItemByPosition(4)
                    command=wx.CommandEvent(wx.EVT_MENU.typeId,item.GetId());command.SetEventObject(menu)
                    self.assertTrue(menu.ProcessEvent(command))
                with patch.object(frame,'PopupMenu',side_effect=choose):frame.on_right_click(event)
            else:
                frame.choice_output.SetSelection(1);frame.img_left_click(event);frame.save_img(None)
            self.pump_until(lambda:not frame._export_active and frame._export_future.done(),timeout=20)
            self.assertEqual(frame._export_status,'Save: success')
            for name in ('original','Gaussian Blur'):
                self.assertEqual(len(list((destination/'image/algorithms'/name/'select_images').rglob('*.png'))),1)
            results.append({str(path.relative_to(destination)):path.read_bytes() for path in destination.rglob('*.png')})
        self.assertEqual(results[0],results[1])

    def test_context_title_injection_targets_one_original_source_and_respects_rename(self):
        from mulimgviewer.src.export_controller import source_slot
        for video in (True,False):
            if not video:self._use_image_input()
            frame=self.frame;frame.magnifier.SetValue(False)
            frame.title_auto.SetValue(False);frame.title_show.SetValue(True)
            frame.title_font_size.ChangeValue('12')
            frame.show_custom_func.SetValue(True);frame.show_all_func.SetValue(False)
            frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            frame.rename.SetValue(False);frame.rename_edit_txt.ChangeValue('Injected target')
            frame.refresh(None)
            ready=self.video_page_ready if video else lambda:frame.image_pipeline.displayed_key is not None
            self.pump_until(ready)
            manager=frame.ImgManager
            original=frame.show_bmp_in_panel.tobytes()
            sources=list(manager.flist);untouched=Path(sources[0]).read_bytes()
            grid=next(i for i in reversed(range(len(manager.xy_grids_id_list))) if source_slot(manager,i)==1)
            x,y=map(int,manager.xy_grid[grid]);event=Mock();event.GetPosition.return_value=(x+1,y+1)
            writes=[];write=manager.update_image_exif_37510
            def inject(path,text):
                writes.append(path);return write(path,text)
            def choose(menu,*args):
                item=next(item for item in menu.GetMenuItems() if 'Inject title:' in item.GetItemLabel())
                command=wx.CommandEvent(wx.EVT_MENU.typeId,item.GetId());command.SetEventObject(menu)
                self.assertTrue(menu.ProcessEvent(command))
            with patch.object(manager,'update_image_exif_37510',side_effect=inject),patch.object(frame,'PopupMenu',side_effect=choose):
                frame.on_right_click(event)
            self.pump_until(ready)
            self.assertEqual(writes,[sources[1]])
            self.assertEqual(Path(sources[0]).read_bytes(),untouched)
            self.assertEqual(frame.show_bmp_in_panel.tobytes(),original)
            self.assertTrue(frame.rename.IsEnabled());self.assertTrue(frame.rename_edit_txt.IsEnabled())
            frame.rename.SetValue(True);frame.refresh(None);self.pump_until(ready)
            self.assertNotEqual(frame.show_bmp_in_panel.tobytes(),original)
            frame.rename.SetValue(False);frame.refresh(None);self.pump_until(ready)
            self.assertEqual(frame.show_bmp_in_panel.tobytes(),original)

    def test_parallel_video_frame_counts_match_image_modes_and_cache_paths_use_video_names(self):
        frame=self.frame;cfg=frame.shared_config
        frame.row_col.ChangeValue('1,2');frame.row_col_one_img.ChangeValue('2,2')
        frame.row_col_img_unit.ChangeValue('1,1');frame.title_show.SetValue(False)
        frame.show_magnifer.SetValue(False)
        frame.parallel_to_sequential.SetValue(False)
        for mode in (1,2):
            cfg.input_mode=mode;frame.choice_input_mode.SetSelection(mode)
            for sequential,count in ((False,1),(True,4),(False,1)):
                frame.parallel_sequential.SetValue(sequential)
                frame.refresh(None)
                self.pump_until(self.video_page_ready)
                self.assertEqual(cfg.count_per_action,count)
                self.assertEqual(len(frame.ImgManager.flist),2*count)
                sources=frame.ImgManager._status_video_sources
                self.assertEqual(sources,tuple((vid,index) for vid in (0,1)
                    for index in range(cfg.batch_idx*count,(cfg.batch_idx+1)*count)))
        vm=frame.video_manager
        cfg.real_video_path=[str(Path('sample.mp4').absolute())]*2
        vm.init_video_frame_cache()
        self.assertEqual([Path(path).name for path in cfg.video_path],['sample','sample_002'])
        self.assertTrue(all(Path(path).parent==Path('cache_frames/sources/frames/video') for path in cfg.video_path))

    def test_video_reselection_refreshes_catalog_names_and_original_paths(self):
        frame=self.frame;cfg=frame.shared_config
        initial=Path('sample.mp4').absolute()
        for stem in ('01','02'):shutil.copyfile(initial,stem+'.mp4')
        cfg.real_video_path=[str(Path(stem+'.mp4').absolute()) for stem in ('01','02')]
        cfg.input_mode=1
        self.assertTrue(frame.video_manager.select_video(type=-1))
        frame.refresh(None)
        self.pump_until(self.video_page_ready)
        root=Path('cache_frames/sources/json/video')
        self.pump_until(lambda:{p.name for p in root.glob('*.json')}=={'01.json','02.json'})
        for original,path in zip(cfg.real_video_path,cfg.video_path):
            self.assertEqual(Path(path).name,Path(original).stem)
            record=json.loads((root/(Path(original).stem+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['path'],original)
        self.assertFalse((Path(cfg.video_path[0])/'source.json').exists())

    def test_image_sources_use_original_paths_while_composed_cache_follows_outer_window(self):
        self._use_image_input()
        frame=self.frame;pipeline=frame.image_pipeline
        frame.show_custom_func.SetValue(True);frame.show_all_func.SetValue(False)
        frame.refresh(None)
        self.pump_until(lambda:pipeline.displayed_key is not None)
        root=Path('cache_frames/sources')
        original=Path(frame.ImgManager.flist[0])
        cached=Path(pipeline.cache[frame.shared_config.batch_idx][0])
        self.assertTrue(original.is_file())
        self.assertEqual(original.parent.resolve(),Path('images/a').resolve())
        self.assertFalse((root/'frames/image').exists())
        for folder in ('a','b'):
            record=json.loads((root/'json/image'/(folder+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['path'],str(Path('images',folder).absolute()))
        frame._seek_display_page(59)
        self.pump_until(lambda:pipeline.displayed_key is not None and pipeline.displayed_key[1]==58)
        self.pump_until(lambda:not cached.exists())
        self.assertTrue(original.is_file(),'Cache pruning must never remove the input image')
        self.assertEqual(Path(frame.ImgManager.flist[0]).resolve(),Path('images/a/058.png').resolve())
        self.assertFalse((root/'frames/image').exists())

    def test_algorithm_and_composed_cache_separate_frames_json_and_prune_together(self):
        from mulimgviewer.src.cache_layout import source_directory_names
        frame=self.frame
        for video in (True,False):
            if not video:self._use_image_input()
            frame.customfunc_choice.SetStringSelection('Image Darkening')
            frame.show_custom_func.SetValue(True);frame.show_all_func.SetValue(False)
            frame.show_all_func_layout.ChangeValue('2,1')
            frame.refresh(None)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
            batch=frame.shared_config.batch_idx
            filename=f'page_{batch+1:06d}.png'
            root=Path('cache_frames')
            composed=root/'composed/frames'/filename
            composed_json=root/'composed/json'/Path(filename).with_suffix('.json')
            self.assertTrue(composed.is_file())
            self.assertTrue(composed_json.is_file())
            self.assertEqual(json.loads(composed_json.read_text(encoding='utf-8'))['size'],list(frame.img_size))
            for name in ('original','Image Darkening'):
                base=root/'algorithms'/name/'stitched'
                self.assertTrue((base/'frames'/filename).is_file())
                self.assertTrue((base/'json'/Path(filename).with_suffix('.json')).is_file())
                self.assertEqual({p.name for p in base.iterdir()},{'frames','json'})
            processed=root/'algorithms/Image Darkening/processed'
            names=source_directory_names(frame.ImgManager)
            for directory in names.values():
                self.assertTrue((processed/'frames'/directory).is_dir())
                metadata=processed/'json'/(directory+'.json')
                self.assertTrue(metadata.is_file())
                descriptor=json.loads(metadata.read_text(encoding='utf-8'))
                self.assertTrue(Path(descriptor['source_catalog']).is_file())
                self.assertEqual(Path(descriptor['processed_frames_path']).resolve(),(processed/'frames'/directory).resolve())
            for directory in names.values():
                self.assertFalse(list((processed/'frames'/directory).glob('*.json')))
            self.assertFalse(list((root/'composed/frames').glob('*.json')))
            target=60 if batch<40 else 21
            frame._seek_display_page(target)
            if video:self.pump_until(self.video_page_ready)
            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and frame.image_pipeline.displayed_key[1]==target-1)
            self.pump_until(lambda:not composed.exists() and not composed_json.exists())
            for name in ('original','Image Darkening'):
                base=root/'algorithms'/name/'stitched'
                self.pump_until(lambda base=base:not (base/'frames'/filename).exists() and
                    not (base/'json'/Path(filename).with_suffix('.json')).exists())

    def test_original_image_paths_and_catalog_support_all_input_modes(self):
        self._use_image_input();frame=self.frame
        root=Path('cache_frames/sources')
        listing=Path('images.txt')
        listing.write_text('images/a/000.png\nimages/b/000.png\n',encoding='utf-8')
        cases=((2,str(Path('images/a')),0,{'a'}),(0,str(Path('images')),1,{'a','b'}),
               (1,['images/a','images/b'],2,{'a','b'}),(3,str(listing),3,{'a','b'}))
        for kind,paths,mode,expected in cases:
            with self.subTest(mode=mode):
                frame.ImgManager.init(paths,type=kind,video_mode=False)
                frame.shared_config.input_mode=mode;frame.choice_input_mode.SetSelection(mode)
                frame.shared_config.batch_idx=0
                frame.refresh(None)
                pipeline=frame.image_pipeline
                self.pump_until(lambda:pipeline.displayed_key is not None and pipeline.displayed_key[1]==0)
                self.assertFalse((root/'frames/image').exists())
                self.assertTrue(all(Path(path).is_file() for path in frame.ImgManager.flist))
                for folder in expected:
                    self.assertTrue((root/'json/image'/(folder+'.json')).is_file())
                    self.assertTrue(any(Path(path).resolve()==Path('images',folder,'000.png').resolve()
                        for path in frame.ImgManager.flist))

    def test_custom_index_paths_and_round_trip_follow_panes_in_sparse_layout(self):
        for video in (True,False):
            if not video:self._use_image_input()
            self.frame.row_col.ChangeValue('1,3')  # Two inputs, one empty source slot.
            self.frame.show_all_func_layout.ChangeValue('2,3')
            self.frame.show_original_panel.SetValue(True)
            self.frame.customfunc_choice.SetStringSelection('Gaussian Blur')
            for all_algorithms,vertical in ((False,False),(True,False),(True,True)):
                self.frame.show_custom_func.SetValue(not all_algorithms)
                self.frame.show_all_func.SetValue(all_algorithms)
                self.frame.func_layout_vertical.SetValue(vertical)
                self.frame.refresh(None)
                self.frame._seek_display_page(21)
                if video:
                    self.pump_until(lambda:getattr(self.frame,'_status_display_batch',None)==20 and self.video_page_ready())
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
                            self.assertEqual(Path(entry['path']).parent.parent.name,'frames')
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
            after=tuple(self.frame.main_status_bar.GetStatusText(i) for i in range(3))
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
            after=tuple(self.frame.main_status_bar.GetStatusText(i) for i in range(3))
            self.assertIn('Video 2/2',after[1])
            self.assertEqual(after,self._click_main_source(1))
            index._select_index(index.catalog.visual_page_start(35));index.jump_selected(None)
            self.assertIn('Video 1/2',self.frame.main_status_bar.GetStatusText(1))
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

    def test_video_csv_input_loads_six_entries_in_csv_order(self):
        folder=Path('csv-videos');folder.mkdir()
        for number in range(1,7):shutil.copyfile('sample.mp4',folder/f'{number:02}.mp4')
        listing=Path('videos.csv')
        listing.write_text('csv-videos/01.mp4,csv-videos/03.mp4\n'
            'csv-videos/02.mp4,csv-videos/04.mp4\n'
            'csv-videos/06.mp4,csv-videos/05.mp4\n',encoding='utf-8')
        self.frame.row_col.ChangeValue('3,2')
        self.assertTrue(self.frame._open_video_file_list(str(listing)))
        self.pump_until(self.video_page_ready)
        self.assertEqual([Path(path).stem for path in self.frame.shared_config.real_video_path],
                         ['01','03','02','04','06','05'])
        self.assertEqual(len(self.frame.ImgManager._status_video_sources),6)
        self.assertEqual(self.frame.shared_config.status_input_mode,3)

    def test_video_csv_partial_valid_input_retains_legacy_skip_missing_behavior(self):
        listing=Path('partial-videos.csv')
        listing.write_text('sample.mp4,missing.mp4\n',encoding='utf-8')
        self.assertTrue(self.frame._open_video_file_list(str(listing)))
        self.pump_until(self.video_page_ready)
        self.assertEqual(self.frame.shared_config.real_video_path,[str(Path('sample.mp4').absolute())])

    def test_invalid_video_csv_keeps_current_input_and_shows_bad_cell(self):
        self.warm_current_window()
        before=list(self.frame.shared_config.real_video_path)
        listing=Path('missing-video.csv');listing.write_text(',missing.mp4\n',encoding='utf-8')
        self.assertFalse(self.frame._open_video_file_list(str(listing)))
        self.assertEqual(self.frame.shared_config.real_video_path,before)
        self.assertIn('Input error',self.frame.main_status_bar.GetStatusText(0))
        text=self.frame.main_status_bar.GetStatusText(2)
        self.assertIn('row 1, column 2',text)
        self.assertIn('missing.mp4',text)

    def test_video_file_list_loads_videos_and_status_identifies_second_source(self):
        listing = Path('videos.txt')
        listing.write_text('sample.mp4\nsample.mp4\n', encoding='utf-8')
        self.assertTrue(self.frame._open_video_file_list(listing))
        self.pump_until(lambda: getattr(self.frame, '_video_display_key', (None,))[0] == 0)
        manager = self.frame.ImgManager
        grid = list(manager.xy_grids_id_list).index(1)
        self.frame.update_status_bar_for_current_page(grid)
        self.assertIn('Video 2/2', self.frame.main_status_bar.GetStatusText(1))
        self.assertIn('Image File List', self.frame.main_status_bar.GetStatusText(2))
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
        self.assertIn('Image File List',self.frame.main_status_bar.GetStatusText(2))

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
        text = self.frame.main_status_bar.GetStatusText(1)
        self.assertIn('Page 21/80', text)
        self.assertIn('Frame 21/80 | Video 2/2', text)
        self.assertIn('sample.mp4', self.frame.main_status_bar.GetStatusText(2))
        self.assertNotIn('cache_frames', self.frame.main_status_bar.GetStatusText(2))
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

    def test_invalid_initial_video_layout_reports_field_without_starting_cache(self):
        frame=self.frame;vm=frame.video_manager
        frame.ImgManager.layout_params=[]
        frame.magnifier_show_scale.ChangeValue('-1.-1')
        with patch.object(frame,'SetStatusText_') as status, \
                patch.object(vm,'_enqueue_cache_config') as enqueue:
            vm.update_cache()
            self.assertIsNone(vm._render_snapshot)
            enqueue.assert_not_called()
            self.assertIn('magnifier_show_scale',status.call_args.args[0][2])
            frame.show_img()  # Must preserve the validation message, not start waiting.
            enqueue.assert_not_called()
        frame.magnifier_show_scale.ChangeValue('-1,-1')
        vm.update_cache();frame.show_img()
        self.pump_until(self.video_page_ready)
        self.assertEqual(len(frame.ImgManager.layout_params),43)
        self.assertEqual(frame.ImgManager.layout_params[42],frame.save_quality.GetValue())

    def test_disk_backed_video_magnifier_preserves_resolution_and_gui_handoff(self):
        from mulimgviewer.src.disk_canvas import DiskCanvas
        frame=self.frame
        frame.show_scale.ChangeValue('1,1');frame.show_original.SetValue(True)
        frame.row_col_img_unit.ChangeValue('3,1');frame.title_show.SetValue(False)
        with patch('mulimgviewer.src.disk_canvas.LARGE_CANVAS_BYTES',0), \
                patch('mulimgviewer.src.disk_canvas.available_memory_bytes',return_value=0):
            frame.refresh(None);self.pump_until(self.video_page_ready)
            self.assertIsInstance(frame.ImgManager.img,DiskCanvas)
            old_size=frame.ImgManager.img.size;old_key=frame._video_display_key
            x,y=map(int,frame.ImgManager.xy_grid[0])
            frame.magnifier.SetValue(True)
            event=Mock();event.GetPosition.return_value=(x+10,y+10)
            frame.img_left_click(event)
            event.GetPosition.return_value=(x+42,y+28)
            frame.img_left_move(event);frame.img_left_release(event)
            self.pump_until(lambda:self.video_page_ready() and frame._video_display_key!=old_key)
            self.assertIsInstance(frame.ImgManager.img,DiskCanvas)
            self.assertEqual(frame.show_scale.GetValue(),'1,1')
            self.assertGreater(frame.ImgManager.img.height,old_size[1])
            self.assertEqual(len(frame.xy_magnifier),1)
            self.assertEqual(len(frame.ImgManager._status_video_sources),2)

    def test_long_video_frame_wait_never_resumes_timer_before_frame_is_ready(self):
        frame=self.frame;cfg=frame.shared_config
        cfg.is_playing=True;cfg.batch_idx=20;frame._play_timer_suspended=True
        callbacks=[]
        with patch('wx.CallLater',side_effect=lambda delay,callback:callbacks.append(callback) or Mock()), \
                patch.object(frame,'_video_cached_batch_path',return_value=None), \
                patch.object(frame,'_resume_play_timer_after_wait') as resume, \
                patch.object(frame,'show_img') as show:
            frame._schedule_frame_wait_retry(20,80,attempt=125)
            for _ in range(4):callbacks.pop(0)()
            self.assertEqual(cfg.batch_idx,20)
            self.assertTrue(frame._play_timer_suspended)
            resume.assert_not_called();show.assert_not_called()
            with patch.object(frame,'_video_cached_batch_path',return_value='ready.jpeg'):
                callbacks.pop(0)()
            show.assert_called_once_with()
            resume.assert_not_called()
        cfg.is_playing=False

    def test_refresh_submits_only_the_final_visible_slider_page(self):
        frame=self.frame;cfg=frame.shared_config
        cfg.batch_idx=21;frame.ImgManager.set_action_count(21)
        frame.slider_value.ChangeValue('21')  # Visible page 21 has zero-based ID 20.
        requests=[]
        with patch.object(frame.video_manager,'update_cache',side_effect=lambda:requests.append(cfg.batch_idx)), \
                patch.object(frame,'show_img'):
            frame.refresh(None)
        self.assertTrue(requests)
        self.assertEqual(set(requests),{20})
        self.assertEqual(frame.ImgManager.img_count,20*cfg.count_per_action)

    def test_magnifier_invalidation_suspends_playback_until_replacement_is_painted(self):
        frame=self.frame;cfg=frame.shared_config
        cfg.is_playing=True;frame._play_timer_suspended=False
        frame.play_timer.Start(1000,oneShot=True)
        frame._invalidate_render_cache()
        self.assertTrue(frame._play_timer_suspended)
        self.assertFalse(frame.play_timer.IsRunning())
        self.assertTrue(cfg.is_playing)
        cfg.is_playing=False

    def test_superseded_frame_wait_cannot_resume_or_cancel_the_new_wait(self):
        frame=self.frame;cfg=frame.shared_config;callbacks=[]
        cfg.is_playing=True;cfg.batch_idx=20;frame._play_timer_suspended=True
        with patch('wx.CallLater',side_effect=lambda delay,callback:callbacks.append(callback) or Mock()), \
                patch.object(frame,'_resume_play_timer_after_wait') as resume,patch.object(frame,'show_img') as show:
            frame._schedule_frame_wait_retry(20)
            cfg.batch_idx=21;frame._schedule_frame_wait_retry(21)
            active_timer=frame._pending_frame_wait_timer
            callbacks[0]()  # The old native callback was already queued before cancellation.
            self.assertIs(frame._pending_frame_wait_timer,active_timer)
            resume.assert_not_called();show.assert_not_called()
            self.assertTrue(frame._play_timer_suspended)
        cfg.is_playing=False

    def test_auto_row_col_waits_for_valid_settings_and_video_count_uses_resolved_shape(self):
        frame=self.frame;frame.row_col.ChangeValue('-1,-1')
        old_gap=frame.gap.GetValue();frame.gap.ChangeValue('invalid')
        self.assertFalse(frame.set_img_layout())
        self.assertEqual(frame.row_col.GetValue(),'-1,-1')
        frame.gap.ChangeValue(old_gap)
        frame.parallel_to_sequential.SetValue(True);frame.row_col_one_img.ChangeValue('1,3')
        self.assertEqual(frame._sync_video_count_per_action(),6)
        self.assertEqual(frame.row_col.GetValue(),'-1,-1')
        params=frame.set_img_layout()
        self.assertEqual(params[0],[1,2])
        self.assertEqual(frame.row_col.GetValue(),'1,2')
        self.assertEqual(frame._sync_video_count_per_action(),6)
        for value in ('0,1','-1,2','2,-1','-2,-2'):
            frame.row_col.ChangeValue(value)
            self.assertFalse(frame.set_img_layout())
            self.assertIsNone(frame._sync_video_count_per_action())

    def test_refresh_with_invalid_row_col_keeps_previous_layout_and_does_not_schedule_display(self):
        frame=self.frame;frame._commit_video_settings();self.warm_current_window()
        previous=frame.ImgManager.layout_params
        frame.row_col.ChangeValue('-1,2')
        with patch.object(frame.video_manager,'update_cache') as cache,patch.object(frame,'show_img') as display:
            frame.refresh(None)
        cache.assert_not_called();display.assert_not_called()
        self.assertIs(frame.ImgManager.layout_params,previous)
        self.assertIn('row_col',frame.main_status_bar.GetStatusText(2))

    def test_auto_row_col_renders_all_input_modes_orders_and_algorithm_layouts(self):
        frame=self.frame;cfg=frame.shared_config
        video_paths=list(cfg.video_path);real_paths=list(cfg.real_video_path)
        folders=[Path('auto-layout-images')/name for name in ('a','b')]
        for folder in folders:
            folder.mkdir(parents=True)
            for index in range(3):Image.new('RGB',(40,24),(index*30,80,100)).save(folder/f'{index}.png')
        listing=Path('auto-layout-images.txt').absolute()
        listing.write_text('\n'.join(str(path.absolute()) for path in (folders[0]/'0.png',folders[1]/'1.png',folders[0]/'2.png')),encoding='utf-8')
        frame.cache_frames.ChangeValue('1');frame.cache_multiplier.ChangeValue('1')
        cases=0
        for video in (False,True):
            for mode in range(4):
                for serial,sequential in ((False,False),(False,True),(True,False),(True,True)):
                    for algorithm in ('original','single','all'):
                        with self.subTest(video=video,mode=mode,serial=serial,sequential=sequential,algorithm=algorithm):
                            frame.video_mode.SetValue(video);cfg.video_mode=video
                            frame.parallel_to_sequential.SetValue(serial);frame.parallel_sequential.SetValue(sequential)
                            frame.row_col.ChangeValue('-1,-1');frame.row_col_one_img.ChangeValue('1,2')
                            frame.row_col_img_unit.ChangeValue('1,1');frame.title_show.SetValue(False)
                            frame.show_magnifer.SetValue(False);frame.show_original.SetValue(True)
                            frame.show_custom_func.SetValue(algorithm=='single');frame.show_all_func.SetValue(algorithm=='all')
                            frame.customfunc_choice.SetStringSelection('Gaussian Blur')
                            frame.show_all_func_layout.ChangeValue('2,2')
                            cfg.batch_idx=0;frame.slider_value.ChangeValue('1');cfg.status_input_mode=mode
                            cfg.input_mode=2 if mode==0 else 3 if mode==3 else 1
                            if video:
                                count=1 if mode==0 else 2
                                cfg.real_video_path=real_paths[:count];cfg.video_path=video_paths[:count]
                                cfg.video_fps_list=[10.]*count;cfg.video_num_list=[3]*count
                                # Real selection recreates directories removed when a source retires.
                                for directory in cfg.video_path:Path(directory).mkdir(parents=True,exist_ok=True)
                                frame.ImgManager.init(video_paths[0] if mode==0 else video_paths,
                                    type=2 if mode==0 else 1,parallel_to_sequential=serial,
                                    video_mode=True,video_fps_list=cfg.video_fps_list,video_num_list=cfg.video_num_list)
                            else:
                                kind=(2,0,1,3)[mode]
                                target=(str(folders[0]),str(folders[0].parent),list(map(str,folders)),str(listing))[mode]
                                frame.ImgManager.init(target,type=kind,parallel_to_sequential=serial and kind in (0,1))
                            expected=frame.ImgManager.layout_advice()
                            frame.refresh(None)
                            if video:self.pump_until(self.video_page_ready)
                            else:self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
                            self.assertEqual(frame.row_col.GetValue(),','.join(map(str,expected)))
                            self.assertEqual(frame.ImgManager.layout_params[0],expected)
                            self.assertGreater(cfg.count_per_action,0)
                            self.assertGreater(frame.ImgManager.img.width,0)
                            self.assertGreater(frame.ImgManager.img.height,0)
                            self.assertEqual(frame._status_display_batch,0)
                            if video:
                                self.pump_until(lambda:not frame.video_manager.cache_update_pending()
                                    and not frame.video_manager._pending_extract
                                    and not frame.video_manager._window_stitches)
                                maintenance=frame.video_manager._cleanup_future
                                if maintenance is not None:maintenance.result(timeout=5)
                            cases+=1
        self.assertEqual(cases,96)

    def test_layout_pair_validation_rejects_incomplete_and_nonfinite_values(self):
        frame=self.frame
        for name,text in (('row_col','4'),('show_scale','nan,1'),('output_scale','1,inf'),
                          ('magnifier_show_scale','-1.-1'),('line_width','2,2,2')):
            with self.subTest(field=name,text=text):
                control=getattr(frame,name);original=control.GetValue()
                control.ChangeValue(text)
                try:
                    with patch.object(frame,'SetStatusText_') as status:
                        self.assertFalse(frame.set_img_layout())
                        self.assertIn(name,status.call_args.args[0][2])
                finally:control.ChangeValue(original)

    def test_failed_snapshot_initialization_does_not_index_short_layout(self):
        frame=self.frame;vm=frame.video_manager
        for values in ([],[None]*33,[None]*41):
            frame.ImgManager.layout_params=values
            with patch.object(frame,'show_img_init',return_value=None), \
                    patch.object(vm,'_enqueue_cache_config') as enqueue:
                vm.update_cache()
                enqueue.assert_not_called()
                self.assertIsNone(vm._render_snapshot)

    def test_video_mode_rejects_image_directory_and_preserves_current_input_and_error(self):
        self.warm_current_window();frame=self.frame;cfg=frame.shared_config
        folder=Path('image-only').absolute();folder.mkdir();Image.new('RGB',(16,12),'red').save(folder/'frame.png')
        before=(list(cfg.real_video_path),list(cfg.video_num_list),list(cfg.video_path),cfg.batch_idx)
        output=frame.main_status_bar.GetStatusText(3)
        frame.choice_input_mode.SetSelection(1)
        with patch.object(wx,'DirDialog') as dialog:
            dialog.return_value.ShowModal.return_value=wx.ID_OK
            dialog.return_value.GetPath.return_value=str(folder)
            frame.open_all_img(None)
        self.assertEqual((cfg.real_video_path,cfg.video_num_list,cfg.video_path,cfg.batch_idx),before)
        self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
        self.assertIn('Video mode',frame.main_status_bar.GetStatusText(2))
        self.assertIn(str(folder),frame.main_status_bar.GetStatusText(2))
        frame.update_status_bar_for_current_page()
        self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
        self.assertEqual(frame.main_status_bar.GetStatusText(3),output)
        videos=Path('valid-video').absolute();videos.mkdir();shutil.copyfile('sample.mp4',videos/'clip.mp4')
        with patch.object(wx,'DirDialog') as dialog:
            dialog.return_value.ShowModal.return_value=wx.ID_OK
            dialog.return_value.GetPath.return_value=str(videos)
            frame.open_all_img(None)
        self.pump_until(self.video_page_ready)
        self.assertNotIn('error',frame.main_status_bar.GetStatusText(0).lower())
        self.assertIsNone(frame._input_feedback)

    def test_manual_image_selector_applies_ordered_folders_and_renders(self):
        from mulimgviewer.src.path_select import PathSelectFrame,on_video_mode_change,_PATH_SELECT_STATE
        frame=self.frame
        previous=dict(_PATH_SELECT_STATE)
        self.addCleanup(_PATH_SELECT_STATE.update,previous)
        on_video_mode_change(False)
        frame.shared_config.video_mode=False
        paths=[]
        for name,color in (('second','blue'),('first','red')):
            folder=Path(name).absolute();folder.mkdir()
            Image.new('RGB',(80,48),color).save(folder/'image.png')
            paths.append(str(folder))
        def apply_selection(kind,input_path=None):
            return frame._open_image_input(input_path,1)
        selector=PathSelectFrame(frame,apply_selection,lambda:0)
        selector.refresh_txt(paths)
        self.assertTrue(selector._finalize_and_return())
        self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
        self.assertEqual(frame.ImgManager.input_path,paths)
        self.assertEqual(frame.choice_input_mode.GetSelection(),2)
        self.assertFalse(frame.ImgManager.video_mode)

    def test_manual_video_selector_applies_ordered_paths_and_renders(self):
        from mulimgviewer.src.path_select import PathSelectFrame,on_video_mode_change,_PATH_SELECT_STATE
        frame=self.frame;cfg=frame.shared_config
        previous=_PATH_SELECT_STATE['video_mode']
        self.addCleanup(on_video_mode_change,previous)
        on_video_mode_change(True)
        paths=[]
        for name in ('second.mp4','first.mp4'):
            shutil.copyfile('sample.mp4',name);paths.append(str(Path(name).absolute()))
        selector=PathSelectFrame(frame,lambda *args,**kwargs:None,lambda:0,video_manager=frame.video_manager)
        selector.set_video_manager(frame.video_manager,cfg)
        selector.refresh_txt(paths)
        self.assertTrue(selector._finalize_and_return())
        self.pump_until(self.video_page_ready)
        self.assertEqual(cfg.real_video_path,paths)
        self.assertEqual(len(cfg.video_path),2)

    def test_manual_video_mode_rejects_image_directory_without_replacing_video_paths(self):
        from mulimgviewer.src.path_select import PathSelectFrame,on_video_mode_change,_PATH_SELECT_STATE
        frame=self.frame;cfg=frame.shared_config
        before=list(cfg.real_video_path)
        directory=Path('manual-images').absolute();directory.mkdir()
        Image.new('RGB',(16,12),'red').save(directory/'image.png')
        previous=_PATH_SELECT_STATE['video_mode']
        self.addCleanup(on_video_mode_change,previous)
        on_video_mode_change(True)
        selector=PathSelectFrame(frame,lambda *args,**kwargs:None,lambda:0,video_manager=frame.video_manager)
        selector.set_video_manager(frame.video_manager,cfg)
        selector.paths_text.SetValue(str(directory))
        self.assertFalse(selector._finalize_and_return())
        self.app.Yield(True)
        self.assertFalse(selector.IsBeingDeleted())
        selector.Destroy()
        self.assertEqual(cfg.real_video_path,before)
        self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
        self.assertIn('Not a supported video file',frame.main_status_bar.GetStatusText(2))

    def test_image_open_reports_empty_and_corrupt_inputs_then_recovers(self):
        self._use_image_input();frame=self.frame
        frame.show_img()
        self.pump_until(lambda:frame.image_pipeline.displayed_key is not None)
        before=frame.ImgManager.input_path
        output=frame.main_status_bar.GetStatusText(3)
        empty=Path('empty-images').absolute();empty.mkdir()
        for mode in (0,1):
            frame.choice_input_mode.SetSelection(mode)
            with patch.object(wx,'DirDialog') as dialog:
                dialog.return_value.ShowModal.return_value=wx.ID_OK
                dialog.return_value.GetPath.return_value=str(empty)
                frame.open_all_img(None)
            self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
            self.assertIn('image',frame.main_status_bar.GetStatusText(2).lower())
            self.assertEqual(frame.ImgManager.input_path,before)
        broken=Path('broken-images').absolute();broken.mkdir();(broken/'invalid.png').write_bytes(b'not an image')
        frame.choice_input_mode.SetSelection(0)
        with patch.object(wx,'DirDialog') as dialog:
            dialog.return_value.ShowModal.return_value=wx.ID_OK
            dialog.return_value.GetPath.return_value=str(broken)
            frame.open_all_img(None)
        self.pump_until(lambda:'error' in frame.main_status_bar.GetStatusText(0).lower())
        self.assertIn('image',frame.main_status_bar.GetStatusText(2).lower())
        self.assertEqual(frame.main_status_bar.GetStatusText(3),output)
        with patch.object(wx,'DirDialog') as dialog:
            dialog.return_value.ShowModal.return_value=wx.ID_OK
            dialog.return_value.GetPath.return_value=str(Path('images/a').absolute())
            frame.open_all_img(None)
        self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and frame._status_display_batch==0)
        self.assertIsNone(frame._input_feedback)
        self.assertNotIn('error',frame.main_status_bar.GetStatusText(0).lower())

    def test_manual_image_callback_reports_invalid_directory_and_can_load_valid_images(self):
        from types import SimpleNamespace
        from mulimgviewer.__main__ import MainAPP
        self._use_image_input();frame=self.frame
        empty=Path('manual-empty').absolute();empty.mkdir()
        app=SimpleNamespace(frame=[frame,Mock()],_last_manual_paths=[],
            _normalize_paths=lambda paths:list(paths or []),SetTopWindow=Mock())
        MainAPP.UpdateUI(app,0,input_path=[str(empty)],parallel_to_sequential=False)
        self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
        self.assertIn('No supported image files',frame.main_status_bar.GetStatusText(2))
        app.SetTopWindow.assert_called_with(frame)
        MainAPP.UpdateUI(app,0,input_path=[str(Path('images/a').absolute())],parallel_to_sequential=False)
        self.pump_until(lambda:frame.image_pipeline.displayed_key is not None and frame._status_display_batch==0)
        self.assertIsNone(frame._input_feedback)
        self.assertEqual(frame.choice_input_mode.GetSelection(),2)

    def test_open_button_reports_unexpected_load_exception_in_input_status(self):
        frame=self.frame;before=frame.shared_config.batch_idx
        frame.choice_input_mode.SetSelection(0)
        with patch.object(frame,'one_dir_mul_img',side_effect=OSError('test unreadable input')):
            self.assertFalse(frame.open_all_img(None))
        self.assertEqual(frame.shared_config.batch_idx,before)
        self.assertIn('Input error',frame.main_status_bar.GetStatusText(0))
        self.assertIn('test unreadable input',frame.main_status_bar.GetStatusText(2))

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
