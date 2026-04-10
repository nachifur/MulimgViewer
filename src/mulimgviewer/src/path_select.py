import wx
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path

class PathSelectFrame(PathSelectFrameGui):
    video_mode = False
    last_manual_paths = []

    def __init__(self, parent, UpdateUI, get_type, title = "Parallel manual choose input directory",video_manager=None):
        super().__init__(parent)

        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.SetTitle(title)
        self.video_manager = video_manager
        self.shared_config = None
        self._last_video_dir = ""
        self._last_folder_dir = ""

        try:
            self.SetIcon(wx.Icon(get_resource_path("mulimgviewer.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        self.Bind(wx.EVT_CLOSE, self._on_close)

        if not hasattr(self, "input_paths"):
            self.input_paths = []

        self.Layout()
        if not type(self).video_mode and type(self).last_manual_paths:
            self.m_richText1.Value = "\n".join(type(self).last_manual_paths) + "\n"

    def set_video_manager(self, vm, sh):
        self.video_manager = vm
        self.shared_config = sh
        if type(self).video_mode and getattr(self.shared_config, "real_video_path", None):
            paths = list(self.shared_config.real_video_path)
            wx.CallAfter(self.refresh_txt, paths)
    def frame_resize(self, _event):
        self.m_richText1.SetMinSize(wx.Size(self.Size.Width, self.Size.Height))
        self.Layout()
        self.Refresh()

    def refresh_txt(self, input_path=None):
        if input_path:
            text = "\n".join(str(p) for p in input_path if p)
            if hasattr(self, "m_richText1") and self.m_richText1:
                try:
                    self.m_richText1.Value = (text + "\n") if text else ""
                except RuntimeError:
                    pass

    def _finalize_and_return(self):
        """Collect selected paths, invoke callback, then close the window."""
        paths = [p for p in self.m_richText1.Value.split("\n") if p]
        if type(self).video_mode:
            self.shared_config.real_video_path = paths
            if self.shared_config.video_mode:
                self.video_manager.select_video(type=-1)
        else:
            type(self).last_manual_paths = paths
        if self.get_type() == -1:
            self.Destroy()
        else:
            if type(self).video_mode:
                self.Destroy()
            else:
                try:
                    self.UpdateUI(0, input_path=paths)
                finally:
                    self.Destroy()

    def on_browse(self, _event):
        paths = []
        if type(self).video_mode:  # Select one or more video files
            wildcard = ("Video files (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv|"
                        "All files (*.*)|*.*")
            # If video files were selected previously, use that as the initial directory
            last_dir = self._last_video_dir
            dlg = wx.FileDialog(None, "Select Video", last_dir,
                                wildcard=wildcard,
                                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
            if dlg.ShowModal() == wx.ID_OK:
                paths = dlg.GetPaths()
        else:  # Select one or more folders (without descending into subfolders)
            last_dir = self._last_folder_dir
            dlg = wx.DirDialog(self, "Select One or More Folders", last_dir, style=wx.DD_DEFAULT_STYLE | wx.DD_MULTIPLE)
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            paths = dlg.GetPaths()
            if paths:
                self._last_folder_dir = paths[-1]  # Update the last selected folder path
        dlg.Destroy()

        # Update selected paths in the text box
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if paths:
            for p in paths:
                if p not in cur:
                    cur.append(p)
            self.m_richText1.Value = "\n".join(cur) + ("\n" if cur else "")
            if not type(self).video_mode:
                type(self).last_manual_paths = list(cur)

    def _on_close(self, _event):
        self._finalize_and_return()

    def Close(self, _event):  # noqa: N802  Keep this name to match generated-code bindings
        self._finalize_and_return()

    def add_dir(self, _event):
        p = self.m_dirPicker1.GetPath()
        if not p:
            return
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if p not in cur:
            cur.append(p)
        self.m_richText1.Value = "\n".join(cur) + "\n"

    def add_video(self, _event):
        p = self.m_filePicker1.GetPath()
        if not p:
            return
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if p not in cur:
            cur.append(p)
        self.m_richText1.Value = "\n".join(cur) + "\n"
        self.m_filePicker1.SetPath("")

    def clear_all_path(self, _event):
        self.m_richText1.Clear()

    def clear_last_path(self, _event):
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if cur:
            cur.pop()
        self.m_richText1.Value = "\n".join(cur) + ("\n" if cur else "")

def on_video_mode_change(video_mode):
    PathSelectFrame.video_mode = bool(video_mode)
