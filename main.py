import wx
from wx.core import App
from main_gui import MulimgViewerGui
import numpy as np
from about import About
from utils_img import ImgManager
from index_table import IndexTable
from pathlib import Path
import copy
from utils import get_resource_path


class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type):
        super().__init__(parent)
        self.create_ImgManager()
        self.UpdateUI = UpdateUI
        self.get_type = get_type

        acceltbl = wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_UP,
                                         self.menu_up.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DOWN,
                                         self.menu_down.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_RIGHT,
                                         self.menu_right.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_LEFT,
                                         self.menu_left.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DELETE,
                                         self.menu_delete_box.GetId())
                                        ])
        self.SetAcceleratorTable(acceltbl)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 950
        self.height = 600
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1
        self.color_list = []
        self.box_id = -1
        self.xy_magnifier = []
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.ico'), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.m_statusBar1.SetStatusWidths([-2, -1, -4, -4])
        self.set_title_font()

    def set_title_font(self):
        font_path = Path("font")/"using"
        font_path = Path(get_resource_path(str(font_path)))
        files_name = [f.stem for f in font_path.iterdir()]
        for file_name in files_name:
            file_name = file_name.split("_", 1)[1]
            file_name = file_name.replace("-", " ")
            self.title_font.Append(file_name)
        self.title_font.SetSelection(0)
        self.font_paths = [str(f) for f in font_path.iterdir()]

    def frame_resize(self, event):
        self.auto_layout(frame_resize=True)

    def open_all_img(self, event):
        input_mode = self.choice_input_mode.GetSelection()
        if input_mode == 0:
            self.one_dir_mul_img(event)
        elif input_mode == 1:
            self.one_dir_mul_dir_auto(event)
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)
        elif input_mode == 3:
            self.onefilelist(event)

    def close(self, event):
        if self.get_type() == -1:
            self.Destroy()
        else:
            self.UpdateUI(-1)

    def next_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.add()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def last_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.subtract()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1",  "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Last", "-1", "-1", "-1"])

    def skip_to_n_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.set_action_count(self.slider_img.GetValue())
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])

        self.SetStatusText_(["Skip", "-1", "-1", "-1"])

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
                    ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Skip", "-1", "-1", "-1"])

    def save_img(self, event):
        layout_params = self.set_img_layout()
        if layout_params != False:
            self.ImgManager.layout_params = layout_params
        type_ = self.choice_output.GetSelection()
        if self.auto_save_all.Value:
            last_count_img = self.ImgManager.action_count
            self.ImgManager.set_action_count(0)
            if Path(self.out_path_str).is_dir():
                continue_ = True
            else:
                continue_ = False
            if continue_:
                for i in range(self.ImgManager.max_action_num):
                    self.SetStatusText_(
                        ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img***", "-1"])
                    self.ImgManager.get_flist()
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.add()
                self.ImgManager.set_action_count(last_count_img)
                self.SetStatusText_(
                    ["-1", "-1", "***Finish***", "-1"])
            else:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
        else:
            try:
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img...***", "-1"])
            except:
                pass
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            self.refresh(event)
            if flag == 0:
                self.SetStatusText_(
                    ["Save", str(self.ImgManager.action_count), "Save success for "+str(self.ImgManager.name_list[self.ImgManager.action_count])+"!", "-1"])
            elif flag == 1:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
            elif flag == 2:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            elif flag == 3:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", the number of img in sub folders is different***", "-1"])
            elif flag == 4:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: No magnification box, the magnified image should not be saved***", "-1"])
        self.SetStatusText_(["Save", "-1", "-1", "-1"])

    def refresh(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.show_img()
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), 0)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(1)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        try:
            if self.ImgManager.type == 1:
                input_path = self.ImgManager.input_path
            else:
                input_path = None
        except:
            input_path = None
        self.UpdateUI(1, input_path)
        self.choice_input_mode.SetSelection(2)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), 2)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])

    def onefilelist(self, event):
        self.SetStatusText_(["Choose the File List", "", "", "-1"])
        wildcard = "List file (*.txt; *.csv)|*.txt;*.csv|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), 3)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(3)
        self.SetStatusText_(["Choose the File List", "-1", "-1", "-1"])

    def input_flist_parallel_manual(self, event):
        wildcard = "List file (*.txt;)|*.txt;|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            with open(dlg.GetPath(), "r") as f:
                input_path = f.read().split('\n')
            self.ImgManager.init(input_path[0:-1], 1)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(2)

    def save_flist_parallel_manual(self, event):
        if self.out_path_str == "":
            self.SetStatusText_(
                ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
        else:
            try:
                np.savetxt(Path(self.out_path_str)/"input_flist_parallel_manual.txt",
                           self.ImgManager.input_path, fmt='%s')
            except:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select parallel manual***", "-1"])
            else:
                self.SetStatusText_(
                    ["-1", "-1", "Save" + str(Path(self.out_path_str)/"input_flist_parallel_manual.txt")+" success!", "-1"])

    def out_path(self, event):
        if len(self.img_name) != 0:
            self.SetStatusText_(
                ["Choose out dir", str(self.ImgManager.action_count), self.img_name[self.ImgManager.action_count], "-1"])
        else:
            self.SetStatusText_(["Choose out dir", "-1", "-1", "-1"])
        dlg = wx.DirDialog(None, "Choose out dir", "",
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

    def delete_box(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                self.xy_magnifier.pop(self.box_id)
                self.refresh(event)
                self.SetStatusText_(
                    ["delete "+str(self.box_id)+"-th box",  "-1", "-1", "-1"])
        else:
            self.xy_magnifier = []
            self.refresh(event)
            self.SetStatusText_(["delete all box",  "-1", "-1", "-1"])

    def up_img(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y-1
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[1] > 0:
                self.position[1] -= 1
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Up",  "-1", "-1", "-1"])

    def down_img(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y+1
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
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
        self.SetStatusText_(["Down",  "-1", "-1", "-1"])

    def right_img(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+1
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
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
        self.SetStatusText_(["Right",  "-1", "-1", "-1"])

    def left_img(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x-1
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[0] > 0:
                self.position[0] -= 1
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.m_statusBar1.SetStatusText(texts[i], i)

    def img_left_click(self, event):

        if self.magnifier.Value:
            x_0, y_0 = event.GetPosition()
            self.x_0 = x_0
            self.y_0 = y_0
            self.x = x_0
            self.y = y_0

        if self.select_img_box.Value:
            # select box
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([x, y])
            xy_grid = self.ImgManager.xy_grid[id]
            x = x-xy_grid[0]
            y = y-xy_grid[1]
            x_y_array = []
            for i in range(len(self.ImgManager.crop_points)):
                x_y_array.append(self.get_center_box(
                    self.ImgManager.crop_points[i]))
            x_y_array = np.array(x_y_array)
            dist = (x_y_array[:, 0]-x)**2+(x_y_array[:, 1]-y)**2
            self.box_id = np.array(dist).argmin()
            str_ = str(self.box_id)
            self.SetStatusText_(["Select "+str_+"-th box",  "-1", "-1", "-1"])

            self.start_flag = 0
        else:
            # magnifier
            if self.magnifier.Value:
                self.start_flag = 1
            else:
                self.start_flag = 0

            self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])

        # rotation
        if self.rotation.Value:
            x, y = event.GetPosition()
            self.ImgManager.rotate(self.get_img_id_from_point([x, y]))
            self.refresh(event)

            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])

    def img_left_dclick(self, event):
        if self.select_img_box.Value:
            pass
        else:
            self.start_flag = 0
            self.xy_magnifier = []
            self.color_list = []

    def img_left_move(self, event):
        # https://stackoverflow.com/questions/57342753/how-to-select-a-rectangle-of-the-screen-to-capture-by-dragging-mouse-on-transpar
        if self.magnifier.Value != False and self.start_flag == 1:
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            xy_limit = np.array(xy_grid) + \
                np.array(self.ImgManager.img_resolution_show)

            if self.x_0 < xy_limit[0] and self.y_0 < xy_limit[1]:

                if x < xy_limit[0] and y < xy_limit[1]:
                    self.x = x
                    self.y = y
                elif x > xy_limit[0] and y > xy_limit[1]:
                    self.x = xy_limit[0]
                    self.y = xy_limit[1]
                elif x > xy_limit[0]:
                    self.x = xy_limit[0]
                    self.y = y
                elif y > xy_limit[1]:
                    self.x = x
                    self.y = xy_limit[1]

    def img_left_release(self, event):
        if self.magnifier.Value != False:
            self.start_flag = 0

            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            x = self.x-xy_grid[0]
            y = self.y-xy_grid[1]
            x_0 = self.x_0 - xy_grid[0]
            y_0 = self.y_0 - xy_grid[1]

            width = np.abs(x-x_0)
            height = np.abs(y-y_0)
            if width > 5 and height > 5:
                self.xy_magnifier = []
                self.color_list.append(self.colourPicker_draw.GetColour())

                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.ImgManager.ImgF.sort_box_point(
                    [x_0, y_0, x, y], show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                self.xy_magnifier.append(points+show_scale)
                self.refresh(event)

    def img_right_click(self, event):
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        # magnifier
        if self.magnifier.Value:
            self.color_list.append(self.colourPicker_draw.GetColour())
            try:
                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.move_box_point(x, y, show_scale)
                self.xy_magnifier.append(points+show_scale)
            except:
                self.SetStatusText_(
                    ["-1",  "Drawing a box need click left mouse button!", "-1", "-1"])
        self.refresh(event)

        self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])

    def move_box_point(self, x, y, show_scale):
        x_0, y_0, x_1, y_1 = self.xy_magnifier[0][0:4]
        show_scale_old = self.xy_magnifier[0][4:6]
        scale = [show_scale[0]/show_scale_old[0],
                 show_scale[1]/show_scale_old[1]]
        x_0 = int(x_0*scale[0])
        x_1 = int(x_1*scale[0])
        y_0 = int(y_0*scale[1])
        y_1 = int(y_1*scale[1])
        x_center_old, y_center_old = self.get_center_box(
            [x_0, y_0, x_1, y_1])
        delta_x = x-x_center_old
        delta_y = y-y_center_old
        return self.ImgManager.ImgF.sort_box_point([x_0+delta_x, y_0+delta_y, x_1+delta_x, y_1+delta_y], self.ImgManager.img_resolution_origin, show_scale)

    def get_center_box(self, box, more=False):
        x_0, y_0, x_1, y_1 = box
        width = abs(x_0-x_1)
        height = abs(y_0-y_1)
        x_center_old = x_0+int((width)/2)
        y_center_old = y_0+int((height)/2)
        if more:
            return [x_center_old, y_center_old, width, height]
        else:
            return [x_center_old, y_center_old]

    def magnifier_fc(self, event):
        self.start_flag = 0
        if self.magnifier.Value != False:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
            if self.rotation.Value != False:
                self.rotation.Value = False
            self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def rotation_fc(self, event):
        if self.rotation.Value != False:
            self.SetCursor(wx.Cursor(wx.CURSOR_POINT_RIGHT))
            if self.magnifier.Value != False:
                self.magnifier.Value = False
            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def show_img_init(self):
        layout_params = self.set_img_layout()
        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                if self.parallel_sequential.Value:
                    self.ImgManager.set_count_per_action(layout_params[1])
                else:
                    self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                self.ImgManager.set_count_per_action(
                    layout_params[0]*layout_params[1]*layout_params[2])

    def set_img_layout(self):

        try:
            num_per_img = int(self.num_per_img.GetLineText(0))
            if num_per_img == -1:
                row_col = self.ImgManager.layout_advice()
                self.img_num_per_row.SetValue(str(row_col[1]))
                self.img_num_per_column.SetValue(str(row_col[0]))
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

            if self.checkBox_auto_draw_color.Value:
                # 10 colors built into the software
                color = [wx.Colour(217, 26, 42, 85/100*255),
                         wx.Colour(147, 81, 166, 65/100*255),
                         wx.Colour(85, 166, 73, 65/100*255),
                         wx.Colour(242, 229, 48, 95/100*255),
                         wx.Colour(242, 116, 5, 95/100*255),
                         wx.Colour(242, 201, 224, 95/100*255),
                         wx.Colour(36, 132, 191, 75/100*255),
                         wx.Colour(65, 166, 90, 65/100*255),
                         wx.Colour(214, 242, 206, 95/100*255),
                         wx.Colour(242, 163, 94, 95/100*255)]
            else:
                color = self.color_list

            line_width = int(self.line_width.GetLineText(0))

            title_setting = [self.title_auto.Value,                     # 0
                             self.title_show.Value,                     # 1
                             self.title_down_up.Value,                  # 2
                             self.title_show_parent.Value,              # 3
                             self.title_show_name.Value,                # 4
                             self.title_show_suffix.Value,              # 5
                             self.title_font.GetSelection(),            # 6
                             self.title_font_size.Value,                # 7
                             self.font_paths]                           # 8

            if title_setting[0]:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    # one_dir_mul_dir_auto / one_dir_mul_dir_manual
                    if self.parallel_sequential.Value:
                        title_setting[2:6] = [False, True, True, False]
                    else:
                        title_setting[2:6] = [False, True, False, False]
                elif self.ImgManager.type == 2:
                    # one_dir_mul_img
                    title_setting[2:6] = [False, False, True, False]
                elif self.ImgManager.type == 3:
                    # read file list from a list file
                    title_setting[2:6] = [False, True, True, False]

        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [img_num_per_row,                        # 0
                    num_per_img,                            # 1
                    img_num_per_column,                     # 2
                    gap,                                    # 3
                    show_scale,                             # 4
                    output_scale,                           # 5
                    img_resolution,                         # 6
                    1 if self.magnifier.Value else 0,       # 7
                    magnifier_scale,                        # 8
                    color,                                  # 9
                    line_width,                             # 10
                    self.move_file.Value,                   # 11
                    self.keep_magnifer_size.Value,          # 12
                    self.image_interp.GetSelection(),       # 13
                    self.show_box.Value,                    # 14
                    self.show_box_in_crop.Value,            # 15
                    self.show_original.Value,               # 16
                    title_setting,                          # 17
                    self.checkBox_orientation.Value]

    def show_img(self):
        # check layout_params change
        try:
            if self.layout_params_old[0:3] != self.ImgManager.layout_params[0:3]:
                action_count = self.ImgManager.action_count
                self.ImgManager.init(
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

        # Destroy the window to avoid memory leaks
        try:
            self.img_last.Destroy()
        except:
            pass

        # show img
        if self.ImgManager.max_action_num > 0:
            self.slider_img.SetMax(self.ImgManager.max_action_num-1)
            self.ImgManager.get_flist()

            flag = self.ImgManager.stitch_images(
                0, copy.deepcopy(self.xy_magnifier))
            if flag != 1:
                bmp = self.ImgManager.img
                self.img_size = bmp.size
                bmp = self.ImgManager.ImgF.PIL2wx(bmp)

                self.img_panel.SetSize(
                    wx.Size(self.img_size[0]+100, self.img_size[1]+100))
                self.img_last = wx.StaticBitmap(parent=self.img_panel,
                                                bitmap=bmp)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_DOWN, self.img_left_click)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_DCLICK, self.img_left_dclick)
                self.img_panel.Children[0].Bind(
                    wx.EVT_MOTION, self.img_left_move)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_UP, self.img_left_release)
                self.img_panel.Children[0].Bind(
                    wx.EVT_RIGHT_DOWN, self.img_right_click)

            # status
            if self.ImgManager.type == 2 or ((self.ImgManager.type == 0 or self.ImgManager.type == 1) and self.parallel_sequential.Value):
                try:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_count+self.ImgManager.count_per_action-1]), "-1"])
                except:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_num-1]), "-1"])
            else:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.action_count]), "-1"])

            if flag == 1:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
        else:
            self.SetStatusText_(
                ["-1", "-1", "***Error: no image in this dir! Maybe you can choose parallel mode!***", "-1"])
        self.auto_layout()
        self.SetStatusText_(["Stitch", "-1", "-1", "-1"])

    def auto_layout(self, frame_resize=False):
        # Auto Layout

        # Get current window size
        # self.displaySize = wx.Size(wx.DisplaySize()) # get main window size
        # Get current window id
        displays = (wx.Display(i) for i in range(wx.Display.GetCount()))
        displays_list = [display for display in displays]
        sizes = [display.GetGeometry().GetSize() for display in displays_list]
        screen_id = wx.Display.GetFromWindow(self)
        self.displaySize = sizes[screen_id]
        # leave some free space
        self.displaySize[0] = self.displaySize[0]-50
        self.displaySize[1] = self.displaySize[1]-50

        if self.auto_layout_check.Value and (not frame_resize):
            if self.img_size[0] < self.width:
                if self.img_size[0]+320 < self.width:
                    w = self.width
                else:
                    w = self.img_size[0]+320
            elif self.img_size[0]+320 > self.displaySize[0]:
                w = self.displaySize[0]
            else:
                w = self.img_size[0]+320

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

        self.scrolledWindow_set.SetMinSize(
            wx.Size((300, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0]-300, self.Size[1]-150)))

        self.Layout()
        self.Refresh()

    def about_gui(self, event):
        about = About(None)
        about.Show(True)

    def index_table_gui(self, event):
        if self.ImgManager.img_num != 0:
            if self.ImgManager.dataset_mode and self.out_path_str == "":
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
            else:
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt saving...", "-1"])
                if self.ImgManager.type == 3:
                    self.index_table = IndexTable(
                        None, self.ImgManager.path_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                else:
                    self.index_table = IndexTable(
                        None, self.ImgManager.name_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt save in "+self.out_path_str, "-1"])
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])

    def create_ImgManager(self):
        self.ImgManager = ImgManager()
        self.colour_change([])
        return self.ImgManager

    def change_img_stitch_mode(self, event):
        self.ImgManager.img_stitch_mode = self.choice_normalized_size.GetSelection()

    def get_img_id_from_point(self, xy):
        # get img_id from grid points
        xy_grid = np.array(self.ImgManager.xy_grid)
        xy_cur = np.array([xy])
        xy_cur = np.repeat(xy_cur, xy_grid.shape[0], axis=0)
        res_ = xy_cur - xy_grid
        id_list = []
        for i in range(xy_grid.shape[0]):
            if res_[i][0] >= 0 and res_[i][1] >= 0:
                id_list.append(i)
            else:
                id_list.append(0)
        return max(id_list)

    def title_down_up_func(self, event):
        if self.title_down_up.Value:
            self.title_down_up.SetLabel('Up  ')
        else:
            self.title_down_up.SetLabel('Down')
