"""Playback pacing, resource estimates and adaptive concurrency."""
import math
import os
import threading
from collections import deque
from typing import NamedTuple, Optional


# Concurrency and resource estimates
# Decode and stitch allocation
class ThreadAllocation(NamedTuple):
    extract: int
    stitch: int
    period: float
    reason: str = 'model'


class BufferLevels(NamedTuple):
    low: int
    critical: int
    recover: int
    capacity: int


def buffer_levels(cache_frames, capacity, interval, refill_latency=0., switch_latency=0.):
    """R pages warn, ceil(R/2) pages are critical; measured lead time can warn earlier."""
    radius, capacity = max(1, int(cache_frames)), max(0, int(capacity))
    lead = max(0., float(refill_latency)) + max(0., float(switch_latency))
    low = min(capacity, max(radius, math.ceil(lead / max(.001, float(interval)) - 1e-9)))
    critical = min(capacity, max(1, math.ceil(radius / 2)))
    recover = min(capacity, max(low + max(1, math.ceil(radius / 2)), math.ceil(radius * 1.5)))
    return BufferLevels(low, critical, recover, capacity)


def buffer_priority(stitched, raw, stitched_levels, raw_levels, previous=None):
    """Compare output pages and UNUSED raw pages beyond the output frontier."""
    s, r = stitched_levels, raw_levels
    s_low = stitched < s.capacity and stitched <= s.low
    r_low = raw < r.capacity and raw <= r.low
    # Input starvation must not be answered by creating more waiting composers.
    if s_low and raw == 0 and r_low:
        return 'raw'
    if s_low and stitched <= s.critical and raw > 0:
        return 'stitch'
    if r_low and raw <= r.critical and stitched > s.critical:
        return 'raw'
    if previous == 'stitch' and stitched < s.recover and stitched < s.capacity and raw > 0:
        return 'stitch'
    if previous == 'raw' and raw < r.recover and raw < r.capacity:
        return 'raw'
    if s_low and r_low:
        return 'stitch' if raw > 0 else 'raw'
    if s_low and (raw >= r.recover or raw >= r.capacity):
        return 'stitch'
    if r_low and (stitched >= s.recover or stitched >= s.capacity):
        return 'raw'
    return None


def available_memory_bytes():
    """Best-effort available physical RAM without launching a helper process."""
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except (ImportError, AttributeError, OSError, ValueError):
        pass
    try:
        if os.name == 'nt':
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in
                    ('total', 'available', 'page_total', 'page_available',
                     'virtual_total', 'virtual_available', 'extended')]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available)
        else:
            return int(os.sysconf('SC_AVPHYS_PAGES')) * int(os.sysconf('SC_PAGE_SIZE'))
    except (AttributeError, OSError, ValueError):
        pass
    return None


