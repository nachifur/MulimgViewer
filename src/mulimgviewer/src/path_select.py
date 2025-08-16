import wx
from ..gui.path_select_gui import PathSelectFrameGui

from .utils import get_resource_path

VIDEO_WILDCARD = "Video (*.mp4;*.mov;*.avi;*.mkv)|*.mp4;*.mov;*.avi;*.mkv|All files (*.*)|*.*"


class PathSelectFrame (PathSelectFrameGui):

    def __init__(self, parent, UpdateUI, get_type, title="Parallel manual choose input directory"):
        super().__init__(parent)
        self.title = title
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.video_mode = False  # 本地缓存
        self.Bind(wx.EVT_CLOSE, self.close)
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)

    def frame_resize(self, event):
        self.m_richText1.SetMinSize(
            wx.Size((self.Size.Width, self.Size.Height)))
        self.Layout()
        self.Refresh()

    #     # ← 新增：主窗体直接调用这个方法即可
    # def on_video_mode_change(self, value: bool):
    #     self.video_mode = bool(value)
    #     if self.video_mode:
    #         self.m_dirPicker1 = wx.FileDialog(self, "Select videos",
    #                         wildcard="Video (*.mp4;*.mov;*.avi;*.mkv)|*.mp4;*.mov;*.avi;*.mkv|All files (*.*)|*.*",
    #                         style=wx.FD_OPEN|wx.FD_MULTIPLE|wx.FD_FILE_MUST_EXIST)

    def on_video_mode_change(self, value: bool):
        row = self.GetSizer().GetItem(0).GetSizer()  # 第一行的水平 sizer
        if value:  # → 视频模式：把 DirPicker 换成“选择视频(多选)”按钮
            if isinstance(self.m_dirPicker1, wx.DirPickerCtrl):
                old = self.m_dirPicker1
                new = wx.Button(self, wx.ID_ANY, "Select videos…")
                new.Bind(wx.EVT_BUTTON, self._choose_videos)
                row.Replace(old, new)     # 关键：替换 sizer 里的控件
                old.Destroy()             # 销毁旧控件
                self.m_dirPicker1 = new   # 二次赋值，指向新控件
                self.Layout()
        else:   # → 图片模式：把按钮换回 DirPicker（一次选一个文件夹）
            if not isinstance(self.m_dirPicker1, wx.DirPickerCtrl):
                old = self.m_dirPicker1
                new = wx.DirPickerCtrl(self, wx.ID_ANY, wx.EmptyString, "Select a folder",style=wx.DIRP_DEFAULT_STYLE)
                new.Bind(wx.EVT_DIRPICKER_CHANGED, self.add_dir)  # 你的原有处理
                row.Replace(old, new)
                old.Destroy()
                self.m_dirPicker1 = new
                self.Layout()

    def _choose_videos(self, event):
        with wx.FileDialog(self, "Select videos", wildcard=VIDEO_WILDCARD,
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.m_richText1.AppendText("\n".join(dlg.GetPaths()) + "\n")
                paths = dlg.GetPaths()                 # list[str]
                self.UpdateUI(2, input_path=paths,video_mode=self.video_mode)

    def refresh_txt(self, input_path=None):
        if input_path == None:
            pass
        else:
            str_ = ""
            for path in input_path:
                str_ = str_+path+"\n"
            self.m_richText1.Value = str_

    def close(self, event):
        if self.get_type() == -1:
            self.Destroy()
        else:
            texts = self.m_richText1.Value
            strlist = texts.split('\n')
            strlist = [i for i in strlist if i != ""]

            self.UpdateUI(0, input_path=strlist)

    def add_dir(self, event):
        if self.m_dirPicker1.GetPath() == "":
            pass
        else:
            texts = self.m_richText1.Value
            strlist = texts.split('\n')
            strlist = [i for i in strlist if i != ""]
            strlist.append(self.m_dirPicker1.GetPath())

            str_ = ""
            for path in strlist:
                str_ = str_+path+"\n"
            self.m_richText1.Value = str_

    def clear_all_path(self, event):
        self.m_richText1.Clear()

    def clear_last_path(self, event):
        texts = self.m_richText1.Value
        strlist = texts.split('\n')
        str_ = ""
        if strlist[-1] == "":
            strlist.pop()
        for value in strlist[0:-1]:
            str_ += value+"\n"
        self.m_richText1.Value = str_
