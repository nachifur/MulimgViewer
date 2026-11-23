"""Deterministic regressions for measured maximum-throughput playback."""
import threading
import unittest
import weakref
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch, Mock

from test_video_cache import PerformanceMonitor, SharedConfig, VideoManager


class VideoIntervalTests(unittest.TestCase):
    def test_incremental_raw_page_eta_does_not_wait_for_outer_window_job(self):
        self.vm._window_token = 'page-eta'
        parent = Future()
        parent.video_timing = dict(queued_at=0.,started_at=0.,expected_seconds=100.,
                                  page_period=2.,page_ready_local=50,page_ready_at=10.)
        dependency = Future()
        dependency.video_parent = parent
        dependency.video_local_batch = 51
        target = Future()
        target.video_dependencies = (dependency,)
        target.video_timing = dict(queued_at=0.,started_at=None,expected_seconds=.1)
        self.vm._pending_extract = {(0,51):parent}
        self.vm._window_stitches = {('page-eta',51):target}
        self.assertAlmostEqual(self.vm._next_stitch_eta(51,11.),1.1)
        dependency.set_result(True)
        self.assertAlmostEqual(self.vm._next_stitch_eta(51,11.),.1)

    def test_first_page_eta_excludes_the_unpublished_tail_before_first_progress(self):
        parent, dependency, target = Future(), Future(), Future()
        parent.video_timing = dict(queued_at=0., first_local=50, last_local=59,
                                   started_at=None, expected_seconds=10.)
        dependency.video_parent = parent
        dependency.video_local_batch = 51
        target.video_dependencies = (dependency,)
        target.video_timing = dict(queued_at=0., expected_seconds=.1)
        self.vm._window_token = 'window'
        self.vm._pending_extract = {(0, 50): parent}
        self.vm._window_stitches = {('window', 51): target}
        self.assertAlmostEqual(self.vm._next_stitch_eta(51, 0.), 2.1)

    def test_queued_outer_work_does_not_delay_next_page_forecast(self):
        outer, target = Future(), Future()
        outer.video_timing = dict(queued_at=0., expected_seconds=30.)
        target.video_timing = dict(queued_at=1., expected_seconds=.1)
        self.vm._window_token = 'priority'
        self.vm._window_stitches = {('priority', 90): outer, ('priority', 51): target}
        self.assertAlmostEqual(self.vm._next_stitch_eta(51, 2.), .1)
        outer.video_timing['started_at'] = 1.
        self.assertAlmostEqual(self.vm._next_stitch_eta(51, 2.), 29.1)

    def test_full_ready_buffer_uses_measured_supply_until_stock_runs_low(self):
        from playback_policy import PlaybackPacer
        self.vm._window_token = 'stock'
        self.vm._pacing_model_period = .1
        pacer = self.vm._playback_pacer = PlaybackPacer()
        context = self.vm._pacing_context()
        pacer.request(context, [49, 50], (49, 60), 48, 1, 0.)
        pacer.publish(context, 49, .1)
        pacer.publish(context, 50, .2)
        self.cfg.cache_num = 8
        self.cfg.cache_img = [None] * 120
        self.cfg.cache_img[51:59] = [True] * 8
        with patch.object(self.vm, '_next_stitch_eta', return_value=9.) as estimate:
            self.vm._refresh_playback_interval()
            estimate.assert_not_called()
            self.assertAlmostEqual(self.cfg.interval_recommend, .05)
            self.cfg.batch_idx += 4
            self.vm._refresh_playback_interval()
            estimate.assert_called_once()
            self.assertAlmostEqual(self.cfg.interval_recommend, 1.8)

    def test_custom_eta_uses_output_supply_instead_of_parent_wait_latency(self):
        from playback_policy import PlaybackPacer
        self.vm._window_token='c'
        self.cfg.play_direction=1
        params=[None]*41;params[32]=True;params[38]=False
        self.vm._render_snapshot=(SimpleNamespace(layout_params=params),[],True)
        p=self.vm._playback_pacer=PlaybackPacer()
        p.request(('c',1),[51,52,53,54],(49,54),50,1,0.)
        p.publish(('c',1),51,1.);p.publish(('c',1),52,2.)
        self.cfg.batch_idx=52
        target=Future();target.video_batch=53;target.video_dependencies=()
        target.video_timing=dict(queued_at=0.,started_at=0.,expected_seconds=100.)
        self.vm._window_stitches={('c',53):target};self.vm._pending_extract={}
        self.assertEqual(self.vm._next_stitch_eta(53,2.),1.)
        raw=Future();raw.video_timing=dict(queued_at=0.,started_at=0.,expected_seconds=10.)
        target.video_dependencies=(raw,);self.vm._pending_extract={(0,53):raw}
        self.assertEqual(self.vm._next_stitch_eta(53,2.),8.)

        # The original-only view uses the same dependency scheduler. Its
        # page coordinator can be queued for far longer than actual rendering.
        params[32] = False
        self.vm._render_snapshot[0]._custom_algorithm_registry = ()
        self.owner.image_pipeline = SimpleNamespace(processing=object())
        self.assertEqual(self.vm._next_stitch_eta(53, 2.), 8.)
        raw.set_result(True)
        self.assertEqual(self.vm._next_stitch_eta(53, 2.), 1.)

    def test_full_output_and_low_raw_inventory_trigger_extraction_before_normal_evaluation(self):
        self.cfg.thread = 12
        self.cfg.video_num_list = [1000] * 24
        self.cfg.cache_multiplier = 3
        self.cfg.cache_img = [None] * 120
        self.cfg.cache_img[51:54] = [True] * 3
        self.vm._extract_threads, self.vm._stitch_threads = 2, 10
        self.vm._stitch_window = (44, 56)
        self.vm._raw_ready_batches = set()
        self.vm._pending_extract = {(v, 54): Future() for v in range(24)}
        self.vm._cooldown_deadline = float('inf')
        self.samples(extract=(.02,) * 24, stitch=.1)
        self.vm.perf_monitor.mark_evaluated()
        with patch.object(self.vm, '_request_thread_plan') as replan, \
             patch.object(self.vm, '_list_missing_range', side_effect=AssertionError('GUI filesystem scan')):
            self.vm._maybe_evaluate_performance()
        replan.assert_called_once_with(4, 8)
        self.assertEqual(self.cfg.thread_allocation_recommend['reason'], 'raw-buffer-low')
        self.assertEqual(self.cfg.thread_allocation_recommend['raw_buffer'], 0)

    def test_low_output_and_ready_raw_inventory_trigger_composition(self):
        self.cfg.thread = 12
        self.cfg.video_num_list = [1000] * 24
        self.cfg.cache_multiplier = 3
        self.cfg.cache_img = [None] * 120
        self.cfg.cache_img[51] = True
        self.vm._extract_threads, self.vm._stitch_threads = 10, 2
        self.vm._stitch_window = (44, 56)
        self.vm._raw_ready_batches = {(v, b) for v in range(24) for b in range(52, 57)}
        self.vm._pending_extract.clear()
        for batch in range(52, 57):
            future = Future()
            future.video_batch = batch
            future.video_waiting_for_extract = False
            self.vm._window_stitches[batch] = future
        self.vm._cooldown_deadline = float('inf')
        self.samples(extract=(.02,) * 24, stitch=.1)
        self.vm.perf_monitor.mark_evaluated()
        with patch.object(self.vm, '_request_thread_plan') as replan:
            self.vm._maybe_evaluate_performance()
        replan.assert_called_once_with(8, 4)
        self.assertEqual(self.cfg.thread_allocation_recommend['reason'], 'stitch-buffer-low')
        self.assertEqual(self.cfg.thread_allocation_recommend['raw_buffer'], 5)

    def test_ready_raw_reserve_bypasses_normal_evaluation_and_resize_cooldowns(self):
        self.cfg.thread = 12
        self.cfg.cache_multiplier = 3
        self.cfg.video_num_list = [1000] * 24
        self.cfg.cache_img = [None] * 120
        self.vm._extract_threads, self.vm._stitch_threads = 11, 1
        self.vm._pending_extract.clear()
        self.vm._cooldown_deadline = float('inf')
        for index in range(6):
            future = Future()
            future.video_batch = 51 + index
            future.video_waiting_for_extract = False
            self.vm._window_stitches[index] = future
        self.samples(extract=(.03,) * 24, stitch=.2)
        self.vm.perf_monitor.mark_evaluated()
        self.assertFalse(self.vm.perf_monitor.should_evaluate())
        with patch.object(self.vm, '_request_thread_plan') as replan:
            self.vm._maybe_evaluate_performance()
        replan.assert_called_once_with(10, 2)

    def setUp(self):
        self.owner = SimpleNamespace()
        self.vm = VideoManager.__new__(VideoManager)
        self.vm._owner = lambda: self.owner
        self.vm.shared_config = self.cfg = SharedConfig()
        self.cfg.video_mode = self.cfg.is_playing = True
        self.cfg.video_num_list = [1000, 1000]
        self.cfg.batch_idx = 50
        self.cfg.cache_img = [True] * 120
        self.vm.perf_monitor = PerformanceMonitor()
        self.vm._extract_threads, self.vm._stitch_threads = 3, 1
        self.vm._cache_guard = threading.RLock()
        self.vm._pending_extract = {(0, 99): Future()}
        self.vm._window_stitches = {}
        self.vm._cooldown_deadline = 0

    def samples(self, extract=(0.03, 0.03), stitch=0.01, display=0.005):
        for _ in range(4):
            for vid, cost in enumerate(extract):
                self.vm.perf_monitor.record_extract(cost * 20, 20, vid)
            self.vm.perf_monitor.record_stitch(stitch)
            self.vm.perf_monitor.record_display(display)

    def test_four_stage_model_normalizes_native_decoder_slot_work(self):
        params=[None]*41;params[32]=True;params[38]=False
        self.vm._render_snapshot=(SimpleNamespace(layout_params=params),[],True)
        self.cfg.real_video_path=['one.mp4'];self.cfg.parallel_to_sequential=False
        self.vm._extract_threads=6;self.vm._decoder_bank=SimpleNamespace(available=True)
        budget=Mock()
        budget.model_snapshot.return_value=dict(work={0:3.,1:.4,2:.1},memory={0:10,1:10,2:10},caps=(7,7,7))
        self.owner.image_pipeline=SimpleNamespace(processing=SimpleNamespace(budget=budget))
        solve=Mock(return_value=SimpleNamespace(reason='minimax',targets=(2,3,1,1),period=.5))
        with patch.object(self.vm,'_decoder_working_set',return_value=10), patch.object(self.vm,'_planning_memory_budget',return_value=1000), patch.dict(
                self.vm._four_stage_proposal.__globals__,allocate_stages=solve):
            proposal=self.vm._four_stage_proposal(.5,7,6,None)
            self.assertEqual(solve.call_args.args[1][0],3.)
            self.assertEqual((proposal.extract,proposal.stitch),(2,5))
            budget.set_target_capacity.assert_called_with(5)
            self.assertEqual(self.cfg.stage_allocation_target,dict(decode=2,process=3,stitch=1,compose=1))
            self.cfg.real_video_path=['one.mp4','two.mp4']
            self.vm._four_stage_proposal(.5,7,6,None)
            self.assertEqual(solve.call_args.args[1][0],1.5)

    def test_four_stage_feedback_can_rebalance_when_raw_buffer_is_critical(self):
        from playback_policy import ThreadAllocation
        self.cfg.thread=12;self.cfg.video_num_list=[1000]*24;self.cfg.cache_multiplier=3
        self.cfg.cache_img=[None]*120;self.cfg.cache_img[51:54]=[True]*3
        self.vm._extract_threads,self.vm._stitch_threads=2,10
        self.vm._stitch_window=(44,56);self.vm._raw_ready_batches=set()
        self.vm._pending_extract={(vid,54):Future() for vid in range(24)}
        self.vm._cooldown_deadline=float('inf')
        self.samples(extract=(.02,)*24,stitch=.1)
        self.vm.perf_monitor.mark_evaluated()
        with patch.object(self.vm,'_four_stage_proposal',return_value=ThreadAllocation(4,8,.1,'four-stage')),patch.object(self.vm,'_request_thread_plan') as replan:
            self.vm._maybe_evaluate_performance()
        replan.assert_called_once_with(4,8)
        self.assertEqual(self.cfg.thread_allocation_recommend['reason'],'four-stage')

    def test_batch_decoder_cost_is_normalized_per_video(self):
        self.samples()
        extract, stitch, display = self.vm.perf_monitor.stage_costs([0, 1])
        self.assertAlmostEqual(extract, 0.06)
        self.assertAlmostEqual(stitch, 0.01)
        self.assertAlmostEqual(display, 0.005)

    def test_manual_interval_is_preserved_across_auto_slowdown_and_recovery(self):
        self.cfg.manual_interval = 0.1
        self.cfg.interval = 0.1
        for recommendation, expected in [(0.05, 0.1), (0.1, 0.1), (0.3, 0.3), (0.08, 0.1)]:
            self.vm._apply_interval_recommendation(recommendation)
            self.assertEqual(self.cfg.interval, expected)
            self.assertEqual(self.cfg.manual_interval, 0.1)

    def test_recent_work_sets_source_order_and_predicts_different_run_lengths(self):
        monitor = self.vm.perf_monitor
        monitor.record_extract(2., batches=4, video_idx=0)
        monitor.record_extract(6., batches=4, video_idx=1)
        self.assertEqual(monitor.extraction_order({0: [2, 3], 1: [2, 3]}), [1, 0])
        self.assertAlmostEqual(monitor.extraction_estimate(1, 2), 3.)
        self.assertAlmostEqual(monitor.extraction_estimate(1, 1), 1.5)

    def test_measured_source_parallelism_accounts_for_a_slow_stream(self):
        monitor = PerformanceMonitor()
        streams = list(range(8))
        for vid in streams[:-1]:
            monitor.record_extract(.125, video_idx=vid)
        self.assertEqual(monitor.source_parallelism(streams, 6), 6)
        monitor.record_extract(1., video_idx=streams[-1])
        self.assertEqual(monitor.source_parallelism(streams, 6), 2)
        self.assertEqual(monitor.source_parallelism([7], 6), 6)

    def test_decoder_samples_are_weighted_by_output_batch_count(self):
        monitor = PerformanceMonitor()
        monitor.record_extract(0.1, 1, 0)
        monitor.record_extract(0.1, 10, 0)
        monitor.record_stitch(0.001)
        monitor.record_display(0.001)
        self.assertAlmostEqual(monitor.stage_costs([0])[0], 0.2 / 11)

    def test_automatically_speeds_up_below_fifty_milliseconds(self):
        self.samples()
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 0.021)

    def test_slows_down_for_combined_parallel_video_work(self):
        self.samples(extract=(0.12, 0.09))
        self.cfg.interval = 0.001
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 0.072)

    def test_display_cost_can_be_the_bottleneck(self):
        self.samples(display=0.08)
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 0.082)

    def test_empty_buffer_does_not_cause_speculative_speedup(self):
        self.samples()
        self.cfg.cache_img = [None] * 120
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 1.0)
        self.assertEqual(self.cfg.interval_recommend, 0.021)

    def test_reverse_buffer_counts_ready_frames_in_reverse(self):
        self.cfg.play_direction = -1
        self.cfg.cache_img[49] = None
        self.assertEqual(self.vm._compute_buffer_depth(), 0)
        self.cfg.cache_img[49] = True
        self.cfg.cache_img[47] = None
        self.assertEqual(self.vm._compute_buffer_depth(), 2)

    def test_cached_remaining_video_ignores_old_decoder_bottleneck(self):
        self.samples(extract=(10.0, 10.0), stitch=2.0)
        self.cfg.video_num_list = [60, 60]
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 0.006)

    def test_sequential_video_only_counts_the_active_stream(self):
        self.samples(extract=(10.0, 0.03))
        self.cfg.parallel_to_sequential = True
        self.cfg.batch_idx = 1050
        self.cfg.cache_img = [True] * 1120
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 0.011)

    def test_busy_pools_are_not_replaced_by_auto_tuning(self):
        self.samples(extract=(0.005, 0.005), stitch=0.09, display=0.001)
        with patch.object(self.vm, '_apply_thread_plan') as replan:
            self.vm._maybe_evaluate_performance(force=True)
        replan.assert_called_once_with(1, 3)
        self.assertEqual(self.cfg.interval, 0.092)

    def test_idle_pools_redistribute_the_full_budget(self):
        self.samples(extract=(0.005, 0.005), stitch=0.09, display=0.001)
        self.vm._pending_extract.clear()
        def apply(extract, stitch):
            self.vm._extract_threads, self.vm._stitch_threads = extract, stitch
        with patch.object(self.vm, '_apply_thread_plan', side_effect=apply) as replan:
            self.vm._maybe_evaluate_performance(force=True)
        replan.assert_called_once_with(1, 3)
        self.assertEqual(self.cfg.interval, 0.031)

    def test_throughput_plan_still_respects_real_display_service_time(self):
        self.samples(display=.5)
        self.vm._extract_threads, self.vm._stitch_threads = 1, 3
        self.vm._pending_extract.clear()
        def apply(extract, stitch):
            self.vm._extract_threads, self.vm._stitch_threads = extract, stitch
        with patch.object(self.vm, '_apply_thread_plan', side_effect=apply) as replan:
            self.vm._maybe_evaluate_performance(force=True)
        replan.assert_called_once_with(3, 1)
        self.assertEqual(self.cfg.interval, .510)

    def test_user_thread_budget_actually_reaches_the_pool_rebuilder(self):
        self.cfg.thread = 6
        with patch.object(self.vm, '_apply_thread_plan') as replan:
            self.vm._enforce_thread_budget()
        replan.assert_called_once_with(5, 1)
        self.assertEqual((self.vm._extract_threads, self.vm._stitch_threads), (3, 1))

    def test_pause_and_missing_samples_do_not_rewrite_interval(self):
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 1.0)
        self.samples()
        self.cfg.is_playing = False
        self.vm._maybe_evaluate_performance(force=True)
        self.assertEqual(self.cfg.interval, 1.0)

    def test_fps_records_completed_adjacent_frames_only(self):
        monitor = PerformanceMonitor()
        with patch('time.perf_counter', side_effect=[1.0, 1.02, 2.0, 2.02]):
            self.assertTrue(monitor.push_render_event(10))
            self.assertTrue(monitor.push_render_event(11))
            self.assertFalse(monitor.push_render_event(11))
            self.assertAlmostEqual(monitor.get_fps(), 50.0)
            monitor.push_render_event(30)
            self.assertEqual(monitor.get_fps(), 0.0)
            monitor.push_render_event(31)
            self.assertAlmostEqual(monitor.get_fps(), 50.0)

    def test_recommendation_does_not_overwrite_an_edited_field(self):
        self.owner.interval = SimpleNamespace(HasFocus=lambda: True)
        self.vm._apply_interval_recommendation(0.005)
        self.assertEqual(self.cfg.interval, 1.0)

    def test_measurements_from_different_allocations_are_not_mixed(self):
        monitor = PerformanceMonitor()
        monitor.record_display(.001)
        monitor.record_extract(.1, 1, 0, plan=(3, 1))
        monitor.record_stitch(.2, plan=(3, 1))
        monitor.record_extract(.3, 1, 0, plan=(1, 3))
        monitor.record_stitch(.6, plan=(1, 3))
        self.assertEqual(monitor.stage_costs([0], plan=(3, 1)), (.1, .2, .001))
        self.assertEqual(monitor.stage_costs([0], plan=(1, 3)), (.3, .6, .001))
        self.assertIsNone(monitor.stage_costs([0], plan=(2, 2)))


if __name__ == '__main__':
    unittest.main()
