"""Integer pipeline optimization; no GUI, executors or third-party dependencies.

Minimize max(E * (ae + (1-ae)/e), S * (as + (1-as)/s), D),
subject to e,s >= 1 and e+s <= budget and available-task limits.
E is the sum of per-video seconds of extraction work per logical batch;
S includes composition and PNG storage; D is serial display service time.
"""
import math
import os
from collections import deque
from typing import NamedTuple


class ThreadAllocation(NamedTuple):
    extract: int
    stitch: int
    period: float
    reason: str = 'model'


def available_memory_bytes():
    """Best-effort available physical RAM; no process creation or filesystem I/O."""
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
                  memory_budget=None, extract_memory=0, stitch_memory=0):
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
