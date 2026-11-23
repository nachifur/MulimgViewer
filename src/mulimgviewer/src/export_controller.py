"""Image and video exports, from render snapshots to background save jobs."""
import copy
import hashlib
import shutil
import subprocess
import threading
import weakref
import wx
from PIL import Image
from concurrent.futures import CancelledError, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from types import SimpleNamespace

from .cache_layout import open_rendered_canvas, page_name, save_cache_image, source_names, write_source_catalog
from .custom_func.contract import display_grid, display_indices, original_index, processing_indices
from .custom_pipeline import CustomPipeline, WorkBudget, current_only
from .image_encoding import (
    JPG,
    PNG,
    cache_extension,
    ffmpeg_jpeg_args,
    jpeg_quality,
    lossless_export,
    manager_cache_format,
)
from .pipeline_executor import ImageWorkers
from .render_layout import gap_pair
from .video_decoder import DecoderBank, av
from .video_source import frame_filename, page_segments, resolve_video_tools


# Page rendering and output files
def source_slot(manager, grid=0):
    """Painted cell -> raw source slot, including repeated algorithm panes."""
    mapping=getattr(manager,'xy_grids_id_list',())
    variants=getattr(manager,'_status_source_slots',None)
    if not mapping:return 0 if getattr(manager,'flist',()) else None
    if not 0<=grid<len(mapping):return None
    slot=int(mapping[grid])
    if variants is not None:
        if not 0<=slot<len(variants):return None
        slot=variants[slot]
    return slot if 0<=slot<len(manager.flist) else None


def parallel_selection(manager):
    if getattr(manager,'parallel_to_sequential',False):return False
    mode=getattr(manager,'_cache_input_mode','')
    if mode:return mode in ('Parallel auto','Parallel manual')
    return getattr(manager,'type',None) in (0,1)


def selection_slots(manager, slot=0):
    """Only parallel auto/manual inputs select across sources, by position."""
    paths=list(manager.flist)
    if slot is None or not 0<=slot<len(paths):return []
    if not parallel_selection(manager):return [slot]
    groups={}
    for index,path in enumerate(paths):
        groups.setdefault(str(Path(path).parent.absolute()),[]).append(index)
    group=groups[str(Path(paths[slot]).parent.absolute())]
    offset=group.index(slot)
    return [items[offset] for items in groups.values() if offset<len(items)]


def _write_export_file(work,source,target,formats):
    checkpoint=getattr(work,'_export_checkpoint',lambda:None)
    cancelled=getattr(work,'_export_cancelled',lambda:False)
    checkpoint()
    target=Path(target).with_suffix('.png' if formats==PNG else '.jpg' if formats==JPG else '.pdf')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Matching extensions still need the captured compression settings;
    # cached pixels remain reusable, but their encoded bytes may differ.
    with Image.open(source) as image:
        size=max(1024**2,image.width*image.height*16)
        budget=getattr(work,'_export_file_budget',None)
        with budget.acquire(size,cancelled) if budget is not None else nullcontext():
            # Once admitted this file is the current task. Finish and release
            # permits before the next checkpoint; pausing must not pin CPU lanes.
            if cancelled():raise CancelledError()
            work.ImgF.save_img_diff_format(target,image,formats,use_vector_titles=False)
    return target


def _write_export_files(work,jobs,formats):
    pool=getattr(work,'_export_writers',None)
    if pool is None:return [_write_export_file(work,source,target,formats) for source,target in jobs]
    futures=[pool.submit(_write_export_file,work,source,target,formats) for source,target in jobs]
    try:return [future.result() for future in futures]
    except BaseException:
        for future in futures:future.cancel()
        wait(futures)  # Drain readers before releasing cache leases or temp files.
        raise


def _save_selected(work,processed,paths,names,slots,base,raw,formats,moves):
    targets=_write_export_files(work,[(processed[index],base/'select_images'/names[index]) for index in slots],formats)
    if raw and work.layout_params[11] and not getattr(work,'video_mode',False):
        moves.extend((paths[index],target) for index,target in zip(slots,targets))


