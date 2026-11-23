"""Quantified warning/critical/recovery levels and symmetric stage borrowing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/mulimgviewer/src'))
from playback_policy import AdaptiveThreadAllocator, buffer_levels, buffer_priority
from test_video_cache import VideoManager, SharedConfig, PerformanceMonitor
import threading


class BufferPolicyTests(unittest.TestCase):
    def test_raw_target_uses_directional_refill_time_and_available_space(self):
        monitor = PerformanceMonitor()
        def targets(period, direction=1, remaining=80):
            output, raw = monitor.stage_buffer_levels(8, 80, remaining, period, direction)
            return output.low, raw.low
        self.assertEqual(targets(.1), (8, 4))
        monitor.record_raw_refill(1, .15)
        self.assertEqual(targets(.1), (8, 2))
        monitor.record_raw_refill(-1, 1.2)
        self.assertEqual(targets(.1, -1), (8, 12))
        self.assertEqual(targets(.2, -1), (8, 6))
        self.assertEqual(targets(.1, -1, remaining=3), (8, 3))
        self.assertEqual(targets(.1, -1, remaining=0), (8, 0))

    def test_warning_half_radius_emergency_and_recovery(self):
        for radius, critical, recover in ((1, 1, 2), (2, 1, 3), (3, 2, 5), (4, 2, 6)):
            levels = buffer_levels(radius, 20, 1.)
            self.assertEqual(tuple(levels), (radius, critical, recover, 20))

    def test_latency_warns_early_without_expanding_outer_window(self):
        levels = buffer_levels(2, 12, .05, .25, .1)
        self.assertEqual(levels.low, 7)
        self.assertEqual(levels.recover, 8)
        self.assertEqual(buffer_levels(2, 6, .001, 1., 1.).low, 6)

    def test_small_cache_and_end_boundaries_never_require_impossible_recovery(self):
        for capacity in (0, 1, 2):
            levels = buffer_levels(4, capacity, .01, 10.)
            self.assertLessEqual(levels.low, capacity)
            self.assertLessEqual(levels.critical, capacity)
            self.assertLessEqual(levels.recover, capacity)
            self.assertIsNone(buffer_priority(capacity, 0, levels, buffer_levels(4, 0, .01)))

    def test_hysteresis_keeps_priority_until_recovery(self):
        levels = buffer_levels(2, 6, 1.)
        self.assertEqual(buffer_priority(1, 3, levels, levels), 'stitch')
        self.assertEqual(buffer_priority(2, 2, levels, levels, 'stitch'), 'stitch')
        self.assertIsNone(buffer_priority(3, 3, levels, levels, 'stitch'))
        self.assertEqual(buffer_priority(4, 1, levels, levels), 'raw')
        self.assertEqual(buffer_priority(4, 2, levels, levels, 'raw'), 'raw')
        self.assertIsNone(buffer_priority(4, 3, levels, levels, 'raw'))

    def test_both_buffers_low_prioritizes_existing_inputs_or_extraction(self):
        levels = buffer_levels(2, 6, 1.)
        self.assertEqual(buffer_priority(0, 0, levels, levels), 'raw')
        self.assertEqual(buffer_priority(0, 1, levels, levels), 'stitch')

    def test_ready_output_and_low_unused_raw_borrow_composition_threads(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.4, .2, .01), (2, 10), extract_backlog=24,
            buffer_depth=3, raw_buffer_depth=0,
            stitched_levels=buffer_levels(2, 6, 1.), raw_levels=buffer_levels(2, 3, 1.))
        self.assertEqual(plan[:2], (4, 8))
        self.assertEqual(plan.reason, 'raw-buffer-low')

    def test_ready_raw_and_low_output_borrow_decoder_threads(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.4, .2, .01), (10, 2), stitch_ready=5,
            buffer_depth=1, raw_buffer_depth=3,
            stitched_levels=buffer_levels(2, 6, 1.), raw_levels=buffer_levels(2, 5, 1.))
        self.assertEqual(plan[:2], (8, 4))
        self.assertEqual(plan.reason, 'stitch-buffer-low')

    def test_waiting_input_never_gets_extra_composition_threads(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.4, .2, .01), (2, 10), extract_backlog=24, stitch_waiting=10,
            buffer_depth=0, raw_buffer_depth=0,
            stitched_levels=buffer_levels(2, 6, 1.), raw_levels=buffer_levels(2, 6, 1.))
        self.assertGreater(plan.extract, 2)
        self.assertLess(plan.stitch, 10)


class RawInventoryTests(unittest.TestCase):
    def setUp(self):
        self.vm = VideoManager.__new__(VideoManager)
        self.vm._cache_guard = threading.RLock()
        self.vm.shared_config = self.cfg = SharedConfig()
        self.cfg.video_num_list = [1000, 1000]
        self.cfg.batch_idx = 50
        self.vm._stitch_window = (44, 56)
        self.vm._raw_ready_batches = {(v, b) for v in range(2) for b in range(44, 57)}

    def test_unused_input_is_counted_after_stitched_frontier(self):
        self.assertEqual(self.vm._raw_buffer_inventory(3), (3, 3, 6))
        self.vm._raw_ready_batches.remove((1, 55))
        self.assertEqual(self.vm._raw_buffer_inventory(3), (1, 3, 6))

    def test_reverse_counts_backwards(self):
        self.cfg.play_direction = -1
        self.assertEqual(self.vm._raw_buffer_inventory(2), (4, 4, 6))
        self.vm._raw_ready_batches.remove((1, 46))
        self.assertEqual(self.vm._raw_buffer_inventory(2), (1, 4, 6))

    def test_all_videos_and_multi_frame_pages_must_be_ready(self):
        self.cfg.count_per_action = 4
        self.cfg.video_num_list = [400, 12]
        self.cfg.batch_idx = 10
        self.vm._stitch_window = (4, 16)
        self.vm._raw_ready_batches = {(0, b) for b in range(14, 17)} | {(1, 2)}
        self.assertEqual(self.vm._raw_buffer_inventory(3), (3, 3, 6))
        self.vm._raw_ready_batches.remove((1, 2))
        self.assertEqual(self.vm._raw_buffer_inventory(3), (0, 3, 6))

    def test_sequential_reverse_crosses_video_boundary(self):
        self.cfg.parallel_to_sequential = True
        self.cfg.play_direction = -1
        self.cfg.video_num_list = [3, 4]
        self.cfg.batch_idx = 4
        self.vm._stitch_window = (0, 6)
        self.vm._raw_ready_batches = {(0, b) for b in range(3)}
        self.assertEqual(self.vm._raw_buffer_inventory(1), (3, 3, 4))

    def test_stale_and_outside_window_readiness_is_rejected(self):
        self.vm._window_token = 'new'
        self.vm._raw_windows = {0: (44, 57), 1: (44, 57)}
        self.vm._raw_ready_batches.clear()
        self.vm._mark_raw_batch_ready(0, 54, 'old', True)
        self.vm._mark_raw_batch_ready(0, 40, 'new', True)
        self.assertFalse(self.vm._raw_ready_batches)
        self.vm._mark_raw_batch_ready(0, 54, 'new', True)
        self.assertEqual(self.vm._raw_ready_batches, {(0, 54)})
