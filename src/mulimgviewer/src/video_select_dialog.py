# # -*- coding: utf-8 -*-
# # video_select_dialog.py

# from __future__ import annotations
# import wx
# import os
# from pathlib import Path
# from typing import List
# import json

# # 支持的视频后缀
# _VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".m4v")

# # —— “记住上次选择” —— #
# _LAST_VIDEO_PATHS: List[str] = []  # 内存里记住；也会和磁盘互相同步
# _LAST_DIR: str | None = None

# _PERSIST_FILE = Path.home() / ".mulimgviewer" / "last_videos.json"
# _PERSIST_LOADED = False


# def _alive(paths: List[str]) -> List[str]:
#     """过滤掉不存在的路径，并转为绝对路径；保持顺序并去重。"""
#     out = []
#     for p in paths or []:
#         try:
#             P = Path(p).expanduser().resolve()
#             if P.exists():
#                 out.append(str(P))
#         except Exception:
#             pass
#     seen = set()
#     uniq = []
#     for p in out:
#         if p not in seen:
#             seen.add(p)
#             uniq.append(p)
#     return uniq


# def _load_persisted_once():
#     global _PERSIST_LOADED, _LAST_VIDEO_PATHS, _LAST_DIR
#     if _PERSIST_LOADED:
#         return
#     _PERSIST_LOADED = True
#     try:
#         if _PERSIST_FILE.exists():
#             data = json.loads(_PERSIST_FILE.read_text(encoding="utf-8"))
#             _LAST_VIDEO_PATHS = _alive(list(data.get("paths", [])))
#             _LAST_DIR = data.get("last_dir") or None
#     except Exception:
#         pass


# def _save_persisted():
#     try:
#         _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
#         data = {
#             "paths": list(_LAST_VIDEO_PATHS),
#             "last_dir": _LAST_DIR,
#         }
#         _PERSIST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
#     except Exception:
#         pass


# # 导入时尝试恢复一次
# _load_persisted_once()


# def _is_video(p: str) -> bool:
#     try:
#         return str(p).lower().endswith(_VIDEO_EXTS)
#     except Exception:
#         return False


# class _FileDrop(wx.FileDropTarget):
#     """支持把视频文件拖入大白板区域。"""
#     def __init__(self, owner: "VideoSelectDialog"):
#         super().__init__()
#         self.owner = owner
#     def OnDropFiles(self, _x, _y, filenames):
#         self.owner._add_paths(filenames)
#         return True


# class VideoSelectDialog(wx.Dialog):
#     """
#     外观尽量贴合你给的控件：
#     ┌──────────────────────────────────────────────┐
#     │ [readonly text]  [Browse] [Clear all path]  │
#     │                           [Clear last path] │
#     │                                              │
#     │   big multiline white area (list preview)    │
#     │                                              │
#     └──────────────────────────────────────────────┘
#     底部提供标准 OK/Cancel（方便 ShowModal 判定）
#     """

#     def __init__(self, parent, title="Parallel manual choose input directory"):
#         super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

#         self._paths: List[str] = _alive(_LAST_VIDEO_PATHS)  # 打开时恢复上次（只保留仍存在的）
#         panel = wx.Panel(self)
#         panel.SetName("panel")

#         # 顶部：只读文本 + 3 个按钮
#         self.txt_current = wx.TextCtrl(panel, style=wx.TE_READONLY)
#         btn_browse      = wx.Button(panel, label="Browse")
#         btn_clear_all   = wx.Button(panel, label="Clear all path")
#         btn_clear_last  = wx.Button(panel, label="Clear last path")

#         # 大白板：纯展示（多行、只读、不自动换行），支持拖文件
#         self.txt_area = wx.TextCtrl(
#             panel,
#             style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SIMPLE | wx.TE_DONTWRAP
#         )
#         self.txt_area.SetDropTarget(_FileDrop(self))

#         # —— 布局（严格贴合横排 + 大白板）——
#         top = wx.BoxSizer(wx.VERTICAL)
#         row = wx.BoxSizer(wx.HORIZONTAL)

#         row.Add(self.txt_current, 1, wx.EXPAND | wx.RIGHT, 12)
#         row.Add(btn_browse,     0, wx.RIGHT, 12)
#         row.Add(btn_clear_all,  0, wx.RIGHT, 12)
#         row.Add(btn_clear_last, 0, 0)

#         top.Add(row, 0, wx.EXPAND | wx.ALL, 12)
#         top.Add(self.txt_area, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

