"""Memory-backed and disk-backed pixels, bounded caches and tiled display."""
import errno
import mmap
import shutil
import tempfile
import threading
import traceback
import wx
from PIL import Image
from collections import OrderedDict
from concurrent.futures import CancelledError
from contextlib import contextmanager, nullcontext
from typing import NamedTuple

if __package__:
    from .playback_policy import available_memory_bytes
else:
    from playback_policy import available_memory_bytes


# Disk-backed canvases and render admission
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


# Pixel caching and lazy frame access
def mosaic_working_bytes(size, source_pixels=0, mapped=None):
    """RGBA canvas + RGB JPEG output, with bounded tile/encoder scratch space.

    Drawing is in place and alpha flattening uses strips. No full-canvas NumPy
    array, RGBA duplicate or alpha mask needs to coexist with these buffers.
    """
    if (disk_backed(size) if mapped is None else mapped):return scratch_bytes(source_pixels)
    return max(32*1024**2, int(size[0]*size[1]*8 + source_pixels*20 + 16*1024**2))


def tiled_display(size):
    """Choose bounded native tiles without changing resolution or RAM budgets."""
    width,height=size
    return width*height*4>32*1024**2 or max(size)>8192


def rgba_display(source):
    """Share immutable RGBA bytes with Pillow instead of retaining two canvases.

    wx still needs its native bitmap. The returned Pillow view owns its byte
    buffer after the input file closes; writes use Pillow's copy-on-write.
    """
    # Large frames use viewport tiles; retain only one Pillow canvas and skip
    # a full-size RGBA byte copy. The source file may close after this call.
    if isinstance(source,DiskCanvas):return source,None
    if tiled_display(source.size):
        if (getattr(source,'format',None)=='JPEG' and source.mode=='RGB'
                and getattr(source,'fp',None) is not None
                and source.width*source.height*4>256*1024**2):
            return decode_jpeg_canvas(source),None
        if source.width*source.height*4>256*1024**2 and getattr(source,'fp',None) is not None:
            available=available_memory_bytes()
            if available is not None and source.width*source.height*4+16*1024**2>available*.85:
                raise MemoryError('Not enough system memory to decode this cached display safely')
        if disk_backed(source.size):return rgba_copy(source),None
        return (source.copy() if source.mode=='RGBA' else source.convert('RGBA')),None
    rgba=source if source.mode=='RGBA' else source.convert('RGBA')
    try:
        size=rgba.size
        data=rgba.tobytes()
    finally:
        if rgba is not source:rgba.close()
    return Image.frombuffer('RGBA',size,data,'raw','RGBA',0,1),data


def source_resolution(sizes, requested, mode=0):
    """Match layout normalization without materializing source pixels."""
    widths,heights=map(sorted,zip(*sizes))
    def normalized(values):
        if mode==2:return max(values)
        if mode==1:return min(values)
        middle=values[1:-1] if len(values)>3 else values
        return sum(middle)/len(middle)
    width,height=normalized(widths),normalized(heights)
    x,y=requested
    if x==-1 and y==-1:return int(width),int(height)
    if x==-1:return int(width*y/height),int(y)
    if y==-1:return int(x),int(height*x/width)
    return int(x),int(y)


class CachedImageInfo(NamedTuple):
    size: tuple
    mode: str
    @property
    def width(self):return self.size[0]
    @property
    def height(self):return self.size[1]


