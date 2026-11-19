"""Background export owns immutable settings and an independent video decoder."""
from .jpeg_policy import jpeg_quality, ffmpeg_jpeg_args
import copy
import hashlib
import shutil
import subprocess
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor, CancelledError
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryFile
from types import SimpleNamespace
import wx
from .export_controller import save_viewer
from .video_paths import frame_filename, cache_extension, manager_cache_format, lossless_export
from .video_tools import resolve_video_tools
from .video_decoder import DecoderBank, av
from .cache_layout import save_cache_image


class ExportControl:
    """Cooperative pause: running kernels finish, queued work waits without GUI locks."""
    def __init__(self,cancel):
        self.cancel=cancel;self.ready=threading.Event();self.ready.set()
        self.lock=threading.Lock();self.paused=False;self.acknowledged=False;self.on_paused=None
        self.working_threads={};self.waiting_threads=set();self.work_budget=None

    @contextmanager
    def working(self):
        thread=threading.get_ident()
        with self.lock:self.working_threads[thread]=self.working_threads.get(thread,0)+1
        try:yield
        finally:
            with self.lock:
                depth=self.working_threads[thread]-1
                if depth:self.working_threads[thread]=depth
                else:self.working_threads.pop(thread,None)

    def set_budget(self,budget):
        with self.lock:self.work_budget=budget

    def active_count(self):
        with self.lock:
            count=len(set(self.working_threads)-self.waiting_threads)
            budget=self.work_budget
            waiting=set(self.waiting_threads)
        if budget is not None:
            with budget.condition:count+=budget.active-len(budget.active_threads & waiting)
        return count

    def toggle(self):
        with self.lock:
            self.paused=not self.paused;self.acknowledged=False
            if self.paused:self.ready.clear()
            else:self.ready.set()
            return self.paused

    def checkpoint(self):
        thread=threading.get_ident()
        try:
            while True:
                if self.cancel.is_set():raise CancelledError()
                notify=None
                with self.lock:
                    if not self.paused:break
                    self.waiting_threads.add(thread)
                    if not self.acknowledged:
                        self.acknowledged=True;notify=self.on_paused
                if notify is not None:notify()
                self.ready.wait(.1)
        finally:
            with self.lock:self.waiting_threads.discard(thread)



def toggle_save_pause(viewer,event=None):
    control=getattr(viewer,'_export_control',None)
    if control is None or not getattr(viewer,'_export_active',False):return
    paused=control.toggle()
    viewer._export_status='Save: pausing...' if paused else 'Saving: resumed'
    viewer.save_butoon.Enable(paused)
    viewer.save_butoon.SetToolTip('Continue saving' if paused else 'Save')
    viewer.SetStatusText_(['-1','-1','-1',viewer._export_status])


def cancel_current_save(viewer,event=None):
    if not getattr(viewer,'_export_active',False):return
    cancel_save(viewer,shutdown=False)
    viewer._export_status='Save: cancelling...'
    viewer.save_butoon.Enable(False)
    viewer.SetStatusText_(['-1','-1','-1',viewer._export_status])


