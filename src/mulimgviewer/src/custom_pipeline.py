"""Bounded disk-backed algorithm stage, shared by image and video playback.

Only metadata is queued. User pixels exist while a task holds a resource permit;
completed results are PNG paths. Waiters never hold a pixel/CPU permit.
"""
import hashlib
import json
import re
import os
import shutil
import threading
import time
import uuid
import weakref
from collections import deque
from concurrent.futures import ThreadPoolExecutor, CancelledError
from contextlib import contextmanager
from pathlib import Path

from PIL import Image
from .custom_func.contract import specification, processing_indices
from .custom_func.runtime import state, execution_lock
from .cache_layout import VisibleCache, source_names, component


def readable_name(value, limit):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',str(value)).strip(' .')[:limit] or 'unnamed'


def current_only(manager):
    registry=getattr(manager,'_custom_algorithm_registry',None)
    params=manager.layout_params
    if not registry or len(params)<=38 or not (params[32] or params[38]):return False
    indices=processing_indices(registry,params)
    return any(specification(registry,index)['ordered'] for index in indices)


class WorkBudget:
    def __init__(self):
        self.condition = threading.Condition()
        self.limit, self.memory = 1, None
        self.active = self.bytes = 0
        self.waiting=[];self.serial=0;self.active_by_stage={0:0,1:0,2:0};self.service={}

    def configure(self, workers, memory):
        with self.condition:
            self.limit, self.memory = max(1,int(workers)), memory
            self.condition.notify_all()

    @contextmanager
    def acquire(self, size=0, cancelled=lambda:False, priority=0):
        size=max(0,int(size))
        with self.condition:
            self.serial+=1;ticket=(-priority,self.serial)
            self.waiting.append(ticket)
            try:
                while True:
                    if cancelled():raise CancelledError()
                    if self.memory is not None and size > self.memory:
                        raise MemoryError('Custom processing exceeds the memory budget; reduce layout or batch size')
                    if (self.active < self.limit and ticket==min(self.waiting)
                            and (self.memory is None or self.bytes+size <= self.memory)):break
                    self.condition.wait(.05)
            finally:
                self.waiting.remove(ticket);self.condition.notify_all()
            self.active+=1;self.bytes+=size
            self.active_by_stage[priority]=self.active_by_stage.get(priority,0)+1
        started=time.perf_counter()
        try:yield
        finally:
            with self.condition:
                self.active-=1;self.bytes-=size;self.condition.notify_all()
                self.active_by_stage[priority]-=1
                elapsed=time.perf_counter()-started
                self.service[priority]=.8*self.service.get(priority,elapsed)+.2*elapsed


