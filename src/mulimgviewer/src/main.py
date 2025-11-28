import copy
import platform
import threading
from pathlib import Path

import numpy as np
import wx
from ..gui.main_gui import MulimgViewerGui

from .. import __version__ as VERSION
from .about import About
from .index_table import IndexTable
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
from .custom_func.main import get_available_algorithms
import json
import shutil
import os
import time
import shutil
import sys
import sys
import shutil
import importlib

class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type, default_path=None):
        self.shift_pressed=False
        super().__init__(parent)
        self.create_ImgManager()
        self.UpdateUI = UpdateUI
        self.get_type = get_type

        self.acceltbl = wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_UP,
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
        self.SetAcceleratorTable(self.acceltbl)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.img_name = []
        self.selected_img_id = 0
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.ID_status_display.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 1000
        self.height = 600
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1
        self.color_list = []
        self.box_id = -1
        self.xy_magnifier = []
        self.show_scale_proportion = 0
        self.key_status = {"shift_s": 0, "ctrl": 0, "alt": 0}
        self.indextablegui = None
        self.aboutgui = None
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)
        self.ID_status_display.SetStatusWidths([-2, -3, -4, -2])
        self.set_title_font()
        self.hidden_flag = 0
        self.button_open_all.SetToolTip("open")
        self.out_path_button.SetToolTip("out path")
        self.save_butoon.SetToolTip("save")
        self.left_arrow_button.SetToolTip("left arrow")
        self.right_arrow_button.SetToolTip("right arrow")
        self.refresh_button.SetToolTip("refresh")
        self.save_config_button.SetToolTip("save_configuration")
        self.magnifier.SetToolTip("magnifier")
        self.rotation.SetToolTip("rotation")
        self.flip.SetToolTip("flip")
        self.load_config_button.SetToolTip("load_configuration")
        self.reset_config_button.SetToolTip("reset_configuration")
        # Different platforms may need to adjust the width of the scrolledWindow_set
        sys_platform = platform.system()
        if sys_platform.find("Windows") >= 0:
            self.width_setting = 300
        elif sys_platform.find("Linux") >= 0:
            self.width_setting = 280
        elif sys_platform.find("Darwin") >= 0:
            self.width_setting = 350
        else:
            self.width_setting = 300

        self.SashPosition = self.width-self.width_setting
        self.m_splitter1.SetSashPosition(self.SashPosition)
        self.split_changing = False
        self.width_setting_ = self.width_setting

        # Draw color to box
        self.colourPicker_draw.Bind(
            wx.EVT_COLOURPICKER_CHANGED, self.draw_color_change)

        # Set ShowAllFunc and ShowCurrFunc mutually exclusive
        self.show_all_func.Bind(wx.EVT_CHECKBOX, self.on_show_all_func_changed)
        self.show_custom_func.Bind(wx.EVT_CHECKBOX, self.on_show_custom_func_changed)

        # Check the software version
        self.myEVT_MY_TEST = wx.NewEventType()
        EVT_MY_TEST = wx.PyEventBinder(self.myEVT_MY_TEST, 1)
        self.Bind(EVT_MY_TEST, self.EVT_MY_TEST_OnHandle)
        self.version = VERSION
        self.check_version()

        # open default path
        if default_path:
            try:
                self.ImgManager.init(default_path, type=2)  # one_dir_mul_img
                self.show_img_init()
                self.ImgManager.set_action_count(0)
                self.show_img(event=None)
            except:
                pass
        self.load_configuration( None , config_name="output.json")
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_right_click)
        self.custom_algorithms = []
        # self.refresh_algorithm_list()
        self.load_configuration( None , config_name="output.json")
        self._bind_settings_wheel_guard()

    def EVT_MY_TEST_OnHandle(self, event):
        self.about_gui(None, update=True, new_version=event.GetEventArgs())

    def check_version(self):
        t1 = threading.Thread(target=self.run, args=())
        t1.setDaemon(True)
        t1.start()

    def run(self):
        url = "https://api.github.com/repos/nachifur/MulimgViewer/releases/latest"
        try:
            # make request to be an optional depend
            import requests
            resp = requests.get(url)
            resp.encoding = 'UTF-8'
            if resp.status_code == 200:
                output = resp.json()
                # version is "rolling" means that it is run from source code
                if self.version == output["tag_name"] or self.version == "rolling":
                    # print("No need to update!")
                    pass
                else:
                    # print(output["tag_name"])
                    # print("Need to update!")
                    evt = MyTestEvent(self.myEVT_MY_TEST)
                    evt.SetEventArgs(output["tag_name"])
                    wx.PostEvent(self, evt)
        except:
            pass

    def set_title_font(self):
        font_path = Path("font")/"using"
        font_path = Path(get_resource_path(str(font_path)))
        files_name = [f.stem for f in font_path.iterdir()]
        files_name = np.sort(np.array(files_name)).tolist()
        for file_name in files_name:
            file_name = file_name.split("_", 1)[1]
            file_name = file_name.replace("-", " ")
            self.title_font.Append(file_name)
        self.title_font.SetSelection(0)
        font_paths = [str(f) for f in font_path.iterdir()]
        self.font_paths = np.sort(np.array(font_paths)).tolist()

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
            self.show_img(event)
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def last_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.subtract()
            self.show_img(event)
        else:
            self.SetStatusText_(
                ["-1",  "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Last", "-1", "-1", "-1"])

    def skip_to_n_img(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.ImgManager.set_action_count(self.slider_img.GetValue())
            self.show_img(event)
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
                self.show_img(event)
            else:
                self.SetStatusText_(
                    ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Skip", "-1", "-1", "-1"])

    def save_img(self, event):
        type_ = self.choice_output.GetSelection()
        save_format = self.save_format.GetSelection()
        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 35:
                self.ImgManager.layout_params[35] = save_format
        if self.auto_save_all.Value:
            last_count_img = self.ImgManager.action_count
            self.ImgManager.set_action_count(0)
            if self.out_path_str != "" and Path(self.out_path_str).is_dir():
                continue_ = True
            else:
                continue_ = False
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            if continue_:
                for i in range(self.ImgManager.max_action_num):
                    self.SetStatusText_(
                        ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img***", "-1"])
                    self.ImgManager.get_flist()
                    if self.show_custom_func.Value:
                        self.ImgManager.layout_params[32] = True  # customfunc
                        self.ImgManager.save_img(self.out_path_str, type_)
                        self.ImgManager.layout_params[32] = False  # customfunc
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)
                    self.ImgManager.add()
                self.ImgManager.set_action_count(last_count_img)
                self.SetStatusText_(
                    ["-1", "-1", "***Finish***", "-1"])
        else:
            try:
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img...***", "-1"])
            except:
                pass
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

            if flag == 0:
                self.SetStatusText_(
                    ["Save", str(self.ImgManager.action_count), "Save success!", "-1"])
            elif flag == 1:
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            elif flag == 2:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            elif flag == 3:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", the number of img in sub folders is different***", "-1"])
            elif flag == 4:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: No magnification box, the magnified image can not be saved***", "-1"])
            elif flag == 5:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Save", "-1", "-1", "-1"])

    def refresh(self, event):
        if self.ImgManager.img_num != 0:
            self.show_img_init()
            self.show_img(event)
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(
                dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img(event)
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
        self.UpdateUI(1, input_path, self.parallel_to_sequential.Value)
        self.choice_input_mode.SetSelection(2)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        dlg = wx.DirDialog(None, "Choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), type=2)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img(event)
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
            self.ImgManager.init(dlg.GetPath(), type=3)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img(event)
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
            self.ImgManager.init(
                input_path[0:-1], type=1, parallel_to_sequential=self.parallel_to_sequential.Value)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img(event)
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
            self.ID_status_display.SetStatusText(self.out_path_str, 3)

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
        if len(self.xy_magnifier)==0:
            self.box_position.SetSelection(0)

    def up_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y-speed
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
                self.position[1] -= speed
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Up",  "-1", "-1", "-1"])

    def down_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y+speed
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
                self.position[1] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[1])
        self.SetStatusText_(["Down",  "-1", "-1", "-1"])

    def right_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+speed
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
                self.position[0] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[0])
        self.SetStatusText_(["Right",  "-1", "-1", "-1"])

    def left_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x-speed
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
                self.position[0] -= speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.ID_status_display.SetStatusText(texts[i], i)

    def update_status_bar_for_current_page(self, clicked_img_id=None):
        try:
            page_num = self.ImgManager.action_count if hasattr(self.ImgManager, 'action_count') else 0
            if self.ImgManager.type == 2:
                total_imgs = self.ImgManager.img_num
                img_index = self.ImgManager.action_count * self.ImgManager.count_per_action
                if clicked_img_id is not None:
                    img_index = img_index + clicked_img_id
                status_text = f"{img_index}-th/{total_imgs} img 0-th/1 dir"

            elif self.ImgManager.type in [0, 1]:
                if hasattr(self.ImgManager, 'get_dir_num'):
                    total_dirs = self.ImgManager.get_dir_num()
                else:
                    total_dirs = self.ImgManager.max_action_num if hasattr(self.ImgManager, 'max_action_num') else 0
                if self.parallel_sequential.Value:
                    # parallel_sequential
                    target_img_id = clicked_img_id if clicked_img_id is not None else 0
                    if hasattr(self, 'current_page_img_paths') and target_img_id < len(self.current_page_img_paths):
                        current_file_path = self.current_page_img_paths[target_img_id]
                        current_dir = os.path.dirname(current_file_path)

                        if os.path.exists(current_dir):
                            img_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
                            files_in_folder = sorted([
                                os.path.join(current_dir, f)
                                for f in os.listdir(current_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            actual_folder_img_count = len(files_in_folder)

                            if current_file_path in files_in_folder:
                                pos_in_folder = files_in_folder.index(current_file_path)
                            else:
                                pos_in_folder = 0
                            all_dirs = sorted(list(set(os.path.dirname(p) for p in self.ImgManager.flist)))
                            actual_folder_idx = all_dirs.index(current_dir) if current_dir in all_dirs else page_num
                        else:
                            pos_in_folder = 0
                            actual_folder_idx = page_num
                            img_cols = self.ImgManager.layout_params[1][1]
                            actual_folder_img_count = self.ImgManager.layout_params[1][0] * img_cols
                    else:
                        pos_in_folder = 0
                        actual_folder_idx = page_num
                        img_cols = self.ImgManager.layout_params[1][1]
                        actual_folder_img_count = self.ImgManager.layout_params[1][0] * img_cols
                    status_text = f"{pos_in_folder}-th/{actual_folder_img_count} img {actual_folder_idx}-th/{total_dirs} dir"

                elif self.parallel_to_sequential.Value:
                    # parallel_to_sequential
                    target_img_id = clicked_img_id if clicked_img_id is not None else 0
                    if hasattr(self, 'current_page_img_paths') and target_img_id < len(self.current_page_img_paths):
                        current_file_path = self.current_page_img_paths[target_img_id]
                        current_dir = os.path.dirname(current_file_path)
                        img_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
                        all_dirs_set = set()
                        old_action_count = self.ImgManager.action_count
                        for i in range(self.ImgManager.max_action_num):
                            try:
                                self.ImgManager.set_action_count(i)
                                self.ImgManager.get_flist()
                                all_dirs_set.update(os.path.dirname(p) for p in self.ImgManager.flist)
                            except:
                                pass
                        self.ImgManager.set_action_count(old_action_count)

                        all_dirs_global = sorted(list(all_dirs_set))
                        total_dirs = len(all_dirs_global)
                        actual_folder_idx = all_dirs_global.index(current_dir) if current_dir in all_dirs_global else 0
                        try:
                            files_in_folder = sorted([
                                os.path.join(current_dir, f)
                                for f in os.listdir(current_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            actual_folder_img_count = len(files_in_folder)
                            pos_in_folder = files_in_folder.index(current_file_path) if current_file_path in files_in_folder else 0
                        except:
                            actual_folder_img_count = 0
                            pos_in_folder = 0
                        status_text = f"{pos_in_folder}-th/{actual_folder_img_count} img {actual_folder_idx}-th/{total_dirs} dir"
                    else:
                        try:
                            self.ImgManager.get_flist()
                            if len(self.ImgManager.flist) > 0:
                                first_file_path = self.ImgManager.flist[0]
                                first_dir = os.path.dirname(first_file_path)

                                img_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
                                files_in_folder = sorted([
                                    os.path.join(first_dir, f)
                                    for f in os.listdir(first_dir)
                                    if Path(f).suffix.lower() in img_extensions
                                ])
                                pos_in_folder = files_in_folder.index(first_file_path) if first_file_path in files_in_folder else 0
                                total_imgs = len(files_in_folder)
                            else:
                                pos_in_folder = 0
                                total_imgs = 0
                        except:
                            pos_in_folder = 0
                            total_imgs = 0
                        status_text = f"{pos_in_folder}-th/{total_imgs} img {page_num}-th/{total_dirs} dir"
                else:
                    # parallel mode (do not check sequential)
                    if clicked_img_id is not None and hasattr(self.ImgManager, 'flist') and clicked_img_id < len(self.ImgManager.flist):
                        clicked_img_path = self.ImgManager.flist[clicked_img_id]
                        clicked_dir = os.path.dirname(clicked_img_path)
                        all_dirs = sorted(list(set(os.path.dirname(p) for p in self.ImgManager.flist)))
                        dir_index = all_dirs.index(clicked_dir) if clicked_dir in all_dirs else page_num
                        img_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
                        if os.path.exists(clicked_dir):
                            folder_images = sorted([
                                os.path.join(clicked_dir, f)
                                for f in os.listdir(clicked_dir)
                                if Path(f).suffix.lower() in img_extensions
                            ])
                            img_count_in_folder = len(folder_images)
                            img_pos_in_folder = folder_images.index(clicked_img_path) if clicked_img_path in folder_images else 0
                        else:
                            img_count_in_folder = 1
                            img_pos_in_folder = 0
                        status_text = f"{img_pos_in_folder}-th/{img_count_in_folder} img {dir_index}-th/{total_dirs} dir"
                    else:
                        total_pages = 0
                        if hasattr(self.ImgManager, 'max_action_num'):
                            total_pages = self.ImgManager.max_action_num
                        else:
                            total_pages = 0
                        status_text = f"{page_num}-th/{total_pages} img 0-th/{total_dirs} dir"

            elif self.ImgManager.type == 3:
                target_img_id = clicked_img_id if clicked_img_id is not None else 0
                img_index = self.ImgManager.action_count * self.ImgManager.count_per_action + target_img_id
                if hasattr(self.ImgManager, 'path_list'):
                    total_imgs = len(self.ImgManager.path_list)
                else:
                    total_imgs = 0

                status_text = f"{img_index}-th/{total_imgs} img 0-th/0 dir"
            else:
                status_text = "0-th/0 img 0-th/0 dir"

            self.ID_status_display.SetStatusText(status_text, 1)

        except:
            self.ID_status_display.SetStatusText("0-th/0 img 0-th/0 dir", 1)

    def img_left_click(self, event):

        click_status = "0-th/0 img 0-th/0 dir"

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
            self.selected_img_id = id
            xy_grid = self.ImgManager.xy_grid[id]
            x = x-xy_grid[0]
            y = y-xy_grid[1]
            x_y_array = []
            for i in range(len(self.ImgManager.crop_points)):
                x_y_array.append(self.get_center_box(
                    self.ImgManager.crop_points[i][0:4]))
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

            if self.magnifier.Value:
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])

        # rotation
        if self.rotation.Value:
            x, y = event.GetPosition()
            self.ImgManager.rotate(
                self.get_img_id_from_point([x, y], img=True))
            self.refresh(event)
            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])

        # flip
        if self.flip.Value:
            x, y = event.GetPosition()
            self.ImgManager.flip(self.get_img_id_from_point(
                [x, y], img=True), FLIP_TOP_BOTTOM=False)
            self.refresh(event)
            self.SetStatusText_(["Flip", "-1", "-1", "-1"])

        # focus img
        if self.indextablegui or self.aboutgui:
            pass
        else:
            self.img_panel.Children[0].SetFocus()

        x, y = event.GetPosition()
        clicked_img_id = self.get_img_id_from_point([x, y])

        self.update_status_bar_for_current_page(clicked_img_id)

    def img_left_dclick(self, event):
        if self.select_img_box.Value:
            pass
        else:
            self.start_flag = 0
            self.xy_magnifier = []
            self.color_list = []
            self.box_position.SetSelection(0)

    def img_left_move(self, event):
        # https://stackoverflow.com/questions/57342753/how-to-select-a-rectangle-of-the-screen-to-capture-by-dragging-mouse-on-transpar
        if self.magnifier.Value != False and self.start_flag == 1:
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([self.x_0, self.y_0])
            if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:

                xy_grid_array = np.array(self.ImgManager.xy_grid)
                xy_cur = np.array([[self.x_0, self.y_0]])
                xy_cur = np.repeat(xy_cur, xy_grid_array.shape[0], axis=0)
                res_ = xy_cur - xy_grid_array
                id_list = []
                for i in range(xy_grid_array.shape[0]):
                    if res_[i][0] >= 0 and res_[i][1] >= 0:
                        id_list.append(i)
                    else:
                        id_list.append(0)
                actual_grid_id = max(id_list)
                xy_grid = self.ImgManager.xy_grid[actual_grid_id]
            else:
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

        # show mouse position
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        RGBA = self.show_bmp_in_panel.getpixel((int(x), int(y)))
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        self.ID_status_display.SetStatusText(str(x)+","+str(y)+"/"+str(RGBA), 0)

    def img_left_release(self, event):
        if self.magnifier.Value != False:
            self.start_flag = 0

            id = self.get_img_id_from_point([self.x_0, self.y_0])
            if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:

                layout_row, layout_col = self.ImgManager._show_all_func_layout
                original_rows, original_cols = self.ImgManager._original_row_col
                total_cols = layout_col * original_cols
                xy_grid_array = np.array(self.ImgManager.xy_grid)
                xy_cur = np.array([[self.x_0, self.y_0]])
                xy_cur = np.repeat(xy_cur, xy_grid_array.shape[0], axis=0)
                res_ = xy_cur - xy_grid_array
                id_list = []
                for i in range(xy_grid_array.shape[0]):
                    if res_[i][0] >= 0 and res_[i][1] >= 0:
                        id_list.append(i)
                    else:
                        id_list.append(0)
                actual_grid_id = max(id_list)
                xy_grid = self.ImgManager.xy_grid[actual_grid_id]
            else:
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
                self.xy_magnifier.append(
                    points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                self.refresh(event)

    def img_right_click(self, event):
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:

            xy_grid_array = np.array(self.ImgManager.xy_grid)
            xy_cur = np.array([[x, y]])
            xy_cur = np.repeat(xy_cur, xy_grid_array.shape[0], axis=0)
            res_ = xy_cur - xy_grid_array
            id_list = []
            for i in range(xy_grid_array.shape[0]):
                if res_[i][0] >= 0 and res_[i][1] >= 0:
                    id_list.append(i)
                else:
                    id_list.append(0)
            actual_grid_id = max(id_list)
            xy_grid = self.ImgManager.xy_grid[actual_grid_id]
        else:
            xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        menu_triggered = getattr(event, 'menu_triggered', False)

        if not menu_triggered:
            self.on_right_click(event)
            return

        if self.select_img_box.Value:
            # move box
            if self.box_id != -1:
                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.move_box_point(x, y, show_scale)
                self.xy_magnifier[self.box_id] = points+show_scale+[
                    self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]]
                self.refresh(event)
                return
        else:
            # new box
            if self.magnifier.Value:
                self.color_list.append(self.colourPicker_draw.GetColour())
                try:
                    show_scale = self.show_scale.GetLineText(0).split(',')
                    show_scale = [float(x) for x in show_scale]
                    points = self.move_box_point(x, y, show_scale)
                    self.xy_magnifier.append(
                        points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                except:
                    self.SetStatusText_(
                        ["-1",  "Drawing a box need click left mouse button!", "-1", "-1"])

                self.refresh(event)
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
            else:
                if self.handle_title_injection(id):
                    pass
                else:
                    self.refresh(event)
        self.on_right_click(event)

    def on_right_click(self, event):
        # Right-click Menu​
        menu = wx.Menu()
        refresh_id = wx.Window.NewControlId()
        menu.Append(refresh_id, "🔄 refresh")
        menu.Bind(wx.EVT_MENU, self.refresh, id=refresh_id)

        prev_id = wx.Window.NewControlId()
        menu.Append(prev_id, "⬅️ Previous Page")
        menu.Bind(wx.EVT_MENU, self.last_img, id=prev_id)

        next_id = wx.Window.NewControlId()
        menu.Append(next_id, "➡️ Next Page")
        menu.Bind(wx.EVT_MENU, self.next_img, id=next_id)

        save_single_id = wx.Window.NewControlId()
        menu.Append(save_single_id, "💾 Save")
        def save_current_page(evt):
            # Default Save
            self.save_img(evt)
        menu.Bind(wx.EVT_MENU, save_current_page, id=save_single_id)

        if (self.ImgManager.type == 0 or self.ImgManager.type == 1) and (self.parallel_sequential.Value):
            save_column_id = wx.Window.NewControlId()
            menu.Append(save_column_id, "📄 save(only select current location)")
            def save_selected_column(evt):
                # save current location images in all folders
                if not self.out_path_str:
                    self.out_path(evt)
                    if not self.out_path_str:
                        return
                x, y = event.GetPosition()
                clicked_grid_id = self.get_img_id_from_point([x, y])
                # Retrieve ID information
                if hasattr(self, 'current_page_img_paths') and clicked_grid_id < len(self.current_page_img_paths):
                    target_path = self.current_page_img_paths[clicked_grid_id]
                else:
                    actual_img_index = self.ImgManager.xy_grids_id_list[clicked_grid_id] \
                        if hasattr(self.ImgManager, 'xy_grids_id_list') and clicked_grid_id < len(self.ImgManager.xy_grids_id_list) \
                        else clicked_grid_id

                    if not hasattr(self.ImgManager, 'flist') or actual_img_index >= len(self.ImgManager.flist):
                        self.SetStatusText_(["Cannot get clicked image", "-1", "-1", "-1"])
                        return
                    target_path = self.ImgManager.flist[actual_img_index]
                if not target_path or not os.path.exists(target_path):
                    self.SetStatusText_(["Invalid image path", "-1", "-1", "-1"])
                    return
                target_name = os.path.basename(target_path)
                type_ = self.choice_output.GetSelection()
                if self.show_custom_func.Value:
                    self.ImgManager.layout_params[32] = True
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.layout_params[32] = False
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

                # Call the default save function
                select_folder = os.path.join(self.out_path_str, "select_images")
                # override it with the new folder selection logic
                if os.path.exists(select_folder):
                    shutil.rmtree(select_folder)
                os.makedirs(select_folder, exist_ok=True)
                all_dirs = sorted(set(os.path.dirname(p) for p in self.ImgManager.flist))
                success_count = 0
                for folder_path in all_dirs:
                    if not os.path.exists(folder_path):
                        continue
                    try:
                        target_file = os.path.join(folder_path, target_name)
                        if os.path.exists(target_file) and os.path.isfile(target_file):
                            folder_name = os.path.basename(folder_path)
                            sub_dir = os.path.join(select_folder, folder_name)
                            os.makedirs(sub_dir, exist_ok=True)
                            shutil.copy2(target_file, os.path.join(sub_dir, target_name))
                            success_count += 1
                    except:
                        pass
                status_msg = f"Save completed! select_images updated with {success_count} images (clicked: {target_name})" \
                    if success_count > 0 \
                    else f"Save completed, but no matching images found for {target_name}"
                self.SetStatusText_([status_msg, "-1", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, save_selected_column, id=save_column_id)

        if self.magnifier.Value:
            new_box_id = wx.Window.NewControlId()
            menu.Append(new_box_id, "🔍 Create zoom box here")

            def create_magnifier_box(evt):
                event.menu_triggered = True
                x, y = event.GetPosition()
                id = self.get_img_id_from_point([x, y])
                xy_grid = self.ImgManager.xy_grid[id]
                x = x-xy_grid[0]
                y = y-xy_grid[1]

                if self.magnifier.Value:
                    self.color_list.append(self.colourPicker_draw.GetColour())
                    try:
                        show_scale = self.show_scale.GetLineText(0).split(',')
                        show_scale = [float(x) for x in show_scale]
                        if len(self.xy_magnifier) == 0:
                            default_size = 50
                            points = self.ImgManager.ImgF.sort_box_point(
                                [x-default_size//2, y-default_size//2, x+default_size//2, y+default_size//2],
                                show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        else:
                            points = self.move_box_point(x, y, show_scale)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        self.refresh(evt)
                        self.SetStatusText_(["Create a zoom box", "-1", "-1", "-1"])
                    except Exception as e:
                        self.SetStatusText_(["-1", f"Failed to create zoom box: {str(e)}", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, create_magnifier_box, id=new_box_id)

        if len(self.xy_magnifier) > 0:
            clear_all_id = wx.Window.NewControlId()
            menu.Append(clear_all_id, "🗑️ Clear all zoom boxes")
            menu.Bind(wx.EVT_MENU, self.img_left_dclick, id=clear_all_id)

        if self.select_img_box.Value:
            box_menu = wx.Menu()

            if self.box_id != -1:
                move_box_id = wx.Window.NewControlId()
                box_menu.Append(move_box_id, f"Move box {self.box_id} to this position")

                def move_box_to_position(evt):
                    event.menu_triggered = True
                    self.img_right_click(event)
                    self.refresh(evt)
                    self.SetStatusText_([f"Move box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, move_box_to_position, id=move_box_id)
                delete_box_id = wx.Window.NewControlId()
                box_menu.Append(delete_box_id, f"Delete box {self.box_id}")
                def delete_specific_box(evt):
                    if self.select_img_box.Value and self.box_id != -1:
                        self.xy_magnifier.pop(self.box_id)
                        if len(self.xy_magnifier) == 0:
                            self.box_position.SetSelection(0)
                        self.refresh(evt)
                        self.SetStatusText_([f"Delete box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, delete_specific_box, id=delete_box_id)
            menu.AppendSubMenu(box_menu, f"Selection box" + (f" ({self.box_id})" if self.box_id != -1 else ""))

        if hasattr(self, 'title_rename_text'):
            new_title = self.title_rename_text.GetValue().strip()
            if new_title:
                inject_title_id = wx.Window.NewControlId()
                display_title = new_title[:20] + "..." if len(new_title) > 20 else new_title
                menu.Append(inject_title_id, f"📝 Inject title: {display_title}")
                def inject_title_directly(evt):
                    x, y = event.GetPosition()
                    id = self.get_img_id_from_point([x, y])
                    success = self.handle_title_injection(id)
                    if success:
                        self.SetStatusText_(["Title injected successfully", "-1", "-1", "-1"])
                    else:
                        self.SetStatusText_(["Failed to inject title", "-1", "-1", "-1"])
                menu.Bind(wx.EVT_MENU, inject_title_directly, id=inject_title_id)
                menu.AppendSeparator()
        try:
            mouse_screen_pos = wx.GetMousePosition()
            client_pos = self.ScreenToClient(mouse_screen_pos)
        except:
            client_pos = wx.Point(100, 100)

        self.PopupMenu(menu, client_pos)
        menu.Destroy()

    #--exif--
    def on_title_exif_changed(self, event):
        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 17:
                self.ImgManager.layout_params[17][11] = self.title_exif.Value
                self.ImgManager.load_exif_display_config(force_reload=True)

    def inject_new_title(self, new_title, img_id=None):
        try:
            if img_id is not None:
                current_index = img_id
            else:
                current_index = getattr(self, 'selected_img_id', self.ImgManager.action_count)
            if hasattr(self.ImgManager, 'xy_grids_id_list') and current_index < len(self.ImgManager.xy_grids_id_list):
                actual_img_index = self.ImgManager.xy_grids_id_list[current_index]
            else:
                actual_img_index = current_index
            if actual_img_index < len(self.ImgManager.flist):
                img_path = self.ImgManager.flist[actual_img_index]
                success = self.ImgManager.update_image_exif_37510(img_path, new_title)
                if success:
                    self.ImgManager.get_img_list()

                    if hasattr(self, 'title_rename_text'):
                        self.title_rename_text.SetValue("")
                    self.SetStatusText_([f"The title has been injected into {current_index+1} images: {new_title}", "-1", "-1", "-1"])
                else:
                    raise Exception("Failed to write EXIF")
            else:
                raise Exception(f"Picture index {actual_img_index} out of range")

        except:
            pass

    def handle_title_injection(self, img_id = None):
        if not hasattr(self, 'title_rename_text'):
            return False
        new_title = self.title_rename_text.GetValue().strip()
        if not new_title:
            return False
        try:
            self.inject_new_title(new_title, img_id)
            return True
        except:
            return False

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

    def img_wheel(self, event):
        # https://wxpython.org/Phoenix/docs/html/wx.MouseEvent.html

        # zoom
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value and self.key_status["ctrl"] == 1:
            if event.GetWheelDelta() >= 120:
                speed = self.get_speed(name="scale")
                self.adjust_show_scale_proportion()  # adjust show_scale_proportion
                # set show_scale
                if event.GetWheelRotation() > 0:
                    self.show_scale_proportion = self.show_scale_proportion+speed
                else:
                    self.show_scale_proportion = self.show_scale_proportion-speed
                if self.show_scale_proportion > 0:
                    show_scale = [1*(1+self.show_scale_proportion),
                                  1*(1+self.show_scale_proportion)]
                elif self.show_scale_proportion < 0:
                    show_scale = [1/(1-self.show_scale_proportion),
                                  1/(1-self.show_scale_proportion)]
                else:
                    show_scale = [1, 1]
                self.show_scale.Value = str(
                    round(show_scale[0], 2))+","+str(round(show_scale[1], 2))
                for i in range(len(self.xy_magnifier)):
                    x_0, y_0, x_1, y_1 = self.xy_magnifier[i][0:4]
                    show_scale_old = self.xy_magnifier[i][4:6]

                    scale_ratio = [show_scale[0]/show_scale_old[0], show_scale[1]/show_scale_old[1]]

                    x_0 = int(x_0 * scale_ratio[0])
                    x_1 = int(x_1 * scale_ratio[0])
                    y_0 = int(y_0 * scale_ratio[1])
                    y_1 = int(y_1 * scale_ratio[1])

                    self.xy_magnifier[i][0:4] = [x_0, y_0, x_1, y_1]
                    self.xy_magnifier[i][4:6] = show_scale
                self.refresh(event)
            else:
                pass
        else:
            pass

        # move
        if self.shift_pressed:
            if event.GetWheelRotation()>0:
                self.left_img(event)
            else:
                self.right_img(event)
        if self.key_status["ctrl"] == 0 and event.GetWheelDelta() >= 120:
            if event.WheelAxis == 0 and self.shift_pressed == 0:
                if event.GetWheelRotation() > 0:
                    self.up_img(event)
                else:
                    self.down_img(event)
            else:
                if event.GetWheelRotation() > 0:
                    self.left_img(event)
                else:
                    self.right_img(event)

    def adjust_show_scale_proportion(self):
        # check "cur_scale", and adjust "self.show_scale_proportion"
        cur_scale = self.show_scale.GetLineText(0).split(',')
        cur_scale = [float(x) for x in cur_scale]
        if self.show_scale_proportion > 0:
            if cur_scale[0] == round(1*(1+self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        elif self.show_scale_proportion < 0:
            if cur_scale[0] == round(1/(1-self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        else:
            self.show_scale_proportion = 0

    def key_down_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 0:
                self.key_status["ctrl"] = 1
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = True
        elif event.GetKeyCode() == ord('S'):
            if self.shift_pressed == True:
                if self.key_status["shift_s"] == 0:
                    self.key_status["shift_s"] = 1
                elif self.key_status["shift_s"] == 1:
                    self.key_status["shift_s"] = 0

    def key_up_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 1:
                self.key_status["ctrl"] = 0
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = False

    def get_speed(self, name="pixel"):
        if name == "pixel":
            if self.key_status["shift_s"] == 1:
                speed = 5
            else:
                speed = 1
        elif name == "scale":
            if self.key_status["shift_s"] == 1:
                speed = 0.5
            else:
                speed = 0.1
        else:
            speed = None
        return speed

    def magnifier_fc(self, event):
        self.start_flag = 0
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def rotation_fc(self, event):
        i_cur = 1
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_POINT_RIGHT))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def flip_fc(self, event):
        i_cur = 2
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            flip_cursor_path = Path(get_resource_path(str(Path("images"))))
            flip_cursor_path = str(flip_cursor_path/"flip_cursor.png")
            self.SetCursor(
                wx.Cursor((wx.Image(flip_cursor_path, wx.BITMAP_TYPE_PNG))))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Flip", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def show_img_init(self):
        layout_params = self.set_img_layout()
        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                if self.parallel_to_sequential.Value:
                    self.ImgManager.set_count_per_action(
                        layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1])
                else:
                    if self.parallel_sequential.Value:
                        self.ImgManager.set_count_per_action(
                            layout_params[1][0]*layout_params[1][1])
                    else:
                        self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                self.ImgManager.set_count_per_action(
                    layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1])
            self.update_status_bar_for_current_page()

    def set_img_layout(self):

        try:
            row_col = self.row_col.GetLineText(0).split(',')
            row_col = [int(x) for x in row_col]

            row_col_one_img = self.row_col_one_img.GetLineText(0).split(',')
            row_col_one_img = [int(x) for x in row_col_one_img]

            if row_col_one_img[0] == -1 and row_col_one_img[1] == -1:
                row_col_one_img= [1,1]
                row_col = self.ImgManager.layout_advice()
                self.row_col.SetValue(str(row_col[0])+","+str(row_col[1]))

            row_col_img_unit = self.row_col_img_unit.GetLineText(0).split(',')
            row_col_img_unit = [int(x) for x in row_col_img_unit]

            magnifer_row_col = self.magnifer_row_col.GetLineText(0).split(',')
            magnifer_row_col = [int(x) for x in magnifer_row_col]

            gap = self.gap.GetLineText(0).split(',')
            gap = [int(x) for x in gap]

            show_scale = self.show_scale.GetLineText(0).split(',')
            show_scale = [float(x) for x in show_scale]

            output_scale = self.output_scale.GetLineText(0).split(',')
            output_scale = [float(x) for x in output_scale]

            img_resolution = self.img_resolution.GetLineText(0).split(',')
            img_resolution = [int(x) for x in img_resolution]

            magnifer_resolution = self.magnifer_resolution.GetLineText(
                0).split(',')
            magnifer_resolution = [int(x) for x in magnifer_resolution]

            magnifier_show_scale = self.magnifier_show_scale.GetLineText(
                0).split(',')
            magnifier_show_scale = [float(x) for x in magnifier_show_scale]

            magnifier_out_scale = self.magnifier_out_scale.GetLineText(
                0).split(',')
            magnifier_out_scale = [float(x) for x in magnifier_out_scale]

            if self.checkBox_auto_draw_color.Value:
                # 10 colors built into the software
                color_list = [
                    wx.Colour(217, 26, 42, int(85/100*255)),
                    wx.Colour(147, 81, 166, int(65/100*255)),
                    wx.Colour(85, 166, 73, int(65/100*255)),
                    wx.Colour(242, 229, 48, int(95/100*255)),
                    wx.Colour(242, 116, 5, int(95/100*255)),
                    wx.Colour(242, 201, 224, int(95/100*255)),
                    wx.Colour(36, 132, 191, int(75/100*255)),
                    wx.Colour(65, 166, 90, int(65/100*255)),
                    wx.Colour(214, 242, 206, int(95/100*255)),
                    wx.Colour(242, 163, 94, int(95/100*255))]
                num_box = len(self.xy_magnifier)
                if num_box <= len(color_list):
                    self.color_list = color_list[0:num_box]
                else:
                    self.color_list = color_list + \
                        color_list[0:num_box-len(color_list)]

            color = self.color_list

            line_width = self.line_width.GetLineText(0).split(',')
            line_width = [int(x) for x in line_width]

            title_setting = [self.title_auto.Value,                     # 0
                             self.title_show.Value,                     # 1
                             self.title_down_up.Value,                  # 2
                             self.title_show_parent.Value,              # 3
                             self.title_show_prefix.Value,              # 4
                             self.title_show_name.Value,                # 5
                             self.title_show_suffix.Value,              # 6
                             self.title_font.GetSelection(),            # 7
                             self.title_font_size.Value,                # 8
                             self.font_paths,                           # 9
                             self.title_position.GetSelection(),        # 10
                             self.title_exif.Value,                     # 11
                             self.title_show_rename.Value]              # 12

            if title_setting[0]:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    # one_dir_mul_dir_auto / one_dir_mul_dir_manual
                    if self.parallel_sequential.Value or self.parallel_to_sequential.Value:
                        title_setting[2:7] = [False, True, True, True, False]
                    else:
                        title_setting[2:7] = [False, True, True, False, False]

                elif self.ImgManager.type == 2:
                    # one_dir_mul_img
                    title_setting[2:7] = [False, False, True, True, False]
                elif self.ImgManager.type == 3:
                    # read file list from a list file
                    title_setting[2:7] = [False, True, True, True, False]

        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [row_col,                                # 0
                    row_col_one_img,                        # 1
                    row_col_img_unit,                       # 2
                    gap,                                    # 3
                    show_scale,                             # 4
                    output_scale,                           # 5
                    img_resolution,                         # 6
                    1 if self.magnifier.Value else 0,       # 7
                    magnifier_show_scale,                   # 8
                    color,                                  # 9
                    line_width,                             # 10
                    self.move_file.Value,                   # 11
                    self.keep_magnifer_size.Value,          # 12
                    self.image_interp.GetSelection(),       # 13
                    self.show_box.Value,                    # 14
                    self.show_box_in_crop.Value,            # 15
                    self.show_original.Value,               # 16
                    title_setting,                          # 17
                    self.show_magnifer.Value,               # 18
                    self.parallel_to_sequential.Value,      # 19
                    self.one_img.Value,                     # 20
                    self.box_position.GetSelection(),       # 21
                    self.parallel_sequential.Value,         # 22
                    self.auto_save_all.Value,               # 23
                    self.img_vertical.Value,                # 24
                    self.one_img_vertical.Value,            # 25
                    self.img_unit_vertical.Value,           # 26
                    self.magnifer_vertical.Value,           # 27
                    magnifer_resolution,                    # 28
                    magnifer_row_col,                       # 29
                    self.onetitle.Value,                    # 30
                    magnifier_out_scale,                    # 31
                    self.show_custom_func.Value,            # 32
                    self.out_path_str,                      # 33
                    self.Magnifier_format.GetSelection(),   # 34
                    self.save_format.GetSelection(),        # 35
                    self.show_unit.Value,                   # 36
                    self.customfunc_choice.GetSelection(),  # 37
                    self.show_all_func.Value,               # 38
                    self.show_all_func_layout.Value,        # 39
                    self.func_layout_vertical.Value ]       # 40

    def show_img(self, event):
        if hasattr(self, 'm_staticText1'):
            self.m_staticText1.Hide()

        if self.show_custom_func.Value and self.out_path_str == "":
            self.out_path(None)
            self.ImgManager.layout_params[33] = self.out_path_str
        # check layout_params change
        try:
            if self.layout_params_old[0:2] != self.ImgManager.layout_params[0:2] or (self.layout_params_old[19] != self.ImgManager.layout_params[19]):
                action_count = self.ImgManager.action_count
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    parallel_to_sequential = self.parallel_to_sequential.Value
                else:
                    parallel_to_sequential = False
                self.ImgManager.init(
                    self.ImgManager.input_path, type=self.ImgManager.type, parallel_to_sequential=parallel_to_sequential)
                self.show_img_init()
                self.ImgManager.set_action_count(action_count)
                if self.index_table_gui:
                    self.index_table_gui.show_id_table(
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
            self.current_page_img_paths = copy.deepcopy(self.ImgManager.flist)
            expected_num = self.ImgManager.count_per_action
            if len(self.current_page_img_paths) < expected_num:
                self.current_page_img_paths += [None] * (expected_num - len(self.current_page_img_paths))

            # show the output image processed by the custom func; return cat(bmp, customfunc_img)
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.stitch_images(
                    0, copy.deepcopy(self.xy_magnifier))
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.stitch_images(
                0, copy.deepcopy(self.xy_magnifier))
            if flag == 0:
                bmp = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)
                self.show_bmp_in_panel = bmp
                self.img_size = bmp.size
                bmp = self.ImgManager.ImgF.PIL2wx(bmp)
                self.img_panel.SetSize(
                    wx.Size(self.img_size[0]+100, self.img_size[1]+100))
                self.img_last = wx.StaticBitmap(parent=self.img_panel,
                                                bitmap=bmp)
                self.img_panel.Children[0].SetFocus()
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
                self.img_panel.Children[0].Bind(
                    wx.EVT_MOUSEWHEEL, self.img_wheel)
                self.img_panel.Children[0].Bind(
                    wx.EVT_KEY_DOWN, self.key_down_detect)
                self.img_panel.Children[0].Bind(
                    wx.EVT_KEY_UP, self.key_up_detect)

            self.update_status_bar_for_current_page()
            try:
                if self.ImgManager.type == 2 or ((self.ImgManager.type == 0 or self.ImgManager.type == 1) and self.parallel_sequential.Value):
                    start_img = self.ImgManager.img_count
                    end_img = min(self.ImgManager.img_count + self.ImgManager.count_per_action - 1, self.ImgManager.img_num - 1)
                    img_range = f"{self.ImgManager.name_list[start_img]}-{self.ImgManager.name_list[end_img]}" if start_img != end_img else f"{self.ImgManager.name_list[start_img]}"
                    detail_text = f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / {img_range}"
                else:
                    detail_text = f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / {self.ImgManager.get_stitch_name()}"
                self.SetStatusText_(["-1", "-1", detail_text, "-1"])
            except:
                self.SetStatusText_(["-1", "-1", f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels", "-1"])
        # Fix the issue where the AutoWinSize button is unresponsive
        if self.auto_layout_check.Value:
            self.auto_layout()
        else:
            # Defer layout refresh to avoid forcing window resize while still updating scrollbars
            wx.CallAfter(self.scrolledWindow_img.FitInside)
            wx.CallAfter(self.Layout)

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

        if self.hidden_flag == 1:
            offset_hight_img_show = 50
        else:
            offset_hight_img_show = 0

        if self.auto_layout_check.Value and (not frame_resize):
            if self.img_size[0] < self.width:
                if self.img_size[0]+self.width_setting+40 < self.width:
                    w = self.width
                else:
                    w = self.img_size[0]+self.width_setting+40
            elif self.img_size[0]+self.width_setting+40 > self.displaySize[0]:
                w = self.displaySize[0]
            else:
                w = self.img_size[0]+self.width_setting+40

            if self.img_size[1] < self.height:
                if self.img_size[1]+200 < self.height:
                    h = self.height
                else:
                    h = self.img_size[1]+200
                    if self.hidden_flag == 1:
                        h = h-50
            elif self.img_size[1]+200 > self.displaySize[1]:
                h = self.displaySize[1]
            else:
                h = self.img_size[1]+200
                if self.hidden_flag == 1:
                    h = h-50

            self.Size = wx.Size((w, h))

        if self.hidden_flag == 1:
            self.m_splitter1.SashPosition = self.Size[0]

        self.init_min_size()

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0]-self.width_setting, self.Size[1]-150+offset_hight_img_show)))

        # issue: You need to change the window size, then the scrollbar starts to display.
        self.scrolledWindow_img.FitInside()
        self.scrolledWindow_set.FitInside()

        self.Layout()
        self.Refresh()

    def init_min_size(self):
        self.scrolledWindow_set.SetMinSize(
            wx.Size((50, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((50, self.Size[1]-150)))

    def split_sash_pos_changing(self, event):

        self.init_min_size()
        self.split_changing = True

    def split_sash_pos_changed(self, event):
        self.SashPosition = self.m_splitter1.SashPosition

        if self.split_changing:
            self.width_setting = self.Size[0]-self.SashPosition

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0] - self.width_setting, self.Size[1]-150)))

        self.split_changing = False
        # print(self.SashPosition)

    def about_gui(self, event, update=False, new_version=None):
        self.aboutgui = About(self, self.version,
                              update=update, new_version=new_version)
        self.aboutgui.Show(True)

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
                    self.indextablegui = IndexTable(
                        None, self.ImgManager.path_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                else:
                    self.indextablegui = IndexTable(
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

    def get_img_id_from_point(self, xy, img=False):
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
        current_id = max(id_list)

        if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:
            layout_row, layout_col = self.ImgManager._show_all_func_layout
            original_rows, original_cols = self.ImgManager._original_row_col
            func_layout_vertical = getattr(self.ImgManager, '_func_layout_vertical', False)
            total_cols = layout_col * original_cols
            final_row = current_id // total_cols
            final_col = current_id % total_cols
            orig_row = final_row % original_rows
            orig_col = final_col % original_cols
            original_id = orig_row * original_cols + orig_col
            current_id = original_id
        if img:
            return self.ImgManager.xy_grids_id_list[max(id_list)]
        else:
            return max(id_list)

    def title_down_up_fc(self, event):
        if self.title_down_up.Value:
            self.title_down_up.SetLabel('Up  ')
        else:
            self.title_down_up.SetLabel('Down')

    def title_rename_fc(self, event):
        if hasattr(self.ImgManager, 'layout_params') and len(self.ImgManager.layout_params) > 17:
            if len(self.ImgManager.layout_params[17]) > 12:
                self.ImgManager.layout_params[17][12] = self.title_show_rename.Value

    def parallel_sequential_fc(self, event):
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False

    def parallel_to_sequential_fc(self, event):
        if self.parallel_to_sequential.Value:
            self.parallel_sequential.Value = False

    def title_auto_fc(self, event):
        titles = [self.title_down_up, self.title_show_parent,
                  self.title_show_name, self.title_show_suffix, self.title_show_prefix, self.title_position, self.title_exif, self.title_show_rename]
        if self.title_auto.Value:
            for title in titles:
                title.Enabled = False
            self.title_exif.SetValue(False)
            #self.title_show_rename.SetValue(False)
        else:
            for title in titles:
                title.Enabled = True

        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 17:
                self.ImgManager.layout_params[17][11] = self.title_exif.Value
                if len(self.ImgManager.layout_params[17]) > 12:
                    self.ImgManager.layout_params[17][12] = self.title_show_rename.Value

    def select_img_box_func(self, event):
        if self.select_img_box.Value:
            self.box_id = -1

    def draw_color_change(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                if self.checkBox_auto_draw_color.Value:
                    self.checkBox_auto_draw_color.Value = False
                self.color_list[self.box_id] = self.colourPicker_draw.GetColour()
                self.refresh(event)

    def on_show_all_func_changed(self, event):
        if self.show_all_func.GetValue():
            self.show_custom_func.SetValue(False)

    def on_show_custom_func_changed(self, event):
        if self.show_custom_func.GetValue():
            self.show_all_func.SetValue(False)

    def hidden(self, event):
        if self.hidden_flag == 0:
            self.Sizer.Hide(self.m_panel1)
            self.scrolledWindow_set.Sizer.Hide(self.m_panel4)

            self.width_setting_ = self.width_setting
            self.width_setting = 0

            self.hidden_flag = 1
        else:
            self.Sizer.Show(self.m_panel1)
            self.scrolledWindow_set.Sizer.Show(self.m_panel4)

            self.width_setting = self.width_setting_

            self.hidden_flag = 0

        # issue: You need to change the window size, then the scrollbar starts to display.
        self.scrolledWindow_set.FitInside()
        self.auto_layout()

    def _bind_settings_wheel_guard(self):
        # Controls that should handle the wheel event
        swallow_types = (wx.Choice, wx.ComboBox, wx.SpinCtrl, wx.SpinCtrlDouble)

        # Reroute wheel event to scrolled window
        def reroute_wheel(event):
            clone = event.Clone()
            clone.SetEventObject(self.scrolledWindow_set)
            clone.ResumePropagation(wx.EVENT_PROPAGATE_MAX)
            self.scrolledWindow_set.GetEventHandler().ProcessEvent(clone)

        # Recursively bind wheel event to relevant controls
        def walk(win):
            for child in win.GetChildren():
                if isinstance(child, swallow_types):
                    child.Bind(wx.EVT_MOUSEWHEEL, reroute_wheel)
                if child.GetChildren():
                    walk(child)

        walk(self.scrolledWindow_set)

    def save_configuration(self, event):
        data = {
            'row_col': self.row_col.GetLineText(0),
            'row_col_one_img': self.row_col_one_img.GetLineText(0),
            'show_scale': self.show_scale.GetLineText(0),
            'row_col_img_unit': self.row_col_img_unit.GetLineText(0),
            'gap': self.gap.GetLineText(0),
            'magnifer_row_col': self.magnifer_row_col.GetLineText(0),
            'output_scale': self.output_scale.GetLineText(0),
            'img_resolution': self.img_resolution.GetLineText(0),
            'magnifer_resolution': self.magnifer_resolution.GetLineText(0),
            'magnifier_show_scale': self.magnifier_show_scale.GetLineText(0),
            'line_width': self.line_width.GetLineText(0),
            'magnifier_out_scale': self.magnifier_out_scale.GetLineText(0),
            'title_font_size': self.title_font_size.GetLineText(0),
            'box_position': self.box_position.GetSelection(),
            'choice_normalized_size': self.choice_normalized_size.GetSelection(),
            'choice_output': self.choice_output.GetSelection(),
            'image_interp': self.image_interp.GetSelection(),
            'Magnifier_format': self.Magnifier_format.GetSelection(),
            'title_font': self.title_font.GetSelection(),
            'parallel_sequential': self.parallel_sequential.GetValue(),
            'parallel_to_sequential': self.parallel_to_sequential.GetValue(),
            'auto_save_all': self.auto_save_all.GetValue(),
            'move_file': self.move_file.GetValue(),
            'img_vertical': self.img_vertical.GetValue(),
            'one_img_vertical': self.one_img_vertical.GetValue(),
            'img_unit_vertical': self.img_unit_vertical.GetValue(),
            'magnifer_vertical': self.magnifer_vertical.GetValue(),
            'show_original': self.show_original.GetValue(),
            'show_magnifer': self.show_magnifer.GetValue(),
            'title_show': self.title_show.GetValue(),
            'auto_layout_check': self.auto_layout_check.GetValue(),
            'one_img': self.one_img.GetValue(),
            'onetitle': self.onetitle.GetValue(),
            'customfunc': self.show_custom_func.GetValue(),
            'show_box': self.show_box.GetValue(),
            'show_box_in_crop': self.show_box_in_crop.GetValue(),
            'select_img_box': self.select_img_box.GetValue(),
            'title_auto': self.title_auto.GetValue(),
            'title_exif': self.title_exif.GetValue(),
            'title_show_parent': self.title_show_parent.GetValue(),
            'title_show_prefix': self.title_show_prefix.GetValue(),
            'title_show_name': self.title_show_name.GetValue(),
            'title_show_suffix': self.title_show_suffix.GetValue(),
            'title_down_up': self.title_down_up.GetValue(),
            'save_format': self.save_format.GetSelection(),
            'title_show_rename': self.title_show_rename.GetValue(),
            'customfunc_choice': self.customfunc_choice.GetSelection(),
            'show_all_func': self.show_all_func.GetValue(),
            'show_all_func_layout': self.show_all_func_layout.GetValue(),
            'func_layout_vertical': self.func_layout_vertical.GetValue(),
        }
        flip_cursor_path = Path(get_resource_path(str(Path("configs"))))
        flip_cursor_path = str(flip_cursor_path / "output.json")
        with open(flip_cursor_path, 'w') as file:
            json.dump(data, file, indent=1)

    def load_configuration(self, event, config_name="output.json"):
        flip_cursor_path = Path(get_resource_path(str(Path("configs"))))
        flip_cursor_path = str(flip_cursor_path / config_name)
        with open(flip_cursor_path, 'r') as file:
            data = json.load(file)
            self.row_col.SetValue(data['row_col'])
            self.row_col_one_img.SetValue(data['row_col_one_img'])
            self.show_scale.SetValue(data['show_scale'])
            self.row_col_img_unit.SetValue(data['row_col_img_unit'])
            self.gap.SetValue(data['gap'])
            self.magnifer_row_col.SetValue(data['magnifer_row_col'])
            self.output_scale.SetValue(data['output_scale'])
            self.img_resolution.SetValue(data['img_resolution'])
            self.magnifer_resolution.SetValue(data['magnifer_resolution'])
            self.magnifier_show_scale.SetValue(data['magnifier_show_scale'])
            self.line_width.SetValue(data['line_width'])
            self.magnifier_out_scale.SetValue(data['magnifier_out_scale'])
            self.title_font_size.SetValue(data['title_font_size'])
            self.box_position.SetSelection(data['box_position'])
            self.choice_normalized_size.SetSelection(data['choice_normalized_size'])
            self.choice_output.SetSelection(data['choice_output'])
            self.image_interp.SetSelection(data['image_interp'])
            self.Magnifier_format.SetSelection(data['Magnifier_format'])
            self.title_font.SetSelection(data['title_font'])
            self.parallel_sequential.SetValue(data['parallel_sequential'])
            self.parallel_to_sequential.SetValue(data['parallel_to_sequential'])
            self.auto_save_all.SetValue(data['auto_save_all'])
            self.move_file.SetValue(data['move_file'])
            self.img_vertical.SetValue(data['img_vertical'])
            self.one_img_vertical.SetValue(data['one_img_vertical'])
            self.img_unit_vertical.SetValue(data['img_unit_vertical'])
            self.magnifer_vertical.SetValue(data['magnifer_vertical'])
            self.show_original.SetValue(data['show_original'])
            self.show_magnifer.SetValue(data['show_magnifer'])
            self.title_show.SetValue(data['title_show'])
            self.auto_layout_check.SetValue(data['auto_layout_check'])
            self.one_img.SetValue(data['one_img'])
            self.onetitle.SetValue(data['onetitle'])
            self.show_custom_func.SetValue(data['show_custom_func'])
            self.show_box.SetValue(data['show_box'])
            self.show_box_in_crop.SetValue(data['show_box_in_crop'])
            self.select_img_box.SetValue(data['select_img_box'])
            self.title_auto.SetValue(data['title_auto'])
            self.title_exif.SetValue(data['title_exif'])
            self.title_show_parent.SetValue(data['title_show_parent'])
            self.title_show_prefix.SetValue(data['title_show_prefix'])
            self.title_show_name.SetValue(data['title_show_name'])
            self.title_show_suffix.SetValue(data['title_show_suffix'])
            self.title_down_up.SetValue(data['title_down_up'])
            self.save_format.SetSelection(data['save_format'])
            self.title_show_rename.SetValue(data.get('title_show_rename', False))
            self.ImgManager.load_exif_display_config(force_reload=True)
            if 'customfunc_choice' in data:
                self.customfunc_choice.SetSelection(data['customfunc_choice'])
            else:
                self.customfunc_choice.SetSelection(0)
            if 'show_all_func' in data:
                self.show_all_func.SetValue(data['show_all_func'])
            else:
                self.show_all_func.SetValue(False)

            if 'show_all_func_layout' in data:
                self.show_all_func_layout.SetValue(data['show_all_func_layout'])
            else:
                self.show_all_func_layout.SetValue("2,2")

            if 'func_layout_vertical' in data:
                self.func_layout_vertical.SetValue(data['func_layout_vertical'])
            else:
                self.func_layout_vertical.SetValue(False)

    def reset_configuration(self, event):
        json_path = Path(get_resource_path(str(Path("configs"))))
        output_json_path = str(json_path / "output.json")
        output_s_json_path = str(json_path / "output_s.json")
        self.load_configuration(event, config_name="output_s.json")
        shutil.copy(output_s_json_path, output_json_path)

    def add_custom_algorithm(self, event):
        algorithm_path = self.custom_algorithm_input.GetValue().strip()
        if not algorithm_path:
            return
        try:
            source_path = Path(algorithm_path)
            if not source_path.exists():
                wx.MessageBox(f"Path does not exist: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
                return
            if not source_path.is_dir():
                wx.MessageBox(f"Path must be a folder: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
                return
            # Check if main.py file exists
            main_file = source_path / "main.py"
            if not main_file.exists():
                wx.MessageBox(f"main.py file missing in algorithm folder: {algorithm_path}", "File Missing", wx.OK | wx.ICON_ERROR)
                return
        except Exception as e:
            wx.MessageBox(f"Path format error: {str(e)}", "Path Error", wx.OK | wx.ICON_ERROR)
            return
        algorithm_name = source_path.name
        current_choices = []
        for i in range(self.customfunc_choice.GetCount()):
            current_choices.append(self.customfunc_choice.GetString(i))

        if algorithm_name in current_choices:
            wx.MessageBox(f"Algorithm '{algorithm_name}' already exists!", "Duplicate Algorithm", wx.OK | wx.ICON_WARNING)
            return
        try:
            self.copy_algorithm_from_path(source_path, algorithm_name)

            self.custom_algorithms.append(algorithm_name)
            time.sleep(0.1)
            def update_ui():
                self.refresh_algorithm_list()
                try:
                    modules_to_clear = [
                        'mulimgviewer.src.custom_func.main',
                        'custom_func.main',
                        '.custom_func.main'
                    ]
                    for module_name in modules_to_clear:
                        if module_name in sys.modules:
                            del sys.modules[module_name]
                    available_algorithms = get_available_algorithms()

                    if algorithm_name in available_algorithms:
                        index = available_algorithms.index(algorithm_name)
                        self.customfunc_choice.SetSelection(index)
                except:
                    pass
                self.custom_algorithm_input.SetValue("")
                self.customfunc_choice.Refresh()
                self.customfunc_choice.Update()
                self.Update()
                parent = self.customfunc_choice.GetParent()
                if parent:
                    parent.Refresh()
                    parent.Update()
                self.Layout()
                wx.MessageBox(f"Algorithm '{algorithm_name}' added successfully from path '{algorithm_path}'!", "Add Success", wx.OK | wx.ICON_INFORMATION)
            wx.CallAfter(update_ui)
        except Exception as e:
            wx.MessageBox(f"Failed to add algorithm: {str(e)}", "Add Failed", wx.OK | wx.ICON_ERROR)

    def copy_algorithm_from_path(self, source_path, algorithm_name):
        target_folder = Path(__file__).parent / "custom_func" / algorithm_name
        try:
            if target_folder.exists():
                shutil.rmtree(str(target_folder))
            shutil.copytree(str(source_path), str(target_folder))
        except Exception as e:
            raise e

    def remove_custom_algorithm(self, event):
        selected_index = self.customfunc_choice.GetSelection()
        if selected_index == wx.NOT_FOUND:
            wx.MessageBox("Please select an algorithm to remove first!", "No Algorithm Selected", wx.OK | wx.ICON_WARNING)
            return
        selected_algorithm = self.customfunc_choice.GetString(selected_index)
        dlg = wx.MessageDialog(self, f"Are you sure you want to remove algorithm '{selected_algorithm}'?", "Confirm Removal", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            try:
                self.remove_custom_algorithm_folder(selected_algorithm)

                if selected_algorithm in self.custom_algorithms:
                    self.custom_algorithms.remove(selected_algorithm)

                modules_to_clear = [
                    'mulimgviewer.src.custom_func.main',
                    'custom_func.main',
                    '.custom_func.main'
                ]
                for module_name in modules_to_clear:
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                self.refresh_algorithm_list()
                wx.MessageBox(f"Algorithm '{selected_algorithm}' removed successfully!", "Remove Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Failed to remove algorithm: {str(e)}", "Remove Failed", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def create_custom_algorithm_template(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        desktop_algorithm_folder = Path.home() / "Desktop" / algorithm_name
        if desktop_algorithm_folder.exists() and (desktop_algorithm_folder / "main.py").exists():
            try:
                if algorithm_folder.exists():
                    shutil.rmtree(str(algorithm_folder))
                shutil.copytree(str(desktop_algorithm_folder), str(algorithm_folder))
                return
            except Exception as e:
                pass
        if not algorithm_folder.exists():
            os.makedirs(str(algorithm_folder))
        template_content = f'''\'\'\'
{algorithm_name} Algorithm
Custom algorithm - Implement your image processing logic here
\'\'\'
from PIL import Image
from pathlib import Path
import os

def custom_process_img(img):
    """
    Custom image processing function
    input: image(pillow)
    output: image(pillow)

    Implement your image processing algorithm here
    Examples:
    - img = img.convert('L')  # Convert to grayscale
    - img = img.transpose(Image.FLIP_LEFT_RIGHT)  # Horizontal flip
    """
    # Default: no processing, return original image
    return img

def main(img_list, save_path, name_list=None, algorithm_name="{algorithm_name}"):
    """
    Batch process image list
    """
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        save_path = Path(save_path) / "processing_function" / algorithm_name
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        img = custom_process_img(img)

        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list) and i < len(name_list):
                img_path = save_path / name_list[i]
            else:
                img_path = save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
'''

        template_path = algorithm_folder / "main.py"
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(template_content)

    def remove_custom_algorithm_folder(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        if algorithm_folder.exists():
            try:
                shutil.rmtree(str(algorithm_folder))
            except Exception as e:
                pass

    def refresh_algorithm_list(self):
        try:
            modules_to_clear = [
                'mulimgviewer.src.custom_func.main',
                'custom_func.main',
                '.custom_func.main'
            ]
            for module_name in modules_to_clear:
                if module_name in sys.modules:
                    del sys.modules[module_name]
            try:
                if 'custom_func.main' in sys.modules:
                    importlib.reload(sys.modules['custom_func.main'])
            except:
                pass
            available_algorithms = get_available_algorithms()
            current_selection = self.customfunc_choice.GetSelection()
            current_algorithm = ""
            if current_selection != wx.NOT_FOUND:
                current_algorithm = self.customfunc_choice.GetString(current_selection)
            self.customfunc_choice.Clear()
            for i, algorithm in enumerate(available_algorithms):
                self.customfunc_choice.Append(algorithm)
            if current_algorithm and current_algorithm in available_algorithms:
                index = available_algorithms.index(current_algorithm)
                self.customfunc_choice.SetSelection(index)
            else:
                self.customfunc_choice.SetSelection(0)
        except:
            self.customfunc_choice.Clear()
            default_algorithms = ["Image Enhancement", "Image Darkening", "Gaussian Blur", "Histogram Equalization"]
            for algorithm in default_algorithms:
                self.customfunc_choice.Append(algorithm)
            self.customfunc_choice.SetSelection(0)

    def disable_accel(self, event):
        self.SetAcceleratorTable(wx.NullAcceleratorTable)

    def enable_accel(self, event):
        self.SetAcceleratorTable(self.acceltbl)