def stitch_memory_limit(output_pixels, input_pixels, available_bytes, maximum):
    """Soft concurrency guard, reserving half available RAM for GUI/other work.

    It prevents multiplying a large working set; it cannot make a single
    oversized composition fit in memory. The buffer multiplier is an estimate.
    """
    maximum = max(1, int(maximum))
    if available_bytes is None or output_pixels <= 0:
        return maximum
    working_set = max(64 * 1024 ** 2, 4 * 4 * int(output_pixels) + 3 * 3 * int(input_pixels))
    return min(maximum, max(1, int(available_bytes * 0.5) // working_set))


def optimize_thread_allocation(total_threads, extract_work, stitch_work, display_cost,
                               extract_serial=0.0, stitch_serial=0.0,
                               max_extract_tasks=None, max_stitch_tasks=None, current=None,
                               prefer_capacity=False, memory_budget=None,
                               extract_memory=0, stitch_memory=0):
    """Find the global integer minimum of this model by finite enumeration.

    The budget is a ceiling. prefer_capacity uses more feasible workers for
    equal predictions; the legacy default prefers fewer. Joint working-set
    constraints are evaluated for each pair, not clipped after solving.
    """
    budget = int(total_threads)
    if budget < 2:
        raise ValueError('At least two workers are required')
    costs = tuple(float(v) for v in (extract_work, stitch_work, display_cost))
    if any(not math.isfinite(v) or v < 0 for v in costs):
        raise ValueError('Stage costs must be finite and nonnegative')
    for fraction in (extract_serial, stitch_serial):
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError('Serial fractions must be between zero and one')
    emax = min(budget - 1, max(1, int(max_extract_tasks or budget - 1)))
    smax = min(budget - 1, max(1, int(max_stitch_tasks or budget - 1)))
    current = current or (budget - 1, 1)
    best, best_key = None, None
    for extract in range(1, emax + 1):
        for stitch in range(1, min(smax, budget - extract) + 1):
            if (memory_budget is not None
                    and extract * extract_memory + stitch * stitch_memory > memory_budget):
                continue
            period = max(costs[0] * (extract_serial + (1 - extract_serial) / extract),
                         costs[1] * (stitch_serial + (1 - stitch_serial) / stitch), costs[2])
            # Round only the tie key, not the returned physical prediction.
            key = (round(period, 12), -(extract + stitch) if prefer_capacity else extract + stitch,
                   abs(extract - current[0]) + abs(stitch - current[1]), extract)
            if best_key is None or key < best_key:
                best, best_key = ThreadAllocation(extract, stitch, period), key
    # One lane per stage is the minimum usable pipeline even if a single
    # composition itself exceeds the soft memory estimate.
    return best or ThreadAllocation(1, 1, max(costs), 'memory-minimum')


class AdaptiveThreadAllocator:
    """Fit saturation from measured plans, validate changes, and roll back losses.

    Measurements are processing costs, not user-paced frame intervals. For each
    stage fit work(n)=a*n+b with a,b>=0; the corresponding period is a+b/n.
    This captures loss of scaling from contention/GIL/serialized operations.
    The fit is an estimate; a new plan is always an online trial, not a promise
    of the globally fastest allocation on unknown hardware. throughput_first
    optimizes production independently of GUI display time and suppresses
    resource-only reductions; contention losses still trigger trial rollback.
    """
    def __init__(self, validation_samples=3, probe_every=8, throughput_first=False):
        self.throughput_first = throughput_first
        self.buffer_priority = None
        self.observations = {}
        self.validation_samples = max(1, int(validation_samples))
        self.probe_every = max(2, int(probe_every))
        self.revision = 0
        self.trial = None
        self.blocked_until = {}
        self.last_probe = 0

    def observe(self, allocation, extract_work, stitch_work, display_cost):
        plan = tuple(allocation)
        values = tuple(float(x) for x in (extract_work, stitch_work, display_cost))
        if any(not math.isfinite(v) or v < 0 for v in values):
            return
        self.revision += 1
        self.blocked_until = {key: until for key, until in self.blocked_until.items() if until > self.revision}
        samples = self.observations.setdefault(plan, deque(maxlen=8))
        samples.append(values)
        # Keep learning bounded for users trying many budgets.
        if len(self.observations) > 32:
            protected = {plan}
            if self.trial:
                protected.update((self.trial['source'], self.trial['target']))
            for old in list(self.observations):
                if old not in protected:
                    del self.observations[old]
                    break
        if self.trial and plan == self.trial['target']:
            self.trial['samples'] += 1

    def _mean(self, plan):
        values = self.observations[tuple(plan)]
        return tuple(sum(v[i] for v in values) / len(values) for i in range(3))

    @staticmethod
    def measured_period(plan, costs):
        return max(costs[0] / plan[0], costs[1] / plan[1], costs[2])

    def _period(self, plan, costs):
        return self.measured_period(plan, (costs[0], costs[1],
                                           0.0 if self.throughput_first else costs[2]))

    def _serial_fraction(self, stage):
        points = [(plan[stage], self._mean(plan)[stage]) for plan in self.observations]
        if len({n for n, _ in points}) < 2:
            return 0.0
        count = len(points)
        sx = sum(n for n, _ in points)
        sy = sum(work for _, work in points)
        sxx = sum(n * n for n, _ in points)
        sxy = sum(n * work for n, work in points)
        determinant = count * sxx - sx * sx
        slope = (count * sxy - sx * sy) / determinant
        intercept = (sy - slope * sx) / count
        candidates = [(0.0, sy / count), (sxy / sxx, 0.0)]
        if slope >= 0 and intercept >= 0:
            candidates.append((slope, intercept))
        a, b = min(candidates, key=lambda ab: sum((work - ab[0] * n - ab[1]) ** 2
                                                  for n, work in points))
        return a / (a + b) if a + b > 0 else 0.0

    def applied(self, old, new):
        """Called only after pools actually change, not when a change is queued."""
        old, new = tuple(old), tuple(new)
        if self.trial and new == self.trial['source']:
            self.trial = None
            return
        if old != new and old in self.observations:
            self.trial = dict(source=old, target=new, samples=0,
                              baseline=self._period(old, self._mean(old)))

    def recommend(self, total_threads, costs, current, max_extract_tasks=None,
                  max_stitch_tasks=None, allow_probe=True, extract_backlog=0,
                  stitch_waiting=0, stitch_ready=0, buffer_depth=None, buffer_target=1,
                  memory_budget=None, extract_memory=0, stitch_memory=0,
                  raw_buffer_depth=None, stitched_levels=None, raw_levels=None,
                  cpu_headroom=False, power_mode=2):
        current = tuple(current)
        budget = int(total_threads)
        def fits(plan):
            return (memory_budget is None
                    or plan[0] * extract_memory + plan[1] * stitch_memory <= memory_budget)
        infeasible = (sum(current) > budget or current[0] > (max_extract_tasks or budget - 1)
                      or current[1] > (max_stitch_tasks or budget - 1) or not fits(current))
        if infeasible:
            self.trial = None
        low_buffer = buffer_depth is not None and buffer_depth < max(1, buffer_target)
        if cpu_headroom and power_mode >= 3 and not infeasible:
            # Move UNUSED quotas to jobs that can actually execute. Do not
            # take lanes needed by the other stage's existing ready work.
            growth = 2. if power_mode >= 4 else 1.5
            raw_demand = max(1, min(current[0], extract_backlog))
            stitch_demand = max(1, min(current[1], stitch_ready))
            if stitch_ready > current[1]:
                target = min(max_stitch_tasks or budget-1, budget-raw_demand,
                             stitch_ready, max(current[1]+1, math.ceil(current[1]*growth)))
                for stitch in range(target, current[1], -1):
                    extract = min(current[0], budget-stitch)
                    if extract >= raw_demand and fits((extract, stitch)):
                        return ThreadAllocation(extract, stitch, self._period((extract, stitch), costs), 'ready-capacity')
            if extract_backlog > current[0]:
                target = min(max_extract_tasks or budget-1, budget-stitch_demand,
                             extract_backlog, max(current[0]+1, math.ceil(current[0]*growth)))
                for extract in range(target, current[0], -1):
                    stitch = min(current[1], budget-extract)
                    if stitch >= stitch_demand and fits((extract, stitch)):
                        return ThreadAllocation(extract, stitch, self._period((extract, stitch), costs), 'ready-capacity')
        if raw_buffer_depth is not None and stitched_levels is not None and raw_levels is not None:
            self.buffer_priority = buffer_priority(buffer_depth, raw_buffer_depth,
                stitched_levels, raw_levels, self.buffer_priority)
            if not infeasible and self.buffer_priority == 'stitch' and stitch_ready > current[1]:
                target = min(budget - 1, max_stitch_tasks or budget - 1,
                             stitch_ready, max(current[1] + 1, 2 * current[1]))
                for stitch in range(target, current[1], -1):
                    extract = min(current[0], budget - stitch)
                    while extract >= 1 and not fits((extract, stitch)):
                        extract -= 1
                    if extract >= 1:
                        return ThreadAllocation(extract, stitch, self._period((extract, stitch), costs),
                                                'stitch-buffer-low')
            if not infeasible and self.buffer_priority == 'raw' and extract_backlog > current[0]:
                target = min(budget - 1, max_extract_tasks or budget - 1,
                             extract_backlog, max(current[0] + 1, 2 * current[0]))
                for extract in range(target, current[0], -1):
                    stitch = min(current[1], budget - extract)
                    while stitch >= 1 and not fits((extract, stitch)):
                        stitch -= 1
                    if stitch >= 1:
                        return ThreadAllocation(extract, stitch, self._period((extract, stitch), costs),
                                                'raw-buffer-low')
            if self.buffer_priority is not None and not infeasible:
                return ThreadAllocation(*current, self._period(current, costs), 'hold-buffer-priority')
            # Explicit inventories replace the older output-only heuristic.
            low_buffer = False
        if (low_buffer and stitch_ready > current[1] and not infeasible
                and (stitch_waiting == 0 or
                     (stitch_ready >= 2 * stitch_waiting and extract_backlog <= current[0]))):
            # Finished raw frames are already waiting to be composed. Borrow
            # upstream lanes even when the entire budget is allocated.
            target = min(budget - 1, max_stitch_tasks or budget - 1,
                         stitch_ready, max(current[1] + 1, current[1] * 2))
            for stitch in range(target, current[1], -1):
                extract = min(current[0], budget - stitch)
                while extract >= 1 and not fits((extract, stitch)):
                    extract -= 1
                if extract >= 1:
                    reason = 'downstream-starved' if extract < current[0] else 'ready-backlog'
                    return ThreadAllocation(extract, stitch,
                        self._period((extract, stitch), costs), reason)
        if low_buffer and stitch_waiting > 0 and extract_backlog > current[0]:
            # Input starvation: increase upstream capacity first, not waiting
            # stitch workers. Use spare budget or one unused downstream lane.
            stitch = current[1]
            room = budget - stitch
            if room <= current[0] and stitch > 1 and stitch_ready == 0:
                stitch -= 1
                room += 1
            extract = min(room, max_extract_tasks or budget - 1, extract_backlog,
                          max(current[0] + 1, current[0] * 2))
            while extract > current[0] and not fits((extract, stitch)):
                extract -= 1
            if extract > current[0] and not infeasible:
                return ThreadAllocation(extract, stitch,
                    self.measured_period((extract, stitch), costs), 'upstream-starved')
        if low_buffer and stitch_ready > current[1] and sum(current) < budget:
            stitch = min(budget - current[0], max_stitch_tasks or budget - 1,
                         stitch_ready, current[1] * 2)
            while stitch > current[1] and not fits((current[0], stitch)):
                stitch -= 1
            if stitch > current[1] and not infeasible:
                return ThreadAllocation(current[0], stitch,
                    self.measured_period((current[0], stitch), costs), 'ready-backlog')
        if self.trial and current == self.trial['target']:
            trial = self.trial
            if trial['samples'] < self.validation_samples:
                return ThreadAllocation(*current, self.measured_period(current, costs), 'validate')
            actual = self._period(current, self._mean(current))
            if (actual > trial['baseline'] * 1.10 and sum(trial['source']) <= budget
                    and fits(trial['source'])):
                self.blocked_until[current] = self.revision + 16
                source = (min(trial['source'][0], max_extract_tasks or budget - 1),
                          min(trial['source'][1], max_stitch_tasks or budget - 1))
                return ThreadAllocation(*source, trial['baseline'], 'rollback')
            self.trial = None
        ae, ass = self._serial_fraction(0), self._serial_fraction(1)
        # Normalize the fitted scaling shape to the most recent workload.
        ebase = costs[0] / (1 + ae * (current[0] - 1))
        sbase = costs[1] / (1 + ass * (current[1] - 1))
        display_floor = 0.0 if self.throughput_first else costs[2]
        plan = optimize_thread_allocation(budget, ebase, sbase, display_floor, ae, ass,
                                          max_extract_tasks, max_stitch_tasks, current,
                                          self.throughput_first, memory_budget, extract_memory, stitch_memory)
        score = self._period(current, costs)
        proposed = (plan.extract, plan.stitch)
        blocked = self.blocked_until.get(proposed, 0) > self.revision
        if infeasible:
            return ThreadAllocation(plan.extract, plan.stitch, plan.period, 'capacity')
        useful = plan.period < score * 0.95 or (plan.period <= score * 1.02 and sum(proposed) < sum(current))
        resource_only = plan.period >= score * 0.95 and sum(proposed) < sum(current)
        if self.throughput_first:
            # Never shrink simply to save workers or because GUI service time
            # masks production gains. Growing capacity is an online trial;
            # shrinking requires an estimated throughput gain and validation.
            useful = (plan.period < score * .95 or
                      (plan.period <= score * 1.02 and sum(proposed) > sum(current)))
            resource_only = False
        if resource_only and buffer_depth is not None:
            samples = len(self.observations.get(current, ()))
            if low_buffer or stitch_waiting or stitch_ready or extract_backlog or samples < self.validation_samples:
                return ThreadAllocation(*current, score, 'keep-buffer-capacity')
        if proposed != current and useful and not blocked:
            return plan
        # Occasionally test a nearby unmeasured plan; feedback can expose a
        # scaling limit that an initially ideal model cannot predict.
        if allow_probe and self.revision - self.last_probe >= self.probe_every and score > display_floor * 1.05:
            candidates = []
            for e, s in ((current[0] + 1, current[1] - 1), (current[0] - 1, current[1] + 1),
                         (current[0] + 1, current[1]), (current[0], current[1] + 1)):
                if (e < 1 or s < 1 or e + s > budget
                        or e > (max_extract_tasks or budget - 1) or s > (max_stitch_tasks or budget - 1)):
                    continue
                if not fits((e, s)):
                    continue
                if (e, s) not in self.observations and self.blocked_until.get((e, s), 0) <= self.revision:
                    candidates.append((max(ebase * (ae + (1-ae)/e), sbase * (ass + (1-ass)/s), display_floor), e, s))
            if candidates:
                period, e, s = min(candidates)
                self.last_probe = self.revision
                return ThreadAllocation(e, s, period, 'probe')
        return ThreadAllocation(*current, score, 'current')


# Multi-stage allocation
class StageAllocation(NamedTuple):
    targets: tuple
    period: float
    reason: str


def allocate_stages(budget, work, caps=None, memory=None, memory_budget=None):
    budget=max(1,int(budget))
    work=tuple(max(0.,float(value)) if math.isfinite(float(value)) else 0. for value in work)
    count=len(work)
    caps=tuple(max(0,min(budget,int(value))) for value in (caps if caps is not None else [budget]*count))
    memory=tuple(max(0,int(value)) for value in (memory if memory is not None else [0]*count))
    if len(caps)!=count or len(memory)!=count:raise ValueError('Stage vector lengths differ')
    active=[i for i in range(count) if work[i]>0 and caps[i]>0]
    if not active:return StageAllocation((0,)*count,0.,'idle')
    # An optimum must equal work[i]/n for one bottleneck stage. Test these
    # O(stages*budget) breakpoints rather than enumerating O(budget**stages).
    periods=sorted({work[i]/n for i in active for n in range(1,caps[i]+1)})
    for period in periods:
        targets=[0]*count
        for i in active:targets[i]=max(1,math.ceil(work[i]/period-1e-10))
        if any(targets[i]>caps[i] for i in active) or sum(targets)>budget:continue
        used=sum(n*m for n,m in zip(targets,memory))
        if memory_budget is not None and used>memory_budget:continue
        # Use spare lanes where they most reduce the next-stage service time.
        while sum(targets)<budget:
            candidates=[i for i in active if targets[i]<caps[i] and
                (memory_budget is None or used+memory[i]<=memory_budget)]
            if not candidates:break
            i=max(candidates,key=lambda i:(work[i]/targets[i]-work[i]/(targets[i]+1),i))
            targets[i]+=1;used+=memory[i]
        return StageAllocation(tuple(targets),max(work[i]/targets[i] for i in active),'minimax')
    # Too few lanes/RAM for every stage simultaneously: targets express
    # preferences only. Admission still time-shares every ready, fitting stage.
    targets=[0]*count;used=0
    for _ in range(budget):
        candidates=[i for i in active if targets[i]<caps[i] and
            (memory_budget is None or used+memory[i]<=memory_budget)]
        if not candidates:break
        i=max(candidates,key=lambda i:(work[i]/(targets[i]+1),i))
        targets[i]+=1;used+=memory[i]
    return StageAllocation(tuple(targets),sum(work[i] for i in active)/budget,'time-share')


# Adaptive concurrency search
class AdaptiveAdmissionBudget:
    def __init__(self, phase_frames=12):
        self.lock = threading.RLock()
        self.phase_frames = max(4, int(phase_frames))
        self.key = None
        self.history = deque(maxlen=32)

    def configure(self, budget, context, enabled=True, warmup=13):
        with self.lock:
            key = max(2, int(budget)), context, bool(enabled)
            if key != self.key:
                self.key = key
                self.ceiling, self.context, self.enabled = key
                self.limit = self.best = self.ceiling
                self.minimum = max(2, math.ceil(self.ceiling / 2))
                self.warmup = max(0, int(warmup))
                self.frames = self.settling = self.phase_count = self.cooldown = 0
                self.start = self.start_produced = None
                self.best_period = None
                self.visited = set()
                self.history.clear()
                self.reason = 'warmup' if self.enabled else 'budget'
            return self.limit

    def _change(self, target, reason):
        self.limit = max(self.minimum, min(self.ceiling, int(target)))
        self.settling = 2
        self.start = self.start_produced = None
        self.phase_count = 0
        self.reason = reason
        return self.limit

    def restart_observation(self):
        """Exclude explicit user pauses, retaining the best resource limit.

        Cache-miss waits are NOT pauses: their time must remain in measured
        supply. Call this only on an explicit playback restart.
        """
        with self.lock:
            if self.key is None:
                return
            self.limit = self.best
            self.best_period = None
            self.start = self.start_produced = None
            self.phase_count = self.cooldown = 0
            self.visited.clear()
            self.settling = 2 if self.frames >= self.warmup else 0
            self.reason = 'resume' if self.frames >= self.warmup else 'warmup'

    def observe(self, now, produced, buffered, target_buffer=2, manual_limited=False):
        """Only completed display events enter; count actual produced pages.

        A cache drain cannot look like faster production: sample duration is
        divided by new valid composites, not by pages consumed from old stock.
        No timer, playback interval, cache radius or image quality is changed.
        """
        with self.lock:
            if not self.enabled or manual_limited:
                self.start = self.start_produced = None
                self.phase_count = 0
                return None
            self.frames += 1
            if self.frames <= self.warmup:
                return None
            if self.settling:
                self.settling -= 1
                return None
            if self.cooldown:
                self.cooldown -= 1
                if self.cooldown:
                    return None
                # Revalidate the incumbent before another neighboring probe;
                # do not compare a new scene against an old cost measurement.
                self.visited.clear()
            if self.start is None:
                self.start, self.start_produced = now, produced
                self.phase_count = 0
                return None
            self.phase_count += 1
            count = produced - self.start_produced
            elapsed = max(0., now-self.start)
            if (self.limit != self.best and self.best_period is not None
                    and self.phase_count >= 2 and buffered < max(1,target_buffer)
                    and elapsed > self.best_period*max(1,count)*1.35):
                self.visited.add(self.limit)
                self.history.append((self.limit,elapsed/max(1,count),'buffer-rollback'))
                self.cooldown = 48
                return self._change(self.best,'buffer-rollback')
            if self.phase_count < self.phase_frames or count < max(2,self.phase_frames//2):
                return None
            period = elapsed/count
            self.visited.add(self.limit)
            self.history.append((self.limit,period,'measured'))
            if self.best_period is None or self.limit == self.best:
                self.best_period = period
            elif period < self.best_period*.95:
                self.best, self.best_period = self.limit, period
            # A change must yield a measured improvement, not just lower CPU.
            if self.limit != self.best:
                return self._change(self.best,'restore-best')
            candidates = [max(self.minimum,int(round(self.best*.75))),
                          min(self.ceiling,max(self.best+1,int(round(self.best*4/3))))]
            # A single unsuccessful neighboring probe is not evidence that
            # all lower concurrencies are slower. Contention can create a
            # non-monotone curve; examine the bounded coarse ladder as well.
            target=self.ceiling
            while target>self.minimum:
                target=max(self.minimum,int(round(target*.75)))
                candidates.append(target)
            for candidate in candidates:
                if candidate != self.best and candidate not in self.visited:
                    return self._change(candidate,'probe')
            self.cooldown = 48
            self.start = self.start_produced = None
            self.phase_count = 0
            self.reason = 'best-measured'
            return None

    def snapshot(self):
        with self.lock:
            return dict(limit=self.limit, ceiling=self.ceiling, best=self.best,
                        period=self.best_period, reason=self.reason, history=list(self.history))


# Playback pacing and supply estimates
class ProductionJob(NamedTuple):
    key: object
    queued: float
    started: Optional[float]
    duration: float
    dependencies: tuple = ()


def refill_guard(radius, multiplier, period, lead_time):
    """Start useful production early without expanding caches or tiny FFmpeg runs.

    Keep at least half an outer radius per refill, amortizing startup/seeking.
    With multiplier 1 or 2 this preserves the original R-page boundary rule.
    """
    radius, multiplier = max(1, int(radius)), max(1, int(multiplier))
    outer = radius * multiplier
    maximum = max(radius, outer // 2)
    return min(maximum, max(radius, math.ceil(max(0., lead_time) / max(.001, period) - 1e-9)))


def completion_estimates(jobs, workers, now, inputs=None):
    """List-schedule outstanding jobs, including dependency and queue delays."""
    inputs = inputs or {}
    result, slots, queued = {}, [], []
    for job in jobs:
        duration = max(.001, job.duration)
        if job.started is not None:
            age = max(0., now - job.started)
            remaining = duration - age if age < duration else max(.05, .2 * duration, .2 * age)
            result[job.key] = remaining
            slots.append(remaining)
        else:
            release = max((inputs.get(key, 0.) for key in job.dependencies), default=0.)
            queued.append((release, job.queued, job, duration))
    slots.extend([0.] * max(0, max(1, workers) - len(slots)))
    if not slots:
        slots = [0.]
    for release, _, job, duration in sorted(queued, key=lambda item: (item[0], item[1])):
        slot = min(range(len(slots)), key=slots.__getitem__)
        finish = max(slots[slot], release) + duration
        result[job.key] = slots[slot] = finish
    return result


class PlaybackPacer:
    """Learn pages/active production time; exclude full-cache idle intervals.

    Throughput samples aggregate batches, rather than averaging interarrival
    times of a burst. One recency-weighted active-time/page window smooths the result.
    Deadline protection is applied after smoothing so warnings are not delayed.
    """
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.context = None
            self.pending = set()
            self.samples = deque(maxlen=8)
            self.first_delays = deque(maxlen=12)
            self.period = None
            self.active_since = self.checkpoint = None
            self.produced = 0
            self.first_ready = False
            self.last_interval = self.last_update = None
            self.last_request = None

    def _context(self, context):
        if context != self.context:
            self.reset()
            self.context = context

    def request(self, context, wanted, window, current, direction, now):
        with self.lock:
            self._context(context)
            self.last_request = current
            lo, hi = window
            wanted = set(wanted)
            self.pending = {batch for batch in self.pending if lo <= batch <= hi and batch in wanted}
            if not self.pending:
                self.active_since = self.checkpoint = now if wanted else None
                self.produced = 0
                self.first_ready = False
            self.pending.update(wanted)

    def publish(self, context, batch, now, group_size=2):
        with self.lock:
            if context != self.context or batch not in self.pending:
                return
            self.pending.remove(batch)
            if not self.first_ready and self.active_since is not None:
                self.first_delays.append(max(0., now - self.active_since))
                self.first_ready = True
            self.produced += 1
            elapsed = now - self.checkpoint if self.checkpoint is not None else 0.
            if elapsed > .001 and (self.produced >= max(2, group_size) or not self.pending):
                self.samples.append((elapsed, self.produced))
                # Average active time/pages with recency weights ONCE. The old
                # full-window average followed by another EWMA let cold-start
                # costs constrain playback for dozens of completed pages.
                recent=list(reversed(self.samples))
                self.period=sum(t*.5**i for i,(t,n) in enumerate(recent))/sum(n*.5**i for i,(t,n) in enumerate(recent))
                self.checkpoint, self.produced = now, 0
            if not self.pending:
                self.active_since = self.checkpoint = None

    def first_ready_delay(self):
        with self.lock:
            values = sorted(self.first_delays)
            return values[math.ceil(.9 * len(values))-1] if values else None

    def supply_period(self, now=None, production_active=True):
        with self.lock:
            period=self.period
            if (period is not None and now is not None and production_active
                    and self.pending and self.checkpoint is not None):
                # If the next output completed NOW, this is the best possible
                # active-time/page rate of the unfinished measurement group.
                # React to a real stall before the ready buffer is exhausted.
                period=max(period,max(0.,now-self.checkpoint)/(self.produced+1))
            return period

    def recommend(self, context, now, buffered, target_buffer, remaining, manual,
                  display_cost, fallback_period, next_eta=None, production_active=True):
        with self.lock:
            self._context(context)
            manual = max(.001, manual or .001)
            if remaining <= buffered:
                candidate = max(manual, display_cost)
                reason = 'all-ready'
            else:
                supply = self.supply_period(now,production_active)
                supply = supply if supply is not None else max(.001,fallback_period)
                # Finite-horizon inventory balance: H new pages take
                # H*supply seconds; B ready pages already exist. Therefore
                # (H+B)*interval >= H*supply. Recalculate every switch and
                # completion so existing stock absorbs production bursts.
                horizon = max(1, min(max(1, target_buffer), remaining-buffered))
                balanced = supply * horizon / (horizon + max(0, buffered))
                candidate = max(manual, display_cost, balanced)
                reason = 'measured-supply' if self.period is not None else 'stage-fallback'
                eta = next_eta if next_eta is not None else (self.first_ready_delay() if self.period is None else None)
                if eta is not None:
                    # The first hole is requested after B cached frames plus
                    # one switch. It should be ready before that deadline.
                    safe = max(0., eta) / (buffered+1)
                    if safe > candidate:
                        candidate, reason = safe, 'buffer-deadline'
            candidate = max(manual, display_cost, candidate)
            self.last_interval, self.last_update = candidate, now
            return candidate, dict(reason=reason, buffered=buffered,
                production_period=self.supply_period(now,production_active), measured_period=self.period, next_eta=next_eta)
