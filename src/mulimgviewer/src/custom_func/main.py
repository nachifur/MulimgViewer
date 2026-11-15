from pathlib import Path
import inspect
from .runtime import state, compiled_source, execution_lock
from .contract import specification
import threading
import weakref
import gc
from contextlib import contextmanager

_device_locks = {}
_resident_devices = {}


@contextmanager
def device_context(device):
    if device == 'cpu':
        yield
        return
    with execution_lock:
        lock=_device_locks.setdefault(device,threading.RLock())
    with lock:yield

DEFAULT_ALGORITHMS = [
    "Image Enhancement",
    "Image Darkening",
    "Gaussian Blur",
    "Histogram Equalization",
    "Original"
]

def get_available_algorithms():
    registry = getattr(state, 'registry', None)
    if registry is not None:
        return [entry[0] for entry in registry]
    algorithms = []
    custom_func_dir = Path(__file__).parent
    for item in sorted(custom_func_dir.iterdir(), key=lambda path: path.name.casefold()):
        if item.is_dir() and item.name != "__pycache__":
            main_file = item / "main.py"
            if main_file.exists():
                algorithms.append(item.name)
    ordered_algorithms = []
    for default_alg in DEFAULT_ALGORITHMS:
        if default_alg in algorithms:
            ordered_algorithms.append(default_alg)
    for alg in algorithms:
        if alg not in DEFAULT_ALGORITHMS:
            ordered_algorithms.append(alg)
    return ordered_algorithms

def load_algorithm_functions(algorithm_type):
    available_algorithms = get_available_algorithms()
    if not available_algorithms:
        return load_default_functions()
    if algorithm_type < 0 or algorithm_type >= len(available_algorithms):
        algorithm_type = 0
    algorithm_name = available_algorithms[algorithm_type]
    session = getattr(state, 'session', None)
    if session is not None and algorithm_type in session.namespaces:
        return session.namespaces[algorithm_type]
    algorithm_path = Path(__file__).parent / algorithm_name / "main.py"
    if getattr(state, 'registry', None) is None and not algorithm_path.exists():
        return load_default_functions()
    try:
        registry = getattr(state, 'registry', None)
        if registry is None:
            code = algorithm_path.read_text(encoding='utf-8-sig')
        else:
            _, filename, code = registry[algorithm_type][:3]
            algorithm_path = Path(filename)
        namespace = {'__file__': str(algorithm_path), '__name__': '__custom_algorithm__'}
        exec(compiled_source(str(algorithm_path), code), namespace)
        if session is not None:
            session.namespaces[algorithm_type] = namespace
        return namespace
    except Exception as error:
        raise RuntimeError(f"Algorithm '{algorithm_name}' failed to load: {error}") from error

