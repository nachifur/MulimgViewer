
import csv
from pathlib import Path

import numpy as np
import math,os

from .utils import solve_factor

class ImgData():
    """Multi-image database.
    Multi-image browsing, path management, loading multi-image data, automatic layout layout, etc. """

    def init(self, input_path, type=2, parallel_to_sequential=False, action_count=None, img_count=None,video_mode=False,video_fps_list=[],video_num_list=[],skip=0):
        self.input_path = input_path
        self.type = type
        self.video_mode = video_mode
        self.img_num_list = []
        self.parallel_to_sequential = parallel_to_sequential
        self.video_fps_list = video_fps_list
        self.video_num_list = video_num_list
        self.skip = skip
        self.max_action_num = 0

        self.init_flist()
        if self.parallel_to_sequential:
            if self.video_mode:
                self.img_num_list = self.video_num_list
                self.img_num = sum(self.img_num_list)
            else:
                list_ = []
                for name_list in self.name_list:
                    list_ = list_+name_list.tolist()
                self.img_num = len(list_)
        else:
            if self.video_mode:
                self.img_num_list = self.video_num_list
                self.img_num = max(self.img_num_list)
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

    def video_name_list(self):
        if not self.img_num_list:
            return []
        step = self.skip + 1
        max_len = max(self.img_num_list) if self.img_num_list else 0

        name_list = []
        for vidx, physical_frame_count in enumerate(self.img_num_list):
            fps = self.video_fps_list[vidx]
            fps_int = int(round(fps))

            # 关键修改：计算逻辑帧数（考虑跳帧）
            logical_frame_count = physical_frame_count // step

            one_video_names = []
            for logical_idx in range(logical_frame_count):  # 使用逻辑帧数
                physical_idx = logical_idx * step
                time_sec = physical_idx / fps

                sec_str = f"{time_sec:.2f}".rstrip("0").rstrip(".") or "0"

                frame_in_sec = (physical_idx % fps_int) + 1

                filename = f"{sec_str}s_frame_{frame_in_sec}.jpeg"
                one_video_names.append(filename)

                # 打印前5个和后5个文件名的详细信息
                if logical_idx < 5 or logical_idx >= logical_frame_count - 5:
                    pass

            name_list.append(one_video_names)

        # 重新计算max_len（基于逻辑帧数）
        if name_list:
            max_logical_len = max(len(video_names) for video_names in name_list)

            # 填充逻辑
            for vidx, one_video_names in enumerate(name_list):
                if one_video_names and len(one_video_names) < max_logical_len:
                    padding = max_logical_len - len(one_video_names)

        if len(name_list) > 0:
            for i, video_names in enumerate(name_list):
                pass

        result = name_list[0] if len(self.img_num_list) == 1 else name_list
        return result

    def get_path_list_from_lf(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
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
        skip = self.skip + 1
        if self.img_num % self.count_per_action:
            self.max_action_num = int(self.img_num/self.count_per_action/skip)+1
        else:
            self.max_action_num = int(self.img_num/self.count_per_action/skip)
         # 添加：确保当前action_count在有效范围内
        if hasattr(self, 'action_count'):
            if self.action_count >= self.max_action_num:
                self.action_count = self.max_action_num - 1
                self.img_count = self.action_count * self.count_per_action

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
        if self.video_mode:
            self.name_list = self.video_name_list()
            if self.type == 0 or self.type == 1:
            # one_dir_mul_dir_auto, one_dir_mul_dir_manual
                if self.parallel_to_sequential:
                    flist_all = []

                    cumulative_frames = 0  # 累积帧数

                    for i in range(len(self.path_list)):
                        actual_frame_count = self.video_num_list[i]  # 这个视频的实际可显示帧数

                        for k in range(actual_frame_count):
                            # 关键修改：使用视频内的局部索引 k，而不是全局索引
                            # k 是这个视频内的第几帧（考虑了跳帧后的逻辑帧号）
                            if hasattr(self, 'video_manager') and self.video_manager:
                                filename = self.video_manager._filename_converter(k, i)  # k是局部索引
                            else:
                                filename = self.name_list[i][k] if k < len(self.name_list[i]) else self.name_list[i][-1]

                            flist_all.append(str(Path(self.path_list[i]) / filename))

                    if self.img_count >= len(flist_all):
                        flist = [flist_all[-1]]
                    elif self.img_count + self.count_per_action > len(flist_all):
                        flist = flist_all[self.img_count:]
                        if not flist:
                            flist = [flist_all[-1]]
                    else:
                        flist = flist_all[self.img_count:self.img_count + self.count_per_action]
                else:
                    flist = []
                    for i in range(len(self.path_list)):
                        for k in range(self.count_per_action):
                            idx = self.img_count + k
                            try:
                                flist.append(str(Path(self.path_list[i]) / self.name_list[i][idx]))
                            except IndexError:
                                flist.append(str(Path(self.path_list[i]) / self.name_list[i][-1]))

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
        else:
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
                                flist += [str(Path(self.path_list[i]) /
                                            self.name_list[-1])]

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

    def get_video_value(self,video_mode,skip):
        self.video_mode = video_mode
        self.skip = skip
