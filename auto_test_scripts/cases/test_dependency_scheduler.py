"""Ready-only execution, failure drainage, cooperative shutdown and fairness."""
import sys
import threading
import subprocess
import textwrap
import unittest
from concurrent.futures import Future,ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.dependency_scheduler import DependencyScheduler,gather
from mulimgviewer.src.pipeline_executor import PipelineWorkers


class DependencyTests(unittest.TestCase):
    def setUp(self):self.scheduler=DependencyScheduler()
    def tearDown(self):self.scheduler.shutdown(wait_for_tasks=True)

    def test_waiting_parent_does_not_occupy_single_compute_worker(self):
        with ThreadPoolExecutor(1) as compute:
            started=threading.Event();dependency=Future()
            def page():
                started.set()
                yield dependency
                return (yield compute.submit(lambda:42))
            result=self.scheduler.start(page)
            self.assertTrue(started.wait(1))
            self.assertEqual(compute.submit(lambda:7).result(timeout=1),7)
            dependency.set_result(True)
            self.assertEqual(result.result(timeout=2),42)

    def test_many_waiting_nodes_do_not_block_the_ready_producer(self):
        dependency=Future()
        with ThreadPoolExecutor(1) as compute:
            def page(index):
                yield dependency
                return (yield compute.submit(lambda:index))
            pages=[self.scheduler.start(page,index) for index in range(30)]
            compute.submit(lambda:dependency.set_result(True)).result(timeout=1)
            self.assertEqual([page.result(timeout=3) for page in pages],list(range(30)))

    def test_failure_waits_for_sibling_writers(self):
        failed=Future();writer=Future()
        combined=gather([failed,writer])
        failed.set_exception(ValueError('algorithm failed'))
        self.assertFalse(combined.done())
        writer.set_result('writer settled')
        with self.assertRaisesRegex(ValueError,'algorithm failed'):combined.result()

    def test_shutdown_resumes_lease_cleanup_instead_of_abandoning_it(self):
        entered=threading.Event();cleaned=threading.Event();dependency=Future()
        def page():
            try:
                entered.set();yield dependency
            finally:cleaned.set()
        result=self.scheduler.start(page)
        self.assertTrue(entered.wait(1))
        self.assertFalse(result.cancel())
        self.scheduler.shutdown()
        self.assertFalse(cleaned.is_set())
        with patch.object(self.scheduler.dispatcher,'submit',side_effect=RuntimeError('interpreter shutdown')):
            dependency.set_result(None)
        result.result(timeout=2)
        self.assertTrue(cleaned.is_set())

    def test_ready_only_submission_and_future_flattening(self):
        dependency=Future();entered=threading.Event()
        with ThreadPoolExecutor(1) as compute:
            def build():
                entered.set();child=Future();child.set_result(5);return child
            result=self.scheduler.submit(compute,build,dependencies=(dependency,))
            self.assertFalse(entered.wait(.02))
            dependency.set_result(True)
            self.assertEqual(result.result(timeout=2),5)

    def test_interpreter_exit_drains_queued_continuations(self):
        script=textwrap.dedent("""
            import sys,time
            from concurrent.futures import ThreadPoolExecutor
            sys.path.insert(0,'src')
            from mulimgviewer.src.dependency_scheduler import DependencyScheduler
            scheduler=DependencyScheduler()
            pool=ThreadPoolExecutor(1)
            dependency=pool.submit(lambda:time.sleep(.05))
            def page():
                yield dependency
                return 1
            pages=[scheduler.start(page) for _ in range(40)]
            scheduler.shutdown()
            pool.shutdown(wait=False)
        """)
        result=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).resolve().parents[2],
            capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('Traceback',result.stderr)

    def test_ready_composition_can_borrow_above_legacy_coordinator_quota(self):
        with patch('mulimgviewer.src.pipeline_executor.os.cpu_count',return_value=2):
            group=PipelineWorkers(3,1)
        group.configure(3,1,total_budget=4)
        gate=threading.Event();all_started=threading.Event();lock=threading.Lock();started=[]
        def compose():
            with lock:
                started.append(True)
                if len(started)==4:all_started.set()
            gate.wait(3)
        try:
            jobs=[group.stages[1].submit(compose,coordinator='ready') for _ in range(4)]
            self.assertTrue(all_started.wait(1))
            with group.lock:self.assertEqual(group.active,[0,0])
            gate.set()
            for job in jobs:job.result(timeout=2)
        finally:
            gate.set()
            for stage in group.stages:stage.shutdown()

    def test_ready_downstream_preserves_cpu_and_ram_from_decode_lending(self):
        group=PipelineWorkers(1,3)
        group.configure(1,3,memory_budget=100,costs=(10,10),total_budget=4)
        entered=threading.Event();release=threading.Event()
        try:
            group.adjust_downstream_waiting('processed-page',60,lambda:None)
            jobs=[group.stages[0].submit(lambda:(entered.set(),release.wait(3))) for _ in range(4)]
            self.assertTrue(entered.wait(1))
            with group.lock:self.assertEqual(group.active[0],1)
            self.assertTrue(group.reserve_downstream(1,60))
            group.adjust_downstream_waiting('processed-page')
            with group.lock:self.assertLessEqual(group._cpu_used(),4)
            group.reserve_downstream(-1,-60)
            release.set()
            for job in jobs:job.result(timeout=3)
        finally:
            release.set()
            for stage in group.stages:stage.shutdown()


if __name__=='__main__':unittest.main()
