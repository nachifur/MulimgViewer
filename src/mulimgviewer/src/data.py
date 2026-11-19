
import csv
import math
from pathlib import Path

import numpy as np

from .status_info import ImageSourceIndex
from .video_paths import FrameNames, manager_cache_format
from .video_timeline import page_segments

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
        self._status_source_index = ImageSourceIndex(self) if not video_mode else None
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
        extension = 'png' if manager_cache_format(self)==1 else 'jpeg'
        name_list = [FrameNames(count, self.video_fps_list[index], self.skip+1, extension)
                     for index, count in enumerate(self.img_num_list)]
        result = name_list[0] if len(self.img_num_list) == 1 else name_list
        return result

    def get_path_list_from_lf(self):
        format_group = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
        if Path(self.input_path).suffix.lower() == '.txt':
            with open(self.input_path, "r",encoding='utf-8-sig') as f:
                dataset = f.read().split('\n')
        elif Path(self.input_path).suffix.lower() == '.csv':
            with open(self.input_path, 'r', newline='',encoding='utf-8-sig') as csvfile:
                dataset = list(csv.reader(csvfile))
                dataset_ = []
                row = len(dataset)
                col = len(dataset[0]) if dataset else 0
                for items in dataset:
                    for item in items:
                        dataset_.append(item)
                dataset = dataset_
                self.csv_flag = 1
                self.csv_row_col = [row, col]
        else:
            dataset = []

        # Lists use their own directory as the base, matching video lists.
        dataset = [item.strip().strip('"') for item in dataset]
        base = Path(self.input_path).absolute().parent
        dataset = [str((Path(item).expanduser() if Path(item).expanduser().is_absolute()
                        else base / Path(item).expanduser())) for item in dataset if item.strip()]
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
        """Positive, bounded layout advice using source metadata only."""
        if getattr(self,'csv_flag',False):
            # A CSV supplies its own shape. Never return its mutable list.
            return [max(1,int(value)) for value in self.csv_row_col]
        if getattr(self,'video_mode',False):
            # Duration/frame counts must not turn one film into thousands of
            # simultaneous cells. Frames per video have their own layout.
            count=len(getattr(self,'path_list',()))
        elif getattr(self,'type',None) in (0,1):
            if getattr(self,'parallel_to_sequential',False):
                count=next((len(names) for names in getattr(self,'name_list',()) if len(names)),1)
            else:count=len(getattr(self,'path_list',()))
        else:count=getattr(self,'img_num',0)
        count=max(1,int(count))
        if count>2500:return [50,50]  # Preserve the existing 50 x 50 limit.
        if count<=2:return [1,count]
        def factor(value):
            return next((row for row in range(math.isqrt(value),1,-1) if value%row==0),1)
        row=factor(count)
        if row==1:  # Retain the original spare-cell rule for prime counts.
            count+=1;row=factor(count)
        return [min(50,row),min(50,count//row)]

    def get_flist(self):
        if self.video_mode:
            # Virtual frame names stay lazy, including cross-video pages. Work
            # is proportional to the visible page, never the full film length.
            self.name_list = self.video_name_list()
            size = max(1, int(self.count_per_action))
            segments = page_segments(self.video_num_list, size, self.img_count//size,
                                     self.parallel_to_sequential)
            flist = []
            for video, first, stop in segments:
                names = self.name_list if len(self.video_num_list)==1 else self.name_list[video]
                for index in range(first, stop):
                    flist.append(str(Path(self.path_list[video])/names[index]))
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

    def get_video_value(self,video_mode,skip):
        self.video_mode = video_mode
        self.skip = skip
