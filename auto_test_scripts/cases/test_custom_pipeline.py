"""Algorithm-stage concurrency, correctness, invalidation and bounded disk use."""
import sys
import json
import tempfile
import unittest
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, CancelledError
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from PIL import Image
from mulimgviewer.src.custom_pipeline import CustomPipeline, WorkBudget
from mulimgviewer.src.custom_func.runtime import AlgorithmSession
from mulimgviewer.src.utils_img import ImgManager


SOURCE='''
import time
calls = 0
def main(images, path, names=None):
    global calls
    calls += 1
    time.sleep(.02)
    return [image.copy() for image in images]
'''


class SoftMemoryBudgetTests(unittest.TestCase):
    def test_measure_only_layout_does_not_allocate_or_process_pixels(self):
        import numpy as np
        from mulimgviewer.src.utils_img import ImgUtils
        layout=[[[1,1],[np.zeros((1,1)),np.zeros((1,1))],
                 [np.array([[20]]),np.array([[12]])],[20,12],None],
                [[1,2],[3,0],[],[],None],[[2,1],[0,4],[],[],None]]
        process=Mock(side_effect=AssertionError('Unexpected pixel processing'))
        with patch('PIL.Image.new',side_effect=AssertionError('Unexpected canvas allocation')):
            size,_,_=ImgUtils().layout_2d(layout,None,[],process,process,
                [False]*3,False,[process,process],measure_only=True)
        self.assertEqual(size,(43,28))

    def test_capacity_callback_does_not_block_a_safe_single_oversized_task(self):
        budget=WorkBudget();budget.configure(4,100,capacity=lambda:(4,100))
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=10000):
            with budget.acquire(200):self.assertEqual(budget.bytes,200)
        self.assertEqual((budget.active,budget.bytes),(0,0))

    def test_standalone_budget_allows_one_safe_oversized_task(self):
        budget=WorkBudget();budget.configure(4,100)
        entered=threading.Event()
        def second():
            with budget.acquire(20):entered.set()
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=10000):
            with ThreadPoolExecutor(1) as pool:
                with budget.acquire(200):
                    future=pool.submit(second)
                    self.assertFalse(entered.wait(.05))
                    self.assertEqual(budget.bytes,200)
                future.result(timeout=2)
        self.assertTrue(entered.is_set())
        self.assertEqual((budget.active,budget.bytes),(0,0))

    def test_oversized_shared_task_drains_decoders_and_keeps_real_charge(self):
        from mulimgviewer.src.pipeline_executor import PipelineWorkers
        group=PipelineWorkers(2,1);group.configure(2,1,100,(30,30))
        budget=WorkBudget();budget.configure(3,100,group.downstream_capacity,group.reserve_downstream)
        raw_started,raw_release=threading.Event(),threading.Event()
        big_started,big_release=threading.Event(),threading.Event()
        later=threading.Event()
        def raw():raw_started.set();raw_release.wait(3)
        def big():
            with budget.acquire(200):big_started.set();big_release.wait(3)
        try:
            running=group.stages[0].submit(raw,resource_key='raw')
            self.assertTrue(raw_started.wait(2))
            with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=10000), ThreadPoolExecutor(1) as pool:
                future=pool.submit(big)
                self.assertFalse(big_started.wait(.05))
                raw_release.set();running.result(timeout=2)
                self.assertTrue(big_started.wait(2))
                self.assertEqual(group.memory_snapshot()[0],200)
                queued=group.stages[0].submit(later.set,resource_key='later')
                self.assertFalse(later.wait(.05))
                big_release.set();future.result(timeout=2);queued.result(timeout=2)
            self.assertTrue(later.is_set())
            self.assertEqual(group.memory_snapshot()[0],0)
        finally:
            raw_release.set();big_release.set()
            for stage in group.stages:stage.shutdown()

    def test_system_headroom_still_protects_an_oversized_task(self):
        budget=WorkBudget();budget.configure(4,100)
        for available in (150,None):
            with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=available), \
                    self.assertRaisesRegex(MemoryError,'system memory'):
                with budget.acquire(200):self.fail('Unsafe task entered')
            self.assertEqual((budget.active,budget.bytes,budget.waiting),(0,0,[]))

    def test_large_regular_task_checks_live_physical_memory(self):
        budget=WorkBudget();budget.configure(4,128*1024**2)
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=16*1024**2), \
                self.assertRaisesRegex(MemoryError,'system memory'):
            with budget.acquire(32*1024**2):self.fail('Unsafe task entered')


class ProcessingStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'input.png';Image.new('RGB',(20,12),'red').save(self.source)
        self.stage=CustomPipeline(self.root/'cache')
        self.stage.configure(4,512*1024**2)
        self.stage.set_window('image','sources',(0,2),0)
    def tearDown(self):
        self.stage.close();self.stage.pool.shutdown(wait=True)
        self.stage.cleanup_future.result(timeout=5);self.temp.cleanup()
    def manager(self,count=10,extra=None,source=SOURCE):
        manager=ImgManager();manager.layout_params=[None]*41+[1]
        manager.path_list=[str(self.root)]
        manager.layout_params[32]=False;manager.layout_params[37]=0
        manager.layout_params[38]=True;manager.layout_params[39]='3,4'
        spec=dict(device='cpu',cacheable=True);spec.update(extra or {})
        manager._custom_algorithm_registry=tuple((str(i),f'/plugin/{i}/main.py',source,json.dumps(spec)) for i in range(count))
        manager._custom_algorithm_session=AlgorithmSession(manager._custom_algorithm_registry)
        return manager
    def prepare(self,manager,batch=0):
        return self.stage.prepare(manager,[str(self.source)],batch,'image','sources')

    def test_ten_algorithms_run_in_parallel_and_results_are_reused_by_layout(self):
        manager=self.manager()
        with self.prepare(manager) as results:
            self.assertEqual(len(results),10)
            for paths in results.values():
                with Image.open(paths[0]) as image:self.assertEqual(image.getpixel((0,0)),(255,0,0))
        self.assertGreaterEqual(self.stage.peak_active,2)
        self.assertLessEqual(self.stage.peak_active,4)
        manager.layout_params[32]=True;manager.layout_params[38]=False;manager.layout_params[37]=4
        with self.prepare(manager) as results:self.assertEqual(set(results),{4})
        self.assertEqual(manager._custom_algorithm_session.namespaces[4]['calls'],1)
        self.assertEqual(self.stage.snapshot()['misses'],10)
        self.assertGreater(self.stage.snapshot()['hits'],0)

    def test_preview_reuses_exact_pixels_without_redecoding_processed_png(self):
        from mulimgviewer.src.video_memory import PixelCache,LazyVideoImage
        manager=self.manager(1)
        manager.layout_params[4]=[.5,.5];manager.layout_params[6]=[20,12]
        cache=self.stage.pixel_cache=PixelCache(4096)
        Image.effect_noise((20,12),80).convert('RGB').save(self.source)
        with self.prepare(manager) as results:
            path=results[0][0]
            with Image.open(path) as native:
                self.assertEqual(native.size,(20,12))
                expected=native.resize((10,6),Image.BICUBIC).tobytes()
            with patch('builtins.open',side_effect=AssertionError('Preview must avoid disk decoding')):
                descriptor=LazyVideoImage(path,cache.get)
                self.assertEqual(descriptor.resize((10,6),Image.BICUBIC).tobytes(),expected)
            cache.prune({str(self.source)})
            self.assertGreater(cache.bytes,0)
            self.assertLessEqual(cache.bytes,cache.limit)
            cache.prune(set());self.assertEqual(cache.bytes,0)

    def test_waiting_for_same_algorithm_does_not_hold_work_permits(self):
        import copy,time
        from contextlib import contextmanager
        from mulimgviewer.src.custom_func import main as functions
        manager=self.manager(2)
        manager.layout_params[32]=True;manager.layout_params[38]=False
        other=copy.copy(manager);other.layout_params=list(manager.layout_params);other.layout_params[37]=1
        self.stage.configure(2,512*1024**2)
        entered=threading.Event();waiting=threading.Event();release=threading.Event()
        context=functions.algorithm_context;calls=[0];lock=threading.Lock()
        @contextmanager
        def observe(index):
            if index==0:
                with lock:
                    calls[0]+=1
                    if calls[0]==2:waiting.set()
            with context(index):yield
        def run(images,output,name_list=None,algorithm_type=0):
            if algorithm_type==0:
                entered.set()
                if not release.wait(4):raise TimeoutError('Test algorithm was not released')
            return [image.copy() for image in images]
        def read(m,batch):
            with self.prepare(m,batch) as result:return result
        with patch.object(functions,'algorithm_context',observe),patch.object(functions,'main',run),ThreadPoolExecutor(3) as pool:
            first=pool.submit(read,manager,0)
            try:
                self.assertTrue(entered.wait(2))
                second=pool.submit(read,manager,1)
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    with self.stage.pool.lock:
                        if self.stage.pool.queue:break
                    time.sleep(.001)
                self.assertFalse(waiting.is_set())
                self.assertEqual(self.stage.pool.active,1)
                self.assertEqual(self.stage.budget.active,1)
                unrelated=pool.submit(read,other,2)
                self.assertTrue(unrelated.result(timeout=2))
            finally:release.set()
            first.result(timeout=2);second.result(timeout=2)

    def test_image_parent_and_children_share_a_single_worker_without_deadlock(self):
        from mulimgviewer.src.custom_workers import ImageWorkers
        self.stage.pool.shutdown(wait=True)
        self.stage.pool=self.stage.image_pool=ImageWorkers(1)
        manager=self.manager(2,extra=dict(api_version=2,processing_mode='image',max_concurrency=1),
            source='def process_image(image, *, context): return image.copy()')
        self.assertIs(self.stage.pool,self.stage.image_pool)
        with self.prepare(manager) as result:
            self.assertEqual(set(result),{0,1})
            self.assertTrue(all(Path(paths[0]).is_file() for paths in result.values()))
        self.assertEqual(self.stage.budget.active,0)

    def test_dynamic_capacity_enforces_shared_cpu_and_decoder_memory(self):
        from mulimgviewer.src.pipeline_executor import PipelineWorkers
        group=PipelineWorkers(3,1)
        try:
            group.configure(3,1,1000,(100,200),total_budget=4)
            with group.lock:
                group.active[:]=[1,0]
                group.coordinators=3
                group.stage_bytes[:]=[100,0]
            self.assertEqual(group.downstream_capacity(),(3,900))
            group.configure(1,1,700,(100,200),total_budget=2)
            self.assertEqual(group.downstream_capacity(),(1,600))
            budget=WorkBudget();budget.configure(4,1000,group.downstream_capacity)
            with budget.acquire(400):self.assertEqual(budget.active,1)
        finally:group.pool.shutdown(wait=True)

    def test_cache_names_and_manifest_identify_algorithm_page_and_source(self):
        manager=self.manager(1)
        with self.prepare(manager) as results:
            output=Path(results[0][0])
            self.assertEqual(output.name,'input.png')
            visible=self.stage.visible.root/'0'/'processed'/'frames'/self.root.name
            self.assertTrue((visible/'input.png').is_file())
            info=json.loads((output.parents[2]/'cache_info.json').read_text(encoding='utf-8'))
            self.assertEqual(info['algorithm'],'0')
            self.assertEqual(info['page'],1)
            self.assertEqual(info['inputs'],[str(self.source)])
            self.assertEqual(info['algorithm_path'],'/plugin/0/main.py')
            self.assertFalse(list((self.stage.visible.root/'0'/'processed').glob('page_*')))

    def test_processed_source_descriptor_traces_video_and_algorithm(self):
        manager=self.manager(1)
        manager.video_mode=True
        manager._cache_original_paths=['meeting.mp4']
        manager._cache_input_mode='Image File List'
        manager.video_fps_list=[29.97];manager.video_num_list=[1200];manager.skip=2
        with self.prepare(manager):
            folder=self.stage.visible.root/'0'/'processed'
            info=json.loads((folder/'json'/'meeting.json').read_text(encoding='utf-8'))
            self.assertEqual(info['source'],1)
            self.assertEqual(info['media'],'video')
            self.assertEqual(info['path'],str(Path('meeting.mp4').absolute()))
            self.assertEqual(info['fps'],29.97)
            self.assertEqual(info['frames'],1200)
            self.assertEqual(info['step'],3)
            self.assertEqual(info['input_mode'],'Image File List')
            self.assertEqual(info['algorithm'],'0')
            self.assertEqual(info['algorithm_path'],str(Path('/plugin/0/main.py').absolute()))
            self.assertEqual(info['raw_frames_path'],str(self.source.parent))
            self.assertEqual(info['processed_frames_path'],str(folder/'frames'/'meeting'))
            self.assertTrue(info['source_catalog'].endswith(str(Path('sources/json/video/meeting.json'))))
            self.assertNotIn('outputs',info)  # Not a growing list of video frames.

    def test_source_descriptor_is_written_once_and_follows_shared_frame_cleanup(self):
        manager=self.manager(1)
        import os
        replace=os.replace;writes=[]
        def record(source,target):
            if Path(target).name==self.root.name+'.json':writes.append(Path(target))
            return replace(source,target)
        with patch('os.replace',side_effect=record):
            with self.prepare(manager,0):pass
            manifest=self.stage.visible.root/'0'/'processed'/'json'/(self.root.name+'.json')
            with self.prepare(manager,1):pass
            self.assertEqual(writes,[manifest])
            self.assertEqual(json.loads(manifest.read_text(encoding='utf-8'))['media'],'image')
            self.stage.set_window('image','sources',(1,2),1);self.stage._prune()
            self.assertTrue(manifest.exists())
            self.stage.set_window('image','sources',(2,3),2);self.stage._prune()
            self.assertFalse(manifest.exists())
            self.assertFalse(self.stage.visible.metadata)
            self.assertFalse(self.stage.visible.file_users)

    def test_source_descriptor_updates_with_algorithm_cache_version(self):
        with self.prepare(self.manager(1)):pass
        manifest=self.stage.visible.root/'0'/'processed'/'json'/(self.root.name+'.json')
        self.assertEqual(json.loads(manifest.read_text(encoding='utf-8'))['cache_version'],'1')
        with self.prepare(self.manager(1,dict(cache_version='2'))):pass
        self.assertEqual(json.loads(manifest.read_text(encoding='utf-8'))['cache_version'],'2')
        self.assertFalse(list(manifest.parent.glob('__tmp_*')))

    def test_disk_composition_estimate_uses_preview_canvas_and_one_source_tile(self):
        manager=self.manager(3)
        params=manager.layout_params
        params[0:3]=[[10,10],[1,1],[1,1]]
        params[3]=[0]*8;params[4]=[1,1];params[6]=[80,45]
        params[17]=[False,False]+[False]*6+['12']
        params[39]='2,2'
        class Header:
            width=3840;height=2160
            size=(3840,2160)
            def __enter__(self):return self
            def __exit__(self,*args):pass
        paths=[str(self.source)]*100
        with patch('PIL.Image.open',return_value=Header()) as opened:
            preview=self.stage.composition_bytes(paths,{0:paths,1:paths,2:paths},manager)
            self.assertEqual(opened.call_count,1)
            self.assertLess(preview,256*1024**2)
            params[6]=[-1,-1]
            native=self.stage.composition_bytes(paths,{0:paths,1:paths,2:paths},manager)
            self.assertGreater(native,preview)
            self.stage.configure(4,256*1024**2)
            with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=128*1024**2), self.assertRaises(MemoryError):
                with self.stage.budget.acquire(native):pass

    def test_transient_windows_directory_sharing_failure_is_retried(self):
        import os
        replace=os.replace;failures=[]
        def transient(source,target):
            if Path(source).name.startswith('tmp_') and not failures:
                failures.append(1)
                error=PermissionError('Temporary sharing violation');error.winerror=32
                raise error
            return replace(source,target)
        with patch('os.replace',side_effect=transient):
            with self.prepare(self.manager(1)) as result:self.assertTrue(Path(result[0][0]).is_file())
        self.assertEqual(failures,[1])
        self.assertFalse(list(self.stage.directory.glob('tmp_*')))

    def test_inputs_and_algorithm_version_invalidate_results(self):
        manager=self.manager(1)
        with self.prepare(manager) as result:first=result[0][0]
        Image.new('RGB',(21,12),'blue').save(self.source)
        with self.prepare(manager) as result:second=result[0][0]
        self.assertNotEqual(first,second)
        replacement=self.manager(1,dict(cache_version='2'))
        with self.prepare(replacement) as result:self.assertNotEqual(second,result[0][0])

    def test_repeated_inputs_share_public_source_path_until_last_page_is_cleaned(self):
        manager=self.manager(1)
        with self.prepare(manager,0) as result:first=result[0][0]
        with self.prepare(manager,1) as result:second=result[0][0]
        self.assertNotEqual(first,second)
        path=self.stage.visible.root/'0'/'processed'/'frames'/self.root.name/'input.png'
        self.assertTrue(path.is_file())
        self.stage.set_window('image','sources',(1,2),1);self.stage._prune()
        self.assertTrue(path.is_file())
        self.stage.set_window('image','sources',(2,3),2);self.stage._prune()
        self.assertFalse(path.exists())

    def test_window_cleanup_waits_for_active_readers(self):
        manager=self.manager(1)
        with self.prepare(manager) as results:
            path=Path(results[0][0])
            self.stage.set_window('image','sources',(10,12),10);self.stage._prune()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists());self.assertEqual(len(self.stage.entries),0)

    def test_identity_references_original_without_loading_module_or_writing_png(self):
        manager=self.manager(1,dict(identity=True),source='raise RuntimeError("must not execute")')
        with self.prepare(manager) as result:self.assertEqual(result[0],(str(self.source),))
        self.assertFalse(list(self.stage.directory.glob('result_*')))
        self.assertFalse(manager._custom_algorithm_session.namespaces)

    def test_duplicate_requests_share_one_processing_task(self):
        manager=self.manager(1)
        def read(_):
            with self.prepare(manager) as result:return result[0]
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(read,range(4)))
        self.assertTrue(all(value==results[0] for value in results))
        self.assertEqual(manager._custom_algorithm_session.namespaces[0]['calls'],1)

    def test_actual_disk_and_memory_failures_do_not_publish_partial_results(self):
        manager=self.manager(1)
        import errno
        with patch.object(Image.Image,'save',side_effect=OSError(errno.ENOSPC,'No space left on device')),self.assertRaises(OSError):
            with self.prepare(manager):pass
        self.assertFalse(list(self.stage.directory.glob('tmp_*')))
        self.assertFalse(list(self.stage.directory.glob('result_*')))
        self.stage.configure(4,1)
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=0), self.assertRaises(MemoryError):
            with self.prepare(manager):pass

    def test_unknown_device_defaults_to_serialized_calls(self):
        manager=self.manager(2,dict(device='exclusive'))
        with self.prepare(manager):pass
        self.assertEqual(self.stage.snapshot()['misses'],2)

    def test_invalid_return_shape_reports_interface_error(self):
        manager=self.manager(1,source='def main(a,b,c): return []')
        with self.assertRaisesRegex(ValueError,'one Pillow image per input'):
            with self.prepare(manager):pass

    def test_deleted_intermediate_is_regenerated(self):
        manager=self.manager(1)
        with self.prepare(manager) as results:path=Path(results[0][0])
        path.unlink()
        with self.prepare(manager) as results:self.assertTrue(Path(results[0][0]).exists())
        self.assertEqual(manager._custom_algorithm_session.namespaces[0]['calls'],2)

    def test_copy_fallback_bytes_are_measured_without_imposing_a_quota(self):
        manager=self.manager(1)
        with patch('os.link',side_effect=OSError('Hard links unavailable')):
            with self.prepare(manager):pass
        entry=next(iter(self.stage.entries.values()))
        private=sum(p.stat().st_size for p in entry['directory'].rglob('*') if p.is_file())
        public=sum(p.stat().st_size for p in self.stage.visible.root.rglob('*') if p.is_file())
        self.assertEqual(entry['bytes'],private+public)
        self.assertEqual(entry.get('reserved',0),0)

    def test_large_valid_window_is_not_rejected_or_evicted_by_byte_count(self):
        manager=self.manager(1)
        with patch('shutil.disk_usage') as disk_usage:
            with self.prepare(manager) as result:path=Path(result[0][0])
            entry=next(iter(self.stage.entries.values()))
            entry['bytes']=8*1024**3
            self.stage._prune()
            self.assertTrue(path.exists())
            self.assertEqual(len(self.stage.entries),1)
            disk_usage.assert_not_called()

    def test_new_version_retires_old_page_but_preserves_active_reader(self):
        old=self.manager(1)
        with self.prepare(old) as result:
            old_path=Path(result[0][0])
            new=self.manager(1,source=SOURCE+'\n# new version\n')
            with self.prepare(new) as updated:new_path=Path(updated[0][0])
            self.assertNotEqual(old_path,new_path)
            self.assertTrue(old_path.exists())
        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.exists())
        self.assertEqual(len(self.stage.entries),1)

    def test_window_bounds_control_retention_when_shrinking_and_reversing(self):
        manager=self.manager(1)
        paths={}
        self.stage.set_window('image','sources',(0,4),2)
        for page in range(5):
            with self.prepare(manager,page) as result:paths[page]=Path(result[0][0])
        self.stage.set_window('image','sources',(1,3),2);self.stage._prune()
        self.assertEqual({p for p,path in paths.items() if path.exists()},{1,2,3})
        self.stage.set_window('image','sources',(0,2),1);self.stage._prune()
        self.assertEqual({p for p,path in paths.items() if path.exists()},{1,2})
        with self.prepare(manager,0) as result:self.assertTrue(Path(result[0][0]).exists())
        self.assertEqual(len(self.stage.entries),3)

    def test_failed_directory_deletion_is_retried_on_next_cleanup(self):
        import shutil
        path=self.stage.directory/'result_retired';path.mkdir(parents=True)
        (path/'frame.png').write_bytes(b'old')
        with patch.object(shutil,'rmtree'):
            self.stage._remove(path)
        self.assertTrue(path.exists())
        self.assertIn(path,self.stage._pending_deletions)
        self.stage._prune()
        self.assertFalse(path.exists())
        self.assertFalse(self.stage._pending_deletions)

    def test_close_reclaims_work_tree_after_last_reader_releases(self):
        manager=self.manager(1)
        with self.prepare(manager) as result:
            path=Path(result[0][0])
            self.stage.close()
            self.assertTrue(path.exists())
            self.assertFalse(self.stage.cleanup_future.done())
        self.stage.cleanup_future.result(timeout=5)
        self.assertFalse(path.exists())
        self.assertFalse(self.stage.entries)
        self.assertFalse(list(self.stage.directory.glob('result_*')))

    def test_normal_close_removes_empty_dot_work_directory(self):
        self.stage.close();self.stage.cleanup_future.result(timeout=5)
        self.stage=CustomPipeline(self.root/'.work'/'processed',public_root=self.root/'algorithms')
        self.stage.configure(2,512*1024**2)
        self.stage.set_window('image','sources',(0,2),0)
        with self.prepare(self.manager(1)):pass
        self.assertTrue((self.root/'.work').exists())
        self.stage.close();self.stage.cleanup_future.result(timeout=5)
        self.assertFalse((self.root/'.work').exists())

    def test_public_file_occupancy_does_not_orphan_private_results(self):
        with self.prepare(self.manager(1)) as result:path=Path(result[0][0])
        self.stage.set_window('image','sources',(10,12),10)
        with patch.object(self.stage.visible,'remove',side_effect=PermissionError('File in use')):
            self.stage._prune()
        self.assertTrue(path.exists())
        self.assertTrue(self.stage._retired_entries)
        self.stage._prune()
        self.assertFalse(path.exists())
        self.assertFalse(self.stage._retired_entries)

    def test_late_algorithm_callback_cannot_pin_a_mosaic_after_plan_exit(self):
        from mulimgviewer.src.mosaic_pipeline import MosaicStage
        self.stage.mosaic_stage=MosaicStage(self.stage)
        def initialize(plan,stage,*args):
            plan.cache=stage.cache;plan.lock=threading.RLock();plan.closed=False
            plan.entries=[{'pins':1}];plan.futures={};plan.cancelled=lambda:False
            plan._request=Mock()
        with patch('mulimgviewer.src.mosaic_pipeline.MosaicPlan.__init__',new=initialize):
            with self.stage.mosaic_stage.plan(None,[],0,'image','sources',[],lambda:False) as plan:
                self.assertFalse(plan.closed)
        self.assertTrue(plan.closed)
        self.assertEqual(plan.entries[0]['pins'],0)
        plan.ready(0,('late.png',))
        plan._request.assert_not_called()

    def test_mosaic_ready_callback_cancellation_is_delivered_to_waiter(self):
        from mulimgviewer.src.mosaic_pipeline import MosaicPlan
        plan=object.__new__(MosaicPlan)
        plan.lock=threading.RLock();plan.closed=False;plan.futures={}
        plan.cancelled=lambda:False;plan.cache=Mock(closed=False)
        plan._request=Mock(side_effect=CancelledError())
        plan.ready(0,('input.png',))
        with self.assertRaises(CancelledError):plan.futures[0].result()

    def test_missing_parent_after_initialization_is_recreated(self):
        self.stage._initialize()
        self.stage.directory.rmdir()
        manager=self.manager(1)
        with self.prepare(manager) as results:
            self.assertTrue(Path(results[0][0]).is_file())
        self.assertTrue(self.stage.directory.is_dir())

    def test_delayed_cleanup_cannot_delete_new_result_for_same_key(self):
        manager=self.manager(1)
        with self.prepare(manager) as results:old=Path(results[0][0]).parents[2]
        entered=threading.Event();release=threading.Event()
        original=self.stage._remove
        def delayed(path):
            if Path(path)==old:
                entered.set()
                if not release.wait(3):raise TimeoutError('Cleanup was not released')
            original(path)
        with patch.object(self.stage,'_remove',side_effect=delayed),ThreadPoolExecutor(1) as pool:
            self.stage.set_window('image','sources',(10,12),10)
            future=pool.submit(self.stage._prune)
            try:
                self.assertTrue(entered.wait(2))
                self.stage.set_window('image','sources',(0,2),0)
                with self.prepare(manager) as results:
                    new=Path(results[0][0])
                    self.assertNotEqual(new.parents[2],old)
                    release.set();future.result(timeout=2)
                    self.assertTrue(new.is_file())
                    self.assertFalse(old.exists())
            finally:release.set()

    def test_ordered_algorithm_resets_on_seek_and_rejects_prefetch(self):
        source='''
count = 0
resets = []
def reset(context):
    global count
    count = 0
    resets.append(context['batch'])
def main(images, path, names):
    global count
    count += 1
    return images
'''
        manager=self.manager(1,dict(ordered=True),source)
        for batch in (0,1,7):
            self.stage.set_window('image','sources',(max(0,batch-1),batch+1),batch)
            with self.prepare(manager,batch):pass
        namespace=manager._custom_algorithm_session.namespaces[0]
        self.assertEqual(namespace['resets'],[0,7])
        self.assertEqual(namespace['count'],1)
        with self.assertRaises(CancelledError):
            with self.prepare(manager,8):pass

    def test_noncacheable_results_are_not_reused_after_readers_finish(self):
        manager=self.manager(1,dict(cacheable=False))
        for _ in range(2):
            with self.prepare(manager):pass
        self.assertEqual(manager._custom_algorithm_session.namespaces[0]['calls'],2)
        self.assertFalse(self.stage.entries)

    def test_downgrade_blocks_new_heavy_work_until_running_tasks_drain(self):
        budget=WorkBudget();budget.configure(2,100)
        started=threading.Event()
        with ThreadPoolExecutor(1) as pool:
            def work():
                with budget.acquire(20):started.set()
            with budget.acquire(20):
                budget.configure(1,50)
                future=pool.submit(work)
                self.assertFalse(started.wait(.05))
            future.result(timeout=2)
        self.assertTrue(started.is_set());self.assertEqual(budget.active,0)

    def test_device_model_eviction_calls_release_hook(self):
        import builtins
        builtins._mulimg_test_release=[]
        source='''
import builtins
def main(images, path, names):return images
def release_resources():builtins._mulimg_test_release.append(True)
'''
        try:
            manager=self.manager(2,dict(device='test:device'),source)
            with self.prepare(manager):pass
            self.assertEqual(len(manager._custom_algorithm_session.namespaces),1)
            self.assertEqual(builtins._mulimg_test_release,[True])
        finally:del builtins._mulimg_test_release


if __name__=='__main__':unittest.main()
