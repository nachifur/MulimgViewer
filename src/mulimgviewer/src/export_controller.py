"""Export applied render settings using private managers, never live GUI state."""
import copy
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from .cache_layout import source_names, page_name, write_source_catalog
from .custom_func.contract import original_index, processing_indices, display_indices, display_grid
from .custom_pipeline import CustomPipeline
from .video_timeline import page_segments


def export_page(manager,root,output,memory=None,workers=1,defer_moves=False):
    """Process once, export each algorithm at output scale, compose from disk."""
    params=copy.deepcopy(manager.layout_params)
    registry=manager._custom_algorithm_registry
    original=original_index(registry)
    indices=list(dict.fromkeys([original]+processing_indices(registry,params)))
    paths=list(manager.flist)
    if not paths:raise ValueError('No source images available for export')
    root=Path(root)/('video' if getattr(manager,'video_mode',False) else 'image')
    root.mkdir(parents=True,exist_ok=True)
    write_source_catalog(manager,root)
    names=source_names(manager,paths)
    formats=params[35];bits=output+1
    if bits&4 and not manager.draw_points:
        raise ValueError('No magnification box; add a box before exporting magnifier images')
    moves=[]
    visible=display_indices(registry,params)
    with TemporaryDirectory(prefix='mulimg-export-') as directory:
        stage=CustomPipeline(Path(directory)/'processing')
        stage.configure(workers,memory)
        stage.set_window('export','page',(manager.action_count,manager.action_count),manager.action_count)
        try:
            with stage.prepare(manager,paths,manager.action_count,'export','page') as results:
                mosaics={};states={};reference=None
                for index in indices:
                    work=manager.video_stitch_snapshot()
                    work.layout_params=copy.deepcopy(params)
                    work.layout_params[38]=False
                    work.layout_params[32]=index is not None and index!=original
                    work.layout_params[37]=0 if index is None else index
                    work._custom_results=results
                    work._video_lazy_frames=True
                    work._video_memory_budget=memory
                    work.flist=paths
                    work.draw_points=copy.deepcopy(manager.draw_points)
                    if reference is not None:work.layout_params[6]=list(reference)
                    algorithm='original' if index is None else work.algorithm_output_name(index)
                    base=root/'algorithms'/algorithm
                    processed=results.get(index,paths)
                    if bits&2:
                        for source,relative in zip(processed,names):
                            target=base/('selected' if index==original or index is None else 'processed')/relative
                            target.parent.mkdir(parents=True,exist_ok=True)
                            raw=index==original or index is None
                            if raw and formats==0:
                                target=target.with_suffix(Path(source).suffix)
                                shutil.copyfile(source,target)
                            else:
                                with Image.open(source) as image:
                                    work.ImgF.save_img_diff_format(target,image,formats,use_vector_titles=False)
                            if raw and params[11] and not getattr(manager,'video_mode',False):
                                moves.append((source,target))
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
                        target=base/'stitched'/page_name(manager.action_count)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        work.ImgF.save_img_diff_format(target,work.img,formats)
                        private=Path(directory)/f'mosaic_{len(mosaics)}.png'
                        work.img.save(private,format='PNG',compress_level=1)
                        mosaics[index]=(private,work.img.size)
                        states[index]=copy.deepcopy(work.pdf_title_layers)
                    if bits&4 and work.draw_points:
                        work.crop_points_process(copy.deepcopy(work.draw_points),img_mode=1)
                        for number,(image,relative) in enumerate(zip(work.img_list,names)):
                            tile=work.img_preprocessing(image,rowcol=work.get_img_row_col(number))
                            for crop_id,crop in enumerate(work.magnifier_preprocessing(tile,img_mode=1)):
                                target=base/'magnifier_images'/Path(relative).parent/f'crop_{crop_id+1:03d}'/Path(relative).name
                                target.parent.mkdir(parents=True,exist_ok=True)
                                work.ImgF.save_img_diff_format(target,crop,formats,use_vector_titles=False)
                    work.clear_cache()
                if bits&1:
                    rows,cols=display_grid(registry,params)
                    width=max(mosaics[i][1][0] for i in visible)
                    height=max(mosaics[i][1][1] for i in visible)
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
                if not defer_moves:
                    _finish_moves(moves)
        finally:
            stage.close()
            stage.pool.shutdown(wait=True)
            stage.cleanup_future.result()
    return moves


def _finish_moves(moves):
    for source,target in moves:
        if Path(source).is_file() and Path(source).resolve()!=Path(target).resolve():
            Path(source).unlink()


def save_viewer(viewer,event=None):
    manager=viewer.ImgManager
    if getattr(manager,'type',None) is None or not manager.layout_params:
        viewer.SetStatusText_(['-1','-1','First select an input','-1'])
        return
    root=viewer.out_path_str
    if not root or not Path(root).is_dir():
        viewer.SetStatusText_(['-1','-1','First select the output directory','-1'])
        viewer.out_path(event)
        return
    output=viewer.choice_output.GetSelection()
    pages=range(manager.max_action_num) if viewer.auto_save_all.Value else [manager.action_count]
    moves=[]
    for page in pages:
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
        try:
            if viewer.shared_config.video_mode and not all(Path(path).is_file() for path in work.flist):
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
                    moves.extend(export_page(work,root,output,config.memory_budget,config.thread,defer_moves=True))
            else:
                moves.extend(export_page(work,root,output,viewer.shared_config.memory_budget,viewer.shared_config.thread,defer_moves=True))
        except Exception as error:
            viewer.SetStatusText_(['-1','-1',f'Export failed, page {page+1}: {error}','-1'])
            return
        work.clear_cache()
    _finish_moves(moves)
    viewer.SetStatusText_(['Save','-1','Save success!','-1'])
