import wx
from ..gui.path_select_gui import PathSelectFrameGui

from .utils import get_resource_path


class PathSelectFrame (PathSelectFrameGui):

    def __init__(self, parent, UpdateUI, get_type, title="Parallel manual choose input directory"):
        super().__init__(parent)

        self.title = title
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.Bind(wx.EVT_CLOSE, self.close)
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)

    def frame_resize(self, event):
        self.m_richText1.SetMinSize(
            wx.Size((self.Size.Width, self.Size.Height)))
        self.Layout()
        self.Refresh()

    def refresh_txt(self, input_path=None):
        if input_path == None:
            pass
        else:
            str_ = ""
            for path in input_path:
                str_ = str_+path+"\n"
            self.m_richText1.Value = str_

    def close(self, event):
        if self.get_type() == -1:
            self.Destroy()
        else:
            texts = self.m_richText1.Value
            strlist = texts.split('\n')
            strlist = [i for i in strlist if i != ""]

            self.UpdateUI(0, input_path=strlist)

    def add_dir(self, event):
        if self.m_dirPicker1.GetPath() == "":
            pass
        else:
            texts = self.m_richText1.Value
            strlist = texts.split('\n')
            strlist = [i for i in strlist if i != ""]
            strlist.append(self.m_dirPicker1.GetPath())

            str_ = ""
            for path in strlist:
                str_ = str_+path+"\n"
            self.m_richText1.Value = str_

    def clear_all_path(self, event):
        self.m_richText1.Clear()

    def clear_last_path(self, event):
        texts = self.m_richText1.Value
        strlist = texts.split('\n')
        str_ = ""
        if strlist[-1] == "":
            strlist.pop()
        for value in strlist[0:-1]:
            str_ += value+"\n"
        self.m_richText1.Value = str_
