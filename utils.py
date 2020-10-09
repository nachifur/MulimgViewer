from numpy.lib.type_check import imag
import wx
import numpy as np
import os
from PIL import Image
from shutil import copyfile, move
from pathlib import Path


class ImgDataset():
    def init(self, input_path, type):
        self.input_path = input_path
        self.type = type

        self.action_count = 0
        self.img_count = 0
        self.init_flist()
        self.img_num = len(self.name_list)
        # self.set_count_per_action(1)

    def init_flist(self):

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
        else:
            self.path_list = []
            self.name_list = []

    def get_name_list(self):

        no_check_list = [str(f.name)
                         for f in Path(self.path_list[0]).iterdir()]
        if len(no_check_list) > 100:
            self.dataset_mode = True
            return no_check_list
        else:
            self.dataset_mode = False
            return [str(f.name) for f in Path(self.path_list[0]).iterdir(
            ) if f.is_file() and f.suffix in self.format_group]

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
        if self.type == 2:
            return [2, 1]
        else:
            num_all = len(self.path_list)
            list_factor = self.solve_factor(num_all)
            list_factor = list(set(list_factor))
            list_factor = np.sort(list_factor)
            if len(list_factor) == 0:
                return [num_all, 1]
            else:
                if len(list_factor) <= 2:
                    row = list_factor[0]
                else:
                    row = list_factor[int(len(list_factor)/2)-1]
                row = int(row)
                col = int(num_all/row)
                if row < col:
                    return [col, row]
                else:
                    return [row, col]

    def solve_factor(self, num):
        list_factor = []
        i = 1
        if num >= 2:
            while i <= num:
                i += 1
                if num % i == 0:
                    list_factor.append(i)
                else:
                    pass
            return list_factor
        else:
            return []


