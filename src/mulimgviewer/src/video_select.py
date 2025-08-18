# -*- coding: utf-8 -*-
import wx
import os

VIDEO_WILDCARD = (
    "Video (*.mp4;*.mov;*.avi;*.mkv;*.webm;*.mpg;*.mpeg;*.ts;*.m2ts)|"
    "*.mp4;*.mov;*.avi;*.mkv;*.webm;*.mpg;*.mpeg;*.ts;*.m2ts|"
    "All files (*.*)|*.*"
)

class VideoSelectFrame(wx.Frame):
    """
    纯独立的视频选择 GUI：
    - “Select videos…” 多选 -> 文本框预览列表
    - Clear last / Clear all
    - Cancel / OK（只有 OK 才把所选路径回传到主窗体）
    - 窗口未关闭期间绝不触发加载
    """
    def __init__(self, parent, UpdateUI, get_type, title="Select Videos"):
        wx.Frame.__init__(self, parent, wx.ID_ANY, title,
                          style=wx.DEFAULT_FRAME_STYLE | wx.CLIP_CHILDREN)
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.paths = []

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 顶部工具行
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(wx.StaticText(panel, label="Selected videos:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        btn_pick = wx.Button(panel, label="Select videos…")
        btn_pick.Bind(wx.EVT_BUTTON, self._on_pick)
        top.Add(btn_pick, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)

        btn_clear_last = wx.Button(panel, label="Clear last")
        btn_clear_last.Bind(wx.EVT_BUTTON, self._on_clear_last)
        top.Add(btn_clear_last, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)

        btn_clear_all = wx.Button(panel, label="Clear all")
        btn_clear_all.Bind(wx.EVT_BUTTON, self._on_clear_all)
        top.Add(btn_clear_all, 0, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 4)

        vbox.Add(top, 0, wx.EXPAND | wx.ALL, 6)

        # 预览列表
        self.txt = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_READONLY)
        self.txt.SetMinSize(wx.Size(640, 320))
        vbox.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # 底部按钮
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        bottom.AddStretchSpacer(1)

        btn_cancel = wx.Button(panel, id=wx.ID_CANCEL, label="Cancel")
        btn_cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        bottom.Add(btn_cancel, 0, wx.ALL, 6)

        btn_ok = wx.Button(panel, id=wx.ID_OK, label="OK")
        btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        bottom.Add(btn_ok, 0, wx.ALL, 6)

        vbox.Add(bottom, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(vbox)
        self.SetMinSize(wx.Size(720, 460))

        # 关闭：只关窗口，不触发任何加载
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # 可选图标（如果你的包里有这个 png 就会设置成功）
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "mulimgviewer.png")
            if os.path.exists(icon_path):
                self.SetIcon(wx.Icon(icon_path))
        except Exception:
            pass

    # —— 行为实现（尽量扁平）——
    def _refresh_text(self):
        self.txt.SetValue("\n".join(self.paths))

    def _on_pick(self, _):
        with wx.FileDialog(self, "Select videos",
                           wildcard=VIDEO_WILDCARD,
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                new = dlg.GetPaths()
                seen = set(self.paths)
                for p in new:
                    if p not in seen:
                        self.paths.append(p); seen.add(p)
                self._refresh_text()

    def _on_clear_last(self, _):
        if self.paths:
            self.paths.pop()
            self._refresh_text()

    def _on_clear_all(self, _):
        if self.paths:
            self.paths = []
            self._refresh_text()

    def _on_ok(self, _):
        if not self.paths:
            wx.MessageBox("Please select at least one video.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return
        try:
            # 1) 回传所选路径，type=2 仍然沿用你项目中“视频已选”的语义
            self.UpdateUI(2, input_path=list(self.paths), video_mode=True)
            # 2) 切回主窗体（此时主窗体里会检查 pending 并再 CallAfter 启动）
            self.UpdateUI(0)
        finally:
            self.Show(False)  # 隐藏窗口（也可以 Destroy）

    def _on_cancel(self, _):
        self.Show(False)

    def _on_close(self, evt):
        self.Destroy()