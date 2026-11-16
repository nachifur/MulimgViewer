"""V2 image kernels, shared GPU batch contexts and bounded parallel scheduling."""
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from PIL import Image, ImageFilter
from mulimgviewer.src.custom_func import runtime
from mulimgviewer.src.custom_func.main import main,get_available_algorithms
from mulimgviewer.src.custom_func.contract import specification
import test_custom_pipeline as fixtures


class KernelPipelineTests(unittest.TestCase):
    setUp = fixtures.ProcessingStageTests.setUp
    tearDown = fixtures.ProcessingStageTests.tearDown
    def manager(self, count=1, extra=None, source=None):
        spec=dict(api_version=2,processing_mode='image',max_concurrency=4)
        spec.update(extra or {})
        return fixtures.ProcessingStageTests.manager(self,count,spec,source or KERNEL)

    def test_parallel_images_preserve_order_names_and_release_memory(self):
        paths=[]
        for i in range(8):
            path=self.root/f'{i}.png'
            Image.new('RGB',(20,12),(i,0,0)).save(path)
            paths.append(str(path))
        manager=self.manager()
        # Make concurrency deterministic rather than measuring wall-clock speed.
        with self.stage.prepare(manager,paths,0,'image','sources') as result:
            for i,path in enumerate(result[0]):
                with Image.open(path) as image:self.assertEqual(image.getpixel((0,0)),(i,0,0))
            namespace=manager._custom_algorithm_session.namespaces[0]
            self.assertEqual(namespace['initialized'],1)
            self.assertGreaterEqual(namespace['peak'],2)
            self.assertLessEqual(namespace['peak'],4)
            self.assertEqual(self.stage.budget.bytes,0)
        with self.stage.prepare(manager,paths,0,'image','sources'):
            self.assertEqual(namespace['calls'],8)

    def test_image_tasks_admit_one_image_not_the_entire_layout(self):
        # Each image fits; the whole batch deliberately exceeds this budget.
        self.stage.configure(2,32*1024**2)
        paths=[str(self.source)]*8
        manager=self.manager(source="THREAD_SAFE=True\ndef process_image(image, *, context): return image.copy()")
        with self.stage.prepare(manager,paths,0,'image','sources') as result:
            self.assertEqual(len(set(result[0])),8)
            self.assertEqual(len(list(self.stage.visible.root.rglob('*.png'))),8)
        self.assertEqual(self.stage.peak_active,1)

    def test_kernel_failure_drains_all_writers(self):
        manager=self.manager(source="THREAD_SAFE=True\ndef process_image(image, *, context): raise RuntimeError('kernel failed')")
        with self.assertRaisesRegex(RuntimeError,'kernel failed'):
            with self.stage.prepare(manager,[str(self.source)]*8,0,'image','sources'):pass
        self.assertEqual(self.stage.budget.active,0)
        self.assertEqual(self.stage.budget.bytes,0)
        self.assertFalse(list(self.stage.directory.glob('tmp_*')))


KERNEL = """
import threading
import time
THREAD_SAFE=True
initialized=0
calls=0
busy=0
peak=0
lock=threading.Lock()
gate=threading.Barrier(2,timeout=5)
def setup():
    global initialized
    initialized+=1
    return object()
def process_image(image, *, context):
    global calls,busy,peak
    with lock:
        calls+=1
        number=calls
        busy+=1
        peak=max(peak,busy)
    if number<=2:gate.wait()
    time.sleep(.005)
    result=image.copy()
    with lock:busy-=1
    return result
"""


