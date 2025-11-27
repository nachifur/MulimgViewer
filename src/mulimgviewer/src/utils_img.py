import copy
import json
import os
from pathlib import Path
from shutil import copyfile, move
import textwrap
from .custom_func.main import main as main_custom_func
import numpy as np
import piexif
import wx
from PIL import Image, ImageDraw, ImageFont
import imageio
import traceback
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

from .data import ImgData
from .utils import rgb2hex
from .custom_func.main import get_available_algorithms

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
                          * np.array(show_scale)).astype(np.int64)

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

    def draw_rectangle(self, img, xy_grids, bounding_boxes, color_list, line_width=2, single_box=False):
        """img
        xy_grids: the position of bounding_boxes (list)
        bounding_boxes: the four points that make up a bounding boxes
        color_list: the color of bounding_boxes
        """

        if single_box:
            xy_grids = [xy_grids[0]]
        else:
            xy_grids = xy_grids

        img_array = np.array(img)

        i = 0
        k = 0
        for bounding_box in bounding_boxes:
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

    def cal_magnifier_size(self, magnifier_scale, crop_size, img_mode, gap, img_size, magnifer_row_col, show_original,
                           box_position=0, row_col_img_unit=[1, 1], img_unit_gap=[1, 1],magnifier_format=0):
        delta_x = 0
        delta_y = 0
        width, height = crop_size
        img_width, img_height = img_size

        if img_mode:
            gap = [0, 0]
        if magnifier_scale[0] != -1 or magnifier_scale[1] != -1:
            if magnifier_scale[0] == -1:
                magnifier_scale[0] = magnifier_scale[1]
            if magnifier_scale[1] == -1:
                magnifier_scale[1] = magnifier_scale[0]
            # custom magnifier scale
            to_height = int(height * magnifier_scale[1])
            to_width = int(width * magnifier_scale[0])

            width_all = to_width * \
                        magnifer_row_col[1] + (magnifer_row_col[1] - 1) * gap[0]
            height_all = to_height * \
                         magnifer_row_col[0] + (magnifer_row_col[0] - 1) * gap[1]

            # if img_width / width_all > img_height / height_all:
            #     if to_height > img_height:
            #         to_width = int(
            #             img_height / height_all * to_width)
            #         to_height = int(
            #             (img_height - gap[1] * (magnifer_row_col[0] - 1)) / magnifer_row_col[0])
            #
            # else:
            #     if width_all >= img_width:
            #         to_height = int(
            #             img_width / width_all * to_height)
            #         to_width = int(
            #             (img_width - gap[0] * (magnifer_row_col[1] - 1)) / magnifer_row_col[1])

            if magnifier_format == 1:
                if row_col_img_unit[1] >= 2:
                    if (int(to_width) > int(img_width / magnifer_row_col[1])):
                        to_height = int(int(to_height) / int(to_width) * int(img_width / magnifer_row_col[1]))
                        to_width = int(img_width / magnifer_row_col[1])
                    if (int(to_height * magnifer_row_col[0]+gap[1]*(magnifer_row_col[0]-1)) > int(img_height)):
                        to_width = int(to_width / to_height * img_height / magnifer_row_col[0])
                        to_height = int((img_height-(magnifer_row_col[0]-1)*gap[1]) / magnifer_row_col[0])
                else:
                    if (int(to_width * magnifer_row_col[1] + gap[0] * (magnifer_row_col[1] - 1)) > int(img_width)):
                        to_height = int(int(to_height) / int(to_width) * int(img_width / magnifer_row_col[1]))
                        to_width = int((img_width - (magnifer_row_col[1] - 1) * gap[0]) / magnifer_row_col[1])
            elif magnifier_format == 2:
                if row_col_img_unit[1] == 1:
                    if (to_height > int(int(img_height) / int(magnifer_row_col[0]))):
                        to_width = int(int(to_width) / int(to_height) * int(int(img_height) / int(magnifer_row_col[0])))
                        to_height = int(int(img_height) / int(magnifer_row_col[0]))
                    if (int(to_width*magnifer_row_col[1] + gap[0]*(magnifer_row_col[1]-1)) > int(img_width)):
                        to_height =int(int(to_height) / int(to_width) * int(img_width / magnifer_row_col[1]))
                        to_width = int((img_width-(magnifer_row_col[1]-1)*gap[0]) / magnifer_row_col[1])
                else :
                    if (int(to_height * magnifer_row_col[0]+gap[1]*(magnifer_row_col[0]-1)) > int(img_height)):
                        to_width = int(int(to_width) / int(to_height) * int(int(img_height) / int(magnifer_row_col[0])))
                        to_height = int((img_height-(magnifer_row_col[0]-1)*gap[1]) / magnifer_row_col[0])


            else:
                if (int(to_height * magnifer_row_col[0]+gap[1]*(magnifer_row_col[0]-1)) > int(img_height)):
                    to_width =  int(int(to_width) / int(to_height) * int(img_height/ int(magnifer_row_col[0])))
                    to_height = int((img_height-(magnifer_row_col[0]-1)*gap[1]) / magnifer_row_col[0])
                if (int(to_width * magnifer_row_col[1] + gap[0] * (magnifer_row_col[1] - 1)) > int(img_width)):
                    to_height = int(int(to_height) / int(to_width) * int(img_width / magnifer_row_col[1]))
                    to_width = int((img_width - (magnifer_row_col[1] - 1) * gap[0]) / magnifer_row_col[1])
        else:
            # auto magnifier scale
            width_all = width * \
                        magnifer_row_col[1] + gap[0] * (magnifer_row_col[1] - 1)
            height_all = height * \
                         magnifer_row_col[0] + gap[1] * (magnifer_row_col[0] - 1)
            if img_width / width_all > img_height / height_all:
                to_height = int(  # img_height)
                    (img_height - gap[1] * (magnifer_row_col[0] - 1)) / magnifer_row_col[0])
                to_width = int(to_height / height * width)
            else:
                to_width = int(  # img_width)
                    (img_width - gap[0] * (magnifer_row_col[1] - 1)) / magnifer_row_col[1])
                to_height = int(to_width / width * height)
            if magnifier_format == 1:
                to_height = int(int(to_height) / int(to_width) * int(img_width/magnifer_row_col[1]))
                to_width = int((img_width - (magnifer_row_col[1] - 1) * gap[0])/magnifer_row_col[1])
                if row_col_img_unit[1] >= 2:
                    if (int(to_height * magnifer_row_col[0] + gap[1] * (magnifer_row_col[0] - 1)) > int(img_height)):
                        to_width = int(int(to_width) / int(to_height) * int(img_height / int(magnifer_row_col[0])))
                        to_height = int((img_height - (magnifer_row_col[0] - 1) * gap[1]) / magnifer_row_col[0])
            elif magnifier_format == 2:
                to_width = int(int(to_width) / int(to_height) * int(int(img_height)/int(magnifer_row_col[0])))
                to_height = int(int(img_height - (magnifer_row_col[0] - 1) * gap[1])/int(magnifer_row_col[0]))
                if row_col_img_unit[1] == 1:
                    if (int(to_width * magnifer_row_col[1] + gap[0] * (magnifer_row_col[1] - 1)) > int(img_width)):
                        to_height = int(int(to_height) / int(to_width) * int(img_width / magnifer_row_col[1]))
                        to_width = int((img_width - (magnifer_row_col[1] - 1) * gap[0]) / magnifer_row_col[1])
            else :
                if (int(to_height) > int(img_height)):
                    to_width = int(int(img_width) / int(to_height) * int(img_height))
                    to_height = img_height
                if (int(to_width) > int(img_width)):
                    to_height = int(int(img_height) / int(to_width) * int(img_width))
                    to_width = img_width

        width_all = to_width * magnifer_row_col[1] + gap[0] * (magnifer_row_col[1] - 1)
        height_all = to_height * \
                     magnifer_row_col[0] + gap[1] * (magnifer_row_col[0] - 1)

        magnifier_img_all_size = [width_all, height_all]

        if row_col_img_unit[1] == 1:
            # adjust box position
            if box_position == 0:  # middle bottom
                delta_y = 0
                delta_x = 0
            elif box_position == 1:  # left bottom
                delta_x = 0
                delta_y = -height_all
            elif box_position == 2:  # right bottom
                delta_x = img_width - width_all
                delta_y = -height_all
            elif box_position == 3:  # left top
                delta_x = 0
                delta_y = -img_height
            elif box_position == 4:  # right top
                delta_x = img_width - width_all
                delta_y = -img_height
        elif row_col_img_unit[0] == 1:
            # adjust box position
            if box_position == 0:  # middle bottom
                delta_y = int((img_height - height_all) / 2)
                delta_x = img_unit_gap[0]
            elif box_position == 2:  # right bottom
                delta_y = img_height - height_all
                delta_x = -to_width
            elif box_position == 1:  # left bottom
                delta_y = img_height - height_all
                delta_x = 0
            elif box_position == 4:  # right top
                delta_y = 0
                delta_x = -to_width
            elif box_position == 3:  # left top
                delta_y = 0
                delta_x = -img_width
        else:
            # adjust box position
            if box_position == 0:  # middle bottom
                delta_y = 0
                delta_x = 0
            elif box_position == 2:  # right bottom
                delta_y = img_height - height_all
                delta_x = -to_width
            elif box_position == 1:  # left bottom
                delta_y = img_height - height_all
                delta_x = -img_width
            elif box_position == 4:  # right top
                delta_y = 0
                delta_x = -to_width
            elif box_position == 3:  # left top
                delta_y = 0
                delta_x = -img_width

        if not show_original:
            delta_x = 0
            delta_y = 0

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
                length_all = length_all + gap

        res_ = (target_length - sum(length) - gap*(number-1) - 2*delta)
        if number == 1:
            res_a = 0
        else:
            res_a = res_ / (number-1)
        # Quantitative change causes qualitative change
        add_ = 0
        add_gap = 0
        gap_out = []
        for i in range(number):
            gap_out.append(gap + add_gap)

            add_ = add_+res_a
            if add_ >= 1:
                add_ -= 1
                add_gap = 0
            else:
                add_gap = 0

        return gap_out

    def get_xy_grid(self, width, height, row, col, gap_x, gap_y, per_gap=False):
        xy_grid = np.zeros((2, row, col)).astype(int)
        if per_gap:
            y = 0
            y0 = 0
            for iy in range(row):
                x = 0
                y0 = height[0:iy, 0].sum()+gap_y[0:iy, 0].sum()
                for ix in range(col):
                    x = x + gap_x[iy][ix]
                    y = y0 + gap_y[iy][ix]

                    xy_grid[:, iy, ix] = [x, y]

                    x = x + width[iy][ix]
        else:
            y = 0
            for iy in range(row):
                x = 0
                y = y + gap_y[iy]
                for ix in range(col):
                    x = x + gap_x[ix]

                    xy_grid[:, iy, ix] = [x, y]

                    x = x + width[ix]
                y = y + height[iy]
        return xy_grid

    def reshape_higher_dim(self, row_cols, img_list, vertical_list, type=object, levels=2):
        """It is currently in 4 dimensions, and can be expanded to higher dimensions by simply modifying the code."""
        id = 0
        size = []
        for i in range(len(row_cols)):
            row_col = row_cols[i]
            size = size+row_col
        output = np.zeros(tuple(size)).astype(type)

        for i in range(len(row_cols)):
            row_col = row_cols[i]
            if vertical_list[i]:
                row_col.reverse()

        if levels == 2:
            # level 0
            for iy_0 in range(row_cols[0][0]):
                for ix_0 in range(row_cols[0][1]):
                    id_0 = [iy_0, ix_0]
                    if vertical_list[0]:
                        id_0.reverse()
                    # level 1
                    for iy_1 in range(row_cols[1][0]):
                        for ix_1 in range(row_cols[1][1]):
                            id_1 = [iy_1, ix_1]
                            if vertical_list[1]:
                                id_1.reverse()
                            output[id_0[0], id_0[1], id_1[0],
                                   id_1[1]] = img_list[id]
                            id += 1
        elif levels == 1:
            # level 0
            for iy_0 in range(row_cols[0][0]):
                for ix_0 in range(row_cols[0][1]):
                    id_0 = [iy_0, ix_0]
                    if vertical_list[0]:
                        id_0.reverse()
                    output[id_0[0], id_0[1]] = img_list[id]
                    id += 1
        return output

    def layout_2d(self, layout_list, gap_color, img_list, img_preprocessing, img_preprocessing_sub, vertical_list, onetitle, title_func, title_hook=None):
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
        per_gap = [True, False, False]
        title_init_func = title_func[0]
        title_preprocessing=title_func[1]
        for layout in layout_list:
            row, col = layout[0]
            gap_x, gap_y = layout[1]

            if isinstance(gap_x, np.ndarray):
                pass
            else:
                gap_x = [0]+[gap_x for i in range(col-1)]
            if isinstance(gap_x, np.ndarray):
                pass
            else:
                gap_y = [0]+[gap_y for i in range(row-1)]

            if i >= 1:
                width = [target_width for i in range(col)]
                height = [target_height for i in range(row)]
                target_width = target_width*col+sum(gap_x[:])
                target_height = target_height*row+sum(gap_y[:])

                if onetitle and i==1:
                    title_max_size = title_init_func(target_width,target_height)
                    gap_add_new_title = gap_y[0]
                    target_height = target_height + title_max_size[1]+gap_y[0]

                layout[2] = [width, height]
                layout[3] = [target_width, target_height]
            else:
                width, height = layout[2]
                target_width, target_height = layout[3]

            xy_grids.append(self.get_xy_grid(
                width, height, row, col, gap_x, gap_y, per_gap=per_gap[i]))

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
                                           Row['level_1'], Col['level_1']]], img_list, vertical_list)

        xy_grids_output = []
        xy_grids_id_list = []
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
                                im = img_preprocessing(
                                    im, rowcol=[iy_1,ix_1])

                                xy_grids_output.append(
                                    [x_offset_0+x_offset_1, y_offset_0+y_offset_1])
                                xy_grids_id_list.append(
                                    img_list[iy_0, ix_0, iy_1, ix_1][1])
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
                                            func = img_preprocessing_sub[iy_2, ix_2]
                                            im_ = func(
                                                im, id=img_list[iy_0, ix_0, iy_1, ix_1][1])
                                            if im_:
                                                # if func == title_preprocessing:
                                                    # print("[PASTE TITLE cell]",
                                                    #     "level0", (iy_0, ix_0),
                                                    #     "level1", (iy_1, ix_1),
                                                    #     "level2", (iy_2, ix_2),
                                                    #     "paste_xy", (x, y),
                                                    #     "title_size", im_.size,
                                                    #     "base_img_size", img.size)
                                                img.paste(im_, (x, y))
                                                if title_hook and func == title_preprocessing:
                                                    title_hook(func.__self__, img_list[iy_0, ix_0, iy_1, ix_1][1], x, y)
                                    i += 1
                # show onetitle
                if onetitle:
                    if im:
                        level_title = 2
                        im_ = title_preprocessing(im, id=img_list[iy_0, ix_0, 0, 0][1])
                        if im_:
                            x_offset_2 = xy_grids[level_title][0, Row['level_2']-1, Col['level_2']-1]
                            y_offset_2 = xy_grids[level_title][1, Row['level_2']-1, Col['level_2']-1]

                            x = x_offset_0
                            y = y_offset_0+y_offset_1+y_offset_2+gap_add_new_title
                            img.paste(im_, (x, y))
                            if title_hook:
                                title_hook(title_preprocessing.__self__, img_list[iy_0, ix_0, 0, 0][1], x, y)

        return img, xy_grids_output, xy_grids_id_list

    def identity_transformation(self, img, id=0):
        return img

    def cal_txt_size_adjust_title(self, title_list, standard_size, font, font_size):
        im = Image.new('RGBA', (256, 256), 0)
        draw = ImageDraw.Draw(im)
        title_size = []
        for title in title_list:
            title_size.append(draw.multiline_textbbox((0,0),title, font))
        title_size = np.array(title_size)
        title_size = title_size.reshape(-1, 2)
        # adjust title names
        for i in range(len(title_list)):
            split_num = 2
            title = title_list[i]
            str_ = title_list[i]
            while title_size[i*2+1, 0] > standard_size:
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
                size_edit = draw.multiline_textbbox((0,0),str_, font)
                size_edit = np.array(size_edit)
                size_edit = size_edit.reshape(-1, 2)
                title_size[i*2+1, :] = size_edit[1,:]
                split_num = split_num+1
                if split_num > len(title):
                    break
            title_list[i] = str_
        # re-calculate title size
        title_size = []
        for title in title_list:
            title_size.append(draw.multiline_textbbox((0,0),title, font))
        title_size = np.array(title_size)
        title_size = title_size.reshape(-1, 2)
        # final title list
        title_list = title_list

        title_max_size = [standard_size,
                          (title_size[:, 1]).max()]
        return title_size, title_list, title_max_size

    def cat_img(self,img1,img2):
        target_width = img1.size[0]
        target_height = img1.size[1]+img2.size[1]
        img = Image.new('RGBA', (target_width, target_height))
        img.paste(img1,(0,0))
        img.paste(img2,(0,img1.size[1]))
        return img

    def save_img_diff_format(self, png_path,img,save_format=0,use_vector_titles=True):
        if save_format == 0:
            img.save(png_path, 'PNG')
        elif save_format == 2:
            rgb_img = img.convert('RGB')
            new_path = os.path.splitext(png_path)[0] + '.jpg'
            rgb_img.save(new_path, 'JPEG')
        else:
            new_path = os.path.splitext(png_path)[0] + '.pdf'
            manager = getattr(self, "manager", None) if use_vector_titles else None
            try:
                base_img = img.copy()
                if manager is None and hasattr(self, "img"):
                    manager = getattr(self, "manager_ref", None)
                if manager and getattr(manager, "pdf_title_layers", []):
                    manager.save_pdf_with_vector_text(new_path, base_img)
                else:
                    base_img.save(new_path, 'PDF')
            except ImportError:
                base_img.save(new_path, 'PDF')

