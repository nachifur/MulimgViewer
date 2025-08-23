# -*- coding: utf-8 -*-
import wx
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path
from .video_select_dialog import VideoSelectDialog

VIDEO_WILDCARD = "Video (*.mp4;*.mov;*.avi;*.mkv)|*.mp4;*.mov;*.avi;*.mkv|All files (*.*)|*.*"

class PathSelectFrame(PathSelectFrameGui):

    def __init__(self, parent, UpdateUI, get_type, title="Parallel manual choose input directory"):
        super().__init__(parent)
        self.title = title
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.video_mode = False
        self.Bind(wx.EVT_CLOSE, self.close)
        self.icon = wx.Icon(get_resource_path('mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)

    def frame_resize(self, event):
        self.m_richText1.SetMinSize(wx.Size((self.Size.Width, self.Size.Height)))
        self.Layout()
        self.Refresh()

    def on_video_mode_change(self, event):
        # 勾选/取消，只更新模式标志，不弹任何窗口
        try:
            self.video_mode = bool(event.IsChecked())
        except Exception:
            # 有些场合你是直接手动传 True/False
            self.video_mode = bool(getattr(self, "video_mode", False))

        # UI 上给个轻提示（可留可删）
        try:
            self.SetStatusText_(["-1", "-1",
                                "Video mode: ON" if self.video_mode else "Video mode: OFF",
                                "-1"])
        except Exception:
            pass

    def _choose_videos(self, event):
        # 这个方法不再使用；保留以兼容可能的旧绑定
        with wx.FileDialog(self, "Select videos", wildcard=VIDEO_WILDCARD,
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.m_richText1.AppendText("\n".join(dlg.GetPaths()) + "\n")
                paths = dlg.GetPaths()
                self.UpdateUI(2, input_path=paths, video_mode=True)

    def refresh_txt(self, input_path=None):
        if input_path is None:
            return
        s = ""
        for p in input_path:
            s += p + "\n"
        self.m_richText1.Value = s

    def close(self, event):
        if self.get_type() == -1:
            self.Destroy()
        else:
            texts = self.m_richText1.Value
            strlist = [i for i in texts.split('\n') if i != ""]
            self.UpdateUI(0, input_path=strlist)

    def add_dir(self, event):
        if self.m_dirPicker1.GetPath() == "":
            return
        texts = self.m_richText1.Value
        strlist = [i for i in texts.split('\n') if i != ""]
        strlist.append(self.m_dirPicker1.GetPath())
        self.m_richText1.Value = "\n".join(strlist) + ("\n" if strlist else "")

    def clear_all_path(self, event):
        self.m_richText1.Clear()

    def clear_last_path(self, event):
        texts = self.m_richText1.Value
        strlist = texts.split('\n')
        if strlist and strlist[-1] == "":
            strlist.pop()
        if strlist:
            strlist = strlist[:-1]
        self.m_richText1.Value = "\n".join([v for v in strlist if v != ""])