class PixelCache:
    def __init__(self, limit=0):
        self.lock = threading.RLock()
        self.limit, self.bytes = max(0, int(limit)), 0
        self.entries = OrderedDict()
        self._raw = OrderedDict()
        self._priority = OrderedDict()
        self.priority_bytes = 0
        self._mapped_keys=set();self._mapped_id=None

    def configure(self, limit):
        with self.lock:
            self.limit = max(0, int(limit))
            self._trim()

    def _remove(self, key):
        entry = self.entries.pop(key)
        self.bytes -= entry[1]
        if entry[3]:
            self.priority_bytes -= entry[1]
            del self._priority[key]
        else:
            del self._raw[key]
        self._mapped_keys.discard(key)
        if not self._mapped_keys:self._mapped_id=None

    def _trim(self):
        # Two LRU indexes avoid scanning every protected preview for each raw
        # frame insertion. Both the victim lookup and byte accounting are O(1).
        while self.bytes > self.limit and self.entries:
            self._remove(next(iter(self._raw or self._priority)))

    def put(self, key, image, owner=None, priority=False):
        key = str(key)
        mapped=isinstance(image,DiskCanvas)
        weight = (4096 if mapped else 256+2*len(key)+2*len(str(owner or key)) if isinstance(image,CachedImageInfo) else
                  max(image.width * image.height * max(4,len(image.getbands())),int(getattr(image,'_video_buffer_bytes',0))))
        with self.lock:
            if weight > self.limit:
                return False
            if mapped and self._mapped_id!=id(image):
                # A handoff to the current display, not another raster cache:
                # retain at most one mapped canvas (and its path aliases).
                for previous in tuple(self._mapped_keys):self._remove(previous)
            old = self.entries.get(key)
            protected = self.priority_bytes - (old[1] if old and old[3] else 0)
            if not priority and weight + protected > self.limit:
                return False
            if old is not None:
                self._remove(key)
            self.entries[key] = image, weight, str(owner) if owner is not None else key, priority
            if mapped:
                self._mapped_keys.add(key);self._mapped_id=id(image)
            self.bytes += weight
            if priority:
                self.priority_bytes += weight
                self._priority[key] = None
            else:
                self._raw[key] = None
            self._trim()
            return True

    def put_header(self,path,size,mode,owner=None):
        return self.put(('header',str(path)),CachedImageInfo(tuple(size),mode),owner=owner or str(path),priority=True)

    def get(self, key):
        key = str(key)
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            self.entries.move_to_end(key)
            (self._priority if entry[3] else self._raw).move_to_end(key)
            return entry[0]  # Immutable by convention; consumers resize/copy.

    def prune(self, allowed):
        with self.lock:
            for key in list(self.entries):
                if self.entries[key][2] not in allowed:
                    self._remove(key)

    def clear(self):
        with self.lock:
            self.entries.clear()
            self._raw.clear()
            self._priority.clear()
            self.bytes = self.priority_bytes = 0
            self._mapped_keys.clear();self._mapped_id=None


class LazyVideoImage:
    """A closed-file image descriptor, materializing only the active tile.

    Keep originals on disk. A 100-video layout must not retain 100 decoded 4K
    images or deepcopy them before shrinking each tile to its display size.
    """
    mode = 'RGB'

    def __init__(self, path, provider=None):
        self.path, self.provider = str(path), provider
        cached = (provider(self.path) or provider(('header',self.path))) if provider else None
        if cached is not None:
            self.size = cached.size
            self.mode = cached.mode
        else:
            # Pillow canonicalizes filename arguments on Windows. Internal
            # cache reads need no repeated filesystem path resolution.
            with open(self.path,'rb') as stream, Image.open(stream) as source:
                self.size = source.size
                self.mode = source.mode
        self.width, self.height = self.size

    def __deepcopy__(self, memo):
        return self  # Descriptor and original pixels are immutable.

    def _apply(self, method, *args, **kwargs):
        cached = self.provider(self.path) if self.provider else None
        if cached is not None:
            return getattr(cached, method)(*args, **kwargs)
        with open(self.path,'rb') as stream, Image.open(stream) as source:
            # JPEG sources are already RGB. Conversion before resize would
            # create an unnecessary full-resolution duplicate of each frame.
            if source.mode not in ('RGB','RGBA'):
                source = source.convert('RGBA' if source.mode=='LA' or 'transparency' in source.info else 'RGB')
            return getattr(source, method)(*args, **kwargs)

    def resize(self, size, resample=Image.BICUBIC, **kwargs):
        key = ('preview', self.path, tuple(size), int(resample))
        preview = self.provider(key) if self.provider else None
        if preview is not None:
            return preview.copy()
        return self._apply('resize', size, resample, **kwargs)

    def render_tile(self, size, resample):
        """Read-only input to the renderer, which creates its own RGBA tile."""
        preview = self.provider(('preview', self.path, tuple(size), int(resample))) if self.provider else None
        if preview is not None:
            return preview
        return self if tuple(size) == self.size else self._apply('resize', size, resample)

    def crop(self, *args, **kwargs):
        return self._apply('crop', *args, **kwargs)

    def convert(self, *args, **kwargs):
        return self._apply('convert', *args, **kwargs)

    def copy(self):
        return self