class ImgManager(ImgData):
    """Multi-image manager.
    Multi-image parallel magnification, stitching, saving, rotation"""
    def __init__(self):
        self.layout_params = []
        self.gap_color = (0, 0, 0, 0)
        self.img = None
        self.customfunc_img = None
        self.gap_alpha = 255
        self.img_alpha = 255
        self.img_stitch_mode = 0  # 0:"fill" 1:"crop" 2:"resize"
        self.img_resolution = [-1, -1]
        self.custom_resolution = False
        self.img_num = 0
        self.format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif",".PNG", ".JPG", ".JPEG", ".BMP", ".TIFF", ".TIF"]
        self.crop_points = []
        self.draw_points = []
        self.ImgF = ImgUtils()
        self.ImgF.manager = self
        self.path_custom_func_path = ""
        self.full_exif_cache = {}
        self._full_mappings = None
        self._tag_mappings_cache = None
        self.exif_display_config = self.load_exif_display_config(force_reload=True)
        # PDF title/vector export state
        self.collect_pdf_layers = True
        self.pdf_title_layers = []
        self._last_title_layout = None
        self._pdf_font_cache = {}
        self._title_line_spacing = 4
    def _get_pdf_font_name(self, font_path):
        """
        Return the registered font name for the given font path to avoid registering the same font twice.
        """
        font_path = str(font_path)
        base_name = Path(font_path).stem.replace(" ", "_")
        if base_name in self._pdf_font_cache:
            return self._pdf_font_cache[base_name]
        try:
            registered_fonts = pdfmetrics.getRegisteredFontNames()
            if base_name not in registered_fonts:
                pdfmetrics.registerFont(TTFont(base_name, font_path))
            self._pdf_font_cache[base_name] = base_name
        except Exception as exc:
            # Log the exception but keep the fallback cache
            traceback.print_exc()
            print(f"[PDF Font Register Error] base_name={base_name}, font_path={font_path}, err={exc}")
            self._pdf_font_cache[base_name] = base_name
        return base_name

    def save_pdf_with_vector_text(self, pdf_path, base_img):
        if base_img.mode not in ('RGB', 'L', 'CMYK'):
            base_img = base_img.convert('RGB')
        else:
            base_img = base_img.copy()

        width, height = base_img.size
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(width, height))
        img_reader = ImageReader(base_img)
        pdf_canvas.drawImage(img_reader, 0, 0, width=width, height=height, mask='auto')

        set_fill_alpha = getattr(pdf_canvas, "setFillAlpha", None)

        for entry in getattr(self, "pdf_title_layers", []):
            if not entry.get("visible", True):
                continue

            font_name = self._get_pdf_font_name(entry.get("font_path", ""))
            font_size = entry.get("font_size", 12)
            pdf_canvas.setFont(font_name, font_size)

            # === Key: convert Pillow coordinates to ReportLab coordinates first ===
            # In Pillow: entry["y"] is the distance from the title block top-left to the top of the image (positive downward)
            # entry["height"] is the height of the title block
            # ReportLab: origin is bottom-left, positive Y goes up
            block_top_pillow = entry.get("y", 0)             # Title block top position in the image (Pillow)
            block_height = entry.get("height", 0)            # Title block height
            overflow = (block_top_pillow + block_height) - height  # height is the height of the full base image
            if overflow > 0:
                block_top_pillow -= overflow
            # Y coordinate of the block bottom edge in PDF coordinates
            block_bottom_pdf = height - (block_top_pillow + block_height)

            # === Background rectangle ===
            bg_rgb = entry.get("bg_rgb")
            bg_alpha = entry.get("bg_alpha", 0.0)
            if bg_rgb and bg_alpha > 0 and set_fill_alpha:
                set_fill_alpha(bg_alpha)
                pdf_canvas.setFillColorRGB(*bg_rgb)
                # Note: use block_bottom_pdf as the rectangle y
                rect_y = block_bottom_pdf
                rect_w = entry.get("width", 0) or entry.get("actual_width", 0) or 0
                pdf_canvas.rect(entry["x"], rect_y, rect_w, block_height, stroke=0, fill=1)
                set_fill_alpha(1.0)

            # === Text color ===
            pdf_canvas.setFillColorRGB(*entry.get("color_rgb", (0, 0, 0)))

            lines = entry.get("lines", [""])
            origin_x = entry.get("x", 0) + entry.get("delta_x", 0)
            line_offsets = entry.get("line_offsets", [])
            ascent = entry.get("ascent", font_size)
            descent = entry.get("descent", 0)
            spacing = entry.get("spacing", 0)

            # Compute default line spacing (used when line_offsets are missing or overflow)
            default_step = None
            if len(line_offsets) >= 2:
                steps = [line_offsets[i] - line_offsets[i - 1] for i in range(1, len(line_offsets))]
                if steps:
                    default_step = steps[-1]
            if default_step is None:
                default_step = ascent + descent + spacing

            # === Baseline position: block_bottom_pdf + baseline_local ===
            for idx, line in enumerate(lines):
                if idx < len(line_offsets):
                    baseline_local = line_offsets[idx]        # Distance from block top to baseline (includes padding_top)
                elif line_offsets:
                    baseline_local = line_offsets[-1] + default_step * (idx - len(line_offsets) + 1)
                else:
                    baseline_local = default_step * idx

                # Baseline y in ReportLab = block bottom + the line offset inside the block
                origin_y = height - (block_top_pillow + baseline_local)
                pdf_canvas.drawString(origin_x, origin_y, line if line else " ")


        pdf_canvas.save()

    def _hex_to_rgb01(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    def _rgba255_to_rgb01(self, rgba):
        if rgba is None:
            return None, 0.0
        if len(rgba) == 3:
            return tuple(channel / 255.0 for channel in rgba), 1.0
        return tuple(channel / 255.0 for channel in rgba[:3]), rgba[3] / 255.0

    def _title_capture_hook(self, manager, img_id, x, y):
        if not self.collect_pdf_layers:
            return
        layout = getattr(manager, "_last_title_layout", None)
        # Add a consistency guard
        if layout.get("source_id", None) not in (None, img_id):
            return
        if not layout:
            return
        bg_rgb, bg_alpha = self._rgba255_to_rgb01(layout.get("bg_rgba", (255, 255, 255, 0)))
        entry = {
            "text": layout.get("text", ""),
            "lines": layout.get("lines", []),
            "font_path": layout.get("font_path", ""),
            "font_size": layout.get("font_size", 12),
            "color_rgb": self._hex_to_rgb01(layout.get("color", "#000000")),
            "delta_x": layout.get("delta_x", 0),
            "line_offsets": copy.deepcopy(layout.get("line_offsets", [])),
            "ascent": layout.get("ascent", 0),
            "descent": layout.get("descent", 0),
            "spacing": layout.get("spacing", 0),
            "bg_rgb": bg_rgb,
            "bg_alpha": bg_alpha,
            "padding_top": layout.get("padding_top", 0),
            "padding_bottom": layout.get("padding_bottom", 0),
            "x": x,
            "y": y,
            "width": layout.get("actual_width", 0),
            "height": layout.get("actual_height", 0),
            "visible": True,
        }
        self.pdf_title_layers.append(entry)
        manager._last_title_layout = None
        # print("[CAPTURE]",
        #   "id", img_id,
        #   "x,y", x, y,
        #   "w,h", layout.get("actual_width"), layout.get("actual_height"),
        #   "padding_top", layout.get("padding_top"),
        #   "line_offsets", layout.get("line_offsets"),
        #   "ascent,descent", layout.get("ascent"), layout.get("descent"),
        #   "lines", layout.get("lines"))

    def get_img_list(self, show_custom_func=False):
        img_list = []
        # load img list
        name_list = []
        self.full_exif_cache = {}

        for i, path in enumerate(self.flist):
            path = Path(path)
            name_list.append(path.name)
            if path.is_file() and path.suffix.lower() in self.format_group:
                if path.suffix.lower() in [".tiff", ".tif"]:
                    img = imageio.imread(path)
                    if img.dtype != np.uint8:
                        img = (255 * img).astype(np.uint8)
                    pil_img = Image.fromarray(img)
                    img_list.append(pil_img.convert('RGB'))
                    self.full_exif_cache[i] = {"raw_exif": {}, "formatted_exif": {}, "has_exif": False}
                else:
                    img = Image.open(path).convert('RGB')
                    img_list.append(img)
                    self.full_exif_cache[i] = self.extract_complete_exif(path)
            else:
                self.full_exif_cache[i] = {"raw_exif": {}, "formatted_exif": {}, "has_exif": False}
        out_path_str = self.layout_params[33]
        # custom
        if show_custom_func:
            algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
            img_list = main_custom_func(img_list,out_path_str,name_list=name_list,algorithm_type=algorithm_type)
            # Ensure processed_img is saved when exporting images too
            # processed_img follows the current save format: write images when saving images, write PDF when saving PDF
            # try:
            #     save_format = self.layout_params[35] if len(self.layout_params) > 35 else 0
            #     if out_path_str:
            #         available_algorithms = get_available_algorithms()
            #         algorithm_name = available_algorithms[algorithm_type] if algorithm_type < len(available_algorithms) else "Unknown"
            #         processed_dir = Path(out_path_str) / "processing_function" / algorithm_name / "processed_img"
            #         processed_dir.mkdir(parents=True, exist_ok=True)
            #         for i_img, img in enumerate(img_list):
            #             if i_img < len(name_list):
            #                 img_name = name_list[i_img]
            #             else:
            #                 img_name = f"{i_img}.png"
            #             target_path = processed_dir / img_name
            #             self.ImgF.save_img_diff_format(target_path, img, save_format=save_format, use_vector_titles=False)
            # except Exception:
            #     pass
            # If saving as PDF, convert images in processed_img to PDF and remove originals
            # try:
            #     save_format = self.layout_params[35] if len(self.layout_params) > 35 else 0
            #     if save_format == 1 and out_path_str:
            #         available_algorithms = get_available_algorithms()
            #         algorithm_name = available_algorithms[algorithm_type] if algorithm_type < len(available_algorithms) else "Unknown"
            #         processed_dir = Path(out_path_str) / "processing_function" / algorithm_name / "processed_img"
            #         if processed_dir.exists():
            #             for img_path in list(processed_dir.glob("*")):
            #                 if img_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]:
            #                     try:
            #                         with Image.open(img_path) as im:
            #                             pdf_path = img_path.with_suffix(".pdf")
            #                             im.convert("RGB").save(pdf_path, "PDF")
            #                         img_path.unlink()
            #                     except Exception:
            #                         pass
            # except Exception:
            #     pass
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
            if self.layout_params[6][0] == -1 and self.layout_params[6][1] == -1:
                self.img_resolution_origin = [int(width), int(height)]
            elif self.layout_params[6][0] == -1 and self.layout_params[6][1] != -1:
                self.img_resolution_origin = [
                    int(width*self.layout_params[6][1]/height), int(self.layout_params[6][1])]
            elif self.layout_params[6][0] != -1 and self.layout_params[6][1] == -1:
                self.img_resolution_origin = [int(self.layout_params[6][0]), int(
                    height*self.layout_params[6][0]/width)]
            self.custom_resolution = False
        else:
            self.img_resolution_origin = [int(i)
                                          for i in self.layout_params[6]]
            self.custom_resolution = True

        self.img_list = img_list

    def get_all_func_img_list(self, show_all_func_layout, original_row_col=None, func_layout_vertical=False):
        if original_row_col:
            max_images_needed = original_row_col[0] * original_row_col[1]
        else:
            max_images_needed = len(self.flist)
        original_img_list = []
        name_list = []
        loaded_count = 0

        for path in self.flist:
            if loaded_count >= max_images_needed:
                break
            path = Path(path)
            name_list.append(path.name)
            if path.is_file() and path.suffix.lower() in self.format_group:
                if path.suffix.lower() in [".tiff", ".tif"]:
                    img = imageio.imread(path)
                    if img.dtype != np.uint8:
                        img = (255 * img).astype(np.uint8)
                    pil_img = Image.fromarray(img)
                    original_img_list.append(pil_img.convert('RGB'))
                else:
                    original_img_list.append(Image.open(path).convert('RGB'))
                loaded_count += 1
            else:
                pass

        available_algorithms = get_available_algorithms()
        all_func_img_lists = []
        out_path_str = self.layout_params[33]
        all_func_img_lists.append(original_img_list)
        for i, algorithm_name in enumerate(available_algorithms):
            pure_img_list = []
            for img in original_img_list:
                pure_img_list.append(img.copy())
            algorithm_img_list = main_custom_func(pure_img_list, out_path_str, name_list=name_list, algorithm_type=i)
            all_func_img_lists.append(algorithm_img_list)
        try:
            layout_row, layout_col = map(int, show_all_func_layout.split(','))
        except:
            layout_row, layout_col = 2, 2
        final_img_list = []
        num_images_per_set = len(original_img_list)

        if original_row_col:
            original_rows, original_cols = original_row_col
        else:
            try:
                import math
                original_rows = int(math.sqrt(num_images_per_set))
                original_cols = math.ceil(num_images_per_set / original_rows)
            except:
                original_rows = 1
                original_cols = num_images_per_set

        enable_group_arrangement = True
        if enable_group_arrangement:
            img_groups = []
            for orig_img_idx in range(num_images_per_set):
                group = []
                for func_idx in range(len(all_func_img_lists)):
                    if orig_img_idx < len(all_func_img_lists[func_idx]):
                        group.append(all_func_img_lists[func_idx][orig_img_idx])
                    elif len(original_img_list) > orig_img_idx:

                        group.append(original_img_list[orig_img_idx])
                img_groups.append(group)
            final_img_list = []
            total_rows = layout_row * original_rows
            total_cols = layout_col * original_cols
            for final_row in range(total_rows):
                for final_col in range(total_cols):
                    if func_layout_vertical:
                        func_row = final_row // original_rows
                        func_col = final_col // original_cols
                        func_idx = func_col * layout_row + func_row
                    else:
                        func_row = final_row // original_rows
                        func_col = final_col // original_cols
                        func_idx = func_row * layout_col + func_col
                    orig_row = final_row % original_rows
                    orig_col = final_col % original_cols
                    orig_img_idx = orig_row * original_cols + orig_col
                    if orig_img_idx < len(img_groups) and func_idx < len(img_groups[orig_img_idx]):
                        final_img_list.append(img_groups[orig_img_idx][func_idx])
                    else:
                        if len(original_img_list) > 0:
                            blank_img = Image.new('RGB', original_img_list[0].size, (255, 255, 255))
                            blank_img._is_blank = True
                            final_img_list.append(blank_img)
                        else:
                            blank_img = Image.new('RGB', (512, 512), (255, 255, 255))
                            blank_img._is_blank = True
                            final_img_list.append(blank_img)
        else:
            total_rows = original_rows * layout_row
            total_cols = layout_col * original_cols

            for final_row in range(total_rows):
                for final_col in range(total_cols):
                    orig_img_row = final_row // layout_row
                    orig_img_col = final_col // layout_col
                    func_row = final_row % layout_row
                    func_col = final_col % layout_col
                    orig_img_idx = orig_img_row * original_cols + orig_img_col
                    func_idx = func_row * layout_col + func_col
                    if orig_img_idx < num_images_per_set and func_idx < len(all_func_img_lists):
                        final_img_list.append(all_func_img_lists[func_idx][orig_img_idx])
                    else:
                        if len(original_img_list) > 0:

                            blank_img = Image.new('RGB', original_img_list[0].size, (255, 255, 255))
                            blank_img._is_blank = True
                            final_img_list.append(blank_img)
                        else:
                            blank_img = Image.new('RGB', (512, 512), (255, 255, 255))
                            blank_img._is_blank = True
                            final_img_list.append(blank_img)

        final_img_list_with_id = []
        for idx, img in enumerate(final_img_list):
            if enable_group_arrangement:
                final_row = idx // total_cols
                final_col = idx % total_cols
                orig_row = final_row % original_rows
                orig_col = final_col % original_cols
                orig_img_id = orig_row * original_cols + orig_col
            else:
                final_row = idx // total_cols
                final_col = idx % total_cols
                orig_img_row = final_row // layout_row
                orig_img_col = final_col // layout_col
                orig_img_id = orig_img_row * original_cols + orig_img_col
            if not hasattr(img, '_original_id'):
                img._original_id = orig_img_id
            final_img_list_with_id.append(img)
        return final_img_list_with_id

    def load_exif_display_config(self, force_reload=False):
        config_path = Path(__file__).parent.parent / "configs" / "exif_display_config.json"
        if force_reload or not hasattr(self, 'exif_display_config'):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.exif_display_config = config
                    self._initialize_tag_mappings(config)
                    return config
            except:
                default_config = {
                    "Make": True, "Model": True, "ExposureTime": True,
                    "FNumber": True, "ISOSpeedRatings": True, "FocalLength": True,
                    "CustomTitle": True
                }
            self.exif_display_config = default_config
            self._initialize_tag_mappings(default_config)
            return default_config
        else:
            return self.exif_display_config

    def load_full_mappings(self):
        if self._full_mappings is not None:
            return self._full_mappings
        config_path = Path(__file__).parent.parent / "configs" / "exif_tag_mappings.json"
        if not config_path.exists():
            self._full_mappings = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
            return self._full_mappings
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                mappings_json = json.load(f)
                self._full_mappings = {}
                for ifd_name, mapping in mappings_json.items():
                    self._full_mappings[ifd_name] = {
                        int(tag_id): field_name
                        for tag_id, field_name in mapping.items()
                    }
                return self._full_mappings
        except:
            self._full_mappings = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
            return self._full_mappings

    def get_complete_tag_mappings(self):
        if self._tag_mappings_cache is None:
            self._initialize_tag_mappings(self.exif_display_config)
        return self._tag_mappings_cache

    def _initialize_tag_mappings(self, config):
        enabled_fields = set(k for k, v in config.items() if v)
        enabled_fields.add("UserComment")
        full_mappings = self.load_full_mappings()
        self._tag_mappings_cache = full_mappings

    def extract_complete_exif(self, img_path):
        try:
            with Image.open(img_path) as img:
                if 'exif' not in img.info:
                    return {"raw_exif": {}, "formatted_exif": {}, "has_exif": False}
                exif_dict = piexif.load(img.info['exif'])
                formatted_exif = {}
                tag_mappings = self.get_complete_tag_mappings()
                enabled_fields = set(k for k, v in self.exif_display_config.items() if v)
                enabled_fields.add("UserComment")

                for ifd_name, ifd_data in exif_dict.items():
                    if ifd_name in tag_mappings and isinstance(ifd_data, dict):
                        mapping = tag_mappings[ifd_name]
                        for tag_id, value in ifd_data.items():
                            if tag_id in mapping:
                                field_name = mapping[tag_id]
                                if field_name in enabled_fields or field_name in ["UserComment"]:
                                    formatted_value = self.format_field_value(field_name, value)
                                    if formatted_value is not None:
                                        formatted_exif[field_name] = formatted_value

                for field_name, is_enabled in self.exif_display_config.items():
                    if is_enabled and field_name not in formatted_exif and field_name != "UserComment":
                        formatted_exif[field_name] = "N/A"

                if "UserComment" in formatted_exif:
                    formatted_exif["CustomTitle"] = formatted_exif["UserComment"]
                else:
                    formatted_exif["CustomTitle"] = "N/A"

                return {
                    "raw_exif": exif_dict,
                    "formatted_exif": formatted_exif,
                    "has_exif": True
                }
        except:
            return {"raw_exif": {}, "formatted_exif": {}, "has_exif": False}

    def format_field_value(self, field_name, value):
        try:
            if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                num, den = value.numerator, value.denominator
            elif isinstance(value, tuple) and len(value) == 2:
                num, den = value
            else:
                num, den = None, None

            if num is not None and den is not None:
                decimal_value = float(num) / float(den)

                if field_name == "FNumber":
                    return f"ƒ/{decimal_value:.1f}"
                elif field_name == "ExposureTime":
                    return f"1/{round(1/decimal_value)}s" if decimal_value < 1 else f"{decimal_value:.1f}s"
                elif field_name == "FocalLength":
                    return f"{decimal_value:.1f}mm"
                elif field_name == "ShutterSpeedValue":
                    return f"1/{round(2**decimal_value)}s" if decimal_value > 0 else f"{2**(-decimal_value):.1f}s"
                elif field_name == "ApertureValue":
                    return f"ƒ/{2**(decimal_value/2):.1f}"
                elif field_name == "ExposureBiasValue":
                    return f"{decimal_value:+.1f}EV" if decimal_value != 0 else "0EV"
                elif field_name == "MaxApertureValue":
                    return f"ƒ/{2**(decimal_value/2):.1f}"
                else:
                    return f"{decimal_value:.2f}"

            elif field_name in ["GPSLatitude", "GPSLongitude"]:
                def dms_to_str(dms):
                    deg = dms[0][0] / dms[0][1]
                    min_ = dms[1][0] / dms[1][1]
                    sec = dms[2][0] / dms[2][1]
                    return f"{deg:.0f}°{min_:.0f}'{sec:.2f}\""
                if isinstance(value, (list, tuple)) and len(value) == 3:
                    return dms_to_str(value)
                else:
                    return str(value)

            elif field_name == "ISOSpeedRatings":
                return f"ISO{value}"
            elif field_name == "FocalLengthIn35mmFilm":
                return f"{value}mm"
            elif field_name == "Flash":
                flash_modes = {0: "No Flash", 1: "Flash", 5: "Flash, No Return", 7: "Flash, Return"}
                return flash_modes.get(value, f"Flash({value})")
            elif field_name == "WhiteBalance":
                wb_modes = {0: "Auto", 1: "Daylight", 2: "Fluorescent", 3: "Tungsten"}
                return wb_modes.get(value, f"WB({value})")
            elif field_name == "ExposureProgram":
                exp_modes = {1: "Manual", 2: "Auto", 3: "Aperture Priority", 4: "Shutter Priority"}
                return exp_modes.get(value, f"Program({value})")
            elif field_name == "MeteringMode":
                meter_modes = {1: "Average", 2: "Center", 3: "Spot", 5: "Multi-segment"}
                return meter_modes.get(value, f"Metering({value})")
            elif field_name == "ExposureMode":
                return {0: "Auto", 1: "Manual", 2: "Auto Bracket"}.get(value, f"Mode({value})")
            elif field_name == "UserComment":
                try:
                    decoded = value.decode('utf-8', errors='ignore') if isinstance(value, bytes) else str(value)
                    try:
                        custom_data = json.loads(decoded)
                        return custom_data.get('custom_title', str(value))
                    except:
                        return decoded
                except:
                    return str(value)
            elif isinstance(value, bytes):
                return value.decode('utf-8', errors='ignore').strip()
            else:
                return str(value)
        except:
            return str(value) if value is not None else "N/A"

    def format_exif_display_complete(self, formatted_exif, custom_title, title_rename_enabled, original_filename):
        display_lines = []

        if hasattr(self, 'type') and self.type in [0, 1]:
            if hasattr(self, 'flist') and len(self.flist) > 0:
                current_img_index = getattr(self, '_current_processing_index', 0)
                if current_img_index < len(self.flist):
                    folder_name = Path(self.flist[current_img_index]).parent.name
                    if title_rename_enabled and custom_title and custom_title != "N/A":
                        display_lines.append(f"Name: {folder_name}")
                    else:
                        display_lines.append(f"Name: {folder_name}")
                else:
                    display_lines.append(f"Name: {original_filename}")
            else:
                display_lines.append(f"Name: {original_filename}")
        else:
            if title_rename_enabled and custom_title and custom_title != "N/A":
                display_lines.append(f"Name: {custom_title}")
            else:
                display_lines.append(f"Name: {original_filename}")

        for field_name, is_enabled in self.exif_display_config.items():
            if is_enabled and field_name not in ["UserComment", "CustomTitle"]:
                value = formatted_exif.get(field_name, "N/A")
                display_lines.append(f"{field_name}: {value}")

        return "\n".join(display_lines)

    def get_display_title_from_cache(self, img_index, original_title, title_rename_enabled):
        if not title_rename_enabled:
            return original_title
        exif_data = self.full_exif_cache.get(img_index, {"formatted_exif": {}, "has_exif": False})
        if exif_data["has_exif"]:
            custom_title = exif_data["formatted_exif"].get("CustomTitle", "N/A")
            if custom_title != "N/A" and custom_title.strip():
                path = Path(self.flist[img_index])
                title_parts = []
                if hasattr(self, 'type') and self.type in [0, 1]:
                    if self.title_setting[3]:
                        title_parts.append(custom_title)
                    if self.title_setting[5]:
                        if self.title_setting[3]:
                            title_parts.append("/")
                        name = path.stem
                        if not self.title_setting[4]:
                            try:
                                name = name.split("_", 1)[1]
                            except:
                                pass
                        title_parts.append(name)
                    if self.title_setting[6]:
                        title_parts.append(path.suffix)
                    return "".join(title_parts)
                else:
                    if self.title_setting[3]:
                        title_parts.append(path.parent.parts[-1])
                    if self.title_setting[5]:
                        if self.title_setting[3]:
                            title_parts.append("/")
                        title_parts.append(custom_title)
                    if self.title_setting[6]:
                        title_parts.append(path.suffix)
                    return "".join(title_parts)
        return original_title

    def update_image_exif_37510(self, img_path, new_title):
        try:
            if not img_path.lower().endswith(('.jpg', '.jpeg', '.tiff', '.tif')):
                return False
            img = Image.open(img_path)
            if 'exif' in img.info:
                try:
                    exif_dict = piexif.load(img.info['exif'])
                except:
                    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            else:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            user_comment_tag = 0x9286
            exif_dict["Exif"][user_comment_tag] = new_title.encode('utf-8')
            exif_bytes = piexif.dump(exif_dict)
            img.save(img_path, exif=exif_bytes)
            for i, path in enumerate(self.flist):
                if str(path) == str(img_path):
                    if i in self.full_exif_cache:
                        self.full_exif_cache[i]["formatted_exif"]["CustomTitle"] = new_title
                        self.full_exif_cache[i]["raw_exif"]["Exif"][user_comment_tag] = new_title.encode('utf-8')
                    break
            return True
        except:
            return False

    def update_exif_config(self, new_config):
        self.exif_display_config = new_config
        self._initialize_tag_mappings(new_config)

    def set_scale_mode(self, img_mode=0):
        """img_mode, 0: show, 1: save"""
        if img_mode == 0:
            self.scale = self.layout_params[4]
        elif img_mode == 1:
            self.scale = self.layout_params[5]
        self.img_resolution = (
            np.array(self.img_resolution_origin) * np.array(self.scale)).astype(np.int64)

        if img_mode == 0:
            self.img_resolution_show = self.img_resolution
        elif img_mode == 1:
            self.img_resolution_save = self.img_resolution

        self.img_resolution = self.img_resolution.tolist()
        return self.img_resolution

    def stitch_img_init(self, img_mode, draw_points, first_run=True):
        """img_mode, 0: show, 1: save"""
        # init
        show_all_func = len(self.layout_params) > 38 and self.layout_params[38]
        if show_all_func:

            current_row_col = self.layout_params[0].copy()
            show_all_func_layout = self.layout_params[39] if len(self.layout_params) > 39 else "2,2"
            func_layout_vertical = self.layout_params[40] if len(self.layout_params) > 40 else False
            self.img_list = self.get_all_func_img_list(show_all_func_layout, current_row_col, func_layout_vertical)

            self._blank_img_ids = set()
            for idx, img in enumerate(self.img_list):
                if hasattr(img, '_is_blank') and img._is_blank:
                    self._blank_img_ids.add(idx)

            layout_row, layout_col = map(int, show_all_func_layout.split(','))

            self.layout_params[0] = [current_row_col[0] * layout_row, current_row_col[1] * layout_col]

            self._show_all_func_enabled = True
            self._show_all_func_layout = (layout_row, layout_col)
            self._original_row_col = current_row_col
            self._func_layout_vertical = func_layout_vertical

        else:
            self._show_all_func_enabled = False
            self.get_img_list(show_custom_func=self.layout_params[32])  # Generate image list
        self.set_scale_mode(img_mode=img_mode)
        if img_mode == 0:
            self.draw_points = draw_points
        self.img_vertical = self.layout_params[24]
        self.one_img_vertical = self.layout_params[25]
        self.img_unit_vertical = self.layout_params[26]
        self.magnifer_vertical = self.layout_params[27]
        self.set_scale_mode(img_mode=img_mode)
        if img_mode == 0:
            self.draw_points = draw_points
        # Two-dimensional arrangement
        # row_col_img_unit:  title image, original image, magnifier image
        row_col2 = self.layout_params[2]
        # row_col_one_img
        row_col1 = self.layout_params[1]
        # row_col
        row_col0 = self.layout_params[0]

        img_preprocessing_sub = []
        layout_level_2 = []
        width_2, height_2 = [[], []]
        gap_x_y_2 = [[], []]

        # show original img
        self.show_original = self.layout_params[16]
        self.one_img = self.layout_params[20]
        one_img_sub_row_col = self.layout_params[1] if self.one_img else [1, 1]
        self.to_size = [
            int(self.img_resolution[0]/one_img_sub_row_col[1]), int(self.img_resolution[1]/one_img_sub_row_col[0])]
        if self.show_original:
            layout_level_2.append(1)
            img_preprocessing_sub.append(self.ImgF.identity_transformation)

            width_2.append(self.to_size[0])
            height_2.append(self.to_size[1])

            gap_x_y_2[0].append(0)
            gap_x_y_2[1].append(0)
        else:
            layout_level_2.append(0)
        # show magnifier img
        self.magnifier_flag = self.layout_params[7]
        self.show_crop = self.layout_params[18]
        if layout_level_2[0] == 0:
            self.box_position = 0
        else:
            self.box_position = self.layout_params[21]
        if len(draw_points) == 0:
            self.show_crop = 0
        if self.show_crop:
            layout_level_2.append(1)
            self.crop_points_process(copy.deepcopy(
                draw_points), img_mode=img_mode)
            # get magnifier size
            crop_width = self.crop_points[0][2]-self.crop_points[0][0]
            crop_height = self.crop_points[0][3]-self.crop_points[0][1]
            magnifer_row_col = self.layout_params[29]
            _, delta, magnifier_img_all_size = self.ImgF.cal_magnifier_size(
                self.layout_params[8], [crop_width, crop_height], 0, self.layout_params[3][6:8], self.to_size, magnifer_row_col, self.show_original, box_position=self.box_position, row_col_img_unit=self.layout_params[2], img_unit_gap=self.layout_params[3][4:6], magnifier_format=self.layout_params[34])
            img_preprocessing_sub.append(self.magnifier_preprocessing)

            if layout_level_2[0] == 0:
                gap_x_y_2[0].append(0)
                gap_x_y_2[1].append(0)
                width_2.append(magnifier_img_all_size[0])
                height_2.append(magnifier_img_all_size[1])
            else:
                if delta[0]<0 or delta[1]<0:
                    gap_x_y_2[0].append(delta[0])
                    gap_x_y_2[1].append(delta[1])
                else:
                    gap_x_y_2[0].append(0)
                    gap_x_y_2[1].append(0)
                if self.layout_params[21] == 0:
                    width_2.append(magnifier_img_all_size[0])
                    height_2.append(magnifier_img_all_size[1])
                else:
                    width_2.append(0)
                    height_2.append(0)
        else:
            layout_level_2.append(0)

        # show title
        self.title_setting = self.layout_params[17]
        self.onetitle = self.layout_params[30]
        if self.onetitle:
            if len(width_2) != 0:
                self.title_init(width_2[0], height_2[0])
        else:
            if self.title_setting[1]:
                if len(width_2) != 0:
                    title_width_height = self.title_init(width_2[0], height_2[0])
                    if self.title_setting[2]:
                        # up
                        width_2 = [title_width_height[0]]+width_2
                        height_2 = [title_width_height[1]]+height_2
                        img_preprocessing_sub = [
                            self.title_preprocessing] + img_preprocessing_sub
                        layout_level_2 = [1]+layout_level_2

                        gap_x_y_2[0] = [0,0]
                        gap_x_y_2[1] = [0,0]
                    else:
                        # down
                        width_2.append(title_width_height[0])
                        height_2.append(title_width_height[1])
                        img_preprocessing_sub.append(self.title_preprocessing)
                        layout_level_2.append(1)

                        gap_x_y_2[0].append(0)
                        gap_x_y_2[1].append(0)
                else:
                    layout_level_2.append(0)
            else:
                layout_level_2.append(0)

        # check gap
        gap_x_y_2_orignal = copy.deepcopy(gap_x_y_2)
        new_add_gap_rowcol_flag = [0 for i in range(sum(layout_level_2))]
        k = 0
        for i in range(len(gap_x_y_2_orignal[0])):
            if gap_x_y_2_orignal[0][i] < 0 or gap_x_y_2_orignal[1][i] < 0:
                if i < len(gap_x_y_2_orignal[0])-1:
                    gap_x_y_2[0] = gap_x_y_2[0][0:i+k+1]+[-gap_x_y_2_orignal[0][i]
                                                          if gap_x_y_2_orignal[0][i] < 0 else 0]+gap_x_y_2[0][i+k+1:]
                    gap_x_y_2[1] = gap_x_y_2[1][0:i+k+1]+[-gap_x_y_2_orignal[1][i]
                                                          if gap_x_y_2_orignal[1][i] < 0 else 0]+gap_x_y_2[1][i+k+1:]
                    width_2 = width_2[0:i+k+1]+[0]+width_2[i+k+1:]
                    height_2 = height_2[0:i+k+1]+[0]+height_2[i+k+1:]
                    img_preprocessing_sub = img_preprocessing_sub[0:i+k+1]+[
                        self.fill_func]+img_preprocessing_sub[i+k+1:]
                    new_add_gap_rowcol_flag = new_add_gap_rowcol_flag[0:i+k+1]+[0]+new_add_gap_rowcol_flag[i+k+1:]
                    new_add_gap_rowcol_flag[i+k]=1
                else:
                    gap_x_y_2[0] = gap_x_y_2[0][0:i+k+1]+[-gap_x_y_2_orignal[0]
                                                          [i] if gap_x_y_2_orignal[0][i] < 0 else 0]
                    gap_x_y_2[1] = gap_x_y_2[1][0:i+k+1]+[-gap_x_y_2_orignal[1]
                                                          [i] if gap_x_y_2_orignal[1][i] < 0 else 0]
                    width_2 = width_2[0:i+k+1]+[0]
                    height_2 = height_2[0:i+k+1]+[0]
                    img_preprocessing_sub = img_preprocessing_sub[0:i+k+1]+[
                        self.fill_func]
                    new_add_gap_rowcol_flag = new_add_gap_rowcol_flag[0:i+k+1]+[0]
                    new_add_gap_rowcol_flag[i+k]=1
                k += 1
        if len(gap_x_y_2[0]) < row_col2[0]*row_col2[1]:
            empty_ = [0 for i in range(
                row_col2[0]*row_col2[1]-len(gap_x_y_2[1]))]
            gap_x_y_2[1] = gap_x_y_2[1]+empty_
            empty_ = [0 for i in range(
                row_col2[0]*row_col2[1]-len(gap_x_y_2[0]))]
            gap_x_y_2[0] = gap_x_y_2[0]+empty_
            empty_ = [0 for i in range(row_col2[0]*row_col2[1]-len(width_2))]
            width_2 = width_2+empty_
            empty_ = [0 for i in range(row_col2[0]*row_col2[1]-len(height_2))]
            height_2 = height_2+empty_
            empty_ = [[] for i in range(
                row_col2[0]*row_col2[1]-len(img_preprocessing_sub))]
            img_preprocessing_sub = img_preprocessing_sub+empty_
            empty_ = [0 for i in range(row_col2[0]*row_col2[1]-len(new_add_gap_rowcol_flag))]
            new_add_gap_rowcol_flag = new_add_gap_rowcol_flag+empty_

        # Extended Dimension
        gap_x_y_2[1] = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], gap_x_y_2[1], [self.img_unit_vertical], type=int, levels=1)
        gap_x_y_2[0] = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], gap_x_y_2[0], [self.img_unit_vertical], type=int, levels=1)
        width_2 = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], width_2, [self.img_unit_vertical], type=int, levels=1)
        height_2 = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], height_2, [self.img_unit_vertical], type=int, levels=1)
        img_preprocessing_sub = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], img_preprocessing_sub, [self.img_unit_vertical], levels=1)
        new_add_gap_rowcol_flag = self.ImgF.reshape_higher_dim(
            [copy.deepcopy(row_col2)], new_add_gap_rowcol_flag, [self.img_unit_vertical], type=int, levels=1)

        # correct gap
        for row in range(row_col2[0]):
            for col in range(row_col2[1]):
                i = row*row_col2[1]+col
                if gap_x_y_2[1][row,col]>=0 and gap_x_y_2[1][row,col]<=self.layout_params[3][5] and gap_x_y_2[0][row,col]>=0 and gap_x_y_2[0][row,col]<=self.layout_params[3][4]:
                    if col!=0 and gap_x_y_2[0][row,col]==0 and i<sum(layout_level_2):
                        gap_x_y_2[0][row,col] = self.layout_params[3][4]

                    if row!=0 and gap_x_y_2[1][row,col]==0 and i<sum(layout_level_2):
                        gap_x_y_2[1][row,col] = self.layout_params[3][5]

                if self.box_position == 0 and i<sum(layout_level_2):
                    if height_2[row,col]<height_2[row][0]:
                        gap_x_y_2[1][row,col] = gap_x_y_2[1][row,col]+int((height_2[row][0]-height_2[row,col])/2)
                    else:
                        height_2[row,col]=height_2[row][0]
                    if width_2[row,col]<width_2[0][col]:
                        gap_x_y_2[0][row,col] = gap_x_y_2[0][row,col]+int((width_2[0][col]-width_2[row,col])/2)
                    else:
                        width_2[row,col]=width_2[0][col]
        # correct row_col2
        if self.box_position != 0 and first_run and np.argwhere(new_add_gap_rowcol_flag == 1).tolist():# Determine if new_add_gap_rowcol_flag is null
            row_col_ = np.argwhere(new_add_gap_rowcol_flag == 1).tolist()[0]
            if row_col_[0] > row_col_[1]:
                self.layout_params[2][0] = row_col2[0] + 1
            else:
                self.layout_params[2][1] = row_col2[1] + 1
            return self.stitch_img_init(img_mode, draw_points, first_run=False)

        if sum(layout_level_2) != 0:
            # Since the title is up, we need to correct crop_points
            if self.magnifier_flag:
                self.crop_points_process(copy.deepcopy(
                    draw_points), img_mode=img_mode)

            gap_x_y_1 = [self.layout_params[3][2], self.layout_params[3][3]]
            gap_x_y_0 = [self.layout_params[3][0], self.layout_params[3][1]]

            # width_2,height_2 = [[],[]]
            width_1, height_1 = [[], []]
            width_0, height_0 = [[], []]

            target_width_2, target_height_2 = [
                width_2[0, :].sum()+gap_x_y_2[0][0, :].sum(), height_2[:, 0].sum()+gap_x_y_2[1][:, 0].sum()]

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
            show_img = True
        else:
            layout_list = []
            show_img = False
            img_preprocessing_sub = []
        return layout_list, img_preprocessing_sub, show_img

    def stitch_images(self, img_mode, draw_points=[]):
        """img_mode, 0: show, 1: save"""
        # init
        layout_list, img_preprocessing_sub, show_img = self.stitch_img_init(
            img_mode, draw_points)
        if show_img:
            # stitch img
            # try:
                # Two-dimensional arrangement
            # Collect title layout for reuse in PDF vector output
            if self.collect_pdf_layers:
                self.pdf_title_layers.clear()
            self._last_title_layout = None
            title_hook = self._title_capture_hook if self.collect_pdf_layers else None
            self.img, self.xy_grid, self.xy_grids_id_list = self.ImgF.layout_2d(
                layout_list, self.gap_color, copy.deepcopy(self.img_list), self.img_preprocessing, img_preprocessing_sub, [self.img_vertical, self.one_img_vertical, self.img_unit_vertical],self.onetitle, [self.title_init,self.title_preprocessing], title_hook=title_hook)

            self.show_box = self.layout_params[14]
            if self.show_original and self.show_box and len(draw_points) != 0:
                crop_points = self.crop_points
                offset = [self.title_max_size[0]+self.layout_params[3]
                        [4], self.title_max_size[1]+self.layout_params[3][5]]
                for crop_point in crop_points:
                    up = crop_point[-1]  # down(False) or up(True)
                    if (up and self.title_setting[2] and self.title_setting[1]) or ((not up) and self.title_setting[2] and self.title_setting[1]):
                        crop_point[1] = crop_point[1]+offset[1]
                        crop_point[3] = crop_point[3]+offset[1]
                if hasattr(self, '_blank_img_ids') and self._blank_img_ids:
                    filtered_xy_grid = []
                    for idx, img_id in enumerate(self.xy_grids_id_list):
                        if img_id not in self._blank_img_ids:
                            filtered_xy_grid.append(self.xy_grid[idx])
                else:
                    filtered_xy_grid = self.xy_grid
                self.img = self.ImgF.draw_rectangle(
                    self.img, filtered_xy_grid, crop_points, self.layout_params[9], line_width=self.layout_params[10][0])
            if self.layout_params[32]:
                self.customfunc_img = self.img
        return 0
            # except:
            #     return 1
            # else:
            #     return 0
        # else:
        #     return 2


    def fill_func(self, img, id=None):
        return None

    def title_preprocessing(self, img, id):
        if hasattr(self, '_blank_img_ids') and id in self._blank_img_ids:
            return None
        if id >= len(self.title_list):
            id = 0
        title_max_size = copy.deepcopy(self.title_max_size)
        img = Image.new('RGBA', tuple(title_max_size), self.gap_color)
        draw = ImageDraw.Draw(img)
        original_id = id
        if hasattr(self, '_original_row_col') and len(self.layout_params) > 38 and self.layout_params[38]:
            show_all_func_layout = self.layout_params[39] if len(self.layout_params) > 39 else "2,2"
            func_layout_vertical = getattr(self, '_func_layout_vertical', False)
            try:
                layout_row, layout_col = map(int, show_all_func_layout.split(','))
                original_rows, original_cols = self._original_row_col
                total_cols = layout_col * original_cols
                final_row = id // total_cols
                final_col = id % total_cols
                orig_row = final_row % original_rows
                orig_col = final_col % original_cols
                original_id = orig_row * original_cols + orig_col
            except:
                original_id = 0

        if original_id >= len(self.title_list):
            original_id = 0

        if original_id * 2 + 1 >= self.title_size.shape[0]:
            original_id = 0

        line_height = int(self.title_setting[8])
        text = self.title_list[id]
        im_tmp = Image.new('RGBA', (title_max_size[0], 1000), self.gap_color)
        draw_tmp = ImageDraw.Draw(im_tmp)

        if "\n" not in text:
            bbox = draw_tmp.textbbox((0, 0), text, font=self.font)
        else:
            bbox = draw_tmp.multiline_textbbox((0, 0), text, font=self.font)

        actual_width = max(title_max_size[0], bbox[2] - bbox[0] + 20)
        actual_height = max(bbox[3] - bbox[1], 1)
        text_bbox_h = bbox[3] - bbox[1]

        # Fonts need at least a minimal height
        try:
            ascent, descent = self.font.getmetrics()
        except:
            ascent, descent = (0, 0)

        min_font_h = ascent + descent

        actual_height = max(text_bbox_h, min_font_h, 1)
        img = Image.new('RGBA', (actual_width, actual_height), self.gap_color)
        draw = ImageDraw.Draw(img)
        title_size = self.title_size[original_id*2+1, :]
        delta_x = max(0,int((title_max_size[0]-title_size[0])/2))
        # one_size = int(int(self.title_setting[8])/2)#int(title_size[0]/int(len(self.title_list[id])))
        # wrapper = textwrap.TextWrapper(width=int(int(title_max_size[0])/int(one_size)))
        # lines = self.title_list[id].split('\n')
        title_position=self.title_setting[10]
        if delta_x + title_size[0] >  title_max_size[0]:
            delta_x = 0
        title_position=self.title_setting[10]
        if title_position == 0:
            # left
            delta_x = 0
        elif title_position == 1:
            # center
            # delta_x = max(0,int((title_max_size[0]-title_size[0])/2))
            delta_x = max(0, int((actual_width - title_size[0]) / 2))
        elif title_position == 2:
            # right
            # delta_x = title_max_size[0]-title_size[0]
            delta_x = max(0, actual_width - title_size[0])

        draw.multiline_text((delta_x, -bbox[1]), text, align="left", font=self.font, fill=self.text_color)
        if self.collect_pdf_layers:
            lines = text.split("\n")
            spacing = getattr(self, "_title_line_spacing", 4)
            try:
                ascent, descent = self.font.getmetrics()
            except:
                ascent, descent = (0, 0)
            # calculate per-line offsets similar to Pillow rendering
            lines = text.split("\n")
            spacing = getattr(self, "_title_line_spacing", 4)

            try:
                ascent, descent = self.font.getmetrics()
            except:
                ascent, descent = (0, 0)

            lines = text.split("\n")

            baseline_offsets = []
            cursor_top = 0

            for line in lines:
                baseline_offsets.append(cursor_top + ascent)
                bbox_line = self.font.getbbox(line if line else " ")
                line_h = bbox_line[3] - bbox_line[1]
                cursor_top += line_h + spacing

            # Total text height (last line does not add extra spacing)
            text_total_h = cursor_top - spacing if lines else 0

            # On the Pillow side you call draw.multiline_text((delta_x, -bbox[1]), ...)
            # Keep this padding_top to match the downward shift
            padding_top = -bbox[1] if bbox[1] < 0 else 0
            padding_bottom = max(0, actual_height - (padding_top + text_total_h))

            # Final stored offsets = baseline offsets + padding_top
            line_offsets = [bo + padding_top for bo in baseline_offsets]

            bg_color = self.gap_color if len(self.gap_color) == 4 else tuple(list(self.gap_color) + [255])
            self._last_title_layout = {
                'source_id': id,
                "text": text,
                "lines": lines,
                "font_path": self.title_setting[9][self.title_setting[7]],
                "font_size": int(self.title_setting[8]),
                "color": self.text_color,
                "delta_x": delta_x,
                "line_offsets": line_offsets,
                "ascent": ascent,
                "descent": descent,
                "spacing": spacing,
                "bg_rgba": bg_color,
                "padding_top": padding_top,
                "padding_bottom": padding_bottom,
                "actual_width": actual_width,
                "actual_height": actual_height,
            }
        return img

    def title_init(self, width_2, height_2):
        # self.title_setting = self.layout_params[17]
        # title_setting = [self.title_auto.Value,                     # 0
        #                  self.title_show.Value,                     # 1
        #                  self.title_down_up.Value,                  # 2
        #                  self.title_show_parent.Value,              # 3
        #                  self.title_show_prefix.Value,              # 4
        #                  self.title_show_name.Value,                # 5
        #                  self.title_show_suffix.Value,              # 6
        #                  self.title_font.GetSelection(),            # 7
        #                  self.title_font_size.Value,                # 8
        #                  self.font_paths,                           # 9
        #                  self.title_position.GetSelection(),        # 10
        #                  self.title_exif.Value]                     # 11

        #  get title
        title_exif = self.title_setting[11]
        title_list = []
        if hasattr(self, 'layout_params') and len(self.layout_params) > 17:
            self.title_setting = self.layout_params[17]
        is_show_all_func = hasattr(self, '_show_all_func_enabled') and self._show_all_func_enabled

        if title_exif:
            for i, img in enumerate(self.img_list):
                if is_show_all_func:
                    if hasattr(img, '_original_id'):
                        original_id = img._original_id
                    else:
                        if hasattr(self, '_original_row_col'):
                            original_rows, original_cols = self._original_row_col
                            layout_row, layout_col = self._show_all_func_layout
                            total_cols = layout_col * original_cols
                            final_row = i // total_cols
                            final_col = i % total_cols
                            orig_row = final_row % original_rows
                            orig_col = final_col % original_cols
                            original_id = orig_row * original_cols + orig_col
                        else:
                            original_id = 0
                else:
                    original_id = i
                if original_id >= len(self.flist):
                    original_id = 0
                self._current_processing_index = original_id
                exif_data = self.full_exif_cache.get(original_id, {"formatted_exif": {}, "has_exif": False})

                if not exif_data["has_exif"]:
                    formatted_exif = {}
                    custom_title = "N/A"
                    title_rename_enabled = len(self.title_setting) > 12 and self.title_setting[12]
                    original_filename = Path(self.flist[original_id]).name
                    title = self.format_exif_display_complete(
                        formatted_exif, custom_title, title_rename_enabled, original_filename
                    )
                else:
                    formatted_exif = exif_data["formatted_exif"]
                    custom_title = formatted_exif.get("CustomTitle", "N/A")
                    title_rename_enabled = len(self.title_setting) > 12 and self.title_setting[12]
                    original_filename = Path(self.flist[original_id]).name
                    title = self.format_exif_display_complete(
                        formatted_exif, custom_title, title_rename_enabled, original_filename
                    )

                title_list.append(title)
        else:
            for i, path_or_img in enumerate(self.img_list if is_show_all_func else self.flist):
                if is_show_all_func:
                    if isinstance(path_or_img, Image.Image):
                        if hasattr(path_or_img, '_original_id'):
                            original_id = path_or_img._original_id
                        else:
                            if hasattr(self, '_original_row_col'):
                                original_rows, original_cols = self._original_row_col
                                layout_row, layout_col = self._show_all_func_layout
                                total_cols = layout_col * original_cols
                                final_row = i // total_cols
                                final_col = i % total_cols
                                orig_row = final_row % original_rows
                                orig_col = final_col % original_cols
                                original_id = orig_row * original_cols + orig_col
                            else:
                                original_id = 0
                    else:
                        original_id = i

                    if original_id >= len(self.flist):
                        original_id = 0

                    path = Path(self.flist[original_id])
                else:
                    path = Path(path_or_img)
                    original_id = i

                if path.is_file() and path.suffix.lower() in self.format_group:
                    title = ""
                    if self.title_setting[3]:
                        title = title + path.parent.parts[-1]
                    if self.title_setting[5]:
                        if self.title_setting[3]:
                            title = title + "/"
                        name = path.stem
                        if not self.title_setting[4]:
                            try:
                                name = name.split("_", 1)[1]
                            except:
                                pass
                        title = title + name
                    if self.title_setting[6]:
                        title = title + path.suffix
                    title_rename_enabled = len(self.title_setting) > 12 and self.title_setting[12]
                    final_title = self.get_display_title_from_cache(original_id, title, title_rename_enabled)
                    title_list.append(final_title)

            if len(title_list) < len(self.img_list):
                title_list += [""] * (len(self.img_list) - len(title_list))

        self.title_list = title_list
        # get title color
        text_color = [255-self.gap_color[0], 255 -
                      self.gap_color[1], 255-self.gap_color[2]]
        text_color = ['%d' % i + "," for i in text_color]
        self.text_color = rgb2hex(("".join(text_color))[0:-1])
        # calculate title size
        font_size = int(self.title_setting[8])
        self.font = ImageFont.truetype(
            self.title_setting[9][self.title_setting[7]], font_size)
        standard_size = width_2
        self.title_size, self.title_list, self.title_max_size = self.ImgF.cal_txt_size_adjust_title(
            title_list, standard_size, self.font, font_size)

        return self.title_max_size

    def img_preprocessing(self, img, rowcol=[1,1]):
        is_blank = hasattr(img, '_is_blank') and img._is_blank
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

        # n img -> one img, split width
        if self.one_img:
            sub_img_width = int(width/self.layout_params[1][1])
            sub_img_height = int(height/self.layout_params[1][0])
            img = np.array(img)
            img = img[rowcol[0]*sub_img_height:(rowcol[0]+1)*sub_img_height,
                      rowcol[1]*sub_img_width:(rowcol[1]+1)*sub_img_width, :]
            img = Image.fromarray(np.uint8(img))

        if is_blank:
            img._is_blank = True
        return img

    def crop_points_process(self, crop_points, img_mode=0):
        """img_mode, 0: show, 1: save"""
        crop_points_ = []
        for crop_point_scale in crop_points:
            crop_point_scale = copy.deepcopy(crop_point_scale)
            crop_point = crop_point_scale[0:4]
            show_scale_old = crop_point_scale[4:6]

            # KeepSize
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

            # magnifer_resolution
            magnifer_resolution = self.layout_params[28]
            if magnifer_resolution[0]==-1 and magnifer_resolution[1]==-1:
                is_to_magnifer_resolution = False
            elif magnifer_resolution[0]==-1:
                is_to_magnifer_resolution = True
                magnifer_resolution[0] = magnifer_resolution[1]
            elif magnifer_resolution[1]==-1:
                is_to_magnifer_resolution = True
                magnifer_resolution[1] = magnifer_resolution[0]
            else:
                is_to_magnifer_resolution = True
            if is_to_magnifer_resolution:
                width = crop_point[2]-crop_point[0]
                height = crop_point[3]-crop_point[1]
                center_x = crop_point[0]+int(width/2)
                center_y = crop_point[1]+int(height/2)

                width = magnifer_resolution[0]
                height = magnifer_resolution[1]

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

            offset = [self.title_max_size[0]+self.layout_params[3]
                      [4], self.title_max_size[1]+self.layout_params[3][5]]

            if crop_point_scale[6]:
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
        is_blank = False
        if hasattr(self, '_blank_img_ids') and id in self._blank_img_ids:
            is_blank = True
        if hasattr(img, '_is_blank') and img._is_blank:
            is_blank = True
        if is_blank:
            if img_mode:
                return []
            else:
                return None

        # crop images
        if img_mode:
            magnifier_scale = self.layout_params[31]
        else:
            magnifier_scale = self.layout_params[8]
        img_list = []
        for crop_point in self.crop_points:
            crop_point = copy.deepcopy(crop_point)
            img_list.append(img.crop(tuple(crop_point[0:4])))

        gap = self.layout_params[3][6:8]

        # get the size of magnifier img
        magnifer_row_col = self.layout_params[29]
        to_resize, delta, magnifier_img_all_size = self.ImgF.cal_magnifier_size(
            magnifier_scale, list(img_list[0].size), img_mode, gap, self.to_size, magnifer_row_col, self.show_original, box_position=self.box_position, row_col_img_unit=self.layout_params[2], img_unit_gap=self.layout_params[3][4:6], magnifier_format=self.layout_params[34])

        # resize images
        line_width = self.layout_params[10][1]
        color_list = self.layout_params[9]
        image_interp = self.layout_params[13]
        if image_interp == 1:
            interp_ = Image.BILINEAR
        elif image_interp == 2:
            interp_ = Image.BICUBIC
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

        if img_mode:
            return img_list

        # stitch magnifier img
        img = Image.new('RGBA', tuple(magnifier_img_all_size), self.gap_color)
        gap = self.layout_params[3][6:8]
        magnifer_row_col = self.layout_params[29]
        width = [to_resize[0] for i in range(magnifer_row_col[1])]
        height = [to_resize[1] for i in range(magnifer_row_col[0])]

        gap_x = self.ImgF.adjust_gap(
            self.to_size[0], magnifer_row_col[1], width, gap[0], delta[0])
        gap_y = self.ImgF.adjust_gap(
            self.to_size[1], magnifer_row_col[0], height, gap[1], delta[1])

        if len(img_list) < magnifer_row_col[0]*magnifer_row_col[1]:
            empty_ = [[] for i in range(
                magnifer_row_col[0]*magnifer_row_col[1]-len(img_list))]
            img_list = img_list+empty_
        # Change the order of the image list
        magnifer_vertical = self.layout_params[27]
        img_list = self.ImgF.reshape_higher_dim([copy.deepcopy(magnifer_row_col)], img_list, [
                                                magnifer_vertical], levels=1)

        y = 0
        for row in range(magnifer_row_col[0]):
            x = 0
            for col in range(magnifer_row_col[1]):
                if img_list[row, col] != []:
                    img.paste(img_list[row, col], (x, y))
                x = gap_x[col]*(col+1)+width[col]*(col+1)
            y = gap_y[row]*(row+1)+height[row]*(row+1)

        return img

    def save_img(self, out_path_str, out_type):
        self.check = []
        self.check_1 = []
        self.check_2 = []
        self.out_path_str = out_path_str
        try:
            if out_path_str != "" and Path(out_path_str).exists():
                # If a custom algorithm is enabled and saving as images, generate the processed_img directory first
                try:
                    save_format = self.layout_params[35] if len(self.layout_params) > 35 else 0
                    if save_format != 1 and len(self.layout_params) > 32 and self.layout_params[32]:
                        available_algorithms = get_available_algorithms()
                        algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
                        algorithm_type = min(algorithm_type, len(available_algorithms) - 1) if available_algorithms else 0
                        name_list_proc = []
                        img_list_proc = []
                        for path in self.flist:
                            p = Path(path)
                            name_list_proc.append(p.name)
                            if p.is_file() and p.suffix.lower() in self.format_group:
                                img = Image.open(p).convert('RGB')
                                img_list_proc.append(img)
                        if img_list_proc:
                            main_custom_func(img_list_proc, out_path_str, name_list=name_list_proc, algorithm_type=algorithm_type)
                except Exception:
                    pass
                self.set_scale_mode(img_mode=1)
                dir_name = [Path(path).parent.name for path in self.flist]
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
                    dir_name = ["stitch_images","magnifier_images"]
                elif out_type == 6:
                    dir_name.append("magnifier_images")
                elif out_type == 7:
                    dir_name.append("stitch_images")
                    dir_name.append("magnifier_images")

                show_all_func = len(self.layout_params) > 38 and self.layout_params[38]
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
                    if show_all_func:
                        original_custom_func = self.layout_params[32]
                        original_show_all_func = self.layout_params[38]
                        original_row_col = self.layout_params[0].copy()
                        self.layout_params[32] = False
                        self.layout_params[38] = False
                        if hasattr(self, '_original_row_col') and self._original_row_col:
                            self.layout_params[0] = self._original_row_col.copy()
                        self.save_stitch(dir_name[-2])
                        self.save_magnifier(dir_name[-1])
                        self.layout_params[32] = original_custom_func
                        self.layout_params[38] = original_show_all_func
                        self.layout_params[0] = original_row_col
                    else:
                        self.save_stitch(dir_name[-2])
                        self.save_magnifier(dir_name[-1])
                if show_all_func:
                    self.save_all_func_images(out_type)
                if sum(self.check) != 0:
                    return 3
                if sum(self.check_1) != 0:
                    return 2
                if sum(self.check_2) != 0:
                    return 4
                return 0
            else:
                return 1
        except:
            return 5

    def save_select(self, dir_name):
        paths_to_save = []
        base_origin = Path(self.out_path_str) / "processing_function" / "origin"
        paths_to_save.append(("origin", base_origin))
        if self.layout_params[32]:
            available_algorithms = get_available_algorithms()
            algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
            if algorithm_type < len(available_algorithms):
                algorithm_name = available_algorithms[algorithm_type]
                base_algorithm = Path(self.out_path_str) / "processing_function" / algorithm_name
                paths_to_save.append((algorithm_name, base_algorithm))
            try:
                self.get_img_list(show_custom_func=True)
            except:
                pass

        for path_label, base_path in paths_to_save:
            if self.type == 3:  # read file list from a list file
                dir_name_local = ["from_file"]
                base_select = base_path / "select_images" / dir_name_local[0]
                if not base_select.exists():
                    os.makedirs(base_select)
                save_format = self.layout_params[35] if len(self.layout_params) > 35 else 0
                for i_ in range(self.count_per_action):
                    if self.action_count * self.count_per_action + i_ < len(self.path_list):
                        idx = self.action_count * self.count_per_action + i_
                        try:
                            f_path = self.path_list[idx]
                            str_ = Path(f_path).parent.stem + "_" + Path(f_path).name
                            target_path = base_select / str_
                            if save_format == 1:
                                img = Image.open(f_path).convert("RGB")
                                self.ImgF.save_img_diff_format(target_path, img, save_format=1, use_vector_titles=False)
                            else:
                                copyfile(f_path, target_path)
                        except:
                            self.check.append(1)
                        else:
                            self.check.append(0)
            else:  # type 0, 1, 2
                if not self.parallel_to_sequential:
                    save_format = self.layout_params[35] if len(self.layout_params) > 35 else 0
                    for i in range(len(dir_name)):
                        if self.layout_params[22]:  # parallel_sequential
                            num_per_img = self.layout_params[1][0] * self.layout_params[1][1]
                        else:
                            num_per_img = 1
                        base_idx = i * num_per_img
                        if base_idx >= len(self.flist):
                            break
                        select_dir = base_path / "select_images" / dir_name[i]
                        if not select_dir.exists():
                            os.makedirs(select_dir)
                        for k in range(num_per_img):
                            idx = base_idx + k
                            if idx >= len(self.flist):
                                break
                            try:
                                f_path = self.flist[idx]
                                name = Path(f_path).name
                                if save_format == 1:
                                    img = Image.open(f_path).convert("RGB")
                                    target_path = select_dir / name
                                    self.ImgF.save_img_diff_format(target_path, img, save_format=1, use_vector_titles=False)
                                else:
                                    if self.layout_params[11]:  # move_file
                                        if path_label == paths_to_save[-1][0]:
                                            move(f_path, select_dir / name)
                                        else:
                                            copyfile(f_path, select_dir / name)
                                    else:
                                        copyfile(f_path, select_dir / name)
                            except:
                                pass
                                self.check.append(1)
                            else:
                                self.check.append(0)
        if self.layout_params[11]:
            if self.action_count == 0:
                action_count = 0
            else:
                action_count = self.action_count - 1
            self.init(self.input_path, self.type,
                      action_count=action_count, img_count=self.img_count - 1)
            self.get_flist()

    def save_stitch(self, dir_name):
        name_f = self.get_stitch_name()
        if self.type == 3: # read file list from a list file
            name_f = "from_file_"+name_f
        if self.layout_params[32]:
            available_algorithms = get_available_algorithms()
            algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
            if algorithm_type < len(available_algorithms):
                algorithm_name = available_algorithms[algorithm_type]
            else:
                algorithm_name = "Unknown"
            stitch_dir = Path(self.out_path_str) / "processing_function" / algorithm_name / "stitch_images"
            if not stitch_dir.exists():
                os.makedirs(stitch_dir)
        else:
            stitch_dir = Path(self.out_path_str) / "processing_function" / "origin"/ dir_name
            if not stitch_dir.exists():
                os.makedirs(stitch_dir)
        if self.layout_params[7]:
            self.check_1.append(self.stitch_images(
                1, copy.deepcopy(self.draw_points)))
        else:
            if self.show_box:
                self.check_1.append(self.stitch_images(
                    1, copy.deepcopy(self.draw_points)))
            else:
                self.check_1.append(self.stitch_images(1))
        if self.layout_params[32]:
            f_path_output_customfunc = stitch_dir / name_f
            self.ImgF.save_img_diff_format(f_path_output_customfunc,self.customfunc_img,save_format=self.layout_params[35])
        else:
            f_path_output = stitch_dir / name_f
            self.ImgF.save_img_diff_format(f_path_output,self.img,save_format=self.layout_params[35])

    def show_stitch_img_and_customfunc_img(self, show_custom_func):
        show_unit = self.layout_params[36]
        img = self.img
        if show_custom_func and self.customfunc_img != None:
            if show_unit and show_custom_func:
                img = self.ImgF.cat_img(self.img, self.customfunc_img)
            elif not show_unit and show_custom_func:
                img = self.customfunc_img
            elif show_unit and not show_custom_func:
                img = img
        return img

    def save_stitch_img_and_customfunc_img(self, out_path_str, show_custom_func):
        self.out_path_str = out_path_str
        name_f = self.get_stitch_name()
        if self.type == 3: # read file list from a list file
            name_f = "from_file_"+name_f
        base_dir = Path(self.out_path_str)/ "stitch_img_and_customfunc_img"
        if not base_dir.exists():
            os.makedirs(base_dir)
        original_row_col = self.layout_params[0].copy()
        original_show_all_func = self.layout_params[38] if len(self.layout_params) > 38 else False
        if original_show_all_func and hasattr(self, '_original_row_col') and self._original_row_col:
            self.layout_params[0] = self._original_row_col.copy()
        if self.layout_params[7]:
            self.check_1.append(self.stitch_images(
                1, copy.deepcopy(self.draw_points)))
        else:
            if self.show_box:
                self.check_1.append(self.stitch_images(
                    1, copy.deepcopy(self.draw_points)))
            else:
                self.check_1.append(self.stitch_images(1))
        # capture origin stitch result and title layers
        origin_img = self.img.copy() if self.img else None
        origin_titles = copy.deepcopy(getattr(self, "pdf_title_layers", []))

        custom_img = None
        custom_titles = []
        if show_custom_func:
            # run custom func stitch
            self.layout_params[32] = True
            self.get_img_list(show_custom_func=True)
            if self.layout_params[7]:
                self.check_1.append(self.stitch_images(1, copy.deepcopy(self.draw_points)))
            else:
                if self.show_box:
                    self.check_1.append(self.stitch_images(1, copy.deepcopy(self.draw_points)))
                else:
                    self.check_1.append(self.stitch_images(1))
            custom_img = self.img.copy() if self.img else None
            custom_titles = copy.deepcopy(getattr(self, "pdf_title_layers", []))

        # restore layout params
        self.layout_params[0] = original_row_col
        if len(self.layout_params) > 32:
            self.layout_params[32] = False

        # compose final image and title layers
        img = origin_img
        merged_titles = []
        merged_titles.extend(origin_titles)
        if show_custom_func and custom_img:
            if self.layout_params[36]:
                # stack origin on top of custom
                offset_y = origin_img.size[1] if origin_img else 0
                shifted = copy.deepcopy(custom_titles)
                for entry in shifted:
                    entry["y"] = entry.get("y", 0) + offset_y
                merged_titles.extend(shifted)
                img = self.ImgF.cat_img(origin_img, custom_img)
            else:
                img = custom_img
                merged_titles = custom_titles

        f_path_output = base_dir / name_f
        if img:
            self.pdf_title_layers = merged_titles
            self.ImgF.save_img_diff_format(f_path_output, img, save_format=self.layout_params[35], use_vector_titles=True)

    def get_stitch_name(self):
        name_first = self.flist[0]
        name_end = self.flist[-1]
        if self.type == 0 or self.type == 1: # one_dir_mul_dir_auto or one_dir_mul_dir_manual
            name_first = Path(name_first).parent.stem+"_"+Path(name_first).stem
        else:
            name_first = Path(name_first).stem
        if self.type == 0 or self.type == 1: # one_dir_mul_dir_auto or one_dir_mul_dir_manual
            name_end = Path(name_end).parent.stem+"_"+Path(name_end).stem
        else:
            name_end = Path(name_end).stem
        name = name_first + "-" + name_end
        name = Path(name).with_suffix(".png")
        if self.layout_params[23]:
            # when automatically saving
            return str(Path(name_first).with_suffix(".png"))
        else:
            return str(name)

    def save_magnifier(self, dir_name):
        if not self.layout_params[32]:
            base_path = Path(self.out_path_str) / "processing_function" / "origin" / dir_name
            if not base_path.exists():
                os.makedirs(base_path)
        try:
            tmp = self.crop_points
        except:
            pass
        else:
            has_draw_points = hasattr(self, 'draw_points') and self.draw_points and len(self.draw_points) > 0
            if not has_draw_points:
                self.check_2.append(0)
                return
            try:
                if self.layout_params[32]:
                    available_algorithms = get_available_algorithms()
                    algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
                    if algorithm_type < len(available_algorithms):
                        algorithm_name = available_algorithms[algorithm_type]
                    else:
                        algorithm_name = "Unknown"
                    base_custom_path = Path(self.out_path_str) / "processing_function" /algorithm_name / "magnifier_images"
                else:
                    base_custom_path = Path(self.out_path_str) / "processing_function" / "origin" / dir_name
                self.get_img_list(show_custom_func=self.layout_params[32])
                self.crop_points_process(copy.deepcopy(self.draw_points), img_mode=1)
                if self.type == 3: # read file list from a list file
                    sub_dir_name = "from_file"
                    if self.layout_params[32]:
                        if not base_custom_path.exists():
                            os.makedirs(base_custom_path)
                        if not (base_custom_path/sub_dir_name).exists():
                            os.makedirs(base_custom_path/sub_dir_name)
                    else:
                        if not (Path(self.out_path_str)/dir_name).exists():
                            os.makedirs(Path(self.out_path_str) / dir_name)
                        if not (Path(self.out_path_str)/dir_name/sub_dir_name).exists():
                            os.makedirs(Path(self.out_path_str) /
                                        dir_name/sub_dir_name)
                    # origin image with box
                    self.save_origin_img_magnifier()
                    for i_ in range(self.count_per_action):
                        if self.action_count*self.count_per_action+i_ < len(self.path_list):
                            f_path = self.path_list[self.action_count *self.count_per_action+i_]
                            i = 0
                            str_ = Path(f_path).parent.stem + \
                                "_"+Path(f_path).stem

                            img = self.img_list[i_]
                            img_list = self.magnifier_preprocessing(
                                self.img_preprocessing(img, rowcol=self.get_img_row_col(i_)), img_mode=1)
                            i = 0
                            for img in img_list:
                                if self.layout_params[32]:
                                    f_path_output = base_custom_path/sub_dir_name / (str_+"_magnifier_"+str(i)+".png")
                                    self.ImgF.save_img_diff_format(f_path_output,img,save_format=self.layout_params[35], use_vector_titles=False)
                                else:
                                    f_path_output = Path(
                                        self.out_path_str) / dir_name/sub_dir_name / (str_+"_magnifier_"+str(i)+".png")
                                    self.ImgF.save_img_diff_format(f_path_output,img,save_format=self.layout_params[35], use_vector_titles=False)
                                i += 1
                else:
                    # origin image with box
                    self.save_origin_img_magnifier()
                    for i, img in enumerate(self.img_list):
                        img_list = self.magnifier_preprocessing(
                            self.img_preprocessing(img, rowcol=self.get_img_row_col(i)), img_mode=1)
                        folder_name = (Path(self.flist[i]).parent).stem
                        if not (base_custom_path / folder_name).exists():
                            os.makedirs(base_custom_path / folder_name)
                        for ii, img_item in enumerate(img_list):
                            f_path_output = base_custom_path / folder_name / (
                                folder_name + "_" + Path(self.flist[i]).stem + "_magnifier_" + str(ii) + ".png")
                            self.ImgF.save_img_diff_format(f_path_output, img_item, save_format=self.layout_params[35], use_vector_titles=False)
                    if self.layout_params[32]:
                        self.get_img_list(show_custom_func=False)
            except:
                self.check_2.append(1)
            else:
                self.check_2.append(0)

    def save_origin_img_magnifier(self):
        # save origin image
        sub_dir_name = "origin_img_with_box"
        if self.layout_params[32]:
            available_algorithms = get_available_algorithms()
            algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
            if algorithm_type < len(available_algorithms):
                algorithm_name = available_algorithms[algorithm_type]
            else:
                algorithm_name = "Unknown"
            base_custom_path = Path(self.out_path_str) / "processing_function"/ algorithm_name
            if not base_custom_path.exists():
                os.makedirs(base_custom_path)
            if not (base_custom_path/sub_dir_name).exists():
                os.makedirs(base_custom_path/sub_dir_name)
        else:
            base_custom_path = Path(self.out_path_str) / "processing_function" / "origin"
            if not base_custom_path.exists():
                os.makedirs(base_custom_path)
        if not (base_custom_path/sub_dir_name).exists():
            os.makedirs(base_custom_path/sub_dir_name)
        i = 0
        for img in self.img_list:
            if hasattr(self, '_blank_img_ids') and i in getattr(self, '_blank_img_ids', []):
                i += 1
                continue
            img = self.img_preprocessing(img, rowcol=self.get_img_row_col(i))
            if self.show_box:
                img = self.ImgF.draw_rectangle(img, self.xy_grid, self.crop_points,
                                               self.layout_params[9], line_width=self.layout_params[10][0], single_box=True)
            if self.layout_params[32]:
                f_path_output = Path(self.out_path_str)/ "processing_function"/ algorithm_name/ sub_dir_name/(Path(self.flist[i]).parent).stem / (
                    (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
                if not (Path(self.out_path_str)/ "processing_function"/ algorithm_name/ sub_dir_name/(Path(self.flist[i]).parent).stem).exists():
                    os.makedirs(Path(self.out_path_str)/ "processing_function"/ algorithm_name/ sub_dir_name/(Path(self.flist[i]).parent).stem)
                self.ImgF.save_img_diff_format(f_path_output,img,save_format=self.layout_params[35], use_vector_titles=False)
            else:
                f_path_output = base_custom_path/ sub_dir_name/(Path(self.flist[i]).parent).stem / (
                    (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
                if not (base_custom_path/ sub_dir_name/(Path(self.flist[i]).parent).stem).exists():
                    os.makedirs(base_custom_path/ sub_dir_name/(Path(self.flist[i]).parent).stem)
                self.ImgF.save_img_diff_format(f_path_output,img,save_format=self.layout_params[35], use_vector_titles=False)
            i += 1

    def save_all_func_images(self, out_type):
        available_algorithms = get_available_algorithms()
        original_custom_func_state = self.layout_params[32]
        original_algorithm_type = self.layout_params[37] if len(self.layout_params) > 37 else 0
        original_show_all_func = self.layout_params[38] if len(self.layout_params) > 38 else False
        if hasattr(self, '_original_row_col') and self._original_row_col:
            base_row_col = self._original_row_col.copy()
            original_row_col = self.layout_params[0].copy()
        else:
            base_row_col = self.layout_params[0].copy()
            original_row_col = self.layout_params[0].copy()
        for algorithm_idx in range(len(available_algorithms)):
            self.layout_params[32] = True
            self.layout_params[37] = algorithm_idx
            self.layout_params[38] = False
            self.layout_params[0] = base_row_col.copy()
            algorithm_name = available_algorithms[algorithm_idx]
            self.get_img_list(show_custom_func=True)
            # out_type: 1=stitch, 4=magnifier, 5=stitch+magnifier, 7=select+stitch+magnifier
            if out_type in [2, 3, 6, 7]:
                try:
                    self.save_select_for_algorithm(algorithm_name)
                except:
                    pass
            if out_type in [1, 3, 5, 7, 8]:
                try:
                    self.save_stitch("stitch_images")
                except:
                    pass
            if out_type in [4, 5, 6, 7, 8]:
                try:
                    self.save_magnifier("magnifier_images")
                except:
                    pass
        self.layout_params[32] = original_custom_func_state
        self.layout_params[0] = original_row_col
        if len(self.layout_params) > 37:
            self.layout_params[37] = original_algorithm_type
        if len(self.layout_params) > 38:
            self.layout_params[38] = original_show_all_func

    def get_img_row_col(self, i):
        if i != None and self.one_img:
            # row_col_one_img
            row_col1 = self.layout_params[1]
            # row_col
            row_col0 = self.layout_params[0]
            one_img_vertical = self.layout_params[25]

            kernel = []
            if one_img_vertical:
                for col in range(row_col1[1]):
                    for row in range(row_col1[0]):
                        kernel = kernel+[[row,col]]
            else:
                for row in range(row_col1[0]):
                    for col in range(row_col1[1]):
                        kernel = kernel+[[row,col]]

            L = []
            for k in range(row_col0[0]*row_col0[1]):
                L = L+kernel
            return L[i]
        else:
            return None

    def save_select_for_algorithm(self, algorithm_name):
        base_select = Path(self.out_path_str) / "processing_function" / algorithm_name / "select_images"
        if self.type == 3:
            sub_dir = "from_file"
            if not (base_select / sub_dir).exists():
                os.makedirs(base_select / sub_dir)
            for i_ in range(min(self.count_per_action, len(self.img_list))):
                if self.action_count * self.count_per_action + i_ < len(self.path_list):
                    f_path = self.path_list[self.action_count * self.count_per_action + i_]
                    str_ = Path(f_path).parent.stem + "_" + Path(f_path).stem + ".png"
                    try:
                        img = self.img_list[i_]
                        img = self.img_preprocessing(img, rowcol=self.get_img_row_col(i_))
                        f_path_output = base_select / sub_dir / str_
                        self.ImgF.save_img_diff_format(
                            f_path_output,
                            img,
                            save_format=self.layout_params[35]
                        )
                        self.check.append(0)
                    except:
                        pass
                        self.check.append(1)
        else:  # type == 0, 1, 2
            for i, img in enumerate(self.img_list):
                if i >= len(self.flist):
                    break
                folder_name = Path(self.flist[i]).parent.stem
                folder_path = base_select / folder_name
                if not folder_path.exists():
                    os.makedirs(folder_path)
                try:
                    img_processed = self.img_preprocessing(img, rowcol=self.get_img_row_col(i))
                    file_name = Path(self.flist[i]).name
                    f_path_output = folder_path / file_name
                    self.ImgF.save_img_diff_format(
                        f_path_output,
                        img_processed,
                        save_format=self.layout_params[35]
                    )
                    self.check.append(0)
                except Exception as e:
                    print(f"[ERROR] Failed to save {file_name}: {e}")
                    self.check.append(1)

    def rotate(self, id):
        img = Image.open(self.flist[id]).convert('RGB').transpose(Image.ROTATE_270)
        self.ImgF.save_img_diff_format(self.flist[id],img,save_format=self.layout_params[35])

    def flip(self, id, FLIP_TOP_BOTTOM=False):
        if FLIP_TOP_BOTTOM:
            img = Image.open(self.flist[id]).convert('RGB').transpose(Image.FLIP_TOP_BOTTOM)
        else:
            img = Image.open(self.flist[id]).convert('RGB').transpose(Image.FLIP_LEFT_RIGHT)
        self.ImgF.save_img_diff_format(self.flist[id],img,save_format=self.layout_params[35])
