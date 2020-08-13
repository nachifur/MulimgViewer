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
                              for path in cwd.iterdir() if cwd.is_dir()]
            self.path_list = np.sort(self.path_list)
            name_list = [str(f.name) for f in Path(self.path_list[0]).iterdir(
            ) if f.is_file() and f.suffix in format_group]
            self.name_list = np.sort(name_list)
        elif self.type == 1:
            # one_dir_mul_dir_manual
            self.path_list = [path
                              for path in self.input_path if Path(path).is_dir()]
            self.path_list = np.sort(self.path_list)
            if len(self.path_list)!=0:
                name_list = [str(f.name) for f in Path(self.path_list[0]).iterdir(
                ) if f.is_file() and f.suffix in format_group]
                self.name_list = np.sort(name_list)
            else:
                self.name_list=[]
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
            self.max_action_num = int(self.img_num/self.count_per_action)

    def set_action_count(self, action_count):
        self.action_count = action_count
        self.img_count = self.count_per_action*self.action_count


class ImgManager(ImgDataset):
    def __init__(self, input_path, type=-1):
        super().__init__(input_path, type)
        self.type = type
        self.layout_params = []
        self.gap_color = (0, 0, 0, 0)

    def load_img(self, f_path):
        img_name_format = Path(f_path).suffix
        if img_name_format == ".png":
            image = wx.Image(f_path, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        elif img_name_format == ".jpeg":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        elif img_name_format == ".jpg":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        elif img_name_format == ".bmp":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_BMP).ConvertToBitmap()
        elif img_name_format == ".tif":
            image = wx.Image(
                f_path, wx.BITMAP_TYPE_TIFF).ConvertToBitmap()
        else:
            image = False
        return image

    def save_img(self, out_path_str, type):
        check = []
        check_1 = []
        if out_path_str != "" and Path(out_path_str).is_dir():
            dir_name = [Path(path)._parts[-1] for path in self.path_list]
            if type == 0:
                pass
            elif type == 1:
                dir_name = ["stitch_images"]
            elif type == 2:
                dir_name.append("stitch_images")
            if type == 0:
                for i in range(len(dir_name)):
                    if not (Path(out_path_str)/dir_name[i]).exists():
                        os.makedirs(Path(out_path_str) / dir_name[i])

                    f_path = self.flist[self.action_count]
                    try:
                        copyfile(f_path, Path(
                            out_path_str) / dir_name[i] / self.name_list[self.action_count])
                    except:
                        check.append(1)
                    else:
                        check.append(0)

            elif type == 1:
                if not (Path(out_path_str)/dir_name[-1]).is_dir():
                    os.makedirs(Path(out_path_str) / dir_name[-1])
                check_1.append(self.stitch_images(out_path_str, dir_name[-1]))
            elif type == 2:
                for i in range(len(dir_name)):
                    if not (Path(out_path_str)/dir_name[i]).exists():
                        os.makedirs(Path(out_path_str) / dir_name[i])

                    f_path = self.flist[self.action_count]
                    try:
                        copyfile(f_path, Path(
                            out_path_str) / dir_name[i] / self.name_list[self.action_count])
                    except:
                        check.append(1)
                    else:
                        check.append(0)

                if not (Path(out_path_str)/dir_name[-1]).exists():
                    os.makedirs(Path(out_path_str) / dir_name[-1])
                check_1.append(self.stitch_images(out_path_str, dir_name[-1]))

            if sum(check) == 0:
                if sum(check_1) == 0:
                    return 0
                else:
                    return 2
            else:
                return 3
        else:
            return 1

    def stitch_images(self, out_path_str, dir_name):
        try:
            img_list = []
            f_path_output = Path(out_path_str) / dir_name / \
                self.name_list[self.action_count]
            for path in self.flist:
                img_list.append(Image.open(path))
            num_per_img = self.layout_params[0]
            gap = self.layout_params[3]
            width_ = []
            height_ = []
            for img in img_list:
                width, height = img.size
                width_.append(width)
                height_.append(height)
            width = max(width_)
            height = max(height_)

            if self.layout_params[-1]:
                img_num_per_row = self.layout_params[-3]
                img_num_per_column = int(self.layout_params[-2]/num_per_img)
                img = Image.new('RGB', (width * img_num_per_row + gap * (img_num_per_row-1), height *
                                        img_num_per_column * num_per_img + gap*(img_num_per_column-1)), self.gap_color)

                for ix in range(img_num_per_row):
                    x = ix * width + gap * ix

                    for iyy in range(img_num_per_column):
                        for iy in range(num_per_img):
                            y = (iyy*num_per_img+iy) * height+gap * iyy
                            if ix*(img_num_per_column * num_per_img)+iyy*num_per_img+iy < len(img_list):
                                im = img_list[ix*(img_num_per_column *
                                                  num_per_img)+iyy*num_per_img+iy]
                                img.paste(im, (x, y))
            else:
                img_num_per_row = int(self.layout_params[-3]/num_per_img)
                img_num_per_column = self.layout_params[-2]
                img = Image.new('RGB', (width * img_num_per_row * num_per_img + gap * (img_num_per_row-1),
                                        height * img_num_per_column + gap * (img_num_per_column-1)), self.gap_color)

                for iy in range(img_num_per_column):

                    y = iy * height + gap * iy

                    for ixx in range(img_num_per_row):
                        for ix in range(num_per_img):
                            x = (ixx*num_per_img+ix) * width+gap * ixx
                            if iy*(img_num_per_row * num_per_img)+ixx*num_per_img+ix < len(img_list):
                                im = img_list[iy*(img_num_per_row *
                                                  num_per_img)+ixx*num_per_img+ix]
                                img.paste(im, (x, y))

            img.save(f_path_output)
        except:
            return 1
        else:
            return 0