def load_default_functions():
    algorithm_path = Path(__file__).parent / "Image Enhancement" / "main.py"
    namespace = {}
    try:
        with open(algorithm_path, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(code, namespace)
        return namespace
    except:
        return {
            'custom_process_img': lambda img: img,
            'main': lambda img_list, save_path, name_list=None: img_list
        }

def custom_process_img(img, algorithm_type=0):
    functions = load_algorithm_functions(algorithm_type)
    if 'process_image' in functions:
        return main([img], '', algorithm_type=algorithm_type)[0]
    return functions['custom_process_img'](img)

def algorithm_specification(index):
    registry=getattr(state,'registry',None)
    if registry:
        return specification(registry,index)
    from .runtime import capture_algorithms
    names=get_available_algorithms()
    return specification(capture_algorithms([names[index]]),0)


@contextmanager
def algorithm_context(algorithm_type):
    registry=getattr(state,'registry',None)
    session=getattr(state,'session',None)
    spec=algorithm_specification(algorithm_type)
    token=(id(session),algorithm_type,spec['device'])
    previous=getattr(state,'algorithm_admission',None)
    if previous==token:
        yield
        return
    with execution_lock:
        if spec['device'] == 'cpu' and session is not None:
            lock = session.locks.setdefault(algorithm_type,threading.RLock() if spec['max_concurrency']==1
                                            else threading.BoundedSemaphore(spec['max_concurrency']))
        else:
            lock = _device_locks.setdefault(spec['device'],threading.RLock())
    with lock:
        state.algorithm_admission=token
        try:yield
        finally:state.algorithm_admission=previous


def main(img_list, save_path, name_list=None, algorithm_type=0):
    registry = getattr(state,'registry',None)
    session = getattr(state,'session',None)
    available = get_available_algorithms()
    if not available:raise RuntimeError('No custom algorithms are installed')
    algorithm_type = algorithm_type if 0 <= algorithm_type < len(available) else 0
    spec = algorithm_specification(algorithm_type)
    with algorithm_context(algorithm_type):
        # Non-CPU devices retain at most one algorithm model by default. Device
        # locks span initialization, processing and eviction, not just inference.
        if spec['device'] != 'cpu' and session is not None:
            previous = _resident_devices.get(spec['device'])
            if previous is not None:
                previous_session, previous_index = previous[0](), previous[1]
                if previous_session is None:gc.collect()
                if previous_session is not None and (previous_session is not session or previous_index != algorithm_type):
                    namespace = previous_session.namespaces.pop(previous_index,None)
                    previous_session.sequence.pop(previous_index,None)
                    if namespace is not None:
                        release = namespace.get('release_resources')
                        if callable(release):release()
                        namespace.clear()
                        gc.collect()
            _resident_devices[spec['device']] = (weakref.ref(session),algorithm_type)
        with execution_lock:
            functions = load_algorithm_functions(algorithm_type)
        if spec['device'] == 'cpu' and spec['max_concurrency'] > 1 and not functions.get('THREAD_SAFE',False):
            raise ValueError('max_concurrency > 1 requires THREAD_SAFE = True')
        context=getattr(state,'sequence_context',None)
        if spec.get('ordered') and session is not None and context is not None:
            owner,epoch,batch=context
            reset=functions.get('reset')
            if not callable(reset):raise ValueError('Ordered plugins must provide reset(context)')
            if session.sequence.get(algorithm_type)!=(owner,epoch,batch-1):reset(dict(owner=owner,batch=batch))
        result=_invoke_main(functions, img_list, save_path, name_list, algorithm_type, spec)
        if spec.get('ordered') and session is not None and context is not None:
            session.sequence[algorithm_type]=context
        return result


def _invoke_main(functions, img_list, save_path, name_list=None, algorithm_type=0, spec=None):
    if spec and spec.get('api_version') == 2:
        return _invoke_kernel(functions, img_list, spec)
    available_algorithms = get_available_algorithms()
    if not available_algorithms:
        raise RuntimeError('No custom algorithms are installed')
    algorithm_type = max(0, min(algorithm_type, len(available_algorithms)-1))
    algorithm_name = available_algorithms[algorithm_type] if algorithm_type < len(available_algorithms) else "Unknown"
    main_func = functions['main']
    sig = inspect.signature(main_func)
    params = list(sig.parameters.keys())
    if getattr(state, 'preview', False):
        save_path = ''
    if 'algorithm_name' in params:
        return main_func(img_list, save_path, name_list, algorithm_name=algorithm_name)
    if len(params) >= 4:
        return main_func(img_list, save_path, name_list, algorithm_name)
    else:
        return main_func(img_list, save_path, name_list)


def _invoke_kernel(functions, images, spec):
    """Model initialization is shared by all calls in one algorithm session."""
    from PIL import Image
    entry = 'process_image' if spec['processing_mode'] == 'image' else 'process_batch'
    kernel = functions.get(entry)
    if not callable(kernel):
        raise ValueError(f'API v2 requires {entry}')
    with execution_lock:
        initialization = functions.setdefault('_kernel_init_lock', threading.RLock())
    with initialization:
        if '_kernel_context' not in functions:
            setup = functions.get('setup')
            context = setup() if callable(setup) else None
            functions['_kernel_context'] = context
            teardown = functions.get('teardown')
            legacy_release = functions.get('release_resources')
            if callable(teardown):
                def release_resources():
                    # Called under the device lock before model eviction.
                    if '_kernel_context' in functions:
                        teardown(functions.pop('_kernel_context'))
                    if callable(legacy_release):
                        legacy_release()
                functions['release_resources'] = release_resources
        context = functions['_kernel_context']
    # Direct export/fallback calls stay serial. The disk pipeline fans out image
    # kernels with one shared CPU/RAM permit per image, without nested permits.
    outputs = []
    try:
        if spec['processing_mode'] == 'image':
            for image in images:
                outputs.append(kernel(image, context=context))
        else:
            for image in kernel(images, context=context):
                outputs.append(image)
        if len(outputs) != len(images) or not all(isinstance(image, Image.Image) for image in outputs):
            raise ValueError('Custom kernel must return one Pillow image per input, in input order')
    except BaseException:
        for image in {id(image): image for image in outputs if isinstance(image, Image.Image)}.values():
            if not any(image is source for source in images):image.close()
        raise
    return outputs
