"""Bounded asynchronous image composition. Workers never touch wx or the live model."""
import copy
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, CancelledError
from pathlib import Path

from PIL import Image

from .resource_policy import cache_window, composition_workers
from .thread_optimizer import available_memory_bytes


RENDER_STATE = (
    'xy_grid', 'xy_grids_id_list', 'crop_points', 'img_resolution_origin',
    'img_resolution_show', 'img_resolution', 'gap_color', 'title_setting',
    'pdf_title_layers', '_last_title_layout', 'flist', '_flist_groups', 'full_exif_cache',
    '_status_source_slots',
    '_show_all_func_enabled', '_show_all_func_layout', '_original_row_col',
    '_show_all_func_expanded_row_col', '_func_layout_vertical', '_blank_img_ids',
)


class ImagePipeline:
    def __init__(self, directory, notify, dispatch):
        self.directory = Path(directory)
        self.notify, self.dispatch = notify, dispatch
        self.lock = threading.RLock()
        self.coordinator = ThreadPoolExecutor(1, thread_name_prefix='image-schedule')
        self.display = ThreadPoolExecutor(1, thread_name_prefix='image-display')
        self.pool = None
        self.retired_pools = []
        self.workers = 0
        self.desired_workers = 1
        self.generation = uuid.uuid4().hex
        self.context = None
        self.window = None
        self.settings = None
        self.cache, self.running, self.failed = {}, {}, set()
        self.closed = False
        self.request_serial = 0
        self.display_key = None
        self.displayed_key = None
        self.display_future = None
        self.output_pixels = self.input_pixels = 0
        self.last_error = None
        self._pump_queued = False
        self._legacy_cleaned = False
        self._published_files = {}

    def _schedule(self):
        with self.lock:
            if self.closed or self._pump_queued:
                return
            self._pump_queued = True
            self.coordinator.submit(self._pump)

    def invalidate(self):
        with self.lock:
            self.generation = uuid.uuid4().hex
            self.cache.clear()
            self.failed.clear()
            self.window = self.context = None
            self.request_serial += 1
            self.displayed_key = self.display_key = None
            for future in list(self.running.values()):
                future.cancel()
        self._schedule()

    def request(self, template, points, custom, context, batch, total, radius, multiplier,
                budget, memory, direction=1):
        with self.lock:
            if self.closed:
                return
            settings = (total, radius, multiplier)
            if context != self.context:
                self.invalidate()
                self.context = context
                self.output_pixels = self.input_pixels = 0
            previous = self.window if settings == self.settings else None
            self.window = cache_window(batch, total, radius, multiplier, previous)
            self.settings = settings
            self.template, self.points, self.custom = template, points, custom
            self.batch, self.direction = batch, direction
            self.failed.discard(batch)  # A fresh user request can retry a failed page.
            self.budget, self.memory = budget, memory
            self.desired_workers = min(self.window[1] - self.window[0] + 1,
                composition_workers(budget, memory, self.output_pixels, self.input_pixels))
            # Until a first batch gives a measured size, launch only one costly
            # composition. Otherwise a 10x10 native-resolution layout can OOM.
            if not self.output_pixels:
                self.desired_workers = 1
        self._schedule()

    def _pump(self):
        # This is the only thread that publishes/deletes PNGs and resizes pools.
        available = available_memory_bytes()
        with self.lock:
            self._pump_queued = False
            if self.closed:
                return
            completed = [(key, f) for key, f in self.running.items() if f.done()]
            notices = []
            for key, future in completed:
                self.running.pop(key, None)
                generation, batch = key
                try:
                    temporary, state, pixels, inputs, duration = future.result()
                except Exception as exc:
                    if (not isinstance(exc, CancelledError) and generation == self.generation
                            and self.window is not None and self.window[0] <= batch <= self.window[1]):
                        self.failed.add(batch)
                        self.last_error = str(exc)
                        notices.append((batch, generation, str(exc)))
                    continue
                valid = (not self.closed and generation == self.generation and self.window is not None
                         and self.window[0] <= batch <= self.window[1])
                # File operations below intentionally do not hold the state lock.
                notices.append((batch, generation, None)) if valid else None
                if valid:
                    self.output_pixels = max(self.output_pixels, pixels)
                    self.input_pixels = max(self.input_pixels, inputs)
                # Workers write generation-specific temporaries; only this
                # coordinator publishes validated results to the shared filenames.
                self.lock.release()
                try:
                    if valid:
                        path = self.directory / f'batch_{batch}.png'
                        os.replace(temporary, path)
                        self._published_files[path] = path.stat()
                    else:
                        Path(temporary).unlink(missing_ok=True)
                except OSError as exc:
                    valid = False
                    self.last_error = str(exc)
                    notices.append((batch, generation, str(exc)))
                    try:
                        Path(temporary).unlink(missing_ok=True)
                    except OSError:
                        pass
                finally:
                    self.lock.acquire()
                if (valid and not self.closed and generation == self.generation
                        and self.window is not None and self.window[0] <= batch <= self.window[1]):
                    self.cache[batch] = (str(path), state, duration)
            if self.window is not None:
                lo, hi = self.window
                self.failed = {batch for batch in self.failed if lo <= batch <= hi}
                for batch in list(self.cache):
                    if not lo <= batch <= hi:
                        self.cache.pop(batch, None)
                memory = self.memory
                if available is not None:
                    memory = min(memory, int(available * .9)) if memory is not None else int(available * .9)
                self.desired_workers = min(hi - lo + 1, composition_workers(
                    self.budget, memory, self.output_pixels, self.input_pixels)) if self.output_pixels else 1
            keep = {entry[0] for entry in self.cache.values()}
            # Holding a state lock over directory scanning would block requests.
            self.lock.release()
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                if not self._legacy_cleaned:
                    self._legacy_cleaned = True
                    legacy = self.directory.parent / 'image_stitch_cache'
                    for path in legacy.glob('batch_*.png'):
                        try:
                            path.unlink()
                        except OSError:
                            pass
                    try:
                        legacy.rmdir()  # Only remove an empty legacy cache folder.
                    except OSError:
                        pass
                # Retire legacy names once; new files share the video's naming
                # format. Only delete PNGs published by this pipeline, and leave
                # replacements by the video writer untouched after a mode switch.
                if not getattr(self, '_names_migrated', False):
                    for path in self.directory.glob('image_*_batch_*.png'):
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass
                    self._names_migrated = True
                for path, published in list(self._published_files.items()):
                    if str(path) not in keep:
                        try:
                            current = path.stat()
                            if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) == (
                                    published.st_dev, published.st_ino, published.st_mtime_ns, published.st_size):
                                path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        self._published_files.pop(path, None)
            finally:
                self.lock.acquire()
            self.retired_pools = [pool for pool in self.retired_pools
                                  if any(thread.is_alive() for thread in pool._threads)]
            if not self.running and self.window is None:
                if self.pool:
                    self.pool.shutdown(wait=False)
                    self.retired_pools.append(self.pool)
                self.pool = None
                self.workers = 0
            elif not self.running and self.workers != self.desired_workers:
                if self.pool:
                    self.pool.shutdown(wait=False)
                    self.retired_pools.append(self.pool)
                self.workers = self.desired_workers
                self.pool = ThreadPoolExecutor(self.workers, thread_name_prefix='image-stitch')
            if self.window is not None and self.pool and self.workers == self.desired_workers:
                lo, hi = self.window
                order = (self.batch + sign * distance
                         for distance in range(max(self.batch - lo, hi - self.batch) + 1)
                         for sign in ((self.direction, -self.direction) if distance else (1,))
                         if lo <= self.batch + sign * distance <= hi)
                for batch in order:
                    if len(self.running) >= self.workers:
                        break
                    key = self.generation, batch
                    if batch in self.cache or batch in self.failed or key in self.running:
                        continue
                    future = self.pool.submit(self._compose, self.template, self.points,
                                              self.custom, batch, self.generation)
                    self.running[key] = future
                    future.add_done_callback(self._task_done)
            current = self.batch if self.window is not None else None
        for batch, generation, error in notices:
            if batch == current:
                self.dispatch(self.notify, batch, generation, error)

    def _task_done(self, future):
        with self.lock:
            closed = self.closed
        if closed:
            try:
                Path(future.result()[0]).unlink(missing_ok=True)
            except Exception:
                pass
        else:
            self._schedule()

    def _compose(self, template, points, custom, batch, generation):
        with self.lock:
            if (self.closed or generation != self.generation or self.window is None
                    or not self.window[0] <= batch <= self.window[1]):
                raise CancelledError()
        started = time.perf_counter()
        manager = template.video_stitch_snapshot()
        with self.lock:
            manager._custom_memory_budget = self.memory // max(1,self.workers) if self.memory is not None else None
        manager.set_action_count(batch)
        manager.img_count = batch * manager.count_per_action
        flist = manager.get_flist()
        if custom:
            manager.layout_params[32] = True
            manager.stitch_images(0, copy.deepcopy(points), flist=flist)
            manager.layout_params[32] = False
        flag = manager.stitch_images(0, copy.deepcopy(points), flist=flist)
        image = manager.show_stitch_img_and_customfunc_img(custom) if flag == 0 else None
        if image is None:
            raise RuntimeError(f'Stitch failed: batch={batch}, flag={flag}')
        state = {name: getattr(manager, name) for name in RENDER_STATE if hasattr(manager, name)}
        # Estimate decoded sources from composition geometry; do not reopen files.
        inputs = getattr(manager, 'img_resolution_origin', image.size)
        inputs = max(1, int(inputs[0])) * max(1, int(inputs[1])) * max(1, len(flist))
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f'__image_{generation}_{batch}_{time.time_ns()}.tmp'
        try:
            image.save(temporary, format='PNG', compress_level=1)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return temporary, state, image.width * image.height, inputs, time.perf_counter() - started

    def prepare_display(self, batch, deliver):
        with self.lock:
            entry = self.cache.get(batch)
            if not entry:
                return False
            key = self.generation, batch, entry[0]
            if key in (self.display_key, self.displayed_key):
                return True
            self.request_serial += 1
            serial = self.request_serial
            self.display_key = key
            if self.display_future is not None:
                self.display_future.cancel()
        def prepare():
            with Image.open(entry[0]) as source:
                image = source.convert('RGBA')
            return image, image.tobytes()
        future = self.display.submit(prepare)
        self.display_future = future
        def done(f):
            if f.cancelled():
                return
            try:
                result, error = f.result(), None
            except Exception as exc:
                result, error = None, str(exc)
            def on_gui():
                with self.lock:
                    if self.display_future is f:
                        self.display_future = None
                    if (self.closed or serial != self.request_serial or key != self.display_key
                            or key[0] != self.generation or batch != self.batch):
                        return
                    self.display_key = None
                    if error:
                        self.cache.pop(batch, None)
                        self.failed.discard(batch)
                    else:
                        self.displayed_key = key
                if error:
                    self._schedule()
                deliver(batch, key[0], result, entry[1], error)
            self.dispatch(on_gui)
        future.add_done_callback(done)
        return True

    def close(self):
        with self.lock:
            self.closed = True
            self.request_serial += 1
            completed = [f for f in self.running.values() if f.done()]
        for future in completed:
            self._task_done(future)
        for executor in (self.coordinator, self.pool, self.display):
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
