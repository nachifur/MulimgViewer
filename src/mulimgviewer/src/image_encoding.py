"""Shared image format and compression policies for preview caches and export."""
from contextlib import contextmanager
from io import BytesIO


JPG = 0
PNG = 1
PDF = 2
ORDER = 'jpg,png,pdf'
LEGACY_TO_CURRENT = {0: PNG, 1: PDF, 2: JPG}


# Cache format selection
def cache_extension(config):
    return 'png' if getattr(config,'cache_save_format',0)==1 else 'jpeg'


def resolve_cache_format(selection,save_format=0,output_scale=(1,1)):
    """Keep legacy jpg=0/png=1; auto=2 resolves from captured output settings."""
    import math
    if selection!=2:return 1 if selection==1 else 0
    try:
        scales=tuple(float(value) for value in output_scale)
        return int(save_format in (1,2) and len(scales)==2
                   and all(math.isfinite(value) and value>=1 for value in scales))
    except (TypeError,ValueError):return 0


def manager_cache_format(manager,save_format=None):
    params=getattr(manager,'layout_params',())
    selection=params[41] if len(params)>41 else getattr(manager,'cache_save_format',0)
    output=(params[35] if len(params)>35 else 0) if save_format is None else save_format
    scale=params[5] if len(params)>5 else (1,1)
    return resolve_cache_format(selection,output,scale)


def lossless_export(manager,save_format=None):
    params=manager.layout_params
    return (manager_cache_format(manager,save_format)==1 and (params[35] if save_format is None else save_format) in (1,2)
        and all(float(scale)>=1 for scale in params[5]))


# JPEG quality for Pillow and FFmpeg
DEFAULT_QUALITY = 100


def jpeg_quality(owner):
    params=getattr(owner,'layout_params',())
    value=params[42] if len(params)>42 else getattr(owner,'save_quality',DEFAULT_QUALITY)
    try:return max(0,min(100,int(value)))
    except (TypeError,ValueError,OverflowError):return DEFAULT_QUALITY


def ffmpeg_jpeg_options(owner):
    # MJPEG uses a quantizer rather than Pillow's 0..100 quality scale.
    # Map monotonically; 1 is its best quality, 31 its lowest.
    return {'q:v':1+round(30*(100-jpeg_quality(owner))/100),'pix_fmt':'yuvj444p'}


def ffmpeg_jpeg_args(owner):
    return [part for key,value in ffmpeg_jpeg_options(owner).items() for part in ('-'+key,str(value))]


def cache_quality(owner):
    value=getattr(owner,'cache_jpeg_quality',None)
    if value is None:return jpeg_quality(owner)
    try:return max(0,min(100,int(value)))
    except (TypeError,ValueError,OverflowError):return jpeg_quality(owner)


# Export-only compression
def png_level(owner):
    return max(0,min(9,int(getattr(owner,'png_compression_level',6))))


@contextmanager
def pdf_raster(image,owner):
    from reportlab.lib.utils import ImageReader

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
