"""Measured concurrency search must not confuse stock consumption with supply."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/mulimgviewer/src'))
from admission_optimizer import AdaptiveAdmissionBudget


class AdmissionTests(unittest.TestCase):
    def simulate(self,curve,frames=200):
        tuner=AdaptiveAdmissionBudget(phase_frames=4)
        tuner.configure(22,'scene',warmup=0)
        now=0.
        for produced in range(1,frames+1):
            now += curve(tuner.limit)
            tuner.observe(now,produced,buffered=6)
            self.assertGreaterEqual(tuner.limit,11)
            self.assertLessEqual(tuner.limit,22)
        return tuner

    def test_contention_curve_converges_to_faster_lower_concurrency(self):
        tuner=self.simulate(lambda n:.1+.001*(n-12)**2)
        self.assertEqual(tuner.best,12)
        self.assertEqual(tuner.limit,12)

    def test_resume_excludes_pause_duration_and_rolls_back_unfinished_probe(self):
        tuner=AdaptiveAdmissionBudget(4)
        tuner.configure(22,'scene',warmup=0)
        for i in range(5):tuner.observe(i*.1,i,6)
        self.assertEqual(tuner.limit,16)
        tuner.restart_observation()
        self.assertEqual(tuner.limit,22)
        self.assertIsNone(tuner.start)
        for i in range(7):tuner.observe(1000+i*.1,5+i,6)
        self.assertAlmostEqual(tuner.best_period,.1)

    def test_scalable_work_stays_at_full_budget(self):
        tuner=self.simulate(lambda n:1/n)
        self.assertEqual(tuner.best,22)

    def test_bad_neighbor_does_not_hide_faster_lower_concurrency(self):
        tuner=self.simulate(lambda n:.1 if n<=12 else (.2 if n==22 else .3),frames=300)
        self.assertLessEqual(tuner.best,12)
        self.assertTrue(any(n<=12 for n,_,_ in tuner.history))

    def test_cached_stock_cannot_be_mistaken_for_fast_production(self):
        tuner=AdaptiveAdmissionBudget(4)
        tuner.configure(22,'scene',warmup=0)
        for i in range(20):tuner.observe(i*.001,0,6)
        self.assertEqual(tuner.limit,22)
        self.assertIsNone(tuner.best_period)

    def test_user_interval_does_not_trigger_resource_search(self):
        tuner=AdaptiveAdmissionBudget(4)
        tuner.configure(22,'scene',warmup=0)
        for i in range(20):tuner.observe(i, i,6,manual_limited=True)
        self.assertEqual(tuner.limit,22)
        self.assertFalse(tuner.history)

    def test_scene_or_budget_change_discards_old_measurements(self):
        tuner=self.simulate(lambda n:.1+.001*(n-12)**2)
        self.assertEqual(tuner.configure(4,'other',warmup=0),4)
        self.assertIsNone(tuner.best_period)
        self.assertFalse(tuner.history)

    def test_buffer_starvation_rolls_back_without_waiting_for_full_trial(self):
        tuner=AdaptiveAdmissionBudget(4)
        tuner.configure(22,'scene',warmup=0)
        for i in range(5):tuner.observe(i*.1,i,6)
        self.assertEqual(tuner.limit,16)
        tuner.observe(.5,5,6)
        tuner.observe(.6,6,6)
        tuner.observe(.7,7,6)
        tuner.observe(1.7,8,0)
        tuner.observe(2.7,9,0)
        self.assertEqual(tuner.limit,22)
        self.assertEqual(tuner.reason,'buffer-rollback')


if __name__=='__main__':unittest.main()
