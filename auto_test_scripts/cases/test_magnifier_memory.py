"""Pixel equivalence and bounded scratch memory for large magnifier canvases."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from concurrent.futures import CancelledError, ThreadPoolExecutor
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
import numpy as np
import wx
from PIL import Image
from mulimgviewer.src.utils_img import ImgUtils
from mulimgviewer.src.cache_layout import save_cache_image
from mulimgviewer.src.canvas import mosaic_working_bytes
from mulimgviewer.src.canvas import PixelCache, rgba_display
from mulimgviewer.src.canvas import new_canvas, DiskCanvas, rgba_copy, RenderLane, decode_jpeg_canvas
from mulimgviewer.src.custom_pipeline import WorkBudget


class MagnifierMemoryTests(unittest.TestCase):
    def test_large_local_canvas_requires_matching_render_dimensions(self):
        from mulimgviewer.src.cache_layout import open_rendered_canvas
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            for fmt in ('jpeg', 'png'):
                path = Path(directory)/('page_000001.'+fmt)
                with Image.new('RGB', (32, 24), 'red') as tile:
                    tile.save(path)
                with patch.object(Image, 'MAX_IMAGE_PIXELS', 100):
                    with self.assertRaises(Image.DecompressionBombError):
                        Image.open(path)
                    with open_rendered_canvas(path, (32, 24)) as decoded:
                        decoded.load()
                        self.assertEqual(decoded.size, (32, 24))
                    with self.assertRaises(ValueError):
                        open_rendered_canvas(path, (32, 23))
                    self.assertEqual(Image.MAX_IMAGE_PIXELS, 100)

    def test_in_place_rectangles_match_legacy_pixels_without_canvas_arrays(self):
        image=Image.new('RGBA',(64,48),(4,5,6,100))
        expected=np.array(image)
        origins=[(0,0),(30,18)]
        boxes=[[2,3,24,19],[4,6,20,22]]
        colors=[wx.Colour(200,30,40,85),wx.Colour(50,180,70,165)]
        for box,color in zip(boxes,colors):
            for dx,dy in origins:
                x0,y0,x1,y1=box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy
                rgba=(color.red,color.green,color.blue,color.alpha)
                expected[y0:y1,x0:x0+2]=rgba
                expected[y0:y0+2,x0:x1]=rgba
                expected[y0:y1,x1-2:x1]=rgba
                expected[y1-2:y1,x0:x1]=rgba
        with patch('numpy.array',side_effect=AssertionError('Full canvas array')), \
                patch.object(image,'copy',side_effect=AssertionError('Full canvas copy')):
            result=ImgUtils().draw_rectangle(image,origins,boxes,colors,in_place=True)
        self.assertIs(result,image)
        self.assertEqual(result.tobytes(),expected.tobytes())
        image.close()

    def test_default_rectangle_call_preserves_input_and_single_box_behavior(self):
        with Image.new('RGBA',(32,20),'blue') as image:
            original=image.tobytes()
            result=ImgUtils().draw_rectangle(image,[(0,0),(16,0)],[[2,2,10,10]],
                [wx.Colour(255,0,0,90)],single_box=True)
            try:
                self.assertEqual(image.tobytes(),original)
                self.assertEqual(result.getpixel((2,2)),(255,0,0,90))
                self.assertEqual(result.getpixel((18,2)),(0,0,255,255))
            finally:result.close()

    def test_jpeg_strip_flattening_matches_full_alpha_matting(self):
        for mode in ('RGBA','LA','P'):
            with self.subTest(mode=mode):
                source=Image.new('RGBA',(96,48),(23,81,179,107))
                if mode=='LA':
                    converted=source.convert('LA');source.close();source=converted
                elif mode=='P':
                    source.close();source=Image.new('P',(96,48),1)
                    source.putpalette([0,0,0,23,81,179]+[0]*762)
                    source.info['transparency']=1
                with source:
                    before=source.tobytes()
                    with source.convert('RGBA') as rgba, Image.new('RGB',source.size,'white') as matte:
                        with rgba.getchannel('A') as alpha:matte.paste(rgba,mask=alpha)
                        expected=io.BytesIO();matte.save(expected,format='JPEG',quality=90,subsampling=0)
                    actual=io.BytesIO();save_cache_image(source,actual,'jpeg',jpeg_quality=90)
                    self.assertEqual(actual.getvalue(),expected.getvalue())
                    self.assertEqual(source.tobytes(),before)

    def test_jpeg_scratch_strips_are_bounded_and_no_full_rgba_copy_is_made(self):
        with Image.new('RGBA',(1024,2100),(30,60,90,125)) as source:
            boxes=[];crop=source.crop
            def observe(box):boxes.append(box);return crop(box)
            with patch.object(source,'crop',side_effect=observe), \
                    patch.object(source,'convert',side_effect=AssertionError('Full RGBA copy')):
                save_cache_image(source,io.BytesIO(),'jpeg')
            self.assertGreater(len(boxes),1)
            self.assertTrue(all((x1-x0)*(y1-y0)*4<=4*1024**2 for x0,y0,x1,y1 in boxes))
            self.assertEqual(sum(y1-y0 for _,y0,_,y1 in boxes),source.height)

    def test_reservation_covers_rgba_rgb_and_tile_scratch_without_four_canvases(self):
        pixels=23090*17400;tile=3840*2160
        with patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=1024**3):
            charge=mosaic_working_bytes((23090,17400),tile)
        self.assertGreaterEqual(charge,tile*20)
        self.assertLess(charge,pixels*16)
        self.assertLess(charge,256*1024**2)
        with patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=64*1024**3):
            self.assertGreater(mosaic_working_bytes((23090,17400),tile),pixels*8)

    def test_writable_mapped_canvas_does_not_copy_on_paste_and_closes_its_file(self):
        with patch('mulimgviewer.src.canvas.LARGE_CANVAS_BYTES',0), \
                patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=0):
            image=new_canvas('RGBA',(16,12),(1,2,3,4))
            self.assertIsInstance(image,DiskCanvas)
            mapping,stream=image._disk_backing
            self.assertEqual(mapping[:4],bytes((1,2,3,4)))
            image.paste((20,30,40,50),(0,0,1,1))
            self.assertEqual(mapping[:4],bytes((20,30,40,50)))
            image.close()
            self.assertTrue(mapping.closed)
            self.assertTrue(stream.closed)

    def test_mapped_display_and_rgbx_encoder_match_normal_pixels(self):
        with Image.new('RGBA',(96,48),(23,81,179,107)) as source:
            expected=io.BytesIO();save_cache_image(source,expected,'jpeg')
            with patch('mulimgviewer.src.canvas.LARGE_CANVAS_BYTES',0), \
                    patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=0):
                display=rgba_copy(source)
                try:
                    self.assertIsInstance(display,DiskCanvas)
                    self.assertEqual(display.tobytes(),source.tobytes())
                    actual=io.BytesIO();save_cache_image(display,actual,'jpeg')
                    self.assertEqual(actual.getvalue(),expected.getvalue())
                finally:display.close()

    def test_only_one_mapped_handoff_is_cached_and_gui_keeps_its_own_view(self):
        with patch('mulimgviewer.src.canvas.LARGE_CANVAS_BYTES',0), \
                patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=0):
            first=new_canvas('RGBA',(16,12),'red')
            second=new_canvas('RGBA',(16,12),'blue')
            try:
                cache=PixelCache(16384)
                self.assertTrue(cache.put('first',first,priority=True))
                self.assertTrue(cache.put('alias',first,priority=True))
                self.assertIs(rgba_display(cache.get('first'))[0],first)
                self.assertTrue(cache.put('second',second,priority=True))
                self.assertIsNone(cache.get('first'));self.assertIsNone(cache.get('alias'))
                self.assertEqual(first.getpixel((0,0)),(255,0,0,255))
                self.assertEqual(len(cache._mapped_keys),1)
                cache.clear()
                self.assertEqual(cache.bytes,0)
                self.assertFalse(cache._mapped_keys)
                self.assertEqual(second.getpixel((0,0)),(0,0,255,255))
            finally:first.close();second.close()

    def test_logical_lane_reservation_still_validates_resident_scratch_ram(self):
        budget=WorkBudget();budget.configure(4,64*1024**2)
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=16*1024**2):
            with budget.acquire(64*1024**2,resident_size=8*1024**2):
                self.assertEqual(budget.bytes,64*1024**2)
        with patch('mulimgviewer.src.custom_pipeline.available_memory_bytes',return_value=4*1024**2):
            with self.assertRaises(MemoryError):
                with budget.acquire(64*1024**2,resident_size=8*1024**2):pass

    def test_giant_cached_decode_is_checked_before_loading_pixels(self):
        source=SimpleNamespace(size=(50000,50000),width=50000,height=50000,fp=object())
        with patch('mulimgviewer.src.canvas.available_memory_bytes',return_value=512*1024**2):
            with self.assertRaisesRegex(MemoryError,'decode'):
                rgba_display(source)

    def test_cached_jpeg_decodes_directly_into_mapped_pixels(self):
        for progressive in (False,True):
            data=io.BytesIO()
            with Image.new('RGB',(96,48),(23,81,179)) as image:
                image.save(data,format='JPEG',progressive=progressive)
            encoded=data.getvalue()
            with Image.open(io.BytesIO(encoded)) as reference:
                expected=reference.convert('RGBA').tobytes()
            with Image.open(io.BytesIO(encoded)) as source:
                with patch.object(source,'convert',side_effect=AssertionError('No full display copy')), \
                        patch.object(source,'copy',side_effect=AssertionError('No full display copy')):
                    result=decode_jpeg_canvas(source)
            try:
                self.assertIsInstance(result,DiskCanvas)
                with result.convert('RGBA') as rgba:self.assertEqual(rgba.tobytes(),expected)
            finally:result.close()  # No retained decoder/exported mmap pointers.

    def test_truncated_jpeg_releases_mapped_file_and_preserves_decode_error(self):
        encoded=io.BytesIO()
        with Image.new('RGB',(640,480),'red') as image:image.save(encoded,format='JPEG')
        allocated=[]
        def allocate(*args,**kwargs):
            result=new_canvas(*args,**kwargs);allocated.append(result);return result
        with Image.open(io.BytesIO(encoded.getvalue()[:-100])) as source:
            with patch('mulimgviewer.src.canvas.new_canvas',side_effect=allocate):
                with self.assertRaisesRegex(OSError,'truncated'):decode_jpeg_canvas(source)
            self.assertNotIn('load_prepare',source.__dict__)
        self.assertEqual(len(allocated),1)
        self.assertIsNone(allocated[0]._disk_backing)

    def test_disk_capacity_is_checked_before_mapping(self):
        with patch('mulimgviewer.src.canvas.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(OSError):new_canvas('RGBA',(16,12),mapped=True)

    def test_cancelled_cache_encoding_stops_without_modifying_pixels(self):
        with Image.new('RGBA',(1024,2100),(23,81,179,107)) as image:
            before=image.getpixel((0,0));calls=[]
            def checkpoint():
                calls.append(1)
                if len(calls)>=3:raise CancelledError()
            with self.assertRaises(CancelledError):
                save_cache_image(image,io.BytesIO(),'jpeg',checkpoint=checkpoint)
            self.assertEqual(len(calls),3)
            self.assertEqual(image.getpixel((0,0)),before)

    def test_checkpoint_writer_preserves_jpeg_and_png_output(self):
        with Image.new('RGBA',(96,48),(23,81,179,107)) as source:
            for extension in ('png','jpeg'):
                original=io.BytesIO();save_cache_image(source,original,extension)
                actual=io.BytesIO();calls=[]
                save_cache_image(source,actual,extension,checkpoint=lambda:calls.append(1))
                self.assertTrue(calls)
                self.assertEqual(original.getvalue(),actual.getvalue())

    def test_large_render_lane_prioritizes_visible_page_before_prefetch(self):
        lane=RenderLane();order=[]
        def job(name,priority):
            with lane.acquire(lambda:priority,lambda:False):order.append(name)
        with ThreadPoolExecutor(2) as pool:
            with lane.acquire(lambda:0,lambda:False):
                background=pool.submit(job,'prefetch',8)
                current=pool.submit(job,'current',0)
                with lane.condition:self.assertTrue(lane.condition.wait_for(lambda:len(lane.waiting)==2,2))
            current.result(timeout=2);background.result(timeout=2)
        self.assertEqual(order,['current','prefetch'])

    def test_cancelled_large_render_waiter_releases_its_queue_ticket(self):
        lane=RenderLane();cancel=threading.Event()
        def job():
            with lane.acquire(lambda:0,cancel.is_set):self.fail('Cancelled render entered')
        with ThreadPoolExecutor(1) as pool:
            with lane.acquire(lambda:0,lambda:False):
                future=pool.submit(job)
                with lane.condition:self.assertTrue(lane.condition.wait_for(lambda:len(lane.waiting)==1,2))
                cancel.set()
                with self.assertRaises(CancelledError):future.result(timeout=2)
        self.assertFalse(lane.waiting);self.assertFalse(lane.active)


if __name__=='__main__':unittest.main()
