"""Cross-platform allocator adapters and background downgrade coordination."""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src import memory_reclaim as memory


class NativeReleaseTests(unittest.TestCase):
    def test_native_release_preserves_live_pixels(self):
        from PIL import Image
        image = Image.new('RGBA', (128, 128), (12, 34, 56, 255))
        result = memory.release_unused_memory(trim_working_set=False)
        self.assertEqual(image.getpixel((127, 127)), (12, 34, 56, 255))
        self.assertIn('heap_released', result)
        self.assertFalse(result['working_set_trimmed'])

    def run_release(self, platform, runtime, trim=False, native_name='posix'):
        with patch.object(memory.os, 'name', native_name), patch.object(memory.sys, 'platform', platform), \
             patch.object(memory.gc, 'collect', return_value=3), \
             patch.object(memory.ctypes, 'CDLL', return_value=runtime):
            return memory.release_unused_memory(trim)

    def test_linux_uses_malloc_trim(self):
        runtime = Mock()
        runtime.malloc_trim.return_value = 1
        result = self.run_release('linux', runtime)
        runtime.malloc_trim.assert_called_once_with(0)
        self.assertTrue(result['heap_released'])
        self.assertEqual(result['collected'], 3)

    def test_macos_uses_all_malloc_zones_without_forcing_live_pages_out(self):
        runtime = Mock()
        runtime.malloc_zone_pressure_relief.return_value = 4096
        result = self.run_release('darwin', runtime)
        runtime.malloc_zone_pressure_relief.assert_called_once_with(None, 0)
        self.assertTrue(result['heap_released'])
        self.assertFalse(result['working_set_trimmed'])

    def test_missing_allocator_api_safely_falls_back_to_gc(self):
        for platform in ('linux', 'darwin', 'freebsd'):
            runtime = Mock(spec=[])
            result = self.run_release(platform, runtime)
            self.assertEqual(result, dict(collected=3, heap_released=False, working_set_trimmed=False))

    def test_windows_trims_working_set_only_when_explicitly_idle(self):
        runtime, kernel, psapi = Mock(), Mock(), Mock()
        runtime._heapmin.return_value = 0
        kernel.GetCurrentProcess.return_value = 123
        psapi.EmptyWorkingSet.return_value = 1
        with patch.object(memory.ctypes, 'WinDLL', create=True, side_effect=[kernel, psapi]):
            result = self.run_release('win32', runtime, trim=True, native_name='nt')
        psapi.EmptyWorkingSet.assert_called_once_with(123)
        self.assertTrue(result['working_set_trimmed'])
        with patch.object(memory.ctypes, 'WinDLL', create=True) as loader:
            self.run_release('win32', runtime, trim=False, native_name='nt')
        loader.assert_not_called()


class ReclaimCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.reclaimer = memory.MemoryReclaimer()

    def tearDown(self):
        self.reclaimer.close()
        self.reclaimer.executor.shutdown(wait=True)

    def test_downgrade_waits_in_background_then_retires_before_reclaiming(self):
        ready = threading.Event()
        order = []
        main_thread = threading.get_ident()
        def release(trim):
            self.assertNotEqual(threading.get_ident(), main_thread)
            order.append(('release', trim))
            return dict(ok=True)
        with patch.object(memory, 'release_unused_memory', side_effect=release):
            started = time.perf_counter()
            self.reclaimer.request(ready.is_set, lambda: order.append('retire'), lambda: False)
            self.assertLess(time.perf_counter() - started, .1)
            self.assertEqual(order, [])
            ready.set()
            self.assertEqual(self.reclaimer.future.result(timeout=3), dict(ok=True))
        self.assertEqual(order, ['retire', ('release', False)])

    def test_upgrade_cancels_pending_reclamation(self):
        entered = threading.Event()
        def not_ready():
            entered.set()
            return False
        with patch.object(memory, 'release_unused_memory') as release:
            self.reclaimer.request(not_ready, Mock(), lambda: True)
            self.assertTrue(entered.wait(2))
            self.reclaimer.cancel()
            self.reclaimer.future.result(timeout=2)
        release.assert_not_called()

    def test_rapid_changes_coalesce_to_latest_request(self):
        entered = threading.Event()
        def blocked():
            entered.set()
            return False
        with patch.object(memory, 'release_unused_memory', return_value={}) as release:
            self.reclaimer.request(blocked, Mock(), lambda: False)
            self.assertTrue(entered.wait(2))
            self.reclaimer.request(lambda: True, Mock(), lambda: True)
            self.reclaimer.future.result(timeout=2)
        release.assert_called_once_with(True)


if __name__ == '__main__':
    unittest.main()
