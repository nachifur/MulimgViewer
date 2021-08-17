import wx
import numpy as np
import os
from PIL import Image
from shutil import copyfile, move
from pathlib import Path
import csv
import copy
from utils import solve_factor, change_order


class ImgUtils():
    """The set of functional programming modules"""

    def __init__(self):
        pass

    def PIL2wx(self, image):
        width, height = image.size
        return wx.Bitmap.FromBufferRGBA(width, height, image.tobytes())

    def add_alpha(self, img, alpha):
        img_array = np.array(img)
        temp = img_array[:, :, 0]
        if img_array.shape[2] == 3:
            img = np.concatenate((img_array, np.ones_like(
                temp[:, :, np.newaxis])*alpha), axis=2)
        elif img_array.shape[2] == 4:
            img_array[:, :, 3] = np.ones_like(temp)*alpha
            img = img_array
        else:
            pass
        img = Image.fromarray(img.astype('uint8')).convert('RGBA')
        return img

    def draw_rectangle(self, img, xy_grids, bounding_boxs, color_list, line_width=2, single_box=False):
        """img
        xy_grids: the position of bounding_boxs (list)
        boxs_points: the four points that make up a bounding boxs 
        color_list: the color of bounding_boxs
        """

        if single_box:
            xy_grids = [xy_grids[0]]
        else:
            xy_grids = xy_grids

        img_array = np.array(img)

        i = 0
        k = 0
        for bounding_box in bounding_boxs:
            x_0, y_0, x, y = bounding_box
            height = y-y_0
            width = x - x_0
            color = color_list[k]
            draw_colour = np.array(
                [color.red, color.green, color.blue, color.alpha])

            for xy in xy_grids:
                x_left_up = [x_0+xy[0], y_0+xy[1]]
                x_left_down = [x_0+xy[0], y_0+xy[1]+height]
                x_right_up = [x_0+xy[0]+width, y_0+xy[1]]
                x_right_down = [x_0+xy[0]+width, y_0+xy[1]+height]
                img_array[x_left_up[1]:x_left_down[1], x_left_up[0]:x_left_up[0]+line_width, :] = np.ones_like(
                    img_array[x_left_up[1]:x_left_down[1], x_left_up[0]:x_left_up[0]+line_width, :])*draw_colour
                img_array[x_left_up[1]:x_left_up[1]+line_width, x_left_up[0]:x_right_up[0], :] = np.ones_like(
                    img_array[x_left_up[1]:x_left_up[1]+line_width, x_left_up[0]:x_right_up[0], :])*draw_colour
                img_array[x_right_up[1]:x_right_down[1], x_right_up[0]-line_width:x_right_up[0], :] = np.ones_like(
                    img_array[x_right_up[1]:x_right_down[1], x_right_up[0]-line_width:x_right_up[0], :])*draw_colour
                img_array[x_left_down[1]-line_width:x_left_down[1], x_left_up[0]:x_right_up[0], :] = np.ones_like(
                    img_array[x_left_down[1]-line_width:x_left_down[1], x_left_up[0]:x_right_up[0], :])*draw_colour
            i += 1
            k += 1
            if k == len(color_list):
                k = 0
        img = Image.fromarray(img_array.astype('uint8')).convert('RGBA')
        return img


