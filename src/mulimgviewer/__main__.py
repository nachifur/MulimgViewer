r"""This module can be called by
`python -m <https://docs.python.org/3/library/__main__.html>`_.
"""
import sys
from pathlib import Path

import wx
import wx.lib.inspection
from PIL import ImageFile,Image

from .src.main import MulimgViewer
from .src.path_select import PathSelectFrame

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

class GuiManager():
    def __init__(self, UpdateUI, get_type):
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.frameDict = {}

    def GetFrame(self, type):
        frame = self.frameDict.get(type)

        if frame is None:
            frame = self.CreateFrame(type)
            self.frameDict[type] = frame

        return frame

    def CreateFrame(self, type):
        global file_name
        if file_name:
            input_path = Path(file_name).parent
        else:
            input_path = None

        if type == 0:
            return MulimgViewer(None, self.UpdateUI, self.get_type, default_path=input_path)
        elif type == 1:
            return PathSelectFrame(None, self.UpdateUI, self.get_type)


class MainAPP(wx.App):

    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI, self.get_type)
        self.frame = []
        self.frame.append(self.manager.GetFrame(0))
        self.frame.append(self.manager.GetFrame(1))
        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        self.type = 0  # init show MulimgViewer
        return True

    def UpdateUI(self, type, input_path=None, parallel_to_sequential=False):
        # type=1: PathSelectFrame
        # type=0: MulimgViewer
        # type=-1: Close
        self.type = type

        if input_path != None:
            if len(input_path) != 0:
                # refresh one_dir_mul_dir_manual path
                self.frame[0].ImgManager.init(
                    input_path, 1, parallel_to_sequential)
                self.frame[1].refresh_txt(input_path)

                self.frame[0].show_img_init()
                self.frame[0].ImgManager.set_action_count(0)
                self.frame[0].show_img()

        if type == -1:
            # close window
            self.frame[0].close(None)
            self.frame[1].close(None)
        elif type == 0:
            # hidden PathSelectFrame, show MulimgViewer
            self.frame[1].Show(False)
            self.frame[type].Show(True)
        elif type == 1:
            # show PathSelectFrame
            self.frame[type].Show(True)

        return True

    def get_type(self):
        return self.type


def main():
    global file_name
    if len(sys.argv)>1:
        file_name = sys.argv[1]
    else:
        file_name = None
    app = MainAPP()
    # debug
    # wx.lib.inspection.InspectionTool().Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
