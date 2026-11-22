"""Background reclamation on policy downgrades and sustained idle RAM pressure."""
import ctypes
import gc
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor


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
