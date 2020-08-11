import wx
from path_select_gui import PathSelectFrameGui


class PathSelectFrame (PathSelectFrameGui):

    def __init__(self, parent, UpdateUI, get_type, title="Select input path"):
        super().__init__(parent)

        self.title = title
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.Bind(wx.EVT_CLOSE, self.Close)

    def Close(self, event):
        if self.get_type()==-1:
            self.Destroy()
        else:
            texts = self.m_richText1.Value
            strlist = texts.split('\n')
            strlist = [i for i in strlist if i != ""]

            self.UpdateUI(0, input_path=strlist)

    def change_dir(self, event):
        if self.m_richText1.Value[-2:] != "\n":
            self.m_richText1.Value += "\n"
        self.m_richText1.AppendText(self.m_dirPicker1.GetPath()+"\n")

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
