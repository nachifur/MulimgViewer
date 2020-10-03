import wx
import numpy as np
import os
from PIL import Image
from shutil import copyfile
from pathlib import Path
import csv

class ImgDataset():
    def init(self, input_path, type):
        self.input_path = input_path
        self.type = type

        self.action_count = 0
        self.img_count = 0
        self.init_flist()
        self.img_num = len(self.name_list)
        self.set_count_per_action(1)

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
        elif self.type == 3:
            # read file list from a list file
            # do somthing
            self.path_list = self.get_flist_from_lf()
            self.name_list = self.get_namelist_from_lf()
        else:
            self.path_list = []
            self.name_list = []

    def get_flist_from_lf(self):
        #format_group = [".txt", ".csv", ".xls", ".xlsx"]
        methods={
            '.txt':get_flist_from_txt,
            '.csv':get_flist_from_csv
            }
        method = methods.get(Path(self.input_path).suffix,notfilelist)
        return method(self)

    def notfilelist(self):
        return []

    def get_namelist_from_lf(self):
        dataset=np.array(self.path_list).ravel().tolist()
        namelist=[Path(item).name for item in dataset]
        return namelist

    def get_flist_from_txt(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
        with open(self.input_path, "r") as f:
            dataset=f.read().split('\n')
        validdataset=[item for item in dataset if Path(item).is_file() and  Path(item).suffix in format_group]
        return validdataset

    def get_flist_from_csv(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
        with open(self.path_list, 'r', newline='') as csvfile:
            spamreader = csv.reader(csvfile)
            validdataset=[item[0] for item in spamreader if Path(item[0]).is_file() and  Path(item[0]).suffix in format_group]
        return validdataset

    def get_name_list(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
        no_check_list = [str(f.name)
                         for f in Path(self.path_list[0]).iterdir()]
        if len(no_check_list) > 100:
            self.dataset_mode = True
            return no_check_list
        else:
            self.dataset_mode = False
            return [str(f.name) for f in Path(self.path_list[0]).iterdir(
            ) if f.is_file() and f.suffix in format_group]

    def get_flist(self):

        if self.type == 0:
            # one_dir_mul_dir_auto
            flist = [str(Path(self.path_list[i])/self.name_list[self.img_count])
                     for i in range(len(self.path_list))]
        elif self.type == 1:
            # one_dir_mul_dir_manual
            flist = [str(Path(self.path_list[i])/self.name_list[self.img_count])
                     for i in range(len(self.path_list))]
        elif self.type == 2:
            # one_dir_mul_img
            try:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.input_path)/self.name_list[i])
                         for i in range(self.img_count, self.img_num)]
        elif self.type == 3:
            # one_dir_mul_img
            try:
                flist = [str(Path(self.path_list)/self.name_list[i])
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.path_list)/self.name_list[i])
                         for i in range(self.img_count, self.img_num)]
        else:
            flist = []

        self.flist = flist
        return flist

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
        if self.type == 0:
            self.max_action_num = self.img_num
        elif self.type == 1:
            self.max_action_num = self.img_num
        elif self.type == 2:
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

    def save_img(self, out_path_str, out_type, img_mode):
        check = []
        check_1 = []
        img = self.img
        img = self.resize(img, self.layout_params[5])
        if out_path_str != "" and Path(out_path_str).is_dir():
            dir_name = [Path(path)._parts[-1] for path in self.path_list]
            if out_type == "Select":
                pass
            elif out_type == "Stitch":
                dir_name = ["stitch_images"]
            elif out_type == "Both":
                dir_name.append("stitch_images")

            name_f = self.name_list[self.action_count]
            name_f = Path(name_f).with_suffix(".png")
            f_path_output = Path(out_path_str) / dir_name[-1] / name_f

            if out_type == "Select":
                for i in range(len(dir_name)):
                    if not (Path(out_path_str)/dir_name[i]).exists():
                        os.makedirs(Path(out_path_str) / dir_name[i])

                    f_path = self.flist[i]
                    try:
                        copyfile(f_path, Path(
                            out_path_str) / dir_name[i] / self.name_list[self.action_count])
                    except:
                        check.append(1)
                    else:
                        check.append(0)

            elif out_type == "Stitch":
                if not (Path(out_path_str)/dir_name[-1]).is_dir():
                    os.makedirs(Path(out_path_str) / dir_name[-1])
                check_1.append(self.stitch_images(1))

                img.save(f_path_output)
            elif out_type == "Both":
                for i in range(len(dir_name)-1):
                    if not (Path(out_path_str)/dir_name[i]).exists():
                        os.makedirs(Path(out_path_str) / dir_name[i])
                    f_path = self.flist[i]
                    try:
                        copyfile(f_path, Path(
                            out_path_str) / dir_name[i] / self.name_list[self.action_count])
                    except:
                        check.append(1)
                    else:
                        check.append(0)

                if not (Path(out_path_str)/dir_name[-1]).exists():
                    os.makedirs(Path(out_path_str) / dir_name[-1])
                check_1.append(self.stitch_images(1))
                img.save(f_path_output)

            if sum(check) == 0:
                if sum(check_1) == 0:
                    return 0
                else:
                    return 2
            else:
                return 3
        else:
            return 1

    def get_img_list(self):
        img_list = []
        for path in self.flist:
            img_list.append(Image.open(path).convert('RGB'))
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

        return img_list

    def stitch_images(self, img_mode, draw_points=0):
        xy_grid = []
        try:
            img_list = self.get_img_list()
            self.set_scale_mode(img_mode=img_mode)
            width, height = self.img_resolution
            img_num_per_row = self.layout_params[0]
            num_per_img = self.layout_params[1]
            img_num_per_column = self.layout_params[2]
            gap = self.layout_params[3]
            self.magnifier_flag = self.layout_params[7]
            if self.layout_params[-1]:
                # Vertical
                img_num_per_column = img_num_per_row
                img_num_per_row = self.layout_params[2]
                if self.magnifier_flag == 0:
                    img = Image.new('RGBA', ((width * img_num_per_row + gap[1] * (img_num_per_row-1)),height * img_num_per_column * num_per_img + gap[0] * (
                        img_num_per_column-1)+gap[2]*(img_num_per_column-1)*(num_per_img-1)), self.gap_color)
                else:
                    img = Image.new('RGBA', ((2*(width * img_num_per_row + gap[1] * (img_num_per_row-1))+gap[3]*img_num_per_row), height * img_num_per_column * num_per_img + gap[0] * (img_num_per_column-1)+gap[2]*(img_num_per_column-1)*(num_per_img-1)),self.gap_color)

                for ix in range(img_num_per_row):
                    for ixx in range(2):
                        if self.magnifier_flag != 0:
                            x = 2*ix * width + ixx * width + \
                                gap[3] * ixx + gap[1]*ix + gap[3]*ix

                        else:
                            x = ix * width + gap[1] * ix

                        for iyy in range(img_num_per_column):
                            for iy in range(num_per_img):
                                y = (iyy*num_per_img+iy) * \
                                    width+gap[0]*iyy+gap[2]*iy
                                if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(img_list):
                                    im = img_list[ix*(img_num_per_column *
                                                      num_per_img)+iyy*num_per_img+iy]
                                    im = self.img_preprocessing(im)
                                    if self.magnifier_flag != 0 and (ixx+1) % 2 == 0:
                                        if draw_points != 0 and np.abs(draw_points[2] - draw_points[0]) > 0 and np.abs(draw_points[3] - draw_points[1]) > 0:
                                            crop_points = self.crop_points_process(
                                                draw_points)
                                            im, delta_x, delta_y = self.magnifier_preprocessing(
                                                im, crop_points)
                                            img.paste(
                                                im, (x+delta_x, y+delta_y))
                                    else:
                                        xy_grid.append([x, y])
                                        img.paste(im, (x, y))

            else:
                # horizontal
                if self.magnifier_flag == 0:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row-1)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)
                else:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row-1)*(num_per_img-1), 2*(height * img_num_per_column + gap[1] * (img_num_per_column-1))+gap[3]*img_num_per_column), self.gap_color)
                for iy in range(img_num_per_column):
                    for iyy in range(2):
                        if self.magnifier_flag != 0:
                            y = 2*iy * height + iyy * height + \
                                gap[3] * iyy + gap[1]*iy + gap[3]*iy

                        else:
                            y = iy * height + gap[1] * iy

                        for ixx in range(img_num_per_row):
                            for ix in range(num_per_img):
                                x = (ixx*num_per_img+ix) * \
                                    width+gap[0]*ixx+gap[2]*ix
                                if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(img_list):
                                    im = img_list[iy*(img_num_per_row *
                                                      num_per_img)+ixx*num_per_img+ix]
                                    im = self.img_preprocessing(im)
                                    if self.magnifier_flag != 0 and (iyy+1) % 2 == 0:
                                        if draw_points != 0 and np.abs(draw_points[2] - draw_points[0]) > 0 and np.abs(draw_points[3] - draw_points[1]) > 0:
                                            crop_points = self.crop_points_process(
                                                draw_points)
                                            im, delta_x, delta_y = self.magnifier_preprocessing(
                                                im, crop_points)
                                            img.paste(
                                                im, (x+delta_x, y+delta_y))
                                    else:
                                        xy_grid.append([x, y])
                                        img.paste(im, (x, y))

            # img = img.convert("RGBA")
            self.img_resolution = self.img_resolution_
            self.img = img
            self.xy_grid = xy_grid
        except:
            return 1
        else:
            return 0

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
        crop_points = list(crop_points)
        if crop_points[2] < crop_points[0]:
            temp = crop_points[0]
            crop_points[0] = crop_points[2]
            crop_points[2] = temp
        if crop_points[3] < crop_points[1]:
            temp = crop_points[1]
            crop_points[1] = crop_points[3]
            crop_points[3] = temp
        return tuple(crop_points)

    def magnifier_preprocessing(self, img, crop_points):
        magnifier_scale = self.layout_params[8]
        img = img.crop(crop_points)

        width, height = img.size
        if magnifier_scale[0] == -1 or magnifier_scale[1] == -1:
            if width > height:
                img = img.resize((self.img_resolution[0], int(
                    height*self.img_resolution[0]/width)), Image.NEAREST)
            else:
                img = img.resize(
                    (int(width*self.img_resolution[1]/height), self.img_resolution[1]), Image.NEAREST)
        else:
            to_resize = [int(width*magnifier_scale[0]),
                         int(height*magnifier_scale[1])]
            if to_resize[0] > to_resize[1]:
                if to_resize[0] > self.img_resolution[0]:
                    img = img.resize((self.img_resolution[0], int(
                        height*self.img_resolution[0]/width)), Image.NEAREST)
                else:
                    img = img.resize(tuple(to_resize), Image.NEAREST)
            else:
                if to_resize[1] > self.img_resolution[1]:
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
