"""Small byte-bounded pixel accelerators; disk remains the backing cache."""
import threading
from collections import OrderedDict
from PIL import Image


class PixelCache:
    def __init__(self, limit=0):
        self.lock = threading.RLock()
        self.limit, self.bytes = max(0, int(limit)), 0
        self.entries = OrderedDict()

    def configure(self, limit):
        with self.lock:
            self.limit = max(0, int(limit))
            self._trim()

    def _trim(self):
        while self.bytes > self.limit and self.entries:
            key = next((k for k,v in self.entries.items() if not v[3]), next(iter(self.entries)))
            self.bytes -= self.entries.pop(key)[1]

    def put(self, key, image, owner=None, priority=False):
        # Pillow RGB storage can use four bytes/pixel internally. Account for
        # that instead of assuming len(getbands()) bytes for RGB images.
        key = str(key)
        weight = image.width * image.height * max(4, len(image.getbands()))
        with self.lock:
            if weight > self.limit:
                return False
            if not priority and weight + sum(v[1] for v in self.entries.values() if v[3]) > self.limit:
                return False
            old = self.entries.pop(key, None)
            if old:
                self.bytes -= old[1]
            self.entries[key] = image, weight, str(owner) if owner is not None else key, priority
            self.bytes += weight
            self._trim()
            return True

    def get(self, key):
        with self.lock:
            entry = self.entries.get(str(key))
            if entry is None:
                return None
            self.entries.move_to_end(str(key))
            return entry[0]  # Immutable by convention; consumers resize/copy.

    def prune(self, allowed):
        with self.lock:
            for key in list(self.entries):
                if self.entries[key][2] not in allowed:
                    self.bytes -= self.entries.pop(key)[1]

    def clear(self):
        self.prune(set())


class LazyVideoImage:
    """A closed-file image descriptor, materializing only the active tile.

    Keep originals on disk. A 100-video layout must not retain 100 decoded 4K
    images or deepcopy them before shrinking each tile to its display size.
    """
    mode = 'RGB'

    def __init__(self, path, provider=None):
        self.path, self.provider = str(path), provider
        cached = provider(self.path) if provider else None
        if cached is not None:
            self.size = cached.size
        else:
            with Image.open(self.path) as source:
                self.size = source.size
        self.width, self.height = self.size

    def __deepcopy__(self, memo):
        return self  # Descriptor and original pixels are immutable.

    def _apply(self, method, *args, **kwargs):
        cached = self.provider(self.path) if self.provider else None
        if cached is not None:
            return getattr(cached, method)(*args, **kwargs)
        with Image.open(self.path) as source:
            # JPEG sources are already RGB. Conversion before resize would
            # create an unnecessary full-resolution duplicate of each frame.
            if source.mode != 'RGB':
                source = source.convert('RGB')
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
