from types import DynamicClassAttribute
from numpy.lib.shape_base import split
import wx
import numpy as np
import os
from PIL import Image, ImageDraw, ImageFont
from shutil import copyfile, move
from pathlib import Path
import csv
import copy

from wx.core import Height, NO
from utils import solve_factor, change_order, rgb2hex


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

    def sort_box_point(self, box_point, show_scale, img_resolution_origin, first_point=False):
        # box_point = [x_0,y_0,x_1,y_1]
        if box_point[2] < box_point[0]:
            temp = box_point[0]
            box_point[0] = box_point[2]
            box_point[2] = temp
        if box_point[3] < box_point[1]:
            temp = box_point[1]
            box_point[1] = box_point[3]
            box_point[3] = temp

        img_resolution = (np.array(img_resolution_origin)
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
            x_0, y_0, x, y = bounding_box[0:4]
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

    def cal_magnifier_size(self, magnifier_scale, crop_size, img_mode, gap, img_size, num_box, show_original, vertical=False):
        delta_x = 0
        delta_y = 0
        width, height = crop_size
        img_width, img_height = img_size

        if img_mode:
            gap = 0
            num_box = 1

        if vertical:
            if not (magnifier_scale[0] == -1 or magnifier_scale[1] == -1):
                # custom magnifier scale
                to_height = int(height*magnifier_scale[1])
                to_width = int(width*magnifier_scale[0])
                height_all = to_height*num_box + (num_box-1)*gap
                width_all = to_width

                if img_height/height_all > img_width/width_all:
                    if to_width > img_width:
                        to_height = int(
                            img_width/to_width*to_height)
                        to_width = img_width
                else:
                    if height_all >= img_height:
                        to_width = int(
                            img_height/height_all*to_width)
                        to_height = int(
                            (img_height-gap*(num_box-1))/num_box)
            else:
                # auto magnifier scale
                to_height= int((img_height-gap*(num_box-1))/num_box)
                to_width = int(to_height/height*width)
                if to_width > img_width:
                    to_width = img_width
                    to_height = int(img_width/width*height) 
            height_all = (to_height*num_box +
                            (num_box-1)*gap)
            delta_y = int((img_height-height_all)/2)

            magnifier_img_all_size = [to_width, img_height] 

            if not show_original:
                magnifier_img_all_size=[to_width,height_all]
                delta_y=0
        else:
            if not (magnifier_scale[0] == -1 or magnifier_scale[1] == -1):
                # custom magnifier scale
                to_height = int(height*magnifier_scale[1])
                to_width = int(width*magnifier_scale[0])
                width_all = to_width*num_box + (num_box-1)*gap
                height_all = to_height

                if img_width/width_all > img_height/height_all:
                    if to_height > img_height:
                        to_width = int(
                            img_height/to_height*to_width)
                        to_height = img_height
                else:
                    if width_all >= img_width:
                        to_height = int(
                            img_width/width_all*to_height)
                        to_width = int(
                            (img_width-gap*(num_box-1))/num_box)
            else:
                # auto magnifier scale
                to_width = int((img_width-gap*(num_box-1))/num_box)
                to_height = int(to_width/width*height)
                if to_height > img_height:
                    to_height = img_height
                    to_width = int(img_height/height*width) 
            width_all = (to_width*num_box +
                            (num_box-1)*gap)
            delta_x = int((img_width-width_all)/2)

            magnifier_img_all_size = [img_width, to_height] 

            if not show_original:
                magnifier_img_all_size=[width_all,to_height]
                delta_x=0

        to_resize = [to_width, to_height]
        delta = [delta_x, delta_y]
        return to_resize, delta, magnifier_img_all_size

    def adjust_gap(self, target_length, number, length, gap, delta):
        """Adjust image gap. target_length>=sum(length)+sum(gap[0:-1])"""
        number = len(length)

        length_all = 0
        for i in range(number):
            length_all = length_all + length[i]
            if i == number-1:
                length_all = length_all + gap[i]

        res_ = (target_length - sum(length) - sum(gap[0:-1]) - 2*delta)
        if number == 1:
            res_a = 0
        else:
            res_a = res_ / (number-1)

        # Quantitative change causes qualitative change
        add_ = 0
        add_gap = 0
        for i in range(number):
            gap[i] = gap[i]+add_gap

            add_ = add_+res_a
            if add_ >= 1:
                add_ -= 1
                add_gap = 1
            else:
                add_gap = 0

        return gap

    def get_xy_grid(self, width, height, row, col, gap_x, gap_y):
        xy_grid = np.zeros((2, row, col)).astype(int)
        y = 0
        for iy in range(row):
            x = 0
            for ix in range(col):
                xy_grid[:, iy, ix] = [x, y]

                x = x + width[ix] + gap_x[ix]

            y = y + height[iy] + gap_y[iy]

        return xy_grid

    def reshape_higher_dim(self, row_cols, img_list, vertical):
        """It is currently in 4 dimensions, and can be expanded to higher dimensions by simply modifying the code."""
        id = 0
        size = []
        for i in range(len(row_cols)):
            row_col = row_cols[i]
            size = size+row_col
        output = np.zeros(tuple(size)).astype(object)

        for i in range(len(row_cols)):
            row_col = row_cols[i]
            if vertical:
                row_col.reverse()

        # level 0
        for iy_0 in range(row_cols[0][0]):
            for ix_0 in range(row_cols[0][1]):
                id_0 = [iy_0, ix_0]
                if vertical:
                    id_0.reverse()
                # level 1
                for iy_1 in range(row_cols[1][0]):
                    for ix_1 in range(row_cols[1][1]):
                        id_1 = [iy_1, ix_1]
                        if vertical:
                            id_1.reverse()
                        output[id_0[0], id_0[1], id_1[0],
                               id_1[1]] = img_list[id]
                        id += 1
        return output

    def layout_2d(self, layout_list, gap_color, img_list, img_preprocessing, img_preprocessing_sub, vertical):
        # Two-dimensional arrangement
        # layout_list = [
        #                 [[row_2,col_2],[gap_x_2,gap_y_2],[width_2,height_2],[target_width_2, target_height_2],discard_table_2],
        #                 [[row_1,col_1],[gap_x_1,gap_y_1],[width_1,height_1],[target_width_1, target_height_1],discard_table_1],
        #                 [[row_0,col_0],[gap_x_0,gap_y_0],[width_0,height_0],[target_width_0, target_height_0],discard_table_0],
        #                ]

        # Construct a two-dimensional grid
        # when i >=1, width layout[2] and layout[6] can be empty
        i = 0
        xy_grids = []
        for layout in layout_list:
            row, col = layout[0]
            gap_x, gap_y = layout[1]

            gap_x = [gap_x for i in range(col)]
            gap_y = [gap_y for i in range(row)]

            if i >= 1:
                width = [target_width for i in range(col)]
                height = [target_height for i in range(row)]
                layout[2] = [width, height]

                target_width = target_width*col+sum(gap_x[0:-1])
                target_height = target_height*row+sum(gap_y[0:-1])
                layout[3] = [target_width, target_height]
            else:
                width, height = layout[2]
                target_width, target_height = layout[3]

            xy_grids.append(self.get_xy_grid(
                width, height, row, col, gap_x, gap_y))

            i += 1

        # Construct a blank image
        img = Image.new('RGBA', (target_width, target_height), gap_color)

        # Fill the image
        layout_list.reverse()
        xy_grids.reverse()
        Row = dict()
        Col = dict()
        Discard_table = dict()
        for level in range(len(layout_list)):
            Row['level_{}'.format(level)] = layout_list[level][0][0]
            Col['level_{}'.format(level)] = layout_list[level][0][1]
            Discard_table['level_{}'.format(level)] = layout_list[level][4]

        # The number of img that a blank img can hold
        image_num_capacity = Row['level_0'] * \
            Col['level_0']*Row['level_1']*Col['level_1']

        for i in range(len(img_list)):
            img_list[i] = [img_list[i], i]

        if len(img_list) < image_num_capacity:
            empty_ = [[] for i in range(image_num_capacity-len(img_list))]
            img_list = img_list+empty_

        # Change the order of the image list
        img_list = self.reshape_higher_dim([[Row['level_0'], Col['level_0']], [
                                           Row['level_1'], Col['level_1']]], img_list, vertical)

        xy_grids_output = []
        # level_0
        for iy_0 in range(Row['level_0']):
            for ix_0 in range(Col['level_0']):
                level = 0
                x_offset_0 = xy_grids[level][0, iy_0, ix_0]
                y_offset_0 = xy_grids[level][1, iy_0, ix_0]

                # level_1
                for iy_1 in range(Row['level_1']):
                    for ix_1 in range(Col['level_1']):
                        level = 1
                        x_offset_1 = xy_grids[level][0, iy_1, ix_1]
                        y_offset_1 = xy_grids[level][1, iy_1, ix_1]

                        if Discard_table['level_0'][iy_0, ix_0] and Discard_table['level_1'][iy_1, ix_1]:
                            im = None
                        else:
                            # img preprocessing
                            if img_list[iy_0, ix_0, iy_1, ix_1] != []:
                                im = img_list[iy_0, ix_0, iy_1, ix_1][0]
                                im = img_preprocessing(im)

                                xy_grids_output.append(
                                    [x_offset_0+x_offset_1, y_offset_0+y_offset_1])
                            else:
                                im = None

                        if im:
                            # level_2
                            i = 0
                            for iy_2 in range(Row['level_2']):
                                for ix_2 in range(Col['level_2']):
                                    level = 2
                                    x_offset_2 = xy_grids[level][0, iy_2, ix_2]
                                    y_offset_2 = xy_grids[level][1, iy_2, ix_2]

                                    x = x_offset_0+x_offset_1+x_offset_2
                                    y = y_offset_0+y_offset_1+y_offset_2

                                    # img preprocessing
                                    if Discard_table['level_2'][iy_2, ix_2]:
                                        pass
                                    else:
                                        if img_preprocessing_sub[iy_2, ix_2] != []:
                                            im_ = img_preprocessing_sub[iy_2, ix_2](
                                                im, id=img_list[iy_0, ix_0, iy_1, ix_1][1])
                                            img.paste(im_, (x, y))
                                    i += 1

        return img, xy_grids_output

    def identity_transformation(self, img, id=0):
        return img

    def cal_txt_size(self, title_list, standard_size, font, font_size,vertical):
        im = Image.new('RGBA', (256, 256), 0)
        draw = ImageDraw.Draw(im)
        title_size = []
        for title in title_list:
            title_size.append(draw.multiline_textsize(title, font))
        title_size = np.array(title_size)
        title_size = title_size.reshape(-1, 2)
        # adjust title names
        for i in range(len(title_list)):
            split_num = 2
            title = title_list[i]
            str_ = title_list[i]
            while title_size[i, 0] > standard_size:
                ids = [0] + [(i+1)*int(len(title)/split_num)
                             for i in range(split_num-1)]
                str_ = ""
                k = 0
                for id in ids:
                    if k == 0:
                        str_ = str_ + title[id:ids[k+1]]
                    elif k+1 < len(ids):
                        str_ = str_ + "\n" + title[id:ids[k+1]]
                    else:
                        str_ = str_ + "\n"+title[id:]
                    k += 1
                size_edit = draw.multiline_textsize(str_, font)
                title_size[i, :] = size_edit
                split_num = split_num+1
                if split_num > len(title):
                    break
            title_list[i] = str_
        # re-calculate title size
        title_size = []
        for title in title_list:
            title_size.append(draw.multiline_textsize(title, font))
        title_size = np.array(title_size)
        title_size = title_size.reshape(-1, 2)
        # final title list
        title_list = title_list

        title_max_size = [standard_size,
                          (title_size[:, 1]).max()+int(font_size/4)]
        if vertical:
            title_max_size.reverse()
        return title_size, title_list, title_max_size


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

        self.img_resolution = self.img_resolution.tolist()
        return self.img_resolution

    def stitch_img_init(self, img_mode, draw_points):
        """img_mode, 0: show, 1: save"""
        # init
        self.get_img_list()  # Generate image list
        self.set_scale_mode(img_mode=img_mode)
        if img_mode == 0:
            self.draw_points = draw_points
        self.vertical = self.layout_params[-1]

        img_preprocessing_sub = []
        layout_level_2 = []
        width_2, height_2 = [[], []]

        # show original img
        self.show_original = self.layout_params[16]
        if self.show_original:
            layout_level_2.append(1)
            img_preprocessing_sub.append(self.ImgF.identity_transformation)
            width_2.append(self.img_resolution[0])
            height_2.append(self.img_resolution[1])
        else:
            layout_level_2.append(0)

        # show magnifier img
        self.magnifier_flag = self.layout_params[7]
        if len(draw_points) == 0:
            self.magnifier_flag = 0
        if self.magnifier_flag:
            layout_level_2.append(1)
            self.crop_points_process(copy.deepcopy(draw_points))
            # get magnifier size
            crop_width = self.crop_points[0][2]-self.crop_points[0][0]
            crop_height = self.crop_points[0][3]-self.crop_points[0][1]
            _, _, magnifier_img_all_size = self.ImgF.cal_magnifier_size(
                self.layout_params[8], [crop_width, crop_height], 0, self.layout_params[3][4], self.img_resolution, len(self.crop_points), self.show_original, vertical=self.vertical)
            img_preprocessing_sub.append(self.magnifier_preprocessing)
            width_2.append(magnifier_img_all_size[0])
            height_2.append(magnifier_img_all_size[1])
        else:
            layout_level_2.append(0)

        # show title
        self.title_setting = self.layout_params[17]
        if self.title_setting[1]:
            title_width_height = self.title_init(width_2,height_2)
            if self.title_setting[2]:
                # up
                width_2 = [title_width_height[0]]+width_2
                height_2 = [title_width_height[1]]+height_2
                img_preprocessing_sub = [
                    self.title_preprocessing] + img_preprocessing_sub
                layout_level_2 = [1]+layout_level_2
            else:
                # down
                width_2.append(title_width_height[0])
                height_2.append(title_width_height[1])
                img_preprocessing_sub.append(self.title_preprocessing)
                layout_level_2.append(1)
        else:
            layout_level_2.append(0)

        # Since the title is up, we need to correct crop_points
        if self.magnifier_flag:
            self.crop_points_process(copy.deepcopy(draw_points),title_up = self.title_setting[2])

        # Two-dimensional arrangement
        # arrangement of sub-images, title image, original image, magnifier image
        row_col2 = [sum(layout_level_2), 1]
        # num_per_img
        row_col1 = [1, self.layout_params[1]]
        # img_num_per_column,img_num_per_row
        row_col0 = [self.layout_params[2], self.layout_params[0]]

        gap_x_y_2 = [0, self.layout_params[3][3]]
        gap_x_y_1 = [self.layout_params[3][2], 0]
        gap_x_y_0 = [self.layout_params[3][0], self.layout_params[3][1]]

        if self.vertical:
            row_col2.reverse()
            row_col1.reverse()
            row_col0.reverse()

            gap_x_y_2.reverse()
            gap_x_y_1.reverse()
            gap_x_y_0.reverse()

        # width_2,height_2 = [[],[]]
        width_1, height_1 = [[], []]
        width_0, height_0 = [[], []]

        if self.vertical:
            target_width_2, target_height_2 = [
                sum(width_2)+gap_x_y_2[0]*(sum(layout_level_2)-1), height_2[0]]
        else:
            target_width_2, target_height_2 = [width_2[0], sum(
                height_2)+gap_x_y_2[1]*(sum(layout_level_2)-1)]
        target_width_1, target_height_1 = [0, 0]
        target_width_0, target_height_0 = [0, 0]

        discard_table_2 = np.zeros(tuple(row_col2))
        discard_table_1 = np.zeros(tuple(row_col1))
        discard_table_0 = np.zeros(tuple(row_col0))
        layout_list = [
            [row_col2, gap_x_y_2, [width_2, height_2], [
                target_width_2, target_height_2], discard_table_2],
            [row_col1, gap_x_y_1, [width_1, height_1], [
                target_width_1, target_height_1], discard_table_1],
            [row_col0, gap_x_y_0, [width_0, height_0], [
                target_width_0, target_height_0], discard_table_0],
        ]

        if len(img_preprocessing_sub) < row_col2[0]*row_col2[1]:
            empty_ = [[] for i in range(
                row_col2[0]*row_col2[1]-len(img_preprocessing_sub))]
            img_preprocessing_sub = img_preprocessing_sub+empty_
        temp_ = np.array(
            list(range(len(img_preprocessing_sub)))).astype(object)
        for i in range(len(img_preprocessing_sub)):
            temp_[i] = img_preprocessing_sub[i]
        img_preprocessing_sub = temp_.reshape(row_col2[0], row_col2[1])
        return layout_list, img_preprocessing_sub

    def stitch_images(self, img_mode, draw_points=[]):
        """img_mode, 0: show, 1: save"""
        # init
        layout_list, img_preprocessing_sub = self.stitch_img_init(
            img_mode, draw_points)

        # stitch img
        try:
            # Two-dimensional arrangement
            self.img, self.xy_grid = self.ImgF.layout_2d(
                layout_list, self.gap_color, copy.deepcopy(self.img_list), self.img_preprocessing, img_preprocessing_sub, self.vertical)

            self.show_box = self.layout_params[14]
            if self.show_original and self.show_box and len(draw_points) != 0:
                crop_points = self.crop_points
                offset = [self.title_max_size[0]+self.layout_params[3][3],self.title_max_size[1]+self.layout_params[3][3]]
                for crop_point in crop_points:
                    up = crop_point[-1] # down(False) or up(True)
                    if (up and self.title_setting[2] and self.title_setting[1]) or ((not up) and self.title_setting[2] and self.title_setting[1]):
                        if self.vertical:
                            crop_point[0] = crop_point[0]+offset[0]
                            crop_point[2] = crop_point[2]+offset[0]
                        else:
                            crop_point[1] = crop_point[1]+offset[1]
                            crop_point[3] = crop_point[3]+offset[1]
                self.img = self.ImgF.draw_rectangle(
                    self.img, self.xy_grid, crop_points, self.layout_params[9], line_width=self.layout_params[10])
        except:
            return 1
        else:
            return 0

    def title_preprocessing(self, img, id):
        title_max_size = copy.deepcopy(self.title_max_size)
        if self.vertical:
            title_max_size.reverse()
        img = Image.new('RGBA', tuple(title_max_size), self.gap_color)
        draw = ImageDraw.Draw(img)
        title_size = self.title_size[id, :]
        delta_x = int((title_max_size[0]-title_size[0])/2)
        if self.title_setting[2]:
            # up
            draw.multiline_text(
                (delta_x, 0), self.title_list[id], font=self.font, fill=self.text_color)
        else:
            # down
            draw.multiline_text(
                (delta_x, 0), self.title_list[id], font=self.font, fill=self.text_color)
        if self.vertical:
            img = img.transpose(Image.ROTATE_90)
        return img

    def title_init(self,width_2,height_2):
        # self.title_setting = self.layout_params[17]
        # title_setting = [self.title_auto.Value,                     # 0
        #                     self.title_show.Value,                     # 1
        #                     self.title_down_up.Value,                  # 2
        #                     self.title_show_parent.Value,              # 3
        #                     self.title_show_name.Value,                # 4
        #                     self.title_show_suffix.Value,              # 5
        #                     self.title_font.GetSelection(),            # 6
        #                     self.title_font_size.Value,                # 7
        #                     self.font_paths]                           # 8

        # get title
        title_list = []
        for path in self.flist:
            path = Path(path)
            if path.is_file() and path.suffix.lower() in self.format_group:
                title = ""
                if self.title_setting[3]:
                    title = title+path.parent.name
                if self.title_setting[4]:
                    if self.title_setting[3]:
                        title = title+"/"
                    title = title+path.stem
                if self.title_setting[5]:
                    title = title+path.suffix
                title_list.append(title)
        # get title color
        text_color = [255-self.gap_color[0], 255 -
                      self.gap_color[1], 255-self.gap_color[2]]
        text_color = ['%d' % i + "," for i in text_color]
        self.text_color = rgb2hex(("".join(text_color))[0:-1])
        # calculate title size
        font_size = int(self.title_setting[7])
        self.font = ImageFont.truetype(
            self.title_setting[8][self.title_setting[6]], font_size)
        if self.vertical:
            standard_size = height_2[0]
        else:
            standard_size = width_2[0]
        self.title_size, self.title_list, self.title_max_size = self.ImgF.cal_txt_size(
            title_list, standard_size, self.font, font_size,self.vertical)

        return self.title_max_size

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

    def crop_points_process(self, crop_points,title_up=False, img_mode=0):
        """img_mode, 0: show, 1: save"""
        crop_points_ = []
        for crop_point_scale in crop_points:
            crop_point_scale = copy.deepcopy(crop_point_scale)
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

            offset = [self.title_max_size[0]+self.layout_params[3][3],self.title_max_size[1]+self.layout_params[3][3]]

            if crop_point_scale[6]:
                if self.vertical:
                    crop_point[0] = crop_point[0]-offset[0]
                    crop_point[2] = crop_point[2]-offset[0]
                else:
                    crop_point[1] = crop_point[1]-offset[1]
                    crop_point[3] = crop_point[3]-offset[1]

            crop_point[0] = int(crop_point[0]*scale[0])
            crop_point[1] = int(crop_point[1]*scale[1])
            crop_point[2] = int(crop_point[2]*scale[0])
            crop_point[3] = int(crop_point[3]*scale[1])                
            crop_points_.append(crop_point+[crop_point_scale[6]])

        self.crop_points = crop_points_

    def magnifier_preprocessing(self, img, img_mode=0, id=0):
        """img_mode, 0: show, 1: save"""
        # crop images
        magnifier_scale = self.layout_params[8]
        img_list = []
        for crop_point in self.crop_points:
            crop_point = copy.deepcopy(crop_point)
            img_list.append(img.crop(tuple(crop_point[0:4])))

        gap = self.layout_params[3][4]

        # get the size of magnifier img
        to_resize, delta, magnifier_img_all_size = self.ImgF.cal_magnifier_size(
            magnifier_scale, list(img_list[0].size), img_mode, gap, self.img_resolution, len(self.crop_points),self.show_original, vertical=self.vertical)

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

        # stitch magnifier img
        img = Image.new('RGBA', tuple(magnifier_img_all_size), self.gap_color)
        gap = [gap for i in range(len(img_list))]
        width = [to_resize[0] for i in range(len(img_list))]
        height = [to_resize[1] for i in range(len(img_list))]
        if self.vertical:
            width = [0 for i in range(len(img_list))]
            height = [to_resize[1] for i in range(len(img_list))]
            gap_x = [0 for i in range(len(img_list))]
            gap_y = self.ImgF.adjust_gap(
                magnifier_img_all_size[1], len(img_list), height, gap, delta[1])
        else:
            width = [to_resize[0] for i in range(len(img_list))]
            height = [0 for i in range(len(img_list))]
            gap_x = self.ImgF.adjust_gap(
                magnifier_img_all_size[0], len(img_list), width, gap, delta[0])
            gap_y = [0 for i in range(len(img_list))]

        x = delta[0]
        y = delta[1]
        for i in range(len(img_list)):
            img.paste(img_list[i], (x, y))
            x = x + gap_x[i]+width[i]
            y = y + gap_y[i]+height[i]

        if img_mode:
            return img_list
        else:
            return img

    def save_img(self, out_path_str, out_type):
        self.check = []
        self.check_1 = []
        self.check_2 = []
        self.out_path_str = out_path_str
        if out_path_str != "" and Path(out_path_str).is_dir():
            self.set_scale_mode(img_mode=1)
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

            if sum(self.check) != 0:
                return 3

            if sum(self.check_1) != 0:
                return 2

            if sum(self.check_2) != 0:
                return 4
                
            return 0
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
            try:
                self.crop_points_process(copy.deepcopy(self.draw_points),title_up=self.title_setting[2], img_mode=1)
                if self.type == 3:
                    sub_dir_name = "from_file"
                    if not (Path(self.out_path_str)/dir_name).exists():
                        os.makedirs(Path(self.out_path_str) / dir_name)
                    if not (Path(self.out_path_str)/dir_name/sub_dir_name).exists():
                        os.makedirs(Path(self.out_path_str) /
                                    dir_name/sub_dir_name)
                    # origin image with box
                    self.save_origin_img_magnifier()

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
                            img_list = self.magnifier_preprocessing(
                                self.img_preprocessing(img), img_mode=1)
                            i = 0
                            for img in img_list:
                                f_path_output = Path(
                                    self.out_path_str) / dir_name/sub_dir_name / (str_+"_"+Path(img_name).stem+"_magnifier_"+str(i)+".png")
                                img.save(f_path_output)
                                i += 1
                else:
                    # origin image with box
                    self.save_origin_img_magnifier()
                    i = 0
                    for img in self.img_list:
                        img_list = self.magnifier_preprocessing(
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
            except:
                self.check_2.append(1)
            else:
                self.check_2.append(0)
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
            if self.show_box:
                img = self.ImgF.draw_rectangle(img, self.xy_grid, self.crop_points,
                                               self.layout_params[9], line_width=self.layout_params[10], single_box=True)
            f_path_output = Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem / (
                (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
            if not (Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                os.makedirs(Path(self.out_path_str) /
                            sub_dir_name/(Path(self.flist[i]).parent).stem)
            img.save(f_path_output)
            i += 1

    def rotate(self, id):
        img = Image.open(self.flist[id]).convert(
            'RGB').transpose(Image.ROTATE_270)
        img.save(self.flist[id])
