import wx
import numpy as np
import os
from PIL import Image
from shutil import copyfile
from pathlib import Path


class ImgDataset():
    def __init__(self, input_path, type):
        self.input_path = input_path
        self.type = type

        self.action_count = 0
        self.img_count = 0
        self.init_flist()
        self.img_num = len(self.name_list)
        self.set_count_per_action(1)

    def init_flist(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif"]
        if self.type == 0:
            # one_dir_mul_dir_auto
            cwd = Path(self.input_path)
            self.path_list = [str(path)
                              for path in cwd.iterdir() if cwd.is_dir() and path.is_dir()]
            if len(self.path_list) == 0:
                self.path_list = [self.input_path]
            self.path_list = np.sort(self.path_list)
            name_list = [str(f.name) for f in Path(self.path_list[0]).iterdir(
            ) if f.is_file() and f.suffix in format_group]
            self.name_list = np.sort(name_list)
        elif self.type == 1:
            # one_dir_mul_dir_manual
            self.path_list = [path
                              for path in self.input_path if Path(path).is_dir()]
            if len(self.path_list) != 0:
                name_list = [str(f.name) for f in Path(self.path_list[0]).iterdir(
                ) if f.is_file() and f.suffix in format_group]
                self.name_list = np.sort(name_list)
            else:
                self.name_list = []
        elif self.type == 2:
            # one_dir_mul_img
            self.path_list = [self.input_path]
            self.path_list = np.sort(self.path_list)
            name_list = [str(f.name) for f in Path(self.path_list[0]).iterdir(
            ) if f.is_file() and f.suffix in format_group]
            self.name_list = np.sort(name_list)
        else:
            self.path_list = []
            self.name_list = []

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
    def __init__(self, input_path, type=-1):
        super().__init__(input_path, type)
        self.type = type
        self.layout_params = []
        self.gap_color = (0, 0, 0, 0)
        self.img = ""
        self.gap_alpha = 255
        self.img_alpha = 255
        self.img_stitch_mode = 0  # 0:"fill" 1:"crop" 2:"resize"
        self.img_resolution = [-1, -1]
        self.custom_resolution = False

    def save_img(self, out_path_str, out_type):
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
                check_1.append(self.stitch_images())

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
                check_1.append(self.stitch_images())
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

        if self.img_stitch_mode == 0:
            width = max(width_)
            height = max(height_)
        elif self.img_stitch_mode == 1:
            width = np.min(width_)
            height = np.min(height_)
        elif self.img_stitch_mode == 2:
            if len(width_) > 3:
                width = np.mean(width_[1:-1])
                height = np.mean(height_[1:-1])
            else:
                width = np.mean(width_)
                height = np.mean(height_)
        else:
            self.img_resolution = [-1, -1]

        if self.layout_params[6][0] == -1 or self.layout_params[6][1] == -1:
            self.img_resolution = [int(width), int(height)]
            self.custom_resolution = False
        else:
            self.img_resolution = [int(i) for i in self.layout_params[6]]
            self.custom_resolution = True

        return img_list

    def stitch_images(self):
        xy_grid = []
        try:
            img_list = self.get_img_list()
            width, height = self.img_resolution
            img_num_per_row = self.layout_params[0]
            num_per_img = self.layout_params[1]
            img_num_per_column = self.layout_params[2]
            gap = self.layout_params[3]
            magnifier_flag = self.layout_params[7]
            if self.layout_params[-1]:
                img_num_per_column = img_num_per_row
                img_num_per_row = self.layout_params[2]
                img = Image.new('RGBA', (width * img_num_per_row + gap[1] * (img_num_per_row-1), height *
                                         img_num_per_column * num_per_img + gap[0]*(img_num_per_column-1)+gap[2]*(img_num_per_column-1)*(num_per_img-1)), self.gap_color)

                for ix in range(img_num_per_row):
                    x = ix * width + gap[1] * ix

                    for iyy in range(img_num_per_column):
                        for iy in range(num_per_img):
                            y = (iyy*num_per_img+iy) * height+gap[0] * iyy+gap[2]*iy
                            if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(img_list):
                                im = img_list[ix*(img_num_per_column *
                                                  num_per_img)+iyy*num_per_img+iy]
                                im = self.img_preprocessing(im)
                                img.paste(im, (x, y))
                                xy_grid.append([x,y])

            else:
                if magnifier_flag==0:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row-1)*(num_per_img-1), height * img_num_per_column + gap[1] * (img_num_per_column-1)), self.gap_color)
                else:
                    img = Image.new('RGBA', (width * img_num_per_row * num_per_img + gap[0] * (
                        img_num_per_row-1)+gap[2]*(img_num_per_row-1)*(num_per_img-1), 2*(height * img_num_per_column + gap[1] * (img_num_per_column-1))+gap[3]*img_num_per_column), self.gap_color)
                for iy in range(img_num_per_column):
                    for iyy in range(img_num_per_column):
                        if magnifier_flag==0:
                            y = iy * height + gap[1] * iy
                        else:
                            y = 2*iy * height + iyy * height + gap[1] * iy + gap[3] * iyy

                        for ixx in range(img_num_per_row):
                            for ix in range(num_per_img):
                                x = (ixx*num_per_img+ix) * \
                                    width+gap[0]*ixx+gap[2]*ix
                                if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(img_list):
                                    im = img_list[iy*(img_num_per_row *
                                                    num_per_img)+ixx*num_per_img+ix]
                                    im = self.img_preprocessing(im)
                                    img.paste(im, (x, y))
                                    xy_grid.append([x,y])
            # img = img.convert("RGBA")

            self.img = img
            self.xy_grid = xy_grid
        except:
            return 1
        else:
            return 0

    def PIL2wx(self, image):
        width, height = image.size
        return wx.Bitmap.FromBufferRGBA(width, height, image.tobytes())

    def img_preprocessing(self, img):
        if self.custom_resolution:
            # custom image resolution
            width, height = self.img_resolution
            img = img.resize((width, height), Image.BICUBIC)
        else:
            if self.img_stitch_mode == 0:
                pass
            elif self.img_stitch_mode == 1:
                width, height = self.img_resolution
                (left, upper, right, lower) = (
                    (img.size[0]-width)/2, (img.size[1]-height)/2, (img.size[0]-width)/2+width, (img.size[1]-height)/2+height)
                img = img.crop((left, upper, right, lower))
            elif self.img_stitch_mode == 2:
                width, height = self.img_resolution
                img = img.resize((width, height), Image.BICUBIC)
        img = self.change_img_alpha(img)
        return img

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
