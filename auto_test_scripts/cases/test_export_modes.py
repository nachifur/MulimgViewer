"""Real layered exports: output bits, input modes, algorithms and formats."""
import copy
import json
import sys
import tempfile
import unittest
import wx
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from PIL import Image
from mulimgviewer.src.utils_img import ImgManager
from mulimgviewer.src.custom_func.runtime import capture_algorithms,AlgorithmSession
from mulimgviewer.src.export_controller import export_page, selection_slots, source_slot
from mulimgviewer.src.render_layout import gap_pair


class ExportModesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for folder,color in (('a','red'),('b','blue')):
            path=self.root/folder;path.mkdir()
            for index in range(2):Image.new('RGB',(24,16),color).save(path/f'{index}.png')

    def manager(self,kind,serial,sequential,algorithm,video=False):
        m=ImgManager()
        paths=[str(self.root/'a'),str(self.root/'b')]
        listing=self.root/'list.txt'
        listing.write_text('\n'.join(str(self.root/folder/'0.png') for folder in ('a','b')),encoding='utf-8')
        target={0:str(self.root),1:paths,2:paths[0],3:str(listing)}[kind]
        # Automatic input must not discover export folders created by earlier cases.
        if kind==0:
            target=self.root/'automatic';target.mkdir(exist_ok=True)
            import shutil
            for folder in ('a','b'):
                if not (target/folder).exists():shutil.copytree(self.root/folder,target/folder)
        m.init(target,type=kind,parallel_to_sequential=serial and kind in (0,1))
        p=[None]*41
        p[:7]=[[1,2],[1,1],[2,1],[2,2,0,0,0,0,0,0],[.5,.5],[1,1],[24,16]]
        p[7:17]=[0,[1,1],[wx.Colour(255,0,0,255)],[1,1],False,False,2,True,True,True]
        p[17]=[False,False,False,True,True,True,True,0,'12',[str(Path(__file__).resolve().parents[2]/'src/mulimgviewer/font/using/01_Arial.ttf')],0,False,False,'']
        p[18:32]=[True,serial,False,0,sequential,False,False,False,False,False,[24,16],[1,1],False,[1,1]]
        p[32:]=[algorithm=='single','',0,1,True,1,algorithm=='all','2,2',False]
        m.layout_params=p
        m._custom_algorithm_registry=capture_algorithms(['Image Enhancement','Gaussian Blur']) + (
            ('Original','/fixture/Original/main.py','',json.dumps(dict(
                role='original',cache_name='original',identity=True,device='cpu'))),)
        m._custom_algorithm_session=AlgorithmSession(m._custom_algorithm_registry)
        m.set_count_per_action(2 if serial or kind in (2,3) else 1)
        m.set_action_count(0);m.get_flist()
        m.draw_points=[[2,2,8,8,.5,.5,False]]
        m.gap_color=(255,255,255,255)
        m.video_mode=video
        if video:
            m.video_fps_list=[10.]*len(m.path_list);m.video_num_list=[2]*len(m.path_list)
        return m

    def export_job(self, manager, workers=2, video=False):
        from types import SimpleNamespace
        output=self.root/'parallel_export';output.mkdir(exist_ok=True)
        return SimpleNamespace(ImgManager=manager,out_path_str=str(output),
            choice_output=SimpleNamespace(GetSelection=lambda:0),
            auto_save_all=SimpleNamespace(Value=True),save_format=SimpleNamespace(GetSelection=lambda:0),
            xy_magnifier=[],shared_config=SimpleNamespace(video_mode=video,memory_budget=256*1024**2,thread=workers),
            SetStatusText_=lambda values:None)

    def test_bulk_pages_really_stitch_in_parallel_with_one_shared_budget(self):
        import threading
        from unittest.mock import patch
        from contextlib import contextmanager
        from mulimgviewer.src import export_controller as controller
        m=self.manager(1,False,False,'original')
        job=self.export_job(m)
        barrier=threading.Barrier(2);lock=threading.Lock();active=peak=0;budgets=set()
        stitch=ImgManager.stitch_images
        def concurrent(work,*args,**kwargs):
            nonlocal active,peak
            with lock:
                active+=1;peak=max(peak,active);budgets.add(id(work._export_budget))
            try:
                barrier.wait(timeout=10)
                return stitch(work,*args,**kwargs)
            finally:
                with lock:active-=1
        with patch.object(ImgManager,'stitch_images',concurrent):controller.save_viewer(job)
        self.assertEqual(peak,2)
        self.assertEqual(len(budgets),1)
        out=Path(job.out_path_str)/'image'
        for path in (out/'composed').glob('*.jpg'):
            self.assertEqual(path.read_bytes(),(out/'algorithms/original/stitch_images'/path.name).read_bytes())
        self.assertEqual(len(list((out/'composed').glob('*.jpg'))),2)

    def test_injected_title_changes_one_source_and_keeps_decoded_pixels(self):
        for suffix in ('.jpg','.png','.tiff'):
            m=self.manager(1,False,False,'original')
            path=self.root/('injection'+suffix)
            with Image.new('RGB',(32,20),(18,90,170)) as image:image.save(path)
            with Image.open(path) as image:before=image.tobytes()
            other=Path(m.flist[1]);unchanged=other.read_bytes()
            m.flist[0]=str(path)
            self.assertTrue(m.update_image_exif_37510(str(path),'Only this image'))
            self.assertEqual(other.read_bytes(),unchanged)
            with Image.open(path) as image:self.assertEqual(image.tobytes(),before)
            self.assertEqual(m.get_display_title_from_cache(0,'original title',False),'original title')
            self.assertEqual(m.get_display_title_from_cache(0,'original title',True),'Only this image')
            self.assertFalse(list(self.root.glob('.title-*')))

    def test_page_cleanup_drains_its_kernels_without_closing_shared_workers(self):
        import threading
        from concurrent.futures import TimeoutError
        from unittest.mock import patch
        from mulimgviewer.src.custom_pipeline import CustomPipeline
        from mulimgviewer.src.pipeline_executor import ImageWorkers
        pool=ImageWorkers(2);stage=CustomPipeline(self.root/'shared_cleanup',pool=pool)
        release=threading.Event();started=threading.Event()
        def kernel():
            started.set();release.wait(5)
        future=pool.submit(kernel);stage.entries['inflight']={'future':future,'pins':0}
        try:
            self.assertTrue(started.wait(2))
            with patch.object(stage,'_prune'):
                stage.close()
                with self.assertRaises(TimeoutError):stage.cleanup_future.result(timeout=.1)
                release.set();stage.cleanup_future.result(timeout=3)
            self.assertEqual(pool.submit(lambda:42).result(timeout=2),42)
        finally:
            release.set();pool.shutdown(wait=True)

    def test_ordered_algorithms_disable_page_overlap(self):
        import threading
        from unittest.mock import patch
        from mulimgviewer.src import export_controller as controller
        m=self.manager(1,False,False,'original');job=self.export_job(m,4)
        pages=[];threads=set();export=controller.export_page
        def record(work,*args,**kwargs):
            pages.append(work.action_count);threads.add(threading.get_ident())
            return export(work,*args,**kwargs)
        with patch.object(controller,'current_only',return_value=True),patch.object(controller,'export_page',record):
            controller.save_viewer(job)
        self.assertEqual(pages,[0,1]);self.assertEqual(len(threads),1)

    def test_parallel_cancellation_commits_only_contiguous_pages_and_can_resume(self):
        import threading
        from concurrent.futures import CancelledError
        from unittest.mock import patch
        from mulimgviewer.src import export_controller as controller
        m=self.manager(1,False,False,'original');job=self.export_job(m)
        job._export_resume={'completed':0,'moves':[]}
        cancel=threading.Event();release=threading.Event();job._export_cancelled=cancel.is_set
        def progress(value):
            if value>=.5:cancel.set();release.set()
        job._export_progress=progress
        export=controller.export_page
        def delayed(work,*args,**kwargs):
            if work.action_count==1:
                if not release.wait(10):raise RuntimeError('First page was never committed')
            return export(work,*args,**kwargs)
        with patch.object(controller,'export_page',delayed),self.assertRaises(CancelledError):
            controller.save_viewer(job)
        self.assertEqual(job._export_resume['completed'],1)
        self.assertTrue(all(Path(path).is_file() for path in m.flist))
        cancel.clear();job._export_progress=lambda value:None;pages=[]
        def resumed(work,*args,**kwargs):
            pages.append(work.action_count);return export(work,*args,**kwargs)
        with patch.object(controller,'export_page',resumed):controller.save_viewer(job)
        self.assertEqual(pages,[1]);self.assertEqual(job._export_resume['completed'],2)

    def test_independent_video_sources_decode_in_parallel_before_rendering(self):
        import threading
        from types import SimpleNamespace
        from mulimgviewer.src import export_controller as controller
        m=self.manager(1,False,False,'original',video=True);job=self.export_job(m,2,True)
        job.shared_config.video_num_list=[2,2];job.shared_config.count_per_action=1
        job.shared_config.parallel_to_sequential=False
        job.shared_config.real_video_path=['first.mp4','second.mp4']
        job.shared_config.video_path=list(m.path_list)
        barrier=threading.Barrier(2);seen=[];lock=threading.Lock()
        def decode(path,first,last,vid,config):
            with lock:seen.append((vid,first))
            barrier.wait(timeout=10)
            for index in range(first,last+1):
                Image.new('RGB',(24,16),'red' if vid==0 else 'blue').save(Path(config.video_path[vid])/f'{index}.png')
        job.video_manager=SimpleNamespace(_save_frame=decode,
            _filename_converter=lambda index,vid,config:f'{index}.png',working_bytes=lambda path:8*1024**2)
        job._export_isolate_video=True
        controller.save_viewer(job)
        self.assertEqual(sorted(seen),[(0,0),(0,1),(1,0),(1,1)])
        self.assertEqual(len(list((Path(job.out_path_str)/'video/composed').glob('*.jpg'))),2)

    def test_selection_uses_clicked_position_across_sources_not_filename(self):
        from types import SimpleNamespace
        paths=[f'/inputs/a/{i}.png' for i in range(3)]+[f'/inputs/b/different_{i}.png' for i in range(3)]
        for video in (False,True):
            m=SimpleNamespace(flist=paths,type=1,video_mode=video,path_list=['a','b'],parallel_to_sequential=False)
            self.assertEqual(selection_slots(m,1),[1,4])
            self.assertEqual(selection_slots(m,5),[2,5])
            m.flist=paths[:4]
            self.assertEqual(selection_slots(m,2),[2])
            m.flist=paths;m.parallel_to_sequential=True
            self.assertEqual(selection_slots(m,4),[4])
            m.parallel_to_sequential=False;m.type=2;m.path_list=['a']
            self.assertEqual(selection_slots(m,1),[1])
            m.type=3;m.video_mode=False;m.path_list=paths
            self.assertEqual(selection_slots(m,4),[4])
            m.type=1;m.video_mode=True;m.path_list=['a','b']
            self.assertEqual(selection_slots(m,4),[1,4])

    def test_image_file_list_selects_only_clicked_entry_even_from_one_folder(self):
        from types import SimpleNamespace
        paths=[str(self.root/'a'/f'{index}.png') for index in range(2)]
        manager=SimpleNamespace(type=3,video_mode=False,flist=paths,parallel_to_sequential=False)
        self.assertEqual(selection_slots(manager,1),[1])

    def test_flattened_parallel_export_selects_one_source_and_preserves_stitch(self):
        from mulimgviewer.src.export_controller import save_viewer
        for video in (False,True):
            for output in (1,2):
                with self.subTest(video=video,output=output):
                    m=self.manager(1,True,False,'single')
                    m.set_count_per_action(1);m.set_action_count(1);m.get_flist()
                    self.assertEqual(len(m.flist),1)
                    m.video_mode=video
                    m._cache_input_mode='Parallel manual'
                    original=list(m.flist)
                    job=self.export_job(m,video=video)
                    job.auto_save_all.Value=False
                    out=self.root/f'flat_selection_{video}_{output}';out.mkdir()
                    job.out_path_str=str(out)
                    job.choice_output.GetSelection=lambda:output
                    job._status_selected_grid=0
                    if video:
                        from types import SimpleNamespace
                        job.shared_config.video_path=list(m.path_list)
                        job.shared_config.real_video_path=list(m.path_list)
                        job.shared_config.video_num_list=[2,2]
                        job.shared_config.video_fps_list=[10.,10.]
                        job.shared_config.count_per_action=1
                        job.shared_config.parallel_to_sequential=True
                        decoded=[]
                        def decode(path,first,last,vid,config):
                            decoded.append((vid,first,last))
                            for index in range(first,last+1):
                                (Path(config.video_path[vid])/f'{index}.png').write_bytes((Path(path)/f'{index}.png').read_bytes())
                        job._export_isolate_video=True
                        job.video_manager=SimpleNamespace(_filename_converter=lambda index,vid,config:f'{index}.png',
                            _save_frame=decode,working_bytes=lambda path:1024**2)
                    if output==2:
                        baseline=out.with_name(out.name+'_stitch');baseline.mkdir()
                        job.out_path_str=str(baseline);job.choice_output.GetSelection=lambda:0
                        save_viewer(job)
                        job.out_path_str=str(out);job.choice_output.GetSelection=lambda:output
                    if video:decoded.clear()
                    save_viewer(job)
                    if video:self.assertEqual(sorted(decoded),[(0,1,1)])
                    root=out/('video' if video else 'image')
                    for name in ('original','Gaussian Blur'):
                        selected=list((root/'algorithms'/name/'select_images').rglob('*.jpg'))
                        self.assertEqual(len(selected),1)
                        self.assertEqual({path.stem for path in selected},{'1'})
                    if output==2:
                        self.assertEqual(len(list((root/'composed').glob('*.jpg'))),1)
                        for image in (root/'composed').glob('*.jpg'):
                            self.assertEqual(image.read_bytes(),(baseline/('video' if video else 'image')/'composed'/image.name).read_bytes())
                    else:self.assertFalse((root/'composed').exists())
                    self.assertEqual(m.flist,original)

    def test_painted_algorithm_cell_resolves_raw_slot_and_rejects_blank(self):
        from types import SimpleNamespace
        m=SimpleNamespace(flist=['a','b'],xy_grids_id_list=[3,0,4,2,1],
            _status_source_slots=[0,1,0,1,-1])
        self.assertEqual(source_slot(m,0),1)
        self.assertEqual(source_slot(m,3),0)
        self.assertIsNone(source_slot(m,2))
        self.assertIsNone(source_slot(m,20))

    def test_selected_files_include_all_visible_algorithms_and_keep_previous_picks(self):
        for folder in ('a','b'):
            Image.new('RGB',(24,16),'green').save(self.root/folder/'2.png')
        for video in (False,True):
            m=self.manager(1,False,True,'all',False)
            m.layout_params[1]=[1,3];m.set_count_per_action(3);m.get_flist()
            m.video_mode=video
            self.assertEqual(len(m.flist),6)
            selected=selection_slots(m,4)
            self.assertEqual(selected,[1,4])
            out=self.root/f'picks_{video}'
            export_page(m,out,1,512*1024**2,2,selected_slots=selected)
            base=out/('video' if video else 'image')/'algorithms'
            for name in ('original','Image Enhancement','Gaussian Blur'):
                picked=sorted((base/name/'select_images').rglob('*.png'))
                self.assertEqual(len(picked),2,name)
                self.assertEqual({p.name for p in picked},{'1.png'})
                if name!='original':self.assertEqual(len(list((base/name/'processed_img').rglob('*.png'))),6)
            export_page(m,out,1,512*1024**2,2,selected_slots=[0,3])
            self.assertEqual(len(list((base/'original/select_images').rglob('*.png'))),4)

    def test_save_all_visits_every_page_reuses_one_pool_and_preserves_live_state(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from mulimgviewer.src import export_controller as controller
        from mulimgviewer.src.custom_pipeline import CustomPipeline
        case=0
        for kind in (0,1,2,3):
            for serial,sequential in ((False,False),(True,False),(False,True)):
                for algorithm in ('original','single','all'):
                    with self.subTest(kind=kind,serial=serial,sequential=sequential,algorithm=algorithm):
                        m=self.manager(kind,serial,sequential,algorithm)
                        m.set_count_per_action(1);m.set_action_count(1);m.get_flist()
                        previous=(m.action_count,list(m.flist),copy.deepcopy(m.layout_params))
                        out=self.root/f'bulk_{case}';out.mkdir();case+=1
                        statuses=[];progress=[]
                        viewer=SimpleNamespace(ImgManager=m,out_path_str=str(out),
                            choice_output=SimpleNamespace(GetSelection=lambda:6),
                            auto_save_all=SimpleNamespace(Value=True),save_format=SimpleNamespace(GetSelection=lambda:1),
                            xy_magnifier=[],shared_config=SimpleNamespace(video_mode=False,memory_budget=512*1024**2,thread=1),
                            SetStatusText_=statuses.append,_export_progress=progress.append)
                        with patch.object(controller,'CustomPipeline',wraps=CustomPipeline) as constructor:
                            controller.save_viewer(viewer)
                            self.assertEqual(constructor.call_count,1)
                        self.assertEqual(statuses[-1][2],'Save success!')
                        self.assertEqual(len(list((out/'image/composed').glob('*.png'))),m.max_action_num)
                        self.assertFalse(list(out.rglob('magnifier_images')))
                        names=['original']+(['Gaussian Blur'] if algorithm=='single' else
                            ['Image Enhancement','Gaussian Blur'] if algorithm=='all' else [])
                        for name in names:
                            folder=out/'image/algorithms'/name
                            self.assertEqual(len(list((folder/'stitch_images').glob('*.png'))),m.max_action_num)
                            self.assertTrue(list((folder/'select_images').rglob('*.png')))
                        self.assertEqual((m.action_count,list(m.flist),m.layout_params),previous)
                        self.assertEqual(progress,sorted(progress))

    def test_independent_file_encoders_run_in_parallel_with_bounded_memory(self):
        import threading
        from unittest.mock import patch
        from concurrent.futures import ThreadPoolExecutor
        from mulimgviewer.src.export_controller import _write_export_files
        from mulimgviewer.src.custom_pipeline import WorkBudget
        m=self.manager(1,False,False,'all')
        budget=WorkBudget();budget.configure(4,2*1024**2)
        m._export_file_budget=budget
        jobs=[(str(self.root/folder/f'{index}.png'),self.root/'parallel'/f'{folder}_{index}.png')
              for folder in ('a','b') for index in range(2)]
        entered=threading.Event();release=threading.Event();lock=threading.Lock();active=[0,0]
        original=m.ImgF.save_img_diff_format
        def encode(*args,**kwargs):
            with lock:
                active[0]+=1;active[1]=max(active)
                if active[0]>=2:entered.set()
            try:
                self.assertTrue(release.wait(5))
                return original(*args,**kwargs)
            finally:
                with lock:active[0]-=1
        with ThreadPoolExecutor(4) as writers,ThreadPoolExecutor(1) as coordinator:
            m._export_writers=writers
            try:
                with patch.object(m.ImgF,'save_img_diff_format',side_effect=encode):
                    future=coordinator.submit(_write_export_files,m,jobs,2)  # PDF forces pixel encoding.
                    self.assertTrue(entered.wait(3));release.set();outputs=future.result(timeout=10)
                self.assertEqual(active[1],2)
                self.assertTrue(all(path.suffix=='.pdf' and path.is_file() for path in outputs))
                self.assertEqual((budget.active,budget.bytes),(0,0))
            finally:release.set()

    def test_save_all_partial_last_page_and_empty_job(self):
        from types import SimpleNamespace
        from mulimgviewer.src.export_controller import save_viewer
        Image.new('RGB',(24,16),'green').save(self.root/'a/2.png')
        m=self.manager(2,False,False,'single')
        out=self.root/'bulk_tail';out.mkdir();statuses=[]
        viewer=SimpleNamespace(ImgManager=m,out_path_str=str(out),
            choice_output=SimpleNamespace(GetSelection=lambda:2),auto_save_all=SimpleNamespace(Value=True),
            save_format=SimpleNamespace(GetSelection=lambda:1),xy_magnifier=[],
            shared_config=SimpleNamespace(video_mode=False,memory_budget=512*1024**2,thread=1),SetStatusText_=statuses.append)
        save_viewer(viewer)
        self.assertEqual(statuses[-1][2],'Save success!')
        self.assertEqual(len(list((out/'image/composed').glob('*.png'))),2)
        for name in ('original','Gaussian Blur'):
            self.assertEqual(len(list((out/'image/algorithms'/name/'select_images').rglob('*.png'))),3)
        m.max_action_num=0;save_viewer(viewer)
        self.assertEqual(statuses[-1][2],'Skipped: no pages to save')

    def test_video_exports_never_return_move_receipts_even_when_move_is_enabled(self):
        for kind in (0,1,2,3):
            for algorithm in ('original','single','all'):
                with self.subTest(kind=kind,algorithm=algorithm):
                    m=self.manager(kind,False,False,algorithm,video=True)
                    m.layout_params[11]=True
                    paths=list(m.flist)
                    moves=export_page(m,self.root/f'video_copy_{kind}_{algorithm}',2,
                        512*1024**2,2,defer_moves=True,selected_slots=list(range(len(paths))))
                    self.assertEqual(moves,[])
                    self.assertTrue(all(Path(path).is_file() for path in paths))
                    self.assertTrue(m.layout_params[11])  # Do not change the stored image-mode preference.

    def test_save_all_cancellation_keeps_sources_when_move_was_requested(self):
        from types import SimpleNamespace
        from concurrent.futures import CancelledError
        from mulimgviewer.src.export_controller import save_viewer
        m=self.manager(1,False,False,'all');m.layout_params[11]=True
        sources=[path for folder in m.path_list for path in Path(folder).glob('*.png')]
        out=self.root/'cancel_bulk';out.mkdir();cancelled=[False]
        def progress(value):
            if value>=.5:cancelled[0]=True
        viewer=SimpleNamespace(ImgManager=m,out_path_str=str(out),
            choice_output=SimpleNamespace(GetSelection=lambda:2),auto_save_all=SimpleNamespace(Value=True),
            save_format=SimpleNamespace(GetSelection=lambda:1),xy_magnifier=[],
            shared_config=SimpleNamespace(video_mode=False,memory_budget=512*1024**2,thread=1),
            SetStatusText_=lambda value:None,_export_progress=progress,_export_cancelled=lambda:cancelled[0])
        viewer._export_resume=dict(completed=0,moves=[])
        with self.assertRaises(CancelledError):save_viewer(viewer)
        self.assertTrue(all(path.is_file() for path in sources))
        self.assertEqual(viewer._export_resume['completed'],1)
        cancelled[0]=False;viewer._export_progress=lambda value:None
        save_viewer(viewer)
        self.assertFalse(any(path.exists() for path in sources))
        self.assertEqual(len(list((out/'image/algorithms/original/select_images').rglob('*.png'))),len(sources))

    def test_selection_only_viewer_action_uses_algorithm_pane_and_ignores_bulk_toggle(self):
        from types import SimpleNamespace
        from mulimgviewer.src.export_controller import save_viewer
        for folder in ('a','b'):Image.new('RGB',(24,16),'green').save(self.root/folder/'2.png')
        m=self.manager(1,False,True,'single')
        m.layout_params[1]=[1,3];m.set_count_per_action(3);m.get_flist()
        m.xy_grids_id_list=list(range(12));m._status_source_slots=tuple(range(6))*2
        output=self.root/'viewer_pick';output.mkdir()
        statuses=[]
        viewer=SimpleNamespace(ImgManager=m,out_path_str=str(output),
            choice_output=SimpleNamespace(GetSelection=lambda:0),auto_save_all=SimpleNamespace(Value=True),
            save_format=SimpleNamespace(GetSelection=lambda:1),xy_magnifier=[],
            shared_config=SimpleNamespace(video_mode=False,memory_budget=512*1024**2,thread=2),
            SetStatusText_=statuses.append)
        save_viewer(viewer,selection_only=True,selected_grid=10)
        self.assertEqual(statuses[-1][2],'Save success!')
        for name in ('original','Gaussian Blur'):
            picked=list((output/'image/algorithms'/name/'select_images').rglob('*.png'))
            self.assertEqual(len(picked),2)
            self.assertEqual({p.name for p in picked},{'1.png'})
        self.assertFalse((output/'image/composed').exists())
        self.assertTrue(all(Path(path).exists() for path in m.flist))

    def test_select_image_mode_matrix_exports_the_clicked_item_and_matching_sources(self):
        from types import SimpleNamespace
        from collections import Counter
        from PIL import ImageEnhance,ImageFilter
        from mulimgviewer.src.export_controller import save_viewer
        from mulimgviewer.src.custom_func.contract import display_indices
        for source,folder in enumerate(('a','b')):
            for index in range(3):
                Image.new('RGB',(24,16),(30+source*90,40+index*50,20+index*20)).save(self.root/folder/f'{index}.png')
        number=0
        for video in (False,True):
            for input_mode in range(4):
                for serial in (False,True):
                    for sequential in (False,True):
                        for algorithm in ('original','single','all'):
                            with self.subTest(video=video,input_mode=input_mode,
                                    parallel_to_sequential=serial,parallel_sequential=sequential,algorithm=algorithm):
                                # Videos from a file list use the same parallel
                                # source model as videos from auto/manual input.
                                kind=(2 if input_mode==0 else 1) if video else (2,0,1,3)[input_mode]
                                m=self.manager(kind,serial,sequential,algorithm,video=False)
                                m.layout_params.append(1)  # Lossless caches make the pixel oracle exact.
                                m.layout_params[1]=[1,3]
                                m._cache_input_mode=('Sequential','Parallel auto','Parallel manual','Image File List')[input_mode]
                                count=6 if m.parallel_to_sequential or kind in (2,3) else (3 if sequential else 1)
                                m.set_count_per_action(count);m.get_flist()
                                m.video_mode=video
                                if video:
                                    m.video_num_list=[3]*len(m.path_list);m.video_fps_list=[10.]*len(m.path_list)
                                    m.layout_params[11]=True  # Video selections must still never move frames.
                                paths=list(m.flist);clicked=len(paths)-1
                                parallel=input_mode in (1,2) and not serial
                                expected=([path for path in paths if Path(path).name==Path(paths[clicked]).name]
                                    if parallel else [paths[clicked]])
                                # The visual order can differ from source order
                                # and the clicked cell can belong to an algorithm.
                                panes=len(display_indices(m._custom_algorithm_registry,m.layout_params))
                                m._status_source_slots=tuple(range(len(paths)))*panes
                                m.xy_grids_id_list=list(reversed(range(len(paths)*panes)))
                                self.assertEqual(source_slot(m,0),clicked)
                                target=self.root/f'selection_matrix_{number}';target.mkdir();number+=1
                                statuses=[]
                                cfg=SimpleNamespace(video_mode=video,memory_budget=512*1024**2,thread=2,
                                    video_path=list(m.path_list),real_video_path=list(m.path_list),
                                    video_num_list=[3]*len(m.path_list),video_fps_list=[10.]*len(m.path_list),
                                    count_per_action=count,parallel_to_sequential=m.parallel_to_sequential)
                                viewer=SimpleNamespace(ImgManager=m,out_path_str=str(target),
                                    choice_output=SimpleNamespace(GetSelection=lambda:6),
                                    auto_save_all=SimpleNamespace(Value=True),save_format=SimpleNamespace(GetSelection=lambda:1),
                                    xy_magnifier=[],shared_config=cfg,SetStatusText_=statuses.append,
                                    video_manager=SimpleNamespace(_filename_converter=lambda index,vid,config:f'{index}.png'))
                                save_viewer(viewer,selection_only=True,selected_grid=0)
                                self.assertEqual(statuses[-1][2],'Save success!',statuses)
                                base=target/('video' if video else 'image')
                                transforms={'original':lambda image:image.copy()}
                                if algorithm in ('single','all'):
                                    transforms['Gaussian Blur']=lambda image:image.filter(ImageFilter.GaussianBlur(radius=2))
                                if algorithm=='all':
                                    transforms['Image Enhancement']=lambda image:ImageEnhance.Contrast(image).enhance(2)
                                self.assertEqual({path.name for path in (base/'algorithms').iterdir()},set(transforms))
                                for name,transform in transforms.items():
                                    selected=list((base/'algorithms'/name/'select_images').rglob('*.png'))
                                    self.assertEqual(len(selected),len(expected))
                                    actual_pixels=[];expected_pixels=[]
                                    for path in selected:
                                        with Image.open(path) as image:actual_pixels.append(image.convert('RGB').tobytes())
                                    for path in expected:
                                        with Image.open(path) as image,transform(image) as result:
                                            expected_pixels.append(result.convert('RGB').tobytes())
                                    self.assertEqual(Counter(actual_pixels),Counter(expected_pixels),name)
                                self.assertFalse((base/'composed').exists())
                                self.assertFalse(list(base.rglob('stitch_images')))
                                self.assertFalse(list(base.rglob('magnifier_images')))
                                self.assertTrue(all(Path(path).is_file() for path in paths))
        self.assertEqual(number,96)

    def test_select_image_retains_original_and_only_exports_visible_algorithm(self):
        from mulimgviewer.src.export_controller import save_viewer
        for mode,chosen in (('single','Gaussian Blur'),('all','Image Enhancement')):
            with self.subTest(custom=mode):
                m=self.manager(1,False,False,mode)
                m.layout_params[36]=False;m.layout_params[39]='1,1'
                m.xy_grids_id_list=[0,1];m._status_source_slots=(0,1)
                viewer=self.export_job(m)
                viewer.out_path_str=str(self.root/f'hidden_selection_{mode}')
                Path(viewer.out_path_str).mkdir()
                save_viewer(viewer,selection_only=True,selected_grid=1)
                base=Path(viewer.out_path_str)/'image/algorithms'
                self.assertEqual({path.name for path in base.iterdir()},{'original',chosen})
                for name in ('original',chosen):
                    self.assertEqual(len(list((base/name/'select_images').rglob('*.jpg'))),2)

    def test_select_image_rejects_blank_algorithm_pane_without_saving_a_default(self):
        from mulimgviewer.src.export_controller import save_viewer
        m=self.manager(1,False,False,'single')
        m.xy_grids_id_list=[0,1,2];m._status_source_slots=(0,1,-1)
        viewer=self.export_job(m);messages=[];viewer.SetStatusText_=messages.append
        save_viewer(viewer,selection_only=True,selected_grid=2)
        self.assertIn('Select a source image',messages[-1][2])
        self.assertFalse(list(Path(viewer.out_path_str).iterdir()))

    def test_video_export_directories_use_real_video_names_with_collision_suffixes(self):
        m=self.manager(1,False,False,'all',video=True)
        m._cache_original_paths=['/videos/left/clip.mp4','/videos/right/clip.mov']
        root=self.root/'named_video'
        export_page(m,root,6,512*1024**2,2)
        out=root/'video'
        expected={'clip','clip_002'}
        self.assertEqual({path.name for path in (out/'sources').iterdir()},expected)
        for name in expected:self.assertTrue((out/'sources'/name/'source.json').is_file())
        for algorithm in ('original','Image Enhancement','Gaussian Blur'):
            for kind in ('magnifier_images','select_images','origin_img_with_box','processed_img'):
                path=out/'algorithms'/algorithm/kind
                if kind=='processed_img' and algorithm=='original':continue
                self.assertEqual({entry.name for entry in path.iterdir()},expected)
        for source,path in zip(('clip','clip_002'),m._cache_original_paths):
            self.assertEqual(json.loads((out/'sources'/source/'source.json').read_text(encoding='utf-8'))['path'],str(Path(path).absolute()))

    def test_boxed_images_use_output_resolution_and_flat_numbered_crops(self):
        for folder in ('a','b'):
            for i in range(2):Image.new('RGB',(24,16),'green').save(self.root/folder/f'{i}.png')
        m=self.manager(1,False,False,'all')
        m.layout_params[4]=[.1,.1];m.layout_params[28]=[-1,-1]
        m.draw_points=[[.4,.4,1.2,1.0,.1,.1,False],[1.4,.2,2.0,.8,.1,.1,False]]
        out=self.root/'boxed'
        export_page(m,out,6,512*1024**2,2)
        for name in ('original','Image Enhancement','Gaussian Blur'):
            base=out/'image/algorithms'/name
            self.assertEqual({p.name for p in base.iterdir()},{'stitch_images','select_images','origin_img_with_box','magnifier_images'} | ({'processed_img'} if name!='original' else set()))
            for path in (base/'origin_img_with_box').rglob('*.png'):
                with Image.open(path) as image:
                    self.assertEqual(image.size,(24,16))
                    self.assertEqual(image.getpixel((4,4))[:3],(255,0,0))
            for kind in ('magnifier_images','select_images','origin_img_with_box'):
                self.assertEqual({path.name for path in (base/kind).iterdir()},{'a','b'})
            crops=list((base/'magnifier_images').rglob('*.png'))
            self.assertEqual(len(crops),4)
            self.assertEqual({p.parent.name for p in crops},{'a','b'})
            self.assertEqual({p.name[:4] for p in crops},{'001_','002_'})
        m.layout_params[5]=[2,2]
        export_page(m,self.root/'boxed_double',3,512*1024**2,2)
        for p in (self.root/'boxed_double/image/algorithms').glob('*/origin_img_with_box/*/*.png'):
            with Image.open(p) as image:self.assertEqual(image.size,(48,32))

    def test_fixed_canvas_and_hidden_original_apply_to_export(self):
        for video in (False,True):
            m=self.manager(1,False,False,'all',video)
            m.layout_params[36]=False;m.layout_params[39]='2,1'
            output=self.root/f'fixed_{video}'
            export_page(m,output,0,512*1024**2,2)
            root=output/('video' if video else 'image')
            with Image.open(root/'composed/page_000001.png') as composed, Image.open(root/'algorithms/Image Enhancement/stitch_images/page_000001.png') as tile:
                self.assertEqual(composed.size,(tile.width,tile.height*2+gap_pair(m.layout_params[3], 'func')[1]))
                self.assertEqual(composed.crop((0,0,tile.width,tile.height)).tobytes(),tile.tobytes())
            self.assertTrue((root/'algorithms/original/stitch_images/page_000001.png').is_file())
            m.layout_params[36]=True
            output=self.root/f'fixed_original_{video}'
            export_page(m,output,0,512*1024**2,2)
            root=output/('video' if video else 'image')
            self.assertFalse((root/'algorithms/Gaussian Blur').exists())

    def test_hidden_identity_only_selection_exports_a_blank_canvas(self):
        m=self.manager(1,False,False,'single')
        m.layout_params[36]=False;m.layout_params[37]=2;m.layout_params[39]='1,1'
        output=self.root/'blank'
        export_page(m,output,0,512*1024**2,2)
        with Image.open(output/'image/composed/page_000001.png') as image:
            self.assertEqual(image.getextrema(),tuple((c,c) for c in m.gap_color))

    def test_synchronous_all_function_fallback_hides_original_and_obeys_grid(self):
        from unittest.mock import patch
        m=self.manager(1,False,False,'all')
        m.layout_params[36]=False;m.layout_params[39]='2,1'
        calls=[]
        def processed(images,*args,**kwargs):
            index=kwargs['algorithm_type'];calls.append(index)
            return [Image.new('RGB',image.size,(10+index,20,30)) for image in images]
        with patch('mulimgviewer.src.utils_img.main_custom_func',side_effect=processed):
            images=m.get_all_func_img_list('2,1',[1,2],False,flist=m.flist)
        try:
            self.assertEqual(calls,[0,1])
            self.assertEqual(len(images),4)
            self.assertEqual([image.getpixel((0,0)) for image in images],[(10,20,30)]*2+[(11,20,30)]*2)
        finally:
            for image in images:image.close()

    def test_synchronous_algorithm_boundaries_use_func_gaps_inside_xy_grid(self):
        from unittest.mock import patch
        m=self.manager(1,False,False,'all')
        m.layout_params[3]=[11,13,17,19,23,29,31,37,41,43]
        m.layout_params[39]='2,2'
        with patch('mulimgviewer.src.utils_img.main_custom_func',
                side_effect=lambda images,*args,**kwargs:[image.copy() for image in images]):
            layout,_,_=m.stitch_img_init(0,[],flist=m.flist)
        # Each algorithm contains one row and two XY cells. Only the middle
        # boundary is Func; the two internal boundaries retain XY spacing.
        self.assertEqual(layout[2][1][0].tolist(),[0,17,11,17])
        self.assertEqual(layout[2][1][1].tolist(),[0,13])
        m.clear_cache()

    def test_all_output_choices_input_orders_and_algorithms(self):
        cases=0
        for kind in (0,1,2,3):
            for serial,sequential in ((False,False),(True,False),(False,True)):
                for algorithm in ('original','single','all'):
                    m=self.manager(kind,serial,sequential,algorithm)
                    for output in range(7):
                        with self.subTest(kind=kind,serial=serial,sequential=sequential,algorithm=algorithm,output=output):
                            destination=self.root/f'export_{cases}';cases+=1
                            export_page(m,destination,output,512*1024**2,2)
                            root=destination/'image';bits=output+1
                            names=['original']+(['Gaussian Blur'] if algorithm=='single' else ['Image Enhancement','Gaussian Blur'] if algorithm=='all' else [])
                            self.assertEqual((root/'composed'/'page_000001.png').exists(),bool(bits&1))
                            for name in names:
                                base=root/'algorithms'/name
                                self.assertEqual((base/'stitch_images'/'page_000001.png').exists(),bool(bits&1))
                                self.assertEqual(bool(list((base/('select_images' if name=='original' else 'processed_img')).rglob('*.png'))),bool(bits&2))
                                self.assertEqual(bool(list((base/'magnifier_images').rglob('*.png'))),bool(bits&4))
                            if bits&1:
                                with Image.open(root/'algorithms/original/stitch_images/page_000001.png') as image:
                                    self.assertGreaterEqual(image.width,48) # output_scale=1, preview_scale=.5
                            m.video_mode=True
                            m.video_fps_list=[10.]*len(m.path_list);m.video_num_list=[2]*len(m.path_list)
                            video_destination=self.root/f'video_export_{cases}'
                            export_page(m,video_destination,output,512*1024**2,2)
                            self.assertEqual((video_destination/'video/composed/page_000001.png').exists(),bool(bits&1))
                            for name in names:
                                base=video_destination/'video/algorithms'/name
                                self.assertEqual((base/'stitch_images/page_000001.png').exists(),bool(bits&1))
                                self.assertEqual(bool(list((base/('select_images' if name=='original' else 'processed_img')).rglob('*.png'))),bool(bits&2))
                                self.assertEqual(bool(list((base/'magnifier_images').rglob('*.png'))),bool(bits&4))
                            m.video_mode=False
        self.assertEqual(cases,252)

    def test_video_branch_and_all_output_formats(self):
        for algorithm in ('original','single','all'):
            m=self.manager(1,False,False,algorithm,video=True)
            for fmt,suffix in ((0,'.jpg'),(1,'.png'),(2,'.pdf')):
                with self.subTest(algorithm=algorithm,format=fmt):
                    m.layout_params[35]=fmt
                    output=self.root/f'video_{algorithm}_{fmt}'
                    export_page(m,output,6,512*1024**2,2)
                    files=list((output/'video').rglob('*'+suffix))
                    self.assertTrue(files)
                    self.assertTrue((output/'video/composed'/('page_000001'+suffix)).is_file())

    def test_move_selected_is_deferred_until_export_finishes_and_never_moves_video_frames(self):
        for video in (False,True):
            m=self.manager(1,False,False,'single',video=video)
            m.layout_params[11]=True
            sources=list(m.flist)
            output=self.root/f'move_{video}'
            export_page(m,output,2,512*1024**2,2)
            self.assertTrue((output/('video' if video else 'image')/'composed/page_000001.png').is_file())
            self.assertEqual([Path(p).exists() for p in sources],[video]*len(sources))
            if not video:
                for p in sources:Image.new('RGB',(24,16),'red').save(p)

    def test_move_only_removes_picked_positions_after_all_algorithms_succeed(self):
        m=self.manager(1,False,True,'single')
        m.layout_params[1]=[1,2];m.set_count_per_action(2);m.get_flist()
        m.layout_params[11]=True
        paths=list(m.flist)
        export_page(m,self.root/'move_position',1,512*1024**2,2,selected_slots=[1,3])
        self.assertEqual([Path(p).exists() for p in paths],[True,False,True,False])
        for name in ('original','Gaussian Blur'):
            self.assertEqual(len(list((self.root/'move_position/image/algorithms'/name/'select_images').rglob('*.png'))),2)

    def test_failed_algorithm_export_does_not_move_any_selected_original(self):
        from unittest.mock import patch
        from mulimgviewer.src.export_controller import _save_selected
        m=self.manager(1,False,False,'single');m.layout_params[11]=True
        def save(*args):
            if not args[6]:raise RuntimeError('simulated export failure')
            return _save_selected(*args)
        with patch('mulimgviewer.src.export_controller._save_selected',side_effect=save):
            with self.assertRaisesRegex(RuntimeError,'simulated export failure'):
                export_page(m,self.root/'failed_move',1,512*1024**2,2)
        self.assertTrue(all(Path(p).exists() for p in m.flist))

    def test_missing_boxes_skip_only_magnifier_and_keep_all_other_output_bits(self):
        for video in (False,True):
            for algorithm in ('original','single','all'):
                m=self.manager(1,False,False,algorithm,video=video)
                m.draw_points=[]
                for bits in (3,4,5,6,7):
                    with self.subTest(video=video,algorithm=algorithm,bits=bits):
                        destination=self.root/f'no_box_{video}_{algorithm}_{bits}'
                        export_page(m,destination,bits-1,512*1024**2,2)
                        root=destination/('video' if video else 'image')
                        self.assertEqual((root/'composed/page_000001.png').exists(),bool(bits&1))
                        names=['original']+(['Gaussian Blur'] if algorithm=='single' else ['Image Enhancement','Gaussian Blur'] if algorithm=='all' else [])
                        for name in names:
                            base=root/'algorithms'/name
                            self.assertEqual((base/'stitch_images/page_000001.png').exists(),bool(bits&1))
                            self.assertEqual(bool(list((base/'select_images').rglob('*.png'))),bool(bits&2))
                            self.assertFalse((base/'magnifier_images').exists())
                            self.assertFalse((base/'origin_img_with_box').exists())
                        self.assertTrue(all(Path(path).is_file() for path in m.flist))


    def test_hidden_original_is_exported_but_not_added_to_single_algorithm_composite(self):
        m=self.manager(1,False,False,'single')
        m.layout_params[36]=False
        output=self.root/'single_hidden'
        export_page(m,output,0,512*1024**2,2)
        root=output/'image'
        self.assertTrue((root/'algorithms/original/stitch_images/page_000001.png').is_file())
        with Image.open(root/'composed/page_000001.png') as actual, Image.open(root/'algorithms/Gaussian Blur/stitch_images/page_000001.png') as selected:
            gap_x,gap_y=gap_pair(m.layout_params[3], 'func')
            self.assertEqual(actual.size,(selected.width*2+gap_x,selected.height*2+gap_y))
            background=tuple((c,c) for c in m.gap_color)
            self.assertEqual(actual.crop((selected.width,0,selected.width+gap_x,actual.height)).getextrema(),background)
            self.assertEqual(actual.crop((0,selected.height,actual.width,selected.height+gap_y)).getextrema(),background)
            self.assertEqual(actual.crop((0,0,selected.width,selected.height)).tobytes(),selected.tobytes())
            self.assertEqual(actual.getpixel((actual.width-1,actual.height-1)),tuple(m.gap_color))

    def test_deferred_move_keeps_inputs_until_all_pages_have_succeeded(self):
        from mulimgviewer.src.export_controller import _finish_moves
        m=self.manager(1,False,False,'original')
        m.layout_params[11]=True
        moves=export_page(m,self.root/'defer_move',1,512*1024**2,2,defer_moves=True)
        self.assertTrue(moves)
        self.assertTrue(all(Path(source).exists() for source,_ in moves))
        _finish_moves(moves)
        self.assertFalse(any(Path(source).exists() for source,_ in moves))


if __name__=='__main__':unittest.main()
