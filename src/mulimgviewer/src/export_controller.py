"""Export applied render settings using private managers, never live GUI state."""
import copy
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from concurrent.futures import CancelledError, ThreadPoolExecutor, wait
from contextlib import nullcontext, ExitStack
from .cache_layout import source_names, page_name, write_source_catalog
from .custom_func.contract import original_index, processing_indices, display_indices, display_grid
from .custom_pipeline import CustomPipeline, WorkBudget, current_only
from .export_formats import PNG, JPG
from .custom_workers import ImageWorkers
from .video_timeline import page_segments
from .layout_gaps import gap_pair


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
    # PNG can reuse its lossless encoding. JPG must use the clicked quality
    # and 4:4:4 policy even when its source is already a JPEG file.
    with Image.open(source) as image:
        copy_encoded=(formats==PNG and image.format=='PNG')
        size=1024**2 if copy_encoded else max(1024**2,image.width*image.height*16)
        budget=getattr(work,'_export_file_budget',None)
        with budget.acquire(size,cancelled) if budget is not None else nullcontext():
            # Once admitted this file is the current task. Finish and release
            # permits before the next checkpoint; pausing must not pin CPU lanes.
            if cancelled():raise CancelledError()
            if copy_encoded:shutil.copyfile(source,target)
            else:work.ImgF.save_img_diff_format(target,image,formats,use_vector_titles=False)
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
                            with Image.open(cached_mosaic[0]) as image:work.img=image.convert('RGBA')
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
                            if cached_mosaic is not None and formats==PNG and Path(cached_mosaic[0]).suffix.lower()=='.png':shutil.copyfile(cached_mosaic[0],target)
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
                            with Image.open(mosaics[index][0]) as image:canvas.paste(image,(x,y))
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
