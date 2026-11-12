"""Background, mode-local rolling resource measurements; no GUI access."""
import ctypes
import os
import subprocess
import sys
import threading
import time
from collections import deque
from functools import lru_cache

try:
    import psutil
except ImportError:
    psutil = None


@lru_cache(maxsize=1)
def _windows_time_api():
    class FileTime(ctypes.Structure):
        _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(FileTime)] * 4
    kernel.GetProcessTimes.restype = ctypes.c_int
    return kernel.GetProcessTimes, FileTime


def _windows_cpu_time(process):
    get_times, FileTime = _windows_time_api()
    created, exited, system, user = (FileTime() for _ in range(4))
    if not get_times(int(process._handle), ctypes.byref(created), ctypes.byref(exited),
                     ctypes.byref(system), ctypes.byref(user)):
        return 0.0
    return ((system.high << 32) + system.low + (user.high << 32) + user.low) / 10_000_000


class ChildCpuTracker:
    """Include short-lived FFmpeg processes that finish between monitor samples."""
    def __init__(self):
        self.lock = threading.RLock()
        self.active = set()
        self.completed = 0.0

    def total(self, children):
        if sys.platform == 'win32':
            with self.lock:
                return self.completed + sum(_windows_cpu_time(p) for p in self.active)
        # POSIX keeps CPU accounting for reaped children, including processes
        # too short-lived for psutil's periodic process-tree enumeration.
        import resource
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        total = usage.ru_utime + usage.ru_stime
        for child in children:
            try:
                usage = child.cpu_times()
                total += usage.user + usage.system
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total


CHILD_CPU = ChildCpuTracker()


def run_video_process(command, **kwargs):
    if sys.platform != 'win32':
        return subprocess.run(command, **kwargs)
    # Retain the Windows handle until CPU accounting has read the exit times.
    capture = kwargs.pop('capture_output', False)
    check = kwargs.pop('check', False)
    timeout = kwargs.pop('timeout', None)
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with subprocess.Popen(command, **kwargs) as process:
        with CHILD_CPU.lock:
            CHILD_CPU.active.add(process)
        try:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException:
                process.kill()
                process.communicate()
                raise
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            with CHILD_CPU.lock:
                CHILD_CPU.completed += _windows_cpu_time(process)
                CHILD_CPU.active.discard(process)
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
    return result


class ResourceMonitor:
    def __init__(self, notify=None, window=10., interval=1., start=True):
        self.notify = notify
        self.window, self.interval = float(window), float(interval)
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.epoch = 0
        self.samples = deque(maxlen=120)
        self.frames = deque(maxlen=2000)
        self.last_frame = None
        self.baseline = None
        self.cpu_count = max(1, os.cpu_count() or 1)
        self.thread = None
        self.process = psutil.Process() if psutil is not None else None
        self.latest = self.snapshot()
        if start:
            self.thread = threading.Thread(target=self._run, name='resource-monitor', daemon=True)
            self.thread.start()

    def reset(self):
        with self.lock:
            self.epoch += 1
            self.samples.clear()
            self.baseline = None
            self.reset_playback()
            self.latest = self.snapshot()

    def reset_playback(self):
        with self.lock:
            self.frames.clear()
            self.last_frame = None
            if hasattr(self, 'latest'):
                self.latest['fps'] = None

    def frame_presented(self, batch, direction=1, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.last_frame is not None:
                previous, timestamp = self.last_frame
                if batch == previous:
                    return
                if batch == previous + (1 if direction >= 0 else -1) and now > timestamp:
                    self.frames.append((timestamp, now))
                else:
                    self.frames.clear()
            self.last_frame = batch, now

    def record(self, now, cpu_seconds, rss, epoch=None):
        with self.lock:
            if epoch is not None and epoch != self.epoch:
                return
            previous = self.baseline
            # A child may finish while POSIX accounting is sampled. Keep the
            # cumulative counter monotonic; a 10s average smooths that boundary.
            cpu_seconds = max(cpu_seconds, previous[1]) if previous else cpu_seconds
            self.baseline = now, cpu_seconds
            if previous and now > previous[0]:
                self.samples.append((previous[0], now, cpu_seconds - previous[1], rss))

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            cutoff = now - self.window
            while self.samples and self.samples[0][1] <= cutoff:
                self.samples.popleft()
            while self.frames and self.frames[0][1] <= cutoff:
                self.frames.popleft()
            samples = list(self.samples)
            elapsed = sum(end - max(start, cutoff) for start, end, _, _ in samples)
            cpu = sum(work * (end - max(start, cutoff)) / (end - start)
                      for start, end, work, _ in samples)
            rss = sum(rss * (end - max(start, cutoff)) for start, end, _, rss in samples)
            frame_start = self.frames[0][0] if self.frames else self.last_frame[1] if self.last_frame else None
            frame_time = now - max(frame_start, cutoff) if frame_start is not None else 0.
            frame_count = sum((end - max(start, cutoff)) / (end - start) for start, end in self.frames)
            return dict(cpu=min(100., cpu / elapsed / self.cpu_count * 100) if elapsed else None,
                        memory=rss / elapsed if elapsed else None,
                        fps=frame_count / frame_time if frame_time else None,
                        seconds=elapsed, available=self.process is not None)

    def read_snapshot(self):
        with self.lock:
            return dict(self.latest)

    def _run(self):
        while not self.stopped.is_set():
            with self.lock:
                epoch = self.epoch
            if self.process is not None:
                try:
                    children = self.process.children(recursive=True)
                    usage = self.process.cpu_times()
                    cpu = usage.user + usage.system + CHILD_CPU.total(children)
                    rss = self.process.memory_info().rss
                    for child in children:
                        try:
                            rss += child.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    self.record(time.monotonic(), cpu, rss, epoch)
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    pass
            with self.lock:
                self.latest = self.snapshot()
            if self.notify is not None and not self.stopped.is_set():
                self.notify()
            self.stopped.wait(self.interval)

    def close(self):
        self.stopped.set()
