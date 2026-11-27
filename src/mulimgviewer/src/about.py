"""About-window content; layout and events are owned by about_gui.fbp."""
import platform
import wx
from ..gui.about_gui import AboutGui
from .localization import bind_window, tr
from .utils import get_resource_path


class About(AboutGui):
    def __init__(self, parent, version, update=False, new_version=None):
        super().__init__(parent)
        self._version_info = version, update, new_version
        self.about_txt.SetEditable(False)
        self.SetIcon(wx.Icon(get_resource_path('mulimgviewer.png'), wx.BITMAP_TYPE_PNG))
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        bind_window(self)

    def _refresh_language(self):
        version, update, new_version = self._version_info
        self.about_txt.Clear()
        self.about_txt.BeginFontSize(max(9, self.GetFont().GetPointSize()))
        if update:
            self.about_txt.BeginBold()
            self.about_txt.WriteText(tr("New version available: {version}").format(version=new_version) + "\n\n")
            self.about_txt.EndBold()
            self.releases_link.SetLabel(tr("Get new version"))
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
            self.about_txt.WriteText(tr(label) + ": ")
            self.about_txt.EndBold()
            self.about_txt.WriteText(tr(value) + "\n")
        self.about_txt.EndFontSize()
        self.about_txt.DiscardEdits()
        self.about_txt.SetInsertionPoint(0)
        self.Layout()

    def on_close(self, event):
        self.Destroy()

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(event)
        else:
            event.Skip()
