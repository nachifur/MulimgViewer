"""Disk-backed Pillow pixels for canvases too large for resident display RAM."""
import mmap
import tempfile
import threading
import shutil
import errno
import traceback
from contextlib import nullcontext, contextmanager
from concurrent.futures import CancelledError
from PIL import Image
if __package__:
    from .thread_optimizer import available_memory_bytes
else:
    from thread_optimizer import available_memory_bytes

LARGE_CANVAS_BYTES = 256*1024**2
STRIP_BYTES = 4*1024**2
class RenderLane:
    def __init__(self):
        self.condition=threading.Condition()
        self.waiting=[];self.active=False;self.serial=0

    @contextmanager
    def acquire(self,priority,cancelled):
        with self.condition:
            self.serial+=1;ticket=(self.serial,priority)
            self.waiting.append(ticket)
            self.condition.notify_all()
            try:
                while True:
                    if cancelled():raise CancelledError()
                    if not self.active and ticket==min(self.waiting,key=lambda item:(item[1](),item[0])):
                        self.active=True
                        break
                    self.condition.wait(.05)
            finally:
                self.waiting.remove(ticket);self.condition.notify_all()
        try:yield
        finally:
            with self.condition:self.active=False;self.condition.notify_all()


_large_render = RenderLane()


class DiskCanvas(Image.Image):
    def flush(self, checkpoint=None):
        backing = getattr(self, '_disk_backing', None)
        if backing is not None:
            mapping=backing[0]
            if checkpoint is None:mapping.flush()
            else:
                # Aligned regions allow a superseded multi-GB render to stop
                # without waiting for a single whole-file flush.
                chunk=32*1024**2
                for offset in range(0,len(mapping),chunk):
                    checkpoint()
                    mapping.flush(offset,min(chunk,len(mapping)-offset))

    def close(self):
        super().close()
        backing = getattr(self, '_disk_backing', None)
        if backing is not None:
            self._disk_backing = None
            mapping, stream = backing
            try:
                mapping.close()
            finally:
                stream.close()

    def __del__(self):
        try:
            self.close()
        except (OSError, BufferError, AttributeError):
            pass


def disk_backed(size):
    pixels=int(size[0])*int(size[1])
    if pixels*4 <= LARGE_CANVAS_BYTES:return False
    available=available_memory_bytes()
    # Keep the RAM path when it comfortably fits. Mapping is a low-memory
    # fallback, not a mandatory disk round trip on high-memory workstations.
    return available is None or pixels*8+64*1024**2 > available*.8


def render_lane(size,priority=lambda:0,cancelled=lambda:False, *, mapped=None):
    # Large disk-backed jobs run serially; do not create a window's worth of
    # multi-gigabyte temporary maps or competing full-disk writes at once.
    # Memory-backed jobs with a measured working-set reservation are already
    # admitted by WorkBudget. Serialize mapped or unbudgeted large jobs.
    exclusive = mapped if mapped is not None else int(size[0])*int(size[1])*4 > LARGE_CANVAS_BYTES
    return _large_render.acquire(priority,cancelled) if exclusive else nullcontext()


def new_canvas(mode, size, color=None, *, directory=None, mapped=None):
    size = tuple(map(int, size))
    if not (disk_backed(size) if mapped is None else mapped):
        return Image.new(mode, size, color)
    if mode not in ('RGBA', 'RGBX'):
        raise ValueError('Disk-backed canvases require four-byte pixel modes')
    if shutil.disk_usage(directory or tempfile.gettempdir()).free < size[0]*size[1]*4+64*1024**2:
        raise OSError(errno.ENOSPC, 'Not enough temporary disk space for the full-resolution canvas')
    stream = tempfile.TemporaryFile(prefix='mulimg_canvas_', dir=directory)
    mapping = None
    try:
        stream.truncate(size[0]*size[1]*4)
        mapping = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_WRITE)
        image = Image.frombuffer(mode, size, mapping, 'raw', mode, 0, 1)
        image.__class__ = DiskCanvas
        image._disk_backing = (mapping, stream)
        image.readonly = 0  # Writable map: paste/draw must not copy the canvas.
        if color is not None:
            image.paste(color, (0, 0, *size))
        return image
    except BaseException:
        if mapping is not None:
            mapping.close()
        stream.close()
        raise


def decode_jpeg_canvas(source):
    """Decode an RGB JPEG straight into mapped pixels, without a RAM raster.

    Pillow's JPEG decoder accepts RGBX storage for RGB input. Supplying its
    destination before load avoids the usual full RGB decode + RGBA copy.
    Only our RGB JPEG caches use this path; other codecs keep their loaders.
    """
    result = new_canvas('RGBX', source.size, mapped=True)
    prepare = source.__dict__.get('load_prepare')
    try:
        source.im = result.im
        source.load_prepare = lambda: None  # Destination is already allocated.
        source.load()
        return result
    except BaseException as error:
        source.im = None
        # A failed Pillow load's traceback can retain PixelAccess exports.
        # Release those locals before closing the mapped destination.
        traceback.clear_frames(error.__traceback__)
        result.close()
        raise
    finally:
        # The file object must not retain another exported mmap reference.
        source.im = None
        if prepare is None:del source.load_prepare
        else:source.load_prepare = prepare


def rgba_copy(source):
    """Keep a large displayed frame on disk; native GUI tiles stay bounded."""
    result = new_canvas('RGBA', source.size, mapped=True)
    rows = max(1, STRIP_BYTES//max(1, source.width*4))
    try:
        for top in range(0, source.height, rows):
            with source.crop((0, top, source.width, min(source.height, top+rows))) as strip:
                result.paste(strip, (0, top))
        return result
    except BaseException:
        result.close()
        raise


def scratch_bytes(source_pixels=0):
    # One source's decode/resize/crops plus bounded alpha/encoder strips.
    return max(64*1024**2, int(source_pixels*20 + 32*1024**2))
