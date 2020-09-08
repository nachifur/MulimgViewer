from index_table_gui import IndexTableGui
import wx


class IndexTable (IndexTableGui):
    def __init__(self, parent, flist, layout_params):
        super().__init__(parent)
        self.index_table.SetEditable(False)
        self.index_table.BeginFontSize(12)
        self.show_id_table(flist, layout_params)

    def frame_resize(self, event):
        # if self.index_table.Size>self.Size, the self.index_table display incomplete
        self.index_table.SetSize(wx.Size(self.Size[0], self.Size[1]-100))

    def show_id_table(self, flist, layout_params):
        self.id_list = []
        self.flist = flist
        self.index_table.Clear()
        img_num_per_row = layout_params[0]
        num_per_img = layout_params[1]
        img_num_per_column = layout_params[2]
        if num_per_img == -1:
            interval = img_num_per_row*img_num_per_column
        else:
            interval = img_num_per_row*img_num_per_column*num_per_img
        len_flist = len(flist)
        self.index_table.BeginBold()
        self.index_table.WriteText("Image index   /   Show index\n")
        self.index_table.EndBold()
        for i in range(len_flist):
            self.index_table.BeginBold()
            self.index_table.WriteText(str(i)+" : ")
            self.index_table.EndBold()
            self.index_table.WriteText(flist[i])

            if interval*i < len_flist:
                if interval*(i+1)-1 < len_flist:
                    self.index_table.WriteText("   /   ")
                    self.index_table.BeginBold()
                    self.index_table.WriteText(
                        str(i*interval)+"/"+str(interval*(i+1)-1)+" : ")
                    self.index_table.EndBold()
                    self.index_table.WriteText(
                        flist[interval*i]+"-"+flist[interval*(i+1)-1]+"\n")
                else:
                    self.index_table.WriteText("   /   ")
                    self.index_table.BeginBold()
                    self.index_table.WriteText(
                        str(i*interval)+"/"+str(len_flist-1)+" : ")
                    self.index_table.EndBold()
                    self.index_table.WriteText(
                        flist[interval*i]+"-"+flist[-1]+"\n")
            else:
                self.index_table.WriteText("\n")

    def search_txt(self, event):
        self.id_list = []
        self.id = 0
        str_search = self.m_search_txt.GetValue()
        i = 0
        for name in self.flist:
            name = str(i)+":"+name
            if name.find(str_search) != -1:
                self.id_list.append(i+1)
            i += 1
        self.set_pos(self.id)

    def next_txt(self, event):
        if self.id < len(self.id_list)-1:
            self.id += 1
            self.set_pos(self.id)

    def last_txt(self, event):
        if self.id > 0:
            self.id -= 1
            self.set_pos(self.id)

    def set_pos(self, id):
        pos = self.index_table.XYToPosition(0, self.id_list[id])
        self.index_table.ShowPosition(pos)
