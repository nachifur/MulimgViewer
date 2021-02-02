import wx
import numpy as np
import os
from PIL import Image
from shutil import copyfile, move
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
        # self.set_count_per_action(1)

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
            self.path_list = self.get_flist_from_lf()
            self.name_list = self.get_namelist_from_lf()
        else:
            self.path_list = []
            self.name_list = []

    def get_flist_from_lf(self):
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

    def get_namelist_from_lf(self):
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
                return [1, 2]
            else:
                num_all = len(self.path_list)
                list_factor = self.solve_factor(num_all)
                list_factor = list(set(list_factor))
                list_factor = np.sort(list_factor)
                if len(list_factor) == 0:
                    return [1, num_all]
                else:
                    if len(list_factor) <= 2:
                        row = list_factor[0]
                    else:
                        row = list_factor[int(len(list_factor)/2)-1]
                    row = int(row)
                    col = int(num_all/row)
                    if row < col:
                        return [row, col]
                    else:
                        return [col, row]

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
            self.img_resolution = [int(width), int(height)]
            self.custom_resolution = False
        else:
            self.img_resolution = [int(i) for i in self.layout_params[6]]
            self.custom_resolution = True
        self.img_list = img_list

    def save_img(self, out_path_str, out_type):
        self.check = []
        self.check_1 = []
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
            self.check_1.append(self.stitch_images(1, self.draw_points))
        else:
            self.check_1.append(self.stitch_images(1))

        self.img.save(f_path_output)

    def save_magnifier(self, dir_name):
        try:
            tmp = self.crop_points
        except:
            pass
        else:
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
                                if i==len(Path(f_path)._cparts)-1:
                                    img_name = stem
                                else:
                                    str_ = str_+"_"+stem
                            i += 1

                        img = self.img_list[i_]
                        img_list, _, _ = self.magnifier_preprocessing(self.add_alpha(img),img_mode=1)
                        i = 0
                        for img in img_list:
                            f_path_output = Path(
                                self.out_path_str) / dir_name/sub_dir_name / (str_+"_"+Path(img_name).stem+"_magnifier_"+str(i)+".png")                           
                            img.save(f_path_output)
                            i+=1    
                # origin image with square
                self.save_origin_img_magnifier(dir_name)                                            
            else:
                i = 0
                for img in self.img_list:
                    img_list, _, _ = self.magnifier_preprocessing(self.add_alpha(img),img_mode=1)
                    if not (Path(self.out_path_str)/dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                        os.makedirs(Path(self.out_path_str) / dir_name /
                                    (Path(self.flist[i]).parent).stem)
                    ii = 0
                    for img in img_list:
                        f_path_output = Path(self.out_path_str) / dir_name / (Path(self.flist[i]).parent).stem / (
                            (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+"_magnifier_"+str(ii)+".png")                               
                        img.save(f_path_output)
                        ii+=1
                    i += 1
                # origin image with square
                self.save_origin_img_magnifier(dir_name)

    def save_origin_img_magnifier(self, dir_name):
        # save origin image
        sub_dir_name = "origin_img"
        if not (Path(self.out_path_str)/dir_name).exists():
            os.makedirs(Path(self.out_path_str) / dir_name)
        if not (Path(self.out_path_str)/dir_name/sub_dir_name).exists():
            os.makedirs(Path(self.out_path_str) /
                                dir_name/sub_dir_name)
        i = 0
        for img in self.img_list:
            img = self.add_alpha(img)
            img = self.draw_rectangle(img, single=True)
            f_path_output = Path(self.out_path_str)/dir_name/sub_dir_name/(Path(self.flist[i]).parent).stem / (
                        (Path(self.flist[i]).parent).stem+"_"+Path(self.flist[i]).stem+".png")
            if not (Path(self.out_path_str)/dir_name/sub_dir_name/(Path(self.flist[i]).parent).stem).is_dir():
                os.makedirs(Path(self.out_path_str)/dir_name /
                                    sub_dir_name/(Path(self.flist[i]).parent).stem)
            img.save(f_path_output)
            i += 1

    def stitch_images(self, img_mode, draw_points=0):
        """img_mode, 0: show, 1: save"""
        # init
        xy_grid = []
        self.get_img_list()  # Generate image list
        self.set_scale_mode(img_mode=img_mode)
        width, height = self.img_resolution
        img_num_per_row = self.layout_params[0]
        num_per_img = self.layout_params[1]
        img_num_per_column = self.layout_params[2]
        gap = self.layout_params[3]
        self.magnifier_flag = self.layout_params[7]
        if draw_points == 0:
            self.draw_points = 0
        else:
            self.draw_points = draw_points.copy()
        if self.magnifier_flag != 0 and draw_points != 0:
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
                    img = Image.new('RGBA', (img_num_per_row*(magnifier_width+width + gap[3]) + gap[1] * (img_num_per_row-1), height * img_num_per_column * num_per_img + gap[0] * (
                        img_num_per_column-1)+gap[2]*(img_num_per_column)*(num_per_img-1)), self.gap_color)

                for ix in range(img_num_per_row):
                    for ixx in range(self.magnifier_flag+1):
                        if self.magnifier_flag != 0:
                            x = ix * (magnifier_width+width) + ixx * width + \
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
                                        if self.magnifier_flag != 0:
                                            im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                                im)
                                            # adjust magnifier image gap
                                            i = 0
                                            res_ = (height - len(im_magnifier_list)*im_magnifier_list[0].size[1] - (
                                                len(im_magnifier_list)-1)*gap[4])
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
                # horizontal
                if self.magnifier_flag == 0:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)
                else:
                    im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                        self.img_preprocessing(self.img_list[0]))
                    magnifier_height = im_magnifier_list[0].size[1]
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row)*(num_per_img-1), img_num_per_column*(magnifier_height+height + gap[3])+gap[1] * (img_num_per_column-1)), self.gap_color)

                for iy in range(img_num_per_column):
                    for iyy in range(self.magnifier_flag+1):
                        if self.magnifier_flag != 0:
                            y = iy * (height+magnifier_height) + iyy * height + \
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
                                        if self.magnifier_flag != 0:
                                            im_magnifier_list, delta_x, delta_y = self.magnifier_preprocessing(
                                                im)
                                            # adjust magnifier image gap
                                            i = 0
                                            res_ = (width - len(im_magnifier_list)*im_magnifier_list[0].size[0] - (
                                                len(im_magnifier_list)-1)*gap[4])
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

            # img = img.convert("RGBA")
            self.img_resolution = self.img_resolution_  # set_scale_mode
            self.img = img
            self.xy_grid = xy_grid
            if self.magnifier_flag != 0 and draw_points != 0:
                self.img = self.draw_rectangle(self.img)
        except:
            return 1
        else:
            return 0

    def draw_rectangle(self, img, single=False):
        if single:
            xy_grid = [self.xy_grid[0]]
        else:
            xy_grid = self.xy_grid
        line_width = self.layout_params[10]
        color_list = self.layout_params[9]
        img_array = np.array(img)

        i = 0
        k = 0
        for crop_point in self.crop_points:
            x_0, y_0, x, y = crop_point
            height = y-y_0
            width = x - x_0
            color = color_list[k]
            draw_colour = np.array(
                [color.red, color.green, color.blue, color.alpha])

            for xy in xy_grid:
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
            k+=1
            if k == len(color_list):
                k = 0
        img = Image.fromarray(img_array.astype('uint8')).convert('RGBA')
        return img

    def set_scale_mode(self, img_mode=0):
        """img_mode, 0: show, 1: save"""
        self.img_resolution_ = self.img_resolution
        self.img_resolution_show = self.img_resolution
        if img_mode == 0:
            self.img_resolution = (
                np.array(self.img_resolution) * np.array(self.layout_params[4])).astype(np.int)
            self.img_resolution_show = self.img_resolution
            self.scale = self.layout_params[4]
        elif img_mode == 1:
            self.img_resolution = (
                np.array(self.img_resolution) * np.array(self.layout_params[5])).astype(np.int)
            self.scale = self.layout_params[5]
        # self.gap = self.layout_params[3]
        # self.gap[0] = int(self.layout_params[3][0]*self.scale[0])
        # self.gap[1] = int(self.layout_params[3][1]*self.scale[1])
        # self.gap[2:] = (np.array(self.layout_params[3][2:])*np.array(self.scale[0])).astype(np.int)

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
        img = self.add_alpha(img)

        return img

    def crop_points_process(self, crop_points, img_mode=0):
        """img_mode, 0: show, 1: save"""
        crop_points_ = []
        for crop_point in crop_points:
            if crop_point[2] < crop_point[0]:
                temp = crop_point[0]
                crop_point[0] = crop_point[2]
                crop_point[2] = temp
            if crop_point[3] < crop_point[1]:
                temp = crop_point[1]
                crop_point[1] = crop_point[3]
                crop_point[3] = temp

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
                scale = np.array(
                    self.layout_params[5])/np.array(self.layout_params[4])
                crop_point[0] = int(crop_point[0]*scale[0])
                crop_point[1] = int(crop_point[1]*scale[1])
                crop_point[2] = int(crop_point[2]*scale[0])
                crop_point[3] = int(crop_point[3]*scale[1])

            crop_points_.append(crop_point)

        self.crop_points = crop_points_

    def magnifier_preprocessing(self, img, img_mode=0):
        """img_mode, 0: show, 1: save"""
        # crop images
        magnifier_scale = self.layout_params[8]
        img_list = []
        for crop_point in self.crop_points:
            img_list.append(img.crop(tuple(crop_point)))
        gap = self.layout_params[3][4]
        width, height = img_list[0].size

        # get to_resize
        if not (magnifier_scale[0] == -1 or magnifier_scale[1] == -1):
            # custom magnifier scale
            to_resize = [int(width*magnifier_scale[0]),
                         int(height*magnifier_scale[1])]
            if self.layout_params[-1]:
                delta_x = 0
                delta_y = int(
                    (self.img_resolution[1]-to_resize[1]*len(self.crop_points)-(len(self.crop_points)-1)*gap)/2)
            else:
                delta_x = int(
                    (self.img_resolution[0]-to_resize[0]*len(self.crop_points)-(len(self.crop_points)-1)*gap)/2)
                delta_y = 0
        else:
            # auto magnifier scale
            if self.layout_params[-1] == 1:
                to_height = int(
                    (self.img_resolution[1]-gap*(len(self.crop_points)-1))/len(self.crop_points))
                to_width = int(to_height/height*width)
                delta_x = 0
                delta_y = 0
                if to_width > self.img_resolution[0]:
                    to_height = int(self.img_resolution[0]/to_width*to_height)
                    to_width = self.img_resolution[0]
                    delta_y = int(
                        (self.img_resolution[1]-to_height*len(self.crop_points)-(len(self.crop_points)-1)*gap)/2)
            else:
                to_width = int(
                    (self.img_resolution[0]-gap*(len(self.crop_points)-1))/len(self.crop_points))
                to_height = int(to_width/width*height)
                delta_x = 0
                delta_y = 0
                if to_height > self.img_resolution[1]:
                    to_width = int(self.img_resolution[1]/to_height*to_width)
                    to_height = self.img_resolution[1]
                    delta_x = int(
                        (self.img_resolution[0]-to_width*len(self.crop_points)-(len(self.crop_points)-1)*gap)/2)

            to_resize = [to_width, to_height]
        if img_mode:
            to_width = self.img_resolution[0]
            to_height = int(to_width/width*height)
            if to_height > self.img_resolution[1]:
                to_width = int(self.img_resolution[1]/to_height*to_width)
                to_height = self.img_resolution[1]

            delta_x = 0
            delta_y = 0
            to_resize = [to_width, to_height]  

        # resize images
        line_width = self.layout_params[10]
        color_list = self.layout_params[9]
        i = 0
        k = 0
        for img in img_list:
            img_list[i] = img.resize(tuple(to_resize), Image.NEAREST)
            img_array = np.array(img_list[i])
            color = color_list[k]
            draw_colour = np.array(
                [color.red, color.green, color.blue, color.alpha])

            # magnifier image with square
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
            k+=1
            if k == len(color_list):
                k = 0

        return img_list, delta_x, delta_y

    def add_alpha(self, img):
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

    def rotate(self, id):
        img = Image.open(self.flist[id]).convert('RGB').rotate(-90)
        img.save(self.flist[id])
