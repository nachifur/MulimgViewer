"""Export applied render settings using private managers, never live GUI state."""
import copy
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from concurrent.futures import CancelledError
from .cache_layout import source_names, page_name, write_source_catalog
from .custom_func.contract import original_index, processing_indices, display_indices, display_grid
from .custom_pipeline import CustomPipeline
from .video_timeline import page_segments


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


def selection_slots(manager, slot=0):
    """Pick a page-relative item across actual parallel sources, by position.

    Sequential, flattened parallel and image file lists select one entry.
    Parallel video file lists use their rendered parallel source groups too.
    A shorter source is skipped instead of choosing a different item.
    """
    paths=list(manager.flist)
    if slot is None or not 0<=slot<len(paths):return []
    parallel=(getattr(manager,'type',None) in (0,1) or
        (getattr(manager,'video_mode',False) and len(getattr(manager,'path_list',()))>1))
    if not parallel or getattr(manager,'parallel_to_sequential',False):return [slot]
    groups={}
    for index,path in enumerate(paths):
        groups.setdefault(str(Path(path).parent.absolute()),[]).append(index)
    group=groups[str(Path(paths[slot]).parent.absolute())]
    offset=group.index(slot)
    return [items[offset] for items in groups.values() if offset<len(items)]


def _save_selected(work,processed,paths,names,slots,base,raw,formats,moves):
    for index in slots:
        source=processed[index]
        target=base/'select_images'/names[index]
        target.parent.mkdir(parents=True,exist_ok=True)
        if raw and formats==0:
            target=target.with_suffix(Path(source).suffix)
            shutil.copyfile(source,target)
        else:
            with Image.open(source) as image:
                work.ImgF.save_img_diff_format(target,image,formats,use_vector_titles=False)
        if raw and work.layout_params[11] and not getattr(work,'video_mode',False):
            moves.append((paths[index],target))


def export_page(manager,root,output,memory=None,workers=1,defer_moves=False,selected_slots=None,progress=lambda value:None,cancelled=lambda:False):
    """Process once, export each algorithm at output scale, compose from disk."""
    params=copy.deepcopy(manager.layout_params)
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
    write_source_catalog(manager,root)
    names=source_names(manager,paths)
    slots=selection_slots(manager) if selected_slots is None else list(dict.fromkeys(selected_slots))
    if any(not 0<=i<len(paths) for i in slots):raise ValueError('Selection is outside the exported page')
    moves=[]
    visible=display_indices(registry,params)
    with TemporaryDirectory(prefix='mulimg-export-') as directory:
        stage=CustomPipeline(Path(directory)/'processing')
        stage.configure(workers,memory)
        stage.set_window('export','page',(manager.action_count,manager.action_count),manager.action_count)
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
                            for source,relative in zip(processed,names):
                                target=base/'processed_img'/relative
                                target.parent.mkdir(parents=True,exist_ok=True)
                                with Image.open(source) as image:
                                    work.ImgF.save_img_diff_format(target,image,formats,use_vector_titles=False)
                    if not bits&5:
                        work.clear_cache()
                        continue
                    # Stitch initialization also supplies output-scale crop geometry.
                    if bits&1:
                        work.stitch_images(1,copy.deepcopy(work.draw_points),flist=paths)
                        if work.img is None:raise RuntimeError(f'{algorithm}: export stitch failed')
                    else:
                        work.stitch_img_init(1,copy.deepcopy(work.draw_points),flist=paths)
                    if reference is None:reference=work.img_resolution_origin
                    if bits&1:
                        target=base/'stitch_images'/page_name(manager.action_count)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        work.ImgF.save_img_diff_format(target,work.img,formats)
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
                if bits&1:
                    rows,cols=display_grid(registry,params)
                    width=max(mosaics[i][1][0] for i in (visible or [original]))
                    height=max(mosaics[i][1][1] for i in (visible or [original]))
                    charge=width*height*(rows*cols+1)*8
                    if memory is not None and charge>memory:raise MemoryError('Export canvas exceeds the memory budget')
                    canvas=Image.new('RGBA',(width*cols,height*rows),tuple(manager.gap_color))
                    titles=[]
                    for slot,index in enumerate(visible):
                        row,col=(slot%rows,slot//rows) if (params[32] or params[38]) and params[40] else divmod(slot,cols)
                        x,y=col*width,row*height
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
            stage.close()
            stage.pool.shutdown(wait=True)
            stage.cleanup_future.result()
    return moves


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
    moves=[]
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
    progress=getattr(viewer,'_export_progress',lambda value:None)
    for number,page in enumerate(pages):
        if cancelled():raise CancelledError()
        progress(number/max(1,len(pages)))
        work=manager.video_stitch_snapshot()
        work.set_action_count(page)
        work.layout_params[35]=viewer.save_format.GetSelection()
        work.draw_points=copy.deepcopy(viewer.xy_magnifier)
        work.show_box=bool(work.layout_params[14])
        # The painted page's flist contains raw inputs, even when several
        # algorithm panes display the same source more than once.
        if viewer.shared_config.video_mode:
            cfg=viewer.shared_config
            spans=page_segments(cfg.video_num_list,cfg.count_per_action,page,cfg.parallel_to_sequential)
            work.flist=[str(Path(cfg.video_path[vid])/viewer.video_manager._filename_converter(index,vid,cfg))
                        for vid,first,stop in spans for index in range(first,stop)]
        elif page==manager.action_count and getattr(manager,'flist',None):
            work.flist=list(manager.flist)
            work._flist_groups=copy.deepcopy(getattr(manager,'_flist_groups',None))
        else:
            work.get_flist()
        slots=list(range(len(work.flist))) if bulk else selection_slots(work,clicked)
        try:
            if viewer.shared_config.video_mode and (getattr(viewer,'_export_isolate_video',False) or not all(Path(path).is_file() for path in work.flist)):
                # Save-all can address virtual frames outside the playback
                # window. Decode those into an isolated temporary tree so
                # playback cleanup cannot delete export inputs mid-read.
                with TemporaryDirectory(prefix='mulimg-export-frames-') as raw:
                    config=copy.copy(viewer.shared_config)
                    config.video_path=[str(Path(raw)/f'source_{i+1:03d}') for i in range(len(config.real_video_path))]
                    for path in config.video_path:Path(path).mkdir()
                    for vid,first,stop in spans:
                        viewer.video_manager._save_frame(config.real_video_path[vid],first,stop-1,vid,config=config)
                    work.flist=[str(Path(config.video_path[vid])/viewer.video_manager._filename_converter(index,vid,config))
                                for vid,first,stop in spans for index in range(first,stop)]
                    work.path_list=list(config.video_path)
                    work._status_source_index=None
                    work._cache_original_paths=list(config.real_video_path)
                    moves.extend(export_page(work,root,output,config.memory_budget,config.thread,defer_moves=True,selected_slots=slots,
                        progress=lambda fraction:progress((number+fraction)/max(1,len(pages))),cancelled=cancelled))
            else:
                moves.extend(export_page(work,root,output,viewer.shared_config.memory_budget,viewer.shared_config.thread,defer_moves=True,selected_slots=slots,
                        progress=lambda fraction:progress((number+fraction)/max(1,len(pages))),cancelled=cancelled))
        except CancelledError:raise
        except Exception as error:
            viewer.SetStatusText_(['-1','-1',f'Export failed, page {page+1}: {error}','-1'])
            return
        finally:
            work.clear_cache()
    if cancelled():raise CancelledError()
    _finish_moves(moves)
    viewer.SetStatusText_(['Save','-1','Save success!','-1'])
