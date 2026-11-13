from pathlib import Path
import inspect
from .runtime import state, compiled_source, execution_lock

DEFAULT_ALGORITHMS = [
    "Image Enhancement",
    "Image Darkening",
    "Gaussian Blur",
    "Histogram Equalization"
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
            _, filename, code = registry[algorithm_type]
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
    return functions['custom_process_img'](img)

def main(img_list, save_path, name_list=None, algorithm_type=0):
    # User modules may own GPU models or mutable state. Initialization and
    # execution are serialized unless the module explicitly opts into threads.
    with execution_lock:
        available = get_available_algorithms()
        if not available:
            raise RuntimeError('No custom algorithms are installed')
        algorithm_type = algorithm_type if 0 <= algorithm_type < len(available) else 0
        functions = load_algorithm_functions(algorithm_type)
        if not functions.get('THREAD_SAFE', False):
            return _invoke_main(functions, img_list, save_path, name_list, algorithm_type)
    return _invoke_main(functions, img_list, save_path, name_list, algorithm_type)


def _invoke_main(functions, img_list, save_path, name_list=None, algorithm_type=0):
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
