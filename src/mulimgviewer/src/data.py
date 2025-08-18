
import csv
from pathlib import Path

import numpy as np
import cv2,math,os

from .utils import solve_factor

class ImgData():
    """Multi-image database.
    Multi-image browsing, path management, loading multi-image data, automatic layout layout, etc. """

    def init(self, input_path, type=2, parallel_to_sequential=False, action_count=None, img_count=None,video_mode=False, video_path=[],skip=0):
        self.input_path = input_path
        self.type = type
        self.video_fps_list = []
        self.video_mode = video_mode
        self.video_path = video_path
        self.img_num_list = []
        self.parallel_to_sequential = parallel_to_sequential
        self.skip = skip

        self.init_flist()
        if self.parallel_to_sequential:
            if self.video_mode:
                self.img_num_list = self.calc_max_extractable_frames(self.video_path,skip=self.skip)
                self.img_num = sum(self.img_num_list)
            else:
                list_ = []
                for name_list in self.name_list:
                    list_ = list_+name_list.tolist()
                self.img_num = len(list_)
        else:
            if self.video_mode:
                self.img_num_list = self.calc_max_extractable_frames(self.video_path,skip=self.skip)
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

    import math  # 确保在文件顶部

    def video_name_list(self):
        """
        生成各视频在 UI/展示用的文件名列表，名称格式为:
        {sec}s_frame_{k}.png
        其中：
        - sec 为物理时间（考虑了 skip），保留两位小数并去掉末尾 0/点；
        - k 为该秒内第几帧，范围 1..fps_int；
        - 仅生成 .png；
        - 若多视频长度不一致，短的用“最后一帧的名称”补齐到最长；
        - fps 直接来自 self.video_fps_list[vidx]；
        - 间隔帧数 skip 来自 self.skip_frames（物理帧 = 逻辑帧 * (skip+1)）。
        """
        # 各视频逻辑帧数
        img_num_list = list(getattr(self, "img_num_list", []) or [])
        if not img_num_list:
            return []

        # 直接用 self.video_fps_list
        fps_list = list(getattr(self, "video_fps_list", []) or [])
        if len(fps_list) < len(img_num_list):
            raise RuntimeError(f"[video_name_list] fps 列表长度不足：需要 {len(img_num_list)} 个，实际 {len(fps_list)}")

        # 读取 skip（间隔帧），物理帧 = 逻辑帧 * step
        try:
            step = int(getattr(self, "skip", 0)) + 1
        except Exception:
            step = 1
        if step < 1:
            step = 1

        # 需要补齐到的最大长度（兼容 self.img_num）
        try:
            max_len = max(int(x) for x in img_num_list) if img_num_list else 0
        except Exception:
            max_len = 0
        if hasattr(self, "img_num"):
            try:
                max_len = max(max_len, int(self.img_num))
            except Exception:
                pass

        name_list = []
        for vidx, n in enumerate(img_num_list):
            # 校验 fps
            fps_raw = fps_list[vidx]
            try:
                fps = float(fps_raw)
                if not math.isfinite(fps) or fps <= 0:
                    raise ValueError
            except Exception:
                raise RuntimeError(f"[video_name_list] 无效的 fps: video[{vidx}] -> {fps_raw}")

            # 用整数 fps 来计算帧号 k，避免浮点误差
            fps_int = max(1, int(round(fps)))

            # 逻辑帧数
            try:
                n = int(n) if n is not None else 0
            except Exception:
                n = 0

            one = []
            for i in range(max(n, 0)):
                # 物理帧号（考虑 skip）
                phys_idx = i * step

                # 物理时间（秒）：用浮点 fps 更准确
                t = phys_idx / fps
                sec_str = f"{round(t, 2):.2f}".rstrip("0").rstrip(".") or "0"

                # 该秒内第几帧（1..fps_int）
                k = (phys_idx % fps_int) + 1
                one.append(f"{sec_str}s_frame_{k}.png")

            # 补齐：重复最后一帧名称；若视频无帧，用 0s_frame_1.png
            last_name = one[-1] if one else "0s_frame_1.png"
            pad = max(0, max_len - n)
            if pad:
                one.extend([last_name] * pad)

            name_list.append(one)

        # 单视频保持旧行为：返回一维列表
        return name_list[0] if len(name_list) == 1 else name_list

    def update_state(self, path, mode):
        self.video_path = path
        self.video_mode = mode

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
        if self.video_mode:
            self.name_list = self.video_name_list()
            if self.type == 0 or self.type == 1:
            # one_dir_mul_dir_auto, one_dir_mul_dir_manual
                if self.parallel_to_sequential:
                    flist_all = []
                    for i in range(len(self.path_list)):
                        flist_all += [
                            str(Path(self.path_list[i]) / self.name_list[i][k])
                            for k in range(len(self.name_list[i]))
                        ]

                    if self.img_count >= len(flist_all):
                        # 超出最后一帧，保留最后一张
                        flist = [flist_all[-1]]
                    elif self.img_count + self.count_per_action > len(flist_all):
                        flist = flist_all[self.img_count:]
                        # 如果是空的，就保留最后一张
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
                                # 超出范围，强制使用最后一张
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

    def calc_max_extractable_frames(self, video_path, skip=0, return_fps=False):
        """
        计算每个视频在按“跳过帧数=skip”采样时能看到的帧数，并记录 fps。
        - video_path: str 或 list[str]
        - skip: 跳过的帧数（>=0），步长 = skip + 1
        - return_fps: 若为 True，则返回 (counts, fps_list)
        同时写入：
        - self.video_fps_list, self.video_fps_by_path
        """
        import cv2, os
        import numpy as np

        paths = [video_path] if isinstance(video_path, str) else list(video_path)
        s = int(skip) if isinstance(skip, int) and skip >= 0 else 0
        step = s + 1

        counts, fps_list = [], []

        for p in paths:
            cap = cv2.VideoCapture(p)
            if not cap.isOpened():
                counts.append(0); fps_list.append(None); continue

            # 1) 名义总帧
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total <= 0:
                # 旧容器兜底
                try:
                    cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1)
                    total = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
                except Exception:
                    total = 0

            # 2) 尾部校正：向后回退最多 3 帧，找到最后“可读”的 k
            safe_total = total
            if total > 0:
                try:
                    for back in range(0, 3):  # 回看末尾 0/1/2 帧
                        k = total - 1 - back
                        if k < 0: break
                        cap.set(cv2.CAP_PROP_POS_FRAMES, int(k))
                        ok, frame = cap.read()
                        if ok and frame is not None and getattr(frame, "size", 0) > 0:
                            safe_total = k + 1
                            break
                    else:
                        # 尾部都读不到，整个视频可能只有 total-3 之前可用
                        safe_total = max(0, total - 3)
                except Exception:
                    pass

            total = max(0, safe_total)

            # 3) FPS
            fps = cap.get(cv2.CAP_PROP_FPS)
            try: fps = float(fps)
            except Exception: fps = 0.0
            if not fps or (fps != fps) or fps < 1e-6:
                fps = 30.0  # 维持你原来的命名依赖；若不想“假 fps”，可改为 None，但要同步改写盘逻辑

            cap.release()

            # 4) 采样后可见帧数（从 0 开始，range(0, total, step) 的项数）
            viewable = (total + step - 1) // step  # = ceil(total/step)
            counts.append(viewable)
            fps_list.append(fps)

        self.video_fps_list = fps_list
        self.video_fps_by_path = {p: fps_list[i] for i, p in enumerate(paths)}

        if return_fps:
            return counts, fps_list
        return counts
