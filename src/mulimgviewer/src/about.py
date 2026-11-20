"""About-window content; layout and events are owned by about_gui.fbp."""
import platform
import wx
from ..gui.about_gui import AboutGui
from .utils import get_resource_path


class About(AboutGui):
    def __init__(self, parent, version, update=False, new_version=None):
        super().__init__(parent)
        self.about_txt.SetEditable(False)
        self.about_txt.BeginFontSize(max(9, self.GetFont().GetPointSize()))
        if update:
            self.about_txt.BeginBold()
            self.about_txt.WriteText(f"New version available: {new_version}\n\n")
            self.about_txt.EndBold()
            self.releases_link.SetLabel("Get new version")
        details = (
            ("Version", str(version)),
            ("Maintainer", "nachifur"),
            ("Contact", "1476879092@qq.com"),
            ("Python", platform.python_version()),
            ("System", f"{platform.system()} {platform.release()}"),
            ("Architecture", platform.machine() or "Unknown"),
            ("wxPython", wx.VERSION_STRING),
            ("Description", "Image/video comparison, magnifiers, custom algorithms and stitch export."),
            ("Image formats", "PNG, JPG, BMP and TIFF."),
            ("Video decoding", "FFmpeg."),
        )
        for label, value in details:
            self.about_txt.BeginBold()
            self.about_txt.WriteText(label + ": ")
            self.about_txt.EndBold()
            self.about_txt.WriteText(value + "\n")
        self.about_txt.EndFontSize()
        self.about_txt.DiscardEdits()
        self.about_txt.SetInsertionPoint(0)
        self.SetIcon(wx.Icon(get_resource_path('mulimgviewer.png'), wx.BITMAP_TYPE_PNG))
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Layout()

    def on_close(self, event):
        self.Destroy()

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(event)
        else:
            event.Skip()
