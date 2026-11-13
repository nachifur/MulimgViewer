"""Immutable algorithm sources and thread-local preview execution settings."""
import threading
from functools import wraps, lru_cache
from pathlib import Path

state = threading.local()
execution_lock = threading.RLock()


class AlgorithmSession:
    """One render recipe shares lazily initialized user modules across workers."""
    def __init__(self, registry):
        self.registry = registry
        self.namespaces = {}


def check_processing_budget(manager, flist):
    budget = getattr(manager, '_custom_memory_budget', None)
    params = manager.layout_params
    if budget is None or len(params) <= 38 or not (params[32] or params[38]):
        return
    from PIL import Image
    paths, _ = manager._normalize_flist_input(flist if flist is not None else manager.get_flist())
    copies = 1
    if params[38]:
        rows, cols = map(int, params[39].split(','))
        if min(rows, cols) < 1:
            raise ValueError('Show all function layout requires positive rows and columns')
        copies = min(rows*cols, 1+len(getattr(manager, '_custom_algorithm_registry', ()) or ()))
    pixels = 0
    for path in paths or ():
        with Image.open(path) as image:
            pixels += image.width*image.height
        if pixels*(16+4*copies) > budget:
            raise MemoryError('Custom processing exceeds the memory budget; reduce the layout or source resolution')


def capture_algorithms(names):
    root = Path(__file__).parent
    return tuple((name, str(root/name/'main.py'),
                  (root/name/'main.py').read_text(encoding='utf-8-sig')) for name in names)


@lru_cache(maxsize=64)
def compiled_source(filename, source):
    return compile(source, filename, 'exec')


def render_context(function):
    @wraps(function)
    def wrapped(manager, img_mode, *args, **kwargs):
        previous = (getattr(state, 'registry', None), getattr(state, 'preview', False),
                    getattr(state, 'session', None))
        state.registry = getattr(manager, '_custom_algorithm_registry', None)
        state.session = getattr(manager, '_custom_algorithm_session', None)
        state.preview = img_mode == 0
        try:
            if state.preview:
                check_processing_budget(manager, kwargs.get('flist', args[1] if len(args)>1 else None))
            return function(manager, img_mode, *args, **kwargs)
        finally:
            state.registry, state.preview, state.session = previous
    return wrapped
