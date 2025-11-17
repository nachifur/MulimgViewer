from pathlib import Path
import inspect

DEFAULT_ALGORITHMS = [
    "Image Enhancement",
    "Image Darkening",
    "Gaussian Blur",
    "Histogram Equalization"
]

def get_available_algorithms():
    algorithms = []
    custom_func_dir = Path(__file__).parent
    for item in custom_func_dir.iterdir():
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
    algorithm_path = Path(__file__).parent / algorithm_name / "main.py"
    if not algorithm_path.exists():
        return load_default_functions()
    try:
        namespace = {}
        with open(algorithm_path, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(code, namespace)
        return namespace
    except:
        return load_default_functions()

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
    functions = load_algorithm_functions(algorithm_type)
    available_algorithms = get_available_algorithms()
    algorithm_name = available_algorithms[algorithm_type] if algorithm_type < len(available_algorithms) else "Unknown"
    main_func = functions['main']
    sig = inspect.signature(main_func)
    params = list(sig.parameters.keys())
    if len(params) >= 4 or 'algorithm_name' in params:
        return main_func(img_list, save_path, name_list, algorithm_name)
    else:
        return main_func(img_list, save_path, name_list)
