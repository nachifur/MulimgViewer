import wx
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path

VIDEO_MODE = False
_LAST_MANUAL_PATHS = []

class PathSelectFrame(PathSelectFrameGui):
    def __init__(self, parent, UpdateUI, get_type, title = "Parallel manual choose input directory",video_manager=None):
        super().__init__(parent)

        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.SetTitle(title)
        self.video_manager = video_manager
        self.shared_config = None
        self._last_folder_dir = ""
        self._last_video_dir = ""

        try:
            self.SetIcon(wx.Icon(get_resource_path("mulimgviewer.png"), wx.BITMAP_TYPE_PNG))
        except Exception:
            pass

        self.Bind(wx.EVT_CLOSE, self._on_close)

        if not hasattr(self, "input_paths"):
            self.input_paths = []

        self.Layout()
        if not VIDEO_MODE and _LAST_MANUAL_PATHS:
            self.m_richText1.Value = "\n".join(_LAST_MANUAL_PATHS) + "\n"

    def set_video_manager(self, vm, sh):
        self.video_manager = vm
        self.shared_config = sh
        if VIDEO_MODE and getattr(self.shared_config, "real_video_path", None):
            paths = list(self.shared_config.real_video_path)
            wx.CallAfter(self.refresh_txt, paths)
    def frame_resize(self, event):
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
        if VIDEO_MODE:
            self.shared_config.real_video_path = paths if VIDEO_MODE else []
            if self.shared_config.video_mode:
                self.video_manager.select_video(type=-1)
        else:
            global _LAST_MANUAL_PATHS
            _LAST_MANUAL_PATHS = paths
        if self.get_type() == -1:
            self.Destroy()
        else:
            if VIDEO_MODE:
                self.Destroy()
            else:
                try:
                    self.UpdateUI(0, input_path=paths)
                finally:
                    self.Destroy()

    def on_browse(self, event):
        paths = []
        if VIDEO_MODE:  # Select one or more video files
            wildcard = ("Video files (*.mp4;*.avi;*.mov;*.mkv)|*.mp4;*.avi;*.mov;*.mkv|"
                        "All files (*.*)|*.*")
            # If video files were selected previously, use that as the initial directory
            last_dir = self._last_video_dir if hasattr(self, '_last_video_dir') else ""
            dlg = wx.FileDialog(None, "Select Video", last_dir,
                                wildcard=wildcard,
                                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
            if dlg.ShowModal() == wx.ID_OK:
                paths = dlg.GetPaths()
        else:  # Select one folder at a time; repeated browse clicks accumulate selections.
            last_dir = self._last_folder_dir if hasattr(self, '_last_folder_dir') else ""
            dlg = wx.DirDialog(self, "Select Folder", last_dir, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            selected_path = dlg.GetPath()
            if selected_path:
                paths = [selected_path]
                self._last_folder_dir = selected_path
        dlg.Destroy()

        # Update selected paths in the text box
        cur = [x for x in self.m_richText1.Value.split("\n") if x]
        if paths:
            for p in paths:
                if p not in cur:
                    cur.append(p)
            self.m_richText1.Value = "\n".join(cur) + ("\n" if cur else "")
            if not VIDEO_MODE:
                global _LAST_MANUAL_PATHS
                _LAST_MANUAL_PATHS = list(cur)

    def _on_close(self, event):
        self._finalize_and_return()

    def Close(self, event):  # noqa: N802  Keep this name to match generated-code bindings
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
