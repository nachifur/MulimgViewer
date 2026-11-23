"""Image pages and shared mosaic rendering for images, video and export."""
import copy
import hashlib
import json
import numpy as np
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .cache_layout import (
    CachedCanvas,
    cache_image_extension,
    component,
    open_rendered_canvas,
    page_name,
    remove_page_catalog,
    save_cache_image,
    write_page_catalog,
    write_source_catalog,
)
from .canvas import DiskCanvas, disk_backed, mosaic_working_bytes, render_lane, rgba_display
from .custom_func.contract import (
    active_cache_names,
    display_grid,
    display_indices,
    original_index,
    processing_indices,
    specification,
)
from .custom_pipeline import CustomPipeline, current_only
from .image_encoding import cache_quality, manager_cache_format
from .pipeline_executor import gather, prepared
from .playback_policy import PlaybackPacer, available_memory_bytes
from .render_layout import gap_pair
from .resources import cache_window, composition_workers


# Algorithm mosaics and final composition
def mosaic_request_key(manager,index,inputs,points,batch):
    params=copy.deepcopy(manager.layout_params)
    if len(params)>41:params[41]=manager_cache_format(manager)
    params[32]=False;params[37]=0;params[38]=False;params[39]='1,1';params[40]=False;params[33]='';params[36]=False;params[35]=1
    signature = []
    for path in inputs:
        info = os.stat(path)
        signature.append((str(path), info.st_size, info.st_mtime_ns))
    key='mosaic:'+hashlib.sha256(repr((params,cache_quality(manager),tuple(manager.gap_color),int(getattr(manager,'img_alpha',255)),signature,points,batch,
        repr(getattr(manager,'exif_display_config',None)))).encode('utf-8')).hexdigest()
    algorithm='original' if index is None else specification(manager._custom_algorithm_registry,index).get(
        'cache_name',manager._custom_algorithm_registry[index][0])
    # Distinguish an identity algorithm from original even when input paths match.
    key+=':'+algorithm
    return key,params,algorithm


def _finish_reference_geometry(render, geometry):
    """Settle geometry on early failure or after the deferred TIFF layout."""
    if geometry.done():
        return
    try:
        _, state = render.result()
        resolution = tuple(state['img_resolution_origin'])
    except BaseException as error:
        geometry.set_exception(error)
    else:
        geometry.set_result(resolution)


class MosaicStage:
    def __init__(self, cache):
        self.cache=cache
        self.pool=ThreadPoolExecutor(max(1,os.cpu_count() or 1),thread_name_prefix='algorithm-stitch')
        self.completed=0;self.seconds=0.

    @contextmanager
    def plan(self, manager, flist, batch, owner, epoch, points, cancelled,defer_prune=False):
        self.cache._initialize()
        plan=MosaicPlan(self,manager,flist,batch,owner,epoch,points,cancelled)
        try:yield plan
        finally:
            # A Future wakes its waiter before finishing its ready callbacks.
            # Stop late callbacks before releasing readers; otherwise a
            # callback could add a new pinned mosaic after this plan exited.
            with plan.lock:
                plan.closed=True
                with self.cache.lock:
                    for entry in plan.entries:entry['pins']-=1
                    self.cache.readers.notify_all()
            self.cache.request_prune() if defer_prune else self.cache._prune()

    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)


