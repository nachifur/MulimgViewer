
import csv
from pathlib import Path

import numpy as np

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
        name_list = []

        for vidx, physical_frame_count in enumerate(self.img_num_list):
            fps = self.video_fps_list[vidx]
            fps_int = int(round(fps))
            logical_frame_count = int(physical_frame_count)

            one_video_names = []
            for logical_idx in range(logical_frame_count):  # Using logical frame count
                physical_idx = logical_idx * step
                time_sec = physical_idx / fps

                sec_str = f"{time_sec:.2f}".rstrip("0").rstrip(".") or "0"
                frame_in_sec = (physical_idx % fps_int) + 1

                filename = f"{sec_str}s_frame_{frame_in_sec}.jpeg"
                one_video_names.append(filename)

            name_list.append(one_video_names)

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
        self.count_per_action = max(1, int(count_per_action))

        if self.img_num % self.count_per_action:
            self.max_action_num = int(self.img_num / self.count_per_action) + 1
        else:
            self.max_action_num = int(self.img_num / self.count_per_action)

        # Set a minimum to prevent indexing issues caused by zero batches
        self.max_action_num = max(1, int(self.max_action_num))

        # Ensure that the current action_count is within the valid range
        if hasattr(self, "action_count"):
            if self.action_count >= self.max_action_num:
                self.action_count = self.max_action_num - 1
                self.img_count = self.action_count * self.count_per_action

    def set_action_count(self, action_count):
        if not hasattr(self, "max_action_num"):
            self.max_action_num = 0
        if not hasattr(self, "count_per_action"):
            self.count_per_action = 1
        if not hasattr(self, "img_count"):
            self.img_count = 0
        if self.max_action_num <= 0:
            self.action_count = 0
            self.img_count = 0
            return
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
                    for i in range(len(self.path_list)):
                        actual_frame_count = self.video_num_list[i]  # The actual frame rate of this video

                        for k in range(actual_frame_count):
                            # Key modification: use local index k within the video, not global index
                            # k is the frame number within this video (considering skipped frames)
                            if hasattr(self, 'video_manager') and self.video_manager:
                                filename = self.video_manager._filename_converter(k, i)  # k is the local index
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

                except Exception:
                    flist = [str(Path(self.path_list[0])/self.name_list[i])
                            for i in range(self.img_count, self.img_num)]
            elif self.type == 3:
                # one file list
                # flist = self.path_list
                try:
                    flist = [str(Path(self.path_list[i]))
                            for i in range(self.img_count, self.img_count+self.count_per_action)]
                except Exception:
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
                    except Exception:
                        flist = [flist_all[k]
                                for k in range(self.img_count, self.img_num)]

                else:
                    flist = []
                    for i in range(len(self.path_list)):
                        for k in range(self.img_count, self.img_count+self.count_per_action):
                            try:
                                flist += [str(Path(self.path_list[i]) /
                                            self.name_list[k])]
                            except Exception:
                                flist += [str(Path(self.path_list[i]) /
                                            self.name_list[-1])]

            elif self.type == 2:
                # one_dir_mul_img
                try:
                    flist = [str(Path(self.path_list[0])/self.name_list[i])
                            for i in range(self.img_count, self.img_count+self.count_per_action)]
                except Exception:
                    flist = [str(Path(self.path_list[0])/self.name_list[i])
                            for i in range(self.img_count, self.img_num)]
            elif self.type == 3:
                # one file list
                # flist = self.path_list
                try:
                    flist = [str(Path(self.path_list[i]))
                            for i in range(self.img_count, self.img_count+self.count_per_action)]
                except Exception:
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
