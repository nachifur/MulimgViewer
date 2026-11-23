"""Stable public names, original plugin selection and layered resource scheduling."""
import sys
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from PIL import Image, ImageDraw, ImageFont
from mulimgviewer.src.cache_layout import VisibleCache, source_names, page_name
from mulimgviewer.src.custom_func.contract import processing_indices, display_indices, display_grid
from mulimgviewer.src.custom_pipeline import WorkBudget
from mulimgviewer.src.canvas import LazyVideoImage, PixelCache, source_resolution


class CacheLayoutTests(unittest.TestCase):
    def test_page_json_separation_and_format_change_cleanup_preserve_replacement(self):
        from mulimgviewer.src.cache_layout import write_page_catalog, page_catalog_path, remove_page_catalog
        with tempfile.TemporaryDirectory() as directory:
            frames=Path(directory)/'composed/frames';frames.mkdir(parents=True)
            png=frames/'page_000001.png';jpg=png.with_suffix('.jpeg')
            Image.new('RGB',(10,6)).save(png)
            write_page_catalog(png,0,'image',['source.png'])
            target=page_catalog_path(png)
            self.assertEqual(target,frames.parent/'json'/'page_000001.json')
            self.assertEqual(json.loads(target.read_text())['size'],[10,6])
            Image.new('RGB',(10,6)).save(jpg)
            write_page_catalog(jpg,0,'video',['source.mp4'],(10,6))
            remove_page_catalog(png)
            self.assertTrue(target.exists(),'Old format cleanup must preserve the new descriptor')
            remove_page_catalog(jpg)
            self.assertFalse(target.exists())

    def test_video_cache_names_are_readable_and_collision_safe(self):
        from mulimgviewer.src.video_source import video_source_names
        paths=['one/01.mp4','two/01.mp4','three/01_002.mov','four/01.MOV','CON.mp4']
        names=video_source_names(paths)
        self.assertEqual(names,['01','01_002','01_002_002','01_003','_CON'])
        self.assertEqual(len(set(name.casefold() for name in names)),len(paths))

    def test_cache_catalog_is_separate_from_video_frames_and_points_to_original(self):
        from mulimgviewer.src.cache_layout import write_source_catalog
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manager=SimpleNamespace(video_mode=True,path_list=['cache/sources/frames/video/01'],
                _cache_original_paths=['original/01.mp4'],video_fps_list=[30],video_num_list=[100],skip=0)
            write_source_catalog(manager,root,split_media=True)
            target=root/'sources/json/video/01.json'
            self.assertTrue(target.is_file())
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['path'],str(Path('original/01.mp4').absolute()))
            self.assertFalse((root/'sources/video').exists())

    def test_image_view_copy_fallback_and_shared_page_pruning_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/'original.png';original.write_bytes(b'original pixels')
            publisher=VisibleCache(root/'sources/frames')
            target=publisher.root/'image';first={'page':0};second={'page':1}
            with patch('mulimgviewer.src.cache_layout.os.link',side_effect=OSError('Hard links unavailable')):
                publisher.publish(target,{'photos/original.png':original},first)
                publisher.publish(target,{'photos/original.png':original},second)
            cached=target/'photos/original.png'
            self.assertEqual(cached.read_bytes(),original.read_bytes())
            publisher.remove(first)
            self.assertTrue(cached.exists(),'Overlapping pages must share their cached source')
            publisher.remove(second)
            self.assertFalse(cached.exists())
            self.assertEqual(original.read_bytes(),b'original pixels')

    def test_public_hardlink_alias_does_not_trigger_false_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'private.png';source.write_bytes(b'pixels')
            publisher=VisibleCache(root/'algorithms')
            with self.assertRaises(ValueError):publisher._inside(publisher.root/'..'/'outside.png')
            target=publisher.root/'original'/'stitched'
            path=target/page_name(0)
            owner={'page':0};publisher.publish(target,{path.name:source},owner)
            original=Path.resolve
            def resolve(value,*args,**kwargs):
                return source if value==path else original(value,*args,**kwargs)
            with patch.object(Path,'resolve',new=resolve):
                publisher.publish(target,{path.name:source},{'page':0})
            self.assertTrue(path.is_file())
    def test_native_alpha_multiplies_existing_rgb_and_rgba_coverage_without_mutating_input(self):
        import numpy as np
        from mulimgviewer.src.utils_img import ImgUtils
        for mode in ('RGB','RGBA'):
            image=Image.new(mode,(9,7),(20,30,40) if mode=='RGB' else (20,30,40,70))
            original=image.tobytes()
            for alpha in (0,127,255):
                values=np.array(image)
                if mode=='RGB':values=np.concatenate((values,np.full((7,9,1),alpha,dtype=np.uint8)),axis=2)
                else:values[:,:,3]=((values[:,:,3].astype(np.uint16)*alpha+127)//255).astype(np.uint8)
                result=ImgUtils().add_alpha(image,alpha)
                self.assertEqual(result.tobytes(),values.tobytes())
                self.assertEqual(image.tobytes(),original)

    def test_shared_text_metrics_preserve_multiline_pixels_and_remain_bounded(self):
        from mulimgviewer.src import render_layout as render_metrics
        from mulimgviewer.src.render_layout import MeasuredFont, _metrics, _limit
        try:font=ImageFont.truetype('arial.ttf',20)
        except OSError:font=ImageFont.truetype('DejaVuSans.ttf',20)
        cached=MeasuredFont.wrap(font)
        import copy
        self.assertEqual(copy.deepcopy(cached).getbbox('copied'),font.getbbox('copied'))
        for text in ('Video 1/0s_frame_1.jpeg','first line\nsecond line','中文 / 1.mp4'):
            a=Image.new('RGBA',(240,80),'white');b=a.copy()
            ImageDraw.Draw(a).multiline_text((3,2),text,font=font,fill='black')
            ImageDraw.Draw(b).multiline_text((3,2),text,font=cached,fill='black')
            self.assertEqual(a.tobytes(),b.tobytes())
            self.assertEqual(font.getbbox(text),cached.getbbox(text))
        first=cached.getmask2('reused mask','L',start=[0,0])
        second=cached.getmask2('reused mask','L',start=[0,0])
        self.assertIs(first[0],second[0])
        for number in range(_limit+20):
            cached.getbbox(str(number))
            cached.getmask2(str(number)+' sample','L',start=[0,0])
        self.assertLessEqual(len(_metrics),_limit)
        self.assertLessEqual(len(render_metrics._masks),_limit)
        self.assertLessEqual(render_metrics._mask_bytes,render_metrics._mask_limit)

    def test_cached_image_headers_are_byte_bounded_and_cleaned_with_source(self):
        cache=PixelCache(700)
        self.assertTrue(cache.put_header('a',(3840,2160),'RGB',owner='source-a'))
        self.assertEqual(cache.get(('header','a')).size,(3840,2160))
        cache.put_header('b',(8000,8000),'RGBA',owner='source-b')
        self.assertLessEqual(cache.bytes,700)
        cache.prune({'source-b'})
        self.assertIsNone(cache.get(('header','a')))
        self.assertEqual(cache.get(('header','b')).mode,'RGBA')
        cache.configure(0)
        self.assertEqual(cache.bytes,0)
        self.assertIsNone(cache.get(('header','b')))

    def test_initial_video_memory_estimate_uses_scaled_canvas_not_full_resolution_tiles(self):
        from mulimgviewer.src.video_manager import VideoManager
        vm=object.__new__(VideoManager)
        paths=['a.mp4','b.mp4']
        vm.shared_config=SimpleNamespace(real_video_path=paths,count_per_action=2)
        vm._video_dimensions=dict(zip(paths,[(1080,1080),(1280,720)]))
        vm._ui=lambda:SimpleNamespace(img_size=[-1,-1])
        params=[None]*41
        params[:3]=[[4,6],[1,2],[3,1]]
        params[3]=[10,10,5,5,3,3,2,2];params[4]=[.15,.15]
        params[6]=[-1,-1];params[17]=[False,True]+[False]*6+[20]
        params[38]=False
        vm._render_snapshot=(SimpleNamespace(layout_params=params),[],False)
        output,inputs=vm._estimated_stitch_pixels()
        self.assertGreater(output,2204*766)
        self.assertLess(output*16+inputs*9,512*1024**2)
        params[4]=[1,1]
        native,_=vm._estimated_stitch_pixels()
        self.assertGreater(native,output*10)

    def test_preview_geometry_matches_mixed_sources_and_serial_boundary(self):
        from mulimgviewer.src.video_manager import VideoManager
        vm=object.__new__(VideoManager)
        params=[None]*41
        params[4]=[.15,.15];params[6]=[-1,-1];params[38]=False
        manager=SimpleNamespace(layout_params=params,img_stitch_mode=0)
        vm._render_snapshot=(manager,[],False)
        vm._video_dimensions={'a.mp4':(1080,1080),'b.mp4':(1280,720)}
        cfg=SimpleNamespace(count_per_action=2,parallel_to_sequential=False,
                            video_num_list=[3,5],real_video_path=['a.mp4','b.mp4'])
        image=Image.new('RGB',(1080,1080))
        self.assertEqual(vm._preview_resize_target(0,0,cfg,image),(177,135))
        cfg.parallel_to_sequential=True
        self.assertEqual(vm._preview_resize_target(0,0,cfg,image),(162,162))
        self.assertEqual(vm._preview_resize_target(0,2,cfg,image),(177,135))
        params[6]=[640,-1];params[4]=[.5,.5]
        self.assertEqual(vm._preview_resize_target(0,2,cfg,image),(320,244))
        manager.img_stitch_mode=1
        self.assertIsNone(vm._preview_resize_target(0,2,cfg,image))
        manager.img_stitch_mode=2
        self.assertEqual(vm._preview_resize_target(0,2,cfg,image),(540,540))
        params[38]=True
        self.assertEqual(vm._preview_resize_target(0,2,cfg,image),(540,540))

    def test_precomputed_preview_is_reused_without_changing_resize_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frame.png'
            image=Image.effect_noise((80,60),80).convert('RGB');image.save(path)
            expected=image.resize((17,13),Image.BICUBIC)
            cache=PixelCache(4096)
            key=('preview',str(path),(17,13),int(Image.BICUBIC))
            cache.put(key,expected,owner=str(path),priority=True)
            descriptor=LazyVideoImage(path,cache.get)
            actual=descriptor.resize((17,13),Image.BICUBIC)
            self.assertEqual(actual.tobytes(),expected.tobytes())
            self.assertIsNot(actual,expected)
            cache.configure(0)
            self.assertEqual(descriptor.resize((17,13),Image.BICUBIC).tobytes(),expected.tobytes())

    def test_resolution_normalization_trims_extremes_and_preserves_aspect(self):
        sizes=[(1,1),(1080,1080),(1280,720),(8000,8000)]
        self.assertEqual(source_resolution(sizes,(-1,-1)),(1180,900))
        self.assertEqual(source_resolution(sizes,(640,-1)),(640,488))
        self.assertEqual(source_resolution(sizes,(-1,-1),1),(1,1))
        self.assertEqual(source_resolution(sizes,(-1,-1),2),(8000,8000))

    def registry(self):
        return tuple((str(i),'/main.py','',json.dumps(dict(identity=i==3,role='original' if i==3 else 'algorithm')))
                     for i in range(11))
    def test_fixed_grid_and_original_checkbox_control_display_and_processing(self):
        params=[None]*41;params[32]=True;params[36]=False;params[37]=7
        params[38]=False;params[39]='2,2';params[40]=False
        registry=self.registry()
        self.assertEqual(processing_indices(registry,params),[7])
        self.assertEqual(display_indices(registry,params),[7])
        params[37]=3
        self.assertEqual(display_indices(registry,params),[])
        params[36]=True
        self.assertEqual(display_indices(registry,params),[3])
        params[38]=True
        self.assertEqual(display_indices(registry,params),[3,0,1,2])
        self.assertEqual(processing_indices(registry,params),[0,1,2])
        for vertical in (False,True):
            params[40]=vertical
            self.assertEqual(display_grid(registry,params),(2,2))
        params[36]=False;params[39]='2,1'
        self.assertEqual(display_indices(registry,params),[0,1])
        self.assertEqual(processing_indices(registry,params),[0,1])
        self.assertEqual(display_grid(registry,params),(2,1))
        params[32]=False;params[38]=False
        self.assertEqual(display_indices(registry,params),[3])
        self.assertEqual(display_grid(registry,params),(1,1))

    def test_visible_replacement_and_old_cleanup_keep_active_private_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);publisher=VisibleCache(root/'algorithms')
            old=root/'old.png';new=root/'new.png'
            Image.new('RGB',(3,2),'red').save(old);Image.new('RGB',(3,2),'blue').save(new)
            a={'page':0};b={'page':0}
            target=publisher.root/'Example'/'stitched'
            publisher.publish(target,{page_name(0):old},a)
            publisher.publish(target,{page_name(0):new},b)
            publisher.remove(a)
            with Image.open(target/page_name(0)) as image:self.assertEqual(image.getpixel((0,0)),(0,0,255))
            with Image.open(old) as image:self.assertEqual(image.getpixel((0,0)),(255,0,0))

    def test_unrelated_algorithms_publish_without_waiting_for_other_io(self):
        import threading,os
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);publisher=VisibleCache(root/'algorithms')
            source=root/'input.png';Image.new('RGB',(3,2)).save(source)
            entered=threading.Event();release=threading.Event();link=os.link
            def delayed(src,target):
                if 'Blocked' in Path(target).parts:
                    entered.set()
                    if not release.wait(3):raise TimeoutError('Blocked publication not released')
                return link(src,target)
            with patch('os.link',side_effect=delayed),ThreadPoolExecutor(2) as pool:
                slow=pool.submit(publisher.publish,publisher.root/'Blocked'/'stitched',{'frame.png':source},{'page':0})
                try:
                    self.assertTrue(entered.wait(2))
                    fast=pool.submit(publisher.publish,publisher.root/'Ready'/'stitched',{'frame.png':source},{'page':0})
                    fast.result(timeout=2)
                    self.assertTrue((publisher.root/'Ready'/'stitched'/'frame.png').is_file())
                finally:release.set()
                slow.result(timeout=2)

    def test_publication_does_not_remove_other_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);publisher=VisibleCache(root/'algorithms');source=root/'input.png'
            Image.new('RGB',(3,2)).save(source)
            a={'page':0};b={'page':1};target=publisher.root/'original'/'stitched'
            publisher.publish(target,{page_name(0):source},a);publisher.publish(target,{page_name(1):source},b)
            publisher.remove(a)
            self.assertTrue((target/page_name(1)).is_file())

    def test_source_folders_disambiguate_names_without_changing_filenames(self):
        manager=SimpleNamespace(path_list=['a','b'])
        values=source_names(manager,['a/frame.jpeg','b/frame.jpeg','a/frame.jpeg'])
        self.assertEqual(values,['source_001/frame.png','source_002/frame.png','source_001/entry_002/frame.png'])

    def test_outer_ready_work_has_priority_over_queued_processing(self):
        budget=WorkBudget();budget.configure(1,None)
        order=[]
        def work(priority):
            with budget.acquire(priority=priority):order.append(priority)
        with ThreadPoolExecutor(2) as pool:
            with budget.acquire():
                a=pool.submit(work,0);b=pool.submit(work,2)
                # Deterministic barrier: both requests must be queued before release.
                import time
                deadline=time.monotonic()+2
                while len(budget.waiting)<2 and time.monotonic()<deadline:time.sleep(.001)
                self.assertEqual(len(budget.waiting),2)
            a.result(timeout=2);b.result(timeout=2)
        self.assertEqual(order,[2,0])

    def test_lazy_processed_png_preserves_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frame.png';Image.new('RGBA',(4,4),(10,20,30,80)).save(path)
            image=LazyVideoImage(path).resize((2,2))
            self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getpixel((0,0))[3],80)

    def test_nested_video_frames_keep_original_video_title_parent(self):
        from mulimgviewer.src.utils_img import ImgManager
        manager=ImgManager();manager.video_mode=True
        manager.path_list=['cache_frames/sources/video/source_001/frames','cache_frames/sources/video/source_002/frames']
        manager._cache_original_paths=['meeting.mp4','experiment.mp4']
        self.assertEqual(manager.display_source_parent(Path(manager.path_list[0])/'0s_frame_1.jpeg'),'meeting')
        self.assertEqual(manager.display_source_parent(Path(manager.path_list[1])/'0s_frame_1.jpeg'),'experiment')


if __name__=='__main__':unittest.main()
