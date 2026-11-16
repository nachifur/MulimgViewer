"""Budget admission, exact incremental decode and disk-backed large layouts."""
import copy
import gc
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import wait
from pathlib import Path
from unittest.mock import patch

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/mulimgviewer/src'))
from pipeline_executor import PipelineWorkers
from video_memory import PixelCache, LazyVideoImage
from video_decoder import DecoderBank, DecoderSession, av


class WorkerBudgetTests(unittest.TestCase):
    def test_short_decode_burst_remains_visible_after_workers_are_idle(self):
        group=PipelineWorkers(4,1)
        try:
            with group.lock:
                group._decode_started=group._decode_clock=0.
                group._decode_samples.clear();group._decode_completed.clear()
                group._record_decode_activity(now=1.)
                group.active[0]=4
                group._record_decode_activity(now=1.1)
                group.active[0]=0
                group._decode_completed.append(1.1)
            snapshot=group.activity_snapshot(now=10.)
            self.assertEqual(snapshot['decode_now'],0)
            self.assertEqual(snapshot['decode_peak'],4)
            self.assertAlmostEqual(snapshot['decode_average'],.04)
            self.assertEqual(snapshot['decode_completed'],1)
            expired=group.activity_snapshot(now=11.2)
            self.assertEqual(expired['decode_peak'],0)
            self.assertEqual(expired['decode_completed'],0)
            self.assertEqual(expired['decode_average'],0)
        finally:
            for stage in group.stages:stage.shutdown()

    def test_completed_decode_tasks_are_recorded_between_gui_samples(self):
        group=PipelineWorkers(1,1)
        try:
            group.stages[0].submit(lambda:None).result(timeout=2)
            snapshot=group.activity_snapshot()
            self.assertEqual(snapshot['decode_now'],0)
            self.assertEqual(snapshot['decode_completed'],1)
            self.assertEqual(snapshot['decode_peak'],1)
            self.assertGreater(snapshot['decode_average'],0)
        finally:
            for stage in group.stages:stage.shutdown()

    def test_decoder_history_resets_at_power_mode_boundary(self):
        group=PipelineWorkers(1,1)
        try:
            group.stages[0].submit(lambda:None).result(timeout=2)
            self.assertEqual(group.activity_snapshot()['decode_completed'],1)
            group.reset_activity()
            snapshot=group.activity_snapshot()
            self.assertEqual(snapshot['decode_peak'],0)
            self.assertEqual(snapshot['decode_average'],0)
            self.assertEqual(snapshot['decode_completed'],0)
        finally:
            for stage in group.stages:stage.shutdown()

    def test_live_quota_change_preserves_workers_and_running_tasks(self):
        group = PipelineWorkers(2, 1)
        entered, release, stitched = threading.Event(), threading.Event(), threading.Event()
        pool = group.pool
        try:
            raw = group.stages[0].submit(lambda: (entered.set(), release.wait(3)))
            self.assertTrue(entered.wait(1))
            group.configure(1, 2)
            composed = group.stages[1].submit(stitched.set)
            self.assertTrue(stitched.wait(1))
            self.assertIs(group.pool, pool)
            self.assertFalse(raw.done())
            self.assertFalse(raw.cancelled())
            self.assertEqual(composed.result(1), None)
        finally:
            release.set()
            for stage in group.stages:
                stage.shutdown()

    def test_lending_cannot_exceed_shared_byte_budget(self):
        group = PipelineWorkers(3, 1)
        group.configure(3, 1, memory_budget=100, costs=(10, 60))
        entered, release = threading.Event(), threading.Event()
        count = []
        def job():
            count.append(1)
            entered.set()
            release.wait(3)
        try:
            futures = [group.stages[1].submit(job) for _ in range(4)]
            self.assertTrue(entered.wait(1))
            self.assertEqual(len(count), 1)
            self.assertLessEqual(group.active_bytes, 100)
            self.assertEqual(group.active[1], 1)
        finally:
            release.set()
            for stage in group.stages:
                stage.shutdown()

    def test_spare_mode_budget_is_not_lost_when_static_reservations_are_smaller(self):
        group=PipelineWorkers(1,1)
        group.configure(1,1,memory_budget=100,costs=(10,10),total_budget=4)
        entered,release=threading.Event(),threading.Event()
        count=[]
        def task():
            count.append(1)
            if len(count)==4:entered.set()
            release.wait(3)
        try:
            tasks=[group.stages[0].submit(task) for _ in range(4)]
            self.assertTrue(entered.wait(1))
            self.assertEqual(sum(group.active),4)
            self.assertLessEqual(group.active_bytes,100)
        finally:
            release.set()
            for stage in group.stages:stage.shutdown()

    def test_global_cap_change_clamps_queued_native_cost_without_deadlock(self):
        group = PipelineWorkers(21, 1)
        release, entered = threading.Event(), threading.Event()
        try:
            group.configure(21, 1, total_budget=16)
            raw = group.stages[0].submit(lambda: (entered.set(), release.wait(3)), cpu_cost=21)
            self.assertTrue(entered.wait(1))
            self.assertEqual(raw.pipeline_cpu_cost, 15)
            self.assertEqual(group.stages[1].submit(lambda: 42).result(1), 42)
            self.assertLessEqual(sum(group.active), 16)
        finally:
            release.set()
            for stage in group.stages:
                stage.shutdown()

    def test_same_video_does_not_occupy_two_decode_permits(self):
        group = PipelineWorkers(2, 1)
        entered, release, other = threading.Event(), threading.Event(), threading.Event()
        try:
            first = group.stages[0].submit(lambda: (entered.set(), release.wait(3)), resource_key='a')
            self.assertTrue(entered.wait(1))
            second = group.stages[0].submit(lambda: None, resource_key='a')
            third = group.stages[0].submit(other.set, resource_key='b')
            self.assertTrue(other.wait(1))
            self.assertFalse(second.running())
            self.assertEqual(third.result(1), None)
        finally:
            release.set()
            for stage in group.stages:
                stage.shutdown()

    def test_idle_downgrade_retires_real_worker_threads(self):
        group=PipelineWorkers(3,1)
        try:
            jobs=[group.stages[0].submit(lambda:None) for _ in range(6)]
            for job in jobs:job.result(2)
            old=group.pool
            old_threads=list(old._threads)
            self.assertTrue(group.trim_idle())
            self.assertIsNot(group.pool,old)
            self.assertTrue(all(not thread.is_alive() for thread in old_threads))
        finally:
            for stage in group.stages:stage.shutdown()

    def test_native_codec_threads_are_weighted_and_queued_costs_follow_downgrade(self):
        group = PipelineWorkers(3,1)
        entered, release, stitched = threading.Event(),threading.Event(),threading.Event()
        try:
            first=group.stages[0].submit(lambda:(entered.set(),release.wait(3)),cpu_cost=3)
            self.assertTrue(entered.wait(1))
            second=group.stages[0].submit(lambda:None,cpu_cost=3)
            composition=group.stages[1].submit(stitched.set)
            self.assertTrue(stitched.wait(1))
            self.assertLessEqual(sum(group.active),4)
            group.configure(1,1)
            self.assertFalse(second.running())
            release.set()
            second.result(2)
            self.assertEqual(second.pipeline_cpu_cost,1)
        finally:
            release.set()
            for stage in group.stages:stage.shutdown()

    def test_cancelled_queued_futures_notify_wait_and_shutdown(self):
        group = PipelineWorkers(1, 1)
        release = threading.Event()
        try:
            first = group.stages[0].submit(lambda: release.wait(3))
            second = group.stages[0].submit(lambda: release.wait(3))
            cancelled = group.stages[0].submit(lambda: self.fail('Cancelled task executed'))
            self.assertTrue(cancelled.cancel())
            release.set()
            completed, pending = wait([first, second, cancelled], timeout=2)
            self.assertFalse(pending)
        finally:
            release.set()
            for stage in group.stages:
                stage.shutdown()


