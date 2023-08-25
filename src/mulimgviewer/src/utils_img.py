import copy
import json
import os
from pathlib import Path
from shutil import copyfile, move

from .custom_func.main import main as main_custom_func
import numpy as np
import piexif
import wx
from PIL import Image, ImageDraw, ImageFont
import imageio

from .data import ImgData
from .utils import rgb2hex


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

    def cal_magnifier_size(self, magnifier_scale, crop_size, img_mode, gap, img_size, magnifer_row_col, show_original, box_position=0, row_col_img_unit=[1, 1], img_unit_gap=[1, 1]):
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
            to_height = int(height*magnifier_scale[1])
            to_width = int(width*magnifier_scale[0])
            width_all = to_width * \
                magnifer_row_col[1] + (magnifer_row_col[1]-1)*gap[0]
            height_all = to_height * \
                magnifer_row_col[0] + (magnifer_row_col[0]-1)*gap[1]

            if img_width/width_all > img_height/height_all:
                if to_height > img_height:
                    to_width = int(
                        img_height/to_height*to_width)
                    to_height = int(
                        (img_height-gap[1]*(magnifer_row_col[0]-1))/magnifer_row_col[0])
            else:
                if width_all >= img_width:
                    to_height = int(
                        img_width/width_all*to_height)
                    to_width = int(
                        (img_width-gap[0]*(magnifer_row_col[1]-1))/magnifer_row_col[1])
        else:
            # auto magnifier scale
            width_all = width * \
                magnifer_row_col[1]+gap[0]*(magnifer_row_col[1]-1)
            height_all = height * \
                magnifer_row_col[0]+gap[1]*(magnifer_row_col[0]-1)
            if img_width/width_all > img_height/height_all:
                to_height = int(
                    (img_height-gap[1]*(magnifer_row_col[0]-1))/magnifer_row_col[0])
                to_width = int(to_height/height*width)
            else:
                to_width = int(
                    (img_width-gap[0]*(magnifer_row_col[1]-1))/magnifer_row_col[1])
                to_height = int(to_width/width*height)

        width_all = to_width*magnifer_row_col[1]+gap[0]*(magnifer_row_col[1]-1)
        height_all = to_height * \
            magnifer_row_col[0]+gap[1]*(magnifer_row_col[0]-1)

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
                delta_x = img_width-width_all
                delta_y = -height_all
            elif box_position == 3:  # left top
                delta_x = 0
                delta_y = -img_height
            elif box_position == 4:  # right top
                delta_x = img_width-width_all
                delta_y = -img_height
        elif row_col_img_unit[0] == 1:
            # adjust box position
            if box_position == 0:  # middle bottom
                delta_y = int((img_height-height_all)/2)
                delta_x = img_unit_gap[0]
            elif box_position == 2:  # right bottom
                delta_y = img_height-height_all
                delta_x = -to_width
            elif box_position == 1:  # left bottom
                delta_y = img_height-height_all
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
                delta_y = img_height-height_all
                delta_x = -to_width
            elif box_position == 1:  # left bottom
                delta_y = img_height-height_all
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
            gap_out.append(gap+add_gap)

            add_ = add_+res_a
            if add_ >= 1:
                add_ -= 1
                add_gap = 1
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

    def layout_2d(self, layout_list, gap_color, img_list, img_preprocessing, img_preprocessing_sub, vertical_list, onetitle, title_func):
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
                                            im_ = img_preprocessing_sub[iy_2, ix_2](
                                                im, id=img_list[iy_0, ix_0, iy_1, ix_1][1])
                                            if im_:
                                                img.paste(im_, (x, y))
                                    i += 1
                # show onetitle
                if onetitle:
                    if im:
                        im_ = title_preprocessing(im, id=img_list[iy_0, ix_0, 0, 0][1])
                        if im_:
                            x_offset_2 = xy_grids[level][0, Row['level_2']-1, Col['level_2']-1]
                            y_offset_2 = xy_grids[level][1, Row['level_2']-1, Col['level_2']-1]

                            x = x_offset_0
                            y = y_offset_0+y_offset_1+y_offset_2+gap_add_new_title
                            img.paste(im_, (x, y))

        return img, xy_grids_output, xy_grids_id_list

    def identity_transformation(self, img, id=0):
        return img

    def cal_txt_size_adjust_title(self, title_list, standard_size, font, font_size):
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
        return title_size, title_list, title_max_size

    def cat_img(self,img1,img2):
        target_width = img1.size[0]
        target_height = img1.size[1]+img2.size[1]
        img = Image.new('RGBA', (target_width, target_height))
        img.paste(img1,(0,0))
        img.paste(img2,(0,img1.size[1]))
        return img