class MosaicPlan:
    def __init__(self, stage, manager, flist, batch, owner, epoch, points, cancelled):
        self.stage=stage;self.cache=stage.cache;self.manager=manager
        self.paths,self.groups=manager._normalize_flist_input(flist)
        self.paths=tuple(self.paths or ())
        self.batch=batch;self.owner=owner;self.epoch=epoch;self.points=points;self.cancelled=cancelled
        self.entries=[];self.futures={};self.lock=threading.RLock();self.closed=False
        # A reused reference future costs this page no new render work.
        self.reference_work_seconds = 0.
        self.indices=display_indices(manager._custom_algorithm_registry,manager.layout_params)
        self.reference=original_index(manager._custom_algorithm_registry)
        if self.reference is None or specification(manager._custom_algorithm_registry,self.reference)['identity']:
            self.futures[self.reference]=self._request(self.reference,self.paths)

    def ready(self,index,paths):
        with self.lock:
            if not self.closed and index not in self.futures and not self.cancelled() and not self.cache.closed:
                try:self.futures[index]=self._request(index,tuple(paths))
                except CancelledError:
                    # A window/close can invalidate the request after the
                    # callback's initial check. Deliver cancellation to the
                    # parent instead of logging an unhandled callback error.
                    future=Future();future.set_exception(CancelledError())
                    self.futures[index]=future

    def _request(self,index,inputs):
        key,params,algorithm=mosaic_request_key(self.manager,index,inputs,self.points,self.batch)
        with self.cache.lock:
            if self.cache.closed or self.cancelled():raise CancelledError()
            self.cache._retire_versions(key,algorithm,(self.owner,self.epoch,self.batch))
            entry=self.cache.entries.get(key)
            if entry is not None and entry['future'].done():
                try:
                    if not Path(entry['future'].result()[0]).is_file():entry=None
                except Exception:entry=None
            if entry is None:
                entry=dict(directory=self.cache.directory/f'result_mosaic_{uuid.uuid4().hex}',
                    users=set(),pins=0,used=time.monotonic(),bytes=0,page=self.batch,
                    cacheable=index is None or specification(self.manager._custom_algorithm_registry,index)['cacheable'],algorithm=algorithm)
                self.cache.entries[key]=entry
                try:
                    if index == self.reference:
                        entry['geometry'] = Future()
                        dependencies = ()
                    else:
                        dependencies = (self.reference_geometry,)
                    entry['future']=self.cache.scheduler.submit(self.stage.pool,self._build,index,inputs,params,entry,algorithm,
                        dependencies=dependencies,priority=lambda:self.cache._image_priority(self.owner,self.batch))
                    if index == self.reference:
                        geometry = entry['geometry']
                        entry['future'].add_done_callback(lambda done: _finish_reference_geometry(done, geometry))
                except BaseException:
                    self.cache.entries.pop(key,None);raise
            if index == self.reference:
                self.reference_geometry = entry['geometry']
            entry['pins']+=1;entry['users'].add((self.owner,self.epoch,self.batch))
            entry['used']=time.monotonic();self.entries.append(entry)
            return entry['future']

    def _build(self,index,inputs,params,entry,algorithm):
        prepare_started = time.perf_counter()
        manager=self.manager.video_stitch_snapshot()
        manager.layout_params=params
        if index != self.reference:
            params[6] = list(self.reference_geometry.result())
        manager._video_lazy_frames=True
        pixel_cache=getattr(self.cache,'pixel_cache',None)
        if pixel_cache is not None:manager._video_pixel_provider=pixel_cache.get
        manager._custom_results={} if index is None else {0:inputs}
        manager.set_action_count(self.batch)
        params[32]=index is not None
        prepared_layout=None;canvas_size=None
        # TIFF normalization can materialize pixels. Keep that legacy path
        # inside admission; JPEG/PNG use closed-file lazy descriptors here.
        if not any(Path(path).suffix.lower() in ('.tif','.tiff') for path in inputs):
            prepared_layout=manager.stitch_img_init(0,copy.deepcopy(self.points),flist=self.paths)
            layout,subprocessing,show=prepared_layout
            if not show:raise RuntimeError(f'{algorithm}: empty mosaic layout')
            if index == self.reference:
                # Other algorithms only need the normalization geometry. Their
                # own render admissions still enforce CPU and memory limits.
                entry['geometry'].set_result(tuple(manager.img_resolution_origin))
            canvas_size,_,_=manager.ImgF.layout_2d(layout,manager.gap_color,[],manager.img_preprocessing,subprocessing,
                [manager.img_vertical,manager.one_img_vertical,manager.img_unit_vertical],manager.onetitle,
                [manager.title_init,manager.title_preprocessing],measure_only=True)
        manager._disk_backed_canvas=disk_backed(canvas_size) if canvas_size is not None else None
        size=self.cache.composition_bytes(self.paths,{} if index is None else {0:inputs},manager,canvas_size=canvas_size)
        resident=size
        if manager._disk_backed_canvas:
            # Reserve the mode's lane to drain competing work, but validate
            # only resident scratch RAM: canvas pixels live in temporary maps.
            size=max(size,self.cache.budget.memory or size)
        def stale():return not self.cache.node_valid(self.owner,self.epoch,self.batch,algorithm)
        mapped = manager._disk_backed_canvas if self.cache.budget.memory is not None else None
        preparation_seconds = time.perf_counter() - prepare_started
        with render_lane(canvas_size or (0,0),lambda:self.cache._image_priority(self.owner,self.batch),stale,mapped=mapped), self.cache.budget.acquire(size,stale,priority=1,resident_size=resident,
                order=lambda:self.cache._image_priority(self.owner,self.batch),
                units=1/(1+len(processing_indices(self.manager._custom_algorithm_registry,self.manager.layout_params)))):
            started=time.perf_counter()
            manager._video_memory_budget=size
            def checkpoint():
                if stale():raise CancelledError()
            manager._render_checkpoint=checkpoint
            flag=manager.stitch_images(0,copy.deepcopy(self.points),flist=self.paths,prepared_layout=prepared_layout)
            if flag!=0 or manager.img is None:raise RuntimeError(f'{algorithm}: mosaic failed')
            state={name:getattr(manager,name) for name in RENDER_STATE if hasattr(manager,name)}
            state['_rendered_canvas_size'] = manager.img.size
            try:
                checkpoint()
                self.cache.request_prune()
                entry['directory'].mkdir(parents=True)
                path=entry['directory']/page_name(self.batch,cache_image_extension(self.manager))
                with open(path,'wb') as stream:save_cache_image(manager.img,stream,cache_image_extension(self.manager),checkpoint=checkpoint,jpeg_quality=cache_quality(self.manager))
                info=path.with_suffix('.json')
                info.write_text(json.dumps(dict(algorithm=algorithm,page=self.batch+1,
                    inputs=list(self.paths)),ensure_ascii=False,indent=2),encoding='utf-8')
                amount=path.stat().st_size+info.stat().st_size
                with self.cache.lock:
                    entry['bytes']=amount
                    entry['reserved']=0
                if stale():raise CancelledError()
                target=self.cache.visible.root/component(algorithm)/'stitched'
                entry['_public_target']=target;entry['_public_files']={'frames/'+path.name:path,'json/'+info.name:info}
                self.cache.publish_entry(entry,lambda:not self.cancelled())
                with self.cache.lock:
                    entry['bytes']=amount+entry.get('_visible_copied',0);entry['reserved']=0
                if pixel_cache is not None:
                    current=self.cache.windows.get(self.owner,(None,None,None))[2]
                    if not isinstance(manager.img,DiskCanvas) or self.batch==current:
                        pixel_cache.put(str(path),manager.img,priority=True)
                    pixel_cache.put_header(str(path),manager.img.size,manager.img.mode)
                render_seconds = time.perf_counter() - started
                if index == self.reference:
                    self.reference_work_seconds = preparation_seconds + render_seconds
                with self.cache.lock:
                    self.stage.completed+=1;self.stage.seconds+=render_seconds
                return str(path),state
            except BaseException:
                self.cache.visible.remove(entry);self.cache._remove(entry['directory']);raise
            finally:
                with self.cache.lock:entry['reserved']=0
                manager.clear_cache()

    def dependencies(self,processed):
        # Do not rely on the ordering of Future callbacks: a processing Future
        # can wake its consumers before its ready callback has finished.
        for index,paths in processed.items():self.ready(index,paths)
        return tuple(self.futures[index] for index in dict.fromkeys([self.reference]+self.indices))

    def compose(self, processed):
        # Compatibility for direct callers. Production keeps the context open
        # through final PNG publication so CPU and canvas RAM remain admitted.
        with self.composed(processed) as output:return output

    @contextmanager
    def composed(self, processed):
        for index,paths in processed.items():self.ready(index,paths)
        params=self.manager.layout_params
        algorithm_grid=bool(params[32] or params[38])
        rows,cols=display_grid(self.manager._custom_algorithm_registry,params)
        indices=self.indices
        slots=rows*cols
        artifacts={index:self.futures[index].result() for index in indices}
        reference=self.futures[self.reference].result()
        if self.cancelled():raise CancelledError()
        for entry in self.entries:self.cache.publish_entry(entry,lambda:not self.cancelled())
        if slots==1 and indices:
            path,state=artifacts[indices[0]]
            state=copy.deepcopy(state)
            state['_status_source_images']=reference[1].get('_status_source_images',())
            yield CachedCanvas(path,state['_rendered_canvas_size']),state
            return
        pixel_cache=getattr(self.cache,'pixel_cache',None)
        width=height=0
        for path,state in (artifacts.values() if artifacts else [reference]):
            w, h = state['_rendered_canvas_size']
            width, height = max(width, w), max(height, h)
        # The final algorithm grid is a separate layout level: retain the
        # configured horizontal/vertical gaps between its cached mosaics.
        gap_x,gap_y=gap_pair(params[3], 'func')
        canvas_width=width*cols+gap_x*(cols-1)
        canvas_height=height*rows+gap_y*(rows-1)
        charge=mosaic_working_bytes((canvas_width,canvas_height),width*height)
        with self.cache.budget.acquire(charge,self.cancelled,priority=2,
                order=lambda:self.cache._image_priority(self.owner,self.batch)):
            base_artifact=artifacts[indices[0]] if indices else reference
            from .canvas import new_canvas
            canvas=new_canvas('RGBA',(canvas_width,canvas_height),tuple(base_artifact[1]['gap_color']))
            state=copy.deepcopy(base_artifact[1])
            xy=[];ids=[];source_slots=[];blanks=set();titles=[]
            base_state=base_artifact[1]
            base=max(len(self.paths),max(base_state['xy_grids_id_list'],default=-1)+1)
            for slot in range(slots):
                if algorithm_grid and params[40]:row=slot%rows;col=slot//rows
                else:row,col=divmod(slot,cols)
                x,y=col*(width+gap_x),row*(height+gap_y)
                present=slot<len(indices)
                current=artifacts[indices[slot]][1] if present else base_state
                if present:
                    path=artifacts[indices[slot]][0]
                    cached=pixel_cache.get(path) if pixel_cache is not None else None
                    if cached is not None:canvas.paste(cached,(x,y))
                    else:
                        with open_rendered_canvas(path,current['_rendered_canvas_size']) as image:canvas.paste(image,(x,y))
                for point,source_id in zip(current['xy_grid'],current['xy_grids_id_list']):
                    output_id=slot*base+int(source_id)
                    xy.append((float(point[0])+x,float(point[1])+y));ids.append(output_id)
                    if not present or int(source_id)>=len(self.paths) or source_id in current.get('_blank_img_ids',()):blanks.add(output_id)
                source_slots.extend([i if present and i<len(self.paths) else -1 for i in range(base)])
                if present:
                    for title in current.get('pdf_title_layers',[]):
                        title=copy.deepcopy(title);title['x']+=x;title['y']+=y;titles.append(title)
            state.update(xy_grid=np.array(xy),xy_grids_id_list=ids,_status_source_slots=tuple(source_slots),
                _status_source_images=reference[1].get('_status_source_images',()),
                _blank_img_ids=blanks,flist=list(self.paths),_flist_groups=self.groups,
                _show_all_func_enabled=algorithm_grid,_show_all_func_layout=(rows,cols) if algorithm_grid else None,
                _original_row_col=list(params[0]) if algorithm_grid else None,
                _show_all_func_expanded_row_col=[params[0][0]*rows,params[0][1]*cols] if algorithm_grid else None,
                _func_layout_vertical=bool(params[40]),pdf_title_layers=titles)
            state['_rendered_canvas_size'] = canvas.size
            yield canvas,state


