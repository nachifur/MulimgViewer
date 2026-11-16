"""Supply-rate pacing, cache deadlines, and dependency-aware ETA regressions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/mulimgviewer/src'))
from playback_pacer import PlaybackPacer, ProductionJob, completion_estimates, refill_guard


class PacerTests(unittest.TestCase):
    def test_refill_lead_starts_production_earlier_but_keeps_large_batches(self):
        self.assertEqual(refill_guard(2, 1, .001, 2.), 2)
        self.assertEqual(refill_guard(2, 2, .001, 2.), 2)
        self.assertEqual(refill_guard(2, 3, .5, 2.), 3)
        self.assertEqual(refill_guard(2, 10, .3, 2.), 7)
        self.assertEqual(refill_guard(2, 10, .001, 20.), 10)

    def test_completed_supply_uses_active_time_not_full_cache_idle(self):
        pacer = PlaybackPacer()
        pacer.request('c', [1, 2], (0, 2), 0, 1, 0.)
        pacer.publish('c', 1, 1.)
        pacer.publish('c', 2, 2.)
        self.assertEqual(pacer.period, 1.)
        pacer.request('c', [3, 4], (0, 4), 2, 1, 100.)
        pacer.publish('c', 3, 101.)
        pacer.publish('c', 4, 102.)
        self.assertEqual(pacer.period, 1.)

    def test_reconcile_completed_pending_pages_does_not_count_full_cache_idle(self):
        pacer = PlaybackPacer()
        pacer.request('c',[1,2],(0,2),0,1,0.)
        pacer.publish('c',1,1.)
        # Reconcile a page already completed before a prior registration.
        pacer.request('c',[],(0,2),0,1,2.)
        self.assertFalse(pacer.pending)
        pacer.request('c',[3,4],(2,4),2,1,100.)
        pacer.publish('c',3,101.)
        pacer.publish('c',4,102.)
        self.assertEqual(pacer.period,1.)

    def test_first_hole_deadline_slows_before_cached_frames_are_exhausted(self):
        pacer = PlaybackPacer()
        interval, info = pacer.recommend('c', 0., buffered=2, target_buffer=2,
            remaining=100, manual=.01, display_cost=.02, fallback_period=.05, next_eta=3.)
        self.assertGreaterEqual(interval * 3, 3.)
        self.assertEqual(info['reason'], 'buffer-deadline')
        self.assertGreater(interval, .05)

    def test_recovery_does_not_add_a_speed_limit_beyond_real_supply(self):
        pacer = PlaybackPacer()
        first, _ = pacer.recommend('c', 0., 0, 2, 100, .001, .01, 1.)
        faster, _ = pacer.recommend('c', 1., 6, 2, 100, .001, .01, .1)
        self.assertAlmostEqual(faster, .025)
        slower, _ = pacer.recommend('c', 2., 1, 2, 100, .001, .01, .1, 10.)
        self.assertGreaterEqual(slower, 5.)

    def test_ready_stock_funds_speed_but_does_not_ignore_deadline(self):
        pacer = PlaybackPacer()
        args = dict(context='c', now=0., target_buffer=2, remaining=100,
                    manual=.001, display_cost=.01, fallback_period=1.)
        empty, _ = pacer.recommend(buffered=0, **args)
        stocked, _ = pacer.recommend(buffered=2, **args)
        self.assertEqual(empty, 1.)
        self.assertEqual(stocked, .5)
        guarded, _ = pacer.recommend(buffered=2, next_eta=2.4, **args)
        self.assertAlmostEqual(guarded, .8)

    def test_startup_cost_fades_without_double_smoothing(self):
        p=PlaybackPacer();p.request('c',[1,2,3,4],(0,4),0,1,0.)
        p.publish('c',1,7.);p.publish('c',2,8.)
        self.assertEqual(p.period,4.)
        p.publish('c',3,9.);p.publish('c',4,10.)
        self.assertEqual(p.period,2.)  # (8*.5 + 2)/(2*.5 + 2)
        interval,info=p.recommend('c',10.,0,2,100,.001,.01,99.)
        self.assertEqual(interval,2.)  # Old startup delay is not a recurring deadline.

    def test_unfinished_active_group_detects_supply_loss_before_buffer_runs_out(self):
        p=PlaybackPacer();p.request('c',range(1,9),(0,8),0,1,0.)
        p.publish('c',1,1.);p.publish('c',2,2.)
        interval,info=p.recommend('c',8.,0,2,100,.001,.01,.001,production_active=True)
        self.assertEqual(interval,6.)
        self.assertEqual(info['production_period'],6.)
        idle,_=p.recommend('c',8.,0,2,100,.001,.01,.001,production_active=False)
        self.assertEqual(idle,1.)

    def test_manual_floor_and_all_ready_end_of_video(self):
        pacer = PlaybackPacer()
        interval, _ = pacer.recommend('c', 0., 1, 2, 100, 2., .01, .1, 1.)
        self.assertEqual(interval, 2.)
        interval, info = pacer.recommend('c', 1., 3, 2, 3, .1, .02, 99., 99.)
        self.assertEqual(interval, .1)
        self.assertEqual(info['reason'], 'all-ready')

    def test_reverse_and_stale_generation_do_not_mix_samples(self):
        pacer = PlaybackPacer()
        pacer.request(('c', -1), [9, 8], (7, 10), 10, -1, 0.)
        pacer.publish(('c', -1), 9, 1.)
        pacer.publish(('c', -1), 8, 2.)
        self.assertEqual(pacer.period, 1.)
        pacer.request(('new', 1), [11, 12], (10, 12), 10, 1, 3.)
        pacer.publish(('c', -1), 11, 4.)
        self.assertIsNone(pacer.period)
        self.assertEqual(pacer.pending, {11, 12})

    def test_burst_interarrival_is_not_mistaken_for_sustained_rate(self):
        pacer = PlaybackPacer()
        pacer.request('c', [1, 2, 3, 4], (0, 4), 0, 1, 0.)
        for batch in range(1, 5):
            pacer.publish('c', batch, 2. + batch*.01)
        self.assertGreater(pacer.period, .1)  # A 10ms burst is not a 100 FPS supply.


class EtaTests(unittest.TestCase):
    def test_queue_waves_and_raw_dependencies_are_included(self):
        raw = [ProductionJob('a', 0., 0., 2.), ProductionJob('b', .1, None, 1.)]
        inputs = completion_estimates(raw, 1, .5)
        self.assertEqual(inputs, dict(a=1.5, b=2.5))
        stitched = [ProductionJob('x', 0., .4, 1.), ProductionJob('y', .2, None, .5, ('b',))]
        outputs = completion_estimates(stitched, 1, .5, inputs)
        self.assertEqual(outputs['y'], 3.)
        inputs = completion_estimates(raw, 2, .5)
        self.assertEqual(completion_estimates(stitched, 1, .5, inputs)['y'], 1.5)

    def test_overdue_running_work_does_not_have_zero_eta(self):
        result = completion_estimates([ProductionJob('a', 0., 0., 1.)], 1, 4.)
        self.assertGreaterEqual(result['a'], .8)


if __name__ == '__main__':
    unittest.main()
