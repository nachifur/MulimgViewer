import wx,os
from wx.lib.agw import multidirdialog as MDD
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path

VIDEO_MODE = False

class PathSelectFrame(PathSelectFrameGui):
    def __init__(self, parent, UpdateUI, get_type, title = "Parallel manual choose input directory"):
        super().__init__(parent)

        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.SetTitle(title)

        try:
            self.SetIcon(wx.Icon(get_resource_path("mulimgviewer.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        self.Bind(wx.EVT_CLOSE, self._on_close)

        row_sizer = self.GetSizer().GetItem(0).GetSizer()

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

    def on_browse(self, event):
        if VIDEO_MODE:  # 选一个或多个视频文件
            wildcard = ("Video files (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv|"
                        "All files (*.*)|*.*")
            with wx.FileDialog(self, "选择视频",
                            wildcard=wildcard,
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                paths = dlg.GetPaths()
            if paths:
                self._last_video_dir = os.path.dirname(paths[-1])
        else:           # 选一个或多个文件夹（不进入子文件）
            dlg = MDD.MultiDirDialog(self, "选择一个或多个文件夹",
                                    agwStyle=MDD.DD_MULTIPLE | MDD.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            paths = dlg.GetPaths()
            if paths:
                self._last_folder_dir = paths[-1]
            dlg.Destroy()
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        for p in paths:
            if p not in cur:
                cur.append(p)
        self.m_richText1.Value = "\n".join(cur) + ("\n" if cur else "")

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

def on_video_mode_change(video_mode):
        global VIDEO_MODE
        VIDEO_MODE = video_mode
