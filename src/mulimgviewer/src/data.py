
import csv
from pathlib import Path

import numpy as np

from .utils import solve_factor

class ImgData():
    """Multi-image database.
    Multi-image browsing, path management, loading multi-image data, automatic layout layout, etc. """

    def init(self, input_path, type=2, parallel_to_sequential=False, action_count=None, img_count=None):
        self.input_path = input_path
        self.type = type
        self.parallel_to_sequential = parallel_to_sequential

        self.init_flist()
        if self.parallel_to_sequential:
            list_ = []
            for name_list in self.name_list:
                list_ = list_+name_list.tolist()
            self.img_num = len(list_)
        else:
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
            self.name_list = self.get_name_list()
        elif self.type == 1:
            # one_dir_mul_dir_manual
            self.path_list = [path
                              for path in self.input_path if Path(path).is_dir()]
            if len(self.path_list) != 0:
                self.name_list = self.get_name_list()
            else:
                self.name_list = []
        elif self.type == 2:
            # one_dir_mul_img
            self.path_list = [self.input_path]
            self.path_list = np.sort(self.path_list)
            self.name_list = self.get_name_list()

        elif self.type == 3:
            # read file list from a list file
            self.path_list = self.get_path_list_from_lf()
            self.name_list = self.get_name_list_from_lf()
        else:
            self.path_list = []
            self.name_list = []

    def get_path_list_from_lf(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".PNG", ".JPG", ".JPEG", ".BMP", ".TIF", ".TIFF"]
        if Path(self.input_path).suffix.lower() == '.txt':
            with open(self.input_path, "r",encoding='utf-8') as f:
                dataset = f.read().split('\n')
        elif Path(self.input_path).suffix.lower() == '.csv':
            with open(self.input_path, 'r', newline='',encoding='utf-8') as csvfile:
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
        i = 0
        output = []
        for path_ in self.path_list:
            no_check_list = [str(f.name)
                             for f in Path(path_).iterdir()]
            if len(no_check_list) > 100:
                self.dataset_mode = True
                no_check_list = np.sort(no_check_list)
                output.append(no_check_list)
            else:
                self.dataset_mode = False
                check_list = [str(f.name) for f in Path(path_).iterdir(
                ) if f.is_file() and f.suffix.lower() in self.format_group]
                check_list = np.sort(check_list)
                output.append(check_list)
            if not self.parallel_to_sequential:
                if i == 0:
                    break
            i += 1

        if self.parallel_to_sequential:
            return output
        else:
            return output[0]

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
            if self.type == 0 or self.type == 1:
                if self.parallel_to_sequential:
                    num_all = len(self.name_list[0])
                else:
                    num_all = len(self.path_list)
            else:
                num_all = self.img_num

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

            if row_col[0] >= 50:
                row_col[0] = 50

            if row_col[1] >= 50:
                row_col[1] = 50

            return row_col

    def get_flist(self):

        if self.type == 0 or self.type == 1:
            # one_dir_mul_dir_auto, one_dir_mul_dir_manual
            if self.parallel_to_sequential:
                flist_all = []
                for i in range(len(self.path_list)):
                    flist_all = flist_all + \
                        [str(Path(self.path_list[i])/self.name_list[i][k])
                         for k in range(len(self.name_list[i]))]

                try:
                    flist = [flist_all[k] for k in range(
                        self.img_count, self.img_count+self.count_per_action)]
                except:
                    flist = [flist_all[k]
                             for k in range(self.img_count, self.img_num)]

            else:
                flist = []
                for i in range(len(self.path_list)):
                    for k in range(self.img_count, self.img_count+self.count_per_action):
                        try:
                            flist += [str(Path(self.path_list[i]) /
                                          self.name_list[k])]
                        except:
                            # flist += [str(Path(self.path_list[i]) /
                            #               self.name_list[-1])]
                            pass

        elif self.type == 2:
            # one_dir_mul_img
            try:
                flist = [str(Path(self.path_list[0])/self.name_list[i])
                         for i in range(self.img_count, self.img_count+self.count_per_action)]
            except:
                flist = [str(Path(self.path_list[0])/self.name_list[i])
                         for i in range(self.img_count, self.img_num)]
        elif self.type == 3:
            # one file list
            # flist = self.path_list
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

    def get_dir_num(self):
        num = len(self.path_list)
        return num
