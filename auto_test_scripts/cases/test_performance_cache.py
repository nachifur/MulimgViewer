"""Resource constraints and real asynchronous image-cache lifecycle regressions."""
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from mulimgviewer.src.image_pipeline import ImagePipeline
from mulimgviewer.src.resource_policy import resource_budget, cache_window, composition_workers, positive_cache_integer


class PolicyTests(unittest.TestCase):
    def test_cache_parameters_accept_one_and_reject_fractional_nonpositive_or_nonfinite_values(self):
        for text in ('1', '2', ' 3 ', '2.0'):
            self.assertEqual(positive_cache_integer(text), int(float(text)))
        for text in ('0.5', '1.5', '0', '-1', 'NaN', 'inf', '', 'abc', '1e999999'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                positive_cache_integer(text)

    def test_modes_monotonic_and_video_has_two_lanes(self):
        budgets = [resource_budget(m, cpus=16, available=8 * 1024 ** 3) for m in range(1, 5)]
        self.assertEqual([b.workers for b in budgets], [4, 8, 12, 16])
        self.assertEqual(sorted(b.memory for b in budgets), [b.memory for b in budgets])
        self.assertEqual(resource_budget(1, video=True, cpus=1, available=1024).workers, 2)
        self.assertEqual(resource_budget(1, cpus=1, available=1024).workers, 1)

    def test_memory_limits_composition_concurrency(self):
        self.assertEqual(composition_workers(12, 128 * 1024 ** 2), 2)
        self.assertEqual(composition_workers(12, 128 * 1024 ** 2, 10000 * 10000), 1)

    def test_two_levels_anchor_trigger_boundaries_and_reverse(self):
        self.assertEqual(cache_window(20, 80, 2, 1), (18, 22))
        outer = cache_window(20, 80, 2, 3)
        self.assertEqual(outer, (14, 26))
        self.assertEqual(cache_window(23, 80, 2, 3, outer), outer)
        self.assertEqual(cache_window(24, 80, 2, 3, outer), (18, 30))
        self.assertEqual(cache_window(16, 80, 2, 3, outer), (10, 22))
        self.assertEqual(cache_window(0, 80, 2, 3, (0, 6)), (0, 6))


class FakeManager:
    cache_save_format = 1  # These lifecycle tests intentionally assert PNG paths.
    count_per_action = 1
    img_resolution_origin = [32, 24]
    layout_params = [None] * 33
    entered = None
    release = None

    def video_stitch_snapshot(self):
        result = FakeManager()
        result.layout_params = self.layout_params[:]
        return result

    def set_action_count(self, batch):
        self.action_count = batch

    def get_flist(self):
        self.flist = [f'image_{self.action_count}.png']
        return self.flist

    def stitch_images(self, *args, **kwargs):
        if self.entered is not None:
            self.entered.set()
            if not self.release.wait(5):
                raise TimeoutError('test did not release compositor')
        self.img = Image.new('RGB', (32, 24), (self.action_count, 0, 0))
        return 0

    def show_stitch_img_and_customfunc_img(self, custom):
        return self.img


class ImageCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.messages = queue.Queue()
        self.events = []
        self.pipeline = ImagePipeline(Path(self.temp.name) / 'stitch_cache',
            lambda *args: self.events.append(args), lambda f, *args: self.messages.put((f, args)))

    def tearDown(self):
        self.pipeline.close()
        for pool in (self.pipeline.coordinator, self.pipeline.pool, self.pipeline.display):
            if pool:
                pool.shutdown(wait=True)
        self.pipeline.processing.cleanup_future.result(timeout=5)
        self.temp.cleanup()

    def pump(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                callback, args = self.messages.get(timeout=.01)
                callback(*args)
            except queue.Empty:
                pass
            if predicate():
                return
        self.fail(f'pipeline did not settle: {self.pipeline.last_error}')

    def request(self, batch=20, context='first', budget=4, memory=2 * 1024 ** 3):
        self.pipeline.request(FakeManager(), [], False, context, batch, 80, 2, 3, budget, memory)

    def settle(self, start, end):
        expected = set(range(start, end + 1))
        self.pump(lambda: set(self.pipeline.cache) == expected and not self.pipeline.running
                  and not self.pipeline._pump_queued)

    def test_thirteen_pngs_use_video_names_and_cleanup_only_owned_files(self):
        self.pipeline.directory.mkdir()
        video = self.pipeline.directory / 'page_000071.png'
        video.write_bytes(b'video cache')
        self.request()
        self.settle(14, 26)
        self.assertEqual(self.pipeline.workers, 4)
        self.assertEqual(len(list(self.pipeline.directory.glob('page_*.png'))), 14)
        self.request(23)
        self.settle(14, 26)
        self.request(24)
        self.settle(18, 30)
        self.assertEqual(len(list(self.pipeline.directory.glob('page_*.png'))), 14)
        self.assertTrue(video.exists())

    def test_request_returns_while_composition_blocked_and_stale_work_is_rejected(self):
        entered, release = threading.Event(), threading.Event()
        try:
            with patch.object(FakeManager, 'entered', entered), patch.object(FakeManager, 'release', release):
                self.request()
                self.assertTrue(entered.wait(3))
                started = time.perf_counter()
                self.request(50, 'replacement', budget=2)
                self.assertLess(time.perf_counter() - started, .1)
                generation = self.pipeline.generation
                release.set()
                self.settle(44, 56)
                self.assertEqual(self.pipeline.workers, 2)
                self.assertEqual(self.pipeline.generation, generation)
                self.assertTrue(all(Path(entry[0]).name == f'page_{batch+1:06d}.png'
                                    for batch, entry in self.pipeline.cache.items()))
                self.assertEqual(len(list(self.pipeline.directory.glob('page_*.png'))), 13)
        finally:
            release.set()

    def test_supply_measures_published_pages_excludes_cache_hits_and_resets_on_refresh(self):
        self.request()
        self.settle(14, 26)
        pacer = self.pipeline.supply_pacer
        period = pacer.supply_period()
        self.assertIsNotNone(period)
        self.assertGreater(period, 0)
        with pacer.lock:
            samples = list(pacer.samples)
            self.assertFalse(pacer.pending)
        self.request()
        self.settle(14, 26)
        self.assertEqual(pacer.supply_period(), period)
        with pacer.lock:self.assertEqual(list(pacer.samples), samples)
        self.pipeline.invalidate()
        self.assertIsNone(pacer.supply_period())

    def test_cached_pixels_load_off_request_thread_and_corrupt_cache_recovers(self):
        self.request()
        self.settle(14, 26)
        Path(self.pipeline.cache[20][0]).write_bytes(b'broken PNG')
        delivered = []
        self.assertTrue(self.pipeline.prepare_display(20, lambda *args: delivered.append(args)))
        self.pump(lambda: bool(delivered))
        self.assertIsNotNone(delivered[0][-1])
        self.settle(14, 26)
        self.pipeline.prepare_display(20, lambda *args: delivered.append(args))
        self.pump(lambda: len(delivered) == 2)
        self.assertEqual(delivered[1][2][0].getpixel((0, 0))[0], 20)
        self.assertEqual(delivered[1][3]['flist'], ['image_20.png'])
        self.assertIsNone(delivered[1][-1])

    def test_mode_switch_cleanup_preserves_replaced_video_file_and_removes_legacy_names(self):
        self.pipeline.directory.mkdir()
        legacy = self.pipeline.directory / 'image_old_batch_20.png'
        legacy.write_bytes(b'old image cache')
        self.request()
        self.settle(14, 26)
        self.assertFalse(legacy.exists())
        current = self.pipeline.directory / 'page_000021.png'
        replacement = self.pipeline.directory / 'video.tmp'
        replacement.write_bytes(b'new video cache')
        replacement.replace(current)
        self.pipeline.invalidate()
        self.pump(lambda: not self.pipeline._pump_queued and not self.pipeline._published_files)
        self.assertEqual(current.read_bytes(), b'new video cache')
        self.assertEqual(list(self.pipeline.directory.glob('page_*.png')), [current])

    def test_memory_budget_resizes_without_losing_window(self):
        self.request()
        self.settle(14, 26)
        self.request(memory=64 * 1024 ** 2)
        self.pump(lambda: self.pipeline.workers == 1 and not self.pipeline._pump_queued)
        self.assertEqual(len(self.pipeline.cache), 13)

    def test_failed_page_can_be_retried_without_changing_layout(self):
        original = FakeManager.stitch_images
        def fail_current(manager, *args, **kwargs):
            return 1 if manager.action_count == 20 else original(manager, *args, **kwargs)
        with patch.object(FakeManager, 'stitch_images', fail_current):
            self.request()
            self.pump(lambda: 20 in self.pipeline.failed and not self.pipeline.running)
        generation = self.pipeline.generation
        self.request()
        self.settle(14, 26)
        self.assertEqual(generation, self.pipeline.generation)
        self.assertNotIn(20, self.pipeline.failed)


if __name__ == '__main__':
    unittest.main()