class CustomPipeline:
    def __init__(self, directory, disk_limit=4*1024**3, free_reserve=256*1024**2, public_root=None):
        self.directory=Path(directory).resolve()
        self.disk_limit=max(1,int(disk_limit))
        self.free_reserve=max(0,int(free_reserve))
        self.lock=threading.RLock()
        self.budget=WorkBudget()
        self.pool=ThreadPoolExecutor(max(1,os.cpu_count() or 1),thread_name_prefix='custom-process')
        self.entries={};self.windows={};self.closed=False
        self.history={};self.hits=self.misses=0
        self.peak_active=0
        self._initialized=False
        self._init_lock=threading.Lock()
        self.visible=VisibleCache(public_root or self.directory/'catalog',self._reserve_visible,self._release_visible)
        self.mosaic_stage=None

    def _reserve_visible(self,entry,size):
        with self.lock:
            total=sum(e.get('bytes',0)+e.get('reserved',0) for e in self.entries.values())
            if total+size>self.disk_limit:raise OSError('Cache disk budget exceeded while copying an artifact')
            entry['reserved']=entry.get('reserved',0)+size
        if shutil.disk_usage(self.directory).free<size+self.free_reserve:raise OSError('Insufficient cache disk space')

    def _release_visible(self,entry,size):
        with self.lock:
            entry['bytes']=max(0,entry.get('bytes',0)-size)
            entry['_visible_copied']=max(0,entry.get('_visible_copied',0)-size)

    def configure(self, workers, memory):
        self.budget.configure(workers,memory)

    def set_window(self, owner, epoch, window, current, active=None):
        # Metadata only: callable from the GUI without disk access.
        with self.lock:
            self.windows={owner:(epoch,tuple(window),current)}
            self.active_names=active

    def node_valid(self,owner,epoch,batch,algorithm):
        return self._valid(owner,epoch,batch) and (getattr(self,'active_names',None) is None or algorithm in self.active_names)

    def _valid(self, owner, epoch, batch):
        value=self.windows.get(owner)
        return not self.closed and value is not None and value[0]==epoch and value[1][0]<=batch<=value[1][1]

    def _initialize(self):
        with self._init_lock:
            if self._initialized:return
            self.directory.mkdir(parents=True,exist_ok=True)
            # This directory belongs exclusively to this pipeline instance.
            for path in self.directory.iterdir():
                if path.is_dir() and path.name.startswith(('result_','tmp_')):
                    self._remove(path)
            self.visible.clear_owned()
            self._initialized=True

    def _remove(self, path):
        resolved=Path(path).resolve()
        if resolved.parent != self.directory:
            raise ValueError('Custom cache cleanup escaped its directory')
        shutil.rmtree(str(resolved),ignore_errors=True)

    def publish_entry(self,entry,valid=lambda:True):
        if '_public_target' in entry and not self.visible.current(entry):
            with self.lock:
                base=max(0,entry.get('bytes',0)-entry.get('_visible_copied',0))
            self.visible.publish(entry['_public_target'],entry['_public_files'],entry,valid)
            if base:
                with self.lock:
                    entry['bytes']=base+entry.get('_visible_copied',0);entry['reserved']=0

    def _prune(self, reserve=0):
        # Workers/coordinators only; no GUI or cache-state lock spans I/O.
        remove=[]
        with self.lock:
            total=sum(entry.get('bytes',0)+entry.get('reserved',0) for entry in self.entries.values())
            for key,entry in sorted(self.entries.items(),key=lambda pair:pair[1]['used']):
                entry['users']={user for user in entry['users'] if self._valid(*user)}
                if not entry['pins'] and entry['future'].done() and (
                        not entry['users'] or not entry.get('cacheable',True) or total+reserve>self.disk_limit
                        or entry['future'].cancelled() or entry['future'].exception() is not None
                        or (getattr(self,'active_names',None) is not None and entry.get('algorithm') not in self.active_names)):
                    self.entries.pop(key,None);total-=entry.get('bytes',0);remove.append((entry['directory'],entry))
        for path,entry in remove:
            self.visible.remove(entry);self._remove(path)

    def _descriptor(self, manager, paths, index, owner, epoch, batch):
        registry=manager._custom_algorithm_registry
        spec=specification(registry,index)
        signature=[];pixels=0
        for value in paths:
            path=Path(value).resolve();info=path.stat()
            signature.append((str(path),info.st_size,info.st_mtime_ns))
            with Image.open(path) as image:pixels+=image.width*image.height
        version=(registry[index],signature,batch)
        if not spec['cacheable']:version+=(owner,repr(epoch),batch)
        digest=hashlib.sha256(repr(version).encode('utf-8')).hexdigest()
        size=max(32*1024**2,pixels*16+spec['working_set_bytes'])
        return digest,spec,size

    def composition_bytes(self, flist, results, manager=None):
        pixels=0;largest=0;width=height=1
        for path in [p for group in results.values() for p in group]+list(flist):
            with Image.open(path) as image:
                pixels+=image.width*image.height
                largest=max(largest,image.width*image.height)
                width=max(width,image.width);height=max(height,image.height)
        if manager is None:return max(32*1024**2,pixels*16)
        params=manager.layout_params
        resolution=params[6]
        if resolution[0]>0 and resolution[1]>0:width,height=resolution
        elif resolution[0]>0:height=height*resolution[0]/width;width=resolution[0]
        elif resolution[1]>0:width=width*resolution[1]/height;height=resolution[1]
        width=max(1,width*params[4][0]);height=max(1,height*params[4][1])
        rows=cols=1
        for grid in params[:3]:rows*=grid[0];cols*=grid[1]
        if params[38]:
            extra_rows,extra_cols=map(int,params[39].split(','));rows*=extra_rows;cols*=extra_cols
        gap=max([0]+[float(value) for value in params[3]])
        title=params[17]
        title_height=2*float(title[8]) if title[1] else 0
        canvas=(width+gap)*cols*(height+gap+title_height)*rows
        variants=2 if params[32] else 1
        # One decoded source tile at a time, plus canvases and display copies.
        return max(32*1024**2,int(largest*12+canvas*16*variants))

    @contextmanager
    def prepare(self, manager, flist, batch, owner, epoch, cancelled=lambda:False, on_ready=None):
        params=manager.layout_params
        if len(params)<=38 or not (params[32] or params[38]):
            yield {};return
        self._initialize()
        paths,_=manager._normalize_flist_input(flist)
        paths=tuple(paths or ())
        registry=manager._custom_algorithm_registry
        if not registry and params[32]:raise ValueError('No custom algorithms are installed')
        selected=params[37] if 0<=params[37]<len(registry) else 0
        indices=processing_indices(registry,params)
        leases=[];lease_indices={};results={}
        try:
            for index in indices:
                if cancelled():raise CancelledError()
                key,spec,size=self._descriptor(manager,paths,index,owner,epoch,batch)
                algorithm=spec.get('cache_name',registry[index][0])
                if spec['identity']:
                    results[index]=paths
                    if on_ready is not None:on_ready(index,paths)
                    continue
                with self.lock:
                    if not self.node_valid(owner,epoch,batch,algorithm):raise CancelledError()
                    if spec['ordered'] and batch!=self.windows[owner][2]:raise CancelledError()
                    entry=self.entries.get(key)
                    if entry is not None and entry['future'].done():
                        try:
                            entry['future'].result()
                        except Exception:entry=None
                        if entry is None:self.entries.pop(key,None)
                    if entry is None:
                        name=readable_name(registry[index][0],32)
                        entry=dict(directory=self.directory/f'result_{name}__page_{batch+1:06d}__{uuid.uuid4().hex[:12]}',users=set(),pins=0,
                                   used=time.monotonic(),bytes=0,cacheable=spec['cacheable'],algorithm=algorithm)
                        self.entries[key]=entry;self.misses+=1
                        entry['future']=self.pool.submit(self._process,manager,paths,index,spec,size,
                            entry,owner,epoch,batch,cancelled)
                    else:self.hits+=1
                    entry['pins']+=1;entry['used']=time.monotonic()
                    entry['users'].add((owner,epoch,batch));leases.append(entry)
                    lease_indices[index]=entry
                    results[index]=entry['future']
                if on_ready is not None:
                    callback_ref=weakref.WeakMethod(on_ready) if getattr(on_ready,'__self__',None) is not None else weakref.ref(on_ready)
                    def ready(future,index=index,callback_ref=callback_ref):
                        callback=callback_ref()
                        if callback is not None and not future.cancelled() and future.exception() is None:callback(index,future.result())
                    entry['future'].add_done_callback(ready)
            for index,future in list(results.items()):
                if hasattr(future,'result'):
                    paths_ready=future.result()
                    if not all(Path(path).is_file() for path in paths_ready):
                        entry=lease_indices[index]
                        _,spec,size=self._descriptor(manager,paths,index,owner,epoch,batch)
                        with self.lock:
                            if entry['future'] is future:
                                entry['bytes']=0
                                entry['future']=self.pool.submit(self._process,manager,paths,index,spec,size,
                                    entry,owner,epoch,batch,cancelled)
                            future=entry['future']
                        paths_ready=future.result()
                    results[index]=paths_ready
            if cancelled():raise CancelledError()
            for entry in leases:self.publish_entry(entry,lambda:not cancelled())
            yield results
        finally:
            with self.lock:
                for entry in leases:entry['pins']-=1
            self._prune()

    def _process(self, manager, paths, index, spec, size, entry, owner, epoch, batch, cancelled):
        from .custom_func.main import main, device_context
        def stale():
            return not self.node_valid(owner,epoch,batch,spec.get('cache_name',manager._custom_algorithm_registry[index][0]))
        previous=(getattr(state,'registry',None),getattr(state,'preview',False),getattr(state,'session',None),
                  getattr(state,'sequence_context',None))
        state.registry=manager._custom_algorithm_registry
        state.session=manager._custom_algorithm_session;state.preview=True
        state.sequence_context=(owner,epoch,batch)
        temporary=self.directory/f'tmp_{uuid.uuid4().hex}'
        images=[];outputs=[]
        try:
            with device_context(spec['device']), self.budget.acquire(size,stale):
                started=time.perf_counter()
                with self.lock:self.peak_active=max(self.peak_active,self.budget.active)
                for path in paths:
                    with Image.open(path) as image:images.append(image.convert('RGB'))
                outputs=list(main(images,'',name_list=[Path(p).name for p in paths],algorithm_type=index))
                if len(outputs)!=len(paths) or not all(isinstance(image,Image.Image) for image in outputs):
                    raise ValueError('Custom main must return one Pillow image per input, in input order')
                if stale():raise CancelledError()
                self._prune()
                temporary.mkdir(parents=True)
                required=sum(image.width*image.height*4+65536 for image in outputs)
                self._prune(required)
                with self.lock:
                    retained=sum(value.get('bytes',0)+value.get('reserved',0) for value in self.entries.values())
                    if required+retained>self.disk_limit:
                        raise OSError('Custom result cache disk budget exceeded; reduce cache window or output size')
                    entry['reserved']=required
                if shutil.disk_usage(self.directory).free<required+self.free_reserve:
                    raise OSError('Custom result cache disk budget exceeded; reduce cache window or output size')
                names=source_names(manager,paths)
                for name,image in zip(names,outputs):
                    (temporary/name).parent.mkdir(parents=True,exist_ok=True)
                    image.save(temporary/name,format='PNG',compress_level=1)
                (temporary/'cache_info.json').write_text(json.dumps(dict(algorithm=manager._custom_algorithm_registry[index][0],
                    page=batch+1,cache_version=spec['cache_version'],inputs=list(paths),outputs=names),
                    ensure_ascii=False,indent=2),encoding='utf-8')
                amount=sum(path.stat().st_size for path in temporary.rglob('*') if path.is_file())
                if stale():raise CancelledError()
                # Atomic directory publication: consumers see all results together.
                if entry['directory'].exists():self._remove(entry['directory'])
                os.replace(str(temporary),str(entry['directory']))
                algorithm=component(manager._custom_algorithm_registry[index][0])
                visible=self.visible.root/algorithm/'processed'/f'page_{batch+1:06d}'
                entry['_public_target']=visible
                entry['_public_files']={name:entry['directory']/name for name in names+['cache_info.json']}
                self.publish_entry(entry,lambda:not cancelled())
                with self.lock:
                    entry['bytes']=amount+entry.get('_visible_copied',0)
                    entry['reserved']=0
                    self.history.setdefault(index,deque(maxlen=32)).append(time.perf_counter()-started)
                return tuple(str(entry['directory']/name) for name in names)
        finally:
            with self.lock:entry['reserved']=0
            state.registry,state.preview,state.session,state.sequence_context=previous
            for image in {id(image):image for image in images+outputs if isinstance(image,Image.Image)}.values():image.close()
            self._remove(temporary)

    def snapshot(self):
        with self.lock:
            return dict(hits=self.hits,misses=self.misses,active=self.budget.active,
                limit=self.budget.limit,bytes=sum(e.get('bytes',0) for e in self.entries.values()),
                stages=dict(self.budget.active_by_stage),stage_seconds=dict(self.budget.service),
                service={str(k):sum(v)/len(v) for k,v in self.history.items() if v})

    def close(self):
        with self.lock:self.closed=True;self.windows.clear()
        with self.budget.condition:self.budget.condition.notify_all()
        if self.mosaic_stage is not None:self.mosaic_stage.close()
        self.pool.shutdown(wait=False,cancel_futures=True)
