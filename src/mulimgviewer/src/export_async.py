"""Background export owns immutable settings and an independent video decoder."""
import copy
import shutil
import subprocess
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor, CancelledError
from pathlib import Path
from tempfile import TemporaryFile
from types import SimpleNamespace
import wx
from .export_controller import save_viewer
from .video_paths import frame_filename
from .video_tools import resolve_video_tools


class ExportDecoder:
    def __init__(self,cancelled,cache=None):self.cancelled=cancelled;self.cache=cache

    def _filename_converter(self,index,video,config):
        return frame_filename(index,config.video_fps_list[video],config.skip_frames+1)

    def _save_frame(self,path,first,last,video,config=None):
        # Exact ordinal selection for VFR too. Output stops once this page is
        # complete; no shared playback session or mutable cache directory.
        if self.cancelled():raise CancelledError()
        folder=Path(config.video_path[video])
        if self.cache is not None:
            copied=[self.cache(index,video,folder/self._filename_converter(index,video,config)) for index in range(first,last+1)]
            if all(copied):return
        tools,env=resolve_video_tools()
        step=config.skip_frames+1
        pattern=folder/'export_%09d.jpeg'
        expression=f'between(n,{first*step},{last*step})*not(mod(n,{step}))'
        command=[tools['ffmpeg'],'-nostdin','-hide_banner','-loglevel','error','-threads','1',
            '-i',str(path),'-vf',f'select={expression.replace(chr(44),chr(92)+chr(44))}',
            '-vsync','0','-threads','1','-frames:v',str(last-first+1),'-start_number',str(first),'-q:v','2',str(pattern)]
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
            (folder/f'export_{index:09d}.jpeg').replace(folder/self._filename_converter(index,video,config))


def cancel_save(viewer):
    event=getattr(viewer,'_export_cancel_event',None)
    if event is not None:event.set()
    pool=getattr(viewer,'_export_pool',None)
    if pool is not None:pool.shutdown(wait=False,cancel_futures=True)


def start_save(viewer,event=None,*,selection_only=False,selected_grid=None):
    """Capture wx values only here on the GUI thread, then submit pure work."""
    if getattr(viewer,'_is_closing',False):return
    previous=getattr(viewer,'_export_future',None)
    if previous is not None and not previous.done():return
    if getattr(viewer.ImgManager,'type',None) is None:
        viewer.SetStatusText_(['-1','-1','-1','Save: first select an input']);return
    if not viewer.out_path_str or not Path(viewer.out_path_str).is_dir():
        viewer.out_path(event)
        if not viewer.out_path_str or not Path(viewer.out_path_str).is_dir():return
    cancel=threading.Event();viewer._export_cancel_event=cancel
    reference=weakref.ref(viewer)
    serial=getattr(viewer,'_export_serial',0)+1;viewer._export_serial=serial
    def deliver(text,final=False):
        def apply():
            owner=reference()
            if owner is None or getattr(owner,'_is_closing',False) or serial!=owner._export_serial:return
            owner._export_status=text
            owner._export_active=not final
            owner.SetStatusText_(['-1','-1','-1',text])
            if final:owner.save_butoon.Enable(True)
        owner=reference()
        if owner is None or getattr(owner,'_is_closing',False):return
        try:wx.CallAfter(apply)
        except (RuntimeError,AssertionError):pass  # wx application already exited.
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
    manager.flist=list(viewer.ImgManager.flist)
    manager._flist_groups=copy.deepcopy(getattr(viewer.ImgManager,'_flist_groups',None))
    manager._status_source_slots=copy.deepcopy(getattr(viewer.ImgManager,'_status_source_slots',None))
    config=copy.copy(viewer.shared_config)
    config.thread=1  # Save serially alongside the latency-sensitive playback.
    vm=viewer.video_manager
    token=vm._window_token
    def cached(index,video,target):
        if cancel.is_set():raise CancelledError()
        if token!=vm._window_token:return False
        try:
            with vm._raw_io_lock(video,config):
                if token!=vm._window_token:return False
                source=Path(config.video_path[video])/frame_filename(index,config.video_fps_list[video],config.skip_frames+1)
                shutil.copyfile(source,target)
                if token==vm._window_token:return True
                target.unlink(missing_ok=True)
        except OSError:pass
        return False
    job=SimpleNamespace(ImgManager=manager,out_path_str=str(viewer.out_path_str),
        shared_config=config,xy_magnifier=copy.deepcopy(viewer.xy_magnifier),
        choice_output=SimpleNamespace(GetSelection=lambda value=viewer.choice_output.GetSelection():value),
        save_format=SimpleNamespace(GetSelection=lambda value=viewer.save_format.GetSelection():value),
        auto_save_all=SimpleNamespace(Value=bool(viewer.auto_save_all.Value)),
        _status_selected_grid=getattr(viewer,'_status_selected_grid',0),
        _status_display_batch=getattr(viewer,'_status_display_batch',viewer.ImgManager.action_count),
        _index_selection_record=copy.deepcopy(getattr(viewer,'_index_selection_record',None)),
        _index_context=lambda:context,SetStatusText_=status,
        _export_cancelled=cancel.is_set,_export_progress=progress,_export_isolate_video=True,
        video_manager=ExportDecoder(cancel.is_set,cached))
    def run():
        try:
            save_viewer(job,selection_only=selection_only,selected_grid=selected_grid)
            deliver(terminal[0] or 'Save: success',True)
        except CancelledError:deliver('Save: cancelled',True)
        except Exception as error:deliver(f'Save failed: {error}',True)
    if getattr(viewer,'_export_pool',None) is None:
        viewer._export_pool=ThreadPoolExecutor(1,thread_name_prefix='viewer-export')
    viewer._export_active=True;viewer._export_status='Saving: 0%'
    viewer.save_butoon.Enable(False)
    viewer.SetStatusText_(['-1','-1','-1',viewer._export_status])
    viewer._export_future=viewer._export_pool.submit(run)
