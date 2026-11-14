"""Small byte-bounded pixel accelerators; disk remains the backing cache."""
import threading
from collections import OrderedDict
from PIL import Image
from typing import NamedTuple


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

    def _trim(self):
        # Two LRU indexes avoid scanning every protected preview for each raw
        # frame insertion. Both the victim lookup and byte accounting are O(1).
        while self.bytes > self.limit and self.entries:
            self._remove(next(iter(self._raw or self._priority)))

    def put(self, key, image, owner=None, priority=False):
        key = str(key)
        weight = (256+2*len(key)+2*len(str(owner or key)) if isinstance(image,CachedImageInfo) else
                  max(image.width * image.height * max(4,len(image.getbands())),int(getattr(image,'_video_buffer_bytes',0))))
        with self.lock:
            if weight > self.limit:
                return False
            old = self.entries.get(key)
            protected = self.priority_bytes - (old[1] if old and old[3] else 0)
            if not priority and weight + protected > self.limit:
                return False
            if old is not None:
                self._remove(key)
            self.entries[key] = image, weight, str(owner) if owner is not None else key, priority
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

    def crop(self, *args, **kwargs):
        return self._apply('crop', *args, **kwargs)

    def convert(self, *args, **kwargs):
        return self._apply('convert', *args, **kwargs)

    def copy(self):
        return self