class ImgDatabase():
    """Multi-image database.  
    Multi-image browsing, path management, loading multi-image data, automatic layout layout, etc. """

    def init(self, input_path, type, action_count=None, img_count=None):
        self.input_path = input_path
        self.type = type

        self.init_flist()
        self.img_num = len(self.name_list)
        # self.set_count_per_action(1)
        if img_count:
            self.img_count = img_count
        else:
            self.img_count = 0
        if action_count:
            self.action_count = action_count
        else:
            self.action_count = 0

    def init_flist(self):
        self.csv_flag = 0
        if self.type == 0:
            # one_dir_mul_dir_auto
            cwd = Path(self.input_path)
            self.path_list = [str(path)
                              for path in cwd.iterdir() if cwd.is_dir() and path.is_dir()]
            if len(self.path_list) == 0:
                self.path_list = [self.input_path]
            self.path_list = np.sort(self.path_list)
            name_list = self.get_name_list()
            self.name_list = np.sort(name_list)
        elif self.type == 1:
            # one_dir_mul_dir_manual
            self.path_list = [path
                              for path in self.input_path if Path(path).is_dir()]
            if len(self.path_list) != 0:
                name_list = self.get_name_list()
                self.name_list = np.sort(name_list)
            else:
                self.name_list = []
        elif self.type == 2:
            # one_dir_mul_img
            self.path_list = [self.input_path]
            self.path_list = np.sort(self.path_list)
            name_list = self.get_name_list()
            self.name_list = np.sort(name_list)
        elif self.type == 3:
            # read file list from a list file
            self.path_list = self.get_path_list_from_lf()
            self.name_list = self.get_name_list_from_lf()
        else:
            self.path_list = []
            self.name_list = []

    def get_path_list_from_lf(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
        if Path(self.input_path).suffix.lower() == '.txt':
            with open(self.input_path, "r") as f:
                dataset = f.read().split('\n')
        elif Path(self.input_path).suffix.lower() == '.csv':
            with open(self.input_path, 'r', newline='') as csvfile:
                dataset = list(csv.reader(csvfile))
                dataset_ = []
                row = len(dataset)
                col = len(dataset[0])
                for items in dataset:
                    for item in items:
                        dataset_.append(item)
                dataset = dataset_
                self.csv_flag = 1
                self.csv_row_col = [row, col]
        else:
            dataset = []

        if len(dataset) == 0:
            validdataset = []
            self.dataset_mode = False
        elif len(dataset) < 100:
            validdataset = [item for item in dataset if Path(
                item).is_file() and Path(item).suffix.lower() in format_group]
            self.dataset_mode = False
        else:
            validdataset = dataset
            self.dataset_mode = True
        return validdataset

    def get_name_list_from_lf(self):
        if self.path_list == []:
            return []
        dataset = np.array(self.path_list).ravel().tolist()
        namelist = [Path(item).name for item in dataset]
        return namelist

    def get_name_list(self):
        no_check_list = [str(f.name)
                         for f in Path(self.path_list[0]).iterdir()]
        if len(no_check_list) > 100:
            self.dataset_mode = True
            return no_check_list
        else:
            self.dataset_mode = False
            return [str(f.name) for f in Path(self.path_list[0]).iterdir() if f.is_file() and f.suffix.lower() in self.format_group]

    def add(self):
        if self.action_count < self.max_action_num-1:
            self.action_count += 1
            self.img_count += self.count_per_action

    def subtract(self):
        if self.action_count > 0:
            self.action_count -= 1
            self.img_count -= self.count_per_action

    def set_count_per_action(self, count_per_action):
        self.count_per_action = count_per_action
        if self.img_num % self.count_per_action:
            self.max_action_num = int(self.img_num/self.count_per_action)+1
        else:
            self.max_action_num = int(self.img_num/self.count_per_action)

    def set_action_count(self, action_count):
        if action_count < self.max_action_num:
            self.action_count = action_count
            self.img_count = self.count_per_action*self.action_count

    def layout_advice(self):
        if self.csv_flag:
            return self.csv_row_col
        else:
            if self.type == 2:
                num_all = len(self.name_list)
            else:
                num_all = len(self.path_list)

            list_factor = solve_factor(num_all)

            if len(list_factor) == 0:
                row_col = [1, num_all]
            else:
                if len(list_factor) <= 1:
                    num_all = num_all+1
                    list_factor = solve_factor(num_all)
                row = list_factor[int(len(list_factor)/2)-1]
                row = int(row)
                col = int(num_all/row)
                if row < col:
                    row_col = [row, col]
                else:
                    row_col = [col, row]

            if row_col[0] >= 100:
                row_col[0] = 50

            if row_col[1] >= 100:
                row_col[1] = 50

            return row_col

    def get_flist(self):

        if self.type == 0 or self.type == 1:
            # one_dir_mul_dir_auto, one_dir_mul_dir_manual
            flist = []
            for i in range(len(self.path_list)):
                for k in range(self.img_count, self.img_count+self.count_per_action):
                    try:
                        flist += [str(Path(self.path_list[i]) /
                                      self.name_list[k])]
                    except:
                        flist += [str(Path(self.path_list[i]) /
                                      self.name_list[-1])]

        elif self.type == 2:
            # one_dir_mul_img
            try:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_num)]
        elif self.type == 3:
            # one file list
            #flist = self.path_list
            try:
                flist = [str(Path(self.path_list[i]))
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.path_list[i]))
                         for i in range(self.img_count, self.img_num)]
        else:
            flist = []

        self.flist = flist
        return flist


