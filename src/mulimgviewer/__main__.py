r"""This module can be called by
`python -m <https://docs.python.org/3/library/__main__.html>`_.
"""
import sys
from pathlib import Path

import wx
import wx.lib.inspection
from PIL import ImageFile, Image

from .src.main import MulimgViewer
from .src.path_select import PathSelectFrame

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


class GuiManager:
    def __init__(self, UpdateUI, get_type):
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.frameDict = {}

    def GetFrame(self, type_):
        f = self.frameDict.get(type_)
        if f is None:
            f = self.CreateFrame(type_)
            self.frameDict[type_] = f
        return f

    def CreateFrame(self, type_):
        global file_name
        input_path = Path(file_name).parent if file_name else None
        if type_ == 0:
            return MulimgViewer(None, self.UpdateUI, self.get_type, default_path=input_path)
        elif type_ == 1:
            return PathSelectFrame(None, self.UpdateUI, self.get_type)
        else:
            raise ValueError(f"Unknown frame type: {type_}")


class MainAPP(wx.App):
    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI, self.get_type)
        self.frame = [None, None]
        self.frame[0] = self.manager.GetFrame(0)  # 主窗口
        self.frame[1] = self.manager.GetFrame(1)  # 选择窗口
        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        self.type = 0  # init show MulimgViewer
        return True

    def UpdateUI(self, type, input_path=None, parallel_to_sequential=False):
        """
        type: 1=PathSelectFrame, 0=MulimgViewer, -1=全部关闭
        input_path: list[str] 或 None
        parallel_to_sequential: 保持原参数
        """
        self.type = type
        self.thread = 4

        if input_path:
            if len(input_path) != 0:
                if self.frame[0].shared_config.video_mode:
                    self.video_manual(input_path)
                    self.frame[0].show_img_init()
                    self.frame[0].ImgManager.set_action_count(0)
                    self.frame[0].show_img()
                    self.frame[0].choice_input_mode.SetSelection(2)
                    self.frame[0].SetStatusText_(["Input", "-1", "-1", "-1"])
                else:
                    self.frame[0].ImgManager.init(input_path, 1, parallel_to_sequential)
                    #self.frame[1].refresh_txt(input_path)
                    self.frame[0].show_img_init()
                    self.frame[0].ImgManager.set_action_count(0)
                    self.frame[0].show_img()

        if type == -1:
            try:
                self.frame[0].close(None)
            except Exception:
                pass
            try:
                self.frame[1].close(None)
            except Exception:
                pass
            return True

        if type == 0:
            if self.frame[1]:
                self.frame[1].Show(False)
            self.frame[0].Show(True)
            self.SetTopWindow(self.frame[0])
            return True

        if type == 1:
            try:
                if self.frame[1]:
                    self.frame[1].Destroy()
            except Exception:
                pass
            self.frame[1] = None

            self.frame[1] = self.manager.CreateFrame(1)

            self.frame[1].Show(True)
            self.frame[1].Raise()
            self.SetTopWindow(self.frame[1])
            return True

        return True

    def get_type(self):
        return self.type

    def video_manual(self,input_path):
        if input_path and len(input_path) == 1:
            self.frame[0].real_video_path = input_path[0]
        else:
            self.frame[0].real_video_path = input_path
        self.thread = int(self.frame[0].m_textCtrl29.GetValue())
        self.cache_num = int(self.frame[0].m_textCtrl30.GetValue())
        if input_path and len(input_path) == 1:
            self.frame[0].count_per_action = self.frame[0].get_count_per_action(2)
        else:
            self.frame[0].count_per_action = self.frame[0].get_count_per_action(type=1)
        self.frame[0].video_path = []
        for vp in input_path:
            cache = self.frame[0].video_manager.init_video_frame_cache(
                Path(vp),
                num_frames=(self.frame[0].cache_num+1)*self.frame[0].count_per_action,
                max_threads=self.frame[0].thread
            )
            self.frame[0].video_path.append(cache)
        if input_path and len(input_path) == 1:
            self.frame[0].ImgManager.init(str(self.frame[0].video_path[0]), type=2, video_mode=self.frame[0].video_mode, video_path=input_path[0],skip=self.frame[0].skip_frames)
        else:
            self.frame[0].ImgManager.init(self.frame[0].video_path, type=1, video_mode=self.frame[0].video_mode, video_path=input_path,skip=self.frame[0].skip_frames)
        self.frame[0].current_batch_idx = 0


def main():
    global file_name
    file_name = sys.argv[1] if len(sys.argv) > 1 else None
    app = MainAPP()
    # 调试可打开：
    # wx.lib.inspection.InspectionTool().Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
