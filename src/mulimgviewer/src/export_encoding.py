"""Export-only compression. Preview/cache PNGs keep their fast encoder."""
from contextlib import contextmanager
from io import BytesIO
from reportlab.lib.utils import ImageReader
from .jpeg_policy import jpeg_quality


def png_level(owner):
    return max(0,min(9,int(getattr(owner,'png_compression_level',6))))


@contextmanager
def pdf_raster(image,owner):
    if getattr(owner,'pdf_compression',0)!=1:
        yield ImageReader(image)
        return
    from .cache_layout import save_cache_image
    with BytesIO() as stream:
        save_cache_image(image,stream,'jpeg',jpeg_quality=jpeg_quality(owner))
        stream.seek(0)
        reader=ImageReader(stream)
        try:yield reader
        finally:reader._image.close()


def capture_export_encoding(owner,manager):
    if hasattr(owner,'png_compression'):
        manager.png_compression_level=(1,6,9)[owner.png_compression.GetSelection()]
    if hasattr(owner,'pdf_compression'):
        manager.pdf_compression=owner.pdf_compression.GetSelection()
