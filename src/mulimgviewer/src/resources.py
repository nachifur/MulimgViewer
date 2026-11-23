"""CPU and memory budgets, usage measurements, and idle reclamation."""
from __future__ import annotations

import ctypes
import gc
import math
import os
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import NamedTuple

if __package__:
    from .playback_policy import available_memory_bytes
else:
    from playback_policy import available_memory_bytes


# Budgets and cache windows
class ResourceBudget(NamedTuple):
    mode: int
    workers: int
    memory: int | None


def positive_cache_integer(raw):
    """Validate before conversion: 0.5 must never silently become 0 or 1."""
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite() or value < 1 or value > sys.maxsize or value != value.to_integral_value():
            raise ValueError('Enter an integer greater than or equal to 1')
        return int(value)
    except (InvalidOperation, TypeError, ValueError, OverflowError) as ex:
        raise ValueError('Enter an integer greater than or equal to 1') from ex


def resource_budget(mode, video=False, cpus=None, available=None):
    """Soft worker/RAM ceilings, not an OS CPU percentage or memory quota.

    One-core machines still need two video pipeline lanes; their work shares
    the CPU. Memory is sampled at policy changes, rather than per GUI paint.
    """
    mode = max(1, min(4, int(mode)))
    cpu_fraction, memory_fraction = ((.25, .15), (.5, .30), (.75, .50), (1., .75))[mode - 1]
    cpus = max(1, int(cpus or os.cpu_count() or 1))
    available = available_memory_bytes() if available is None else available
    return ResourceBudget(mode, max(2 if video else 1, math.floor(cpus * cpu_fraction)),
                          int(available * memory_fraction) if available is not None else None)


def cache_window(batch, total, radius, multiplier, previous=None):
    """Retain an anchored outer window until within one inner radius of an edge."""
    radius, multiplier = max(1, int(radius)), max(1, int(multiplier))
    end = max(0, int(total) - 1)
    batch = max(0, min(end, int(batch)))
    if previous is not None and multiplier >= 2:
        lo, hi = previous
        if (lo <= batch <= hi and (lo == 0 or batch - lo > radius)
                and (hi == end or hi - batch > radius)):
            return previous
    return max(0, batch - radius * multiplier), min(end, batch + radius * multiplier)


def composition_workers(budget, memory, output_pixels=0, input_pixels=0):
    """All image lanes compose; cap simultaneous working sets by the RAM budget."""
    working = max(64 * 1024 ** 2, 16 * output_pixels + 9 * input_pixels)
    return max(1, min(int(budget), int(memory) // working if memory is not None else int(budget)))


# Usage sampling and subprocess accounting
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


@contextmanager
def tracked_video_process(command, **kwargs):
    """Stream a bounded child output, accounting CPU and reaping on cancellation."""
    with subprocess.Popen(command, **kwargs) as process:
        if sys.platform == 'win32':
            with CHILD_CPU.lock:CHILD_CPU.active.add(process)
        try:
            yield process
        finally:
            if process.poll() is None:process.kill()
            process.wait()
            if sys.platform == 'win32':
                with CHILD_CPU.lock:
                    CHILD_CPU.completed += _windows_cpu_time(process)
                    CHILD_CPU.active.discard(process)


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
                        memory_now=samples[-1][3] if samples else None,
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


# Memory reclamation
def release_unused_memory(trim_working_set=False):
    """Collect unused objects and ask the native allocator to return free pages.

    Windows working-set trimming also evicts live pages, so reserve it for an
    idle, paused viewer. This never deletes cache files or closes live images.
    Native calls are best effort; freed Python objects need not reduce RSS by
    their full size because allocator arenas can still contain live objects.
    """
    collected = gc.collect()
    heap_released = working_set_trimmed = False
    if os.name == 'nt':
        try:
            runtime = ctypes.CDLL('ucrtbase')
            runtime._heapmin.restype = ctypes.c_int
            heap_released = runtime._heapmin() == 0
        except (AttributeError, OSError):
            pass
        if trim_working_set:
            try:
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                psapi = ctypes.WinDLL('psapi', use_last_error=True)
                kernel.GetCurrentProcess.restype = ctypes.c_void_p
                psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
                psapi.EmptyWorkingSet.restype = ctypes.c_int
                working_set_trimmed = bool(psapi.EmptyWorkingSet(kernel.GetCurrentProcess()))
            except (AttributeError, OSError):
                pass
    elif sys.platform == 'darwin':
        try:
            runtime = ctypes.CDLL(None)
            runtime.malloc_zone_pressure_relief.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            runtime.malloc_zone_pressure_relief.restype = ctypes.c_size_t
            heap_released = bool(runtime.malloc_zone_pressure_relief(None, 0))
        except (AttributeError, OSError):
            pass
    elif sys.platform.startswith('linux'):
        try:
            runtime = ctypes.CDLL(None)
            runtime.malloc_trim.argtypes = [ctypes.c_size_t]
            runtime.malloc_trim.restype = ctypes.c_int
            heap_released = bool(runtime.malloc_trim(0))
        except (AttributeError, OSError):
            pass
    return dict(collected=collected, heap_released=heap_released,
                working_set_trimmed=working_set_trimmed)


class MemoryReclaimer:
    """Coalesce policy changes; never wait or invoke GC on the GUI thread."""
    def __init__(self):
        self.executor = ThreadPoolExecutor(1, thread_name_prefix='memory-reclaim')
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.serial = 0
        self.future = None
        self.last_result = None
        self.idle_since = None
        self.idle_reclaimed = False

    def cancel(self):
        with self.lock:
            self.serial += 1

    def request(self, ready, retire, allow_working_set_trim):
        with self.lock:
            if self.closed.is_set():
                return
            self.serial += 1
            serial = self.serial
            if self.future is not None:
                self.future.cancel()
            def reclaim():
                while not self.closed.is_set():
                    with self.lock:
                        if serial != self.serial:
                            return
                    if ready():
                        break
                    self.closed.wait(.05)
                if self.closed.is_set():
                    return
                retire()  # Join drained old pools and drop completed results.
                with self.lock:
                    if self.closed.is_set() or serial != self.serial:
                        return
                result = release_unused_memory(allow_working_set_trim())
                with self.lock:
                    if serial == self.serial:
                        self.last_result = result
                return result
            self.future = self.executor.submit(reclaim)

    def observe_idle_pressure(self, over_budget, idle, retire, now):
        """One reclaim per sustained idle episode. Share the downgrade worker."""
        eligible = over_budget and idle()
        with self.lock:
            if not eligible:
                self.idle_since = None
                self.idle_reclaimed = False
                return
            if self.idle_since is None:
                self.idle_since = now
            if (self.closed.is_set() or self.idle_reclaimed or now - self.idle_since < 10.
                    or (self.future is not None and not self.future.done())):
                return
            serial = self.serial
            def reclaim():
                with self.lock:
                    if serial != self.serial or self.closed.is_set():
                        return
                if idle():
                    retire()
                    if idle():
                        return release_unused_memory(trim_working_set=True)
            self.idle_reclaimed = True
            self.future = self.executor.submit(reclaim)

    def close(self):
        self.closed.set()
        self.cancel()
        self.executor.shutdown(wait=False)
