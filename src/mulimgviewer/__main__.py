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

    def get_type(self):
        # 没设过就给个默认 0
        return getattr(self, "type", 0)

    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI, self.get_type)
        self.frame = []
        self.frame.append(self.manager.GetFrame(0))
        self.frame.append(self.manager.GetFrame(1))
        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        self.type = 0  # init show MulimgViewer
        return True

    def UpdateUI(self, type, input_path=None, video_mode=False, parallel_to_sequential=False):
        # type=1: PathSelectFrame
        # type=0: MulimgViewer
        # type=-1: Close
        # type=2: 选择了视频文件列表（自定义）
        self.type = type

        main   = self.frame[0]  # MulimgViewer 实例
        picker = self.frame[1]  # PathSelectFrame 实例

        # 计算“有效视频模式”：显式开关优先；否则 type==2；否则沿用主窗体当前状态
        use_video = bool(video_mode or type == 2 or getattr(main, "video_mode", False))

        # ======= 视频流程（等价于你 second 版）=======
        if use_video:
            if type == 2 and input_path:   # 真正开始加载视频
                main.video_mode = True
                if hasattr(main, "set_video_paths"):
                    main.set_video_paths(input_path)
                else:
                    main.real_video_path = list(input_path)
                import wx
                wx.CallAfter(main.one_dir_mul_dir_manual, None)  # 避免与对话框收尾重入
            elif type == 0:
                picker.Show(False); main.Show(True)
            elif type == 1:
                picker.Show(True)
            return True  # 早退，避免被图片流程覆盖

        # ======= 图片流程（等价于你 first 版）=======
        if type in (0, 1):
            # 先做显示切换
            if type == 0:
                picker.Show(False); main.Show(True)
            else:
                picker.Show(True)

            # 有路径才刷新
            if input_path:
                main.video_mode = False
                self.frame[0].ImgManager.init(input_path, 1, parallel_to_sequential)
                self.frame[1].refresh_txt(input_path)
                self.frame[0].show_img_init()
                self.frame[0].ImgManager.set_action_count(0)
                self.frame[0].show_img()
            return True

        # 关闭
        if type == -1:
            self.frame[0].close(None)
            self.frame[1].close(None)
        return True

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
