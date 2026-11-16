"""Shutdown deletion waits for writers and is restricted to cache_frames."""
from concurrent.futures import Future,ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.cache_shutdown import schedule_cache_removal, clear_cache_on_startup


class ShutdownTests(unittest.TestCase):
    def test_close_removes_all_layers_only_after_writers_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames'
            for layer in ('.work/processed','algorithms/original/stitched','sources/video/source_001/frames','composed'):
                path=root/layer;path.mkdir(parents=True)
                (path/'frame.png').write_bytes(b'cache')
            entered=threading.Event();release=threading.Event()
            pool=ThreadPoolExecutor(1)
            def writer():
                entered.set();release.wait(5)
                (root/'composed'/'last.png').write_bytes(b'last')
            pool.submit(writer);self.assertTrue(entered.wait(2))
            done=schedule_cache_removal(root,(pool,))
            try:
                self.assertTrue(root.exists());self.assertFalse(done.done())
            finally:release.set()
            done.result(timeout=5)
            self.assertFalse(root.exists())

    def test_close_waits_for_work_cleanup_and_preserves_neighbor_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            neighbor=Path(directory)/'user_images';neighbor.mkdir()
            (neighbor/'keep.png').write_bytes(b'keep')
            reader=Future()
            done=schedule_cache_removal(root,futures=(reader,))
            self.assertFalse(done.done());self.assertTrue(root.exists())
            reader.set_result(None);done.result(timeout=5)
            self.assertFalse(root.exists());self.assertTrue((neighbor/'keep.png').is_file())
            with self.assertRaises(ValueError):schedule_cache_removal(neighbor)

    def test_replaced_cache_directory_is_not_deleted_by_old_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            gate=Future()
            done=schedule_cache_removal(root,futures=(gate,))
            root.rename(Path(directory)/'old_cache')
            root.mkdir();(root/'new.png').write_bytes(b'new session')
            gate.set_result(None)
            with self.assertRaises(ValueError):done.result(timeout=5)
            self.assertTrue((root/'new.png').is_file())


