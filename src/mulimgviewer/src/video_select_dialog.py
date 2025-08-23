import wx
from pathlib import Path

# 支持的视频扩展名
_VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts")

def _is_video(p: str) -> bool:
    try:
        return str(p).lower().endswith(_VIDEO_EXTS)
    except Exception:
        return False

# ========== 会话级（仅本次运行有效）的“记忆” ==========
# 不写入磁盘，进程结束即清空
_SESSION_PATHS = []          # list[str]，本次会话已选的所有视频（存在才保留）
from typing import Optional
_SESSION_DIR: Optional[str] = None 

class _FileDrop(wx.FileDropTarget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
    def OnDropFiles(self, x, y, filenames):
        self.owner._add_paths(filenames)
        return True


class VideoSelectDialog(wx.Dialog):
    """
    外观/布局尽量贴合你给的截图：
    顶部：只读路径框 + Browse / Clear all path / Clear last path
    中部：大号只读多行框显示所有已选路径（支持拖拽视频进来）
    底部：标准 OK / Cancel
    """
    def __init__(self, parent, title="Parallel manual choose input directory",
             default_paths=None, default_dir: Optional[str] = None):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # —— 初始化本次对话框的初始内容 —— #
        # 优先用调用者传入的 default_paths/default_dir；否则回退到会话记忆
        init_paths = list(default_paths or _SESSION_PATHS)
        # 只保留“仍然存在”的视频文件
        init_paths = [str(Path(p)) for p in init_paths if _is_video(p) and Path(p).exists()]

        self._paths = init_paths
        self._default_dir = default_dir or _SESSION_DIR

        # ====== UI ======
        panel = wx.Panel(self)
        panel.SetName("panel")

        self.txt_current = wx.TextCtrl(panel, style=wx.TE_READONLY)
        btn_browse      = wx.Button(panel, label="Browse")
        btn_clear_all   = wx.Button(panel, label="Clear all path")
        btn_clear_last  = wx.Button(panel, label="Clear last path")

        self.txt_area = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SIMPLE | wx.TE_DONTWRAP
        )
        self.txt_area.SetDropTarget(_FileDrop(self))  # 支持拖拽视频到白板

        # —— 布局（与截图一致的横向按钮行 + 大白板）——
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.txt_current, 1, wx.EXPAND | wx.RIGHT, 12)
        row.Add(btn_browse,     0, wx.RIGHT, 12)
        row.Add(btn_clear_all,  0, wx.RIGHT, 12)
        row.Add(btn_clear_last, 0, 0)

        top = wx.BoxSizer(wx.VERTICAL)
        top.Add(row, 0, wx.EXPAND | wx.ALL, 12)
        top.Add(self.txt_area, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(top)

        # 标准按钮（OK/Cancel）
        std = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        dlg_sizer = wx.BoxSizer(wx.VERTICAL)
        dlg_sizer.Add(panel, 1, wx.EXPAND)
        if std:
            dlg_sizer.Add(std, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizerAndFit(dlg_sizer)

        self.SetSize((780, 520))
        self.SetMinSize((620, 420))
        self.CentreOnParent()

        # 事件
        btn_browse.Bind(wx.EVT_BUTTON, self.on_browse)
        btn_clear_all.Bind(wx.EVT_BUTTON, self.on_clear_all)
        btn_clear_last.Bind(wx.EVT_BUTTON, self.on_clear_last)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)

        # 刷新显示
        self._refresh_preview()
        self._update_ok_enabled()

    # ===== 对外 API =====
    def get_paths(self):
        """返回当前有效的视频路径（自动剔除不存在的）。"""
        self._drop_non_exists()
        return list(self._paths)

    # ===== 内部逻辑 =====
    def _drop_non_exists(self):
        """剔除已不存在的文件。"""
        changed = False
        if self._paths:
            filtered = [p for p in self._paths if Path(p).exists()]
            if len(filtered) != len(self._paths):
                self._paths = filtered
                changed = True
        if changed:
            self._refresh_preview()
            self._update_ok_enabled()

    def _add_paths(self, paths):
        added = False
        for p in paths:
            if not p:
                continue
            p = str(Path(p).expanduser().resolve())
            if not _is_video(p):
                continue
            if not Path(p).exists():
                continue
            if p not in self._paths:
                self._paths.append(p)
                added = True
                # 记录最近目录（供 FileDialog 默认目录使用）
                try:
                    self._default_dir = str(Path(p).parent)
                except Exception:
                    pass
        if added:
            self._refresh_preview()
            self._update_ok_enabled()

    def _refresh_preview(self):
        self.txt_current.SetValue(self._paths[-1] if self._paths else "")
        self.txt_area.SetValue("\n".join(self._paths))

    def _update_ok_enabled(self):
        ok_btn = self.FindWindowById(wx.ID_OK)
        if ok_btn:
            ok_btn.Enable(bool(self._paths))

    # ===== 事件处理 =====
    def on_browse(self, evt):
        wildcard = "Video files|" + ";".join(f"*{ext}" for ext in _VIDEO_EXTS)
        # 使用会话内记忆的目录（若可用）
        start_dir = None
        if self._default_dir and Path(self._default_dir).exists():
            start_dir = self._default_dir
        elif self._paths:
            pd = str(Path(self._paths[-1]).parent)
            if Path(pd).exists():
                start_dir = pd

        with wx.FileDialog(
            self,
            message="Choose video(s)",
            wildcard=wildcard,
            defaultDir=start_dir or "",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
        ) as fd:
            if fd.ShowModal() == wx.ID_OK:
                self._add_paths(fd.GetPaths())

    def on_clear_all(self, evt):
        self._paths.clear()
        self._refresh_preview()
        self._update_ok_enabled()

    def on_clear_last(self, evt):
        if self._paths:
            self._paths.pop()
            self._refresh_preview()
            self._update_ok_enabled()

    def on_ok(self, evt):
        # 退出前再清一次不存在的路径
        self._drop_non_exists()

        # 写回“会话记忆”（只在内存里，进程结束即清）
        global _SESSION_PATHS, _SESSION_DIR
        _SESSION_PATHS = list(self._paths)
        if self._paths:
            try:
                _SESSION_DIR = str(Path(self._paths[-1]).parent)
            except Exception:
                pass

        self.EndModal(wx.ID_OK)
