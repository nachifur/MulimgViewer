"""Persistent workers with nonblocking, shared-budget stage admission."""
import os
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, wait


class PipelineWorkers:
    def __init__(self, extract, stitch):
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2), thread_name_prefix='video-work')
        self.limits = [extract, stitch]
        self.total_budget = extract + stitch
        self.active = [0, 0]
        self.keys = set()
        self.memory_budget, self.active_bytes = None, 0
        self.costs = [1, 1]
        self.queues = [deque(), deque()]
        self.closed = [False, False]
        self.handles = [set(), set()]
        self.stages = (StageExecutor(self, 0), StageExecutor(self, 1))

    def configure(self, extract, stitch, memory_budget=None, costs=(1, 1), total_budget=None):
        with self.lock:
            self.limits = [max(1, int(extract)), max(1, int(stitch))]
            self.total_budget = sum(self.limits) if total_budget is None else max(2,int(total_budget))
            self.memory_budget = memory_budget
            self.costs = [max(1, int(cost)) for cost in costs]
            self._dispatch()

    def downstream_capacity(self):
        """Child compute borrows only the lanes held by admitted parent pages.

        Parent jobs orchestrate/wait; counting each child against these same
        lanes avoids adding an independent second CPU or decode-memory budget.
        """
        with self.lock:
            lanes=max(1,min(self.active[1],max(1,self.total_budget-self.active[0])))
            memory=None if self.memory_budget is None else max(0,self.memory_budget-self.active[0]*self.costs[0])
            return lanes,memory

    def submit(self, stage, fn, args, kwargs, resource_key=None, cpu_cost=1):
        future = Future()
        with self.lock:
            if self.closed[stage]:
                raise RuntimeError('Cannot schedule work after shutdown')
            self.handles[stage].add(future)
            self.queues[stage].append((future, fn, args, kwargs, resource_key, max(1,int(cpu_cost))))
            self._dispatch()
        return future

    def _dispatch(self):
        # All calls hold the lock. Never invoke user Future callbacks here.
        while sum(self.active) < self.total_budget:
            chosen = None
            # First honor stage reservations. Then lend otherwise idle CPU
            # permits to runnable work, but NEVER lend unaccounted memory.
            for borrow in (False, True):
                for stage in (1, 0):
                    if not borrow and self.active[stage] >= self.limits[stage]:
                        continue
                    queue = self.queues[stage]
                    for index, job in enumerate(queue):
                        cpu = min(job[5], self.limits[stage], max(1, self.total_budget-1) if stage == 0 else self.total_budget)
                        charge = self.costs[stage]*cpu
                        charge = min(charge,self.memory_budget) if self.memory_budget is not None else charge
                        if sum(self.active)+cpu > self.total_budget:
                            continue
                        if not borrow and self.active[stage]+cpu > self.limits[stage]:
                            continue
                        if self.memory_budget is not None and self.active_bytes+charge > self.memory_budget:
                            continue
                        key = (stage, job[4]) if job[4] is not None else None
                        if job[0].cancelled() or key is None or key not in self.keys:
                            chosen = stage, index, key
                            break
                    if chosen is not None:
                        break
                if chosen is not None:
                    break
            if chosen is None:
                return
            stage, index, key = chosen
            queue = self.queues[stage]
            job = queue[index]
            del queue[index]
            if job[0].cancelled():
                job[0].set_running_or_notify_cancel()
                self.handles[stage].discard(job[0])
                continue
            cpu = min(job[5], self.limits[stage], max(1, self.total_budget-1) if stage == 0 else self.total_budget)
            job[0].pipeline_cpu_cost = cpu
            charge = self.costs[stage]*cpu
            charge = min(charge,self.memory_budget) if self.memory_budget is not None else charge
            self.active_bytes += charge
            self.active[stage] += cpu
            if key is not None:
                self.keys.add(key)
            self.pool.submit(self._run, stage, key, job, charge, cpu)

    def _run(self, stage, key, job, charge, cpu):
        future, fn, args, kwargs, _, _ = job
        value, error, ran = None, None, False
        try:
            ran = future.set_running_or_notify_cancel()
            if ran:
                value = fn(*args, **kwargs)
        except BaseException as ex:
            error = ex
        finally:
            with self.lock:
                self.active_bytes -= charge
                self.active[stage] -= cpu
                if key is not None:
                    self.keys.discard(key)
                self._dispatch()
            # Callbacks may acquire application/cache locks. No executor lock
            # can span them, including callbacks that submit dependent work.
            if ran:
                if error is None:
                    future.set_result(value)
                else:
                    future.set_exception(error)
            with self.lock:
                self.handles[stage].discard(future)
                complete = all(self.closed) and not any(self.handles)
            if complete:
                self.pool.shutdown(wait=False)

    def trim_idle(self):
        # Called only by the background reclaimer. Never drain a productive
        # pipeline merely to reduce idle thread stacks after a downgrade.
        with self.lock:
            if any(self.active) or any(self.queues) or any(self.closed):
                return False
            old = self.pool
            self.pool = ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2), thread_name_prefix='video-work')
        old.shutdown(wait=True)
        return True

    def shutdown(self, stage, block=True, cancel=False):
        with self.lock:
            self.closed[stage] = True
            pending = list(self.handles[stage])
            cancel_jobs = [job[0] for job in self.queues[stage]] if cancel else []
        for future in cancel_jobs:
            future.cancel()
        with self.lock:
            self._dispatch()
        if block:
            wait(pending)
        with self.lock:
            complete = all(self.closed) and not any(self.handles)
        if complete:
            self.pool.shutdown(wait=block)


class StageExecutor:
    def __init__(self, group, stage):
        self.group, self.stage = group, stage

    @property
    def _max_workers(self):
        return self.group.limits[self.stage]

    @property
    def _threads(self):
        return self.group.pool._threads

    def submit(self, fn, *args, **kwargs):
        resource_key = kwargs.pop('resource_key', None)
        cpu_cost = kwargs.pop('cpu_cost', 1)
        return self.group.submit(self.stage, fn, args, kwargs, resource_key, cpu_cost)

    def shutdown(self, wait=True, cancel_futures=False):
        self.group.shutdown(self.stage, wait, cancel_futures)
