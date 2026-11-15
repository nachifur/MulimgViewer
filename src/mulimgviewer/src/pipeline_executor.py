"""Persistent workers with nonblocking, shared-budget stage admission."""
import os
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, wait


class PipelineWorkers:
    def __init__(self, extract, stitch):
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2), thread_name_prefix='video-work')
        self.limits = [extract, stitch]
        self.total_budget = extract + stitch
        self.active = [0, 0]
        self.stage_bytes = [0, 0]
        self.downstream_active = self.downstream_bytes = 0
        self.coordinators=0
        self._downstream_waiters={}
        self._decode_clock = self._decode_started = time.perf_counter()
        self._decode_samples = deque(maxlen=2048)
        self._decode_completed = deque(maxlen=2048)
        self._decode_peaks = deque(maxlen=2048)
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

    def reset_activity(self):
        with self.lock:
            self._decode_clock=self._decode_started=time.perf_counter()
            self._decode_samples.clear();self._decode_completed.clear();self._decode_peaks.clear()

    def _record_decode_activity(self, now=None):
        # Caller holds the executor lock. Integrate every state transition so
        # short bursts are retained even between GUI/monitor refreshes.
        now=time.perf_counter() if now is None else now
        if now>self._decode_clock:
            self._decode_samples.append((self._decode_clock,now,self.active[0]))
        self._decode_clock=now
        while self._decode_samples and self._decode_samples[0][1]<=now-10.:
            self._decode_samples.popleft()
        while self._decode_peaks and self._decode_peaks[0][0]<=now-10.:
            self._decode_peaks.popleft()
        while self._decode_completed and self._decode_completed[0]<=now-10.:
            self._decode_completed.popleft()

    def activity_snapshot(self, now=None):
        with self.lock:
            now=time.perf_counter() if now is None else now
            self._record_decode_activity(now)
            cutoff=max(self._decode_started,now-10.)
            samples=self._decode_samples
            elapsed=now-max(cutoff,samples[0][0] if samples else cutoff)
            work=sum((end-max(start,cutoff))*slots for start,end,slots in samples)
            return dict(decode_now=self.active[0],
                decode_average=work/elapsed if elapsed>0 else 0.,
                decode_peak=max([self.active[0]]+[slots for _,_,slots in samples]+[slots for _,slots in self._decode_peaks]),
                decode_completed=len(self._decode_completed),
                decode_queued=sum(not job[0].cancelled() for job in self.queues[0]),
                admitted=self.total_budget)

    def _cpu_used(self):
        return sum(self.active) + self.downstream_active

    def _memory_used(self):
        return sum(self.stage_bytes) + self.downstream_bytes

    def downstream_capacity(self):
        """All idle decode lanes can serve bounded downstream computation."""
        with self.lock:
            lanes=max(0,self.total_budget-sum(self.active))
            memory=None if self.memory_budget is None else max(0,self.memory_budget-sum(self.stage_bytes))
            return lanes,memory

    def adjust_downstream_waiting(self,key,size=0,wake=None):
        with self.lock:
            if wake is None:
                self._downstream_waiters.pop(key,None)
                self._dispatch()
            else:self._downstream_waiters[key]=(size,wake)

    def reserve_downstream(self, count, size):
        """Atomically arbitrate child permits against newly admitted decoders.

        Metadata coordinators have a separate bounded count and no CPU/pixel
        charge. Sum real ordinary-task and child usage exactly once.
        """
        with self.lock:
            active=self.downstream_active+count
            memory=self.downstream_bytes+size
            if count>0 and (sum(self.active)+active>self.total_budget or
                    (self.memory_budget is not None and
                     sum(self.stage_bytes)+memory>self.memory_budget)):
                return False
            self.downstream_active=active;self.downstream_bytes=memory
            if count<0:self._dispatch()
            return True

    def submit(self, stage, fn, args, kwargs, resource_key=None, cpu_cost=1, coordinator=False):
        future = Future()
        with self.lock:
            if self.closed[stage]:
                raise RuntimeError('Cannot schedule work after shutdown')
            self.handles[stage].add(future)
            self.queues[stage].append((future, fn, args, kwargs, resource_key, max(1,int(cpu_cost)), coordinator))
            self._dispatch()
        return future

    def _dispatch(self):
        # All calls hold the lock. Never invoke user Future callbacks here.
        while self._cpu_used() < self.total_budget:
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
                        if stage==0 and self._downstream_waiters:
                            # Lend only genuinely idle downstream capacity.
                            if borrow and self.active[0]>=self.limits[0]:continue
                            needed=min(size for size,_ in self._downstream_waiters.values())
                            if self.memory_budget is not None and self._memory_used()+self.costs[0]*cpu+needed>self.memory_budget:continue
                        coordinator=len(job)>6 and job[6]
                        if coordinator:
                            cap=self.total_budget if coordinator=='ready' else self.limits[1]
                            if self.coordinators>=max(1,min(cap,self.pool._max_workers-1)):continue
                            cpu=0
                        charge = self.costs[stage]*cpu
                        charge = min(charge,self.memory_budget) if self.memory_budget is not None else charge
                        if self._cpu_used()+cpu > self.total_budget:
                            continue
                        if not borrow and self.active[stage]+cpu > self.limits[stage]:
                            continue
                        if self.memory_budget is not None and self._memory_used()+charge > self.memory_budget:
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
            coordinator=len(job)>6 and job[6]
            if coordinator:
                cpu=0;self.coordinators+=1
            job[0].pipeline_cpu_cost = cpu
            charge = self.costs[stage]*cpu
            charge = min(charge,self.memory_budget) if self.memory_budget is not None else charge
            self.active_bytes += charge
            self.stage_bytes[stage] += charge
            if stage==0:self._record_decode_activity()
            self.active[stage] += cpu
            if stage==0:self._decode_peaks.append((self._decode_clock,self.active[0]))
            if key is not None:
                self.keys.add(key)
            self.pool.submit(self._run, stage, key, job, charge, cpu)

    def _run(self, stage, key, job, charge, cpu):
        future, fn, args, kwargs, _, _ = job[:6]
        value, error, ran = None, None, False
        try:
            ran = future.set_running_or_notify_cancel()
            if ran:
                value = fn(*args, **kwargs)
        except BaseException as ex:
            error = ex
        finally:
            with self.lock:
                if len(job)>6 and job[6]:self.coordinators-=1
                self.active_bytes -= charge
                self.stage_bytes[stage] -= charge
                if stage==0:
                    self._record_decode_activity()
                    if ran:self._decode_completed.append(self._decode_clock)
                self.active[stage] -= cpu
                if key is not None:
                    self.keys.discard(key)
                self._dispatch()
                wake=tuple(set(callback for _,callback in self._downstream_waiters.values()))
            for callback in wake:callback()
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
            if any(self.active) or self.coordinators or self.downstream_active or any(self.queues) or any(self.closed):
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
        coordinator=kwargs.pop('coordinator',False)
        return self.group.submit(self.stage, fn, args, kwargs, resource_key, cpu_cost,coordinator)

    def shutdown(self, wait=True, cancel_futures=False):
        self.group.shutdown(self.stage, wait, cancel_futures)