class ExportDecoder:
    def __init__(self,cancelled,cache=None,decoder_budget=0,checkpoint=lambda:None,working=nullcontext):
        self.cancelled,self.cache=cancelled,cache
        self.checkpoint=checkpoint
        self.working=working
        self.bank=DecoderBank(decoder_budget)
        self.dimensions={}

    def working_bytes(self,path):
        key=str(path)
        if key not in self.dimensions and av is not None:
            try:
                with av.open(key, metadata_errors='replace') as container:
                    codec=container.streams.video[0].codec_context
                    self.dimensions[key]=int(codec.width)*int(codec.height)
            except (OSError,ValueError,IndexError):pass
        return max(8*1024**2,self.dimensions.get(key,1920*1080)*40)

    def close(self):
        self.bank.close()
        self.dimensions.clear()

    def _decode_native(self,path,first,last,video,config):
        if not self.bank.available or str(path) in self.bank.disabled:return False
        try:
            if str(path) not in self.dimensions:
                with av.open(str(path), metadata_errors='replace') as container:
                    codec=container.streams.video[0].codec_context
                    pixels=int(codec.width)*int(codec.height)
                if pixels<=0:return False
                self.dimensions[str(path)]=pixels
            step=max(1,int(config.skip_frames)+1)
            count=0
            with self.bank.lease(path,config.video_fps_list[video],False,self.dimensions[str(path)]) as decoder:
                frames=decoder.frames(first*step,last*step,step,self.cancelled,buffer_images=True)
                try:
                    for physical,image in frames:
                        try:
                            self.checkpoint()
                            if self.cancelled():raise CancelledError()
                            target=Path(config.video_path[video])/self._filename_converter(physical//step,video,config)
                            save_cache_image(image,target,cache_extension(config),jpeg_quality=jpeg_quality(config))
                            count+=1
                        finally:image.close()
                finally:frames.close()
            if self.cancelled():raise CancelledError()
            if count!=last-first+1:raise RuntimeError('Incomplete export frame range')
            return True
        except CancelledError:raise
        except (OSError,ValueError,RuntimeError,IndexError,TypeError,AttributeError):
            # Unsupported streams/transforms retain the exact FFmpeg fallback.
            self.bank.disabled.add(str(path))
            self.bank.trim(set(self.bank.sessions)-{str(path)})
            return False

    def _filename_converter(self,index,video,config):
        return frame_filename(index,config.video_fps_list[video],config.skip_frames+1,cache_extension(config))

    def _save_frame(self,path,first,last,video,config=None):
        with self.working():return self._save_frame_impl(path,first,last,video,config)

    def _save_frame_impl(self,path,first,last,video,config=None):
        # Exact ordinal selection for VFR too. Output stops once this page is
        # complete; no shared playback session or mutable cache directory.
        if self.cancelled():raise CancelledError()
        self.checkpoint()
        folder=Path(config.video_path[video])
        if self.cache is not None:
            copied=[self.cache(index,video,folder/self._filename_converter(index,video,config)) for index in range(first,last+1)]
            if all(copied):return
        if self._decode_native(path,first,last,video,config):return
        tools,env=resolve_video_tools()
        step=config.skip_frames+1
        extension=cache_extension(config)
        pattern=folder/f'export_%09d.{extension}'
        expression=f'between(n,{first*step},{last*step})*not(mod(n,{step}))'
        command=[tools['ffmpeg'],'-nostdin','-hide_banner','-loglevel','error','-threads','1',
            '-i',str(path),'-vf',f'select={expression.replace(chr(44),chr(92)+chr(44))}',
            '-fps_mode','passthrough','-threads','1','-frames:v',str(last-first+1),'-start_number',str(first),
            *(['-c:v','png','-pix_fmt','rgb24','-compression_level','1'] if extension=='png' else ffmpeg_jpeg_args(config)),str(pattern)]
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with TemporaryFile() as errors:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=errors,env=env,creationflags=flags)
            try:
                while True:
                    try:code=process.wait(timeout=.1);break
                    except subprocess.TimeoutExpired:
                        if self.cancelled():raise CancelledError()
                if code:
                    errors.seek(0);raise RuntimeError(errors.read().decode('utf-8',errors='replace')[-2000:])
            finally:
                if process.poll() is None:process.kill();process.wait()
        for index in range(first,last+1):
            (folder/f'export_{index:09d}.{extension}').replace(folder/self._filename_converter(index,video,config))


def cancel_save(viewer,*,shutdown=True):
    event=getattr(viewer,'_export_cancel_event',None)
    if event is not None:event.set()
    control=getattr(viewer,'_export_control',None)
    if control is not None:control.ready.set()
    pool=getattr(viewer,'_export_pool',None)
    if shutdown and pool is not None:pool.shutdown(wait=False,cancel_futures=True)


def _input_stamp(manager,config,checkpoint):
    """Check input versions on the worker before resuming, using bounded metadata."""
    if config.video_mode:paths=iter(config.real_video_path)
    elif manager.type==3:paths=iter(manager.path_list)
    elif manager.type in (0,1) and manager.parallel_to_sequential:
        paths=(Path(folder)/name for folder,names in zip(manager.path_list,manager.name_list) for name in names)
    else:paths=(Path(folder)/name for folder in manager.path_list for name in manager.name_list)
    digest=hashlib.sha256()
    for path in paths:
        checkpoint();path=Path(path)
        try:
            info=path.stat();version=(info.st_size,info.st_mtime_ns)
        except OSError:version=None
        digest.update(repr((str(path.absolute()),version)).encode('utf-8'))
    return digest.hexdigest()


