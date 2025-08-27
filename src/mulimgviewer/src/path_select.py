import wx
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path


class PathSelectFrame(PathSelectFrameGui):
    def __init__(self, parent, UpdateUI, get_type, video_mode=False, title = "Parallel manual choose input directory"):
        super().__init__(parent)

        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.SetTitle(title)
        self.video_mode = False  

        try:
            self.SetIcon(wx.Icon(get_resource_path("mulimgviewer.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        self.Bind(wx.EVT_CLOSE, self._on_close)

        row_sizer = self.GetSizer().GetItem(0).GetSizer()

        if video_mode:
            try:
                self.m_dirPicker1.Unbind(wx.EVT_DIRPICKER_CHANGED)
            except Exception:
                pass
            self.m_dirPicker1.Hide()

            self.m_filePicker1 = wx.FilePickerCtrl(
                self, wx.ID_ANY, wx.EmptyString, u"Select a video",
                wildcard="Video files (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv",
                style=wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST | wx.FLP_USE_TEXTCTRL
            )
            row_sizer.Insert(0, self.m_filePicker1, 0, wx.ALL, 5)
            self.m_filePicker1.Bind(wx.EVT_FILEPICKER_CHANGED, self.add_video)

        if not hasattr(self, "input_paths"):
            self.input_paths = []

        self.Layout()

    def frame_resize(self, event):
        self.m_richText1.SetMinSize(wx.Size(self.Size.Width, self.Size.Height))
        self.Layout()
        self.Refresh()

    def refresh_txt(self, input_path=None):
        if input_path:
            self.m_richText1.Value = "\n".join(input_path) + "\n"

    def _finalize_and_return(self):
        """收集路径并回调，然后关闭窗口。"""
        paths = [p for p in self.m_richText1.Value.split("\n") if p]
        if self.get_type() == -1:
            self.Destroy()
        else:
            try:
                self.UpdateUI(0, input_path=paths)
            finally:
                self.Destroy()
    
    def on_video_mode_change(self, video_mode):
        self.video_mode = video_mode

    def _on_close(self, event):
        self._finalize_and_return()

    def Close(self, event):  # noqa: N802  保持与生成代码绑定的名字一致
        self._finalize_and_return()

    def add_dir(self, event):
        p = self.m_dirPicker1.GetPath()
        if not p:
            return
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if p not in cur:
            cur.append(p)
        self.m_richText1.Value = "\n".join(cur) + "\n"

    def add_video(self, event):
        p = self.m_filePicker1.GetPath()
        if not p:
            return
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if p not in cur:
            cur.append(p)
        self.m_richText1.Value = "\n".join(cur) + "\n"
        self.m_filePicker1.SetPath("")

    def clear_all_path(self, event):
        self.m_richText1.Clear()

    def clear_last_path(self, event):
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if cur:
            cur.pop()
        self.m_richText1.Value = "\n".join(cur) + ("\n" if cur else "")