class ImgManager(ImgDataset):
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
        self.save_select_move = 0

    def get_flist(self):

        if self.type == 0 or self.type == 1:
            # one_dir_mul_dir_auto, one_dir_mul_dir_manual
            flist = []
            for i in range(len(self.path_list)):
                for k in range(self.img_count, self.img_count+self.count_per_action):
                    try:
                        flist += [str(Path(self.path_list[i])/self.name_list[k])]
                    except:
                        flist += [str(Path(self.path_list[i])/self.name_list[-1])]

        elif self.type == 2:
            # one_dir_mul_img
            try:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_num)]
        else:
            flist = []

        self.flist = flist
        return flist

    def get_img_list(self):
        img_list = []
        for path in self.flist:
            path = Path(path)
            if path.is_file() and path.suffix in self.format_group:
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
            self.img_resolution = [int(width), int(height)]
            self.custom_resolution = False
        else:
            self.img_resolution = [int(i) for i in self.layout_params[6]]
            self.custom_resolution = True
        self.img_list = img_list

    def save_img(self, out_path_str, out_type):
        self.check = []
        self.check_1 = []
        img = self.img
        img = self.resize(img, self.layout_params[5])
        self.out_path_str = out_path_str
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
                self.save_stitch(dir_name[-1], img)
            elif out_type == 3:
                self.save_select(dir_name[0:-1])
                self.save_stitch(dir_name[-1], img)
            elif out_type == 4:
                self.save_magnifier(dir_name[-1])
            elif out_type == 5:
                self.save_stitch(dir_name[0], img)
                self.save_magnifier(dir_name[-1])
            elif out_type == 6:
                self.save_select(dir_name[0:-1])
                self.save_magnifier(dir_name[-1])
            elif out_type == 7:
                self.save_select(dir_name[0:-2])
                self.save_stitch(dir_name[-2], img)
                self.save_magnifier(dir_name[-1])
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
            self.save_select_move = 1

    def save_stitch(self, dir_name, img):
        name_f = self.name_list[self.action_count]
        name_f = Path(name_f).with_suffix(".png")
        f_path_output = Path(self.out_path_str) / dir_name / name_f
        if not (Path(self.out_path_str)/dir_name).is_dir():
            os.makedirs(Path(self.out_path_str) / dir_name)
        if self.layout_params[7]:
            self.check_1.append(self.stitch_images(1, self.crop_points))
        else:
            self.check_1.append(self.stitch_images(1))

        img.save(f_path_output)

    def save_magnifier(self, dir_name):
        i = 0
        for img in self.img_list:
            img, _, _ = self.magnifier_preprocessing(img)
            path = (Path(self.flist[0]).parent).stem
            f_path_output = Path(self.out_path_str) / dir_name / (Path(self.flist[i]).parent).stem / (
                (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
            if not (Path(self.out_path_str)/dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                os.makedirs(Path(self.out_path_str) / dir_name /
                            (Path(self.flist[i]).parent).stem)
            img.save(f_path_output)
            i += 1

    def stitch_images(self, img_mode, draw_points=0):
        xy_grid = []
        # try:
        self.get_img_list()
        self.set_scale_mode(img_mode=img_mode)
        width, height = self.img_resolution
        img_num_per_row = self.layout_params[0]
        num_per_img = self.layout_params[1]
        img_num_per_column = self.layout_params[2]
        gap = self.layout_params[3]
        self.magnifier_flag = self.layout_params[7]
        if self.magnifier_flag != 0 == 0 and draw_points != 0 and np.abs(draw_points[2] - draw_points[0]) > 0 and np.abs(draw_points[3] - draw_points[1]) > 0:
            self.crop_points_process(
                draw_points)
        if self.layout_params[-1]:
            # Vertical
            img_num_per_column = img_num_per_row
            img_num_per_row = self.layout_params[2]
            if self.magnifier_flag == 0:
                img = Image.new('RGBA', ((width * img_num_per_row + gap[1] * (img_num_per_row-1)), height * img_num_per_column * num_per_img + gap[0] * (
                    img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)
            else:
                img = Image.new('RGBA', (img_num_per_row*(2*width + gap[3]) + gap[1] * (img_num_per_row-1), height * img_num_per_column * num_per_img + gap[0] * (
                    img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)

            for ix in range(img_num_per_row):
                for ixx in range(self.magnifier_flag+1):
                    if self.magnifier_flag != 0:
                        x = 2*ix * width + ixx * width + \
                            gap[3] * ixx + gap[1]*ix + gap[3]*ix

                    else:
                        x = ix * width + gap[1] * ix

                    for iyy in range(img_num_per_column):
                        for iy in range(num_per_img):
                            y = (iyy*num_per_img+iy) * \
                                height+gap[0]*iyy+gap[2]*iy + \
                                gap[2]*iyy*(num_per_img-1)
                            if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(self.img_list):
                                im = self.img_list[ix*(img_num_per_column *
                                                       num_per_img)+iyy*num_per_img+iy]
                                im = self.img_preprocessing(im)
                                if (ixx+1) % 2 == 0:
                                    if self.magnifier_flag != 0 and draw_points != 0 and np.abs(draw_points[2] - draw_points[0]) > 0 and np.abs(draw_points[3] - draw_points[1]) > 0:
                                        im, delta_x, delta_y = self.magnifier_preprocessing(
                                            im)
                                        img.paste(
                                            im, (x+delta_x, y+delta_y))
                                else:
                                    xy_grid.append([x, y])
                                    img.paste(im, (x, y))

        else:
            # horizontal
            if self.magnifier_flag == 0:
                img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                    img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)
            else:
                img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                    img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), img_num_per_column*(2*height + gap[3])+gap[1] * (img_num_per_column-1)), self.gap_color)

            for iy in range(img_num_per_column):
                for iyy in range(self.magnifier_flag+1):
                    if self.magnifier_flag != 0:
                        y = 2*iy * height + iyy * height + \
                            gap[3] * iyy + gap[1]*iy + gap[3]*iy

                    else:
                        y = iy * height + gap[1] * iy

                    for ixx in range(img_num_per_row):
                        for ix in range(num_per_img):
                            x = (ixx*num_per_img+ix) * \
                                width+gap[0]*ixx+gap[2]*ix + \
                                gap[2]*ixx*(num_per_img-1)
                            if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(self.img_list):
                                im = self.img_list[iy*(img_num_per_row *
                                                       num_per_img)+ixx*num_per_img+ix]
                                im = self.img_preprocessing(im)
                                if (iyy+1) % 2 == 0:
                                    if self.magnifier_flag != 0 and draw_points != 0 and np.abs(draw_points[2] - draw_points[0]) > 0 and np.abs(draw_points[3] - draw_points[1]) > 0:
                                        im, delta_x, delta_y = self.magnifier_preprocessing(
                                            im)
                                        img.paste(
                                            im, (x+delta_x, y+delta_y))
                                else:
                                    xy_grid.append([x, y])
                                    img.paste(im, (x, y))

        # img = img.convert("RGBA")
        self.img_resolution = self.img_resolution_
        self.img = img
        self.xy_grid = xy_grid
        if self.magnifier_flag != 0 and draw_points != 0:
            self.draw_rectangle()
        # except:
        #     return 1
        # else:
        return 0

    def draw_rectangle(self):
        line_width = self.layout_params[10]
        colour = self.layout_params[9]

        x_0, y_0, x, y = self.crop_points
        height = y-y_0
        width = x - x_0
        draw_colour = np.array([colour.red, colour.green, colour.blue, 255])
        img_array = np.array(self.img)
        for xy in self.xy_grid:
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

        img = Image.fromarray(img_array.astype('uint8')).convert('RGBA')
        self.img = img

    def set_scale_mode(self, img_mode=0):
        """img_mode, 0: show, 1: save"""
        self.img_resolution_ = self.img_resolution
        if img_mode == 0:
            self.img_resolution = (
                np.array(self.img_resolution) * np.array(self.layout_params[4])).astype(np.int)
            self.img_resolution_show = self.img_resolution
        elif img_mode == 1:
            self.img_resolution = (
                np.array(self.img_resolution) * np.array(self.layout_params[5])).astype(np.int)
            self.img_resolution_show = self.img_resolution_

    def PIL2wx(self, image):
        width, height = image.size
        return wx.Bitmap.FromBufferRGBA(width, height, image.tobytes())

    def img_preprocessing(self, img):
        if self.custom_resolution:
            # custom image resolution
            width, height = self.img_resolution
            img = img.resize((width, height), Image.BICUBIC)
        else:
            if self.img_stitch_mode == 2:
                pass
            elif self.img_stitch_mode == 1:
                width, height = self.img_resolution
                (left, upper, right, lower) = (
                    (img.size[0]-width)/2, (img.size[1]-height)/2, (img.size[0]-width)/2+width, (img.size[1]-height)/2+height)
                img = img.crop((left, upper, right, lower))
            elif self.img_stitch_mode == 0:
                width, height = self.img_resolution
                img = img.resize((width, height), Image.BICUBIC)
        img = self.change_img_alpha(img)

        return img

    def crop_points_process(self, crop_points):
        if crop_points[2] < crop_points[0]:
            temp = crop_points[0]
            crop_points[0] = crop_points[2]
            crop_points[2] = temp
        if crop_points[3] < crop_points[1]:
            temp = crop_points[1]
            crop_points[1] = crop_points[3]
            crop_points[3] = temp

        if self.layout_params[12]:
            width = crop_points[2]-crop_points[0]
            height = crop_points[3]-crop_points[1]
            center_x = crop_points[0]+int(width/2)
            center_y = crop_points[1]+int(height/2)
            if self.img_resolution[0]/width > self.img_resolution[1]/height:
                height = int(
                    width*self.img_resolution[1]/self.img_resolution[0])
            else:
                width = int(
                    height*self.img_resolution[0]/self.img_resolution[1])
            crop_points[0] = center_x - int(width/2)
            crop_points[2] = center_x + int(width/2)

            crop_points[1] = center_y-int(height/2)
            crop_points[3] = center_y+int(height/2)
        self.crop_points = crop_points

    def magnifier_preprocessing(self, img):
        magnifier_scale = self.layout_params[8]
        img = img.crop(tuple(self.crop_points))

        width, height = img.size
        if height == 0 or width == 0:
            a = 1
        if magnifier_scale[0] == -1 or magnifier_scale[1] == -1:
            if self.img_resolution[0]/width < self.img_resolution[1]/height:
                img = img.resize((self.img_resolution[0], int(
                    height*self.img_resolution[0]/width)), Image.NEAREST)
            else:
                img = img.resize(
                    (int(width*self.img_resolution[1]/height), self.img_resolution[1]), Image.NEAREST)
        else:
            to_resize = [int(width*magnifier_scale[0]),
                         int(height*magnifier_scale[1])]
            if to_resize[0] > self.img_resolution[0] or to_resize[1] > self.img_resolution[1]:
                if self.img_resolution[0]/width < self.img_resolution[1]/height:
                    img = img.resize((self.img_resolution[0], int(
                        height*self.img_resolution[0]/width)), Image.NEAREST)
                else:
                    img = img.resize(
                        (int(width*self.img_resolution[1]/height), self.img_resolution[1]), Image.NEAREST)
            else:
                img = img.resize(tuple(to_resize), Image.NEAREST)

        delta_x = int((self.img_resolution[0]-img.size[0])/2)
        delta_y = int((self.img_resolution[1]-img.size[1])/2)
        return img, delta_x, delta_y

    def change_img_alpha(self, img):
        img_array = np.array(img)
        temp = img_array[:, :, 0]
        if img_array.shape[2] == 3:
            img = np.concatenate((img_array, np.ones_like(
                temp[:, :, np.newaxis])*self.img_alpha), axis=2)
        elif img_array.shape[2] == 4:
            img_array[:, :, 3] = np.ones_like(temp)*self.img_alpha
            img = img_array
        else:
            pass
        img = Image.fromarray(img.astype('uint8')).convert('RGBA')
        return img

    def resize(self, img, scale):
        width = int(img.size[0]*scale[0])
        height = int(img.size[1]*scale[1])
        img = img.resize((width, height), Image.BICUBIC)
        return img
