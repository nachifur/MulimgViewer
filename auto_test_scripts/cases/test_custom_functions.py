"""Thread-safe custom processing, immutable sources and preview side effects."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.custom_func import runtime
from mulimgviewer.src.custom_func.main import main, get_available_algorithms


class Runner:
    layout_params=[]
    def __init__(self, registry):
        self._custom_algorithm_registry=registry
        self._custom_algorithm_session=runtime.AlgorithmSession(registry)
    @runtime.render_context
    def stitch(self, img_mode, save_path='', index=0):
        return main([],save_path,algorithm_type=index)


class CustomRuntimeTests(unittest.TestCase):
    def registry(self, name='Example', value=1):
        return ((name,'/unavailable/custom/main.py',
                 f'def main(images, path, names, *, algorithm_name):\n    return [{value}, path, algorithm_name]\n'),)

    def test_preview_disables_export_but_explicit_save_retains_path(self):
        runner=Runner(self.registry())
        self.assertEqual(runner.stitch(0,save_path='output'),[1,'','Example'])
        self.assertEqual(runner.stitch(1,save_path='output'),[1,'output','Example'])

    def test_workers_keep_registry_and_do_not_cross_contaminate(self):
        runners=[Runner(self.registry('A',1)),Runner(self.registry('B',2))]
        with ThreadPoolExecutor(8) as pool:
            values=list(pool.map(lambda i:runners[i%2].stitch(0),range(100)))
        for i,value in enumerate(values):self.assertEqual(value,[i%2+1,'','AB'[i%2]])
        self.assertIsNone(getattr(runtime.state,'registry',None))

    def test_running_snapshot_survives_algorithm_removal_and_new_code_is_seen(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);folder=root/'Example';folder.mkdir()
            source=folder/'main.py'
            source.write_text('def main(a,b,c): return [1]',encoding='utf-8')
            with patch.object(runtime,'__file__',str(root/'runtime.py')):
                old=Runner(runtime.capture_algorithms(['Example']))
                source.write_text('def main(a,b,c): return [2]',encoding='utf-8')
                new=Runner(runtime.capture_algorithms(['Example']))
            source.unlink()
            self.assertEqual(old.stitch(0),[1]);self.assertEqual(new.stitch(0),[2])

    def test_invalid_algorithm_is_reported_instead_of_silently_replaced(self):
        runner=Runner((('Broken','/missing/main.py','def broken('),))
        with self.assertRaisesRegex(RuntimeError,'Broken'):
            runner.stitch(0)
        self.assertIsNone(getattr(runtime.state,'registry',None))

    def test_registry_names_are_isolated_and_restored(self):
        class Names(Runner):
            @runtime.render_context
            def names(self,img_mode):return get_available_algorithms()
        self.assertEqual(Names(self.registry('Frozen')).names(0),['Frozen'])
        self.assertIn('Gaussian Blur',get_available_algorithms())

    def test_stateful_model_is_initialized_once_and_calls_are_serialized(self):
        source='''
import time
calls = 0
busy = False
def main(images, path, names):
    global calls, busy
    if busy: raise RuntimeError('Concurrent model access')
    busy = True
    time.sleep(.001)
    calls += 1
    result = calls
    busy = False
    return [result]
'''
        runner=Runner((('Model','/model/main.py',source),))
        with ThreadPoolExecutor(8) as pool:
            results=list(pool.map(lambda _:runner.stitch(0),range(30)))
        self.assertEqual(sorted(value[0] for value in results),list(range(1,31)))
        self.assertEqual(len(runner._custom_algorithm_session.namespaces),1)

    def test_custom_memory_guard_precedes_user_model_allocation(self):
        from PIL import Image
        from mulimgviewer.src.utils_img import ImgManager
        with tempfile.TemporaryDirectory() as root:
            image=Path(root)/'large.png';Image.new('RGB',(100,100)).save(image)
            manager=ImgManager()
            manager.layout_params=[None]*41
            manager.layout_params[32]=True;manager.layout_params[38]=False
            manager._custom_memory_budget=1000
            with patch('mulimgviewer.src.playback_policy.available_memory_bytes',return_value=1000), \
                    self.assertRaisesRegex(MemoryError,'system memory'):
                runtime.check_processing_budget(manager,[str(image)])
            with patch('mulimgviewer.src.playback_policy.available_memory_bytes',return_value=1000000):
                runtime.check_processing_budget(manager,[str(image)])

    def test_processed_disk_results_do_not_repeat_legacy_full_batch_memory_charge(self):
        from types import SimpleNamespace
        manager=SimpleNamespace(_custom_memory_budget=1,_custom_results={0:('cached.png',)})
        with patch('PIL.Image.open',side_effect=AssertionError('Processed inputs must not be charged again')):
            runtime.check_processing_budget(manager,['original.png'])


if __name__=='__main__':unittest.main()
