import wx
from select_image_gui import SelectImgFrameGui
import numpy as np
import os
from PIL import Image


class SelectImgFrame (SelectImgFrameGui):

    def __init__(self, parent, UpdateUI):
        super().__init__(parent)
        self.UpdateUI = UpdateUI

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
        self.count_img = 0
        self.img_num = 0
        self.input_paths = []
        self.out_path_str = ""
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.m_scrolledWindow1.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.width = self.Size[0]

    def Close(self, event):
        self.UpdateUI(-1)

    def next_img(self, event):
        self.SetStatusText_(["Next", "-1", "-1", "-1"])
        if self.img_num != 0:
            if self.count_img < self.img_num-1:
                self.count_img += 1
                self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the output directory***", "-1"])

    def last_img(self, event):
        self.SetStatusText_(["Last", "-1", "-1", "-1"])
        if self.img_num != 0:
            if self.count_img > 0:
                self.count_img -= 1
                self.show_img()
            else:
                self.SetStatusText_(
                    ["-1", str(self.count_img)+' image', str(self.img_name[self.count_img]), "-1"])
        else:
            self.SetStatusText_(
                ["-1",  "", "***Error: First, need to select the output directory***", "-1"])

    def skip_to_n_img(self, event):
        self.count_img = self.m_slider1.GetValue()
        self.slider_value.SetLabel(str(self.count_img))
        if self.img_num != 0:
            if not (self.count_img < self.img_num-1):
                self.SetStatusText_(
                    ["-1", str(self.count_img)+' image', str(self.img_name[self.count_img]), "-1"])
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the output directory***", "-1"])

    def save(self):
        check = []
        check_1 = []
        if os.path.isdir(self.out_path_str):
            dir_name = []
            if self.m_choice1.GetSelection() == 0:
                for path in self.input_paths:
                    dir_name.append(path.split("/")[-1])
                if len(dir_name) == len(set(dir_name)):
                    pass
                else:
                    dir_name = [dir_name[0]+str(i)
                                for i in range(len(dir_name))]
            elif self.m_choice1.GetSelection() == 1:
                dir_name = ["stitch_images" for i in range(
                    len(self.input_paths))]
            else:
                for path in self.input_paths:
                    dir_name.append(path.split("/")[-1])
                if len(dir_name) == len(set(dir_name)):
                    pass
                else:
                    dir_name = [dir_name[0]+str(i)
                                for i in range(len(dir_name))]
                dir_name.append("stitch_images")
            if self.m_choice1.GetSelection() == 0:
                for i in range(len(dir_name)):
                    if not os.path.exists(os.path.join(self.out_path_str, dir_name[i])):
                        os.system(
                            "mkdir "+os.path.join(self.out_path_str, dir_name[i]))

                        f_path = os.path.join(
                            self.input_paths[i], self.img_name[self.count_img])
                        if os.path.isfile(f_path):
                            check.append(os.system("cp "+f_path+" " + os.path.join(
                                os.path.join(self.out_path_str, dir_name[i]), str(self.img_name[self.count_img]))))
                        else:
                            check.append(1)
            elif self.m_choice1.GetSelection() == 1:
                if not os.path.exists(os.path.join(self.out_path_str, dir_name[-1])):
                    os.system(
                        "mkdir "+os.path.join(self.out_path_str, dir_name[-1]))
                check_1.append(self.stitch_images(dir_name[-1]))
            else:
                for i in range(len(dir_name)-1):
                    if not os.path.exists(os.path.join(self.out_path_str, dir_name[i])):
                        os.system(
                            "mkdir "+os.path.join(self.out_path_str, dir_name[i]))

                        f_path = os.path.join(
                            self.input_paths[i], self.img_name[self.count_img])
                        if os.path.isfile(f_path):
                            check.append(os.system("cp "+f_path+" " + os.path.join(
                                os.path.join(self.out_path_str, dir_name[i]), str(self.img_name[self.count_img]))))
                        else:
                            check.append(1)
                if not os.path.exists(os.path.join(self.out_path_str, dir_name[-1])):
                    os.system(
                        "mkdir "+os.path.join(self.out_path_str, dir_name[-1]))
                check_1.append(self.stitch_images(dir_name[-1]))

            if sum(check) == 0:
                self.SetStatusText_(
                    ["Save", str(self.count_img)+' image', "Save "+str(self.img_name[self.count_img]) + " success!", "-1"])
            else:
                self.SetStatusText_(
                    ["-1", str(self.count_img)+' image', "***Error: "+str(self.img_name[self.count_img]) + ", the number of img in sub folders is different***", "-1"])
            if sum(check_1) != 0:
                self.SetStatusText_(
                    ["-1", str(self.count_img)+' image', "***"+str(self.img_name[self.count_img]) + ". Error during stitching images***", "-1"])
        else:
            self.SetStatusText_(
                ["-1", "-1", "***Error: First, need to select the output directory***", "-1"])

    def save_img(self, event):
        self.set_img_sizer()
        if self.auto_save_all.Value:
            last_count_img = self.count_img
            self.count_img = 0
            for i in range(self.img_num):
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.img_name[self.count_img])+", saving img***", "-1"])
                self.save()
                self.count_img += 1
            self.count_img = last_count_img
            self.SetStatusText_(
                ["-1", "-1", "***Finish***", "-1"])
        else:
            self.save()

    def refresh(self, event):
        if self.checkBox_orientation.Value:
            self.show_img(orientation="Vertical")
        else:
            self.show_img(orientation="Horizontal")

    def stitch_images(self, dir_name):
        try:
            dir_num = len(self.input_paths)
            f_path_input = []
            img_list = []
            f_path_output = os.path.join(os.path.join(
                self.out_path_str, dir_name), str(self.img_name[self.count_img]))
            for i in range(dir_num):
                f_path_input.append(os.path.join(
                    self.input_paths[i], self.img_name[self.count_img]))
                img_list.append(Image.open(f_path_input[-1]))
            num_per_img = int(self.num_per_img.GetLineText(0))
            gap = 5
            width, height = img_list[0].size

            if self.checkBox_orientation.Value:
                img_num_per_row = self.img_Sizer.GetCols()
                img_num_per_column = int(self.img_Sizer.GetRows()/num_per_img)
                img = Image.new('RGB', (width * img_num_per_row, height *
                                        img_num_per_column * num_per_img + gap*(img_num_per_column-1)))

                for ix in range(img_num_per_row):
                    x = ix * width + gap * ix

                    for iyy in range(img_num_per_column):
                        for iy in range(num_per_img):
                            y = (iyy*num_per_img+iy) * height+gap * iyy
                            if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(img_list):
                                im = img_list[ix*(img_num_per_column *
                                                  num_per_img)+iyy*num_per_img+iy]
                                img.paste(im, (x, y))
            else:
                img_num_per_row = int(self.img_Sizer.GetCols()/num_per_img)
                img_num_per_column = self.img_Sizer.GetRows()   
                img = Image.new('RGB', (width * img_num_per_row * num_per_img + gap * (img_num_per_row-1),
                                        height * img_num_per_column))

                for iy in range(img_num_per_column):

                    y = iy * height + gap * iy

                    for ixx in range(img_num_per_row):
                        for ix in range(num_per_img):
                            x = (ixx*num_per_img+ix) * width+gap * ixx
                            if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(img_list):
                                im = img_list[iy*(img_num_per_row *
                                                  num_per_img)+ixx*num_per_img+ix]
                                img.paste(im, (x, y))

            img.save(f_path_output)
        except:
            return 1
        else:
            return 0

    def one_dir_input_path(self, event):
        self.input_paths = []
        self.SetStatusText_(["input_path", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.input_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.input_path_str, 2)
            i = 0

            for root, dirs, files in os.walk(self.input_path_str):
                if i == 0:
                    dirname = dirs
                    root_path = root
                else:
                    break
                i += 1
            dirname = np.sort(dirname)
            for dir in dirname:
                self.input_paths.append(os.path.join(root_path, dir))
            self.count_img = 0
            self.show_img_init()
            self.show_img()

    def detached_dir_input_path(self, event):
        self.input_paths = []
        self.SetStatusText_(["input_path", "", "", "-1"])
        self.UpdateUI(1)
        self.count_img = 0

    def out_path(self, event):
        if len(self.img_name) != 0:
            self.SetStatusText_(
                ["out_path", str(self.count_img)+' image', self.img_name[self.count_img], "-1"])
        else:
            self.SetStatusText_(["out_path", "-1", "-1", "-1"])
        dlg = wx.DirDialog(None, "Choose out directory", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.out_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.out_path_str, 3)

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

    def show_img_init(self):
        self.img_name = np.sort(os.listdir(self.input_paths[0]))

        self.img_num = len(self.img_name)
        self.m_slider1.SetMax(self.img_num-1)
        format_group = ["png", "jpg", "jpeg", "bmp", "tif"]
        k = 0
        for i in range(len(self.img_name)):
            if not (self.img_name[i-k].split('.')[-1] in format_group) and i < len(self.img_name):
                self.img_name = np.delete(self.img_name, i-k)
                k += 1

    def load_img(self, f_path):
        img_name_format = f_path.split('/')[-1].split('.')[-1]
        if img_name_format == "png":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        elif img_name_format == "jpeg":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        elif img_name_format == "jpg":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        elif img_name_format == "bmp":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_BMP).ConvertToBitmap()
        elif img_name_format == "tif":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_TIFF).ConvertToBitmap()
        return image

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
            return True

    def show_img(self, orientation="Horizontal"):
        self.m_slider1.SetValue(self.count_img)
        self.slider_value.SetLabel(str(self.count_img))
        self.m_slider1.Update()
        dir_num = len(self.input_paths)
        if self.set_img_sizer():
            try:
                for i in range(self.img_Sizer.ItemCount):
                    # Destroy the window to avoid memory leaks
                    self.img_Sizer.Children[0].GetWindow().Destroy()
            except:
                pass
            for i in range(dir_num):
                m_panel1 = wx.Panel(self.m_scrolledWindow1, wx.ID_ANY,
                                    wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
                f_path = os.path.join(
                    self.input_paths[i], self.img_name[self.count_img])
                if os.path.isfile(f_path):
                    image = self.load_img(f_path)
                    size = image.GetWidth(), image.GetHeight()
                    m_panel1.SetSize(size)
                    wx.StaticBitmap(parent=m_panel1, bitmap=image)
                    if orientation == "Horizontal":
                        col = i % self.img_Sizer.GetCols()
                        row = int((i-col)/self.img_Sizer.GetCols())
                    else:
                        row = i % self.img_Sizer.GetRows()
                        col = int((i-row)/self.img_Sizer.GetRows())
                    self.img_Sizer.Add(m_panel1, pos=(row, col), flag=wx.EXPAND |
                                       wx.ALL, border=5)
                    self.SetStatusText_(
                        ["-1", str(self.count_img)+' image', str(self.img_name[self.count_img]), "-1"])
                else:
                    self.SetStatusText_(
                        ["-1", str(self.count_img)+' image', "***Error: "+str(self.img_name[self.count_img]) + ", the number of img in sub folders is different***", "-1"])

            # self.Size = wx.Size(wx.DisplaySize())
            if self.auto_layout.Value:
                if self.img_Sizer.MinSize[0]+50 < self.width:
                    w = self.width
                else:
                    w = self.img_Sizer.MinSize[0]+50
                h = self.img_Sizer.MinSize[1]+250
                self.Size = wx.Size((w, h))
            self.Layout()
