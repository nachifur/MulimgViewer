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
from .src.video_select import VideoSelectFrame  # ★ 新增

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# 简单的视频扩展名判定
_VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts")

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
        elif type == 3:  # ★ 新增：独立视频选择窗
            return VideoSelectFrame(None, self.UpdateUI, self.get_type)


class MainAPP(wx.App):

    def get_type(self):
        # 没设过就给个默认 0
        return getattr(self, "type", 0)

    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI, self.get_type)
        # 用 list 固定下标：0=主窗体, 1=路径选择, 2=视频选择
        self.frame = []
        self.frame.append(self.manager.GetFrame(0))  # idx 0
        self.frame.append(self.manager.GetFrame(1))  # idx 1
        self.frame.append(self.manager.GetFrame(3))  # idx 2 ★ 新增

        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        self.type = 0  # init show MulimgViewer

        # —— 视频延后启动的 pending 状态 —— #
        self._video_pending_paths = None
        self._video_pending_p2s   = False
        return True

    def UpdateUI(self, type, input_path=None, video_mode=False, parallel_to_sequential=False):
        """
        type=1: PathSelectFrame
        type=0: MulimgViewer
        type=-1: Close
        type=2: 选择了视频文件列表（OK 之后的回传，不是窗口）
        type=3: 打开独立“视频选择窗口”
        """
        self.type = type

        main   = self.frame[0]  # MulimgViewer
        picker = self.frame[1]  # PathSelectFrame
        vsel   = self.frame[2]  # VideoSelectFrame

        # 这次调用是否“看起来像视频流程”
        looks_like_video = False
        if input_path:
            if isinstance(input_path, (list, tuple)):
                for p in input_path:
                    try:
                        if str(p).lower().endswith(_VIDEO_EXTS):
                            looks_like_video = True
                            break
                    except Exception:
                        pass
            else:
                try:
                    looks_like_video = str(input_path).lower().endswith(_VIDEO_EXTS)
                except Exception:
                    looks_like_video = False
        use_video = bool(video_mode or type == 2 or looks_like_video)

        # ========== 独立“视频选择窗口” ==========
        if type == 3:
            # 仅负责显示/隐藏，不做任何加载
            picker.Show(False)
            main.Show(False)
            vsel.Show(True)
            return True

        # ========== 视频流程 ==========
        if use_video:
            main.video_mode = True

            # 同步并转串开关到主窗体（有就设）
            try:
                if hasattr(main, "parallel_to_sequential") and hasattr(main.parallel_to_sequential, "SetValue"):
                    main.parallel_to_sequential.SetValue(bool(parallel_to_sequential))
                elif hasattr(main, "parallel_to_sequential"):
                    setattr(main.parallel_to_sequential, "Value", bool(parallel_to_sequential))
            except Exception:
                pass

            if type == 2 and input_path:
                # ★★ 只记录 pending（不加载不显示），等切回主窗体 type==0 再启动
                self._video_pending_paths = list(input_path) if isinstance(input_path, (list, tuple)) else [input_path]
                self._video_pending_p2s   = bool(parallel_to_sequential)
                return True

            if type == 0:
                # 切到主窗体：若有 pending，在这里启动
                vsel.Show(False); picker.Show(False); main.Show(True)

                if self._video_pending_paths:
                    if hasattr(main, "set_video_paths"):
                        main.set_video_paths(self._video_pending_paths)
                    else:
                        main.real_video_path = list(self._video_pending_paths)

                    try:
                        if hasattr(main, "parallel_to_sequential") and hasattr(main.parallel_to_sequential, "SetValue"):
                            main.parallel_to_sequential.SetValue(self._video_pending_p2s)
                        elif hasattr(main, "parallel_to_sequential"):
                            setattr(main.parallel_to_sequential, "Value", self._video_pending_p2s)
                    except Exception:
                        pass

                    # 确保选择窗已经隐藏，此时才启动渲染，避免“未关先显”
                    wx.CallAfter(main.one_dir_mul_dir_manual, None)

                    # 清空 pending
                    self._video_pending_paths = None
                    self._video_pending_p2s   = False
                return True

            if type == 1:
                # 虽然在视频流程里，也允许用户临时打开路径窗（不建议）
                vsel.Show(False); picker.Show(True)
                return True

            return True  # 兜底

        # ========== 图片流程 ==========
        main.video_mode = False

        if type in (0, 1):
            if type == 0:
                vsel.Show(False); picker.Show(False); main.Show(True)
            else:
                vsel.Show(False); picker.Show(True)

            if input_path:
                # 初始化图片模式
                if hasattr(main, "ImgManager") and hasattr(main.ImgManager, "init"):
                    main.ImgManager.init(input_path, 1, parallel_to_sequential)
                try:
                    picker.refresh_txt(input_path)
                except Exception:
                    pass
                try:
                    main.show_img_init()
                    main.ImgManager.set_action_count(0)
                    main.show_img()
                except Exception:
                    pass
            return True

        # ========== 关闭 ==========
        if type == -1:
            try: main.close(None)
            except: pass
            try: picker.close(None)
            except: pass
            try: vsel.Destroy()
            except: pass
        return True


def main():
    global file_name
    if len(sys.argv) > 1:
        file_name = sys.argv[1]
    else:
        file_name = None
    app = MainAPP()
    # wx.lib.inspection.InspectionTool().Show()  # 如需调试可打开
    app.MainLoop()


if __name__ == '__main__':
    main()
