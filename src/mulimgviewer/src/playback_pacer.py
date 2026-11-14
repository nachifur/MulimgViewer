"""Supply-driven playout pacing. No wx, filesystem access, or sleeping."""
import math
import threading
from collections import deque
from typing import NamedTuple, Optional


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
