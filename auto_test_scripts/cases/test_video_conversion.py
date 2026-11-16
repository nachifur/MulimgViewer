"""Native-plane conversion lifetime, RGB compatibility and bounded cache indexes."""
import gc
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/mulimgviewer/src'))
from video_decoder import DecoderSession,av
from video_memory import PixelCache,LazyVideoImage


@unittest.skipUnless(av,'PyAV required')
class ConversionTests(unittest.TestCase):
    def frame(self,width=98,height=66):
        data=np.arange(width*height*3,dtype=np.uint8).reshape(height,width,3)
        return av.VideoFrame.from_ndarray(data,format='rgb24')

    def test_pixels_jpeg_and_resize_match_for_supported_color_formats_and_strides(self):
        for width in (97,98,320):
            for fmt in ('rgb24','bgr24','yuv420p','yuv420p10le','yuv444p','gray'):
                with self.subTest(width=width,format=fmt):
                    frame=self.frame(width).reformat(format=fmt)
                    reference=frame.to_image()
                    image=DecoderSession._buffered_image(frame)
                    self.assertEqual(image.mode,'RGB')
                    self.assertFalse(image.readonly)
                    self.assertEqual(image.convert('RGB').tobytes(),reference.tobytes())
                    a,b=io.BytesIO(),io.BytesIO()
                    reference.save(a,format='JPEG',quality=90)
                    image.save(b,format='JPEG',quality=90)
                    self.assertEqual(a.getvalue(),b.getvalue())
                    self.assertEqual(image.resize((31,17),Image.BICUBIC).convert('RGB').tobytes(),
                                     reference.resize((31,17),Image.BICUBIC).tobytes())

    def test_pixels_remain_valid_after_other_frames_and_source_variables_are_gone(self):
        frame=self.frame()
        expected=frame.to_image().tobytes()
        image=DecoderSession._buffered_image(frame)
        del frame
        for _ in range(40):DecoderSession._buffered_image(self.frame(100,70))
        gc.collect()
        self.assertEqual(image.convert('RGB').tobytes(),expected)
        self.assertFalse(hasattr(image,'_video_owner'))

    def test_native_plane_path_does_not_silently_use_old_conversion(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        frame=self.frame(97)
        proxy=SimpleNamespace(reformat=frame.reformat,
            to_image=Mock(side_effect=AssertionError('unexpected fallback')))
        image=DecoderSession._buffered_image(proxy)
        self.assertEqual(image.mode,'RGB')
        self.assertEqual(image.tobytes(),frame.to_image().tobytes())
        proxy.to_image.assert_not_called()

    def test_image_does_not_alias_mutable_decoder_plane(self):
        frame=self.frame()
        image=DecoderSession._buffered_image(frame)
        before=image.tobytes()
        memoryview(frame.planes[0])[:3]=bytes((10,20,30))
        self.assertEqual(image.tobytes(),before)

    def test_plane_buffer_unavailable_falls_back_to_original_rgb(self):
        frame=self.frame()
        expected=frame.to_image().tobytes()
        original=Image.Image.frombytes
        def unsupported_buffer(image,data,*args,**kwargs):
            if isinstance(data,av.video.plane.VideoPlane):
                raise TypeError('unsupported plane buffer')
            return original(image,data,*args,**kwargs)
        with patch('video_decoder.Image.Image.frombytes',new=unsupported_buffer):
            image=DecoderSession._buffered_image(frame)
        self.assertEqual(image.mode,'RGB')
        self.assertEqual(image.tobytes(),expected)

    def test_allocation_failure_does_not_attempt_another_large_conversion(self):
        with patch('video_decoder.Image.Image.frombytes',side_effect=MemoryError):
            with self.assertRaises(MemoryError):DecoderSession._buffered_image(self.frame())

    def test_lazy_crop_resize_and_explicit_conversion_keep_public_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.jpeg'
            frame=self.frame();expected=frame.to_image()
            image=DecoderSession._buffered_image(frame)
            image.save(str(path),format='JPEG',quality=90)
            cache=PixelCache(1024**2);cache.put(str(path),image)
            source=LazyVideoImage(path,cache.get)
            tile=source.resize((20,16),Image.BICUBIC)
            self.assertEqual(tile.mode,'RGB')
            self.assertEqual(tile.tobytes(),expected.resize((20,16),Image.BICUBIC).tobytes())
            crop=source.crop((3,4,31,20))
            self.assertEqual(crop.mode,'RGB')
            self.assertEqual(crop.tobytes(),expected.crop((3,4,31,20)).tobytes())
            self.assertEqual(source.convert('RGBA').mode,'RGBA')
            cache.prune(set())
            self.assertEqual(image.convert('RGB').tobytes(),expected.tobytes())


class CacheIndexTests(unittest.TestCase):
    def consistent(self,cache):
        self.assertEqual(cache.bytes,sum(v[1] for v in cache.entries.values()))
        self.assertEqual(cache.priority_bytes,sum(v[1] for v in cache.entries.values() if v[3]))
        self.assertEqual(set(cache._raw)|set(cache._priority),set(cache.entries))
        self.assertFalse(set(cache._raw)&set(cache._priority))
        self.assertLessEqual(cache.bytes,cache.limit)

    def test_priority_replacements_lru_shrink_and_owner_pruning(self):
        cache=PixelCache(1200);image=Image.new('RGB',(10,10))
        cache.put('raw_a',image);cache.put('protected',image,owner='owner',priority=True)
        cache.put('raw_b',image);cache.get('raw_a');cache.put('raw_c',image)
        self.assertIsNone(cache.get('raw_b'))
        self.assertIs(cache.get('protected'),image)
        cache.put('raw_a',image,priority=True);self.consistent(cache)
        cache.put('raw_a',image,priority=False);self.consistent(cache)
        cache.prune({'owner'});self.consistent(cache)
        cache.configure(0);self.consistent(cache)
        cache.configure(800);cache.put('x',image,priority=True);cache.clear();self.consistent(cache)

    def test_mapped_stride_storage_counts_towards_byte_cap(self):
        image=Image.new('RGBX',(3,2));image._video_buffer_bytes=512
        cache=PixelCache(500)
        self.assertFalse(cache.put('padded',image))
        cache.configure(512);self.assertTrue(cache.put('padded',image))
        self.assertEqual(cache.bytes,512)

    def test_concurrent_put_get_prune_preserves_indexes_and_limits(self):
        cache=PixelCache(8000);image=Image.new('RGB',(10,10))
        def work(worker):
            for index in range(100):
                key=str((index+worker)%30)
                cache.put(key,image,priority=index%3==0)
                cache.get(str(index%30))
                if index%17==0:cache.prune({str(i) for i in range(25)})
        with ThreadPoolExecutor(8) as pool:list(pool.map(work,range(8)))
        self.consistent(cache)


if __name__=='__main__':unittest.main()
