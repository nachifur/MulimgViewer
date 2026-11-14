"""Cache each algorithm mosaic, then compose mosaics without rerendering tiles."""
import copy
import hashlib
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, CancelledError, Future
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image
from .cache_layout import page_name, component, CachedCanvas
from .custom_func.contract import specification, original_index, display_indices, display_grid


class MosaicStage:
    def __init__(self, cache):
        self.cache=cache
        self.pool=ThreadPoolExecutor(max(1,os.cpu_count() or 1),thread_name_prefix='algorithm-stitch')
        self.completed=0;self.seconds=0.

    @contextmanager
    def plan(self, manager, flist, batch, owner, epoch, points, cancelled):
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
            self.cache._prune()

    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)


class MosaicPlan:
    def __init__(self, stage, manager, flist, batch, owner, epoch, points, cancelled):
        self.stage=stage;self.cache=stage.cache;self.manager=manager
        self.paths,self.groups=manager._normalize_flist_input(flist)
        self.paths=tuple(self.paths or ())
        self.batch=batch;self.owner=owner;self.epoch=epoch;self.points=points;self.cancelled=cancelled
        self.entries=[];self.futures={};self.lock=threading.RLock();self.closed=False
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
        params=copy.deepcopy(self.manager.layout_params)
        params[32]=False;params[37]=0;params[38]=False;params[39]='1,1';params[40]=False;params[33]='';params[36]=False
        signature=[(str(path),Path(path).stat().st_size,Path(path).stat().st_mtime_ns) for path in inputs]
        key='mosaic:'+hashlib.sha256(repr((params,tuple(self.manager.gap_color),signature,self.points,self.batch,
            repr(getattr(self.manager,'exif_display_config',None)))).encode('utf-8')).hexdigest()
        algorithm='original' if index is None else specification(self.manager._custom_algorithm_registry,index).get(
            'cache_name',self.manager._custom_algorithm_registry[index][0])
        # Distinguish an identity algorithm from original even when input paths match.
        key+=':'+algorithm
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
                try:entry['future']=self.stage.pool.submit(self._build,index,inputs,params,entry,algorithm)
                except BaseException:
                    self.cache.entries.pop(key,None);raise
            entry['pins']+=1;entry['users'].add((self.owner,self.epoch,self.batch))
            entry['used']=time.monotonic();self.entries.append(entry)
            return entry['future']

    def _build(self,index,inputs,params,entry,algorithm):
        from .image_pipeline import RENDER_STATE
        manager=self.manager.video_stitch_snapshot()
        manager.layout_params=params
        if index != self.reference:
            reference=self.futures[self.reference].result()[1]
            params[6]=list(reference['img_resolution_origin'])
        manager._video_lazy_frames=True
        pixel_cache=getattr(self.cache,'pixel_cache',None)
        if pixel_cache is not None:manager._video_pixel_provider=pixel_cache.get
        manager._custom_results={} if index is None else {0:inputs}
        size=self.cache.composition_bytes(self.paths,{} if index is None else {0:inputs},manager)
        def stale():return not self.cache.node_valid(self.owner,self.epoch,self.batch,algorithm)
        with self.cache.budget.acquire(size,stale,priority=1):
            started=time.perf_counter()
            manager._video_memory_budget=size
            manager.set_action_count(self.batch)
            params[32]=index is not None
            flag=manager.stitch_images(0,copy.deepcopy(self.points),flist=self.paths)
            if flag!=0 or manager.img is None:raise RuntimeError(f'{algorithm}: mosaic failed')
            state={name:getattr(manager,name) for name in RENDER_STATE if hasattr(manager,name)}
            try:
                self.cache._prune()
                entry['directory'].mkdir(parents=True)
                path=entry['directory']/page_name(self.batch)
                with open(path,'wb') as stream:manager.img.save(stream,format='PNG',compress_level=1)
                info=path.with_suffix('.json')
                info.write_text(json.dumps(dict(algorithm=algorithm,page=self.batch+1,
                    inputs=list(self.paths)),ensure_ascii=False,indent=2),encoding='utf-8')
                amount=path.stat().st_size+info.stat().st_size
                with self.cache.lock:
                    entry['bytes']=amount
                    entry['reserved']=0
                if stale():raise CancelledError()
                target=self.cache.visible.root/component(algorithm)/'stitched'
                entry['_public_target']=target;entry['_public_files']={path.name:path,info.name:info}
                self.cache.publish_entry(entry,lambda:not self.cancelled())
                with self.cache.lock:
                    entry['bytes']=amount+entry.get('_visible_copied',0);entry['reserved']=0
                if pixel_cache is not None:
                    pixel_cache.put(str(path),manager.img,priority=True)
                    pixel_cache.put_header(str(path),manager.img.size,manager.img.mode)
                with self.cache.lock:
                    self.stage.completed+=1;self.stage.seconds+=time.perf_counter()-started
                return str(path),state
            except BaseException:
                self.cache.visible.remove(entry);self.cache._remove(entry['directory']);raise
            finally:
                with self.cache.lock:entry['reserved']=0
                manager.clear_cache()

    def compose(self, processed):
        for index,paths in processed.items():self.ready(index,paths)
        params=self.manager.layout_params
        algorithm_grid=bool(params[32] or params[38])
        rows,cols=display_grid(self.manager._custom_algorithm_registry,params)
        indices=self.indices
        slots=rows*cols
        artifacts={index:self.futures[index].result() for index in indices}
        self.futures[self.reference].result()
        if self.cancelled():raise CancelledError()
        for entry in self.entries:self.cache.publish_entry(entry,lambda:not self.cancelled())
        if slots==1:
            path,state=artifacts[indices[0]]
            return CachedCanvas(path),copy.deepcopy(state)
        pixel_cache=getattr(self.cache,'pixel_cache',None)
        width=height=0
        for path,state in artifacts.values():
            cached=(pixel_cache.get(path) or pixel_cache.get(('header',path))) if pixel_cache is not None else None
            if cached is not None:width=max(width,cached.width);height=max(height,cached.height)
            else:
                with Image.open(path) as image:width=max(width,image.width);height=max(height,image.height)
        charge=max(32*1024**2,width*height*slots*16+width*height*8)
        with self.cache.budget.acquire(charge,self.cancelled,priority=2):
            canvas=Image.new('RGBA',(width*cols,height*rows),tuple(artifacts[indices[0]][1]['gap_color']))
            state=copy.deepcopy(artifacts[indices[0]][1])
            xy=[];ids=[];source_slots=[];blanks=set();titles=[]
            base_state=artifacts[indices[0]][1]
            base=max(len(self.paths),max(base_state['xy_grids_id_list'],default=-1)+1)
            for slot in range(slots):
                if algorithm_grid and params[40]:row=slot%rows;col=slot//rows
                else:row,col=divmod(slot,cols)
                x,y=col*width,row*height
                present=slot<len(indices)
                current=artifacts[indices[slot]][1] if present else base_state
                if present:
                    path=artifacts[indices[slot]][0]
                    cached=pixel_cache.get(path) if pixel_cache is not None else None
                    if cached is not None:canvas.paste(cached,(x,y))
                    else:
                        with Image.open(path) as image:canvas.paste(image,(x,y))
                for point,source_id in zip(current['xy_grid'],current['xy_grids_id_list']):
                    output_id=slot*base+int(source_id)
                    xy.append((float(point[0])+x,float(point[1])+y));ids.append(output_id)
                    if not present or int(source_id)>=len(self.paths) or source_id in current.get('_blank_img_ids',()):blanks.add(output_id)
                source_slots.extend([i if present and i<len(self.paths) else -1 for i in range(base)])
                if present:
                    for title in current.get('pdf_title_layers',[]):
                        title=copy.deepcopy(title);title['x']+=x;title['y']+=y;titles.append(title)
            state.update(xy_grid=np.array(xy),xy_grids_id_list=ids,_status_source_slots=tuple(source_slots),
                _blank_img_ids=blanks,flist=list(self.paths),_flist_groups=self.groups,
                _show_all_func_enabled=algorithm_grid,_show_all_func_layout=(rows,cols) if algorithm_grid else None,
                _original_row_col=list(params[0]) if algorithm_grid else None,
                _show_all_func_expanded_row_col=[params[0][0]*rows,params[0][1]*cols] if algorithm_grid else None,
                _func_layout_vertical=bool(params[40]),pdf_title_layers=titles)
            return canvas,state