# Image page cache and playback
RENDER_STATE = (
    'xy_grid', 'xy_grids_id_list', 'crop_points', 'img_resolution_origin',
    'img_resolution_show', 'img_resolution', 'gap_color', 'title_setting',
    'pdf_title_layers', '_last_title_layout', 'flist', '_flist_groups', 'full_exif_cache', 'title_max_size',
    '_status_source_slots', '_status_source_images',
    '_show_all_func_enabled', '_show_all_func_layout', '_original_row_col',
    '_show_all_func_expanded_row_col', '_func_layout_vertical', '_blank_img_ids',
)


class ImagePipeline:
    def __init__(self, directory, notify, dispatch):
        self.directory = Path(directory)
        self.cache_root=(self.directory.parent.parent if self.directory.name=='frames' and self.directory.parent.name=='composed'
                         else self.directory.parent)
        self.notify, self.dispatch = notify, dispatch
        self.lock = threading.RLock()
        self.coordinator = ThreadPoolExecutor(1, thread_name_prefix='image-schedule')
        self.display = ThreadPoolExecutor(1, thread_name_prefix='image-display')
        self.pool = None
        self.retired_pools = []
        self.workers = 0
        self.desired_workers = 1
        self.generation = uuid.uuid4().hex
        self.supply_pacer = PlaybackPacer()
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
        self.processing = CustomPipeline(self.cache_root/'.work'/'processed',public_root=self.cache_root/'algorithms')
        self.processing.mosaic_stage=MosaicStage(self.processing)

    def _schedule(self):
        with self.lock:
            if self.closed or self._pump_queued:
                return
            self._pump_queued = True
            self.coordinator.submit(self._pump)

    def invalidate(self):
        with self.lock:
            self.generation = uuid.uuid4().hex
            self.supply_pacer.reset()
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
                self._catalog_pending=True
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
        self.processing.configure(budget,memory)
        self._schedule()

    def _pump(self):
        # This is the only thread that publishes/deletes PNGs and resizes pools.
        available = available_memory_bytes()
        with self.lock:
            template=getattr(self,'template',None)
            current_window=self.window
            current=getattr(self,'batch',0)
        if template is not None and current_window is not None:
            if getattr(self,'_catalog_pending',False):
                self._catalog_pending=False
                write_source_catalog(template,self.cache_root,split_media=True)
            self.processing.set_window('image',('image',repr(getattr(template,'input_path',''))),current_window,current,active_cache_names(template))
            self.processing.request_prune()
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
                        path = self.directory / page_name(batch,cache_image_extension(template))
                        os.replace(temporary, path)
                        self._published_files[path] = path.stat()
                        write_page_catalog(path,batch,'image',state.get('flist',()),state.get('_rendered_canvas_size'))
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
                    self.supply_pacer.publish(generation, batch, time.perf_counter())
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
                    root=self.cache_root.resolve()
                    for name in ('image_stitch_cache','stitch_cache','custom_cache'):
                        legacy=self.cache_root/name
                        if legacy!=self.directory and legacy.is_dir() and legacy.resolve().parent==root:
                            shutil.rmtree(str(legacy.resolve()),ignore_errors=True)
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
                                remove_page_catalog(path)
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
                # Measure complete, usable pages across all processing stages.
                # Cache hits and full-window idle time are not new production.
                wanted = [batch for batch in range(lo, hi + 1)
                          if batch not in self.cache and batch not in self.failed
                          and (not current_only(self.template) or batch == self.batch)]
                self.supply_pacer.request(self.generation, wanted, self.window,
                                          self.batch, self.direction, time.perf_counter())
                order = (self.batch + sign * distance
                         for distance in range(max(self.batch - lo, hi - self.batch) + 1)
                         for sign in ((self.direction, -self.direction) if distance else (1,))
                         if lo <= self.batch + sign * distance <= hi)
                for batch in order:
                    if current_only(self.template) and batch!=self.batch:continue
                    if len(self.running) >= self.workers:
                        break
                    key = self.generation, batch
                    if batch in self.cache or batch in self.failed or key in self.running:
                        continue
                    future = self.processing.scheduler.submit(self.pool,self._compose, self.template, self.points,
                                              self.custom, batch, self.generation,
                                              priority=lambda batch=batch:self.processing._image_priority('image',batch))
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
        params=template.layout_params
        if len(params)>38 and getattr(template,'_custom_algorithm_registry',None) is not None:
            return self.processing.scheduler.start(self._compose_steps,template,points,batch,generation,
                priority=lambda:self.processing._image_priority('image',batch))
        return self._compose_pixels(template,points,custom,batch,generation)

    def _compose_steps(self,template,points,batch,generation):
        manager=template.video_stitch_snapshot();manager.set_action_count(batch)
        with self.lock:window=self.window
        if window is None:raise CancelledError()
        epoch=('image',repr(manager.input_path))
        def cancelled():return self.closed or generation!=self.generation
        started=time.perf_counter();paths=manager.get_flist()
        with ExitStack() as stack:
            plan=stack.enter_context(self.processing.mosaic_stage.plan(manager,paths,batch,'image',epoch,points,cancelled,defer_prune=True))
            results=yield from prepared(self.processing.prepare_steps(manager,paths,batch,'image',epoch,cancelled,on_ready=plan.ready,defer_prune=True),stack)
            yield gather(plan.dependencies(results))
            if cancelled():raise CancelledError()
            def render():
                if cancelled():raise CancelledError()
                with plan.composed(results) as (image,state):
                    self.directory.mkdir(parents=True,exist_ok=True)
                    temporary=self.directory/f'__image_{generation}_{batch}_{time.time_ns()}.tmp'
                    try:save_cache_image(image,temporary,cache_image_extension(manager),jpeg_quality=cache_quality(manager))
                    except BaseException:
                        temporary.unlink(missing_ok=True);raise
                    inputs=state.get('img_resolution_origin',image.size)
                    return temporary,state,image.width*image.height,int(inputs[0])*int(inputs[1])*len(state['flist']),time.perf_counter()-started
            return (yield self.pool.submit(render))

    def _compose_pixels(self, template, points, custom, batch, generation):
        with self.lock:
            if (self.closed or generation != self.generation or self.window is None
                    or not self.window[0] <= batch <= self.window[1]):
                raise CancelledError()
        started = time.perf_counter()
        manager = template.video_stitch_snapshot()
        if getattr(manager,'_custom_results',None) is not None:
            manager._video_lazy_frames=True
            manager._video_memory_budget=manager._custom_composition_budget
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
        state['_rendered_canvas_size'] = image.size
        # Estimate decoded sources from composition geometry; do not reopen files.
        inputs = getattr(manager, 'img_resolution_origin', image.size)
        inputs = max(1, int(inputs[0])) * max(1, int(inputs[1])) * max(1, len(flist))
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f'__image_{generation}_{batch}_{time.time_ns()}.tmp'
        try:
            save_cache_image(image,temporary,cache_image_extension(manager),jpeg_quality=cache_quality(manager))
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
            with open_rendered_canvas(entry[0],entry[1].get('_rendered_canvas_size')) as source:
                return rgba_display(source)
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
        self.processing.close()
        for future in completed:
            self._task_done(future)
        for executor in (self.coordinator, self.pool, self.display):
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
