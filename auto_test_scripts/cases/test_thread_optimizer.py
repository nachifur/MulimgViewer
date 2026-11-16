"""Analytical and feedback regressions for the generic thread allocator."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/mulimgviewer/src'))
from thread_optimizer import (AdaptiveThreadAllocator, optimize_thread_allocation,
                              stitch_memory_limit)


class ThreadOptimizerTests(unittest.TestCase):
    def test_cpu_headroom_fills_ready_work_with_unused_opposite_stage_quota(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        maximum = learner.recommend(12, (.5, .5, .01), (10, 2),
            extract_backlog=2, stitch_ready=8, buffer_depth=4, cpu_headroom=True, power_mode=4)
        performance = learner.recommend(12, (.5, .5, .01), (10, 2),
            extract_backlog=2, stitch_ready=8, buffer_depth=4, cpu_headroom=True, power_mode=3)
        self.assertEqual(maximum[:2], (8, 4))
        self.assertEqual(performance[:2], (9, 3))
        self.assertEqual(maximum.reason, 'ready-capacity')

    def test_cpu_feedback_does_not_take_required_ready_capacity_or_exceed_ram(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.5, .5, .01), (10, 2),
            extract_backlog=10, stitch_ready=8, buffer_depth=4, cpu_headroom=True, power_mode=4)
        self.assertNotEqual(plan.reason, 'ready-capacity')
        plan = learner.recommend(12, (.5, .5, .01), (10, 2),
            extract_backlog=2, stitch_ready=8, buffer_depth=4, cpu_headroom=True, power_mode=4,
            memory_budget=1600, extract_memory=100, stitch_memory=300)
        self.assertLessEqual(plan.extract*100 + plan.stitch*300, 1600)

    def test_raw_reserve_borrows_extraction_lanes_when_entire_budget_is_assigned(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.12, .8, .01), (11, 1),
            stitch_ready=8, stitch_waiting=0, extract_backlog=0,
            buffer_depth=1, buffer_target=2)
        self.assertEqual(plan[:2], (10, 2))
        self.assertEqual(plan.reason, 'downstream-starved')
        plan = learner.recommend(12, (.12, .8, .01), (10, 2),
            stitch_ready=6, stitch_waiting=0, extract_backlog=0,
            buffer_depth=0, buffer_target=2)
        self.assertEqual(plan[:2], (8, 4))

    def test_downstream_transfer_keeps_joint_memory_constraint(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.12, .8, .01), (11, 1),
            stitch_ready=8, buffer_depth=0, memory_budget=1400,
            extract_memory=100, stitch_memory=300)
        self.assertGreater(plan.stitch, 1)
        self.assertLessEqual(plan.extract * 100 + plan.stitch * 300, 1400)

    def test_throughput_mode_does_not_collapse_at_display_bottleneck(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        for _ in range(4):
            learner.observe((9, 3), .72, .24, .5)
        plan = learner.recommend(12, (.72, .24, .5), (9, 3), allow_probe=False,
                                 buffer_depth=3, buffer_target=2)
        self.assertEqual(plan[:2], (9, 3))

    def test_throughput_ties_use_capacity_and_larger_budget_improves_production(self):
        performance = optimize_thread_allocation(12, .72, .24, 0, prefer_capacity=True)
        maximum = optimize_thread_allocation(16, .72, .24, 0, prefer_capacity=True)
        self.assertEqual(performance[:2], (9, 3))
        self.assertEqual(maximum[:2], (12, 4))
        self.assertLess(maximum.period, performance.period)
        limited = optimize_thread_allocation(12, .24, .08, 0,
            max_extract_tasks=5, max_stitch_tasks=5, prefer_capacity=True)
        self.assertEqual(limited[:2], (5, 5))

    def test_joint_memory_solver_rebalances_instead_of_clipping_composition(self):
        plan = optimize_thread_allocation(12, .12, 1.2, 0,
            prefer_capacity=True, memory_budget=1400, extract_memory=100, stitch_memory=300)
        self.assertEqual(plan[:2], (2, 4))
        self.assertLessEqual(plan.extract * 100 + plan.stitch * 300, 1400)
        self.assertLess(plan.period, 1.2)  # Decoder-first clipping would leave one compositor.

    def test_starvation_and_probe_respect_joint_memory(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        plan = learner.recommend(12, (.72, .24, .5), (3, 1),
            extract_backlog=24, stitch_waiting=5, buffer_depth=0,
            memory_budget=700, extract_memory=100, stitch_memory=300)
        self.assertLessEqual(plan.extract * 100 + plan.stitch * 300, 700)

    def test_joint_memory_matrix_matches_exhaustive_minimum(self):
        for budget in (4, 12, 16):
            for extract_work, stitch_work in ((.72, .24), (.12, 1.2), (.01, .01)):
                for memory in (400, 700, 1400, 4000):
                    plan = optimize_thread_allocation(budget, extract_work, stitch_work, 0,
                        prefer_capacity=True, memory_budget=memory, extract_memory=100, stitch_memory=300)
                    candidates = [(max(extract_work / e, stitch_work / s), -(e+s))
                        for e in range(1, budget) for s in range(1, budget-e+1)
                        if e*100 + s*300 <= memory]
                    self.assertAlmostEqual(plan.period, min(candidates)[0])
                    self.assertEqual(-(plan.extract + plan.stitch), min(candidates)[1])

    def test_throughput_growth_still_rolls_back_measured_contention_loss(self):
        learner = AdaptiveThreadAllocator(throughput_first=True)
        learner.observe((9, 3), .72, .24, .5)
        learner.applied((9, 3), (12, 4))
        for _ in range(3):
            learner.observe((12, 4), 1.44, .48, .5)
        proposal = learner.recommend(16, (1.44, .48, .5), (12, 4))
        self.assertEqual(proposal[:2], (9, 3))
        self.assertEqual(proposal.reason, 'rollback')

    def test_24_streams_with_moderate_composition(self):
        self.assertEqual(optimize_thread_allocation(12, 24 * .03, .24, .02)[:2], (9, 3))
        self.assertEqual(optimize_thread_allocation(4, 24 * .03, .24, .02)[:2], (3, 1))

    def test_expensive_layout_moves_workers_to_composition(self):
        self.assertEqual(optimize_thread_allocation(12, .72, 2.16, .02)[:2], (3, 9))
        self.assertEqual(optimize_thread_allocation(4, .72, 2.16, .02)[:2], (1, 3))

    def test_single_video_task_limit_and_unused_budget(self):
        plan = optimize_thread_allocation(12, .24, .08, .005, max_extract_tasks=5)
        self.assertEqual(plan[:2], (5, 2))
        self.assertAlmostEqual(plan.period, .048)

    def test_small_cache_limits_parallel_stitches(self):
        plan = optimize_thread_allocation(12, .72, 2.16, .02, max_stitch_tasks=5)
        self.assertEqual(plan[:2], (2, 5))

    def test_serial_composition_does_not_waste_more_workers(self):
        plan = optimize_thread_allocation(12, .72, .24, .02, stitch_serial=1)
        self.assertEqual(plan[:2], (3, 1))

    def test_display_bottleneck_leaves_unused_workers(self):
        plan = optimize_thread_allocation(12, .72, .24, .5)
        self.assertEqual(plan[:2], (2, 1))
        self.assertEqual(plan.period, .5)

    def test_upstream_starvation_wakes_unused_extraction_capacity(self):
        learner = AdaptiveThreadAllocator()
        plan = learner.recommend(12, (.03, .02, .1), (1, 1), extract_backlog=24,
                                 stitch_waiting=5, buffer_depth=0, buffer_target=2)
        self.assertEqual(plan[:2], (2, 1))
        self.assertEqual(plan.reason, 'upstream-starved')

    def test_input_waiting_does_not_need_more_stitch_workers(self):
        learner = AdaptiveThreadAllocator()
        plan = learner.recommend(4, (.2, .01, .1), (1, 3), extract_backlog=24,
                                 stitch_waiting=5, buffer_depth=0)
        self.assertEqual(plan[:2], (2, 2))

    def test_display_bottleneck_does_not_shrink_busy_pipeline(self):
        learner = AdaptiveThreadAllocator()
        for _ in range(4):
            learner.observe((3, 1), .01, .01, .2)
        plan = learner.recommend(12, (.01, .01, .2), (3, 1), extract_backlog=24,
                                 buffer_depth=3, buffer_target=2)
        self.assertEqual(plan[:2], (3, 1))
        self.assertEqual(plan.reason, 'keep-buffer-capacity')

    def test_ready_backlog_wakes_stitch_capacity(self):
        learner = AdaptiveThreadAllocator()
        plan = learner.recommend(12, (.01, .03, .1), (1, 1), stitch_ready=6, buffer_depth=0)
        self.assertEqual(plan[:2], (1, 2))

    def test_budget_two_always_has_one_worker_per_stage(self):
        self.assertEqual(optimize_thread_allocation(2, 100, .001, .001)[:2], (1, 1))

    def test_works_for_varied_stream_counts_and_tile_costs(self):
        for videos in (1, 2, 24, 64, 100):
            for tiles in (1, 4, 100):
                for budget in (2, 4, 12, 32):
                    with self.subTest(videos=videos, tiles=tiles, budget=budget):
                        plan = optimize_thread_allocation(budget, videos * .01, tiles * .005, .002)
                        self.assertGreaterEqual(plan.extract, 1)
                        self.assertGreaterEqual(plan.stitch, 1)
                        self.assertLessEqual(plan.extract + plan.stitch, budget)
                        self.assertGreaterEqual(plan.period, .002)

    def test_increasing_composition_cost_changes_optimum(self):
        a = optimize_thread_allocation(12, .72, .01, .001)
        b = optimize_thread_allocation(12, .72, 5, .001)
        self.assertGreater(a.extract, b.extract)
        self.assertLess(a.stitch, b.stitch)

    def test_invalid_inputs(self):
        for costs in ((float('nan'), 1, 1), (1, float('inf'), 1), (-1, 1, 1)):
            with self.assertRaises(ValueError):
                optimize_thread_allocation(4, *costs)
        with self.assertRaises(ValueError):
            optimize_thread_allocation(1, 1, 1, 1)
        with self.assertRaises(ValueError):
            optimize_thread_allocation(4, 1, 1, 1, stitch_serial=1.1)

    def test_fit_detects_no_composition_scaling(self):
        learner = AdaptiveThreadAllocator()
        learner.observe((3, 1), .02, .1, .001)
        learner.observe((8, 4), .02, .4, .001)
        self.assertAlmostEqual(learner._serial_fraction(1), 1)
        plan = learner.recommend(12, (.02, .4, .001), (8, 4), allow_probe=False)
        self.assertEqual(plan[:2], (1, 1))

    def test_regressing_trial_rolls_back_and_is_not_immediately_repeated(self):
        learner = AdaptiveThreadAllocator()
        source, target = (2, 2), (3, 1)
        learner.observe(source, .06, .02, .001)
        self.assertEqual(learner.recommend(4, (.06, .02, .001), source)[:2], target)
        learner.applied(source, target)
        for _ in range(3):
            learner.observe(target, .3, .2, .001)
        plan = learner.recommend(4, (.3, .2, .001), target)
        self.assertEqual(plan[:2], source)
        self.assertEqual(plan.reason, 'rollback')
        learner.applied(target, source)
        self.assertNotEqual(learner.recommend(4, (.06, .02, .001), source)[:2], target)

    def test_trial_requires_multiple_fresh_measurements(self):
        learner = AdaptiveThreadAllocator()
        learner.observe((2, 2), .06, .02, .001)
        learner.applied((2, 2), (3, 1))
        learner.observe((3, 1), .06, .02, .001)
        plan = learner.recommend(4, (.06, .02, .001), (3, 1))
        self.assertEqual(plan.reason, 'validate')
        self.assertEqual(plan[:2], (3, 1))

    def test_equal_costs_keep_the_current_smallest_plan(self):
        plan = optimize_thread_allocation(4, 0, 0, .01, current=(1, 1))
        self.assertEqual(plan[:2], (1, 1))

    def test_large_canvas_has_lower_memory_concurrency_limit(self):
        available = 4 * 1024 ** 3
        small = stitch_memory_limit(640 * 480, 640 * 480, available, 12)
        large = stitch_memory_limit(10800 * 10800, 24 * 1080 * 1080, available, 12)
        self.assertEqual(small, 12)
        self.assertEqual(large, 1)
        self.assertEqual(stitch_memory_limit(1, 1, None, 5), 5)

    def test_capacity_change_overrides_incomplete_trial(self):
        learner = AdaptiveThreadAllocator()
        learner.observe((3, 1), .01, .1, .001)
        learner.applied((3, 1), (1, 3))
        plan = learner.recommend(4, (.01, .1, .001), (1, 3), max_stitch_tasks=1)
        self.assertEqual(plan.stitch, 1)
        self.assertEqual(plan.reason, 'capacity')

    def test_saturation_learning_can_accept_a_successful_trial(self):
        learner = AdaptiveThreadAllocator()
        learner.observe((2, 2), .06, .02, .001)
        learner.applied((2, 2), (3, 1))
        for _ in range(3):
            learner.observe((3, 1), .06, .02, .001)
        plan = learner.recommend(4, (.06, .02, .001), (3, 1))
        self.assertEqual(plan[:2], (3, 1))
        self.assertIsNone(learner.trial)


if __name__ == '__main__':
    unittest.main()
