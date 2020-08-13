import wx
from select_image_gui import SelectImgFrameGui
import numpy as np
import os
from about import About
from shutil import copyfile
from pathlib import Path
from utils import ImgManager

class SelectImgFrame (SelectImgFrameGui):

    def __init__(self, parent, UpdateUI, get_type):
        super().__init__(parent)
        self.ImgManager = ImgManager(None)
        self.UpdateUI = UpdateUI
        self.get_type = get_type

        acceltbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('N'), self.menu_next.GetId()),
                                        (wx.ACCEL_CTRL, ord('L'),
                                         self.menu_last.GetId()),
                                        (wx.ACCEL_CTRL, ord('S'),
                                         self.menu_save.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_UP,
                                         self.menu_up.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DOWN,
                                         self.menu_down.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_RIGHT,
                                         self.menu_right.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_LEFT,
                                         self.menu_left.GetId())
                                        ])
        self.SetAcceleratorTable(acceltbl)
        self.img_Sizer = self.m_scrolledWindow1.GetSizer()
        self.m_scrolledWindow1.SetMinSize(wx.DisplaySize())
        self.Bind(wx.EVT_CLOSE, self.Close)

        # parameter
        self.input_paths = []
        self.out_path_str = ""
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.m_scrolledWindow1.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.width = self.Size[0]

    def Close(self, event):
        if self.get_type() == -1:
            self.Destroy()
        else:
            self.UpdateUI(-1)

    def next_img(self, event):
        self.SetStatusText_(["Next", "-1", "-1", "-1"])
        if self.ImgManager.img_num != 0:
            self.ImgManager.add()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the output directory***", "-1"])

    def last_img(self, event):
        self.SetStatusText_(["Last", "-1", "-1", "-1"])
        if self.ImgManager.img_num != 0:
            self.ImgManager.subtract()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1",  "", "***Error: First, need to select the output directory***", "-1"])

    def skip_to_n_img(self, event):
        self.ImgManager.set_action_count(self.m_slider1.GetValue())
        self.slider_value.SetLabel(str(self.ImgManager.action_count))
        if self.ImgManager.img_num != 0:
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the output directory***", "-1"])

    def save_img(self, event):
        layout_params = self.set_img_sizer()
        if layout_params != False:
            self.ImgManager.layout_params = layout_params
        type_ = self.m_choice1.GetSelection()
        if self.auto_save_all.Value:
            last_count_img = self.ImgManager.action_count
            self.ImgManager.set_action_count(0)

            for i in range(self.ImgManager.max_action_num):
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img***", "-1"])
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.add()

            self.ImgManager.set_action_count(last_count_img)
            self.SetStatusText_(
                ["-1", "-1", "***Finish***", "-1"])
        else:
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            if flag == 0:
                self.SetStatusText_(
                    ["Save", str(self.ImgManager.action_count)+' image', "Save "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + " success!", "-1"])
            elif flag == 1:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output directory***", "-1"])
            elif flag == 2:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count)+' image', "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            elif flag == 3:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count)+' image', "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", the number of img in sub folders is different***", "-1"])

    def refresh(self, event):
        if self.checkBox_orientation.Value:
            self.show_img(orientation="Vertical")
        else:
            self.show_img(orientation="Horizontal")

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["input_path", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager = self.create_ImgManager(dlg.GetPath(), 0)
            self.ImgManager.set_action_count(0)
            self.show_img()

    def one_dir_mul_dir_manual(self, event):
        self.input_paths = []
        self.SetStatusText_(["input_path", "", "", "-1"])
        self.UpdateUI(1)

    def one_dir_mul_img(self, event):
        self.SetStatusText_(["input_path", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager = self.create_ImgManager(dlg.GetPath(), 2)
            self.ImgManager.set_action_count(0)
            self.show_img()

    def out_path(self, event):
        if len(self.img_name) != 0:
            self.SetStatusText_(
                ["out_path", str(self.ImgManager.action_count), self.img_name[self.ImgManager.action_count], "-1"])
        else:
            self.SetStatusText_(["out_path", "-1", "-1", "-1"])
        dlg = wx.DirDialog(None, "Choose out directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.out_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.out_path_str, 3)

    def colour_change(self, event):
        c = self.m_colourPicker1.GetColour()
        self.ImgManager.gap_color = (c[0], c[1], c[2], c[3])

    def up_img(self, event):
        size = self.m_scrolledWindow1.GetSize()
        self.position[0] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if self.position[1] > 0:
            self.position[1] -= 1
        self.m_scrolledWindow1.Scroll(
            self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["up",  "-1", "-1", "-1"])

    def down_img(self, event):
        size = self.m_scrolledWindow1.GetSize()
        self.position[0] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if (self.position[1]-1)*self.Uint[1] < size[1]:
            self.position[1] += 1
            self.m_scrolledWindow1.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        else:
            self.m_scrolledWindow1.Scroll(
                self.position[0]*self.Uint[0], size[1])
        self.SetStatusText_(["down",  "-1", "-1", "-1"])

    def right_img(self, event):
        size = self.m_scrolledWindow1.GetSize()
        self.position[0] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if (self.position[0]-1)*self.Uint[0] < size[0]:
            self.position[0] += 1
            self.m_scrolledWindow1.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        else:
            self.m_scrolledWindow1.Scroll(
                self.position[0]*self.Uint[0], size[0])
        self.SetStatusText_(["right",  "-1", "-1", "-1"])

    def left_img(self, event):
        size = self.m_scrolledWindow1.GetSize()
        self.position[0] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.m_scrolledWindow1.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if self.position[0] > 0:
            self.position[0] -= 1
            self.m_scrolledWindow1.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.m_statusBar1.SetStatusText(texts[i], i)

    def set_img_sizer(self):
        try:
            img_num_per_row = int(self.img_num_per_row.GetLineText(0))
            img_num_per_column = int(self.img_num_per_column.GetLineText(0))
            num_per_img = int(self.num_per_img.GetLineText(0))
            if self.checkBox_orientation.Value:
                self.img_Sizer.SetCols(img_num_per_column)
                self.img_Sizer.SetRows(img_num_per_row*num_per_img)
            else:
                self.img_Sizer.SetCols(img_num_per_row*num_per_img)
                self.img_Sizer.SetRows(img_num_per_column)
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [num_per_img, img_num_per_row, img_num_per_column, int(self.gap.GetLineText(0)), self.img_Sizer.GetCols(), self.img_Sizer.GetRows(), self.checkBox_orientation.Value]

    def show_img(self, orientation="Horizontal"):
        self.m_slider1.SetValue(self.ImgManager.action_count)
        self.slider_value.SetLabel(str(self.ImgManager.action_count))
        layout_params = self.set_img_sizer()

        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2:
                self.ImgManager.set_count_per_action(
                    self.img_Sizer.GetCols()*self.img_Sizer.GetRows())

            # Destroy the window to avoid memory leaks
            try:
                for i in range(self.img_Sizer.ItemCount):
                    self.img_Sizer.Children[0].GetWindow().Destroy()
            except:
                pass

            # show img
            if self.ImgManager.max_action_num > 1:
                self.m_slider1.SetMax(self.ImgManager.max_action_num-1)
            img_list = self.ImgManager.get_flist()
            if len(img_list) != 0:
                i = 0
                for img_path in img_list:
                    m_panel1 = wx.Panel(self.m_scrolledWindow1, wx.ID_ANY,
                                        wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
                    if Path(img_path).is_file():
                        image = self.ImgManager.load_img(img_path)
                        size = image.GetWidth(), image.GetHeight()
                        m_panel1.SetSize(size)
                        wx.StaticBitmap(parent=m_panel1, bitmap=image)
                        if orientation == "Horizontal":
                            col = i % self.img_Sizer.GetCols()
                            row = int((i-col)/self.img_Sizer.GetCols())
                        elif orientation == "Vertical":
                            row = i % self.img_Sizer.GetRows()
                            col = int((i-row)/self.img_Sizer.GetRows())
                        self.img_Sizer.Add(m_panel1, pos=(row, col), flag=wx.EXPAND |
                                           wx.ALL, border=5)
                        if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                            self.SetStatusText_(
                                ["-1", str(self.ImgManager.action_count), str(self.ImgManager.name_list[self.ImgManager.action_count]), "-1"])
                        elif self.ImgManager.type == 2:
                            try:
                                self.SetStatusText_(
                                    ["-1", str(self.ImgManager.action_count), str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_count+self.ImgManager.count_per_action-1]), "-1"])
                            except:
                                self.SetStatusText_(
                                    ["-1", str(self.ImgManager.action_count), str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_num-1]), "-1"])
                    else:
                        self.SetStatusText_(
                            ["-1", str(self.ImgManager.action_count), "***Error: check image format and name***", "-1"])
                    i += 1
                # self.Size = wx.Size(wx.DisplaySize())
                if self.auto_layout.Value:
                    if self.img_Sizer.MinSize[0]+50 < self.width:
                        w = self.width
                    else:
                        w = self.img_Sizer.MinSize[0]+50
                    h = self.img_Sizer.MinSize[1]+250
                    self.Size = wx.Size((w, h))
                self.Layout()
                self.Refresh()
            else:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: setting***", "-1"])

    def about_gui(self, event):
        about = About(None)
        about.Show(True)

    def create_ImgManager(self, input_path, type):
        return ImgManager(input_path, type=type)