class ImgManager(ImgData):
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
        self.path_custom_func_path = ""

    def get_img_list(self):
        img_list = []
        # load img list
        name_list = []
        for path in self.flist:
            path = Path(path)
            name_list.append(path.name)
            if path.is_file() and path.suffix.lower() in self.format_group:
                img = imageio.imread(path)
                if img.dtype != np.uint8:
                    img = (255 * img).astype(np.uint8)
                pil_img = Image.fromarray(img)
                img_list.append(pil_img.convert('RGB'))
                # img_list.append(Image.open(path).convert('RGB'))
            else:
                pass
        # custom process
        customfunc = self.layout_params[32]
        out_path_str = self.layout_params[33]
        if customfunc:
            img_list = main_custom_func(img_list,out_path_str,name_list=name_list)
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
        self.get_img_list()  # Generate image list
        self.set_scale_mode(img_mode=img_mode)
        if img_mode == 0:
            self.draw_points = draw_points
        self.img_vertical = self.layout_params[24]
        self.one_img_vertical = self.layout_params[25]
        self.img_unit_vertical = self.layout_params[26]
        self.magnifer_vertical = self.layout_params[27]
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
                self.layout_params[8], [crop_width, crop_height], 0, self.layout_params[3][6:8], self.to_size, magnifer_row_col, self.show_original, box_position=self.box_position, row_col_img_unit=self.layout_params[2], img_unit_gap=self.layout_params[3][4:6])
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
        if self.box_position != 0 and first_run:
            row_col_ = np.argwhere(new_add_gap_rowcol_flag==1).tolist()[0]
            if row_col_[0]>row_col_[1]:
                self.layout_params[2][0] = row_col2[0]+1
            else:
                self.layout_params[2][1] = row_col2[1]+1
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
            try:
                # Two-dimensional arrangement
                self.img, self.xy_grid, self.xy_grids_id_list = self.ImgF.layout_2d(
                    layout_list, self.gap_color, copy.deepcopy(self.img_list), self.img_preprocessing, img_preprocessing_sub, [self.img_vertical, self.one_img_vertical, self.img_unit_vertical],self.onetitle, [self.title_init,self.title_preprocessing])

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
                    self.img = self.ImgF.draw_rectangle(
                        self.img, self.xy_grid, crop_points, self.layout_params[9], line_width=self.layout_params[10][0])
            # return 0
            except:
                return 1
            else:
                return 0
        else:
            return 2

    def fill_func(self, img, id=None):
        return None

    def title_preprocessing(self, img, id):
        title_max_size = copy.deepcopy(self.title_max_size)
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

        # get title
        title_exif = self.title_setting[11]
        title_list = []

        if title_exif:
            for img in self.img_list:
                exif = piexif.load(img.info['exif'])
                try:
                    exif_dict = json.loads(exif["0th"][270])["MulimgViewer"]

                except:
                    title = str(exif["0th"][270], encoding = "utf-8")
                else:
                    i = 0
                    title = ""
                    for key in exif_dict.keys():
                        title = title+key+": "+exif_dict[key]
                        if i<len(exif_dict.keys())-1:
                            title = title+"\n"
                        i+=1

                title_list.append(title)
        else:
            for path in self.flist:
                path = Path(path)
                if path.is_file() and path.suffix.lower() in self.format_group:
                    title = ""
                    if self.title_setting[3]:
                        title = title+path.parent.parts[-1]
                    if self.title_setting[5]:
                        if self.title_setting[3]:
                            title = title+"/"
                        name = path.stem
                        if not self.title_setting[4]:
                            try:
                                name = name.split("_", 1)[1]
                            except:
                                pass
                        title = title+name
                    if self.title_setting[6]:
                        title = title+path.suffix
                    title_list.append(title)
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
            magnifier_scale, list(img_list[0].size), img_mode, gap, self.to_size, magnifer_row_col, self.show_original, box_position=self.box_position, row_col_img_unit=self.layout_params[2], img_unit_gap=self.layout_params[3][4:6])

        # resize images
        line_width = self.layout_params[10][1]
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
            if out_path_str != "" and Path(out_path_str).is_dir():
                self.set_scale_mode(img_mode=1)
                dir_name = [Path(path).name for path in self.path_list]
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

                if out_type == 2:
                    if not self.layout_params[32]:
                        self.save_select(dir_name)
                elif out_type == 1:
                    self.save_stitch(dir_name[-1])
                elif out_type == 3:
                    if not self.layout_params[32]:
                        self.save_select(dir_name[0:-1])
                    self.save_stitch(dir_name[-1])
                elif out_type == 4:
                    self.save_magnifier(dir_name[-1])
                elif out_type == 5:
                    self.save_stitch(dir_name[0])
                    self.save_magnifier(dir_name[-1])
                elif out_type == 6:
                    if not self.layout_params[32]:
                        self.save_select(dir_name[0:-1])
                    self.save_magnifier(dir_name[-1])
                elif out_type == 7:
                    if not self.layout_params[32]:
                        self.save_select(dir_name[0:-2])
                    self.save_stitch(dir_name[-2])
                    self.save_magnifier(dir_name[-1])

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
                        str_ = Path(f_path).parent.stem+"_"+Path(f_path).name

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

            if not self.parallel_to_sequential:
                for i in range(len(dir_name)):
                    if not (Path(self.out_path_str)/"select_images"/dir_name[i]).exists():
                        os.makedirs(Path(self.out_path_str) /
                                    "select_images" / dir_name[i])
                    if self.layout_params[22]:  # parallel_sequential
                        num_per_img = self.layout_params[1][0] * \
                            self.layout_params[1][1]
                    else:
                        num_per_img = 1
                    for k in range(num_per_img):
                        f_path = self.flist[i*num_per_img+k]
                        name = Path(f_path).name
                        try:
                            if self.layout_params[11]:
                                move(f_path, Path(self.out_path_str) / "select_images" /
                                     dir_name[i] / name)
                            else:
                                copyfile(f_path, Path(self.out_path_str) / "select_images" /
                                         dir_name[i] / name)
                        except:
                            self.check.append(1)
                        else:
                            self.check.append(0)

        if self.layout_params[11]:
            if self.action_count == 0:
                action_count = 0
            else:
                action_count = self.action_count-1
            self.init(self.input_path, self.type,
                      action_count=action_count, img_count=self.img_count-1)
            self.get_flist()

    def save_stitch(self, dir_name):
        name_f = self.get_stitch_name()
        if self.type == 3:
            name_f = "from_file_"+name_f
        f_path_output = Path(self.out_path_str) / dir_name / name_f
        if not (Path(self.out_path_str)/dir_name).is_dir():
            os.makedirs(Path(self.out_path_str) / dir_name)
        if self.layout_params[7]:
            self.check_1.append(self.stitch_images(
                1, copy.deepcopy(self.draw_points)))
        else:
            if self.show_box:
                self.check_1.append(self.stitch_images(
                    1, copy.deepcopy(self.draw_points)))
            else:
                self.check_1.append(self.stitch_images(1))

        self.img.save(f_path_output)

    def get_stitch_name(self):
        name_first = self.flist[0]
        name_end = self.flist[-1]
        if self.type == 0 or self.type == 1:
            name_first = Path(name_first).parent.stem+"_"+Path(name_first).stem
        else:
            name_first = Path(name_first).stem
        if self.type == 0 or self.type == 1:
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
        try:
            tmp = self.crop_points
        except:
            pass
        else:
            try:
                self.crop_points_process(
                    copy.deepcopy(self.draw_points), img_mode=1)
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

                            str_ = Path(f_path).parent.stem + \
                                "_"+Path(f_path).stem

                            img = self.img_list[i_]
                            img_list = self.magnifier_preprocessing(
                                self.img_preprocessing(img, rowcol=self.get_img_row_col(i_)), img_mode=1)
                            i = 0
                            for img in img_list:
                                f_path_output = Path(
                                    self.out_path_str) / dir_name/sub_dir_name / (str_+"_magnifier_"+str(i)+".png")
                                img.save(f_path_output)
                                i += 1
                else:
                    # origin image with box
                    self.save_origin_img_magnifier()
                    i = 0
                    for img in self.img_list:
                        img_list = self.magnifier_preprocessing(
                            self.img_preprocessing(img, rowcol=self.get_img_row_col(i)), img_mode=1)
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
                # self.check_2.append(0)
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
            img = self.img_preprocessing(img, rowcol=self.get_img_row_col(i))
            if self.show_box:
                img = self.ImgF.draw_rectangle(img, self.xy_grid, self.crop_points,
                                               self.layout_params[9], line_width=self.layout_params[10][0], single_box=True)
            f_path_output = Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem / (
                (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
            if not (Path(self.out_path_str)/sub_dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                os.makedirs(Path(self.out_path_str) /
                            sub_dir_name/(Path(self.flist[i]).parent).stem)
            img.save(f_path_output)
            i += 1

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

    def rotate(self, id):
        img = Image.open(self.flist[id]).convert(
            'RGB').transpose(Image.ROTATE_270)
        img.save(self.flist[id])

    def flip(self, id, FLIP_TOP_BOTTOM=False):
        if FLIP_TOP_BOTTOM:
            img = Image.open(self.flist[id]).convert(
                'RGB').transpose(Image.FLIP_TOP_BOTTOM)
        else:
            img = Image.open(self.flist[id]).convert(
                'RGB').transpose(Image.FLIP_LEFT_RIGHT)
        img.save(self.flist[id])
