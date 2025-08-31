import wx
from ..gui.about_gui import AboutGui

from .utils import get_resource_path


class About (AboutGui):
    def __init__(self, parent, version, update=False, new_version=None):
        super().__init__(parent)

        self.about_txt.SetEditable(False)
        self.about_txt.BeginFontSize(12)
        self.about_txt.BeginBold()
        if update:
            self.about_txt.BeginTextColour(wx.Colour(255,0,0,255))
            self.about_txt.WriteText(f"A new version ({new_version}) is available!!!\n")
            self.about_txt.EndTextColour()

        self.about_txt.WriteText("Software: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("MulimgViewer\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Maintainer: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("nachifur\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Mail: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("1476879092@qq.com\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Version: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText(str(version)+"\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Platform: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("python3.6\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Architecture: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("amd64\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Image format: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText("png, jpg, bmp, tif\n")

        self.about_txt.BeginBold()
        self.about_txt.WriteText("Description: ")
        self.about_txt.EndBold()
        self.about_txt.WriteText(
            "MulimgViewer is a multi-image viewer that can open multiple images in one interface, which is convenient for image comparison and image stitching.\n")

        self.about_txt.EndFontSize()

        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)

        if update:
            self.m_hyperlink3.SetBackgroundColour(wx.Colour(255, 0, 0, 255))
