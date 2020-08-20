import wx
from mulimg_viewer_gui import MulimgViewerGui
import numpy as np
import os
from about import About
from shutil import copyfile
from pathlib import Path
from utils import ImgManager
from PIL import Image


class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type):
        super().__init__(parent)
        self.ImgManager = self.create_ImgManager(None, -1)
        self.UpdateUI = UpdateUI
        self.get_type = get_type

        acceltbl = wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_UP,
                                         self.menu_up.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DOWN,
                                         self.menu_down.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_RIGHT,
                                         self.menu_right.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_LEFT,
                                         self.menu_left.GetId())
                                        ])
        self.SetAcceleratorTable(acceltbl)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.Close)

        # parameter
        self.input_paths = []
        self.out_path_str = ""
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.width = self.Size[0]
        self.img_size = [-1, -1]

    def frame_resize(self, event):
        self.auto_layout(mode=2)

    def open_all_img(self, event):
        input_mode = self.choice_input_mode.GetSelection()
        if input_mode == 0:
            self.one_dir_mul_img(event)
        elif input_mode == 1:
            self.one_dir_mul_dir_auto(event)
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)

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
        self.ImgManager.set_action_count(self.slider_img.GetValue())
        self.slider_value.SetLabel(str(self.ImgManager.action_count))
        if self.ImgManager.img_num != 0:
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the output directory***", "-1"])

    def save_img(self, event):
        layout_params = self.set_img_layout()
        if layout_params != False:
            self.ImgManager.layout_params = layout_params
        type_ = self.choice_output.Items[self.choice_output.GetSelection()]
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
        self.show_img()

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["input_path", "", "", "-1"])
        dlg = wx.DirDialog(None, "Parallel auto choose input directory", "",
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
        self.SetStatusText_(
            ["Sequential choose input directory", "", "", "-1"])
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
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def background_alpha(self, event):
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_alpha = self.background_slider.GetValue()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def foreground_alpha(self, event):
        self.ImgManager.img_alpha = self.foreground_slider.GetValue()

    def up_img(self, event):
        size = self.scrolledWindow_img.GetSize()
        self.position[0] = int(
            self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if self.position[1] > 0:
            self.position[1] -= 1
        self.scrolledWindow_img.Scroll(
            self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["up",  "-1", "-1", "-1"])

    def down_img(self, event):
        size = self.scrolledWindow_img.GetSize()
        self.position[0] = int(
            self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if (self.position[1]-1)*self.Uint[1] < size[1]:
            self.position[1] += 1
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        else:
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], size[1])
        self.SetStatusText_(["down",  "-1", "-1", "-1"])

    def right_img(self, event):
        size = self.scrolledWindow_img.GetSize()
        self.position[0] = int(
            self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if (self.position[0]-1)*self.Uint[0] < size[0]:
            self.position[0] += 1
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        else:
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], size[0])
        self.SetStatusText_(["right",  "-1", "-1", "-1"])

    def left_img(self, event):
        size = self.scrolledWindow_img.GetSize()
        self.position[0] = int(
            self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
        self.position[1] = int(
            self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
        if self.position[0] > 0:
            self.position[0] -= 1
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.m_statusBar1.SetStatusText(texts[i], i)

    def set_img_layout(self):
        try:
            num_per_img = int(self.num_per_img.GetLineText(0))
            if num_per_img == -1:
                row_col = self.ImgManager.layout_advice()
                self.img_num_per_row.SetValue(str(row_col[0]))
                self.img_num_per_column.SetValue(str(row_col[1]))
                num_per_img = 1

            img_num_per_row = int(self.img_num_per_row.GetLineText(0))
            img_num_per_column = int(self.img_num_per_column.GetLineText(0))

            gap = self.gap.GetLineText(0).split(',')
            gap = [int(x) for x in gap]

            show_scale = self.show_scale.GetLineText(0).split(',')
            show_scale = [float(x) for x in show_scale]

            output_scale = self.output_scale.GetLineText(0).split(',')
            output_scale = [float(x) for x in output_scale]

            img_resolution = self.img_resolution.GetLineText(0).split(',')
            img_resolution = [int(x) for x in img_resolution]
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [img_num_per_row, num_per_img, img_num_per_column, gap, show_scale, output_scale, img_resolution, self.checkBox_orientation.Value]

    def show_img(self):
        self.slider_img.SetValue(self.ImgManager.action_count)
        self.slider_value.SetLabel(str(self.ImgManager.action_count))
        layout_params = self.set_img_layout()

        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2:
                self.ImgManager.set_count_per_action(
                    layout_params[0]*layout_params[1]*layout_params[2])

            # # Destroy the window to avoid memory leaks
            # try:
            #     for i in range(self.img_Sizer.ItemCount):
            #         self.img_Sizer.Children[0].GetWindow().Destroy()
            # except:
            #     pass
            try:
                self.img_last.Destroy()
            except:
                pass

            # show img
            self.SetStatusText_(
                ["-1", "-1", "strat stitch image", "-1"])
            if self.ImgManager.max_action_num > 1:
                self.slider_img.SetMax(self.ImgManager.max_action_num-1)
            self.ImgManager.get_flist()
            flag = self.ImgManager.stitch_images()
            if flag != 1:
                bmp = self.ImgManager.resize(
                    self.ImgManager.img, layout_params[4])
                self.img_size = bmp.size
                bmp = self.ImgManager.PIL2wx(bmp)

                self.img_panel.SetSize(self.img_size)
                self.img_last = wx.StaticBitmap(parent=self.img_panel,
                                                bitmap=bmp)
                self.auto_layout()
            # status
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.action_count]), "-1"])
            elif self.ImgManager.type == 2:
                try:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_count+self.ImgManager.count_per_action-1]), "-1"])
                except:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_num-1]), "-1"])
            if flag == 1:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count)+' image', "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])

    def auto_layout(self, mode=1):
        if self.img_size[0] == -1 or self.img_size[1] == -1:
            pass
        else:
            # Auto Layout
            self.displaySize = wx.Size(wx.DisplaySize())
            if self.auto_layout_check.Value:
                if self.img_size[0]+300 < self.width:
                    w = self.width
                elif self.img_size[0]+300 > self.displaySize[0]:
                    w = self.displaySize[0]
                else:
                    w = self.img_size[0]+300
                if self.img_size[1]+200 < self.displaySize[1]:
                    h = self.img_size[1]+200
                else:
                    h = self.displaySize[1]
                if mode == 1:
                    self.Size = wx.Size((w, h))

                self.scrolledWindow_img.SetMinSize(
                    wx.Size((self.Size[0]-250, self.Size[1]-150)))

        self.Layout()
        self.Refresh()

    def about_gui(self, event):
        about = About(None)
        about.Show(True)

    def create_ImgManager(self, input_path, type):
        self.ImgManager = ImgManager(input_path, type=type)
        self.colour_change([])
        return self.ImgManager

    def change_img_stitch_mode(self, event):
        self.ImgManager.img_stitch_mode = self.choice_normalized_size.GetSelection()
