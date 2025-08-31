import copy
import os
import sys
from pathlib import Path

import numpy as np
import wx

ROOT = os.path.dirname(os.path.dirname(__file__))


class MyTestEvent(wx.PyCommandEvent):

    def __init__(self, evtType, id=0):
        wx.PyCommandEvent.__init__(self, evtType, id)
        self.eventArgs = ""

    def GetEventArgs(self):
        return self.eventArgs

    def SetEventArgs(self, args):
        self.eventArgs = args


def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return str(Path(sys._MEIPASS)/'src'/'mulimgviewer'/relative_path)
    return str(Path(os.path.join(ROOT, relative_path)).absolute())


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
    if isinstance(list_[1], list):
        temp = copy.deepcopy(list_[0])
    else:
        temp = list_[0]
    list_[0] = list_[1]
    list_[1] = temp
    return list_


def rgb2hex(rgbcolor):
    # https://blog.csdn.net/Forter_J/article/details/89145794
    rgb = rgbcolor.split(',')
    strs = '#'
    for i in rgb:
        num = int(i)
        strs += str(hex(num))[-2:].replace('x', '0').upper()
    return strs