#         panel.SetSizer(top)

#         # 底部标准按钮（OK / Cancel）
#         std = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

#         dlg_sizer = wx.BoxSizer(wx.VERTICAL)
#         dlg_sizer.Add(panel, 1, wx.EXPAND)
#         if std:
#             dlg_sizer.Add(std, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
#         self.SetSizerAndFit(dlg_sizer)

#         self.SetSize((780, 520))
#         self.SetMinSize((620, 420))
#         self.CentreOnParent()

#         # 事件绑定
#         btn_browse.Bind(wx.EVT_BUTTON, self.on_browse)
#         btn_clear_all.Bind(wx.EVT_BUTTON, self.on_clear_all)
#         btn_clear_last.Bind(wx.EVT_BUTTON, self.on_clear_last)
#         self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
#         self.Bind(wx.EVT_BUTTON, self.on_cancel, id=wx.ID_CANCEL)

#         # 打开时刷新显示
#         self._refresh_preview()

#     # ===== 对外 API =====
#     def get_paths(self) -> List[str]:
#         """返回用户选中的路径列表（绝对路径，按加入顺序去重）。"""
#         return list(self._paths)

#     # ===== 内部逻辑 =====
#     def _add_paths(self, paths: List[str]):
#         added = False
#         seen = set(self._paths)
#         for p in paths:
#             if not p:
#                 continue
#             try:
#                 abs_p = str(Path(p).expanduser().resolve())
#             except Exception:
#                 continue
#             if not _is_video(abs_p):
#                 continue
#             if abs_p not in seen and Path(abs_p).exists():
#                 self._paths.append(abs_p)
#                 seen.add(abs_p)
#                 added = True
#         if added:
#             self._refresh_preview()

#     def _refresh_preview(self):
#         # 顶部只读框显示最后一次加入的条目
#         self.txt_current.SetValue(self._paths[-1] if self._paths else "")
#         # 大白板显示完整列表
#         self.txt_area.SetValue("\n".join(self._paths))

#     # ===== 事件处理 =====
#     def on_browse(self, _evt):
#         wildcard = (
#             "Video files (" + ";".join(f"*{ext}" for ext in _VIDEO_EXTS) + ")|"
#             + ";".join(f"*{ext}" for ext in _VIDEO_EXTS)
#             + "|All files (*.*)|*.*"
#         )
#         style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
#         with wx.FileDialog(
#             self,
#             message="Choose video(s)",
#             defaultDir=_LAST_DIR or "",
#             wildcard=wildcard,
#             style=style
#         ) as fd:
#             if fd.ShowModal() == wx.ID_OK:
#                 paths = fd.GetPaths()
#                 if paths:
#                     # 记住最后一次目录（不在方法里用 global，改用 globals() 写回模块变量）
#                     try:
#                         globals()["_LAST_DIR"] = str(Path(paths[0]).parent)
#                     except Exception:
#                         pass
#                     self._add_paths(paths)

#     def on_clear_all(self, _evt):
#         self._paths.clear()
#         self._refresh_preview()

#     def on_clear_last(self, _evt):
#         if self._paths:
#             self._paths.pop()
#             self._refresh_preview()

#     def on_ok(self, _evt):
#         # 点击 OK：把当前列表写回“记忆”，并持久化（只保留仍存在的项）
#         paths = _alive(self._paths)
#         _LAST_VIDEO_PATHS.clear()
#         _LAST_VIDEO_PATHS.extend(paths)
#         # 更新 last_dir（使用 globals()，避免在方法里写 global）
#         if paths:
#             try:
#                 globals()["_LAST_DIR"] = str(Path(paths[-1]).parent)
#             except Exception:
#                 pass
#         _save_persisted()
#         self.EndModal(wx.ID_OK)

#     def on_cancel(self, _evt):
#         # 取消：不覆盖列表，但清理一下内存里的失效条目，保持下次打开干净
#         pruned = _alive(_LAST_VIDEO_PATHS)
#         if pruned != _LAST_VIDEO_PATHS:
#             _LAST_VIDEO_PATHS.clear()
#             _LAST_VIDEO_PATHS.extend(pruned)
#             _save_persisted()
#         self.EndModal(wx.ID_CANCEL)

# -*- coding: utf-8 -*-
# video_select_dialog.py

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
_SESSION_DIR: str | None = None  # 最近一次选择文件的父目录（用于下次 FileDialog 默认目录）

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
                 default_paths=None, default_dir: str | None = None):
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
