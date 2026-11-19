"""Shared JPG quality for immutable rendering/export snapshots."""
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
