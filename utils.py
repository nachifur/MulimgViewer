import sys
from pathlib import Path
import numpy as np

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return str(Path(sys._MEIPASS)/relative_path)
    return str(Path(relative_path).absolute())

def solve_factor(num):
    # solve factors for a number
    list_factor = []
    i = 1
    if num > 2:
        while i <= num:
            i += 1
            if num % i == 0:
                list_factor.append(i)
            else:
                pass
    else:
        pass

    list_factor = list(set(list_factor))
    list_factor = np.sort(list_factor)
    return list_factor

def change_order(list_):
    temp = list_[1]
    list_[0] = list_[1]
    list_[1] = temp
    return list_