# wx tiled display
class TiledImageCanvas(wx.Panel):
    tile_size=512
    cache_limit=8*1024**2

    def __init__(self,parent,viewport,image):
        super().__init__(parent)
        self.viewport=viewport
        self.tiles=OrderedDict()
        self.tile_bytes=0
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,self._paint)
        self.viewport_backed=max(image.size)>32767
        self.SetImage(image)
        if self.viewport_backed:
            viewport.Bind(wx.EVT_SCROLLWIN,self._viewport_changed)
            viewport.Bind(wx.EVT_SIZE,self._viewport_changed)
            viewport.Bind(wx.EVT_PAINT,self._viewport_painted)
            self.Bind(wx.EVT_WINDOW_DESTROY,self._destroy_viewport_bindings)

    def _destroy_viewport_bindings(self,event):
        if event.GetEventObject() is self and self.viewport and not self.viewport.IsBeingDeleted():
            self.viewport.Unbind(wx.EVT_SCROLLWIN,handler=self._viewport_changed)
            self.viewport.Unbind(wx.EVT_SIZE,handler=self._viewport_changed)
            self.viewport.Unbind(wx.EVT_PAINT,handler=self._viewport_painted)
        event.Skip()

    def _viewport_changed(self,event):
        # ScrolledWindow moves children before the scroll event completes.
        wx.CallAfter(self._sync_viewport)
        event.Skip()

    def _viewport_painted(self,event):
        # Programmatic Scroll() (keyboard/panning) does not emit EVT_SCROLLWIN.
        if self.GetPosition()!=(0,0):wx.CallAfter(self._sync_viewport)
        event.Skip()

    def _sync_viewport(self):
        if not self or not self.viewport:return
        self.SetPosition((0,0))
        self.SetSize(self.viewport.GetClientSize())
        self.Refresh(False)
        self.Update()

    def image_origin(self):
        return self.viewport.CalcUnscrolledPosition((0,0)) if self.viewport_backed else wx.Point(0,0)

    def bind_image_mouse(self,event_type,handler):
        def logical_event(event):
            if self.viewport_backed:
                event=wx.MouseEvent(event)
                event.SetPosition(event.GetPosition()+self.image_origin())
            handler(event)
        self.Bind(event_type,logical_event)

    def SetImage(self,image):
        # Pixels belong to the immutable displayed frame. No full wx bitmap
        # or second RGBA byte buffer is needed for this backend.
        self.image=image
        self.tiles.clear();self.tile_bytes=0
        self.Refresh(False)

    def _tile(self,x,y):
        key=x,y
        if key in self.tiles:
            self.tiles.move_to_end(key)
            return self.tiles[key][0]
        box=(x,y,min(x+self.tile_size,self.image.width),min(y+self.tile_size,self.image.height))
        with self.image.crop(box) as crop:
            converted=None
            try:
                rgba=crop
                if crop.mode!='RGBA':converted=rgba=crop.convert('RGBA')
                bitmap=wx.Bitmap.FromBufferRGBA(rgba.width,rgba.height,rgba.tobytes())
            finally:
                if converted is not None:converted.close()
        if not bitmap.IsOk():raise RuntimeError('Cannot allocate a display tile')
        amount=(box[2]-x)*(box[3]-y)*4
        while self.tiles and self.tile_bytes+amount>self.cache_limit:
            _,(_,old)=self.tiles.popitem(last=False);self.tile_bytes-=old
        self.tiles[key]=bitmap,amount;self.tile_bytes+=amount
        return bitmap

    def visible_rect(self):
        # A native child can be much larger than the viewport. Never allocate
        # an AutoBufferedPaintDC of the whole child, or visit invisible tiles.
        origin=(self.image_origin() if self.viewport_backed else
                self.ScreenToClient(self.viewport.ClientToScreen((0,0))))
        return wx.Rect(origin,self.viewport.GetClientSize()).Intersect(wx.Rect(0,0,*self.image.size))

    def _paint(self,event):
        origin=self.image_origin()
        update=self.GetUpdateRegion().GetBox()
        update.Offset(origin)
        visible=self.visible_rect().Intersect(update)
        # BeginPaint validates the native update region on Windows. Capture
        # it before constructing PaintDC, otherwise repaint can look empty.
        dc=wx.PaintDC(self)
        if visible.IsEmpty():return
        try:
            local=wx.Rect(visible)
            local.Offset(-origin.x,-origin.y)
            with wx.DCClipper(dc,local):
                dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
                dc.Clear()
                step=self.tile_size
                for y in range(visible.y//step*step,visible.y+visible.height,step):
                    for x in range(visible.x//step*step,visible.x+visible.width,step):
                        dc.DrawBitmap(self._tile(x,y),x-origin.x,y-origin.y,True)
        except (RuntimeError,MemoryError) as error:
            # Do not let an OS graphics allocation error escape an EVT_PAINT
            # callback or trigger a perpetual refresh/redecode loop.
            dc.DrawText(f'Display unavailable: {error}',visible.x-origin.x,visible.y-origin.y)