def start_save(viewer,event=None,*,selection_only=False,selected_grid=None):
    """Capture wx values only here on the GUI thread, then submit pure work."""
    if getattr(viewer,'_is_closing',False):return
    previous=getattr(viewer,'_export_future',None)
    if previous is not None and not previous.done():
        control=getattr(viewer,'_export_control',None)
        if control is not None and control.paused and not control.cancel.is_set():toggle_save_pause(viewer)
        return
    if getattr(viewer.ImgManager,'type',None) is None:
        viewer.SetStatusText_(['-1','-1','-1','Save: first select an input']);return
    if not viewer.out_path_str or not Path(viewer.out_path_str).is_dir():
        viewer.out_path(event)
        if not viewer.out_path_str or not Path(viewer.out_path_str).is_dir():return
    cancel=threading.Event();viewer._export_cancel_event=cancel
    control=ExportControl(cancel);viewer._export_control=control
    reference=weakref.ref(viewer)
    serial=getattr(viewer,'_export_serial',0)+1;viewer._export_serial=serial
    def deliver(text,final=False):
        def apply():
            owner=reference()
            if owner is None or getattr(owner,'_is_closing',False) or serial!=owner._export_serial:return
            if not final and (cancel.is_set() or not getattr(owner,'_export_active',False)):return
            if not final and text.startswith('Saving:') and control.paused:return
            if not final and text=='Save: paused' and not control.paused:return
            owner._export_status=text
            owner._export_active=not final
            owner.SetStatusText_(['-1','-1','-1',text])
            if final or control.paused:owner.save_butoon.Enable(True)
            if final:owner.save_butoon.SetToolTip('Save')
        owner=reference()
        if owner is None or getattr(owner,'_is_closing',False):return
        try:wx.CallAfter(apply)
        except (RuntimeError,AssertionError):pass  # wx application already exited.
    control.on_paused=lambda:deliver('Save: paused')
    last=[-1]
    def progress(value):
        percent=min(99,int(value*100))
        if percent!=last[0]:last[0]=percent;deliver(f'Saving: {percent}%')
    terminal=[None]
    def status(values):
        message=str(values[2]) if len(values)>2 else ''
        terminal[0]='Save: success' if message=='Save success!' else 'Save: '+message
    context=viewer._index_context()
    manager=viewer.ImgManager.video_stitch_snapshot()
    # Rendering snapshots deliberately drop pixel and painted source state.
    # Export must retain the displayed cell -> original source mapping.
    manager._export_checkpoint=control.checkpoint
    manager._export_working=control.working
    manager._export_set_budget=control.set_budget
    manager.flist=list(getattr(viewer.ImgManager,'flist',()))
    manager._flist_groups=copy.deepcopy(getattr(viewer.ImgManager,'_flist_groups',None))
    manager._status_source_slots=copy.deepcopy(getattr(viewer.ImgManager,'_status_source_slots',None))
    viewer_format=viewer.save_format.GetSelection()
    # Export's clicked format can differ from the last refreshed playback policy.
    # Resolve auto against this immutable export snapshot before looking up caches.
    manager.layout_params[35]=viewer_format
    quality=viewer.save_quality.GetValue() if hasattr(viewer,'save_quality') else jpeg_quality(manager)
    if len(manager.layout_params)<=42:manager.layout_params.extend([None]*(43-len(manager.layout_params)))
    manager.layout_params[42]=quality
    manager.cache_jpeg_quality=quality
    from .export_encoding import capture_export_encoding
    capture_export_encoding(viewer,manager)
    config=copy.copy(viewer.shared_config)
    for name in ('video_path','real_video_path','video_fps_list','video_num_list'):
        setattr(config,name,list(getattr(config,name)))
    manager.video_mode=bool(config.video_mode)
    if config.video_mode:manager.layout_params[11]=False
    config.cache_save_format=manager_cache_format(manager)
    config.save_quality=quality
    # Reserve a bounded quarter for independent codecs; rendering gets the rest.
    decoder_budget=max(0,int(config.memory_budget or 0)//4) if config.video_mode and av is not None else 0
    if config.memory_budget is not None:config.memory_budget-=decoder_budget
    config.thread=max(1,int(config.thread))
    if config.is_playing:config.thread=max(1,config.thread//4)  # Prioritize playback while it runs.
    vm=viewer.video_manager
    token=vm._window_token
    def cached(index,video,target):
        if cancel.is_set():raise CancelledError()
        if token!=vm._window_token or jpeg_quality(config)!=jpeg_quality(viewer.shared_config):return False
        try:
            with vm._raw_io_lock(video,config):
                if token!=vm._window_token or jpeg_quality(config)!=jpeg_quality(viewer.shared_config):return False
                source=Path(config.video_path[video])/frame_filename(index,config.video_fps_list[video],config.skip_frames+1,cache_extension(config))
                if lossless_export(manager,viewer_format) :
                    from PIL import Image
                    with Image.open(source) as image:
                        if image.format!='PNG':return False
                shutil.copyfile(source,target)
                if token==vm._window_token:return True
                target.unlink(missing_ok=True)
        except OSError:pass
        return False
    processing=viewer.image_pipeline.processing
    # Managed video playback and export atomically share its downstream CPU/RAM permits.
    if config.is_playing and config.video_mode and processing.budget.reservation is not None:
        manager._export_capacity=processing.budget.capacity
        manager._export_reservation=processing.budget.reservation
    from .configuration import settings_controls,control_value
    settings={name:control_value(name,widget) for name,widget in settings_controls(viewer).items() if name!='interval'}
    bulk=bool(viewer.auto_save_all.Value and not selection_only)
    key=repr((settings,str(viewer.out_path_str),manager.layout_params,tuple(manager.gap_color),manager.img_alpha,
        manager._custom_algorithm_registry,manager.input_path,manager.type,manager.count_per_action,manager.max_action_num,
        tuple(config.real_video_path),tuple(config.video_num_list),config.skip_frames,
        id(manager.name_list) if not config.video_mode else None))
    resume=getattr(viewer,'_export_resume_state',None)
    if not bulk or resume is None or resume.get('key')!=key or resume.get('finished'):
        resume=dict(key=key,completed=0,moves=[],stamp=None,finished=False)
    viewer._export_resume_state=resume
    job=SimpleNamespace(ImgManager=manager,out_path_str=str(viewer.out_path_str),
        shared_config=config,xy_magnifier=copy.deepcopy(viewer.xy_magnifier),
        choice_output=SimpleNamespace(GetSelection=lambda value=viewer.choice_output.GetSelection():value),
        save_format=SimpleNamespace(GetSelection=lambda value=viewer.save_format.GetSelection():value),
        auto_save_all=SimpleNamespace(Value=bool(viewer.auto_save_all.Value)),
        _status_selected_grid=getattr(viewer,'_status_selected_grid',0),
        _status_display_batch=getattr(viewer,'_status_display_batch',viewer.ImgManager.action_count),
        _index_selection_record=copy.deepcopy(getattr(viewer,'_index_selection_record',None)),
        _index_context=lambda:context,SetStatusText_=status,
        _export_reuse=processing.lease_export_results,
        _export_resume=resume if bulk else None,
        _export_cancelled=cancel.is_set,_export_checkpoint=control.checkpoint,_export_progress=progress,_export_isolate_video=True,
        video_manager=ExportDecoder(cancel.is_set,cached,decoder_budget,control.checkpoint))
    def run():
        try:
            if bulk:
                with control.working():stamp=_input_stamp(manager,config,control.checkpoint)
                if resume['stamp'] is not None and stamp!=resume['stamp']:
                    resume.update(completed=0,moves=[])
                resume['stamp']=stamp
            save_viewer(job,selection_only=selection_only,selected_grid=selected_grid)
            if terminal[0]=='Save: success':resume['finished']=True
            outcome=terminal[0] or 'Save: success'
        except CancelledError:outcome='Save: cancelled'
        except Exception as error:outcome=f'Save failed: {error}'
        try:job.video_manager.close()
        except Exception as error:outcome=f'Save failed during cleanup: {error}'
        deliver(outcome,True)  # Re-enable Save only after file/codec handles are released.
    if getattr(viewer,'_export_pool',None) is None:
        viewer._export_pool=ThreadPoolExecutor(1,thread_name_prefix='viewer-export')
    viewer._export_active=True;viewer._export_status='Saving: 0%'
    viewer.save_butoon.Enable(False)
    viewer.SetStatusText_(['-1','-1','-1',viewer._export_status])
    viewer._export_future=viewer._export_pool.submit(run)
