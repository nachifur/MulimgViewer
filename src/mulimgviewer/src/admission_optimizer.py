"""Bounded online search for useful producer concurrency, independent of wx."""
import math
import threading
from collections import deque


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
