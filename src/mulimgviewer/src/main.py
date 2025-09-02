import platform
import threading
from pathlib import Path
import ffmpeg,os,time
from concurrent.futures import ThreadPoolExecutor
import atexit
import signal
import re
from fractions import Fraction

import numpy as np
import wx
from ..gui.main_gui import MulimgViewerGui
from .path_select import on_video_mode_change
from concurrent.futures import wait, ALL_COMPLETED

from .. import __version__ as VERSION
from .about import About
from .index_table import IndexTable
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
import json
import shutil
import copy

class SharedConfig:
    def __init__(self):
        self.cache_num = 2 #缓存数量
        self.skip_frames = 0 #跳过帧数
        self.thread = 4 #线程数量
        self.video_mode = False #视频模式
        self.interval = 1.0 #播放间隔
        self.is_playing = False #是否正在播放
        self.play_direction = 0 #播放方向
        self.real_video_path = [] #实际视频路径,以mp4结尾
        self.video_path = [] #视频缓存路径
        self.parallel_to_sequential = False #并行转为顺序
        self.parallel_sequential = False #并行转为顺序
        self.input_mode = 0 # 输入模式
        self.video_fps_list = [] #视频的fps
        self.batch_idx = 0 #当前批次索引
        self.count_per_action = 1 #每次处理的帧数
        self.video_num_list = []
        self.current_video_index = 0
        self.last_direction = 0

