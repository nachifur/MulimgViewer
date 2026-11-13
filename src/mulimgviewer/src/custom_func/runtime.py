"""Immutable algorithm sources and thread-local preview execution settings."""
import threading
import json
from functools import wraps, lru_cache
from pathlib import Path

state = threading.local()
execution_lock = threading.RLock()


class AlgorithmSession:
    """One render recipe shares lazily initialized user modules across workers."""
    def __init__(self, registry):
        self.registry = registry
        self.namespaces = {}
        self.locks = {}
        self.sequence = {}


def check_processing_budget(manager, flist):
    # Disk-stage results are already admitted and processed. Composition has
    # its own shared permit and canvas check; do not charge full input copies again.
    if getattr(manager,'_custom_results',None) is not None:
        return
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
    result = []
    for name in names:
        folder = root/name
        manifest = folder/'plugin.json'
        spec = json.loads(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else {}
        dependencies = []
        for item in spec.get('cache_dependencies', []):
            path = folder/item
            info = path.stat()
            dependencies.append((str(path.resolve()),info.st_size,info.st_mtime_ns))
        # Helper-code edits invalidate results without reading large model files.
        helpers = [(str(p.relative_to(folder)),p.stat().st_size,p.stat().st_mtime_ns)
                   for p in sorted(folder.glob('*.py'))]
        spec['_dependencies'] = dependencies+helpers
        result.append((name,str(folder/'main.py'),(folder/'main.py').read_text(encoding='utf-8-sig'),
                       json.dumps(spec,sort_keys=True)))
    from .contract import specification
    from ..cache_layout import component
    names=set();originals=0
    for index,entry in enumerate(result):
        spec=specification(result,index)
        name=component(spec.get('cache_name',entry[0])).casefold()
        if name in names:raise ValueError('Algorithm cache names must be unique; change cache_name in plugin.json')
        names.add(name)
        if spec.get('role')=='original':
            originals+=1
            if not spec['identity']:raise ValueError('The original role must declare identity=true')
    if originals>1:raise ValueError('Only one algorithm can declare the original role')
    return tuple(result)


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
