import wx
from mulimg_viewer_gui import MulimgViewerGui
import numpy as np
import os
from about import About
from shutil import copyfile
from pathlib import Path
from utils import ImgManager
from PIL import Image
from index_table import IndexTable


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
        self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 1050
        self.height = 600
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1

    def OnPaint(self, event):
        if self.magnifier.Value != False and self.x_0 != -1 and len(self.img_panel.Children) != 0:
            dc = wx.PaintDC(self.img_panel.Children[0])
            pen = wx.Pen(wx.Colour(255, 0, 0))
            dc.SetPen(pen)
            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0), wx.TRANSPARENT))
            for xy in self.ImgManager.xy_grid:
                dc.DrawRectangle(self.x_0+xy[0], self.y_0+xy[1], self.x -
                                 self.x_0, self.y-self.y_0)

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
            self.show_img_init()
            self.ImgManager.add()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input directory***", "-1"])

    def last_img(self, event):
        self.SetStatusText_(["Last", "-1", "-1", "-1"])
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.subtract()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1",  "", "***Error: First, need to select the input directory***", "-1"])

    def skip_to_n_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.set_action_count(self.slider_img.GetValue())
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input directory***", "-1"])

    def slider_value_change(self, event):
        try:
            value = int(self.slider_value.GetValue())
        except:
            self.slider_value.SetValue(str(self.ImgManager.action_count))
        else:
            if self.ImgManager.img_num != 0:
                self.show_img_init()
                self.ImgManager.set_action_count(value)
                self.show_img()
                self
            else:
                self.SetStatusText_(
                    ["-1", "", "***Error: First, need to select the input directory***", "-1"])

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
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input directory***", "-1"])

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["input_path", "", "", "-1"])
        dlg = wx.DirDialog(None, "Parallel auto choose input directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager = self.create_ImgManager(dlg.GetPath(), 0)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["input_path", "", "", "-1"])
        self.UpdateUI(1)

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input directory", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager = self.create_ImgManager(dlg.GetPath(), 2)
            self.show_img_init()
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

    def show_img_init(self):
        layout_params = self.set_img_layout()
        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2:
                self.ImgManager.set_count_per_action(
                    layout_params[0]*layout_params[1]*layout_params[2])

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

            magnifier_scale = self.magnifier_scale.GetLineText(0).split(',')
            magnifier_scale = [float(x) for x in magnifier_scale]
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [img_num_per_row, num_per_img, img_num_per_column, gap, show_scale, output_scale, img_resolution, 1 if self.magnifier.Value else 0, magnifier_scale, self.checkBox_orientation.Value]

    def select_point_release(self, event):
        if self.magnifier.Value != False:
            self.start_flag = 0
            self.refresh(event)

    def select_point(self, event):
        if self.magnifier.Value != False:
            x_0, y_0 = event.GetPosition()
            self.x_0 = x_0
            self.y_0 = y_0
            self.x = x_0
            self.y = y_0
            self.start_flag = 1

    def point_move(self, event):
        # https://stackoverflow.com/questions/57342753/how-to-select-a-rectangle-of-the-screen-to-capture-by-dragging-mouse-on-transpar
        if self.magnifier.Value != False and self.start_flag == 1 and self.x_0 < self.ImgManager.img_resolution[0] and self.y_0 < self.ImgManager.img_resolution[1]:
            x, y = event.GetPosition()
            if x < self.ImgManager.img_resolution[0] and y < self.ImgManager.img_resolution[1]:
                self.x = x
                self.y = y
            elif x > self.ImgManager.img_resolution[0] and y > self.ImgManager.img_resolution[1]:
                self.x = self.ImgManager.img_resolution[0]
                self.y = self.ImgManager.img_resolution[1]
            elif x > self.ImgManager.img_resolution[0]:
                self.x = self.ImgManager.img_resolution[0]
                self.y = y
            elif y > self.ImgManager.img_resolution[1]:
                self.x = x
                self.y = self.ImgManager.img_resolution[1]

            self.Refresh()

    def magnifier_draw(self, event):
        self.start_flag = 0
        if self.magnifier.Value != False:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def show_img(self):
        # check layout_params change
        try:
            if self.layout_params_old != self.ImgManager.layout_params[0:3]:
                action_count = self.ImgManager.action_count
                self.ImgManager = self.create_ImgManager(
                    self.ImgManager.input_path, self.ImgManager.type)
                self.show_img_init()
                self.ImgManager.set_action_count(action_count)
                self.index_table.show_id_table(
                    self.ImgManager.name_list, self.ImgManager.layout_params)
        except:
            pass

        self.layout_params_old = self.ImgManager.layout_params
        self.slider_img.SetValue(self.ImgManager.action_count)
        self.slider_value.SetValue(str(self.ImgManager.action_count))
        self.slider_value_max.SetLabel(
            str(self.ImgManager.max_action_num-1))

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
        if self.ImgManager.max_action_num > 0:
            self.slider_img.SetMax(self.ImgManager.max_action_num-1)
            self.ImgManager.get_flist()
            flag = self.ImgManager.stitch_images(
                (self.x_0, self.y_0, self.x, self.y))
            if flag != 1:
                bmp = self.ImgManager.resize(
                    self.ImgManager.img, self.ImgManager.layout_params[4])
                self.img_size = bmp.size
                bmp = self.ImgManager.PIL2wx(bmp)

                self.img_panel.SetSize(
                    wx.Size(self.img_size[0]+100, self.img_size[1]+100))
                self.img_last = wx.StaticBitmap(parent=self.img_panel,
                                                bitmap=bmp)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_DOWN, self.select_point)
                self.img_panel.Children[0].Bind(wx.EVT_MOTION, self.point_move)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_UP, self.select_point_release)

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
        else:
            self.SetStatusText_(
                ["-1", "-1", "***Error: no image in this dir! Maybe you can choose parallel mode!***", "-1"])

        self.auto_layout()

    def auto_layout(self, mode=1):
        # Auto Layout
        self.displaySize = wx.Size(wx.DisplaySize())
        if self.auto_layout_check.Value:
            if mode == 1:
                if self.img_size[0] < self.width:
                    if self.img_size[0]+300 < self.width:
                        w = self.width
                    else:
                        w = self.img_size[0]+300
                elif self.img_size[0]+300 > self.displaySize[0]:
                    w = self.displaySize[0]
                else:
                    w = self.img_size[0]+300

                if self.img_size[1] < self.height:
                    if self.img_size[1]+200 < self.height:
                        h = self.height
                    else:
                        h = self.img_size[1]+200
                elif self.img_size[1]+200 > self.displaySize[1]:
                    h = self.displaySize[1]
                else:
                    h = self.img_size[1]+200
                self.Size = wx.Size((w, h))

            self.scrolledWindow_img.SetMinSize(
                wx.Size((self.Size[0]-250, self.Size[1]-150)))

        self.Layout()
        self.Refresh()

    def about_gui(self, event):
        about = About(None)
        about.Show(True)

    def index_table_gui(self, event):
        if self.ImgManager.img_num != 0:
            self.index_table = IndexTable(
                None, self.ImgManager.name_list, self.ImgManager.layout_params)
            self.index_table.Show(True)
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input directory***", "-1"])

    def create_ImgManager(self, input_path, type):
        self.ImgManager = ImgManager(input_path, type=type)
        self.colour_change([])
        return self.ImgManager

    def change_img_stitch_mode(self, event):
        self.ImgManager.img_stitch_mode = self.choice_normalized_size.GetSelection()
