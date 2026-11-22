"""Exact four-stage minimax model and work-conserving shared admission."""
import itertools
import random
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.stage_allocator import allocate_stages
from mulimgviewer.src.custom_pipeline import WorkBudget
from mulimgviewer.src.pipeline_executor import PipelineWorkers


class StageAllocatorTests(unittest.TestCase):
    def test_queued_decoder_runs_follow_seek_and_reverse_without_preempting_codec(self):
        group = PipelineWorkers(1, 1)
        extract, stitch = group.stages
        entered, release = threading.Event(), threading.Event()
        order = []
        try:
            group.set_playback_focus(10, 1, 3)
            active = extract.submit(lambda: (entered.set(), release.wait(5)), resource_key='source')
            self.assertTrue(entered.wait(2))
            pending = [extract.submit(order.append, span, page_span=span, resource_key='source')
                       for span in [(11, 12), (32, 35), (30, 31), (27, 29)]]
            group.set_playback_focus(30, -1, 3)
            release.set()
            active.result(timeout=3)
            for future in pending:
                future.result(timeout=3)
            self.assertEqual(order, [(30, 31), (27, 29), (11, 12), (32, 35)])
        finally:
            release.set()
            extract.shutdown()
            stitch.shutdown()

    def test_last_slot_prefers_the_stage_inside_its_own_lookahead(self):
        for raw_horizon, expected in ((12, ['raw', 'stitch']), (3, ['stitch', 'raw'])):
            with self.subTest(raw_horizon=raw_horizon):
                group = PipelineWorkers(1, 1)
                extract, stitch = group.stages
                order = []
                try:
                    group.set_playback_focus(0, 1, 8, raw_horizon)
                    self.assertTrue(group.reserve_downstream(2, 0))
                    # Both have work. With a deep raw target, prioritise page
                    # 10 over the speculative stitch on page 9. With a small
                    # raw target, the finished page nearest playback wins.
                    a = stitch.submit(order.append, 'stitch', page_span=(9, 9))
                    b = extract.submit(order.append, 'raw', page_span=(10, 10))
                    group.reserve_downstream(-1, 0)
                    a.result(timeout=3)
                    b.result(timeout=3)
                    self.assertEqual(order, expected)
                finally:
                    group.reserve_downstream(-group.downstream_active, 0)
                    extract.shutdown()
                    stitch.shutdown()

    def test_integer_optimum_matches_exhaustive_search(self):
        randomizer=random.Random(9)
        for _ in range(30):
            budget=randomizer.randint(4,9)
            work=[randomizer.uniform(.1,12) for _ in range(4)]
            caps=[randomizer.randint(1,budget) for _ in range(4)]
            costs=[randomizer.randint(1,4) for _ in range(4)]
            memory=randomizer.randint(sum(costs),budget*max(costs))
            feasible=[max(w/n for w,n in zip(work,allocation))
                for allocation in itertools.product(*(range(1,cap+1) for cap in caps))
                if sum(allocation)<=budget and sum(n*m for n,m in zip(allocation,costs))<=memory]
            result=allocate_stages(budget,work,caps,costs,memory)
            self.assertEqual(result.reason,'minimax')
            self.assertAlmostEqual(result.period,min(feasible),places=9)
            self.assertLessEqual(sum(result.targets),budget)
            self.assertLessEqual(sum(n*m for n,m in zip(result.targets,costs)),memory)

    def test_gpu_cap_and_inactive_stages_are_respected(self):
        result=allocate_stages(16,(3,50,4,1),(16,1,16,16))
        self.assertEqual(result.targets[1],1)
        self.assertEqual(result.period,50)
        image=allocate_stages(8,(0,12,3,1),(0,8,8,8))
        self.assertEqual(image.targets[0],0)
        small=allocate_stages(1,(1,3,2))
        self.assertEqual(small.reason,'time-share')
        self.assertEqual(sum(small.targets),1)

    def test_serial_algorithm_does_not_occupy_other_algorithms_workers(self):
        from mulimgviewer.src.custom_workers import ImageWorkers
        pool=ImageWorkers(2);entered=threading.Event();release=threading.Event();other=threading.Event()
        try:
            first=pool.submit(lambda:(entered.set(),release.wait(3)),resource_key='A',max_concurrency=1)
            self.assertTrue(entered.wait(1))
            waiting=pool.submit(lambda:None,resource_key='A',max_concurrency=1)
            independent=pool.submit(other.set,resource_key='B',max_concurrency=1)
            self.assertTrue(other.wait(1))
            self.assertFalse(waiting.done())
            release.set()
            first.result(2);waiting.result(2);independent.result(2)
        finally:
            release.set();pool.shutdown(wait=True,cancel_futures=True)

    def test_memory_blocked_head_does_not_idle_fitting_work(self):
        budget=WorkBudget();budget.configure(3,100)
        def work(size):
            with budget.acquire(size):return size
        with ThreadPoolExecutor(2) as pool:
            with budget.acquire(30):
                big=pool.submit(work,80)
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    with budget.condition:
                        if budget.waiting:break
                    time.sleep(.001)
                small=pool.submit(work,20)
                self.assertEqual(small.result(timeout=2),20)
                self.assertFalse(big.done())
            self.assertEqual(big.result(timeout=2),80)
        self.assertEqual(budget.bytes,0)

    def test_one_pane_reuses_mosaic_without_reserving_a_compose_stage(self):
        import json,tempfile
        from types import SimpleNamespace
        from mulimgviewer.src.custom_pipeline import CustomPipeline
        params=[None]*41;params[32]=True;params[36]=False;params[37]=0
        params[38]=False;params[39]='1,1';params[40]=False
        registry=(('Example','/example/main.py','',json.dumps(dict(device='cpu'))),)
        manager=SimpleNamespace(layout_params=params,_custom_algorithm_registry=registry)
        with tempfile.TemporaryDirectory() as directory:
            stage=CustomPipeline(Path(directory)/'work')
            try:
                stage.set_window('image','epoch',(0,4),0)
                stage.configure_stages(manager)
                self.assertEqual(stage.budget.model_snapshot()['caps'][2],0)
                params[39]='2,1'
                stage.configure_stages(manager)
                self.assertGreater(stage.budget.model_snapshot()['caps'][2],0)
                with stage.budget.condition:stage.budget.page_work[0]=100.
                stage.set_window('image','new-input',(0,4),0)
                stage.configure_stages(manager)
                self.assertEqual(stage.budget.model_snapshot()['work'],{})
            finally:
                stage.close();stage.cleanup_future.result(timeout=3)

    def test_service_cost_is_normalized_to_one_final_page(self):
        budget=WorkBudget();budget.configure(4,100)
        with patch('mulimgviewer.src.custom_pipeline.time.perf_counter',side_effect=[10.,12.,12.]):
            with budget.acquire(10,units=.25):pass
        self.assertEqual(budget.model_snapshot()['work'][0],8.)

    def test_metadata_coordinators_do_not_deadlock_after_downgrade(self):
        group=PipelineWorkers(1,3);group.configure(1,3,100,(10,50),total_budget=4)
        budget=WorkBudget();budget.configure(4,100,group.downstream_capacity,group.reserve_downstream)
        gate=threading.Event();entered=threading.Event()
        def coordinate():
            entered.set();gate.wait(3)
            with budget.acquire(10):time.sleep(.01)
        jobs=[]
        try:
            jobs=[group.stages[1].submit(coordinate,coordinator=True) for _ in range(3)]
            self.assertTrue(entered.wait(1))
            with group.lock:
                self.assertEqual(group.active[1],0)
                self.assertEqual(group.stage_bytes[1],0)
            group.configure(1,1,50,(10,50),total_budget=2)
            budget.configure(2,50,group.downstream_capacity,group.reserve_downstream)
            gate.set()
            for job in jobs:job.result(timeout=3)
            self.assertEqual(group.downstream_active,0)
            self.assertEqual(group.downstream_bytes,0)
        finally:
            gate.set()
            for stage in group.stages:stage.shutdown()


if __name__=='__main__':unittest.main()