class StartupTests(unittest.TestCase):
    def test_parent_alias_is_normalized_for_startup_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);(parent/'alias').mkdir()
            aliases=[('dot segments',parent/'alias'/'..'/'cache_frames')]
            if sys.platform=='win32':
                import ctypes
                buffer=ctypes.create_unicode_buffer(32768)
                if ctypes.windll.kernel32.GetShortPathNameW(str(parent),buffer,len(buffer)):
                    requested=Path(buffer.value)/'cache_frames'
                    if requested.absolute()!=requested.resolve():aliases.append(('native Windows 8.3',requested))
            for kind,requested in aliases:
                with self.subTest(alias=kind):
                    root=parent/'cache_frames';root.mkdir()
                    (root/'old.png').write_bytes(b'old')
                    self.assertNotEqual(requested.absolute(),requested.resolve())
                    self.assertTrue(clear_cache_on_startup(requested));self.assertFalse(root.exists())
                    root.mkdir();(root/'new.png').write_bytes(b'new')
                    schedule_cache_removal(requested).result(timeout=5)
                    self.assertFalse(root.exists());self.assertTrue((parent/'alias').is_dir())

    def test_startup_removes_all_stale_layers_and_preserves_neighbors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames'
            for layer in ('.work/processed','sources/video/source_001/frames','algorithms/Example/processed','algorithms/original/stitched','composed'):
                folder=root/layer;folder.mkdir(parents=True)
                (folder/'stale.png').write_bytes(b'stale')
            neighbor=Path(directory)/'user_images';neighbor.mkdir()
            image=neighbor/'keep.png';image.write_bytes(b'original')
            config=Path(directory)/'userdef_config.json';config.write_bytes(b'config')
            self.assertTrue(clear_cache_on_startup(root))
            self.assertFalse(root.exists())
            self.assertEqual(image.read_bytes(),b'original')
            self.assertEqual(config.read_bytes(),b'config')
            self.assertFalse(clear_cache_on_startup(root))
            # New session can create fresh files after startup cleanup completes.
            (root/'composed').mkdir(parents=True)
            fresh=root/'composed/page_000001.png';fresh.write_bytes(b'fresh')
            self.assertEqual(fresh.read_bytes(),b'fresh')

    def test_startup_rejects_non_cache_roots_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            neighbor=Path(directory)/'images';neighbor.mkdir()
            with self.assertRaises(ValueError):clear_cache_on_startup(neighbor)
            root=Path(directory)/'cache_frames';root.write_bytes(b'not a directory')
            with self.assertRaises(ValueError):clear_cache_on_startup(root)
            self.assertTrue(root.is_file())

    def test_startup_retries_transient_removal_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            import shutil
            remove=shutil.rmtree
            calls=[]
            def removing(path):
                calls.append(path)
                if len(calls)==1:raise PermissionError('transient sharing failure')
                remove(path)
            with patch('mulimgviewer.src.cache_shutdown.shutil.rmtree',side_effect=removing),patch('mulimgviewer.src.cache_shutdown.time.sleep'):
                self.assertTrue(clear_cache_on_startup(root))
            self.assertEqual(len(calls),2)

    def test_missing_child_does_not_leave_a_partially_cleaned_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            (root/'stale.png').write_bytes(b'stale')
            import shutil
            remove=shutil.rmtree
            count=[]
            def removing(path):
                count.append(path)
                if len(count)==1:raise FileNotFoundError('a child disappeared')
                remove(path)
            with patch('mulimgviewer.src.cache_shutdown.shutil.rmtree',side_effect=removing),patch('mulimgviewer.src.cache_shutdown.time.sleep'):
                self.assertTrue(clear_cache_on_startup(root))
            self.assertFalse(root.exists())
            self.assertEqual(len(count),2)

    def test_startup_does_not_delete_a_replacement_root_during_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            def replacing(path):
                root.rename(Path(directory)/'old_cache')
                root.mkdir();(root/'new.png').write_bytes(b'new session')
                raise PermissionError('transient failure')
            with patch('mulimgviewer.src.cache_shutdown.shutil.rmtree',side_effect=replacing),patch('mulimgviewer.src.cache_shutdown.time.sleep'):
                with self.assertRaisesRegex(ValueError,'was replaced'):
                    clear_cache_on_startup(root)
            self.assertEqual((root/'new.png').read_bytes(),b'new session')

    def test_startup_aborts_if_cleanup_cannot_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'cache_frames';root.mkdir()
            with patch('mulimgviewer.src.cache_shutdown.shutil.rmtree',side_effect=PermissionError('in use')),patch('mulimgviewer.src.cache_shutdown.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'Cannot clear previous cache'):
                    clear_cache_on_startup(root)
            self.assertTrue(root.exists())

    def test_startup_rejects_linked_cache_root_before_removing_any_files(self):
        with tempfile.TemporaryDirectory() as directory:
            outside=Path(directory)/'photos';outside.mkdir()
            original=outside/'keep.png';original.write_bytes(b'original')
            root=Path(directory)/'cache_frames'
            try:
                root.symlink_to(outside,target_is_directory=True)
                link_kind='real symlink'
            except OSError:
                # Some Windows accounts/sandboxes forbid both symlinks and
                # junctions. Still exercise the production rejection guard,
                # explicitly labelling the metadata simulation in the report.
                if sys.platform!='win32':raise
                link_kind='simulated link metadata; OS denied symlink creation'
            actual=Path.is_symlink
            def is_link(path):return path==root or actual(path)
            with self.subTest(link_kind=link_kind),patch.object(Path,'is_symlink',is_link),\
                 patch('mulimgviewer.src.cache_shutdown.shutil.rmtree') as remove:
                with self.assertRaises(ValueError):clear_cache_on_startup(root)
                remove.assert_not_called()
            self.assertEqual(original.read_bytes(),b'original')



if __name__=='__main__':unittest.main()