class KernelContractTests(unittest.TestCase):
    def run_plugin(self,source,spec,images,session=None):
        registry=(('Kernel','/kernel/main.py',source,json.dumps(spec)),)
        session=session or runtime.AlgorithmSession(registry)
        previous=tuple(getattr(runtime.state,k,None) for k in ('registry','session','preview'))
        runtime.state.registry=registry;runtime.state.session=session;runtime.state.preview=True
        try:return main(images,''),session
        finally:runtime.state.registry,runtime.state.session,runtime.state.preview=previous

    def test_gpu_batch_model_is_initialized_once_and_receives_the_list(self):
        source="""
initialized=0
batches=[]
def setup():
    global initialized
    initialized+=1
    return object()
def process_batch(images, *, context):
    batches.append((len(images),id(context)))
    return [image.copy() for image in images]
def teardown(context):
    batches.append('released')
"""
        spec=dict(api_version=2,processing_mode='batch',device='test-gpu-v2')
        images=[Image.new('RGB',(4,3)) for _ in range(3)]
        try:
            outputs,session=self.run_plugin(source,spec,images)
            for image in outputs:image.close()
            outputs,_=self.run_plugin(source,spec,images,session)
            for image in outputs:image.close()
            ns=session.namespaces[0]
            self.assertEqual(ns['initialized'],1)
            self.assertEqual(ns['batches'][0],ns['batches'][1])
            ns['release_resources']()
            self.assertEqual(ns['batches'][-1],'released')
        finally:
            for image in images:image.close()

    def test_bad_v2_output_is_rejected(self):
        image=Image.new('RGB',(2,2))
        try:
            with self.assertRaisesRegex(ValueError,'one Pillow image'):
                self.run_plugin('def process_batch(images, *, context): return []',
                    dict(api_version=2,processing_mode='batch',device='cpu'),[image])
        finally:image.close()

    def test_gpu_and_ordered_image_parallelism_are_rejected(self):
        for overrides in (dict(device='cuda:0'),dict(device='cpu',ordered=True)):
            spec=dict(api_version=2,processing_mode='image');spec.update(overrides)
            with self.assertRaisesRegex(ValueError,'unordered CPU'):
                specification((('a','b','c',json.dumps(spec)),),0)

    def test_bundled_plugins_have_only_kernels_and_match_pixels(self):
        names=['Image Enhancement','Image Darkening','Gaussian Blur','Original']
        existing=set(get_available_algorithms())
        names=[name for name in names if name in existing]
        if not names:self.skipTest('No bundled examples are installed')
        registry=runtime.capture_algorithms(names)
        image=Image.effect_noise((32,24),80).convert('RGB')
        from PIL import ImageEnhance
        expected=[ImageEnhance.Contrast(image).enhance(2),ImageEnhance.Brightness(image).enhance(.5),
                  image.filter(ImageFilter.GaussianBlur(radius=2)),image]
        expected_by_name=dict(zip(['Image Enhancement','Image Darkening','Gaussian Blur','Original'],expected))
        previous=tuple(getattr(runtime.state,k,None) for k in ('registry','session'))
        runtime.state.registry=registry;runtime.state.session=runtime.AlgorithmSession(registry)
        try:
            with patch.object(Image.Image,'save',side_effect=AssertionError('Kernel must not save')):
                for index,entry in enumerate(registry):
                    self.assertNotIn('save_path',entry[2])
                    result=main([image],'ignored',algorithm_type=index)
                    self.assertEqual(result[0].tobytes(),expected_by_name[entry[0]].tobytes())
                    if result[0] is not image:result[0].close()
        finally:
            runtime.state.registry,runtime.state.session=previous
            for im in {id(im):im for im in expected+[image]}.values():im.close()


class SharedKernelBudgetTests(unittest.TestCase):
    def test_idle_parent_lanes_can_be_borrowed_but_decoder_cannot_oversubscribe(self):
        from mulimgviewer.src.pipeline_executor import PipelineWorkers
        group=PipelineWorkers(3,1)
        group.configure(3,1,memory_budget=100,costs=(10,10),total_budget=4)
        entered=threading.Event();release=threading.Event()
        try:
            self.assertEqual(group.downstream_capacity(),(4,100))
            self.assertTrue(group.reserve_downstream(1,20))
            self.assertTrue(group.reserve_downstream(1,20))
            job=group.stages[0].submit(lambda:(entered.set(),release.wait(5)),cpu_cost=3)
            self.assertFalse(entered.wait(.05))
            group.reserve_downstream(-1,-20)
            self.assertTrue(entered.wait(2))
            self.assertEqual(group.downstream_capacity(),(1,70))
            self.assertFalse(group.reserve_downstream(1,1))
            group.reserve_downstream(-1,-20)
            release.set();job.result(timeout=3)
            self.assertEqual(group.downstream_active,0)
            self.assertEqual(group.downstream_bytes,0)
        finally:
            release.set()
            for stage in group.stages:stage.shutdown(wait=True,cancel_futures=True)

    def test_memory_budget_and_downgrade_block_new_child_admission(self):
        from mulimgviewer.src.pipeline_executor import PipelineWorkers
        group=PipelineWorkers(2,2)
        try:
            group.configure(2,2,memory_budget=100,total_budget=4)
            self.assertTrue(group.reserve_downstream(1,70))
            self.assertFalse(group.reserve_downstream(1,31))
            group.configure(1,1,memory_budget=50,total_budget=2)
            self.assertFalse(group.reserve_downstream(1,1))
            group.reserve_downstream(-1,-70)
            self.assertTrue(group.reserve_downstream(1,40))
            group.reserve_downstream(-1,-40)
        finally:
            for stage in group.stages:stage.shutdown(wait=True,cancel_futures=True)


class ImagePriorityTests(unittest.TestCase):
    def test_queued_jobs_follow_latest_position(self):
        from mulimgviewer.src.custom_workers import ImageWorkers
        pool=ImageWorkers(1)
        entered=threading.Event();release=threading.Event();order=[]
        current=[0]
        try:
            running=pool.submit(lambda:(entered.set(),release.wait(5)))
            self.assertTrue(entered.wait(2))
            old=pool.submit(lambda:order.append(1),priority=lambda:abs(1-current[0]))
            new=pool.submit(lambda:order.append(5),priority=lambda:abs(5-current[0]))
            current[0]=5
            release.set()
            running.result(3);old.result(3);new.result(3)
            self.assertEqual(order,[5,1])
        finally:
            release.set();pool.shutdown(wait=True,cancel_futures=True)

    def test_close_cancels_waiters_and_settles_running_future(self):
        from mulimgviewer.src.custom_workers import ImageWorkers
        pool=ImageWorkers(1)
        entered=threading.Event();release=threading.Event()
        try:
            running=pool.submit(lambda:(entered.set(),release.wait(5)))
            self.assertTrue(entered.wait(2))
            queued=pool.submit(lambda:None)
            pool.shutdown(wait=False,cancel_futures=True)
            self.assertTrue(queued.cancelled())
            release.set();running.result(3)
        finally:
            release.set();pool.shutdown(wait=True)


if __name__=='__main__':unittest.main()