def export_page(manager,root,output,memory=None,workers=1,defer_moves=False,selected_slots=None,progress=lambda value:None,cancelled=lambda:False,processing=None,write_catalog=True):
    """Process once, export each algorithm at output scale, compose from disk."""
    checkpoint=getattr(manager,'_export_checkpoint',lambda:None)
    report=progress
    def progress(value):
        checkpoint();report(value)
    checkpoint()
    params=copy.deepcopy(manager.layout_params)
    if getattr(manager,'video_mode',False):params[11]=False
    registry=manager._custom_algorithm_registry
    original=original_index(registry)
    indices=list(dict.fromkeys([original]+processing_indices(registry,params)))
    paths=list(manager.flist)
    if not paths:raise ValueError('No source images available for export')
    formats=params[35];bits=output+1
    if not manager.draw_points:bits &= ~4
    if not bits:
        progress(1.)
        return []
    root=Path(root)/('video' if getattr(manager,'video_mode',False) else 'image')
    root.mkdir(parents=True,exist_ok=True)
    if write_catalog:write_source_catalog(manager,root)
    names=source_names(manager,paths,readable=True)
    slots=selection_slots(manager) if selected_slots is None else list(dict.fromkeys(selected_slots))
    if any(not 0<=i<len(paths) for i in slots):raise ValueError('Selection is outside the exported page')
    moves=[]
    visible=display_indices(registry,params)
    direct_composite=len(visible)==1 and tuple(display_grid(registry,params))==(1,1)
    with TemporaryDirectory(prefix='mulimg-export-') as directory:
        stage=processing if processing is not None else CustomPipeline(Path(directory)/'processing',
            workers=workers,pool=getattr(manager,'_export_image_pool',None))
        if processing is None:
            shared=getattr(manager,'_export_budget',None)
            if shared is not None:stage.budget=shared
            else:stage.configure(workers,memory,
                capacity=getattr(manager,'_export_capacity',None),reservation=getattr(manager,'_export_reservation',None))
        getattr(manager,'_export_set_budget',lambda budget:None)(stage.budget)
        stage.set_window('export','page',(manager.action_count,manager.action_count),manager.action_count)
        stage._prune()  # Retire the previous page before producing this page.
        try:
            with stage.prepare(manager,paths,manager.action_count,'export','page',cancelled=cancelled) as results:
                mosaics={};states={};reference=None
                for algorithm_number,index in enumerate(indices):
                    if cancelled():raise CancelledError()
                    progress(algorithm_number/max(1,len(indices)))
                    work=manager.video_stitch_snapshot()
                    work.layout_params=copy.deepcopy(params)
                    work.layout_params[38]=False
                    work.layout_params[32]=index is not None and index!=original
                    work.layout_params[37]=0 if index is None else index
                    work._custom_results=results
                    work._video_pixel_provider=None
                    work._video_lazy_frames=True
                    work._video_memory_budget=memory
                    work._export_file_budget=stage.budget
                    work.flist=paths
                    work.draw_points=copy.deepcopy(manager.draw_points)
                    if reference is not None:work.layout_params[6]=list(reference)
                    algorithm='original' if index is None else work.algorithm_output_name(index)
                    base=root/'algorithms'/algorithm
                    processed=results.get(index,paths)
                    raw=index==original or index is None
                    if bits&2:
                        _save_selected(work,processed,paths,names,slots,base,raw,formats,moves)
                        if not raw:
                            _write_export_files(work,[(source,base/'processed_img'/relative)
                                for source,relative in zip(processed,names)],formats)
                    estimate=work.video_stitch_snapshot()
                    estimate.layout_params[4]=list(estimate.layout_params[5])
                    charge=stage.composition_bytes(paths,{index:processed},estimate) if bits&5 else 0
                    checkpoint()
                    with stage.budget.acquire(charge,cancelled,priority=1):
                        if not bits&5:
                            work.clear_cache()
                            continue
                        # Stitch initialization also supplies output-scale crop geometry.
                        cached_mosaic=getattr(manager,'_export_reused_mosaics',{}).get(index)
                        # A JPEG preview already baked compression artefacts into
                        # its titles. Render these again from source/processed
                        # tiles for final JPEG output; PNG mosaics remain reusable.
                        if formats==JPG and cached_mosaic is not None and Path(cached_mosaic[0]).suffix.lower() in ('.jpg','.jpeg'):
                            cached_mosaic=None
                        if bits&1 and cached_mosaic is not None:
                            work.stitch_img_init(1,copy.deepcopy(work.draw_points),flist=paths)
                            with open_rendered_canvas(cached_mosaic[0],cached_mosaic[1].get('_rendered_canvas_size')) as image:work.img=image.convert('RGBA')
                            work.pdf_title_layers=copy.deepcopy(cached_mosaic[1].get('pdf_title_layers',[]))
                        elif bits&1:
                            work.stitch_images(1,copy.deepcopy(work.draw_points),flist=paths)
                            if work.img is None:raise RuntimeError(f'{algorithm}: export stitch failed')
                        else:
                            work.stitch_img_init(1,copy.deepcopy(work.draw_points),flist=paths)
                        if reference is None:reference=work.img_resolution_origin
                        if bits&1:
                            target=base/'stitch_images'/page_name(manager.action_count)
                            target.parent.mkdir(parents=True,exist_ok=True)
                            if cached_mosaic is not None and formats==PNG and Path(cached_mosaic[0]).suffix.lower()=='.png' and getattr(work,'png_compression_level',6)==1:shutil.copyfile(cached_mosaic[0],target)
                            else:work.ImgF.save_img_diff_format(target,work.img,formats)
                            private=target.with_suffix('.png' if formats==PNG else '.jpg' if formats==JPG else '.pdf')
                            if index in visible and not direct_composite:
                                private=Path(directory)/f'mosaic_{len(mosaics)}.png'
                                work.img.save(private,format='PNG',compress_level=1)
                            mosaics[index]=(private,work.img.size)
                            states[index]=copy.deepcopy(work.pdf_title_layers)
                        if bits&4 and work.draw_points:
                            work.crop_points_process(copy.deepcopy(work.draw_points),img_mode=1)
                            for number,(image,relative) in enumerate(zip(work.img_list,names)):
                                if number in getattr(work,'_blank_img_ids',()):continue
                                tile=work.img_preprocessing(image,rowcol=work.get_img_row_col(number))
                                try:
                                    # Local tile coordinates: mosaic offsets must not
                                    # shift the rectangles on individually saved images.
                                    boxed=work.ImgF.draw_rectangle(tile,[[0,0]],work.crop_points,
                                        work.layout_params[9],line_width=work.layout_params[10][0],single_box=True)
                                    try:
                                        target=base/'origin_img_with_box'/relative
                                        target.parent.mkdir(parents=True,exist_ok=True)
                                        work.ImgF.save_img_diff_format(target,boxed,formats,use_vector_titles=False)
                                    finally:boxed.close()
                                    for crop_id,crop in enumerate(work.magnifier_preprocessing(tile,img_mode=1,id=number)):
                                        try:
                                            target=base/'magnifier_images'/Path(relative).parent/f'{crop_id+1:03d}_{Path(relative).name}'
                                            target.parent.mkdir(parents=True,exist_ok=True)
                                            work.ImgF.save_img_diff_format(target,crop,formats,use_vector_titles=False)
                                        finally:crop.close()
                                finally:tile.close()
                        work.clear_cache()
                if bits&1 and not direct_composite:
                    width=max(mosaics[i][1][0] for i in (visible or [original]))
                    height=max(mosaics[i][1][1] for i in (visible or [original]))
                    rows,cols=display_grid(registry,params)
                    gap_x,gap_y=gap_pair(params[3], 'func')
                    canvas_width=width*cols+gap_x*(cols-1)
                    canvas_height=height*rows+gap_y*(rows-1)
                    charge=(canvas_width*canvas_height+width*height)*8
                else:charge=0
                checkpoint()
                with stage.budget.acquire(charge,cancelled,priority=2):
                    if bits&1 and direct_composite:
                        source=mosaics[visible[0]][0]
                        target=(root/'composed'/page_name(manager.action_count)).with_suffix(source.suffix)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(source,target)
                    elif bits&1:
                        if memory is not None and charge>memory:raise MemoryError('Export canvas exceeds the memory budget')
                        canvas=Image.new('RGBA',(canvas_width,canvas_height),tuple(manager.gap_color))
                        titles=[]
                        for slot,index in enumerate(visible):
                            row,col=(slot%rows,slot//rows) if (params[32] or params[38]) and params[40] else divmod(slot,cols)
                            x,y=col*(width+gap_x),row*(height+gap_y)
                            with open_rendered_canvas(*mosaics[index]) as image:canvas.paste(image,(x,y))
                            for title in states[index]:
                                title=copy.deepcopy(title);title['x']+=x;title['y']+=y;titles.append(title)
                        manager.pdf_title_layers=titles
                        target=root/'composed'/page_name(manager.action_count)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        manager.ImgF.save_img_diff_format(target,canvas,formats)
                        canvas.close()
                if cancelled():raise CancelledError()
                if not defer_moves:
                    _finish_moves(moves)
                progress(1.)
        finally:
            if processing is None:
                _close_export_processing(stage)
    return moves


def _close_export_processing(stage):
    stage.close()
    if stage._owns_pool:stage.pool.shutdown(wait=True)
    stage.cleanup_future.result()


def _finish_moves(moves):
    for source,target in moves:
        if Path(source).is_file() and Path(source).resolve()!=Path(target).resolve():
            Path(source).unlink()


def save_viewer(viewer,event=None,*,selection_only=False,selected_grid=None):
    manager=viewer.ImgManager
    if getattr(manager,'type',None) is None or not manager.layout_params:
        viewer.SetStatusText_(['-1','-1','First select an input','-1'])
        return
    root=viewer.out_path_str
    if not root or not Path(root).is_dir():
        viewer.SetStatusText_(['-1','-1','First select the output directory','-1'])
        viewer.out_path(event)
        return
    output=1 if selection_only else viewer.choice_output.GetSelection()
    if output==3 and not viewer.xy_magnifier:
        viewer.SetStatusText_(['-1','-1','Skipped: no magnification boxes','-1']);return
    bulk=bool(viewer.auto_save_all.Value and not selection_only)
    pages=range(manager.max_action_num) if bulk else [manager.action_count]
    if not pages:
        viewer.SetStatusText_(['-1','-1','Skipped: no pages to save','-1']);return
    resume=getattr(viewer,'_export_resume',None) if bulk else None
    completed=min(len(pages),max(0,int(resume.get('completed',0)))) if resume is not None else 0
    moves=list(resume.get('moves',())) if resume is not None and not viewer.shared_config.video_mode else []
    painted=getattr(viewer,'_status_display_batch',manager.action_count)
    if not bulk and painted!=manager.action_count:
        viewer.SetStatusText_(['-1','-1','Wait for the requested page before selecting images','-1']);return
    grid=getattr(viewer,'_status_selected_grid',0) if selected_grid is None else selected_grid
    record=getattr(viewer,'_index_selection_record',None)
    if selected_grid is None and record and (record.get('page')!=getattr(viewer,'_status_display_batch',manager.action_count)
            or record.get('context')!=viewer._index_context()):grid=0
    clicked=source_slot(manager,grid)
    if not bulk and (output+1)&2 and clicked is None:
        viewer.SetStatusText_(['-1','-1','Select a source image before saving','-1']);return
    cancelled=getattr(viewer,'_export_cancelled',lambda:False)
    checkpoint=getattr(viewer,'_export_checkpoint',lambda:None)
    progress=getattr(viewer,'_export_progress',lambda value:None)
    with ExitStack() as resources:
        source=manager;manager=source.video_stitch_snapshot()
        manager.video_mode=bool(viewer.shared_config.video_mode)
        if manager.video_mode:
            manager.layout_params[11]=False
            manager._cache_original_paths=list(getattr(viewer.shared_config,'real_video_path',
                getattr(manager,'_cache_original_paths',())))
        manager.flist=list(getattr(source,'flist',()))
        manager._flist_groups=copy.deepcopy(getattr(source,'_flist_groups',None))
        manager._export_checkpoint=checkpoint
        manager._export_writers=resources.enter_context(ThreadPoolExecutor(
            max(1,int(viewer.shared_config.thread)),thread_name_prefix='export-file'))
        manager._export_cancelled=cancelled
        # All ready kernels (decode/process/stitch/compose/file encoding) borrow
        # the same permits. Coordinators never hold a permit while awaiting children.
        budget=WorkBudget()
        budget.configure(viewer.shared_config.thread,viewer.shared_config.memory_budget,
            capacity=getattr(manager,'_export_capacity',None),reservation=getattr(manager,'_export_reservation',None))
        manager._export_budget=budget
        getattr(manager,'_export_set_budget',lambda value:None)(budget)
        manager._export_image_pool=ImageWorkers(viewer.shared_config.thread,thread_name_prefix='export-process')
        resources.callback(manager._export_image_pool.shutdown,wait=True,cancel_futures=True)
        page_workers=min(max(1,int(viewer.shared_config.thread)),len(pages)) if bulk else 1
        if current_only(manager):page_workers=1  # Stateful plugins require page order.
        renderers=resources.enter_context(ThreadPoolExecutor(page_workers,thread_name_prefix='export-page'))
        decoders=resources.enter_context(ThreadPoolExecutor(max(1,int(viewer.shared_config.thread)),thread_name_prefix='export-decode'))
        processing=None
        if page_workers==1:
            directory=resources.enter_context(TemporaryDirectory(prefix='mulimg-export-processing-'))
            processing=CustomPipeline(Path(directory)/'processing',pool=manager._export_image_pool)
            processing.budget=budget
            resources.callback(_close_export_processing,processing)
        pending=[]
        def commit():
            number,page,future,leases=pending.pop(0)
            try:
                moves.extend(future.result())
                if resume is not None:resume.update(completed=number+1,moves=list(moves))
                progress((number+1)/max(1,len(pages)))
            finally:leases.close()

        def render(work,slots,number):
            try:
                return export_page(work,root,output,viewer.shared_config.memory_budget,viewer.shared_config.thread,
                    defer_moves=True,selected_slots=slots,cancelled=cancelled,processing=processing,
                    write_catalog=number==completed)
            finally:work.clear_cache()

        def decode(path,first,last,vid,config):
            checkpoint()
            # Codec reference frames and one decoded output, in addition to the
            # separately reserved resident decoder cache. Never queue pixels.
            decoder=viewer.video_manager
            charge=getattr(decoder,'working_bytes',lambda path:64*1024**2)(path)
            with budget.acquire(charge,cancelled):
                decoder._save_frame(path,first,last,vid,config=config)

        try:
            for number,page in enumerate(pages):
                if number<completed:continue
                checkpoint()
                if cancelled():raise CancelledError()
                if len(pending)>=page_workers:commit()
                work=manager.video_stitch_snapshot()
                work.set_action_count(page)
                work.layout_params[35]=viewer.save_format.GetSelection()
                work.draw_points=copy.deepcopy(viewer.xy_magnifier)
                work.show_box=bool(work.layout_params[14])
                if viewer.shared_config.video_mode:
                    cfg=viewer.shared_config
                    spans=page_segments(cfg.video_num_list,cfg.count_per_action,page,cfg.parallel_to_sequential)
                    work.flist=[str(Path(cfg.video_path[vid])/viewer.video_manager._filename_converter(index,vid,cfg))
                                for vid,first,stop in spans for index in range(first,stop)]
                elif page==manager.action_count and getattr(manager,'flist',None):
                    work.flist=list(manager.flist)
                    work._flist_groups=copy.deepcopy(getattr(manager,'_flist_groups',None))
                else:work.get_flist()
                slots=list(range(len(work.flist))) if bulk else selection_slots(work,clicked)
                leases=ExitStack()
                try:
                    reuse=getattr(viewer,'_export_reuse',None)
                    cached=leases.enter_context(reuse(work,list(work.flist),page) if reuse else nullcontext({}))
                    work._export_reused_results={i:value for i,value in cached.items() if i!='_mosaics'}
                    work._export_reused_mosaics=cached.get('_mosaics',{})
                    if viewer.shared_config.video_mode and (getattr(viewer,'_export_isolate_video',False) or not all(Path(p).is_file() for p in work.flist)):
                        raw=leases.enter_context(TemporaryDirectory(prefix='mulimg-export-frames-'))
                        config=copy.copy(viewer.shared_config)
                        config.video_path=[str(Path(raw)/f'source_{i+1:03d}') for i in range(len(config.real_video_path))]
                        for vid,_,_ in spans:Path(config.video_path[vid]).mkdir(exist_ok=True)
                        jobs=[decoders.submit(decode,config.real_video_path[vid],first,stop-1,vid,config)
                              for vid,first,stop in spans]
                        try:
                            for job in jobs:job.result()
                        finally:
                            for job in jobs:job.cancel()
                            wait(jobs)  # Readers finish before private frame directories disappear.
                        work.flist=[str(Path(config.video_path[vid])/viewer.video_manager._filename_converter(index,vid,config))
                                    for vid,first,stop in spans for index in range(first,stop)]
                        work.path_list=list(config.video_path)
                        work._status_source_index=None
                        work._cache_original_paths=list(config.real_video_path)
                    pending.append((number,page,renderers.submit(render,work,slots,number),leases))
                except BaseException:
                    leases.close();work.clear_cache();raise
            while pending:commit()
        except BaseException as error:
            # Drain every reader before releasing leases or temporary directories.
            for _,_,future,_ in pending:future.cancel()
            wait([item[2] for item in pending])
            for _,_,_,leases in pending:leases.close()
            if isinstance(error,CancelledError):raise
            if not isinstance(error,Exception):raise
            viewer.SetStatusText_(['-1','-1',f'Export failed: {error}','-1'])
            return
    checkpoint()
    if cancelled():raise CancelledError()
    if not viewer.shared_config.video_mode:_finish_moves(moves)
    viewer.SetStatusText_(['Save','-1','Save success!','-1'])


# Background export and private video decoding
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
    from .image_encoding import capture_export_encoding
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
