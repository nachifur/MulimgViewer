"""Headless regressions using the production VideoManager and real FFmpeg.

Run with the application's Python environment and FFmpeg on PATH:
    python -m unittest test_video_cache -v
"""
import ast
import atexit
import copy
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import weakref
from collections import deque
from contextlib import ExitStack
from concurrent.futures import ALL_COMPLETED, CancelledError, Future, ThreadPoolExecutor, wait
from fractions import Fraction
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ffmpeg
import numpy as np
from PIL import Image


# Load the actual classes without importing the GUI/application startup tree.
source = Path(__file__).resolve().parents[2] / 'src/mulimgviewer/src/video_manager.py'
sys.path.insert(0, str(source.parent))
from dependency_scheduler import prepared, gather, run_inline
from viewer_state import SharedConfig
from video_timeline import page_count, page_segments, raw_dependencies
from video_paths import frame_filename, cache_extension
from cache_layout import page_name, save_cache_image
from thread_optimizer import (AdaptiveThreadAllocator, optimize_thread_allocation,
                              available_memory_bytes, stitch_memory_limit, buffer_levels, buffer_priority, ThreadAllocation)
from resource_monitor import run_video_process
from stage_allocator import allocate_stages
from pipeline_executor import PipelineWorkers
from admission_optimizer import AdaptiveAdmissionBudget
from video_decoder import DecoderBank
from video_memory import PixelCache, source_resolution
from playback_pacer import PlaybackPacer, ProductionJob, completion_estimates, refill_guard
tree = ast.parse(source.read_text(encoding='utf-8'))
classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
           and node.name in ('PerformanceMonitor', 'VideoManager')]
