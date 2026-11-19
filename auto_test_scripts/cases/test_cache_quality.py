"""Lossless export policy, PDF encoding and safe full-resolution cache reuse."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from PIL import Image
import test_export_modes as fixtures
from mulimgviewer.src.custom_pipeline import CustomPipeline
from mulimgviewer.src.mosaic_pipeline import MosaicStage
from mulimgviewer.src.export_controller import export_page
from mulimgviewer.src.video_paths import lossless_export


class CacheQualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExportModesTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manager=self.fixture.manager(1,False,False,'all')
        self.manager.layout_params.append(1)
        self.manager.layout_params[4]=[1,1]
        self.root=self.fixture.root

    def test_every_algorithm_cache_layer_uses_the_selected_encoding(self):
        from mulimgviewer.src.cache_layout import save_cache_image
        for selected,extension,encoding in ((0,'jpeg','JPEG'),(1,'png','PNG')):
            with self.subTest(cache_format=selected):
                m=self.manager;m.layout_params[41]=selected
                cache=CustomPipeline(self.root/f'encoding_{selected}')
                cache.mosaic_stage=MosaicStage(cache)
                cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
                try:
                    with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                        with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                            for future in plan.dependencies(processed):future.result(timeout=10)
                            paths=[Path(p) for group in processed.values() for p in group]
                            # Identity nodes can reuse original source files.
                            paths=[p for p in paths if cache.directory in p.parents]
                            paths.extend(Path(future.result()[0]) for future in plan.futures.values())
                            with plan.composed(processed) as (image,_):
                                final=self.root/f'composed.{extension}'
                                save_cache_image(image,final,extension)
                                paths.append(final)
                            self.assertGreater(len(paths),2)
                            for path in paths:
                                self.assertEqual(path.suffix,'.'+extension)
                                with Image.open(path) as image:self.assertEqual(image.format,encoding)
                    with cache.lease_export_results(m,list(m.flist),0) as reuse:
                        self.assertTrue([key for key in reuse if isinstance(key,int)])
                        self.assertTrue(reuse['_mosaics'])
                    if selected==0:
                        with cache.lease_export_results(m,list(m.flist),0) as reuse:
                            m._export_reused_results={key:value for key,value in reuse.items() if key!='_mosaics'}
                            m._export_reused_mosaics=reuse['_mosaics']
                            export_page(m,self.root/'png_from_jpeg_cache',0,512*1024**2,1)
                        exported=list((self.root/'png_from_jpeg_cache').rglob('*.png'))
                        self.assertTrue(exported)
                        for path in exported:
                            with Image.open(path) as image:self.assertEqual(image.format,'PNG',str(path))
                        del m._export_reused_results,m._export_reused_mosaics
                    m.layout_params[41]=1-selected
                    with cache.lease_export_results(m,list(m.flist),0) as reuse:
                        self.assertFalse([key for key in reuse if isinstance(key,int)])
                        self.assertFalse(reuse['_mosaics'])
                finally:
                    cache.close();cache.cleanup_future.result(timeout=10)

    def test_png_encoding_preserves_pixels_and_jpeg_does_not_tint_with_gap_color(self):
        from mulimgviewer.src.cache_layout import save_cache_image
        with Image.new('RGBA',(16,16),(220,40,80,128)) as source:
            png=self.root/'pixels.png';jpg=self.root/'pixels.jpeg'
            save_cache_image(source,png,'png');save_cache_image(source,jpg,'jpeg')
            with Image.open(png) as actual:
                self.assertEqual(actual.mode,'RGBA')
                self.assertEqual(actual.tobytes(),source.tobytes())
            with Image.open(jpg) as actual:
                self.assertEqual(actual.mode,'RGB')
                self.assertTrue(all(abs(a-b)<=3 for a,b in zip(actual.getpixel((0,0)),(237,147,167))))
            self.assertEqual(source.getpixel((0,0)),(220,40,80,128))

    def test_quality_policy_uses_captured_format_and_both_output_axes(self):
        m=self.manager
        for cache in (0,1,2):
            m.layout_params[41]=cache
            for fmt in (0,1,2):
                for scale in ([1,1],[.5,1],[1,.5],[2,2]):
                    m.layout_params[35]=fmt;m.layout_params[5]=scale
                    self.assertEqual(lossless_export(m),cache in (1,2) and fmt!=0 and min(scale)>=1)

    def test_auto_resolves_both_axes_and_invalidates_lossy_algorithm_and_mosaic_results(self):
        from mulimgviewer.src.video_paths import manager_cache_format,resolve_cache_format
        from mulimgviewer.src.mosaic_pipeline import mosaic_request_key
        m=self.manager;m.layout_params[41]=2
        for fmt in (0,1,2):
            for scale in ([1,1],[2,1],[1,2],[.5,1],[1,.5],[.5,.5]):
                m.layout_params[35]=fmt;m.layout_params[5]=scale
                self.assertEqual(manager_cache_format(m),int(fmt in (1,2) and min(scale)>=1))
        for invalid in ([],[1],[float('nan'),1],[float('inf'),1],None):
            self.assertEqual(resolve_cache_format(2,1,invalid),0)
        m.layout_params[35]=0;m.layout_params[5]=[1,1]
        old_key=mosaic_request_key(m,None,m.flist,m.draw_points,0)[0]
        cache=CustomPipeline(self.root/'auto_cache');cache.mosaic_stage=MosaicStage(cache)
        cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
        try:
            with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                    for future in plan.dependencies(processed):future.result(timeout=10)
                    for future in plan.futures.values():
                        with Image.open(future.result()[0]) as image:self.assertEqual(image.format,'JPEG')
            m.layout_params[35]=1
            self.assertNotEqual(old_key,mosaic_request_key(m,None,m.flist,m.draw_points,0)[0])
            with cache.lease_export_results(m,list(m.flist),0) as reuse:
                self.assertFalse([key for key in reuse if isinstance(key,int)])
                self.assertFalse(reuse['_mosaics'])
        finally:
            cache.close();cache.cleanup_future.result(timeout=10)

    def test_full_resolution_algorithms_and_matching_mosaics_are_reused_for_pdf(self):
        m=self.manager;cache=CustomPipeline(self.root/'cache');cache.mosaic_stage=MosaicStage(cache)
        cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
        try:
            with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                    for future in plan.dependencies(processed):future.result(timeout=5)
            m.layout_params[35]=2
            with cache.lease_export_results(m,list(m.flist),0) as reuse:
                self.assertTrue([i for i in reuse if isinstance(i,int)])
                self.assertTrue(reuse['_mosaics'])
                m._export_reused_results={i:p for i,p in reuse.items() if isinstance(i,int)}
                m._export_reused_mosaics=reuse['_mosaics']
                with patch.object(CustomPipeline,'_submit_process',side_effect=AssertionError('algorithm recomputed')),patch.object(type(m),'stitch_images',side_effect=AssertionError('mosaic recomputed')):
                    export_page(m,self.root/'reused',0,512*1024**2,1)
            pdfs=list((self.root/'reused').rglob('*.pdf'));self.assertTrue(pdfs)
            for path in pdfs:
                content=path.read_bytes();self.assertNotIn(b'/DCTDecode',content)
                self.assertIn(b'/FlateDecode',content)
        finally:
            cache.close();cache.cleanup_future.result(timeout=10)

    def test_reuse_rejects_changed_inputs_and_never_upscales_preview_mosaics(self):
        m=self.manager;cache=CustomPipeline(self.root/'cache');cache.mosaic_stage=MosaicStage(cache)
        cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
        try:
            with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                    for future in plan.dependencies(processed):future.result(timeout=5)
            m.layout_params[5]=[2,2]
            with cache.lease_export_results(m,list(m.flist),0) as reuse:
                self.assertTrue([i for i in reuse if isinstance(i,int)])
                self.assertFalse(reuse.get('_mosaics'))
            Image.new('RGB',(24,16),'yellow').save(m.flist[0])
            with cache.lease_export_results(m,list(m.flist),0) as reuse:
                self.assertFalse([i for i in reuse if isinstance(i,int)])
                self.assertFalse(reuse.get('_mosaics'))
        finally:
            cache.close();cache.cleanup_future.result(timeout=10)

    def test_foreground_alpha_invalidates_mosaics_but_keeps_algorithm_results(self):
        m=self.manager;cache=CustomPipeline(self.root/'alpha_cache');cache.mosaic_stage=MosaicStage(cache)
        cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
        try:
            with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                    for future in plan.dependencies(processed):future.result(timeout=5)
            with cache.lease_export_results(m,list(m.flist),0) as reuse:self.assertTrue(reuse['_mosaics'])
            m.img_alpha=80
            with cache.lease_export_results(m,list(m.flist),0) as reuse:
                self.assertFalse(reuse['_mosaics'])
                self.assertTrue([i for i in reuse if isinstance(i,int)])
        finally:
            cache.close();cache.cleanup_future.result(timeout=10)

    def test_original_png_alpha_survives_loading_and_jpeg_is_flattened(self):
        from mulimgviewer.src.utils_img import ImgUtils
        m=self.fixture.manager(1,False,False,'original')
        Image.new('RGBA',(24,16),(200,40,60,64)).save(m.flist[0])
        m.get_img_list(flist=m.flist)
        self.assertEqual(m.img_list[0].getpixel((0,0)),(200,40,60,64))
        m.img_alpha=128
        tile=m.ImgF.add_alpha(m.img_list[0],m.img_alpha)
        self.assertEqual(tile.getpixel((0,0)),(200,40,60,32));tile.close()
        m.gap_color=(240,250,255,0)
        target=self.root/'transparent.png'
        with Image.new('RGBA',(24,16),(200,40,60,0)) as image:
            m.ImgF.save_img_diff_format(target,image,save_format=0)
        with Image.open(target.with_suffix('.jpg')) as image:
            self.assertTrue(all(abs(a-b)<=3 for a,b in zip(image.getpixel((10,8)),(255,255,255))))
        m.clear_cache()

    def test_jpeg_gap_colour_never_tints_image_tiles(self):
        m=self.manager
        foreground=(60,120,180)
        for opacity in (0,96,255):
            centres=[]
            for gap in ((240,20,30,255),(20,30,240,255)):
                m.gap_color=gap
                with Image.new('RGBA',(128,64),gap) as image:
                    with Image.new('RGBA',(80,48),foreground+(opacity,)) as tile:image.paste(tile,(16,8))
                    before=image.tobytes()
                    target=self.root/f'matte_{opacity}_{gap[0]}.png'
                    m.ImgF.save_img_diff_format(target,image,save_format=0)
                    self.assertEqual(image.tobytes(),before)
                    with Image.open(target.with_suffix('.jpg')) as jpeg:
                        centres.append(jpeg.getpixel((56,32)))
                        self.assertTrue(all(abs(a-b)<=4 for a,b in zip(jpeg.getpixel((112,32)),gap[:3])))
                    m.ImgF.save_img_diff_format(target,image,save_format=1)
                    with Image.open(target) as png:self.assertEqual(png.tobytes(),before)
            expected=tuple((value*opacity+255*(255-opacity)+127)//255 for value in foreground)
            for actual in centres:self.assertTrue(all(abs(a-b)<=4 for a,b in zip(actual,expected)),(actual,expected))
            self.assertTrue(all(abs(a-b)<=2 for a,b in zip(*centres)),centres)

    def test_composed_jpeg_keeps_foreground_independent_of_gap_colour(self):
        m=self.fixture.manager(1,False,False,'original')
        m.layout_params[4]=[1,1];m.layout_params[5]=[1,1];m.layout_params[6]=[80,48]
        m.layout_params[35]=0;m.draw_points=[];m.img_alpha=128
        for path in m.flist:Image.new('RGBA',(80,48),(60,120,180,128)).save(path)
        samples=[]
        for label,gap in [('red',(240,20,30,255)),('blue',(20,30,240,255))]:
            m.gap_color=gap
            output=self.root/f'composed_{label}'
            export_page(m,output,0,512*1024**2,1)
            with Image.open(output/'image/composed/page_000001.jpg') as image:samples.append(image.getpixel((40,24)))
        expected=tuple((c*64+255*191+127)//255 for c in (60,120,180))
        for sample in samples:self.assertTrue(all(abs(a-b)<=5 for a,b in zip(sample,expected)),(sample,expected))
        self.assertTrue(all(abs(a-b)<=2 for a,b in zip(*samples)),samples)

    def test_selected_jpeg_reencoding_keeps_injected_title_icc_and_dpi(self):
        from PIL import ImageCms
        from PIL.JpegImagePlugin import get_sampling
        from mulimgviewer.src.export_controller import _write_export_file
        m=self.manager;m.layout_params.append(80)
        source=self.root/'source_with_title.jpg';target=self.root/'selected.jpg'
        exif=Image.Exif();exif[37510]=b'ASCII\0\0\0Injected title'
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        with Image.new('RGB',(40,24),'red') as image:
            image.save(source,'JPEG',quality=20,subsampling=2,exif=exif,icc_profile=profile,dpi=(240,240))
        before=source.read_bytes()
        _write_export_file(m,source,target,0)
        self.assertEqual(source.read_bytes(),before)
        with Image.open(target) as image:
            self.assertEqual(get_sampling(image),0)
            self.assertEqual(image.getexif()[37510],exif[37510])
            self.assertEqual(image.info['icc_profile'],profile)
            self.assertEqual(image.info['dpi'],(240,240))
            self.assertEqual(image.size,(40,24))

    def test_quality_controls_all_algorithm_cache_layers_and_export(self):
        from PIL.JpegImagePlugin import get_sampling
        m=self.manager
        m.layout_params[41]=0;m.layout_params[35]=0;m.layout_params.append(25)
        cache=CustomPipeline(self.root/'quality_cache');cache.mosaic_stage=MosaicStage(cache)
        cache.configure(2,512*1024**2);cache.set_window('image','data',(0,0),0)
        tables=[]
        try:
            for quality in (25,95):
                m.layout_params[42]=quality
                with cache.mosaic_stage.plan(m,m.flist,0,'image','data',m.draw_points,lambda:False) as plan:
                    with cache.prepare(m,m.flist,0,'image','data',on_ready=plan.ready) as processed:
                        for future in plan.dependencies(processed):future.result(timeout=10)
                        paths=[Path(path) for group in processed.values() for path in group if cache.directory in Path(path).parents]
                        paths.extend(Path(f.result()[0]) for f in plan.futures.values())
                        self.assertTrue(paths)
                        current=[]
                        for path in paths:
                            with Image.open(path) as image:
                                self.assertEqual(get_sampling(image),0)
                                current.append(sum(image.quantization[0]))
                        tables.append(current)
                output=self.root/f'quality_export_{quality}'
                export_page(m,output,0,512*1024**2,1)
                for path in output.rglob('*.jpg'):
                    with Image.open(path) as image:
                        self.assertEqual(get_sampling(image),0)
                        self.assertEqual(sum(image.quantization[0]),current[0])
            self.assertEqual(len(tables[0]),len(tables[1]))
            for low,high in zip(*tables):self.assertGreater(low,high)
        finally:
            cache.close();cache.cleanup_future.result(timeout=10)

    def test_small_coloured_titles_keep_full_chroma_in_jpeg_exports(self):
        import numpy as np
        from PIL.JpegImagePlugin import get_sampling
        m=self.fixture.manager(1,False,False,'original')
        m.layout_params[6]=[640,400]
        m.layout_params[17][1]=True
        m.layout_params[17][8]='18'
        for path in m.flist:Image.new('RGB',(640,400),'white').save(path)
        for scale in (1,.2):
            m.layout_params[5]=[scale,scale]
            for colour in ((230,20,40),(10,90,230),(20,160,40)):
                with self.subTest(scale=scale,colour=colour):
                    m.layout_params[17][13]=colour
                    root=self.root/f'title_{scale}_{colour[0]}'
                    m.layout_params[35]=1
                    export_page(m,root/'png',0,512*1024**2,1)
                    m.layout_params[35]=0
                    export_page(m,root/'jpg',0,512*1024**2,1)
                    with Image.open(root/'png/image/composed/page_000001.png') as image:
                        reference=image.convert('RGB')
                    with reference:
                        legacy=root/'legacy.jpg';reference.save(legacy,'JPEG')
                        expected=np.asarray(reference,dtype=float)
                        coloured=expected.max(axis=2)-expected.min(axis=2)>30
                        self.assertTrue(coloured.any(),'The fixture must contain coloured title pixels')
                        with Image.open(legacy) as image:
                            old_error=np.abs(np.asarray(image,dtype=float)-expected)[coloured].mean()
                        with Image.open(root/'jpg/image/composed/page_000001.jpg') as image:
                            self.assertEqual(get_sampling(image),0)
                            self.assertEqual(image.size,reference.size)
                            new_error=np.abs(np.asarray(image,dtype=float)-expected)[coloured].mean()
                        self.assertLess(new_error,old_error*.5,(new_error,old_error))

    def test_jpeg_export_rebuilds_lossy_mosaic_but_reuses_png(self):
        from mulimgviewer.src.custom_func.contract import original_index
        m=self.fixture.manager(1,False,False,'original')
        m.layout_params[35]=0
        index=original_index(m._custom_algorithm_registry)
        export_page(m,self.root/'baseline',0,512*1024**2,1)
        expected=(self.root/'baseline/image/composed/page_000001.jpg').read_bytes()
        preview=self.root/'preview.jpeg'
        with Image.new('RGB',(24,16),'magenta') as image:image.save(preview,'JPEG')
        m._export_reused_mosaics={index:(str(preview),{})}
        export_page(m,self.root/'rebuilt',0,512*1024**2,1)
        self.assertEqual((self.root/'rebuilt/image/composed/page_000001.jpg').read_bytes(),expected)
        preview=self.root/'preview.png'
        with Image.new('RGBA',(24,16),'cyan') as image:image.save(preview,'PNG')
        m._export_reused_mosaics={index:(str(preview),{})}
        with patch.object(type(m),'stitch_images',side_effect=AssertionError('PNG mosaic should be reused')):
            export_page(m,self.root/'reused',0,512*1024**2,1)

    def test_pdf_crops_and_selected_files_never_use_jpeg_embedding(self):
        m=self.manager;m.layout_params[35]=2
        export_page(m,self.root/'pdf',6,512*1024**2,1)
        files=list((self.root/'pdf').rglob('*.pdf'));self.assertTrue(files)
        self.assertTrue(any('magnifier_images' in path.parts for path in files))
        self.assertTrue(any('select_images' in path.parts for path in files))
        for path in files:self.assertNotIn(b'/DCTDecode',path.read_bytes(),str(path))


if __name__=='__main__':unittest.main()