class PixelMemoryTests(unittest.TestCase):
    def test_byte_limit_eviction_downgrade_and_oversized_bypass(self):
        cache = PixelCache(800)
        a = Image.new('RGB', (10,10))
        self.assertTrue(cache.put('a', a))
        self.assertTrue(cache.put('b', a))
        self.assertTrue(cache.put('c', a))
        self.assertIsNone(cache.get('a'))
        self.assertLessEqual(cache.bytes, 800)
        self.assertFalse(cache.put('huge', Image.new('RGB', (20,20))))
        cache.configure(400)
        self.assertLessEqual(cache.bytes, 400)
        cache.prune(set())
        self.assertEqual(cache.bytes, 0)

    def test_previews_share_byte_cap_and_prune_with_original_owner(self):
        cache = PixelCache(800)
        preview = Image.new('RGB',(10,10))
        key = ('preview','frame.jpeg',(10,10),3)
        cache.put(key,preview,owner='frame.jpeg',priority=True)
        cache.put('page.png',preview,priority=True)
        self.assertFalse(cache.put('raw.jpeg',preview))
        cache.prune({'frame.jpeg'})
        self.assertIs(cache.get(key),preview)
        self.assertLessEqual(cache.bytes,400)
        cache.prune(set())
        self.assertEqual(cache.bytes,0)

    def test_initial_or_previous_gui_size_cannot_underestimate_100_4k_layout(self):
        from types import SimpleNamespace
        from test_video_cache import VideoManager
        vm=VideoManager.__new__(VideoManager)
        paths=['stream_%d.mp4'%i for i in range(100)]
        vm.shared_config=SimpleNamespace(real_video_path=paths,count_per_action=1)
        vm._video_dimensions={p:(3840,2160) for p in paths}
        params=[[10,10],[1,1],[1,1],None,None,None,[64,36]]
        vm._render_snapshot=(SimpleNamespace(layout_params=params),[],False)
        vm._window_token='new-layout'
        ui=SimpleNamespace(_video_display_key=(0,'old.png','old-layout'))
        vm._ui=lambda:ui
        for placeholder in ([-1,-1],[0,0],[800,600]):
            ui.img_size=placeholder
            output,inputs=vm._estimated_stitch_pixels()
            self.assertEqual(inputs,3840*2160)
            self.assertGreaterEqual(output,100*64*36)
            self.assertLess(output,10_000_000)

    def test_oversized_canvas_is_rejected_before_pixel_allocation(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
        from mulimgviewer.src.utils_img import ImgUtils
        tool = ImgUtils()
        tool.manager = SimpleNamespace(_video_memory_budget=128*1024**2)
        import numpy as np
        layouts = [[[1,1],[np.zeros((1,1)),np.zeros((1,1))],
                    [np.array([[3840]]),np.array([[2160]])],[3840,2160],None],
                   [[1,1],[0,0],[],[],None], [[10,10],[0,0],[],[],None]]
        with patch('mulimgviewer.src.utils_img.Image.new') as allocate:
            with self.assertRaisesRegex(MemoryError,'canvas'):
                tool.layout_2d(layouts,(0,0,0,0),[],lambda im:im,[],[False]*3,False,[None,None])
            allocate.assert_not_called()

    def test_100_4k_descriptors_materialize_one_tile_at_a_time(self):
        import psutil
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'4k.jpeg'
            image = Image.new('RGB', (3840,2160), (20,40,60))
            image.save(str(path), quality=90)
            image.close()
            gc.collect()
            process = psutil.Process()
            before = process.memory_info().rss
            descriptors = [LazyVideoImage(path) for _ in range(100)]
            self.assertTrue(all(copy.deepcopy(d) is d for d in descriptors))
            self.assertTrue(all(d.size==(3840,2160) for d in descriptors))
            tiles = [d.resize((64,36)) for d in descriptors]
            self.assertTrue(all(t.size==(64,36) for t in tiles))
            self.assertLess(process.memory_info().rss-before, 256*1024**2)
            self.assertTrue(path.exists())


@unittest.skipUnless(av and shutil.which('ffmpeg'), 'PyAV and FFmpeg required')
class DecoderAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = str(Path(cls.temp.name)/'sample.mp4')
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
            'testsrc2=size=96x64:rate=10:duration=8','-c:v','libx264','-g','12','-bf','2','-y',cls.path],check=True,capture_output=True)
        with av.open(cls.path) as container:
            cls.expected = [frame.to_image().tobytes() for frame in container.decode(video=0)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_forward_resume_does_not_redecode_prefix_and_reverse_is_exact(self):
        session = DecoderSession(self.path,10.,False,96*64)
        try:
            frames = list(session.frames(20,24,1,lambda:False))
            self.assertEqual([img.tobytes() for _,img in frames],self.expected[20:25])
            decoded = session.decoded
            frames = list(session.frames(25,29,1,lambda:False))
            self.assertEqual(session.decoded-decoded,5)
            self.assertEqual(session.opens,1)
            self.assertEqual([img.tobytes() for _,img in frames],self.expected[25:30])
            frames = list(session.frames(5,8,1,lambda:False))
            self.assertEqual([img.tobytes() for _,img in frames],self.expected[5:9])
        finally:
            session.close()

    def test_buffered_forward_reverse_skip_and_decoder_close_preserve_pixels(self):
        session=DecoderSession(self.path,10.,False,96*64)
        try:
            frames=list(session.frames(20,29,3,lambda:False,buffer_images=True))
            self.assertEqual([i for i,_ in frames],[20,23,26,29])
            self.assertEqual([im.convert('RGB').tobytes() for _,im in frames],
                             [self.expected[i] for i in (20,23,26,29)])
            saved=frames[0][1]
            backward=list(session.frames(5,8,1,lambda:False,buffer_images=True))
            self.assertEqual([im.convert('RGB').tobytes() for _,im in backward],self.expected[5:9])
        finally:session.close()
        gc.collect()
        self.assertEqual(saved.convert('RGB').tobytes(),self.expected[20])

    def test_skip_indices_and_fast_seek_are_exact(self):
        session = DecoderSession(self.path,10.,True,96*64)
        try:
            frames = list(session.frames(42,54,3,lambda:False))
            self.assertEqual([i for i,_ in frames],[42,45,48,51,54])
            self.assertEqual([img.tobytes() for _,img in frames],[self.expected[i] for i in (42,45,48,51,54)])
        finally:
            session.close()

    def test_vfr_forward_reverse_uses_ordinals_instead_of_nominal_fps(self):
        path = str(Path(self.temp.name)/'vfr.mp4')
        subprocess.run(['ffmpeg','-v','error','-i',self.path,'-vf',
            'setpts=if(lt(N\\,40)\\,N\\,40+(N-40)*2)/(10*TB)',
            '-fps_mode','vfr','-c:v','libx264','-g','12','-y',path],check=True,capture_output=True)
        with av.open(path) as container:
            reference = [frame.to_image().tobytes() for frame in container.decode(video=0)]
        session = DecoderSession(path,10.,False,96*64)
        try:
            forward=list(session.frames(45,49,1,lambda:False))
            self.assertEqual([im.tobytes() for _,im in forward],reference[45:50])
            backward=list(session.frames(12,15,1,lambda:False))
            self.assertEqual([im.tobytes() for _,im in backward],reference[12:16])
        finally:
            session.close()

    def test_rotation_matches_ffmpeg_autorotation(self):
        import io
        import numpy as np
        path=str(Path(self.temp.name)/'rotated.mp4')
        subprocess.run(['ffmpeg','-v','error','-i',self.path,'-c','copy',
            '-metadata:s:v:0','rotate=90','-y',path],check=True,capture_output=True)
        output=subprocess.run(['ffmpeg','-v','error','-i',path,'-frames:v','1',
            '-f','image2pipe','-c:v','png','pipe:1'],check=True,capture_output=True).stdout
        reference=Image.open(io.BytesIO(output)).convert('RGB')
        session=DecoderSession(path,10.,False,96*64)
        try:
            image=list(session.frames(0,0,1,lambda:False,buffer_images=True))[0][1].convert('RGB')
            self.assertEqual(image.size,reference.size)
            self.assertLess(np.abs(np.asarray(image,dtype=float)-np.asarray(reference,dtype=float)).mean(),2.)
        finally:
            session.close()

    def test_native_frame_threading_preserves_display_order(self):
        session=DecoderSession(self.path,10.,True,96*64,threads=3)
        try:
            frames=list(session.frames(25,39,1,lambda:False))
            self.assertEqual([im.tobytes() for _,im in frames],self.expected[25:40])
        finally:
            session.close()

    def test_cyclic_scan_larger_than_idle_cache_keeps_resident_decoders(self):
        bank=DecoderBank(16*1024**2)
        paths=[]
        for index in range(4):
            path=str(Path(self.temp.name)/('linked_%d.mp4'%index))
            if not Path(path).exists():
                os.link(self.path,path)
            paths.append(path)
        try:
            for path in paths:
                with bank.lease(path,10.,False,96*64) as session:
                    list(session.frames(0,0,1,lambda:False))
            before={p:s.opens for p,s in bank.sessions.items()}
            for path in paths:
                with bank.lease(path,10.,False,96*64) as session:
                    list(session.frames(1,1,1,lambda:False))
            retained=sum(s.opens==before[p] for p,s in bank.sessions.items())
            self.assertGreaterEqual(retained,2)
            idle=sum(s.bytes_hint for s in bank.sessions.values() if s.container is not None and s.users==0)
            self.assertLessEqual(idle,bank.limit)
        finally:
            bank.close()

    def test_policy_change_does_not_wait_for_codec_close_lock(self):
        bank=DecoderBank(100)
        entered,release,updated=threading.Event(),threading.Event(),threading.Event()
        def hold():
            with bank.lock:
                entered.set()
                release.wait(2)
        thread=threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            update=threading.Thread(target=lambda:(bank.configure(10),updated.set()))
            update.start()
            self.assertTrue(updated.wait(.5))
            update.join(1)
        finally:
            release.set()
            thread.join(2)
            bank.close()

    def test_context_eviction_keeps_exact_keyframe_index(self):
        bank = DecoderBank(1)
        with bank.lease(self.path,10.,False,96*64) as session:
            list(session.frames(35,45,1,lambda:False))
        self.assertIsNone(session.container)
        before = session.decoded
        with bank.lease(self.path,10.,False,96*64) as same:
            frames = list(same.frames(46,49,1,lambda:False))
            self.assertIs(same,session)
            self.assertEqual([img.tobytes() for _,img in frames],self.expected[46:50])
            self.assertLess(session.decoded-before,25)
        bank.close()


if __name__=='__main__':
    unittest.main()