exec(compile(ast.Module(body=classes, type_ignores=[]), str(source), 'exec'), globals())


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg executable required')
class VideoCacheTests(unittest.TestCase):
    def setUp(self):
        self.previous_dir = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=80x48:rate=10:duration=8', '-c:v', 'mpeg4',
                        '-y', 'sample.mp4'], check=True, capture_output=True)
        self.cfg = SharedConfig()
        self.cfg.video_mode = True
        self.cfg.cache_multiplier = 3
        self.cfg.batch_idx = 20
        self.cfg.video_fps_list = [10.0, 10.0]
        self.cfg.video_num_list = [80, 80]
        self.cfg.real_video_path = [str(Path('sample.mp4').resolve())] * 2
        self.cfg.video_path = ['cache_frames/a', 'cache_frames/b']
        for path in self.cfg.video_path:
            Path(path).mkdir(parents=True)
        manager = SimpleNamespace(layout_params=[None] * 33, action_count=0)
        manager.set_action_count = lambda value: setattr(manager, 'action_count', value)
        self.owner = SimpleNamespace()
        # SimpleNamespace cannot be weak-referenced.
        class Owner:
            pass
        self.owner = Owner()
        self.owner.ImgManager = manager
        self.owner.compose_current_frame = lambda *a, **k: (Image.new('RGB', (80, 48)), 0)
        self.vm = VideoManager(self.owner, self.cfg, manager)
        self.vm._mark_batch_processed = lambda: None
        self.vm._set_video_status = lambda message: None

    def tearDown(self):
        self.vm._cache_executor.shutdown(wait=True)
        self.vm.shutdown()
        self.vm.executor.shutdown(wait=True)
        self.vm.stitch_executor.shutdown(wait=True)
        self.vm._maintenance_executor.shutdown(wait=True)
        self.vm._display_executor.shutdown(wait=True)
        os.chdir(self.previous_dir)
        self.temp.cleanup()

    def settle(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with self.vm._cache_guard:
                futures = set(self.vm._pending_extract.values()) | set(self.vm._window_stitches.values())
                if self.vm._cache_update_future is not None:
                    futures.add(self.vm._cache_update_future)
                if self.vm._cleanup_future is not None:
                    futures.add(self.vm._cleanup_future)
            if not futures:
                return
            for future in futures:
                if not future.cancelled():
                    try:
                        future.result(timeout=20)
                    except CancelledError:
                        pass  # A moving window may cancel after the check above.
        self.fail('Background work did not settle')

    def assert_window(self, lo, hi):
        self.settle()
        files = {int(p.stem.split('_')[1])-1 for p in self.vm.disk_cache_dir.glob('page_*.'+cache_extension(self.cfg))}
        self.assertEqual(files, set(range(lo, hi + 1)))
        for vid, directory in enumerate(self.cfg.video_path):
            start, end = self.vm._raw_windows.get(vid, (0, 0))
            names = {self.vm._filename_converter(i, vid) for i in range(start, end)}
            self.assertEqual({p.name for p in Path(directory).glob('*.jpeg')}, names)
        self.assertFalse(list(Path('cache_frames').rglob('__tmp_*')))

    def test_legacy_extract_with_retired_format_cannot_publish(self):
        old=copy.copy(self.cfg)
        self.cfg.cache_save_format=1
        self.vm._save_frame(self.cfg.real_video_path[0],20,21,0,config=old)
        self.assertFalse(list(Path(self.cfg.video_path[0]).glob('*.jpeg')))

    def test_png_native_and_ffmpeg_paths_write_real_lossless_png(self):
        self.cfg.cache_save_format=1
        for native in (True,False):
            with self.subTest(native=native):
                if native and not self.vm._decoder_bank.available:continue
                for folder in self.cfg.video_path:
                    for p in Path(folder).iterdir():p.unlink()
                if native:
                    self.vm._save_frame(self.cfg.real_video_path[0],20,21,0,config=self.cfg)
                else:
                    with patch.object(self.vm,'_decode_incremental',return_value=False):
                        self.vm._save_frame(self.cfg.real_video_path[0],20,21,0,config=self.cfg)
                for index in (20,21):
                    path=Path(self.cfg.video_path[0])/self.vm._filename_converter(index,0)
                    self.assertEqual(path.suffix,'.png')
                    with Image.open(path) as image:
                        self.assertEqual(image.format,'PNG')
                        self.assertEqual(image.size,(80,48))
                if native:
                    import av
                    with av.open(self.cfg.real_video_path[0]) as container:
                        reference=next(frame for i,frame in enumerate(container.decode(video=0)) if i==20).to_image()
                    with Image.open(Path(self.cfg.video_path[0])/self.vm._filename_converter(20,0)) as image:
                        self.assertEqual(image.convert('RGB').tobytes(),reference.convert('RGB').tobytes())

    def test_format_change_reschedules_cleanup_even_when_window_bounds_do_not_move(self):
        self.vm.update_cache();self.settle()
        previous=self.vm._stitch_window
        self.cfg.cache_save_format=1
        with patch.object(self.vm,'_schedule_video_cleanup') as schedule:
            self.assertTrue(self.vm._cache_context_changed())
            schedule.reset_mock()  # Initial invalidation cleanup may already have exited.
            self.vm.update_cache();self.settle()
            self.assertEqual(self.vm._stitch_window,previous)
            schedule.assert_called()
        self.vm._schedule_video_cleanup();self.settle()
        for folder in self.cfg.video_path:
            self.assertFalse(list(Path(folder).glob('*.jpeg')))
            self.assertTrue(list(Path(folder).glob('*.png')))

    def test_png_window_refills_and_cleans_outside_frames(self):
        self.cfg.cache_save_format=1
        self.vm.update_cache();self.settle()
        for video,directory in enumerate(self.cfg.video_path):
            first,last=self.vm._raw_windows[video]
            self.assertEqual({p.name for p in Path(directory).glob('*.png')},
                {self.vm._filename_converter(i,video) for i in range(first,last)})
            self.assertFalse(list(Path(directory).glob('*.jpeg')))
        self.cfg.batch_idx=60;self.vm.update_cache();self.settle()
        for video,directory in enumerate(self.cfg.video_path):
            first,last=self.vm._raw_windows[video]
            self.assertEqual({p.name for p in Path(directory).glob('*.png')},
                {self.vm._filename_converter(i,video) for i in range(first,last)})

    def test_raw_readers_survive_window_trim_and_are_removed_after_release(self):
        self.vm.update_cache();self.settle()
        token=self.vm._window_token
        first,last=self.vm._batch_range(80,self.cfg.count_per_action,20)
        path=Path(self.cfg.video_path[0])/self.vm._filename_converter(first,0)
        def waiting(*args,**kwargs):
            yield Future()
        with patch.object(self.vm,'_run_window_stitch_leased_steps',side_effect=waiting):
            steps=self.vm._run_window_stitch_steps(20,[(0,20)],token)
            next(steps)
        try:
            self.cfg.batch_idx=60;self.vm.update_cache();self.settle()
            self.vm._trim_video_window()
            self.assertTrue(path.is_file(),'Cleanup deleted a frame with an active reader')
        finally:steps.close()
        self.vm._maintenance_executor.submit(lambda:None).result(timeout=5)
        self.assertFalse(path.exists())
        self.assertFalse(self.vm._raw_readers)

    def test_cleanup_active_directories_need_no_repeated_realpath_but_stale_dirs_retire(self):
        self.vm.update_cache()
        self.settle()
        with patch.object(Path,'resolve',side_effect=AssertionError('unexpected active-directory resolution')):
            self.vm._trim_video_window()
        obsolete=Path('cache_frames/obsolete')
        obsolete.mkdir()
        (obsolete/'old.jpeg').write_bytes(b'old')
        self.vm._trim_video_window()
        self.assertFalse(obsolete.exists())
        self.assertTrue(all(Path(p).exists() for p in self.cfg.video_path))

    def test_equal_video_basenames_have_distinct_source_folders(self):
        self.cfg.real_video_path=['first/clip.mp4','second/clip.mp4']
        self.vm.init_video_frame_cache()
        a,b=map(Path,self.cfg.video_path)
        self.assertNotEqual(a,b)
        self.assertEqual(a,Path('cache_frames/sources/video/source_001/frames'))
        self.assertEqual(b,Path('cache_frames/sources/video/source_002/frames'))

    def test_raw_cleanup_preserves_custom_results_and_inflight_temporaries(self):
        self.vm.update_cache();self.settle()
        for cleanup in (self.vm._trim_video_window,self.vm._cleanup_dead_directories):
            with self.subTest(cleanup=cleanup.__name__):
                root=self.vm.cache_dir/'algorithms'
                temporary=root/'tmp_live';temporary.mkdir(parents=True,exist_ok=True)
                marker=temporary/'writing.png';marker.write_bytes(b'in progress')
                result=root/'result_ready';result.mkdir(exist_ok=True)
                cached=result/'0.png';cached.write_bytes(b'cached')
                cleanup()
                self.assertTrue(marker.is_file(),'Raw cleanup removed an active custom processing directory')
                self.assertTrue(cached.is_file(),'Raw cleanup removed algorithm results owned by another stage')

    def test_unknown_cleanup_candidate_outside_resolved_root_is_preserved(self):
        self.vm.update_cache()
        self.settle()
        escape=Path('cache_frames/escape')
        escape.mkdir()
        (escape/'marker').write_bytes(b'keep')
        outside=Path('outside_cache')
        outside.mkdir()
        target=outside.resolve()
        original=Path.resolve
        def resolve(path,*args,**kwargs):
            if path==escape:return target
            return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',new=resolve):self.vm._trim_video_window()
        self.assertTrue((escape/'marker').exists())
        self.assertTrue(outside.exists())

    def test_outer_window_batches_decode_and_reuses(self):
        with patch.object(self.vm, '_save_frame', wraps=self.vm._save_frame) as decode:
            self.vm.update_cache()
            self.assert_window(14, 26)
            # Per video: current, inner left/right, outer left/right; not 13 starts.
            self.assertEqual(decode.call_count, 10)
            self.vm.update_cache()
            self.settle()
            self.assertEqual(decode.call_count, 10)
            self.cfg.batch_idx = 23
            self.vm.update_cache()
            self.assert_window(14, 26)
            self.assertEqual(decode.call_count, 10)
            self.cfg.batch_idx = 24
            self.vm.update_cache()
            self.assert_window(18, 30)
            self.assertEqual(decode.call_count, 12)
        self.cfg.batch_idx = 20
        self.cfg.cache_multiplier = 1
        self.vm.update_cache()
        self.assert_window(18, 22)

    def test_refill_threshold_in_both_directions(self):
        for multiplier in (2, 3):
            with self.subTest(multiplier=multiplier):
                self.cfg.cache_multiplier = multiplier
                self.cfg.batch_idx = 20
                self.vm._invalidate_stitch_cache()
                self.vm.update_cache()
                outer = 2 * multiplier
                self.assert_window(20 - outer, 20 + outer)
                # One batch beyond the threshold: retain the existing window.
                self.cfg.batch_idx = 20 - outer + 3
                self.cfg.play_direction = -1
                self.vm.update_cache()
                self.assert_window(20 - outer, 20 + outer)
                # Exactly cache_num batches from the left edge: refill now.
                self.cfg.batch_idx = 20 - outer + 2
                self.vm.update_cache()
                center = self.cfg.batch_idx
                self.assert_window(center - outer, center + outer)

    def test_video_end_does_not_force_window_to_move(self):
        self.cfg.batch_idx = 1
        self.vm.update_cache()
        self.assert_window(0, 7)
        self.cfg.batch_idx = 2
        self.vm.update_cache()
        self.assert_window(0, 7)
        self.cfg.batch_idx = 78
        self.vm.update_cache()
        self.assert_window(72, 79)
        self.cfg.batch_idx = 77
        self.vm.update_cache()
        self.assert_window(72, 79)

    def test_jump_while_workers_active(self):
        self.vm.update_cache()
        self.cfg.batch_idx = 60
        self.vm.update_cache()
        self.assert_window(54, 66)

    def test_cache_request_does_not_wait_for_decode(self):
        entered, release = threading.Event(), threading.Event()
        original = self.vm._save_frame
        def slow_decode(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release decoder')
            return original(*args, **kwargs)
        try:
            with patch.object(self.vm, '_save_frame', slow_decode):
                self.vm.update_cache()
                self.assertTrue(entered.wait(2))
                # update_cache has returned while its decoder is still blocked.
                self.assertFalse(release.is_set())
                self.assertTrue(self.vm._cache_guard.acquire(timeout=0.2))
                self.vm._cache_guard.release()
                release.set()
                self.assert_window(14, 26)
        finally:
            release.set()

    def test_stitch_does_not_hold_cache_guard(self):
        entered, release = threading.Event(), threading.Event()
        compose = self.owner.compose_current_frame
        def slow_compose(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release compositor')
            return compose(*args, **kwargs)
        try:
            self.owner.compose_current_frame = slow_compose
            self.vm.update_cache()
            self.assertTrue(entered.wait(3))
            self.assertTrue(self.vm._cache_guard.acquire(timeout=0.2))
            self.vm._cache_guard.release()
            # A jump is schedulable even while an old compositor is blocked.
            self.cfg.batch_idx = 60
            self.vm.update_cache()
            release.set()
            self.assert_window(54, 66)
        finally:
            release.set()

    def test_prepared_video_pixels_preserve_blank_layout_background(self):
        image = Image.new('RGBA', (80, 48), (0, 0, 0, 0))
        image.paste((240, 120, 60, 255), (12, 8, 68, 40))
        image.save('prepared.png')
        original, prepared, rgba = self.vm._prepare_video_image('prepared.png', (0, 0, 0, 0))
        self.assertEqual(original.size, (80, 48))
        self.assertEqual(prepared.size, (80, 48))
        self.assertEqual(prepared.tobytes(), image.tobytes())
        self.assertEqual(rgba, prepared.tobytes())

    def test_context_change_while_workers_active(self):
        self.vm.update_cache()
        self.cfg.skip_frames = 1
        self.cfg.video_num_list = [40, 40]
        self.vm.update_cache()
        self.assert_window(14, 26)

    def test_layout_invalidation_rebuilds_stitches(self):
        self.vm.update_cache()
        self.settle()
        self.vm._invalidate_stitch_cache()
        with patch.object(self.vm, '_save_frame', wraps=self.vm._save_frame) as decode:
            self.vm.update_cache()
            self.assert_window(14, 26)
            self.assertEqual(decode.call_count, 0)

    def test_skip_and_unequal_lengths(self):
        self.cfg.skip_frames = 2
        self.cfg.video_num_list = [27, 9]
        self.cfg.batch_idx = 22
        self.vm.update_cache()
        self.assert_window(16, 26)
        self.assertEqual(self.vm._raw_windows.get(1), (8, 9))

    def test_sequential_crosses_video_boundary(self):
        self.cfg.parallel_to_sequential = True
        self.cfg.video_num_list = [8, 8]
        self.cfg.batch_idx = 8
        self.vm.update_cache()
        self.assert_window(2, 14)

    def test_multi_frame_batches_and_end(self):
        self.cfg.count_per_action = 3
        self.cfg.batch_idx = 25
        self.vm.update_cache()
        self.assert_window(19, 26)

    def test_cli_fallback_matches_absolute_frame_selection(self):
        self.vm._decoder_bank.disabled.update(self.cfg.real_video_path)
        self.cfg.video_path = self.cfg.video_path[:1]
        self.cfg.video_num_list = [40]
        self.cfg.skip_frames = 1
        self.cfg.batch_idx = 15
        with patch.object(ffmpeg, 'input', None):
            self.vm.update_cache()
            self.assert_window(9, 21)

    def test_fast_seek_matches_conservative_frames(self):
        self.cfg.skip_frames = 2
        self.cfg.video_num_list = [27, 27]
        self.vm._save_frame(self.cfg.real_video_path[0], 8, 12, 0)
        self.vm._fast_seek_paths[self.cfg.real_video_path[1]] = True
        self.vm._save_frame(self.cfg.real_video_path[1], 8, 12, 1)
        for index in range(8, 13):
            a = Path(self.cfg.video_path[0]) / self.vm._filename_converter(index, 0)
            b = Path(self.cfg.video_path[1]) / self.vm._filename_converter(index, 1)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_conservative_output_limit(self):
        self.vm._decoder_bank.disabled.update(self.cfg.real_video_path)
        with patch.object(subprocess, 'Popen', wraps=subprocess.Popen) as launch:
            self.vm._save_frame(self.cfg.real_video_path[0], 2, 5, 0)
        self.assertEqual(launch.call_count, 1)
        cmd = launch.call_args[0][0]
        self.assertEqual(cmd[cmd.index('-vframes') + 1], '4')
        self.assertNotIn('-vsync',cmd)
        self.assertEqual(cmd[cmd.index('-fps_mode')+1],'passthrough')

    def test_blocked_jpeg_publication_does_not_block_state_or_another_video(self):
        if not self.vm._decoder_bank.available:
            self.skipTest('PyAV required')
        second=Path('second.mp4').resolve()
        shutil.copyfile(self.cfg.real_video_path[0],second)
        self.cfg.real_video_path[1]=str(second)
        entered,release,other=threading.Event(),threading.Event(),threading.Event()
        first_dir=os.path.abspath(self.cfg.video_path[0])+os.sep
        second_dir=os.path.abspath(self.cfg.video_path[1])+os.sep
        original=os.replace
        def delayed(src,dst):
            target=os.path.abspath(str(dst))
            if target.startswith(first_dir) and target.endswith('.jpeg') and not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('JPEG publication held the shared state lock')
            result=original(src,dst)
            if target.startswith(second_dir) and target.endswith('.jpeg'):
                other.set()
            return result
        try:
            with patch.object(os,'replace',delayed):
                self.vm.update_cache()
                self.assertTrue(entered.wait(3))
                acquired=self.vm._cache_guard.acquire(timeout=.5)
                if acquired:self.vm._cache_guard.release()
                self.assertTrue(acquired,'GUI/shared state waited for disk publication')
                self.assertTrue(other.wait(2),'An unrelated video waited for another directory')
                release.set()
                self.assert_window(14,26)
        finally:
            release.set()

    def test_missing_source_after_readiness_is_revalidated_on_retry(self):
        original=self.owner.compose_current_frame
        def verify_sources(*args,**kwargs):
            for group in kwargs['flist']:
                for path in group:
                    with Image.open(path) as opened:
                        opened.load()
            return original(*args,**kwargs)
        self.owner.compose_current_frame=verify_sources
        self.vm.update_cache()
        self.assert_window(14,26)
        raw=Path(self.cfg.video_path[0])/self.vm._filename_converter(20,0)
        raw.unlink()
        Path(self.vm._cached_batch_path(20,validate=False)).unlink()
        self.cfg.cache_img[20]=None
        self.vm.update_cache()
        try:
            self.settle()
        except (OSError,ValueError):
            pass  # First compositor detects the missing source descriptor.
        self.vm.update_cache()
        self.assert_window(14,26)
        self.assertTrue(raw.exists())

    def test_known_ready_and_pending_raw_batches_do_not_rescan_disk(self):
        self.vm.update_cache()
        self.assert_window(14,26)
        token=self.vm._window_token
        with patch.object(self.vm,'_list_missing_range',side_effect=AssertionError('Redundant disk scan')):
            self.assertEqual(self.vm._queue_extract_run(0,14,26,token),[])
        pending=Future()
        self.vm._pending_extract[(0,20)]=pending
        self.vm._raw_ready_batches.discard((0,20))
        try:
            with patch.object(self.vm,'_list_missing_range',side_effect=AssertionError('Pending decode was rescanned')):
                self.assertEqual(self.vm._queue_extract_run(0,20,20,token),[pending])
            self.assertNotIn((0,20),self.vm._raw_ready_batches)
        finally:
            self.vm._pending_extract.pop((0,20),None)
            pending.cancel()

    def test_first_batch_stitches_before_its_decode_run_finishes(self):
        if not self.vm._decoder_bank.available:
            self.skipTest('PyAV required for incremental readiness')
        from video_decoder import DecoderSession
        token = ('streaming-test', 0)
        self.vm._window_token = token
        self.vm._stitch_window = (0, 10)
        self.vm._raw_windows = {0: (0, 11)}
        self.cfg.batch_idx = 0
        self.cfg.cache_img = [None]*11
        entered, release, stitched = threading.Event(), threading.Event(), threading.Event()
        original = DecoderSession.frames
        compose = self.vm._run_window_stitch
        def delayed(session, *args, **kwargs):
            for index, image in original(session, *args, **kwargs):
                yield index, image
                if index == 0:
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError('First batch was held behind its whole decode run')
        def record(*args, **kwargs):
            result = compose(*args, **kwargs)
            stitched.set()
            return result
        try:
            with patch.object(DecoderSession, 'frames', delayed), patch.object(self.vm, '_run_window_stitch', record):
                run = self.vm._queue_extract_run(0, 0, 5, token)[0]
                self.vm._queue_window_stitch(0, [(0,0)], token)
                self.assertTrue(entered.wait(2))
                self.assertTrue(stitched.wait(2))
                self.assertFalse(run.done())
                release.set()
                run.result(timeout=3)
        finally:
            release.set()

    def test_ready_batch_bypasses_batch_waiting_for_extraction(self):
        token = ('dependency-test', 0)
        self.vm._window_token = token
        self.vm._stitch_window = (0, 30)
        dependency = Future()
        self.vm._pending_extract[(0, 21)] = dependency
        ready = threading.Event()
        handled = []
        def compose(batch, *args):
            handled.append(batch)
            if batch == 22:
                ready.set()
        try:
            with patch.object(self.vm, '_run_window_stitch', compose):
                self.vm._queue_window_stitch(21, [(0, 21)], token)
                self.vm._queue_window_stitch(22, [(0, 22)], token)
                self.assertTrue(ready.wait(2))
                self.assertEqual(handled, [22])
                dependency.set_result(None)
                self.vm._pending_extract.pop((0, 21), None)
                self.settle()
                self.assertEqual(handled, [22, 21])
        finally:
            if not dependency.done():
                dependency.set_result(None)
            self.vm._pending_extract.pop((0, 21), None)

    def test_cleanup_with_none_token_cannot_delete_new_selection(self):
        entered, release = threading.Event(), threading.Event()
        new_directory = Path('cache_frames/new_selection')
        new_directory.mkdir()
        original = Path.iterdir
        def delayed(directory):
            if directory == self.vm.cache_dir:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Test did not release cleanup')
            return original(directory)
        try:
            with patch.object(Path, 'iterdir', delayed):
                future = self.vm._maintenance_executor.submit(self.vm._trim_video_window)
                self.assertTrue(entered.wait(2))
                self.cfg.video_path = [str(new_directory)]
                self.vm._window_generation = getattr(self.vm, '_window_generation', 0) + 1
                self.assertIsNone(self.vm._window_token)
                release.set()
                future.result(timeout=5)
            self.assertTrue(new_directory.is_dir())
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()
