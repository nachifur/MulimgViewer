"""Known-input decode and rendering checks; expectations are independent of app code."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

HOME=Path(__file__).resolve().parents[1]
ROOT=HOME.parent
sys.path[:0]=[str(HOME),str(ROOT/'src')]
from PIL import Image, ImageChops
from support.fixture_recipe import pixel_hash, expected_pair, frame
import test_export_modes as fixtures
from mulimgviewer.src.export_async import ExportDecoder
from mulimgviewer.src.export_controller import export_page

ASSETS=HOME/'assets'


class ReferenceAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.manifest=json.loads((ASSETS/'manifest.json').read_text(encoding='utf-8'))

    def test_checked_in_image_and_golden_pixels_match_independent_recipe(self):
        for section in ('images','goldens'):
            for relative,expected in self.manifest[section].items():
                with self.subTest(path=relative),Image.open(ASSETS/relative) as image:
                    self.assertEqual(pixel_hash(image),expected)
                    if section=='images':
                        path=Path(relative)
                        with frame(int(path.parent.name.split('_')[1]),int(path.stem.split('_')[1])-1) as oracle:
                            self.assertEqual(image.tobytes(),oracle.tobytes())
        self.assertLess(sum(p.stat().st_size for p in ASSETS.rglob('*') if p.is_file()),100_000)

    def test_real_video_decode_native_and_ffmpeg_preserve_all_known_pixels(self):
        for fallback in (False,True):
            for relative,entry in self.manifest['videos'].items():
                with self.subTest(fallback=fallback,path=relative),tempfile.TemporaryDirectory() as directory:
                    path=ASSETS/relative
                    decoder=ExportDecoder(lambda:False,decoder_budget=16*1024**2)
                    self.addCleanup(decoder.close)
                    if fallback:decoder.bank.disabled.add(str(path))
                    config=SimpleNamespace(video_fps_list=[4.],skip_frames=0,cache_save_format=1,video_path=[directory])
                    # Several ranges exercise continuation and backward reads.
                    for first,last in ((0,1),(2,entry['frames']-1),(0,0)):
                        decoder._save_frame(path,first,last,0,config)
                    for index,expected in enumerate(entry['rgb_sha256']):
                        with Image.open(Path(directory)/decoder._filename_converter(index,0,config)) as image:
                            self.assertEqual(image.format,'PNG');self.assertEqual(pixel_hash(image),expected)
                    decoder.close()

    def test_original_mosaics_match_checked_in_pixel_oracles_in_all_input_modes(self):
        fixture=fixtures.ExportModesTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        for kind in (0,1,2,3):
            with self.subTest(input_mode=kind):
                manager=fixture.manager(kind,False,False,'original')
                targets={0:str(ASSETS/'images'),1:[str(p) for p in sorted((ASSETS/'images').iterdir())],
                         2:str(ASSETS/'images/source_001'),3:str(ASSETS/'lists/images.txt')}
                manager.init(targets[kind],type=kind)
                manager.layout_params[0]=[1,2];manager.layout_params[1]=[1,1];manager.layout_params[2]=[1,1]
                manager.layout_params[3]=[0]*10;manager.layout_params[4]=[1,1];manager.layout_params[5]=[1,1]
                manager.layout_params[6]=[64,48];manager.layout_params[17][1]=False;manager.draw_points=[]
                manager.set_count_per_action(2 if kind in (2,3) else 1);manager.set_action_count(0);manager.get_flist()
                output=fixture.root/f'known_{kind}'
                export_page(manager,output,0,256*1024**2,2)
                with Image.open(output/'image/composed/page_000001.png') as actual,Image.open(ASSETS/f'expected/{"sequential" if kind==2 else "parallel"}.png') as expected:
                    self.assertEqual(actual.size,expected.size)
                    self.assertIsNone(ImageChops.difference(actual.convert('RGB'),expected).getbbox())

    def test_rotation_flip_and_unicode_exif_title_on_private_input_copies(self):
        import piexif
        import piexif.helper
        fixture=fixtures.ExportModesTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        manager=fixture.manager(2,False,False,'original')
        target=fixture.root/'private.png';shutil.copyfile(ASSETS/'images/source_001/frame_000001.png',target)
        manager.flist=[str(target)]
        with Image.open(target) as image:original=image.convert('RGB')
        try:
            manager.rotate(0)
            with Image.open(target) as actual,self.subTest(operation='rotate'):
                self.assertEqual(actual.tobytes(),original.transpose(Image.Transpose.ROTATE_270).tobytes())
            manager.flip(0)
            with Image.open(target) as actual,self.subTest(operation='flip'):
                self.assertEqual(actual.tobytes(),original.transpose(Image.Transpose.ROTATE_270).transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())
            jpeg=fixture.root/'metadata.jpg';original.save(jpeg);manager.flist=[str(jpeg)]
            title='Regression title \\u6d4b\\u8bd5'.encode().decode('unicode_escape')
            self.assertTrue(manager.update_image_exif_37510(str(jpeg),title))
            actual=piexif.helper.UserComment.load(piexif.load(str(jpeg))['Exif'][piexif.ExifIFD.UserComment])
            self.assertEqual(actual,title)
            # PNG title metadata is supported without changing rotated pixels.
            with Image.open(target) as image:before=image.tobytes()
            self.assertTrue(manager.update_image_exif_37510(str(target),title))
            with Image.open(target) as image:
                self.assertEqual(image.tobytes(),before)
                stored=piexif.load(image.info['exif'])['Exif'][piexif.ExifIFD.UserComment]
                self.assertEqual(piexif.helper.UserComment.load(stored),title)
        finally:original.close()

    def test_processed_pixels_and_second_level_composition_match_independent_oracles(self):
        from PIL import ImageEnhance, ImageFilter
        fixture=fixtures.ExportModesTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        manager=fixture.manager(1,False,False,'all')
        manager.layout_params.append(1)  # Exact pixel oracle requires lossless algorithm caches.
        manager.init([str(p) for p in sorted((ASSETS/'images').iterdir())],type=1)
        manager.layout_params[0]=[1,2];manager.layout_params[1]=[1,1];manager.layout_params[2]=[1,1]
        # The no-spacing oracle explicitly disables all five gap pairs.
        manager.layout_params[3]=[0]*10;manager.layout_params[4]=[1,1];manager.layout_params[5]=[1,1]
        manager.layout_params[6]=[64,48];manager.layout_params[17][1]=False
        manager.draw_points=[];manager.set_count_per_action(1);manager.get_flist()
        root=fixture.root/'algorithms'
        export_page(manager,root,0,256*1024**2,3)
        expected=Image.new('RGBA',(256,96),tuple(manager.gap_color))
        try:
            transforms=(('original',lambda image:image.copy()),
                ('Image Enhancement',lambda image:ImageEnhance.Contrast(image).enhance(2)),
                ('Gaussian Blur',lambda image:image.filter(ImageFilter.GaussianBlur(radius=2))))
            for slot,(algorithm,transform) in enumerate(transforms):
                mosaic=Image.new('RGB',(128,48))
                try:
                    for source in (1,2):
                        with frame(source,0) as original,transform(original) as processed:
                            mosaic.paste(processed,((source-1)*64,0))
                    path=root/'image/algorithms'/algorithm/'stitch_images/page_000001.png'
                    with Image.open(path) as actual:self.assertEqual(actual.convert('RGB').tobytes(),mosaic.tobytes())
                    expected.paste(mosaic,((slot%2)*128,(slot//2)*48))
                finally:mosaic.close()
            with Image.open(root/'image/composed/page_000001.png') as actual:
                self.assertEqual(actual.size,expected.size)
                self.assertEqual(actual.convert('RGBA').tobytes(),expected.tobytes())
        finally:expected.close()


if __name__=='__main__':unittest.main()