class VideoManager:
    def __init__(self, shared_config=None, ImgManager=None):
        self.shared_config = shared_config
        self.ImgManager = ImgManager
        self.cache_dir = Path("Video_frames")
        self.executor = ThreadPoolExecutor(max_workers=self.shared_config.thread)
        self._meta_cache = {}
        atexit.register(self._global_cleanup_cache, str(self.cache_dir))

    def calc_max_extractable_frames_single(self, video_path):
        '''使用 ffmpeg 获取视频信息，替换 cv2.VideoCapture'''
        step = self.shared_config.skip_frames + 1
        fps, total = self._get_meta(video_path)
        viewable = (total + step - 1) // step
        self.shared_config.video_fps_list.append(fps)
        self.shared_config.video_num_list.append(viewable)

    def _get_meta(self, video_path):
        if video_path in self._meta_cache:
            return self._meta_cache[video_path]
        p = ffmpeg.probe(str(video_path))
        vs = next(s for s in p['streams'] if s.get('codec_type')=='video')
        rate = vs.get('avg_frame_rate') or vs.get('r_frame_rate') or '0/1'
        fps = float(Fraction(rate)) if rate!='0/0' else 0.0
        nb = vs.get('nb_frames')
        if not nb: 
            dur = float(vs.get('duration') or p.get('format', {}).get('duration') or 0)
            nb = int(dur * fps) if fps>0 and dur>0 else 0
        total = int(nb)
        self._meta_cache[video_path] = (fps, total)
        return self._meta_cache[video_path]

    def init_video_frame_cache(self):
        video_paths = self.shared_config.real_video_path
        
        output_list = []
        
        for video_path in video_paths:
            video_path = Path(video_path)
            cache_name = video_path.stem  
            out_dir = self.cache_dir / cache_name
            out_dir.mkdir(parents=True, exist_ok=True)  
            output_list.append(str(out_dir))
        self.shared_config.video_path = output_list

    def update_thread_count(self, frame_num=-1):
        if frame_num == -1:
            thread_count = self.shared_config.thread
        else:
            user_max_threads = self.shared_config.thread  
            
            if frame_num < 10:
                thread_count = 1
            elif frame_num <= 30:
                thread_count = min(2, user_max_threads)
            else:
                thread_count = max(4, user_max_threads)
        
        current_workers = 0
        if hasattr(self, 'executor') and self.executor:
            try:
                current_workers = self.executor._max_workers
            except:
                current_workers = 0
        
        if current_workers != thread_count:
            
            if hasattr(self, 'executor') and self.executor:
                self.executor.shutdown(wait=False)
            
            self.executor = ThreadPoolExecutor(max_workers=thread_count)
        else:
            pass

    def update_cache(self):
        current_batch = self.shared_config.batch_idx
        cache_radius = self.shared_config.cache_num
        count_per_action = self.shared_config.count_per_action
        
        cache_start = max(0, (current_batch - cache_radius) * count_per_action)
        cache_end = (current_batch + cache_radius + 1) * count_per_action
        self.update_thread_count(cache_end - cache_start)

        if self.flag == 0:
            self.current_video_index = 0

        all_futures = []

        for video_idx, cache_dir in enumerate(self.shared_config.video_path):
            video_path = self.shared_config.real_video_path[video_idx]
            
            if self.flag == 0:
                self.calc_max_extractable_frames_single(video_path)
            
            frame_count = self.shared_config.video_num_list[video_idx]
            cache_end_actual = min(cache_end, frame_count)
            
            if cache_start < cache_end_actual:
                fut = self.executor.submit(
                    self._save_frame, 
                    video_path,  
                    cache_start,
                    cache_end_actual - 1,
                    video_idx
                )
                all_futures.append(fut)
            else:
                pass

        if all_futures:
            wait(all_futures, return_when=ALL_COMPLETED)
            for f in all_futures:
                f.result()
            for vid_i, _ in enumerate(self.shared_config.video_path):
                self._cleanup_out_of_range_cache(vid_i, cache_start, min(cache_end, self.shared_config.video_num_list[vid_i]))

        return

    def _cleanup_out_of_range_cache(self, video_idx, cache_start, cache_end_actual):
        cache_dir = self.shared_config.video_path[video_idx]
        if not os.path.isdir(cache_dir):
            return

        grace = max(0, self.shared_config.count_per_action)  # 保留一屏作为缓冲
        s = max(0, cache_start - grace)
        e = cache_end_actual + grace

        keep_names = { self._filename_converter(i, video_idx) for i in range(s, e) }

        deleted = kept = 0
        for filename in os.listdir(cache_dir):
            if filename.startswith("__tmp_"):
                continue
            if filename not in keep_names:
                try:
                    os.remove(os.path.join(cache_dir, filename))
                    deleted += 1
                except Exception as ex:
                    print(f"[_cleanup_out_of_range_cache] 删除失败 {filename}: {ex}")
            else:
                kept += 1
        self._cleanup_dead_directories()

    def _cleanup_dead_directories(self):
        """删除不在当前video_path列表中的目录"""
        current_video_dirs = set(self.shared_config.video_path)
        
        for item in self.cache_dir.iterdir():
            if item.is_dir() and str(item) not in current_video_dirs:
                shutil.rmtree(str(item))

    def _filename_converter(self, input_value, video_idx):
        '''双向转换：数字序号 <-> 帧秒文件名称'''
        
        if isinstance(input_value, int):
            step = self.shared_config.skip_frames + 1
            phys_idx = input_value * step  # 物理帧号
            fps = self.shared_config.video_fps_list[video_idx]
            
            # 计算时间
            t = phys_idx / fps
            sec_str = f"{t:.2f}".rstrip("0").rstrip(".") or "0"
            
            # 修复：直接使用物理帧号计算帧内序号
            k = (phys_idx % int(fps)) + 1
            
            # 边界检查
            if k > int(fps):
                k = int(fps)
            if k < 1:
                k = 1
            
            return f"{sec_str}s_frame_{k}.jpeg"
        
        else:
            if 's_frame_' in input_value:
                parts = input_value.split('s_frame_')
                sec_str = parts[0]
                
                fps = self.shared_config.video_fps_list[video_idx] 
                step = self.shared_config.skip_frames + 1
                
                time_seconds = float(sec_str)
                logical_idx = round(time_seconds * fps / step)
                
                return logical_idx
            else:
                return int(input_value.split('.')[0])
            
    def _save_frame(self, video_path, frame_start, frame_end, video_idx, max_retries=1):
        start_time = time.time()
        cache_dir = self.shared_config.video_path[video_idx]
        step = self.shared_config.skip_frames + 1
        target_size = 256

        # 计算还缺哪些（不存在或0字节都视为缺失）
        def list_missing(a, b):
            miss = []
            for idx in range(a, b + 1):
                dst = os.path.join(cache_dir, self._filename_converter(idx, video_idx))
                try:
                    if (not os.path.exists(dst)) or os.path.getsize(dst) == 0:
                        miss.append(idx)
                except Exception:
                    miss.append(idx)
            return miss

        # 把连续索引合并成区间，方便一次select抽帧
        def chunks(seq):
            if not seq: return []
            run = [seq[0]]; out = []
            for x in seq[1:]:
                if x == run[-1] + 1: run.append(x)
                else: out.append((run[0], run[-1])); run = [x]
            out.append((run[0], run[-1]))
            return out

        def extract_ranges(ranges):
            """把若干 [s,e] 区间批量抽帧到临时文件，再原子改名到目标名"""
            for s, e in ranges:
                n_start = s * step
                n_end   = e * step
                sel = f'between(n,{n_start},{n_end})*not(mod(n,{step}))'

                suffix = f"{os.getpid()}_{threading.get_ident()}_{int(time.time()*1000)}"
                tmp_tpl = os.path.join(cache_dir, f'__tmp_{video_idx}_{suffix}_%d.jpeg')

                (
                    ffmpeg
                    .input(str(video_path))
                    .filter('select', sel)
                    .filter('scale', target_size, -1, force_original_aspect_ratio='decrease')
                    .output(tmp_tpl, vsync='vfr', **{'q:v': 6}, start_number=s)
                    .global_args('-threads', '1', '-hide_banner', '-loglevel', 'error')
                    .overwrite_output()
                    .run(quiet=True)
                )

                for idx in range(s, e + 1):
                    src = os.path.join(cache_dir, f'__tmp_{video_idx}_{suffix}_{idx}.jpeg')
                    if os.path.exists(src):
                        if os.path.getsize(src) == 0:
                            try: os.remove(src)
                            except: pass
                            continue
                        dst = os.path.join(cache_dir, self._filename_converter(idx, video_idx))
                        try:
                            os.replace(src, dst)   
                        except Exception:
                            try: os.remove(src)
                            except: pass

        missing = list_missing(frame_start, frame_end)
        if missing:
            extract_ranges(chunks(missing))

        attempt = 0
        while attempt < max_retries:
            missing = list_missing(frame_start, frame_end)
            if not missing:
                break
            extract_ranges(chunks(missing))
            attempt += 1

        try:
            for name in os.listdir(cache_dir):
                if name.startswith(f'__tmp_{video_idx}_') and name.endswith('.jpeg'):
                    try: os.remove(os.path.join(cache_dir, name))
                    except: pass
        except Exception:
            pass

        end_time = time.time()
        left = list_missing(frame_start, frame_end)


    def collect_video_paths(self, dlg, selection_type):
        '''应对不同模式下,视频文件路径的不同获得方式'''
        video_paths = []
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return video_paths
            selected_path = dlg.GetPath()
            
            if selection_type == 1:
                for root, dirs, files in os.walk(selected_path):
                    for file in files:
                        if file.lower().endswith(('.mp4', '.avi', '.mov')):
                            video_paths.append(os.path.join(root, file))
                            
            elif selection_type == 0:
                if selected_path.lower().endswith(('.mp4', '.avi', '.mov')):
                    video_paths.append(selected_path)
        finally:
            dlg.Destroy()
        return video_paths

    def select_video(self, type=0):
        '''不同模式下,共用初始化部分'''
        self.flag = 0
        self.shared_config.video_fps_list = []
        self.shared_config.video_num_list = []
        wildcard = "Video files (*.mp4;*.avi;*.mov)|*.mp4;*.avi;*.mov"
        if type == 1:
            dlg = wx.DirDialog(None, "Select folder containing videos", style=wx.DD_DEFAULT_STYLE)
        elif type == 0:
            dlg = wx.FileDialog(None, "Choose video file", "", "",
                                wildcard, wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        self.shared_config.real_video_path = self.collect_video_paths(dlg, type)
        if self.shared_config.batch_idx == 0:
            self.init_video_frame_cache()
        if self.shared_config.video_path == []:
            return
        self.update_cache()
        self.flag = 1
        if len(self.shared_config.video_path) == 1:
            self.ImgManager.init(self.shared_config.video_path[0],type=self.shared_config.input_mode,parallel_to_sequential=self.shared_config.parallel_to_sequential,video_mode=self.shared_config.video_mode,video_fps_list=self.shared_config.video_fps_list,video_num_list=self.shared_config.video_num_list)
        else:
            self.ImgManager.init(self.shared_config.video_path,type=self.shared_config.input_mode,parallel_to_sequential=self.shared_config.parallel_to_sequential,video_mode=self.shared_config.video_mode,video_fps_list=self.shared_config.video_fps_list,video_num_list=self.shared_config.video_num_list)

        self.current_batch_idx = 0

    def _collect_missing_targets(self, batch_start: int, batch_end: int):
        missing = []

        frame_dirs = self.frame_cache_dir if isinstance(self.frame_cache_dir, (list, tuple)) else [self.frame_cache_dir]

        for vid_i, cache_dir in enumerate(frame_dirs):
            if not cache_dir:
                continue

            try:
                n = int(self.ImgManager.img_num_list[vid_i])
            except Exception:
                try:
                    n = int(self.ImgManager.img_num)
                except Exception:
                    n = 0

            s = max(0, int(batch_start))
            e = min(int(batch_end), max(0, n))

            for idx in range(s, e):
                try:
                    expect_path, ready, clamped = self._expected_path_for_idx(cache_dir, vid_i, idx)
                except Exception:
                    missing.append((cache_dir, idx, None, idx))
                    continue

                if not ready:
                    missing.append((cache_dir, idx, expect_path, clamped))

        return missing

    @staticmethod
    def _global_cleanup_cache(cache_dir_str):
        '''静态方法，确保能被正确调用'''
        try:
            cache_dir = Path(cache_dir_str)
            if cache_dir.exists():
                shutil.rmtree(str(cache_dir))
        except Exception as e:
            print(f"[cleanup] 清理缓存失败: {e}")
    
    def _cleanup_cache(self):
        '''实例方法清理'''
        self._global_cleanup_cache(str(self.cache_dir))
    
    def __del__(self):
        # 保留作为备用
        try:
            self._cleanup_cache()
        except:
            pass

class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type, default_path=None):
        self.shared_config = SharedConfig()
        super().__init__(parent)
        self.create_ImgManager()
        self.video_manager = VideoManager(shared_config=self.shared_config,ImgManager=self.ImgManager)
        self.shift_pressed=False
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self._is_closing = False
        acceltbl = wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_UP,
                                         self.menu_up.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DOWN,
                                         self.menu_down.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_RIGHT,
                                         self.menu_right.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_LEFT,
                                         self.menu_left.GetId()),
                                        (wx.ACCEL_NORMAL, wx.WXK_DELETE,
                                         self.menu_delete_box.GetId())
                                        ])
        self.SetAcceleratorTable(acceltbl)
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 1000
        self.height = 600
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1
        self.color_list = []
        self.box_id = -1
        self.xy_magnifier = []
        self.show_scale_proportion = 0
        self.key_status = {"shift_s": 0, "ctrl": 0, "alt": 0}
        self.indextablegui = None
        self.aboutgui = None
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.SetIcon(self.icon)
        self.m_statusBar1.SetStatusWidths([-2, -1, -4, -4])
        self.set_title_font()
        self.hidden_flag = 0
        self.button_open_all.SetToolTip("open")
        self.out_path_button.SetToolTip("out path")
        self.save_butoon.SetToolTip("save")
        self.left_arrow_button.SetToolTip("left arrow")
        self.right_arrow_button.SetToolTip("right arrow")
        self.refresh_button.SetToolTip("refresh")
        self.save_config_button.SetToolTip("save_configuration")
        self.magnifier.SetToolTip("magnifier")
        self.rotation.SetToolTip("rotation")
        self.flip.SetToolTip("flip")
        self.load_config_button.SetToolTip("load_configuration")
        self.reset_config_button.SetToolTip("reset_configuration")
        # Different platforms may need to adjust the width of the scrolledWindow_set
        sys_platform = platform.system()
        if sys_platform.find("Windows") >= 0:
            self.width_setting = 300
        elif sys_platform.find("Linux") >= 0:
            self.width_setting = 280
        elif sys_platform.find("Darwin") >= 0:
            self.width_setting = 350
        else:
            self.width_setting = 300

        self.SashPosition = self.width-self.width_setting
        self.m_splitter1.SetSashPosition(self.SashPosition)
        self.split_changing = False
        self.width_setting_ = self.width_setting
        self.play_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_play_timer, self.play_timer)
        self._from_timer = False     # 区分计时器触发/用户点击

        # Draw color to box
        self.colourPicker_draw.Bind(
            wx.EVT_COLOURPICKER_CHANGED, self.draw_color_change)

        # Check the software version
        self.myEVT_MY_TEST = wx.NewEventType()
        EVT_MY_TEST = wx.PyEventBinder(self.myEVT_MY_TEST, 1)
        self.Bind(EVT_MY_TEST, self.EVT_MY_TEST_OnHandle)
        self.version = VERSION
        self.check_version()

        # open default path
        if default_path:
            try:
                self.ImgManager.init(default_path, type=2)  # one_dir_mul_img
                self.show_img_init()
                self.ImgManager.set_action_count(0)
                self.show_img()
            except:
                pass

        self.load_configuration( None , config_name="output.json")

    def on_cache_num_change(self, event):
        self.shared_config.cache_num = int(self.m_textCtrl30.GetValue() or 2)

    def on_skip_changed(self, event):
        self.shared_config.skip_frames = max(0, int(self.m_textCtrl281.GetValue() or 0))

    def on_thread_change(self, event):
        self.shared_config.thread = int(self.m_textCtrl29.GetValue() or 4)
    
    def on_enable_video_mode(self, event):
        self.shared_config.video_mode = self.m_checkBox66.GetValue()
        on_video_mode_change(self.shared_config.video_mode)

    def on_interval_changed(self, event):
        self.shared_config.interval = float(self.m_textCtrl28.GetValue() or 1.0)

    def toggle_play(self, event):
        self.shared_config.is_playing = not self.shared_config.is_playing
        
        if self.shared_config.is_playing:
            self.shared_config.play_direction = 1 
        if self.shared_config.is_playing:
            interval = float(self.m_textCtrl28.GetValue() or 1.0)
            self.play_timer.Start(int(interval * 1000), oneShot=False)
            label = "⏸"
        else:
            self.play_timer.Stop()
            label = "▶"
        
        self.right_arrow_button1.SetLabel(label)

    def on_play_timer(self, event):
        if self.shared_config.is_playing:
            self._from_timer = True
            if self.shared_config.play_direction >= 0:
                self.next_img(None)  # 正向播放
            else:
                self.last_img(None)  # 倒放
            self._from_timer = False

    def parallel_sequential_fc(self, event):
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False

    def parallel_to_sequential_fc(self, event):
        self.shared_config.parallel_to_sequential = self.parallel_to_sequential.GetValue()
        if self.parallel_to_sequential.Value:
            self.parallel_sequential.Value = False
            self.shared_config.parallel_sequential = False

    def EVT_MY_TEST_OnHandle(self, event):
        self.about_gui(None, update=True, new_version=event.GetEventArgs())

    def check_version(self):
        t1 = threading.Thread(target=self.run, args=())
        t1.setDaemon(True)
        t1.start()

    def run(self):
        url = "https://api.github.com/repos/nachifur/MulimgViewer/releases/latest"
        try:
            # make request to be an optional depend
            import requests

            resp = requests.get(url)
            resp.encoding = 'UTF-8'
            if resp.status_code == 200:
                output = resp.json()
                # version is "rolling" means that it is run from source code
                if self.version == output["tag_name"] or self.version == "rolling":
                    # print("No need to update!")
                    pass
                else:
                    evt = MyTestEvent(self.myEVT_MY_TEST)
                    evt.SetEventArgs(output["tag_name"])
                    wx.PostEvent(self, evt)
        except:
            pass

    def set_title_font(self):
        font_path = Path("font")/"using"
        font_path = Path(get_resource_path(str(font_path)))
        files_name = [f.stem for f in font_path.iterdir()]
        files_name = np.sort(np.array(files_name)).tolist()
        for file_name in files_name:
            file_name = file_name.split("_", 1)[1]
            file_name = file_name.replace("-", " ")
            self.title_font.Append(file_name)
        self.title_font.SetSelection(0)
        font_paths = [str(f) for f in font_path.iterdir()]
        self.font_paths = np.sort(np.array(font_paths)).tolist()

    def frame_resize(self, event):
        self.auto_layout(frame_resize=True)

    def open_all_img(self, event):
        input_mode = self.choice_input_mode.GetSelection()
        self.shared_config.batch_idx = 0
        if input_mode == 0:
            self.shared_config.input_mode = 2
        elif input_mode == 1:
            self.shared_config.input_mode = 1
        elif input_mode == 2:
            self.shared_config.input_mode = 1
        else:
            self.shared_config.input_mode = 3
        self.ImgManager.get_video_value(video_mode=self.shared_config.video_mode, skip=self.shared_config.skip_frames)
        if input_mode == 0:
            self.one_dir_mul_img(event)
        elif input_mode == 1:
            self.one_dir_mul_dir_auto(event)
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)
        elif input_mode == 3:
            self.onefilelist()

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        if self.shared_config.video_mode:
            self.video_manager.select_video(type=1)
        else:
            dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                self.ImgManager.init(dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        self.show_img()
        self.choice_input_mode.SetSelection(1)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def close(self, event):
        if self._is_closing:
            return
        self._is_closing = True

        self.play_timer.Stop()
        self.shared_config.is_playing = False

        if hasattr(self, "video_manager") and hasattr(self.video_manager, "executor"):
            self.video_manager.executor.shutdown(wait=False, cancel_futures=True)

        if hasattr(self, 'show_bmp_in_panel'):
            del self.show_bmp_in_panel
        if hasattr(self, 'ImgManager'):
            if hasattr(self.ImgManager, 'clear_cache'):
                self.ImgManager.clear_cache()
        import gc
        gc.collect() 

        cache_base = "Video_frames"
        if os.path.isdir(cache_base):
            shutil.rmtree(cache_base)
        
        if hasattr(self, "indextablegui") and self.indextablegui: 
            self.indextablegui.Destroy()
        if hasattr(self, "aboutgui") and self.aboutgui: 
            self.aboutgui.Destroy()

        self.Destroy()
        os._exit(0)

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        try:
            if self.ImgManager.type == 1:
                input_path = self.ImgManager.input_path
            else:
                input_path = None
        except:
            input_path = None
        if self.shared_config.video_mode:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value)
        else:
            self.UpdateUI(1, input_path, self.parallel_to_sequential.Value)
        self.choice_input_mode.SetSelection(2)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def last_img(self, event):
        if self.shared_config.batch_idx == 0:
            pass
        else:
            if self.shared_config.video_mode:
                if self.shared_config.is_playing:
                    self.shared_config.play_direction = -1
                if self.shared_config.batch_idx > 0:
                    self.shared_config.batch_idx -= 1
                self.video_manager.update_cache()
            if self.ImgManager.img_num != 0:
                self.ImgManager.subtract()
                self.show_img_init()
                self.show_img()
                self.SetStatusText_((["Last", "-1", "-1", "-1"]))
            else:
                self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])

    def skip_to_n_img(self, event):
        
        if self.ImgManager.img_num == 0:
            return

        target = int(self.slider_img.GetValue())
        self.slider_value.SetValue(str(target))

        self.shared_config.batch_idx = target
        self.ImgManager.set_action_count(target)

        try:
            et = event.GetEventType()
            try:
                thumb_release = wx.EVT_SCROLL_THUMBRELEASE.evtType[0]
            except Exception:
                thumb_release = None
            if thumb_release and et == thumb_release:
                self.video_manager.update_cache()
                return
        except Exception:
            pass

        import time
        now = time.time()
        last = getattr(self, "_last_slider_render_ts", 0)
        if now - last < 0.12:   # 120ms 节流窗口
            return
        self._last_slider_render_ts = now

    def slider_value_change(self, event, value=None):
        if self.ImgManager.img_num == 0:
            return

        target_str = str(self.slider_value.GetValue()).strip()
        self.slider_value.SetValue(target_str)

        try:
            target = int(target_str)
        except Exception:
            return

        self.shared_config.batch_idx = target
        self.ImgManager.set_action_count(target)
        if self.shared_config.video_mode:
            self.video_manager.update_cache()

    def save_img(self, event):
        type_ = self.choice_output.GetSelection()
        if self.auto_save_all.Value:
            last_count_img = self.ImgManager.action_count
            self.ImgManager.set_action_count(0)
            if self.out_path_str != "" and Path(self.out_path_str).is_dir():
                continue_ = True
            else:
                continue_ = False
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            if continue_:
                for i in range(self.ImgManager.max_action_num):
                    self.SetStatusText_(
                        ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img***", "-1"])
                    self.ImgManager.get_flist()
                    if self.show_custom_func.Value:
                        self.ImgManager.layout_params[32] = True  # customfunc
                        self.ImgManager.save_img(self.out_path_str, type_)
                        self.ImgManager.layout_params[32] = False  # customfunc
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

                    self.ImgManager.add()
                self.ImgManager.set_action_count(last_count_img)
                self.SetStatusText_(
                    ["-1", "-1", "***Finish***", "-1"])
        else:
            try:
                self.SetStatusText_(
                    ["-1", "-1", "***"+str(self.ImgManager.name_list[self.ImgManager.action_count])+", saving img...***", "-1"])
            except:
                pass
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.save_img(self.out_path_str, type_)
            self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

            if flag == 0:
                self.SetStatusText_(
                    ["Save", str(self.ImgManager.action_count), "Save success!", "-1"])
            elif flag == 1:
                self.SetStatusText_(
                    ["-1", "-1", "***First, you need to select the output dir***", "-1"])
                self.out_path(event)
                self.SetStatusText_(
                    ["-1", "-1", "", "-1"])
            elif flag == 2:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            elif flag == 3:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", the number of img in sub folders is different***", "-1"])
            elif flag == 4:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: No magnification box, the magnified image can not be saved***", "-1"])
            elif flag == 5:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count), "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Save", "-1", "-1", "-1"])

    def refresh(self, event):
        self.show_img_init()
        
        if self.shared_config.video_mode:
            current_batch = self.shared_config.batch_idx
            current_count_per_action = self.shared_config.count_per_action
            
            last_batch = getattr(self, '_last_refresh_batch', None)
            last_count_per_action = getattr(self, '_last_refresh_count_per_action', None)
            
            if (last_batch != current_batch or 
                last_count_per_action != current_count_per_action or
                last_batch is None): 
                self.video_manager.update_cache()
                self._last_refresh_batch = current_batch
                self._last_refresh_count_per_action = current_count_per_action
            else:
                pass
        
        if self.ImgManager.img_num != 0:
            self.show_img()
        else:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        if self.shared_config.video_mode:
            self.video_manager.select_video(type=0)
        else:
            dlg = wx.DirDialog(None, "Choose input dir", "",
                               wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

            if dlg.ShowModal() == wx.ID_OK:
                self.ImgManager.init(dlg.GetPath(), type=2)
        if self.shared_config.video_path == []:
            return
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        self.show_img()
        self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])

    def onefilelist(self):
        self.SetStatusText_(["Choose the File List", "", "", "-1"])
        wildcard = "List file (*.txt; *.csv)|*.txt; *.csv|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.ImgManager.init(dlg.GetPath(), type=3)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(3)
        self.SetStatusText_(["Choose the File List", "-1", "-1", "-1"])

    def input_flist_parallel_manual(self, event):
        wildcard = "List file (*.txt;)|*.txt;|" \
            "All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "choose the Images List", "", "",
                            wildcard, wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            with open(dlg.GetPath(), "r") as f:
                input_path = f.read().split('\n')
            self.ImgManager.init(
                input_path[0:-1], type=1, parallel_to_sequential=self.parallel_to_sequential.Value)
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(2)

    def save_flist_parallel_manual(self, event):
        if self.out_path_str == "":
            self.SetStatusText_(
                ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
        else:
            try:
                np.savetxt(Path(self.out_path_str)/"input_flist_parallel_manual.txt",
                           self.ImgManager.input_path, fmt='%s')
            except:
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select parallel manual***", "-1"])
            else:
                self.SetStatusText_(
                    ["-1", "-1", "Save" + str(Path(self.out_path_str)/"input_flist_parallel_manual.txt")+" success!", "-1"])

    def out_path(self, event):
        dlg = wx.DirDialog(None, "Choose output dir", "", 
                        wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.out_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.out_path_str, 3)

        dlg.Destroy()

    def colour_change(self, event):
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def background_alpha(self, event):
        c = self.colourPicker_gap.GetColour()
        self.ImgManager.gap_alpha = self.background_slider.GetValue()
        self.ImgManager.gap_color = (
            c.red, c.green, c.blue, self.ImgManager.gap_alpha)

    def foreground_alpha(self, event):
        self.ImgManager.img_alpha = self.foreground_slider.GetValue()

    def delete_box(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                self.xy_magnifier.pop(self.box_id)
                self.refresh(event)
                self.SetStatusText_(
                    ["delete "+str(self.box_id)+"-th box",  "-1", "-1", "-1"])
        else:
            self.xy_magnifier = []
            self.refresh(event)
            self.SetStatusText_(["delete all box",  "-1", "-1", "-1"])
        if len(self.xy_magnifier)==0:
            self.box_position.SetSelection(0)

    def up_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y-speed
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[1] > 0:
                self.position[1] -= speed
            self.scrolledWindow_img.Scroll(
                self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Up",  "-1", "-1", "-1"])

    def down_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+0
                y = y+speed
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if (self.position[1]-1)*self.Uint[1] < size[1]:
                self.position[1] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[1])
        self.SetStatusText_(["Down",  "-1", "-1", "-1"])

    def right_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x+speed
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if (self.position[0]-1)*self.Uint[0] < size[0]:
                self.position[0] += speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
            else:
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], size[0])
        self.SetStatusText_(["Right",  "-1", "-1", "-1"])

    def left_img(self, event):
        speed = self.get_speed(name="pixel")

        if self.select_img_box.Value:
            if self.box_id != -1:
                box_point = self.xy_magnifier[self.box_id][0:4]
                show_scale = self.xy_magnifier[self.box_id][4:6]
                x, y = self.get_center_box(box_point)
                x = x-speed
                y = y+0
                self.xy_magnifier[self.box_id][0:4] = self.move_box_point(
                    x, y, show_scale)
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[0] > 0:
                self.position[0] -= speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Left",  "-1", "-1", "-1"])

    def SetStatusText_(self, texts):
        for i in range(self.Status_number):
            if texts[i] != '-1':
                self.m_statusBar1.SetStatusText(texts[i], i)

    def img_left_click(self, event):

        if self.magnifier.Value:
            x_0, y_0 = event.GetPosition()
            self.x_0 = x_0
            self.y_0 = y_0
            self.x = x_0
            self.y = y_0

        if self.select_img_box.Value:
            # select box
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([x, y])
            xy_grid = self.ImgManager.xy_grid[id]
            x = x-xy_grid[0]
            y = y-xy_grid[1]
            x_y_array = []
            for i in range(len(self.ImgManager.crop_points)):
                x_y_array.append(self.get_center_box(
                    self.ImgManager.crop_points[i][0:4]))
            x_y_array = np.array(x_y_array)
            dist = (x_y_array[:, 0]-x)**2+(x_y_array[:, 1]-y)**2
            self.box_id = np.array(dist).argmin()
            str_ = str(self.box_id)
            self.SetStatusText_(["Select "+str_+"-th box",  "-1", "-1", "-1"])

            self.start_flag = 0
        else:
            # magnifier
            if self.magnifier.Value:
                self.start_flag = 1
            else:
                self.start_flag = 0

            if self.magnifier.Value:
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])

        # rotation
        if self.rotation.Value:
            x, y = event.GetPosition()
            self.ImgManager.rotate(
                self.get_img_id_from_point([x, y], img=True))
            self.refresh(event)

            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])

        # flip
        if self.flip.Value:
            x, y = event.GetPosition()
            self.ImgManager.flip(self.get_img_id_from_point(
                [x, y], img=True), FLIP_TOP_BOTTOM=False)
            # self.ImgManager.flip(self.get_img_id_from_point(
            #     [x, y], img=True), FLIP_TOP_BOTTOM=self.checkBox_orientation.Value)
            self.refresh(event)

            self.SetStatusText_(["Flip", "-1", "-1", "-1"])

        # focus img
        if self.indextablegui or self.aboutgui:
            pass
        else:
            self.img_panel.Children[0].SetFocus()

        # show dir_id
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        second_txt = self.m_statusBar1.GetStatusText(1)
        second_txt = second_txt.split("/")[0]
        self.m_statusBar1.SetStatusText(second_txt+"/"+str(id)+"-th img", 1)

    def img_left_dclick(self, event):
        if self.select_img_box.Value:
            pass
        else:
            self.start_flag = 0
            self.xy_magnifier = []
            self.color_list = []
            self.box_position.SetSelection(0)

    def img_left_move(self, event):
        # https://stackoverflow.com/questions/57342753/how-to-select-a-rectangle-of-the-screen-to-capture-by-dragging-mouse-on-transpar
        if self.magnifier.Value != False and self.start_flag == 1:
            x, y = event.GetPosition()
            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            xy_limit = np.array(xy_grid) + \
                np.array(self.ImgManager.img_resolution_show)

            if self.x_0 < xy_limit[0] and self.y_0 < xy_limit[1]:

                if x < xy_limit[0] and y < xy_limit[1]:
                    self.x = x
                    self.y = y
                elif x > xy_limit[0] and y > xy_limit[1]:
                    self.x = xy_limit[0]
                    self.y = xy_limit[1]
                elif x > xy_limit[0]:
                    self.x = xy_limit[0]
                    self.y = y
                elif y > xy_limit[1]:
                    self.x = x
                    self.y = xy_limit[1]

        # show mouse position
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        RGBA = self.show_bmp_in_panel.getpixel((int(x), int(y)))
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        self.m_statusBar1.SetStatusText(str(x)+","+str(y)+"/"+str(RGBA), 0)

    def img_left_release(self, event):
        if self.magnifier.Value != False:
            self.start_flag = 0

            id = self.get_img_id_from_point([self.x_0, self.y_0])
            xy_grid = self.ImgManager.xy_grid[id]
            x = self.x-xy_grid[0]
            y = self.y-xy_grid[1]
            x_0 = self.x_0 - xy_grid[0]
            y_0 = self.y_0 - xy_grid[1]

            width = np.abs(x-x_0)
            height = np.abs(y-y_0)
            if width > 5 and height > 5:
                self.xy_magnifier = []
                self.color_list.append(self.colourPicker_draw.GetColour())

                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.ImgManager.ImgF.sort_box_point(
                    [x_0, y_0, x, y], show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                self.xy_magnifier.append(
                    points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                self.refresh(event)

    def img_right_click(self, event):
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        if self.select_img_box.Value:
            # move box
            if self.box_id != -1:
                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.move_box_point(x, y, show_scale)
                self.xy_magnifier[self.box_id] = points+show_scale+[
                    self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]]
                self.refresh(event)
        else:
            # new box
            if self.magnifier.Value:
                self.color_list.append(self.colourPicker_draw.GetColour())
                try:
                    show_scale = self.show_scale.GetLineText(0).split(',')
                    show_scale = [float(x) for x in show_scale]
                    points = self.move_box_point(x, y, show_scale)
                    self.xy_magnifier.append(
                        points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                except:
                    self.SetStatusText_(
                        ["-1",  "Drawing a box need click left mouse button!", "-1", "-1"])

                self.refresh(event)
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
            else:
                self.refresh(event)

    def move_box_point(self, x, y, show_scale):
        x_0, y_0, x_1, y_1 = self.xy_magnifier[0][0:4]
        show_scale_old = self.xy_magnifier[0][4:6]
        scale = [show_scale[0]/show_scale_old[0],
                 show_scale[1]/show_scale_old[1]]
        x_0 = int(x_0*scale[0])
        x_1 = int(x_1*scale[0])
        y_0 = int(y_0*scale[1])
        y_1 = int(y_1*scale[1])
        x_center_old, y_center_old = self.get_center_box(
            [x_0, y_0, x_1, y_1])
        delta_x = x-x_center_old
        delta_y = y-y_center_old
        return self.ImgManager.ImgF.sort_box_point([x_0+delta_x, y_0+delta_y, x_1+delta_x, y_1+delta_y], self.ImgManager.img_resolution_origin, show_scale)

    def get_center_box(self, box, more=False):
        x_0, y_0, x_1, y_1 = box
        width = abs(x_0-x_1)
        height = abs(y_0-y_1)
        x_center_old = x_0+int((width)/2)
        y_center_old = y_0+int((height)/2)
        if more:
            return [x_center_old, y_center_old, width, height]
        else:
            return [x_center_old, y_center_old]

    def img_wheel(self, event):
        # https://wxpython.org/Phoenix/docs/html/wx.MouseEvent.html

        # zoom
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value and self.key_status["ctrl"] == 1:
            if event.GetWheelDelta() >= 120:
                speed = self.get_speed(name="scale")
                self.adjust_show_scale_proportion()  # adjust show_scale_proportion
                # set show_scale
                if event.GetWheelRotation() > 0:
                    self.show_scale_proportion = self.show_scale_proportion+speed
                else:
                    self.show_scale_proportion = self.show_scale_proportion-speed
                if self.show_scale_proportion > 0:
                    show_scale = [1*(1+self.show_scale_proportion),
                                  1*(1+self.show_scale_proportion)]
                elif self.show_scale_proportion < 0:
                    show_scale = [1/(1-self.show_scale_proportion),
                                  1/(1-self.show_scale_proportion)]
                else:
                    show_scale = [1, 1]
                self.show_scale.Value = str(
                    round(show_scale[0], 2))+","+str(round(show_scale[1], 2))

                self.refresh(event)
            else:
                pass
        else:
            pass

        # move
        if self.shift_pressed:
            if event.GetWheelRotation()>0:
                self.left_img(event)
            else:
                self.right_img(event)
        if self.key_status["ctrl"] == 0 and event.GetWheelDelta() >= 120:
            if event.WheelAxis == 0 and self.shift_pressed == 0:
                if event.GetWheelRotation() > 0:
                    self.up_img(event)
                else:
                    self.down_img(event)
            else:
                if event.GetWheelRotation() > 0:
                    self.left_img(event)
                else:
                    self.right_img(event)

    def adjust_show_scale_proportion(self):
        # check "cur_scale", and adjust "self.show_scale_proportion"
        cur_scale = self.show_scale.GetLineText(0).split(',')
        cur_scale = [float(x) for x in cur_scale]
        if self.show_scale_proportion > 0:
            if cur_scale[0] == round(1*(1+self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        elif self.show_scale_proportion < 0:
            if cur_scale[0] == round(1/(1-self.show_scale_proportion), 2):
                pass
            else:
                if cur_scale[0] > 1:
                    self.show_scale_proportion = cur_scale[0]-1
                elif cur_scale[0] < 1 and cur_scale[0] > 0:
                    self.show_scale_proportion = 1-1/cur_scale[0]
                elif cur_scale[0] == 1:
                    self.show_scale_proportion = 0
                else:
                    pass
        else:
            self.show_scale_proportion = 0

    def key_down_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 0:
                self.key_status["ctrl"] = 1
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = True
            # 检查是否同时按下 Shift 和 'S'
        elif event.GetKeyCode() == ord('S'):
            if self.shift_pressed == True:
                # Shift + S 被按下，做出反应
                if self.key_status["shift_s"] == 0:
                    self.key_status["shift_s"] = 1
                elif self.key_status["shift_s"] == 1:
                    self.key_status["shift_s"] = 0

    def key_up_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 1:
                self.key_status["ctrl"] = 0
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = False

    def get_speed(self, name="pixel"):
        if name == "pixel":
            if self.key_status["shift_s"] == 1:
                speed = 5
            else:
                speed = 1
        elif name == "scale":
            if self.key_status["shift_s"] == 1:
                speed = 0.5
            else:
                speed = 0.1
        else:
            speed = None
        return speed

    def magnifier_fc(self, event):
        self.start_flag = 0
        i_cur = 0
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def rotation_fc(self, event):
        i_cur = 1
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            self.SetCursor(wx.Cursor(wx.CURSOR_POINT_RIGHT))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Rotate", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def flip_fc(self, event):
        i_cur = 2
        status_toggle = [self.magnifier, self.rotation, self.flip]
        if status_toggle[i_cur].Value:
            flip_cursor_path = Path(get_resource_path(str(Path("images"))))
            flip_cursor_path = str(flip_cursor_path/"flip_cursor.png")
            self.SetCursor(
                wx.Cursor((wx.Image(flip_cursor_path, wx.BITMAP_TYPE_PNG))))
            for i in range(len(status_toggle)):
                if i != i_cur and status_toggle[i].Value:
                    status_toggle[i].Value = False
            self.SetStatusText_(["Flip", "-1", "-1", "-1"])
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.Refresh()

    def show_img_init(self):
        layout_params = self.set_img_layout()
        if self.shared_config.video_mode:
            row_col = self.row_col.GetLineText(0).split(',')
            row_col = [int(x) for x in row_col]
            
            s = self.row_col_one_img.GetValue().replace('，', ',')
            r, c = map(int, [x.strip() for x in s.split(',')])
            one_img_product = r * c
            
            if self.shared_config.input_mode in (2, 3) or (self.shared_config.input_mode in (0, 1) and self.parallel_to_sequential.Value):
                count_per_action = row_col[0] * row_col[1] * one_img_product
            else:
                count_per_action = one_img_product
            self.shared_config.count_per_action = count_per_action
            self.ImgManager.img_num_list = self.shared_config.video_num_list
            if self.shared_config.parallel_to_sequential:
                if self.shared_config.video_mode:
                    self.ImgManager.img_num = sum(self.shared_config.video_num_list)
            else:
                if self.shared_config.video_mode:
                    self.ImgManager.img_num = max(self.shared_config.video_num_list)
        if layout_params:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                if self.parallel_to_sequential.Value:
                    count_per_action=layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1]
                else:
                    if self.parallel_sequential.Value:
                        count_per_action=layout_params[1][0]*layout_params[1][1]
                    else:
                        count_per_action=1
            elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                count_per_action=layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1]
            self.ImgManager.set_count_per_action(count_per_action)
        self.shared_config.count_per_action = count_per_action

    def set_img_layout(self):

        try:
            row_col = self.row_col.GetLineText(0).split(',')
            row_col = [int(x) for x in row_col]

            row_col_one_img = self.row_col_one_img.GetLineText(0).split(',')
            row_col_one_img = [int(x) for x in row_col_one_img]

            if row_col_one_img[0] == -1 and row_col_one_img[1] == -1:
                row_col_one_img= [1,1]
                row_col = self.ImgManager.layout_advice()
                self.row_col.SetValue(str(row_col[0])+","+str(row_col[1]))

            row_col_img_unit = self.row_col_img_unit.GetLineText(0).split(',')
            row_col_img_unit = [int(x) for x in row_col_img_unit]

            magnifer_row_col = self.magnifer_row_col.GetLineText(0).split(',')
            magnifer_row_col = [int(x) for x in magnifer_row_col]

            gap = self.gap.GetLineText(0).split(',')
            gap = [int(x) for x in gap]

            show_scale = self.show_scale.GetLineText(0).split(',')
            show_scale = [float(x) for x in show_scale]

            output_scale = self.output_scale.GetLineText(0).split(',')
            output_scale = [float(x) for x in output_scale]

            img_resolution = self.img_resolution.GetLineText(0).split(',')
            img_resolution = [int(x) for x in img_resolution]

            magnifer_resolution = self.magnifer_resolution.GetLineText(
                0).split(',')
            magnifer_resolution = [int(x) for x in magnifer_resolution]

            magnifier_show_scale = self.magnifier_show_scale.GetLineText(
                0).split(',')
            magnifier_show_scale = [float(x) for x in magnifier_show_scale]

            magnifier_out_scale = self.magnifier_out_scale.GetLineText(
                0).split(',')
            magnifier_out_scale = [float(x) for x in magnifier_out_scale]

            if self.checkBox_auto_draw_color.Value:
                # 10 colors built into the software
                color_list = [
                    wx.Colour(217, 26, 42, int(85/100*255)),
                    wx.Colour(147, 81, 166, int(65/100*255)),
                    wx.Colour(85, 166, 73, int(65/100*255)),
                    wx.Colour(242, 229, 48, int(95/100*255)),
                    wx.Colour(242, 116, 5, int(95/100*255)),
                    wx.Colour(242, 201, 224, int(95/100*255)),
                    wx.Colour(36, 132, 191, int(75/100*255)),
                    wx.Colour(65, 166, 90, int(65/100*255)),
                    wx.Colour(214, 242, 206, int(95/100*255)),
                    wx.Colour(242, 163, 94, int(95/100*255))]
                num_box = len(self.xy_magnifier)
                if num_box <= len(color_list):
                    self.color_list = color_list[0:num_box]
                else:
                    self.color_list = color_list + \
                        color_list[0:num_box-len(color_list)]

            color = self.color_list

            line_width = self.line_width.GetLineText(0).split(',')
            line_width = [int(x) for x in line_width]

            title_setting = [self.title_auto.Value,                     # 0
                             self.title_show.Value,                     # 1
                             self.title_down_up.Value,                  # 2
                             self.title_show_parent.Value,              # 3
                             self.title_show_prefix.Value,              # 4
                             self.title_show_name.Value,                # 5
                             self.title_show_suffix.Value,              # 6
                             self.title_font.GetSelection(),            # 7
                             self.title_font_size.Value,                # 8
                             self.font_paths,                           # 9
                             self.title_position.GetSelection(),        # 10
                             self.title_exif.Value]                     # 11

            if title_setting[0]:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    # one_dir_mul_dir_auto / one_dir_mul_dir_manual
                    if self.parallel_sequential.Value or self.parallel_to_sequential.Value:
                        title_setting[2:7] = [False, True, True, True, False]
                    else:
                        if self.shared_config.video_mode:
                            title_setting[2:7] = [False, False, True, True, False]
                        else:
                            title_setting[2:7] = [False, True, True, False, False]

                elif self.ImgManager.type == 2:
                    # one_dir_mul_img
                    title_setting[2:7] = [False, False, True, True, False]
                elif self.ImgManager.type == 3:
                    # read file list from a list file
                    title_setting[2:7] = [False, True, True, True, False]
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            return [row_col,                                # 0
                    row_col_one_img,                        # 1
                    row_col_img_unit,                       # 2
                    gap,                                    # 3
                    show_scale,                             # 4
                    output_scale,                           # 5
                    img_resolution,                         # 6
                    1 if self.magnifier.Value else 0,       # 7
                    magnifier_show_scale,                   # 8
                    color,                                  # 9
                    line_width,                             # 10
                    self.move_file.Value,                   # 11
                    self.keep_magnifer_size.Value,          # 12
                    self.image_interp.GetSelection(),       # 13
                    self.show_box.Value,                    # 14
                    self.show_box_in_crop.Value,            # 15
                    self.show_original.Value,               # 16
                    title_setting,                          # 17
                    self.show_magnifer.Value,               # 18
                    self.parallel_to_sequential.Value,      # 19
                    self.one_img.Value,                     # 20
                    self.box_position.GetSelection(),       # 21
                    self.parallel_sequential.Value,         # 22
                    self.auto_save_all.Value,               # 23
                    self.img_vertical.Value,                # 24
                    self.one_img_vertical.Value,            # 25
                    self.img_unit_vertical.Value,           # 26
                    self.magnifer_vertical.Value,           # 27
                    magnifer_resolution,                    # 28
                    magnifer_row_col,                       # 29
                    self.onetitle.Value,                    # 30
                    magnifier_out_scale,                    # 31
                    self.show_custom_func.Value,            # 32
                    self.out_path_str,                      # 33
                    self.Magnifier_format.GetSelection(),   # 34
                    self.save_format.GetSelection(),        # 35
                    self.show_unit.Value ]                  # 36

    def show_img(self):
        self._setup_img_panel()
        if self.show_custom_func.Value and self.out_path_str == "":
            self.out_path(None)
            self.ImgManager.layout_params[33] = self.out_path_str
        # check layout_params change
        try:
            if self.layout_params_old[0:2] != self.ImgManager.layout_params[0:2] or (self.layout_params_old[19] != self.ImgManager.layout_params[19]):
                action_count = self.ImgManager.action_count
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    parallel_to_sequential = self.parallel_to_sequential.Value
                else:
                    parallel_to_sequential = False
                self.ImgManager.init(
                    self.ImgManager.input_path, type=self.ImgManager.type, parallel_to_sequential=parallel_to_sequential)
                self.show_img_init()
                self.ImgManager.set_action_count(action_count)
                if self.index_table_gui:
                    self.index_table_gui.show_id_table(
                        self.ImgManager.name_list, self.ImgManager.layout_params)
        except:
            pass

        self.layout_params_old = self.ImgManager.layout_params
        self.slider_img.SetValue(self.ImgManager.action_count)
        self.slider_value.SetValue(str(self.ImgManager.action_count))
        self.slider_value_max.SetLabel(
            str(self.ImgManager.max_action_num-1))
        # Destroy the window to avoid memory leaks
        try:
            self.img_last.Destroy()
        except:
            pass

        # show img
        if self.ImgManager.max_action_num > 0:
            self.slider_img.SetMax(self.ImgManager.max_action_num-1)
            self.ImgManager.get_flist()

            # show the output image processed by the custom func; return cat(bmp, customfunc_img)
            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True  # customfunc
                self.ImgManager.stitch_images(
                    0, copy.deepcopy(self.xy_magnifier))
                self.ImgManager.layout_params[32] = False  # customfunc
            flag = self.ImgManager.stitch_images(
                0, copy.deepcopy(self.xy_magnifier))
            if flag == 0:
                bmp = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)
                self.show_bmp_in_panel = bmp
                self.img_size = bmp.size
                bmp = self.ImgManager.ImgF.PIL2wx(bmp)
                self.img_panel.SetSize(
                    wx.Size(self.img_size[0]+100, self.img_size[1]+100))
                self.img_last = wx.StaticBitmap(parent=self.img_panel,
                                                bitmap=bmp)
                self.img_panel.Children[0].SetFocus()
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_DOWN, self.img_left_click)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_DCLICK, self.img_left_dclick)
                self.img_panel.Children[0].Bind(
                    wx.EVT_MOTION, self.img_left_move)
                self.img_panel.Children[0].Bind(
                    wx.EVT_LEFT_UP, self.img_left_release)
                self.img_panel.Children[0].Bind(
                    wx.EVT_RIGHT_DOWN, self.img_right_click)
                self.img_panel.Children[0].Bind(
                    wx.EVT_MOUSEWHEEL, self.img_wheel)
                self.img_panel.Children[0].Bind(
                    wx.EVT_KEY_DOWN, self.key_down_detect)
                self.img_panel.Children[0].Bind(
                    wx.EVT_KEY_UP, self.key_up_detect)

            # status
            if self.ImgManager.type == 2 or ((self.ImgManager.type == 0 or self.ImgManager.type == 1) and self.parallel_sequential.Value):
                try:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count)+"/"+str(self.ImgManager.get_dir_num())+" dir", str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_count+self.ImgManager.count_per_action-1]), "-1"])
                except:
                    self.SetStatusText_(
                        ["-1", str(self.ImgManager.action_count)+"/"+str(self.ImgManager.get_dir_num())+" dir", str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+str(self.ImgManager.name_list[self.ImgManager.img_count])+"-"+str(self.ImgManager.name_list[self.ImgManager.img_num-1]), "-1"])
            else:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count)+"/"+str(self.ImgManager.get_dir_num())+" dir", str(self.ImgManager.img_resolution[0])+"x"+str(self.ImgManager.img_resolution[1])+" pixels / "+self.ImgManager.get_stitch_name(), "-1"])
            if flag == 1:
                self.SetStatusText_(
                    ["-1", str(self.ImgManager.action_count)+"/"+str(self.ImgManager.get_dir_num())+" dir", "***Error: "+str(self.ImgManager.name_list[self.ImgManager.action_count]) + ", during stitching images***", "-1"])
            if flag == 2:
                self.SetStatusText_(
                    ["-1", "-1", "No image is displayed! Check Show original/Show 🔍️/Show title.", "-1"])
        else:
            self.SetStatusText_(
                ["-1", "-1", "***Error: no image in this dir!***", "-1"])
        self.auto_layout()
        self.SetStatusText_(["Stitch", "-1", "-1", "-1"])
        
    def auto_layout(self, frame_resize=False):
        displays = (wx.Display(i) for i in range(wx.Display.GetCount()))
        displays_list = [display for display in displays]
        sizes = [display.GetGeometry().GetSize() for display in displays_list]
        screen_id = wx.Display.GetFromWindow(self)
        self.displaySize = sizes[screen_id]

        if self.hidden_flag == 1:
            offset_hight_img_show = 50
        else:
            offset_hight_img_show = 0

        if self.auto_layout_check.Value and (not frame_resize):
            if self.img_size[0] < self.width:
                if self.img_size[0]+self.width_setting+40 < self.width:
                    w = self.width
                else:
                    w = self.img_size[0]+self.width_setting+40
            elif self.img_size[0]+self.width_setting+40 > self.displaySize[0]:
                w = self.displaySize[0]
            else:
                w = self.img_size[0]+self.width_setting+40

            if self.img_size[1] < self.height:
                if self.img_size[1]+200 < self.height:
                    h = self.height
                else:
                    h = self.img_size[1]+200
                    if self.hidden_flag == 1:
                        h = h-50
            elif self.img_size[1]+200 > self.displaySize[1]:
                h = self.displaySize[1]
            else:
                h = self.img_size[1]+200
                if self.hidden_flag == 1:
                    h = h-50

            self.Size = wx.Size((w, h))

        if self.hidden_flag == 1:
            self.m_splitter1.SashPosition = self.Size[0]

        self.init_min_size()

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0]-self.width_setting, self.Size[1]-150+offset_hight_img_show)))

        # issue: You need to change the window size, then the scrollbar starts to display.
        self.scrolledWindow_img.FitInside()
        self.scrolledWindow_set.FitInside()

        self.Layout()
        self.Refresh()

    def init_min_size(self):
        self.scrolledWindow_set.SetMinSize(
            wx.Size((50, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((50, self.Size[1]-150)))

    def split_sash_pos_changing(self, event):

        self.init_min_size()
        self.split_changing = True

    def split_sash_pos_changed(self, event):
        self.SashPosition = self.m_splitter1.SashPosition

        if self.split_changing:
            self.width_setting = self.Size[0]-self.SashPosition

        self.scrolledWindow_set.SetMinSize(
            wx.Size((self.width_setting, -1)))
        self.scrolledWindow_img.SetMinSize(
            wx.Size((self.Size[0] - self.width_setting, self.Size[1]-150)))

        self.split_changing = False
        # print(self.SashPosition)

    def about_gui(self, event, update=False, new_version=None):
        self.aboutgui = About(self, self.version,
                              update=update, new_version=new_version)
        self.aboutgui.Show(True)

    def index_table_gui(self, event):
        if self.ImgManager.img_num != 0:
            if self.ImgManager.dataset_mode and self.out_path_str == "":
                self.SetStatusText_(
                    ["-1", "-1", "***Error: First, need to select the output dir***", "-1"])
            else:
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt saving...", "-1"])
                if self.ImgManager.type == 3:
                    self.indextablegui = IndexTable(
                        None, self.ImgManager.path_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                else:
                    self.indextablegui = IndexTable(
                        None, self.ImgManager.name_list, self.ImgManager.layout_params, self.ImgManager.dataset_mode, self.out_path_str, self.ImgManager.type, self.parallel_sequential.Value)
                if self.ImgManager.dataset_mode:
                    self.SetStatusText_(
                        ["-1", "-1", "index_table.txt save in "+self.out_path_str, "-1"])
        else:
            self.SetStatusText_(
                ["-1", "", "***Error: First, need to select the input dir***", "-1"])

    def create_ImgManager(self):
        self.ImgManager = ImgManager()
        self.colour_change([])
        return self.ImgManager

    def change_img_stitch_mode(self, event):
        self.ImgManager.img_stitch_mode = self.choice_normalized_size.GetSelection()

    def get_img_id_from_point(self, xy, img=False):
        # get img_id from grid points
        xy_grid = np.array(self.ImgManager.xy_grid)
        xy_cur = np.array([xy])
        xy_cur = np.repeat(xy_cur, xy_grid.shape[0], axis=0)
        res_ = xy_cur - xy_grid
        id_list = []
        for i in range(xy_grid.shape[0]):
            if res_[i][0] >= 0 and res_[i][1] >= 0:
                id_list.append(i)
            else:
                id_list.append(0)
        if img:
            return self.ImgManager.xy_grids_id_list[max(id_list)]
        else:
            return max(id_list)

    def title_down_up_fc(self, event):
        if self.title_down_up.Value:
            self.title_down_up.SetLabel('Up  ')
        else:
            self.title_down_up.SetLabel('Down')

    def title_auto_fc(self, event):
        titles = [self.title_down_up, self.title_show_parent,
                  self.title_show_name, self.title_show_suffix, self.title_show_prefix, self.title_position, self.title_exif]
        if self.title_auto.Value:
            for title in titles:
                title.Enabled = False
        else:
            for title in titles:
                title.Enabled = True

    def select_img_box_func(self, event):
        if self.select_img_box.Value:
            self.box_id = -1
        event.Skip()

    def draw_color_change(self, event):
        if self.select_img_box.Value:
            if self.box_id != -1:
                if self.checkBox_auto_draw_color.Value:
                    self.checkBox_auto_draw_color.Value = False
                self.color_list[self.box_id] = self.colourPicker_draw.GetColour()
                self.refresh(event)
        event.Skip()

    def hidden(self, event):
        if self.hidden_flag == 0:
            self.Sizer.Hide(self.m_panel1)
            self.scrolledWindow_set.Sizer.Hide(self.m_panel4)

            self.width_setting_ = self.width_setting
            self.width_setting = 0

            self.hidden_flag = 1
        else:
            self.Sizer.Show(self.m_panel1)
            self.scrolledWindow_set.Sizer.Show(self.m_panel4)

            self.width_setting = self.width_setting_

            self.hidden_flag = 0

        # issue: You need to change the window size, then the scrollbar starts to display.
        self.scrolledWindow_set.FitInside()
        self.auto_layout()

    def save_configuration(self, event):
        data = {
            'row_col': self.row_col.GetLineText(0),
            'row_col_one_img': self.row_col_one_img.GetLineText(0),
            'show_scale': self.show_scale.GetLineText(0),
            'row_col_img_unit': self.row_col_img_unit.GetLineText(0),
            'gap': self.gap.GetLineText(0),
            'magnifer_row_col': self.magnifer_row_col.GetLineText(0),
            'output_scale': self.output_scale.GetLineText(0),
            'img_resolution': self.img_resolution.GetLineText(0),
            'magnifer_resolution': self.magnifer_resolution.GetLineText(0),
            'magnifier_show_scale': self.magnifier_show_scale.GetLineText(0),
            'line_width': self.line_width.GetLineText(0),
            'magnifier_out_scale': self.magnifier_out_scale.GetLineText(0),
            'title_font_size': self.title_font_size.GetLineText(0),
            'box_position': self.box_position.GetSelection(),
            'choice_normalized_size': self.choice_normalized_size.GetSelection(),
            'choice_output': self.choice_output.GetSelection(),
            'image_interp': self.image_interp.GetSelection(),
            'Magnifier_format': self.Magnifier_format.GetSelection(),
            'title_font': self.title_font.GetSelection(),
            'parallel_sequential': self.parallel_sequential.GetValue(),
            'parallel_to_sequential': self.parallel_to_sequential.GetValue(),
            'auto_save_all': self.auto_save_all.GetValue(),
            'move_file': self.move_file.GetValue(),
            'img_vertical': self.img_vertical.GetValue(),
            'one_img_vertical': self.one_img_vertical.GetValue(),
            'img_unit_vertical': self.img_unit_vertical.GetValue(),
            'magnifer_vertical': self.magnifer_vertical.GetValue(),
            'show_original': self.show_original.GetValue(),
            'show_magnifer': self.show_magnifer.GetValue(),
            'title_show': self.title_show.GetValue(),
            'auto_layout_check': self.auto_layout_check.GetValue(),
            'one_img': self.one_img.GetValue(),
            'onetitle': self.onetitle.GetValue(),
            'customfunc': self.show_custom_func.GetValue(),
            'show_box': self.show_box.GetValue(),
            'show_box_in_crop': self.show_box_in_crop.GetValue(),
            'select_img_box': self.select_img_box.GetValue(),
            'title_auto': self.title_auto.GetValue(),
            'title_exif': self.title_exif.GetValue(),
            'title_show_parent': self.title_show_parent.GetValue(),
            'title_show_prefix': self.title_show_prefix.GetValue(),
            'title_show_name': self.title_show_name.GetValue(),
            'title_show_suffix': self.title_show_suffix.GetValue(),
            'title_down_up': self.title_down_up.GetValue(),
            'save_format': self.save_format.GetSelection(),
        }
        flip_cursor_path = Path(get_resource_path(str(Path("configs"))))
        flip_cursor_path = str(flip_cursor_path / "output.json")
        with open(flip_cursor_path, 'w') as file:
            json.dump(data, file, indent=1)

    def load_configuration(self, event, config_name="output.json"):
        flip_cursor_path = Path(get_resource_path(str(Path("configs"))))
        flip_cursor_path = str(flip_cursor_path / config_name)
        with open(flip_cursor_path, 'r') as file:
            data = json.load(file)
            self.row_col.SetValue(data['row_col'])
            self.row_col_one_img.SetValue(data['row_col_one_img'])
            self.show_scale.SetValue(data['show_scale'])
            self.row_col_img_unit.SetValue(data['row_col_img_unit'])
            self.gap.SetValue(data['gap'])
            self.magnifer_row_col.SetValue(data['magnifer_row_col'])
            self.output_scale.SetValue(data['output_scale'])
            self.img_resolution.SetValue(data['img_resolution'])
            self.magnifer_resolution.SetValue(data['magnifer_resolution'])
            self.magnifier_show_scale.SetValue(data['magnifier_show_scale'])
            self.line_width.SetValue(data['line_width'])
            self.magnifier_out_scale.SetValue(data['magnifier_out_scale'])
            self.title_font_size.SetValue(data['title_font_size'])
            self.box_position.SetSelection(data['box_position'])
            self.choice_normalized_size.SetSelection(data['choice_normalized_size'])
            self.choice_output.SetSelection(data['choice_output'])
            self.image_interp.SetSelection(data['image_interp'])
            self.Magnifier_format.SetSelection(data['Magnifier_format'])
            self.title_font.SetSelection(data['title_font'])
            self.parallel_sequential.SetValue(data['parallel_sequential'])
            self.parallel_to_sequential.SetValue(data['parallel_to_sequential'])
            self.auto_save_all.SetValue(data['auto_save_all'])
            self.move_file.SetValue(data['move_file'])
            self.img_vertical.SetValue(data['img_vertical'])
            self.one_img_vertical.SetValue(data['one_img_vertical'])
            self.img_unit_vertical.SetValue(data['img_unit_vertical'])
            self.magnifer_vertical.SetValue(data['magnifer_vertical'])
            self.show_original.SetValue(data['show_original'])
            self.show_magnifer.SetValue(data['show_magnifer'])
            self.title_show.SetValue(data['title_show'])
            self.auto_layout_check.SetValue(data['auto_layout_check'])
            self.one_img.SetValue(data['one_img'])
            self.onetitle.SetValue(data['onetitle'])
            self.show_custom_func.SetValue(data['show_custom_func'])
            self.show_box.SetValue(data['show_box'])
            self.show_box_in_crop.SetValue(data['show_box_in_crop'])
            self.select_img_box.SetValue(data['select_img_box'])
            self.title_auto.SetValue(data['title_auto'])
            self.title_exif.SetValue(data['title_exif'])
            self.title_show_parent.SetValue(data['title_show_parent'])
            self.title_show_prefix.SetValue(data['title_show_prefix'])
            self.title_show_name.SetValue(data['title_show_name'])
            self.title_show_suffix.SetValue(data['title_show_suffix'])
            self.title_down_up.SetValue(data['title_down_up'])
            self.save_format.SetSelection(data['save_format'])

    def reset_configuration(self, event):
        json_path = Path(get_resource_path(str(Path("configs"))))
        output_json_path = str(json_path / "output.json")
        output_s_json_path = str(json_path / "output_s.json")
        self.load_configuration(event, config_name="output_s.json")
        shutil.copy(output_s_json_path, output_json_path)

    def next_img(self, event):
        if self.shared_config.batch_idx >= self.ImgManager.img_num-1:
            pass
        else:
            if self.shared_config.video_mode:
                if self.shared_config.is_playing:
                    self.shared_config.play_direction = 1
                self.last_direction = self.shared_config.play_direction
                if self.shared_config.batch_idx < int(self.ImgManager.img_num) - 1:
                    self.shared_config.batch_idx += 1
                self.video_manager.update_cache()
            if getattr(self.ImgManager, "img_count", 0) < int(self.ImgManager.img_num) - 1:
                self.ImgManager.add()
            self.show_img_init()
            self.show_img()
            self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def _setup_img_panel(self):
        #本函数用于防止白色背景闪烁
        if getattr(self, "_img_panel_ready", False):
            return
        pnl = self.img_panel
        pnl.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        pnl.SetDoubleBuffered(True)
        pnl.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self._img_panel_ready = True

