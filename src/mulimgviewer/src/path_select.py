"""Ordered parallel-source selection; FBP owns the window layout."""
from pathlib import Path
import wx
from ..gui.path_select_gui import PathSelectFrameGui
from .utils import get_resource_path

_PATH_SELECT_STATE = {"video_mode": False, "last_manual_paths": []}


class PathSelectFrame(PathSelectFrameGui):
    def __init__(self, parent, UpdateUI, get_type, title=None, video_manager=None):
        super().__init__(parent)
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.video_manager = video_manager
        self.shared_config = None
        self._last_folder_dir = ""
        self._last_video_dir = ""
        self._finalizing = False
        self._custom_title = title
        self.SetMinSize(self.FromDIP(wx.Size(440, 320)))
        self.SetIcon(wx.Icon(get_resource_path("mulimgviewer.png"), wx.BITMAP_TYPE_PNG))
        self.apply_button.SetDefault()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        shortcuts = (
            (wx.ACCEL_CTRL, wx.WXK_RETURN, self.apply_button, self.on_apply),
            (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, self.cancel_button, self.on_cancel),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_DELETE, self.button_clear_all, self.clear_all_path),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_BACK, self.button_clear_last, self.clear_last_path),
        )
        self._selection_accelerators = [(flags, key, control.GetId()) for flags, key, control, _ in shortcuts]
        self.SetAcceleratorTable(wx.AcceleratorTable(self._selection_accelerators))
        for _, _, control, handler in shortcuts:
            self.Bind(wx.EVT_MENU, handler, id=control.GetId())
        self._sync_mode()
        if not _PATH_SELECT_STATE["video_mode"]:
            self.refresh_txt(_PATH_SELECT_STATE["last_manual_paths"])
            if self._paths():
                self._last_folder_dir = self._paths()[0]
        self._update_actions()
        self.Layout()

    def _sync_mode(self):
        video = _PATH_SELECT_STATE["video_mode"]
        self.SetTitle(self._custom_title or ("Parallel video sources" if video else "Parallel image folders"))
        self._set_source_hint()
        self.browse_button.SetLabel("Add videos..." if video else "Add folders...")
        self.Layout()

    def _paths(self):
        paths = []
        for line in self.paths_text.GetValue().splitlines():
            path = line.strip()
            if len(path) > 1 and path[0] == path[-1] and path[0] in ('"', "'"):
                path = path[1:-1]
            # Manual repetitions are intentional parallel sources; preserve
            # them just as the original editor did. Browse avoids new repeats.
            if path:
                paths.append(path)
        return paths

    def _update_actions(self):
        if not hasattr(self, 'source_count'):
            return
        count = len(self._paths())
        self.source_count.SetLabel(f"{count} source" + ("" if count == 1 else "s"))
        for control in (self.apply_button, self.button_clear_last, self.button_clear_all):
            control.Enable(count > 0)

    def _set_source_hint(self, message=None):
        media = "video" if _PATH_SELECT_STATE["video_mode"] else "folder"
        self.source_hint.SetLabel(message or f"One {media} per line, in display order.")
        self.Layout()

    def on_paths_changed(self, event):
        self._update_actions()
        self._set_source_hint()
        event.Skip()

    def set_video_manager(self, vm, sh):
        self.video_manager = vm
        self.shared_config = sh
        self._sync_mode()
        if _PATH_SELECT_STATE["video_mode"] and getattr(sh, "real_video_path", None):
            paths = list(sh.real_video_path)
            self.refresh_txt(paths)
            self._last_video_dir = str(Path(paths[0]).parent)

    def refresh_txt(self, input_path=None):
        paths = [str(path) for path in (input_path or []) if path]
        self.paths_text.SetValue("\n".join(paths) + ("\n" if paths else ""))
        self._update_actions()

    def _return_to_main(self):
        if self.get_type() != -1:
            self.UpdateUI(0)
        self.Destroy()

    def _finalize_and_return(self):
        """Apply the ordered list; preserve the existing close-to-apply workflow."""
        if self._finalizing:
            return False
        if self.get_type() == -1:
            self.Destroy()
            return True
        paths = self._paths()
        if not paths:
            self._return_to_main()
            return True
        self._finalizing = True
        try:
            if _PATH_SELECT_STATE["video_mode"]:
                if self.video_manager is None or self.shared_config is None:
                    self._set_source_hint("Video input is not ready; reopen this window.")
                    return False
                if not getattr(self.shared_config, 'video_mode', False):
                    self._set_source_hint("Video mode changed; reopen this window.")
                    return False
                if not self.video_manager.select_video(type=-1, paths=paths):
                    self._set_source_hint("Cannot open sources; check the main status bar.")
                    return False
                self.Destroy()
            else:
                for index, path in enumerate(paths, 1):
                    if not Path(path).is_dir():
                        self._set_source_hint(f"Source {index}: choose an existing image folder.")
                        return False
                self.UpdateUI(0, input_path=paths)
                _PATH_SELECT_STATE["last_manual_paths"] = paths
                self.Destroy()
            return True
        finally:
            self._finalizing = False

    def on_apply(self, event):
        if self.apply_button.IsEnabled():
            self._finalize_and_return()

    def on_cancel(self, event):
        self._return_to_main()

    def on_browse(self, event):
        self._sync_mode()
        video = _PATH_SELECT_STATE["video_mode"]
        if video:
            from .video_manager import VideoManager
            wildcard = 'Video files|' + ';'.join('*' + suffix for suffix in VideoManager.VIDEO_EXTENSIONS) + '|All files (*.*)|*.*'
            dialog = wx.FileDialog(self, "Add video sources", self._last_video_dir,
                                   wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
        else:
            dialog = wx.DirDialog(self, "Add image folder", self._last_folder_dir,
                                  style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            paths = dialog.GetPaths() if video else [dialog.GetPath()]
            if paths:
                if video:
                    self._last_video_dir = str(Path(paths[0]).parent)
                else:
                    self._last_folder_dir = paths[0]
                current = self._paths()
                for path in paths:
                    if path not in current:
                        current.append(path)
                self.refresh_txt(current)
        finally:
            dialog.Destroy()

    def _on_close(self, event):
        if not self._finalize_and_return():
            if event.CanVeto():
                event.Veto()
            else:
                self.Destroy()

    def close(self, event):
        self._finalize_and_return()

    def clear_all_path(self, event):
        self.refresh_txt([])

    def clear_last_path(self, event):
        self.refresh_txt(self._paths()[:-1])


def on_video_mode_change(video_mode):
    _PATH_SELECT_STATE["video_mode"] = video_mode