class ImgManager(ImgDatabase):
    """Multi-image manager.  
    Multi-image parallel magnification, stitching, saving, rotation"""

    def __init__(self):
        self.layout_params = []
        self.gap_color = (0, 0, 0, 0)
        self.img = ""
        self.gap_alpha = 255
        self.img_alpha = 255
        self.img_stitch_mode = 0  # 0:"fill" 1:"crop" 2:"resize"
        self.img_resolution = [-1, -1]
        self.custom_resolution = False
        self.img_num = 0
        self.format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"]
        self.crop_points = []
        self.draw_points = []
        self.ImgF = ImgUtils()

    def get_img_list(self):
        img_list = []
        for path in self.flist:
            path = Path(path)
            if path.is_file() and path.suffix.lower() in self.format_group:
                img_list.append(Image.open(path).convert('RGB'))
            else:
                pass
        # resolution
        width_ = []
        height_ = []
        for img in img_list:
            width, height = img.size
            width_.append(width)
            height_.append(height)
        width_ = np.sort(width_)
        height_ = np.sort(height_)

        if self.img_stitch_mode == 2:
            width = max(width_)
            height = max(height_)
        elif self.img_stitch_mode == 1:
            width = np.min(width_)
            height = np.min(height_)
        elif self.img_stitch_mode == 0:
            if len(width_) > 3:
                width = np.mean(width_[1:-1])
                height = np.mean(height_[1:-1])
            else:
                width = np.mean(width_)
                height = np.mean(height_)

        if self.layout_params[6][0] == -1 or self.layout_params[6][1] == -1:
            self.img_resolution_origin = [int(width), int(height)]
            self.custom_resolution = False
        else:
            self.img_resolution_origin = [int(i)
                                          for i in self.layout_params[6]]
            self.custom_resolution = True

        self.img_list = img_list

    def stitch_images(self, img_mode, draw_points=[]):
        """img_mode, 0: show, 1: save"""
        # init
        xy_grid = []
        self.get_img_list()  # Generate image list
        img_resolution = self.set_scale_mode(img_mode=img_mode)
        width, height = img_resolution
        img_num_per_row = self.layout_params[0]
        num_per_img = self.layout_params[1]
        img_num_per_column = self.layout_params[2]
        gap = self.layout_params[3]
        self.magnifier_flag = self.layout_params[7]
        self.show_box = self.layout_params[14]
        if img_mode:
            show_original = True
        else:
            show_original = self.layout_params[16]
        if img_mode == 0:
            self.draw_points = draw_points

        if len(draw_points) == 0:
            self.magnifier_flag = 0
        if self.magnifier_flag != 0:
            self.crop_points_process(draw_points, img_mode)

        # stitch img
        try:
            if self.layout_params[-1]:
                # Vertical
                img_num_per_column = img_num_per_row
                img_num_per_row = self.layout_params[2]
                if self.magnifier_flag == 0:
                    img = Image.new('RGBA', ((width * img_num_per_row + gap[1] * (img_num_per_row-1)), height * img_num_per_column * num_per_img + gap[0] * (
                        img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)
                else:
                    im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                        self.img_preprocessing(self.img_list[0]))
                    magnifier_width = im_magnifier_list[0].size[0]
                    magnifier_height = im_magnifier_list[0].size[1]

                    if show_original:
                        img = Image.new('RGBA', (img_num_per_row*(magnifier_width+width + gap[3]) + gap[1] * (img_num_per_row-1), height * img_num_per_column * num_per_img + gap[0] * (
                            img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)
                    else:
                        width = magnifier_width
                        height = magnifier_height
                        num_per_img = len(self.crop_points)
                        img = Image.new('RGBA', ((width * img_num_per_row + gap[1] * (img_num_per_row-1)), height * img_num_per_column * num_per_img + gap[0] * (
                            img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)

                for ix in range(img_num_per_row):
                    for ixx in range(self.magnifier_flag+1):
                        if self.magnifier_flag != 0 and show_original:
                            x = ix * (magnifier_width+width) + ixx * width + \
                                gap[3] * ixx + gap[1]*ix + gap[3]*ix

                        else:
                            x = ix * width + gap[1] * ix

                        for iyy in range(img_num_per_column):
                            for iy in range(num_per_img):
                                y = (iyy*num_per_img+iy) * \
                                    height+gap[0]*iyy+gap[2]*iy + \
                                    gap[2]*iyy*(num_per_img-1)
                                if show_original:
                                    if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(self.img_list):
                                        im = self.img_list[ix*(img_num_per_column *
                                                               num_per_img)+iyy*num_per_img+iy]
                                        im = self.img_preprocessing(im)
                                        if (ixx+1) % 2 == 0:
                                            if self.magnifier_flag != 0:
                                                im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                                    im)
                                                # adjust magnifier image gap
                                                i = 0
                                                res_ = (height - len(im_magnifier_list)*im_magnifier_list[0].size[1] - (
                                                    len(im_magnifier_list)-1)*gap[4]-2*delta_y)
                                                if len(im_magnifier_list) == 1:
                                                    res_a = 0
                                                else:
                                                    res_a = res_ / \
                                                        (len(im_magnifier_list)-1)
                                                add_ = 0
                                                add_gap = 0
                                                y_ = 0
                                                for im_magnifier in im_magnifier_list:
                                                    if i == 0:
                                                        y_ = y+delta_y
                                                    else:
                                                        y_ = y_ + \
                                                            im_magnifier.size[1] + \
                                                            gap[4]+add_gap
                                                    img.paste(
                                                        im_magnifier, (x, y_))
                                                    i += 1
                                                    add_ = add_+res_a
                                                    if add_ >= 1:
                                                        add_ -= 1
                                                        add_gap = 1
                                                    else:
                                                        add_gap = 0
                                        else:
                                            xy_grid.append([x, y])
                                            img.paste(im, (x, y))

                                else:
                                    if self.magnifier_flag != 0:
                                        im = self.img_list[ix *
                                                           (img_num_per_column)+iyy]
                                        im = self.img_preprocessing(im)

                                        im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                            im)
                                        img.paste(
                                            im_magnifier_list[iy], (x, y))
            else:
                # horizontal
                if self.magnifier_flag == 0:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)
                else:
                    im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                        self.img_preprocessing(self.img_list[0]))
                    magnifier_width = im_magnifier_list[0].size[0]
                    magnifier_height = im_magnifier_list[0].size[1]

                    if show_original:
                        img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                            img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), img_num_per_column*(magnifier_height+height + gap[3])+gap[1] * (img_num_per_column-1)), self.gap_color)
                    else:
                        width = magnifier_width
                        height = magnifier_height
                        num_per_img = len(self.crop_points)
                        img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                            img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)

                for iy in range(img_num_per_column):
                    for iyy in range(self.magnifier_flag+1):
                        if self.magnifier_flag != 0 and show_original:
                            y = iy * (height+magnifier_height) + iyy * height + \
                                gap[3] * iyy + gap[1]*iy + gap[3]*iy
                        else:
                            y = iy * height + gap[1] * iy

                        for ixx in range(img_num_per_row):
                            for ix in range(num_per_img):
                                x = (ixx*num_per_img+ix) * \
                                    width+gap[0]*ixx+gap[2]*ix + \
                                    gap[2]*ixx*(num_per_img-1)
                                if show_original:
                                    if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(self.img_list):
                                        im = self.img_list[iy*(img_num_per_row *
                                                               num_per_img)+ixx*num_per_img+ix]
                                        im = self.img_preprocessing(im)

                                        if (iyy+1) % 2 == 0:
                                            if self.magnifier_flag != 0:
                                                im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                                    im)
                                                # adjust magnifier image gap
                                                i = 0
                                                res_ = (width - len(im_magnifier_list)*im_magnifier_list[0].size[0] - (
                                                    len(im_magnifier_list)-1)*gap[4] - 2*delta_x)
                                                if len(im_magnifier_list) == 1:
                                                    res_a = 0
                                                else:
                                                    res_a = res_ / \
                                                        (len(im_magnifier_list)-1)
                                                add_ = 0
                                                add_gap = 0
                                                x_ = 0
                                                for im_magnifier in im_magnifier_list:
                                                    if i == 0:
                                                        x_ = x+delta_x
                                                    else:
                                                        x_ = x_ + \
                                                            im_magnifier.size[0] + \
                                                            gap[4]+add_gap
                                                    img.paste(
                                                        im_magnifier, (x_, y))
                                                    i += 1
                                                    add_ = add_+res_a
                                                    if add_ >= 1:
                                                        add_ -= 1
                                                        add_gap = 1
                                                    else:
                                                        add_gap = 0
                                        else:
                                            xy_grid.append([x, y])
                                            img.paste(im, (x, y))
                                else:
                                    if self.magnifier_flag != 0:
                                        im = self.img_list[iy *
                                                           (img_num_per_row)+ixx]
                                        im = self.img_preprocessing(im)

                                        im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                            im)
                                        img.paste(
                                            im_magnifier_list[ix], (x, y))

            # img = img.convert("RGBA")
            self.img = img
            self.xy_grid = xy_grid
            if self.show_box and len(draw_points) != 0:
                self.img = self.ImgF.draw_rectangle(
                    img, self.xy_grid, self.crop_points, self.layout_params[9], line_width=self.layout_params[10])
        except:
            return 1
        else:
            return 0

    def set_scale_mode(self, img_mode=0):
        """img_mode, 0: show, 1: save"""
        if img_mode == 0:
            self.scale = self.layout_params[4]
        elif img_mode == 1:
            self.scale = self.layout_params[5]
        self.img_resolution = (
            np.array(self.img_resolution_origin) * np.array(self.scale)).astype(np.int)

        if img_mode == 0:
            self.img_resolution_show = self.img_resolution
        elif img_mode == 1:
            self.img_resolution_save = self.img_resolution

        return self.img_resolution
        # self.gap = self.layout_params[3]
        # self.gap[0] = int(self.layout_params[3][0]*self.scale[0])
        # self.gap[1] = int(self.layout_params[3][1]*self.scale[1])
        # self.gap[2:] = (np.array(self.layout_params[3][2:])*np.array(self.scale[0])).astype(np.int)

    def img_preprocessing(self, img):
        if self.custom_resolution:
            # custom image resolution
            width, height = self.img_resolution
            img = img.resize((width, height), Image.BICUBIC)
        else:
            if self.img_stitch_mode == 2:
                width = int(self.scale[0]*img.size[0])
                height = int(self.scale[1]*img.size[1])
                img = img.resize((width, height), Image.BICUBIC)
            elif self.img_stitch_mode == 1:
                width, height = self.img_resolution
                (left, upper, right, lower) = (
                    (img.size[0]-width)/2, (img.size[1]-height)/2, (img.size[0]-width)/2+width, (img.size[1]-height)/2+height)
                img = img.crop((left, upper, right, lower))
            elif self.img_stitch_mode == 0:
                width, height = self.img_resolution
                img = img.resize((width, height), Image.BICUBIC)
        img = self.ImgF.add_alpha(img, self.img_alpha)

        return img

    def crop_points_process(self, crop_points, img_mode=0):
        """img_mode, 0: show, 1: save"""
        crop_points_ = []
        for crop_point_scale in crop_points:
            crop_point = crop_point_scale[0:4]
            show_scale_old = crop_point_scale[4:6]

            if self.layout_params[12]:
                width = crop_point[2]-crop_point[0]
                height = crop_point[3]-crop_point[1]
                center_x = crop_point[0]+int(width/2)
                center_y = crop_point[1]+int(height/2)
                if self.img_resolution[0]/width > self.img_resolution[1]/height:
                    height = int(
                        width*self.img_resolution[1]/self.img_resolution[0])
                else:
                    width = int(
                        height*self.img_resolution[0]/self.img_resolution[1])
                crop_point[0] = center_x - int(width/2)
                crop_point[2] = center_x + int(width/2)

                crop_point[1] = center_y-int(height/2)
                crop_point[3] = center_y+int(height/2)

            if img_mode == 1:
                show_scale = self.layout_params[5]
            else:
                show_scale = self.layout_params[4]
            scale = [show_scale[0]/show_scale_old[0],
                     show_scale[1]/show_scale_old[1]]

            crop_point[0] = int(crop_point[0]*scale[0])
            crop_point[1] = int(crop_point[1]*scale[1])
            crop_point[2] = int(crop_point[2]*scale[0])
            crop_point[3] = int(crop_point[3]*scale[1])

            crop_points_.append(crop_point)

        self.crop_points = crop_points_

    def sort_box_point(self, box_point, show_scale, first_point=False):
        # box_point = [x_0,y_0,x_1,y_1]
        if box_point[2] < box_point[0]:
            temp = box_point[0]
            box_point[0] = box_point[2]
            box_point[2] = temp
        if box_point[3] < box_point[1]:
            temp = box_point[1]
            box_point[1] = box_point[3]
            box_point[3] = temp

        img_resolution = (np.array(self.img_resolution_origin)
                          * np.array(show_scale)).astype(np.int)

        width = abs(box_point[0]-box_point[2])
        height = abs(box_point[1]-box_point[3])

        # limit box boundary
        if first_point:
            if box_point[2] > img_resolution[0]:
                box_point[2] = img_resolution[0]

            if box_point[0] < 0:
                box_point[0] = 0

            if box_point[3] > img_resolution[1]:
                box_point[3] = img_resolution[1]

            if box_point[1] < 0:
                box_point[1] = 0
        else:
            if box_point[2] > img_resolution[0]:
                box_point[2] = img_resolution[0]
                box_point[0] = img_resolution[0]-width
            elif box_point[0] < 0:
                box_point[0] = 0
                box_point[2] = width

            if box_point[3] > img_resolution[1]:
                box_point[3] = img_resolution[1]
                box_point[1] = img_resolution[1]-height
            elif box_point[1] < 0:
                box_point[1] = 0
                box_point[3] = height

        return box_point

    def magnifier_preprocessing(self, img, img_mode=0):
        """img_mode, 0: show, 1: save"""
        # crop images
        magnifier_scale = self.layout_params[8]
        img_list = []
        for crop_point in self.crop_points:
            img_list.append(img.crop(tuple(crop_point)))
        gap = self.layout_params[3][4]
        width, height = img_list[0].size
        delta_x = 0
        delta_y = 0

        # get to_resize
        if self.layout_params[-1] == 1:
            # vertical
            to_resize, delta_y = self.cal_magnifier_size(
                [magnifier_scale[1], magnifier_scale[0]], width, height, img_mode, gap, self.img_resolution[1], self.img_resolution[0])
            to_resize = [to_resize[1], to_resize[0]]
        else:
            # horizontal
            to_resize, delta_x = self.cal_magnifier_size(
                magnifier_scale, height, width, img_mode, gap, self.img_resolution[0], self.img_resolution[1])

        # resize images
        line_width = self.layout_params[10]
        color_list = self.layout_params[9]
        image_interp = self.layout_params[13]
        if image_interp == 1:
            interp_ = Image.LINEAR
        elif image_interp == 2:
            interp_ = Image.CUBIC
        else:
            interp_ = Image.NEAREST
        i = 0
        k = 0
        for img in img_list:
            img_list[i] = img.resize(tuple(to_resize), interp_)
            img_array = np.array(img_list[i])
            color = color_list[k]
            draw_colour = np.array(
                [color.red, color.green, color.blue, color.alpha])

            # magnifier image with box
            show_box_in_crop = self.layout_params[15]
            if show_box_in_crop:
                x_left_up = [0, 0]
                x_left_down = [0, img_list[i].size[1]]
                x_right_up = [img_list[i].size[0], 0]
                x_right_down = [img_list[i].size[0], img_list[i].size[1]]
                img_array[x_left_up[1]:x_left_down[1], x_left_up[0]:x_left_up[0]+line_width, :] = np.ones_like(
                    img_array[x_left_up[1]:x_left_down[1], x_left_up[0]:x_left_up[0]+line_width, :])*draw_colour
                img_array[x_left_up[1]:x_left_up[1]+line_width, x_left_up[0]:x_right_up[0], :] = np.ones_like(
                    img_array[x_left_up[1]:x_left_up[1]+line_width, x_left_up[0]:x_right_up[0], :])*draw_colour
                img_array[x_right_up[1]:x_right_down[1], x_right_up[0]-line_width:x_right_up[0], :] = np.ones_like(
                    img_array[x_right_up[1]:x_right_down[1], x_right_up[0]-line_width:x_right_up[0], :])*draw_colour
                img_array[x_left_down[1]-line_width:x_left_down[1], x_left_up[0]:x_right_up[0], :] = np.ones_like(
                    img_array[x_left_down[1]-line_width:x_left_down[1], x_left_up[0]:x_right_up[0], :])*draw_colour

            img_list[i] = Image.fromarray(
                img_array.astype('uint8')).convert('RGBA')
            i += 1
            k += 1
            if k == len(color_list):
                k = 0

        return img_list, delta_x, delta_y

    def cal_magnifier_size(self, magnifier_scale, height, width, img_mode, gap, img_width, img_height):
        delta_x = 0
        num_box = len(self.crop_points)

        if img_mode:
            gap = 0
            num_box = 1

        if not (magnifier_scale[0] == -1 or magnifier_scale[1] == -1):
            # custom magnifier scale
            to_height = int(height*magnifier_scale[1])
            to_width = int(width*magnifier_scale[0])
            width_all = (to_width*num_box +
                         (num_box-1)*gap)
            height_all = to_height

            if img_width/width_all > img_height/height_all:
                if to_height > img_height:
                    to_width = int(
                        img_height/to_height*to_width)
                    to_height = img_height
                width_all = (to_width*num_box +
                             (num_box-1)*gap)
                delta_x = int((img_width-width_all)/2)
            elif img_width/width_all == img_height/height_all:
                pass
            else:
                if width_all >= img_width:
                    to_height = int(
                        img_width/width_all*to_height)
                    to_width = int(
                        (img_width-gap*(num_box-1))/num_box)
                else:
                    width_all = (to_width*num_box +
                                 (num_box-1)*gap)
                    delta_x = int((img_width-width_all)/2)
        else:
            # auto magnifier scale
            to_width = int(
                (img_width-gap*(num_box-1))/num_box)
            to_height = int(to_width/width*height)
            if to_height > img_height:
                to_width = int(img_height/to_height*to_width)
                to_height = img_height
                width_all = (to_width*num_box +
                             (num_box-1)*gap)
                delta_x = int((img_width-width_all)/2)

        to_resize = [to_width, to_height]
        return to_resize, delta_x

    def rotate(self, id):
        img = Image.open(self.flist[id]).convert(
            'RGB').transpose(Image.ROTATE_270)
        img.save(self.flist[id])

    def save_img(self, out_path_str, out_type):
        self.check = []
        self.check_1 = []
        self.out_path_str = out_path_str
        self.set_scale_mode(img_mode=1)
        if out_path_str != "" and Path(out_path_str).is_dir():
            dir_name = [Path(path)._parts[-1] for path in self.path_list]
            out_type = out_type+1
            if out_type == 2:
                pass
            elif out_type == 1:
                dir_name = ["stitch_images"]
            elif out_type == 3:
                dir_name.append("stitch_images")
            elif out_type == 4:
                dir_name = ["magnifier_images"]
            elif out_type == 5:
                dir_name = ["stitch_images"]
                dir_name.append("magnifier_images")
            elif out_type == 6:
                dir_name.append("magnifier_images")
            elif out_type == 7:
                dir_name.append("stitch_images")
                dir_name.append("magnifier_images")

            if out_type == 2:
                self.save_select(dir_name)
            elif out_type == 1:
                self.save_stitch(dir_name[-1])
            elif out_type == 3:
                self.save_select(dir_name[0:-1])
                self.save_stitch(dir_name[-1])
            elif out_type == 4:
                self.save_magnifier(dir_name[-1])
            elif out_type == 5:
                self.save_stitch(dir_name[0])
                self.save_magnifier(dir_name[-1])
            elif out_type == 6:
                self.save_select(dir_name[0:-1])
                self.save_magnifier(dir_name[-1])
            elif out_type == 7:
                self.save_select(dir_name[0:-2])
                self.save_stitch(dir_name[-2])
                self.save_magnifier(dir_name[-1])

            # self.stitch_images(0,copy.deepcopy(self.draw_points))

            if sum(self.check) == 0:
                if sum(self.check_1) == 0:
                    return 0
                else:
                    return 2
            else:
                return 3
        else:
            return 1

    def save_select(self, dir_name):
        if self.type == 3:
            dir_name = ["from_file"]
            if not (Path(self.out_path_str)/"select_images"/dir_name[0]).exists():
                os.makedirs(Path(self.out_path_str) /
                            "select_images" / dir_name[0])
            for i_ in range(self.count_per_action):
                if self.action_count*self.count_per_action+i_ < len(self.path_list):
                    f_path = self.path_list[self.action_count *
                                            self.count_per_action+i_]
                    try:
                        i = 0
                        for stem in Path(f_path)._cparts:
                            if i == 0:
                                str_ = str(self.action_count *
                                           self.count_per_action+i_)+"_"+stem
                                i += 1
                            else:
                                str_ = str_+"_"+stem

                        if self.layout_params[11]:
                            move(f_path, Path(self.out_path_str) / "select_images" /
                                 dir_name[0] / str_)
                        else:
                            copyfile(f_path, Path(self.out_path_str) / "select_images" /
                                     dir_name[0] / str_)
                    except:
                        self.check.append(1)
                    else:
                        self.check.append(0)
        else:
            for i in range(len(dir_name)):
                if not (Path(self.out_path_str)/"select_images"/dir_name[i]).exists():
                    os.makedirs(Path(self.out_path_str) /
                                "select_images" / dir_name[i])

                f_path = self.flist[i]
                try:
                    if self.layout_params[11]:
                        move(f_path, Path(self.out_path_str) / "select_images" /
                             dir_name[i] / self.name_list[self.action_count])
                    else:
                        copyfile(f_path, Path(self.out_path_str) / "select_images" /
                                 dir_name[i] / self.name_list[self.action_count])
                except:
                    self.check.append(1)
                else:
                    self.check.append(0)

        if self.layout_params[11]:
            self.init(self.input_path, self.type,
                      self.action_count, self.img_count)
            self.get_flist()

    def save_stitch(self, dir_name):
        if self.type == 3:
            name_f = self.path_list[self.action_count*self.count_per_action]
            i = 0
            for stem in Path(name_f)._cparts:
                if i == 0:
                    str_ = str(self.action_count *
                               self.count_per_action)+"_"+stem
                    i += 1
                else:
                    str_ = str_+"_"+stem
            name_f = str_
        else:
            name_f = self.name_list[self.action_count]
        name_f = Path(name_f).with_suffix(".png")
        f_path_output = Path(self.out_path_str) / dir_name / name_f
        if not (Path(self.out_path_str)/dir_name).is_dir():
            os.makedirs(Path(self.out_path_str) / dir_name)
        if self.layout_params[7]:
            self.check_1.append(self.stitch_images(
                1, copy.deepcopy(self.draw_points)))
        else:
            self.check_1.append(self.stitch_images(1))

        self.img.save(f_path_output)

    def save_magnifier(self, dir_name):
        try:
            tmp = self.crop_points
        except:
            pass
        else:
            self.crop_points_process(copy.deepcopy(self.draw_points), 1)
            if self.type == 3:
                sub_dir_name = "from_file"
                if not (Path(self.out_path_str)/dir_name).exists():
                    os.makedirs(Path(self.out_path_str) / dir_name)
                if not (Path(self.out_path_str)/dir_name/sub_dir_name).exists():
                    os.makedirs(Path(self.out_path_str) /
                                dir_name/sub_dir_name)

                for i_ in range(self.count_per_action):
                    if self.action_count*self.count_per_action+i_ < len(self.path_list):
                        f_path = self.path_list[self.action_count *
                                                self.count_per_action+i_]
                        i = 0
                        img_name = ""
                        for stem in Path(f_path)._cparts:
                            if i == 0:
                                str_ = str(self.action_count *
                                           self.count_per_action+i_)+"_"+stem
                            else:
                                if i == len(Path(f_path)._cparts)-1:
                                    img_name = stem
                                else:
                                    str_ = str_+"_"+stem
                            i += 1

                        img = self.img_list[i_]
                        img_list, _, _ = self.magnifier_preprocessing(
                            self.img_preprocessing(img), img_mode=1)
                        i = 0
                        for img in img_list:
                            f_path_output = Path(
                                self.out_path_str) / dir_name/sub_dir_name / (str_+"_"+Path(img_name).stem+"_magnifier_"+str(i)+".png")
                            img.save(f_path_output)
                            i += 1
                # origin image with square
                self.save_origin_img_magnifier()
            else:
                i = 0
                for img in self.img_list:
                    img_list, _, _ = self.magnifier_preprocessing(
                        self.img_preprocessing(img), img_mode=1)
                    if not (Path(self.out_path_str)/dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                        os.makedirs(Path(self.out_path_str) / dir_name /
                                    (Path(self.flist[i]).parent).stem)
                    ii = 0
                    for img in img_list:
                        f_path_output = Path(self.out_path_str) / dir_name / (Path(self.flist[i]).parent).stem / (
                            (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+"_magnifier_"+str(ii)+".png")
                        img.save(f_path_output)
                        ii += 1
                    i += 1
                # origin image with square
                self.save_origin_img_magnifier()

    def save_origin_img_magnifier(self):
        # save origin image
        sub_dir_name = "origin_img_with_box"
        if not (Path(self.out_path_str)).exists():
            os.makedirs(Path(self.out_path_str))
        if not (Path(self.out_path_str)/sub_dir_name).exists():
            os.makedirs(Path(self.out_path_str) /
                        sub_dir_name)
        i = 0
        for img in self.img_list:
            img = self.img_preprocessing(img)
            img = self.ImgF.draw_rectangle(img, self.xy_grids, self.crop_points,
                                           self.layout_params[9], line_width=self.layout_params[10], single=True)
            f_path_output = Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem / (
                (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
            if not (Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                os.makedirs(Path(self.out_path_str) /
                            sub_dir_name/(Path(self.flist[i]).parent).stem)
            img.save(f_path_output)
            i += 1
