import copy
import platform
import threading
from pathlib import Path
import cv2,os,time
from concurrent.futures import ThreadPoolExecutor
import atexit
import signal
import re
import math

import numpy as np
import wx
from ..gui.main_gui import MulimgViewerGui

from .. import __version__ as VERSION  # type: ignore
from .about import About
from .index_table import IndexTable
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
import json
import shutil
import copy

class MulimgViewer (MulimgViewerGui):

    def __init__(self, parent, UpdateUI, get_type, default_path=None):
        self.shift_pressed=False
        super().__init__(parent)
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self._is_closing = False
        self.create_ImgManager()
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
        self.img_name = []
        self.position = [0, 0]
        self.Uint = self.scrolledWindow_img.GetScrollPixelsPerUnit()
        self.Status_number = self.m_statusBar1.GetFieldsCount()
        self.img_size = [-1, -1]
        self.width = 1000
        self.height = 600
        self.video_fps_list = []
        self.start_flag = 0
        self.x = -1
        self.x_0 = -1
        self.y = -1
        self.y_0 = -1
        self.color_list = []
        self.box_id = -1
        self.xy_magnifier = []
        self.real_video_path = []
        self.show_scale_proportion = 0
        self.key_status = {"shift_s": 0, "ctrl": 0, "alt": 0}
        self.video_mode = False
        self.cache_enabled = False
        self.skip_frames = self.m_textCtrl281.GetValue()
        self.count_per_action = 1
        self.indextablegui = None
        self.aboutgui = None
        self.current_batch_idx = 0
        self.icon = wx.Icon(get_resource_path(
            'mulimgviewer.png'), wx.BITMAP_TYPE_PNG)
        self.interval = float(self.m_textCtrl28.GetValue())
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
        self.cache_gen = 0   # 导航“世代”号，用来淘汰过期等待任务
        self.width_setting_ = self.width_setting
        self.thread = 4
        self.cache_num = 2
        self.play_direction = +1   # +1 正向；-1 反向
        self.frame_cache_dir = []
        self.play_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_play_timer, self.play_timer)
        self.total_frames = 0
        self._tick_running = False   # 定时器回调防重入
        self._from_timer = False     # 区分计时器触发/用户点击
        self.executor = ThreadPoolExecutor(max_workers=int(self.m_textCtrl29.GetValue()))  # 或者你想开的线程数

        # Draw color to box
        self.colourPicker_draw.Bind(
            wx.EVT_COLOURPICKER_CHANGED, self.draw_color_change)

        # Check the software version
        self.myEVT_MY_TEST = wx.NewEventType()
        EVT_MY_TEST = wx.PyEventBinder(self.myEVT_MY_TEST, 1)
        self.Bind(EVT_MY_TEST, self.EVT_MY_TEST_OnHandle)
        self.version = VERSION
        self.check_version()
        self.video_path = None
        self.is_playing = False
        self.manual_flag = 0
        if not hasattr(self, "_missing_by_gen"):  self._missing_by_gen = {}  # gen -> set((cache_dir, idx))
        if not hasattr(self, "_missing_lock"):
            self._missing_lock = threading.Lock()


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

    def EVT_MY_TEST_OnHandle(self, event):
        self.about_gui(None, update=True, new_version=event.GetEventArgs())

    def on_cache_num_change(self, event):
        try:
            self.cache_num = int(self.m_textCtrl30.GetValue())
        except ValueError:
            self.cache_num = 2  # 你默认的安全值

    def on_skip_changed(self, event):
        try:
            self.skip_frames = int(self.m_textCtrl281.GetValue())
        except ValueError:
            self.skip_frames = 0  # 默认：不跳帧
        if self.skip_frames < 0:
            self.skip_frames = 0

            # 让新的 skip 立即生效：换 cache 世代 + 预热当前批次
        try:
            self.cache_gen = getattr(self, "cache_gen", 0) + 1
            if getattr(self, "video_mode", False):
                cpa = int(getattr(self, "count_per_action", 1)) or 1
                cur = int(getattr(self, "current_batch_idx", 0)) * cpa
                if hasattr(self, "update_cache"):
                    self.update_cache(cur)
        except Exception:
            pass

    def on_thread_change(self, event):
        try:
            self.thread = int(self.m_textCtrl29.GetValue())
        except ValueError:
            self.thread = 4  # 你默认的安全值

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
        if self.video_mode:
            dlg = wx.DirDialog(None, "Select folder containing videos", style=wx.DD_DEFAULT_STYLE)
            video_paths = []
        else:
            dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            if self.video_mode:
                self.video_path = []
                selected_folder = dlg.GetPath()
                # 遍历该文件夹及其所有子目录
                for root, dirs, files in os.walk(selected_folder):
                    for file in files:
                        if file.lower().endswith(('.mp4', '.avi', '.mov')):
                            full_path = os.path.join(root, file)
                            video_paths.append(full_path)
                self.real_video_path = video_paths
                self.thread = int(self.m_textCtrl29.GetValue())
                self.cache_num = int(self.m_textCtrl30.GetValue())
                if video_paths and len(video_paths) == 1:
                    self.count_per_action = self.get_count_per_action(type=2)
                else:
                    self.count_per_action = self.get_count_per_action(type=1)
                for vp in video_paths:
                    cache = self.init_video_frame_cache(
                        Path(vp),
                        num_frames=(self.cache_num+1)*self.count_per_action,
                        max_threads=self.thread
                    )
                    self.video_path.append(cache)
                if video_paths and len(video_paths) == 1:
                    self.ImgManager.init(str(self.video_path[0]), type=2, video_mode=self.video_mode, video_path=video_paths[0],skip=self.skip_frames)
                else:
                    self.ImgManager.init(self.video_path, type=1, video_mode=self.video_mode, video_path=video_paths,skip=self.skip_frames)
            else:
                self.ImgManager.init(
                    dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
            self.current_batch_idx = 0
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(1)
            self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def close(self, event):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True
        self._shutdown = True  # 给后台任务一个退出信号

        # 1) 停计时器
        try:
            if hasattr(self, "play_timer") and self.play_timer.IsRunning():
                self.play_timer.Stop()
        except: pass

        # 2) 停播放状态（防止其它地方又续期）
        try:
            self.is_playing = False
        except: pass

        # 3) 关线程池（取消未开始的任务）
        try:
            if hasattr(self, "executor") and self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
        except: pass

        # 4) 关掉子窗口（如果可能还开着）
        try:
            if getattr(self, "indextablegui", None):
                self.indextablegui.Destroy()
        except: pass
        try:
            if getattr(self, "aboutgui", None):
                self.aboutgui.Destroy()
        except: pass

        # 5) OpenCV 等资源
        try:
            cv2.destroyAllWindows()
        except: pass

        # 6) 主窗口销毁 + 退出主循环（保险做法，两者都调用）
        try: self.Destroy()
        except: pass
        try:
            app = wx.GetApp()
            if app: app.ExitMainLoop()
        except: pass

    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        if self.video_mode:
            if self.real_video_path:
                self.video_path = []
                video_paths = self.real_video_path
                self.thread = int(self.m_textCtrl29.GetValue())
                self.cache_num = int(self.m_textCtrl30.GetValue())
                if video_paths and len(video_paths) == 1:
                    self.count_per_action = self.get_count_per_action(type=2)
                else:
                    self.count_per_action = self.get_count_per_action(type=1)
                for vp in video_paths:
                    cache = self.init_video_frame_cache(Path(vp),
                    num_frames=(self.cache_num+1)*self.count_per_action,
                    max_threads=self.thread
                    )
                    self.video_path.append(cache)
                if video_paths and len(video_paths) == 1:
                    self.ImgManager.init(str(self.video_path[0]), type=2, video_mode=self.video_mode, video_path=video_paths[0],skip=self.skip_frames)
                else:
                    self.ImgManager.init(self.video_path, type=1, video_mode=self.video_mode, video_path=video_paths,skip=self.skip_frames)
                self.current_batch_idx = 0
                self.show_img_init()
                self.ImgManager.set_action_count(0)
                self.show_img()
        try:
            if self.ImgManager.type == 1:
                input_path = self.ImgManager.input_path
            else:
                input_path = None
        except:
            input_path = None
        self.UpdateUI(1, input_path, self.parallel_to_sequential.Value)
        self.choice_input_mode.SetSelection(2)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    def last_img(self, event):
        assert hasattr(self, 'executor'), "self.executor 未初始化！"

        # 基本状态兜底
        if not hasattr(self, "next_frozen"):       self.next_frozen = False
        if not hasattr(self, "_missing_by_gen"):   self._missing_by_gen = {}   # gen -> set((cache_dir, idx))
        if not hasattr(self, "_missing_lock"):     self._missing_lock = threading.Lock()
        if not hasattr(self, "_play_loop_gen"):    self._play_loop_gen = 0

        # ========== 冻结中：不动索引，但记录“倒放一步”的意图 ==========
        if self.next_frozen:
            if not hasattr(self, "_pending_direction"):  self._pending_direction = None  # +1 / -1 / None
            if not hasattr(self, "_pending_step"):       self._pending_step = 0         # +1 / -1 / 0
            if not hasattr(self, "_pending_is_playing"): self._pending_is_playing = None# True/False/None

            if not getattr(self, "_from_timer", False):
                self._pending_direction = -1
                self._pending_step = -1
                try: self.SetStatusText_(["-1","-1","Queued: last after unfreeze","-1"])
                except: pass
            return

        # 播放中 & 用户点击上一张：只改方向
        if getattr(self, 'is_playing', False) and not getattr(self, '_from_timer', False):
            self.play_direction = -1
            try: self.right_arrow_button1.SetLabel("⏸")
            except: pass
            return

        # ---------- 换代 ----------
        self.cache_gen = int(getattr(self, "cache_gen", 0)) + 1
        cur_gen = self.cache_gen

        # 统一 frame_cache_dir（兼容单/多视频）
        if isinstance(getattr(self, "video_path", None), str):
            self.frame_cache_dir = [self.video_path]
        else:
            self.frame_cache_dir = list(getattr(self, "video_path", []) or [])

        if int(getattr(self.ImgManager, "img_num", 0)) == 0:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
            return

        # ========== 视频模式 ==========
        if getattr(self, "video_mode", False):
            prev_idx = int(getattr(self, "current_batch_idx", 0))
            if prev_idx <= 0:
                return  # 已在最前

            # 先算候选索引，不立刻提交
            proposed_idx = prev_idx - 1

            cpa = int(getattr(self, "count_per_action", 1)) or 1
            batch_start = proposed_idx * cpa
            batch_end   = batch_start + cpa

            # 预热滑窗（可选）
            if hasattr(self, "update_cache"):
                try: self.update_cache(batch_start)
                except Exception as e: print("[update_cache] warn:", e)

            # —— 用统一收集器检查缺帧（支持“秒_帧”，仅 .png）——
            missing_info = self._collect_missing_targets(batch_start, batch_end)
            # 只要 tuple 的 (cache_dir, idx) 交给等待器；路径/夹紧索引由等待器/渲染处处理
            missing = [(cd, i) for (cd, i, _expect_path, _clamped) in missing_info]

            if missing:
                # 冻结：登记集合、提交等待；不提交索引（保持 prev_idx）
                need = {(cd, i) for (cd, i) in missing}
                try:
                    self._missing_lock.acquire()
                    self._missing_by_gen[cur_gen] = need
                finally:
                    try: self._missing_lock.release()
                    except: pass

                self.next_frozen = True

                # 解冻后是否自动续播 & 方向（倒放）
                was_playing = bool(getattr(self, 'is_playing', False))
                self._resume_after_unfreeze = getattr(self, "_resume_after_unfreeze", False) or was_playing
                self._resume_play_dir = -1

                # 暂停 UI（不动索引）
                if getattr(self, 'is_playing', False):
                    self.is_playing = False
                    try: self.right_arrow_button1.SetLabel("▶")
                    except: pass

                # 提交等待任务（只等这一批的目标帧）
                for cache_dir, idx in need:
                    try:
                        self.executor.submit(self._await_and_notify, cache_dir, idx, cur_gen)
                    except Exception as e:
                        print("[submit await prev] error:", e)

                self.SetStatusText_(["-1","-1","Loading previous batch… (frozen)","-1"])
                return

            # —— 无缺帧：现在才提交索引并显示（顺序不乱） —— #
            self.current_batch_idx = proposed_idx
            self.ImgManager.subtract()
            self.show_img_init()
            self.show_img()
            self.SetStatusText_(["Last", "-1", "-1", "-1"])
            return

        # ========== 图片模式 ==========
        if self.ImgManager.img_num != 0:
            self.ImgManager.subtract()
            self.show_img_init()
            self.show_img()
            self.SetStatusText_((["Last", "-1", "-1", "-1"]))
        else:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])

    def _sync_play_label(self, playing: bool):
        """根据播放状态同步右侧播放按钮的文案：True=⏸，False=▶。"""
        try:
            import wx
            if not (hasattr(self, "right_arrow_button1") and self.right_arrow_button1):
                return
            txt = "⏸" if playing else "▶"
            if wx.IsMainThread():
                self.right_arrow_button1.SetLabel(txt)
                # 尽量马上可见
                try:
                    if hasattr(self, "Layout"):  self.Layout()
                    if hasattr(self, "Refresh"): self.Refresh(False)
                except Exception:
                    pass
            else:
                wx.CallAfter(self.right_arrow_button1.SetLabel, txt)
                wx.CallAfter(getattr(self, "Layout",  lambda: None))
                wx.CallAfter(getattr(self, "Refresh", lambda *_: None), False)
        except Exception as e:
            print(f"[_sync_play_label] fail: {e}")

    def skip_to_n_img(self, event):
        if self.ImgManager.img_num == 0:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
            return
        
        try:
            target = int(self.slider_img.GetValue())
        except Exception:
            target = 0

        try:
            self.slider_value.SetValue(str(target))
        except Exception:
            pass

        if not hasattr(self, "_skip_timer"):
            self._debounce_ms = getattr(self, "_debounce_ms", 120)  # 停顿阈值(毫秒)，按需调 80~200
            self._skip_timer = wx.Timer(self)

            # 持久回调（存到 self 上，避免被回收）
            def _on_skip_timer(evt, _self=self):
                tg = getattr(_self, "_pending_target", None)
                if tg is None:
                    return
                _self._pending_target = None
                # 仅此一次：把“最后稳定值”传给快路径
                _self.slider_value_change(None, value=tg)

            self._on_skip_timer = _on_skip_timer
            self.Bind(wx.EVT_TIMER, self._on_skip_timer, self._skip_timer)

        # 记录候选值并重启定时器
        self._pending_target = target
        if self._skip_timer.IsRunning():
            self._skip_timer.Stop()
        self._skip_timer.Start(self._debounce_ms, oneShot=True)

    def slider_value_change(self, event, value=None):
        # 冻结中：不接受滑块跳转，避免叠起等待
        if getattr(self, "next_frozen", False):
            try: self.SetStatusText_(["-1","-1","Busy decoding… (frozen)","-1"])
            except: pass
            return

        # 1) 解析目标值（允许 0；None/空串用当前计数兜底）
        if value is None:
            try:
                s = str(self.slider_value.GetValue()).strip()
            except Exception:
                s = ""
            if s == "":
                value = int(getattr(self.ImgManager, "action_count", 0))
            else:
                try:
                    value = int(s)
                except Exception:
                    # 非法输入回退到当前值
                    self.slider_value.SetValue(str(getattr(self.ImgManager, "action_count", 0)))
                    return

        # 无输入直接报错
        if int(getattr(self.ImgManager, "img_num", 0)) == 0:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
            return

        # 2) clamp & 同步 UI
        try:
            max_idx = max(0, int(getattr(self.ImgManager, "max_action_num", self.ImgManager.img_num)) - 1)
        except Exception:
            max_idx = max(0, int(self.ImgManager.img_num) - 1)
        target = max(0, min(int(value), max_idx))

        try: self.slider_value.SetValue(str(target))
        except: pass
        try: self.slider_img.SetValue(target)
        except: pass

        # 3) 换代 + 基础布局
        self.cache_gen = getattr(self, "cache_gen", 0) + 1
        cur_gen = self.cache_gen
        self.show_img_init()

        # 4) 视频模式
        if getattr(self, "video_mode", False):
            # 线程池兜底
            if not hasattr(self, "executor"):
                from concurrent.futures import ThreadPoolExecutor  # 以防外部未 import
                self.executor = ThreadPoolExecutor(max_workers=int(getattr(self, "thread", 4)))

            # 统一真实路径/缓存目录（与 refresh 中保持一致的兜底）
            real_paths = self.real_video_path if isinstance(self.real_video_path, (list, tuple)) else [self.real_video_path]
            frame_cache_dir = [self.video_path] if isinstance(self.video_path, str) else (self.video_path or [])
            if not frame_cache_dir or len(frame_cache_dir) != len(real_paths):
                frame_cache_dir = []
                for p in real_paths:
                    if not p:
                        frame_cache_dir.append(None)
                        continue
                    try:
                        # num_frames=0 只建目录不解码
                        cache_dir = self.init_video_frame_cache(p, num_frames=0, max_threads=int(getattr(self, "thread", 4)))
                    except Exception:
                        base = os.path.dirname(str(p))
                        cache_dir = os.path.join(base, "frames_cache")
                        try: os.makedirs(cache_dir, exist_ok=True)
                        except Exception: pass
                    frame_cache_dir.append(cache_dir)
                self.video_path = frame_cache_dir[0] if len(frame_cache_dir) == 1 else frame_cache_dir
            self.frame_cache_dir = frame_cache_dir

            # 批次信息
            if isinstance(self.real_video_path, str):
                cpa = int(self.get_count_per_action(type=2)) or 1
            else:
                cpa = int(self.get_count_per_action(type=1)) or 1

            # 设置 ImgManager 位置（与原逻辑一致）
            self.ImgManager.set_action_count(target)
            self.current_batch_idx = target // cpa
            batch_start = self.current_batch_idx * cpa
            batch_end   = min(batch_start + cpa, int(self.ImgManager.img_num))

            # 可选：滑动窗口预热
            if hasattr(self, "update_cache"):
                try: self.update_cache(batch_start)
                except Exception: pass

            # 跳帧步长（解码精确批次时使用）
            try:
                step = int(self.m_textCtrl281.GetValue() or 0)
            except Exception:
                step = int(getattr(self, "skip_frames", 0) or 0)
            if step < 0:
                step = 0
            step = step + 1

            # 提交定点拆帧（仅对 [batch_start, batch_end)）
            for vid_i, (cache_dir, src_path) in enumerate(zip(self.frame_cache_dir, real_paths)):
                if not src_path or not cache_dir:
                    continue
                try:
                    # 按每视频的真实帧数夹上界
                    try:
                        max_frame = int(self.ImgManager.img_num_list[vid_i])
                    except Exception:
                        max_frame = int(self.ImgManager.img_num)
                    s = batch_start
                    e = min(batch_end, max_frame)
                    if s < e:
                        try:
                            self.executor.submit(self._predecode_exact_batch, src_path, cache_dir, s, e, step, cur_gen)
                        except Exception:
                            pass
                except Exception:
                    pass

            # —— 关键：缺帧检查改为“命名无关”的统一映射 —— #
            # 只检查目标批次（batch_start..batch_end-1），既支持旧名 idx.png，也支持新名 {sec}s_frame_{k}.png
            if hasattr(self, "_collect_missing_targets"):
                missing_info = self._collect_missing_targets(batch_start, batch_end)
                # 只取 (cache_dir, idx) 交给 await；路径/夹紧索引在 _await_and_notify 内部再判定
                need_pairs = {(cd, i) for (cd, i, _exp, _clamped) in missing_info}
            else:
                # 兜底：如果没有该工具函数，则退化为“只认 .png 的旧名”（尽量不发生）
                need_pairs = set()
                img_num_list = getattr(self.ImgManager, "img_num_list", [self.ImgManager.img_num])
                for vid_i, (cache_dir, max_frame) in enumerate(zip(self.frame_cache_dir, img_num_list)):
                    s = batch_start
                    e = min(batch_end, max_frame)
                    for idx in range(s, e):
                        p = os.path.join(cache_dir, f"{idx}.png")
                        try:
                            ready = os.path.exists(p) and os.path.getsize(p) > 0
                        except Exception:
                            ready = False
                        if not ready:
                            need_pairs.add((cache_dir, idx))

            # 初始化缺帧容器（兜底）
            if not hasattr(self, "_missing_by_gen"):
                self._missing_by_gen = {}
                self._missing_lock = threading.Lock()

            if need_pairs:
                # 冻结：登记集合、提交等待；不推进索引（保持当前）
                try:
                    self._missing_lock.acquire()
                    self._missing_by_gen[cur_gen] = set(need_pairs)
                finally:
                    try: self._missing_lock.release()
                    except: pass

                self.next_frozen = True
                # 滑块跳转默认不自动续播；若你想支持解冻后继续播，可在此设 _resume_after_unfreeze=True
                self._resume_after_unfreeze = False
                self._resume_play_dir = +1  # 无所谓，统一成正向

                # 提交等待任务（仅目标批次）
                for cache_dir, idx in need_pairs:
                    try:
                        self.executor.submit(self._await_and_notify, cache_dir, idx, cur_gen)
                    except Exception:
                        pass

                self.SetStatusText_(["-1","-1","Seeking… (waiting target frame(s), frozen)","-1"])
                return

            # —— 整批已就绪：直接显示 —— #
            self.show_img()
            self.SetStatusText_(["Skip", "-1", "-1", "-1"])
            return

        # 5) 图片模式（非视频）
        self.ImgManager.set_action_count(target)
        self.show_img()
        self.SetStatusText_(["Skip", "-1", "-1", "-1"])

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
        if self.video_mode:
            assert hasattr(self, 'executor'), "self.executor 未初始化！"

            # 无输入直接报错
            if int(getattr(self.ImgManager, "img_num", 0)) == 0:
                self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
                return

            # 冻结中：避免叠起新一轮等待
            if getattr(self, "next_frozen", False):
                try: self.SetStatusText_(["-1","-1","Busy decoding… (frozen)","-1"])
                except: pass
                return

            # —— 记录刷新前状态 —— #
            was_playing = bool(getattr(self, "is_playing", False))
            old_cpa     = int(getattr(self, "count_per_action", 1) or 1)
            old_action  = int(getattr(self.ImgManager, "action_count", getattr(self, "current_batch_idx", 0)) or 0)
            old_abs_idx = max(0, old_action * old_cpa)

            # —— 读取最新参数 —— #
            try: self.thread = int(self.m_textCtrl29.GetValue())
            except Exception: self.thread = int(getattr(self, "thread", 4))
            try: self.cache_num = int(self.m_textCtrl30.GetValue())
            except Exception: self.cache_num = int(getattr(self, "cache_num", 1))

            vp = getattr(self, "real_video_path", None)
            if not vp:
                self.SetStatusText_(["-1", "", "***Error: No input video***", "-1"])
                return

            # —— 计算新的 cpa，并重建缓存 —— #
            if isinstance(vp, str):
                new_cpa = int(self.get_count_per_action(type=2)) or 1
            else:
                new_cpa = int(self.get_count_per_action(type=1)) or 1
            self.count_per_action = new_cpa

            if isinstance(vp, str):
                self.video_mode = True
                try:
                    self.video_path = self.init_video_frame_cache(
                        vp,
                        num_frames=(self.cache_num + 1) * new_cpa,
                        max_threads=int(self.thread),
                    )
                except Exception as e:
                    print("[init_video_frame_cache] single error:", e)
                    self.video_path = None
                self.ImgManager.init(self.video_path, type=2, video_mode=True, video_path=vp, skip=getattr(self, "skip_frames", 0))
            else:
                self.video_mode = True
                caches = []
                for p in vp:
                    try:
                        cache = self.init_video_frame_cache(
                            Path(p),
                            num_frames=(self.cache_num + 1) * new_cpa,
                            max_threads=int(self.thread),
                        )
                    except Exception as e:
                        print("[init_video_frame_cache] multi error:", e)
                        cache = None
                    caches.append(cache)
                self.video_path = caches
                self.ImgManager.init(self.video_path, type=1, video_mode=True, video_path=vp, skip=getattr(self, "skip_frames", 0))

            # 统一 frame_cache_dir
            if isinstance(self.video_path, str):
                self.frame_cache_dir = [self.video_path]
            else:
                self.frame_cache_dir = list(self.video_path or [])

            # —— 将旧位置映射到新 cpa —— #
            new_action = int(old_abs_idx // new_cpa)
            try:
                total_frames = int(getattr(self.ImgManager, "img_num", 0))
            except Exception:
                total_frames = 0
            max_action = max(0, (total_frames - 1) // new_cpa) if total_frames > 0 else 0
            new_action = max(0, min(new_action, max_action))

            try: self.ImgManager.set_action_count(new_action)
            except Exception: pass
            self.current_batch_idx = int(new_action)

            # —— 预热滑窗到新批次 —— #
            batch_start = new_action * new_cpa
            if hasattr(self, "update_cache"):
                try: self.update_cache(batch_start)
                except Exception as e: print("[update_cache] warn:", e)

            # —— 整批缺帧检查（统一用 _expected_path_for_idx；只认 .png；越界按最后一帧夹紧）—— #
            self.cache_gen = int(getattr(self, "cache_gen", 0)) + 1
            cur_gen = self.cache_gen

            missing = []  # [(cache_dir, logical_idx)]
            frame_cache_dirs = (
                self.frame_cache_dir
                if isinstance(self.frame_cache_dir, (list, tuple))
                else [self.frame_cache_dir]
            )
            batch_end = batch_start + new_cpa

            for v_idx, cache_dir in enumerate(frame_cache_dirs):
                if not cache_dir:
                    continue
                for logical_idx in range(batch_start, batch_end):
                    try:
                        _expect_path, ready, _clamped = self._expected_path_for_idx(
                            cache_dir, v_idx, logical_idx
                        )
                    except Exception as e:
                        # 取不到 fps 或其它异常 → 视为未就绪，方便定位
                        print("[refresh/_expected_path_for_idx] warn:", e)
                        ready = False
                    if not ready:
                        missing.append((cache_dir, logical_idx))

            # 初始化缺帧容器（兜底）
            if not hasattr(self, "_missing_by_gen"):
                self._missing_by_gen = {}
                self._missing_lock = threading.Lock()

            if missing:
                need = {(cd, i) for (cd, i) in missing}
                try:
                    self._missing_lock.acquire()
                    self._missing_by_gen[cur_gen] = need
                finally:
                    try: self._missing_lock.release()
                    except: pass

                # 冻结 & 记录恢复标志（仅当刷新前在播）
                self.next_frozen = True
                self._resume_after_unfreeze = bool(was_playing)
                self._resume_play_dir = +1  # 刷新视为“前进态”

                if getattr(self, "is_playing", False):
                    self.is_playing = False
                    try: self.right_arrow_button1.SetLabel("▶")
                    except: pass

                # 提交等待任务（整批）
                for cache_dir, logical_idx in need:
                    try:
                        self.executor.submit(self._await_and_notify, cache_dir, logical_idx, cur_gen)
                    except Exception as e:
                        print("[submit await refresh] error:", e)

                self.SetStatusText_(["-1","-1","Refreshing… (waiting batch, frozen)","-1"])
                return

            # —— 整批已就绪：直接显示 —— #
            self.show_img_init()
            self.show_img()
            self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

            # 如刷新前在播：按间隔继续播放（不立即推进）
            if was_playing:
                try:
                    self.is_playing = True
                    try: self.right_arrow_button1.SetLabel("⏸")
                    except: pass
                    interval_ms = int(getattr(self, "play_interval", 0.2) * 1000)
                    if hasattr(self, "play_timer"):
                        self.play_timer.StartOnce(interval_ms)
                except Exception:
                    pass

        else:
            if self.ImgManager.img_num != 0:
                self.show_img_init()
                self.show_img()
            else:
                self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
            self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        if self.video_mode:
            wildcard = "Video files (*.mp4;*.avi;*.mov)|*.mp4;*.avi;*.mov"
            dlg = wx.FileDialog(None, "Choose video file", "", "",
                                wildcard, wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        else:
            dlg = wx.DirDialog(None, "Choose input dir", "",
                               wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            if self.video_mode:
                video_path = dlg.GetPath()
                self.real_video_path = video_path
                self.thread = int(self.m_textCtrl29.GetValue())
                self.cache_num = int(self.m_textCtrl30.GetValue())
                self.count_per_action = self.get_count_per_action(type=2)

                self.video_path = self.init_video_frame_cache(Path(video_path), num_frames=(self.cache_num+1)*self.count_per_action, max_threads=self.thread)
                self.ImgManager.init(self.video_path, type=2, video_mode=self.video_mode, video_path = video_path,skip=self.skip_frames)
                if isinstance(self.video_path, str):
                    self.video_path = [self.video_path]  # 单个也转成列表
            else:
                self.ImgManager.init(dlg.GetPath(), type=2)
            self.current_batch_idx = 0
            self.show_img_init()
            self.ImgManager.set_action_count(0)
            self.show_img()
            self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])

    def onefilelist(self):
        self.SetStatusText_(["Choose the File List", "", "", "-1"])
        wildcard = "List file (*.txt; *.csv)|*.txt;*.csv|" \
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
        if len(self.img_name) != 0:
            self.SetStatusText_(
                ["Choose out dir", str(self.ImgManager.action_count), self.img_name[self.ImgManager.action_count], "-1"])
        else:
            self.SetStatusText_(["Choose out dir", "-1", "-1", "-1"])
        dlg = wx.DirDialog(None, "Choose out dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

        if dlg.ShowModal() == wx.ID_OK:
            self.out_path_str = dlg.GetPath()
            self.m_statusBar1.SetStatusText(self.out_path_str, 3)

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
        if layout_params != False:
            # setting
            self.ImgManager.layout_params = layout_params
            if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                if self.parallel_to_sequential.Value:
                    self.ImgManager.set_count_per_action(
                        layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1])
                else:
                    if self.parallel_sequential.Value:
                        self.ImgManager.set_count_per_action(
                            layout_params[1][0]*layout_params[1][1])
                    else:
                        self.ImgManager.set_count_per_action(1)
            elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                self.ImgManager.set_count_per_action(
                    layout_params[0][0]*layout_params[0][1]*layout_params[1][0]*layout_params[1][1])

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
                        if self.video_mode:
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
        # 一次性初始化：关闭擦背景/开双缓冲
        self._setup_img_panel()

        # 若用户勾选自定义处理且没路径，先补齐
        if self.show_custom_func.Value and self.out_path_str == "":
            self.out_path(None)
            self.ImgManager.layout_params[33] = self.out_path_str

        # ============ 仅在布局参数变化时，才重建 ImgManager/重排 ============
        try:
            if (self.layout_params_old[0:2] != self.ImgManager.layout_params[0:2]) or \
            (self.layout_params_old[19]  != self.ImgManager.layout_params[19]):
                action_count = self.ImgManager.action_count
                if self.ImgManager.type in (0, 1):
                    parallel_to_sequential = self.parallel_to_sequential.Value
                else:
                    parallel_to_sequential = False
                if not self.video_mode:
                    self.ImgManager.init(self.ImgManager.input_path, type=self.ImgManager.type,
                                        parallel_to_sequential=parallel_to_sequential)
                self.show_img_init()
                self.ImgManager.set_action_count(action_count)
                if self.index_table_gui:
                    self.index_table_gui.show_id_table(self.ImgManager.name_list, self.ImgManager.layout_params)
        except Exception:
            pass

        self.layout_params_old = self.ImgManager.layout_params

        # 同步 UI 数值（这两行不会触发布局）
        try: self.slider_img.SetValue(self.ImgManager.action_count)
        except: pass
        try: self.slider_value.SetValue(str(self.ImgManager.action_count))
        except: pass
        try: self.slider_value_max.SetLabel(str(self.ImgManager.max_action_num-1))
        except: pass

        # ===== 不要每帧 Destroy / 新建控件（这是闪烁元凶）=====
        # 原来的 self.img_last.Destroy() 删掉

        if self.ImgManager.max_action_num <= 0:
            self.SetStatusText_(["-1", "-1", "***Error: no image in this dir!***", "-1"])
            return

        # 限制滑块上限
        try: self.slider_img.SetMax(self.ImgManager.max_action_num-1)
        except: pass

        self.ImgManager.get_flist()

        # 拼图 / 自定义叠加
        if self.show_custom_func.Value:
            self.ImgManager.layout_params[32] = True
            self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier))
            self.ImgManager.layout_params[32] = False

        flag = self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier))
        if flag == 0:
            # 生成 PIL 图
            pil_img = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)

            self.show_bmp_in_panel = pil_img
            self.img_size = pil_img.size

            # —— 将 PIL 转成 wx.Bitmap（一次性换图，避免先白后画）——
            wxbmp = self.ImgManager.ImgF.PIL2wx(pil_img)

            # 懒创建：只创建一次 StaticBitmap，并关掉它自己的擦背景
            if not getattr(getattr(self, "img_last", None), "GetBitmap", lambda: None)() \
            or not self.img_last.GetBitmap().IsOk():
                self.img_last = wx.StaticBitmap(parent=self.img_panel, bitmap=wxbmp)
                # 事件只绑定一次
                try:
                    self.img_last.Bind(wx.EVT_LEFT_DOWN,   self.img_left_click)
                    self.img_last.Bind(wx.EVT_LEFT_DCLICK, self.img_left_dclick)
                    self.img_last.Bind(wx.EVT_MOTION,      self.img_left_move)
                    self.img_last.Bind(wx.EVT_LEFT_UP,     self.img_left_release)
                    self.img_last.Bind(wx.EVT_RIGHT_DOWN,  self.img_right_click)
                    self.img_last.Bind(wx.EVT_MOUSEWHEEL,  self.img_wheel)
                    self.img_last.Bind(wx.EVT_KEY_DOWN,    self.key_down_detect)
                    self.img_last.Bind(wx.EVT_KEY_UP,      self.key_up_detect)
                    self.img_last.SetBackgroundStyle(wx.BG_STYLE_PAINT)
                    self.img_last.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
                except Exception:
                    pass
            else:
                # 仅更新位图；用 Freeze/Thaw 降低闪烁
                try:
                    self.img_panel.Freeze()
                    self.img_last.SetBitmap(wxbmp)
                finally:
                    self.img_panel.Thaw()

            # —— 不要每帧改尺寸；仅在确实变化时设置最小尺寸（避免反复 Layout）——
            desired = wx.Size(self.img_size[0], self.img_size[1])
            if desired != getattr(self, "_last_img_min_size", None):
                try:
                    self.img_panel.SetMinSize(desired)
                    self._last_img_min_size = desired
                    # 仅此时再做一次轻量布局
                    try: self.img_panel.Layout()
                    except: pass
                except Exception:
                    pass

            # 焦点只需要在首次设置
            try:
                if not getattr(self, "_img_focus_once", False):
                    self.img_last.SetFocus()
                    self._img_focus_once = True
            except Exception:
                pass

        # ===== 状态栏 =====
        if self.ImgManager.type == 2 or (self.ImgManager.type in (0, 1) and self.parallel_sequential.Value):
            try:
                self.SetStatusText_(["-1",
                                    f"{self.ImgManager.action_count}/{self.ImgManager.get_dir_num()} dir",
                                    f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / "
                                    f"{self.ImgManager.name_list[self.ImgManager.img_count]}-"
                                    f"{self.ImgManager.name_list[self.ImgManager.img_count+self.ImgManager.count_per_action-1]}",
                                    "-1"])
            except Exception:
                self.SetStatusText_(["-1",
                                    f"{self.ImgManager.action_count}/{self.ImgManager.get_dir_num()} dir",
                                    f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / "
                                    f"{self.ImgManager.name_list[self.ImgManager.img_count]}-"
                                    f"{self.ImgManager.name_list[self.ImgManager.img_num-1]}",
                                    "-1"])
        else:
            self.SetStatusText_(["-1",
                                f"{self.ImgManager.action_count}/{self.ImgManager.get_dir_num()} dir",
                                f"{self.ImgManager.img_resolution[0]}x{self.ImgManager.img_resolution[1]} pixels / "
                                f"{self.ImgManager.get_stitch_name()}",
                                "-1"])

        if flag == 1:
            self.SetStatusText_(["-1",
                                f"{self.ImgManager.action_count}/{self.ImgManager.get_dir_num()} dir",
                                f"***Error: {self.ImgManager.name_list[self.ImgManager.action_count]}, during stitching images***",
                                "-1"])
        elif flag == 2:
            self.SetStatusText_(["-1", "-1", "No image is displayed! Check Show original/Show 🔍️/Show title.", "-1"])

        # 只有在面板最小尺寸变化时才需要较重的布局；否则不要每帧 auto_layout（避免擦背景）
        # 如果你必须保留，至少加一个条件
        try:
            if getattr(self, "_last_auto_layout_size", None) != getattr(self, "_last_img_min_size", None):
                self.auto_layout()
                self._last_auto_layout_size = getattr(self, "_last_img_min_size", None)
        except Exception:
            pass

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

    def parallel_sequential_fc(self, event):
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False

    def parallel_to_sequential_fc(self, event):
        if self.parallel_to_sequential.Value:
            self.parallel_sequential.Value = False

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

    def on_enable_video_mode(self, event):
        self.video_mode = self.m_checkBox66.GetValue()
        app = wx.GetApp()
        try:
            if hasattr(app, "frame") and len(app.frame) > 1 and app.frame[1] is not None:
                app.frame[1].on_video_mode_change(self.video_mode)
        except Exception as e:
            print("[Main] forward video_mode failed:", e)
        return self.video_mode

    def on_enable_cache(self, event):
        self.cache_enabled = self.m_checkBox67.GetValue()
        return self.cache_enabled

    def init_video_frame_cache(self, input_path, num_frames=8, max_threads=4):
        input_path = Path(input_path)
        output_list = []

        def extract_head_frames(video_path: Path):
            video_name = video_path.stem
            out_dir = Path("video_frames") / video_name

            # 清旧缓存
            if out_dir.exists():
                shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return None

            # 记录该目录的 fps，供 _cv_imwrite_atomic 使用
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            if fps <= 0 or not np.isfinite(fps):
                cap.release()
                raise ValueError(f"[init_video_frame_cache] 获取 fps 失败：{video_path}")
            if not hasattr(self, "_cache_fps_map"): self._cache_fps_map = {}
            self._cache_fps_map[str(out_dir)] = fps

            frame_idx = 0
            while frame_idx < num_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                h, w = frame.shape[:2]
                scale = 256 / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                resized = cv2.resize(frame, (new_w, new_h))

                # 按旧接口传入 idx.png；实际命名在 _cv_imwrite_atomic 内完成
                self._cv_imwrite_atomic(str(out_dir / f"{frame_idx}.png"), resized)
                frame_idx += 1

            cap.release()
            return str(out_dir)

        # 多线程执行
        executor = ThreadPoolExecutor(max_workers=max_threads)

        if input_path.is_file() and input_path.suffix.lower() == ".mp4":
            return extract_head_frames(input_path)

        elif input_path.is_dir():
            video_paths = list(input_path.glob("*.mp4"))
            futures = [executor.submit(extract_head_frames, v) for v in video_paths]
            for f in futures:
                result = f.result()
                if result:
                    output_list.append(result)
            return output_list

        else:
            raise ValueError("路径既不是 .mp4 文件，也不是包含 .mp4 的目录")

    def get_count_per_action(self,type=2):
        if type == 2 or type == 3:
            s  = 1
            row_col = self.row_col.GetLineText(0).split(',')
            s = self.row_col_one_img.GetValue().replace('，', ',')
            r, c = map(int, [x.strip() for x in s.split(',')])
            prod = r * c
            row_col = [int(x) for x in row_col]
            product = row_col[0] * row_col[1] *prod
        if type == 1 or type == 0:
            if self.parallel_to_sequential.Value:
                s  = 1
                row_col = self.row_col.GetLineText(0).split(',')
                s = self.row_col_one_img.GetValue().replace('，', ',')
                r, c = map(int, [x.strip() for x in s.split(',')])
                prod = r * c
                row_col = [int(x) for x in row_col]
                product = row_col[0] * row_col[1] *prod
            else:
                if self.parallel_sequential.Value:
                    row_col = self.row_col.GetLineText(0).split(',')
                    s = self.row_col_one_img.GetValue().replace('，', ',')
                    r, c = map(int, [x.strip() for x in s.split(',')])
                    product = r * c
                else:
                    product = 1
        return product

        # 2. 事件处理函数
    
    def on_interval_changed(self, event):
        val = self.m_textCtrl28.GetValue()
        try:
            self.interval = float(val)
        except ValueError:
            self.interval = 1.0  # 你默认的安全值

    def toggle_play(self, event):
        interval_str = self.m_textCtrl28.GetValue()
        try:
            interval = float(interval_str)
        except ValueError:
            interval = 1.0

        # === 修改点：不管正放还是倒放，只要在播放，就暂停 ===
        if self.is_playing:
            self.is_playing = False
            self.play_timer.Stop()
            self.right_arrow_button1.SetLabel("▶")
            return

        # 未在播放 -> 开始正向播放
        self.is_playing = True
        self.play_direction = +1
        self.play_timer.Start(int(interval * 1000), oneShot=False)
        self.right_arrow_button1.SetLabel("⏸")

    def on_play_timer(self, event):
        if not self.is_playing:
            return
        if self._tick_running:
            return
        self._tick_running = True
        self._from_timer = True
        try:
            if getattr(self, "play_direction", +1) >= 0:
                self.next_img(None)
            else:
                self.last_img(None)
        finally:
            self._from_timer = False
            self._tick_running = False
            if self.is_playing:
                try:
                    interval = float(self.m_textCtrl28.GetValue())
                except Exception:
                    interval = 1.0
                self.play_timer.Start(max(30, int(interval*1000)), oneShot=True)

    def _start_playback(self):
        self.is_playing = True
        try:
            interval = float(self.m_textCtrl28.GetValue())
        except Exception:
            interval = 1.0
        self.play_timer.Start(max(30, int(interval*1000)), oneShot=True)

    def _stop_playback(self):
        self.is_playing = False
        try:
            if self.play_timer.IsRunning():
                self.play_timer.Stop()
        except Exception:
            pass

    def next_img(self, event):
        assert hasattr(self, 'executor'), "self.executor 未初始化！"

        if not hasattr(self, "next_frozen"):       self.next_frozen = False
        if not hasattr(self, "_missing_by_gen"):   self._missing_by_gen = {}   # gen -> set((cache_dir, idx))
        if not hasattr(self, "_missing_lock"):     self._missing_lock = threading.Lock()
        if not hasattr(self, "_play_loop_gen"):    self._play_loop_gen = 0     # 自驱动播放循环代号

       # 已冻结：不执行，但闩住意图，解冻后按意图执行
        if self.next_frozen:
            if not hasattr(self, "_pending_direction"): self._pending_direction = None   # +1 / -1 / None
            if not hasattr(self, "_pending_step"):      self._pending_step = 0           # +1 表示解冻后走一步 next；-1 表示走一步 last
            if not hasattr(self, "_pending_is_playing"):self._pending_is_playing = None  # True/False/None（None 表示不改）

            # 用户点击（非定时器）→ 记录“向前一步”
            if not getattr(self, "_from_timer", False):
                self._pending_direction = +1
                self._pending_step = +1   # 只记录一步；重复点击会覆盖为“最后一次意图”
                try: self.SetStatusText_(["-1","-1","Queued: next after unfreeze","-1"])
                except: pass

            # 冻结时不要反复改播放状态，避免图标闪烁；只在进入冻结时改过一次即可
            return

        # 正在播放 & 用户点击：只切方向（定时器触发会带 _from_timer=True，不会走到这里）
        if getattr(self, 'is_playing', False) and not getattr(self, '_from_timer', False):
            self.play_direction = +1
            try: self.right_arrow_button1.SetLabel("⏸")
            except: pass
            return

        # ---------- 换代 ----------
        self.cache_gen = getattr(self, "cache_gen", 0) + 1
        cur_gen = self.cache_gen

        # 规范 frame_cache_dir
        if isinstance(getattr(self, "video_path", None), str):
            self.frame_cache_dir = [self.video_path]
        else:
            self.frame_cache_dir = list(getattr(self, "video_path", []) or [])

        if getattr(self.ImgManager, "img_num", 0) == 0:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
            return

        # ========== 视频模式 ==========
        if getattr(self, "video_mode", False):
            # —— 这里不立刻提交自增；先算候选索引 —— #
            prev_idx = getattr(self, "current_batch_idx", 0)
            proposed_idx = prev_idx + 1

            # 每次动作对应的帧数
            cpa = int(getattr(self, "count_per_action", 1)) or 1
            batch_start = proposed_idx * cpa
            batch_end   = batch_start + cpa

            # 预热滑窗（可选）
            if hasattr(self, "update_cache"):
                try: self.update_cache(batch_start)
                except Exception as e: print("[update_cache] warn:", e)

            # —— 只检查“目标帧”（batch_start..batch_end-1）；其余帧后台预热 —— #
            missing_info = self._collect_missing_targets(batch_start, batch_end)
            missing = [(cd, i) for (cd, i, _expect_path, _clamped) in missing_info]

            if missing:
                # —— 触发“缺帧冻结”：登记集合 → 后台等待；不提交索引，保持 prev_idx —— #
                need = {(cd, i) for (cd, i) in missing}
                with self._missing_lock:
                    self._missing_by_gen[cur_gen] = need

                self.next_frozen = True

                # 记录是否需要解冻后恢复播放（只在 next/播放路径置位）
                was_playing = bool(getattr(self, 'is_playing', False))
                self._resume_after_unfreeze = getattr(self, "_resume_after_unfreeze", False) or was_playing

                self._resume_play_dir = +1

                # 停止播放的 UI 状态（不改索引）
                if getattr(self, 'is_playing', False):
                    self.is_playing = False
                    try: self.right_arrow_button1.SetLabel("▶")
                    except: pass

                # 提交等待任务（仅目标帧）
                for cache_dir, idx in need:
                    try:
                        self.executor.submit(self._await_and_notify, cache_dir, idx, cur_gen)
                    except Exception as e:
                        print("[submit await] error:", e)

                self.SetStatusText_(["-1","-1","Loading target frame... (Next frozen)","-1"])
                return

            # —— 无缺帧：现在才提交索引并前进显示（顺序不乱） —— #
            self.current_batch_idx = proposed_idx
            self.ImgManager.add()
            self.show_img_init()
            self.show_img()
            self.SetStatusText_(["Next", "-1", "-1", "-1"])
            return

        # ========== 图片模式 ==========
        if getattr(self.ImgManager, "img_count", 0) < int(self.ImgManager.img_num) - 1:
            self.ImgManager.add()
        self.show_img_init()
        self.show_img()
        self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def update_cache(self, batch_start):

        assert hasattr(self, 'executor'), "self.executor 未初始化！"

        # —— 原有参数（保留）——
        self.cache_radius  = int(getattr(self, "cache_num", 1))
        if isinstance(self.real_video_path, str):
            cpa = self.get_count_per_action(type=2)
        else:
            cpa = self.get_count_per_action(type=1)
        cpa = int(cpa) or 1

        self.total_frames  = int(self.ImgManager.img_num)
        current_batch      = batch_start // cpa
        total_batches      = (self.total_frames + cpa - 1) // cpa

        cache_start_batch  = max(0, current_batch - self.cache_radius)
        cache_end_batch    = min(total_batches - 1, current_batch + self.cache_radius)

        # 全局滑窗范围（右开）
        global_cache_start = cache_start_batch * cpa
        global_cache_end   = (cache_end_batch + 1) * cpa

        # —— 保护带（避开当前批次 ± guard_batches）——
        guard_batches = int(getattr(self, "guard_batches", 1))
        protect_start = max(0, batch_start - guard_batches * cpa)
        protect_end   = batch_start + (guard_batches + 1) * cpa   # 右开

        # 统一目录列表（兼容单/多视频）
        frame_cache_dirs = self.frame_cache_dir if isinstance(self.frame_cache_dir, (list, tuple)) else [self.frame_cache_dir]

        # 读 skip -> step（优先 UI → skip_frames → skip）
        try:
            if hasattr(self, "m_textCtrl281") and self.m_textCtrl281:
                _sv = self.m_textCtrl281.GetValue()
                if str(_sv).strip() != "":
                    _skip = int(_sv)
                else:
                    _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
            else:
                _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
        except Exception:
            _skip = 0
        if _skip < 0: _skip = 0
        step = _skip + 1

        # 正则：新/旧命名
        pat_new = re.compile(r'^(\d+(?:\.\d+)?)s_frame_(\d+)\.(?:png|jpg|jpeg)$', re.I)
        pat_old = re.compile(r'^(\d+)\.(?:png|jpg|jpeg)$', re.I)

        # 小工具：优先安全删除
        def _rm(path):
            try:
                if hasattr(self, "_safe_remove"):
                    self._safe_remove(path)
                else:
                    os.remove(path)
            except Exception:
                pass

        for video_idx, cache_dir in enumerate(frame_cache_dirs):
            if not cache_dir or not os.path.isdir(cache_dir):
                continue

            # —— 每视频独立帧数（保留原逻辑）——
            if len(self.ImgManager.img_num_list) == 1:
                real_frame_count = int(self.ImgManager.img_num_list[0])
            else:
                real_frame_count = int(self.ImgManager.img_num_list[video_idx])

            # 夹逼，避免越界
            last_valid_idx = max(0, real_frame_count - 1)

            # 目标窗口宽度（你原本想缓存的宽度 = 全局滑窗右开区间长度）
            window_len = max(1, int(global_cache_end - global_cache_start))

            # 尾部最小保留：self.count_per_action + 1（若取不到就用 cpa）
            try:
                _cpa_attr = int(getattr(self, "count_per_action", cpa))
            except Exception:
                _cpa_attr = cpa
            min_tail_keep = max(1, _cpa_attr + 1)

            # N = 本视频的逻辑总帧
            N = int(real_frame_count)

            if N <= 0:
                cache_start_frame = 0
                cache_end_frame   = 0
            else:
                if global_cache_end >= N:
                    # —— 已经滑到尾部（或越过）：窗口锚到尾部 —— 
                    # 若你希望“至少保留 cpa+1”，用 max(window_len, min_tail_keep)
                    # 若你希望“恰好保留 cpa+1”，把下一行改成：keep_len = min_tail_keep
                    keep_len = max(window_len, min_tail_keep)
                    keep_len = min(keep_len, N)  # 不能超过总帧数
                    cache_end_frame   = N
                    cache_start_frame = max(0, N - keep_len)
                else:
                    # —— 正常区域：保持原窗口宽度 —— 
                    cache_start_frame = max(0, min(int(global_cache_start), max(0, N - window_len)))
                    cache_end_frame   = min(cache_start_frame + window_len, N)

            # 本视频的保护带上界也要按本视频帧数夹逼
            v_protect_end = min(protect_end, real_frame_count)

            # （可选）如果你有 pending 集合就避开它；没有就略过
            v_pending = set()
            if hasattr(self, "_pending_decode"):
                try:
                    v_pending = {idx for (vid, idx) in self._pending_decode if vid == video_idx}
                except Exception:
                    v_pending = set()

            # —— fps（多源兜底）——
            fps = None
            try:
                if hasattr(self, "_cache_fps_map") and cache_dir in self._cache_fps_map:
                    fps = float(self._cache_fps_map[cache_dir])
            except Exception:
                fps = None
            if fps is None:
                try:
                    vlist = list(getattr(self.ImgManager, "video_fps_list", []) or [])
                    if vlist:
                        fps = float(vlist[video_idx] if video_idx < len(vlist) else vlist[0])
                except Exception:
                    fps = None
            if fps is None or not np.isfinite(fps) or fps <= 0:
                fps = 30.0
            fps_int = max(1, int(round(fps)))

            # —— 根据“当前规则”计算期望的新命名 —— #
            def _expected_new_name(i: int) -> str:
                phys = i * step
                t = phys / float(fps)
                sec_str = f"{t:.2f}".rstrip("0").rstrip(".") or "0"
                k = (phys % fps_int) + 1
                return f"{sec_str}s_frame_{k}.png"

            # ===== 删除：滑窗外文件（兼容新/旧命名；能反推 idx 的才参与判断）=====
            try:
                files = os.listdir(cache_dir)
            except Exception:
                files = []

            for name in files:
                # 跳过临时文件
                if name.endswith(".tmp.png") or name.endswith(".tmp.jpg") or name.endswith(".tmp.jpeg"):
                    continue

                fpath = os.path.join(cache_dir, name)
                inferred_idx = None

                m_old = pat_old.match(name)
                if m_old:
                    try:
                        inferred_idx = int(m_old.group(1))
                    except Exception:
                        inferred_idx = None

                else:
                    m_new = pat_new.match(name)
                    if m_new:
                        # 反推 idx（考虑两位小数的四舍五入误差 ±1 帧）
                        try:
                            sec = float(m_new.group(1))
                            kfile = int(m_new.group(2))
                            phys_base = int(round(sec * fps))
                            for phys in (phys_base - 1, phys_base, phys_base + 1):
                                if phys < 0: 
                                    continue
                                if (phys % fps_int) + 1 != kfile:
                                    continue
                                inferred_idx = phys // step
                                break
                        except Exception:
                            inferred_idx = None

                # 无法识别命名 → 跳过（可能是其他附带文件）
                if inferred_idx is None:
                    continue

                # 避开：当前批次±保护带、以及 pending 解码中的索引
                if protect_start <= inferred_idx < v_protect_end:
                    continue
                if inferred_idx in v_pending:
                    continue

                # 只清“滑窗外”或“越界”的帧
                if (inferred_idx < cache_start_frame) or (inferred_idx >= cache_end_frame) or (inferred_idx > last_valid_idx):
                    _rm(fpath)

            # ===== （可选）批次内的“非预期名”再清一遍（更干净）=====
            # 只有当你把 _purge_unexpected_cache_range 放进类里时才会调用
            if hasattr(self, "_purge_unexpected_cache_range"):
                try:
                    # 当前批次范围：batch_start .. batch_start+cpa
                    b_s = batch_start
                    b_e = min(batch_start + cpa, real_frame_count)
                    self._purge_unexpected_cache_range(cache_dir, video_idx, b_s, b_e, keep_legacy_idx_names=False)
                except Exception as e:
                    print(f"[purge] batch inner fail: {e!r}")

            # ===== 补：滑窗内逐“逻辑 idx”检查（按新命名判断是否已存在）=====
            for idx in range(cache_start_frame, cache_end_frame):
                # 仅当新命名不存在时才补（旧命名不算“满足”，以推动迁移）
                new_name = _expected_new_name(idx)
                save_path_new = os.path.join(cache_dir, new_name)
                need_save = True
                try:
                    need_save = not (os.path.exists(save_path_new) and os.path.getsize(save_path_new) > 0)
                except Exception:
                    need_save = True

                if need_save:
                    actual_idx = idx if idx < real_frame_count else last_valid_idx
                    try:
                        # 仍传入“逻辑 idx 路径”（idx.png），_cv_imwrite_atomic 会重命名为新命名
                        legacy_path = os.path.join(cache_dir, f"{idx}.png")
                        self.executor.submit(self._save_frame, actual_idx, video_idx, idx)
                    except Exception:
                        pass

    def _save_frame(self, frame_idx, video_idx, save_idx):
        # 1) 路径（兼容单/多视频、多目录）
        if isinstance(self.real_video_path, str):
            video_path = self.real_video_path
        else:
            video_path = self.real_video_path[video_idx]
        if isinstance(self.frame_cache_dir, str):
            cache_dir = self.frame_cache_dir
        else:
            cache_dir = self.frame_cache_dir[video_idx]

        os.makedirs(cache_dir, exist_ok=True)

        # 2) 打开视频并记录 fps → 提供给 _cv_imwrite_atomic
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if fps <= 0 or not np.isfinite(fps):
            cap.release()
            raise ValueError(f"[save_frame] 获取 fps 失败：{video_path}")
        if not hasattr(self, "_cache_fps_map"): self._cache_fps_map = {}
        self._cache_fps_map[cache_dir] = fps

        # 3) 跳帧策略
        try:
            step = int(self.m_textCtrl281.GetValue() or 0)
        except Exception:
            step = int(getattr(self, "skip_frames", 0) or 0)
        if step < 0:
            step = 0
        step = step + 1
        if step < 1:
            step = 1
        src_idx = int(frame_idx) * step

        # 4) 越界夹紧
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        except Exception:
            total = 0
        if total > 0 and src_idx >= total:
            src_idx = total - 1

        cap.set(cv2.CAP_PROP_POS_FRAMES, src_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return

        # 5) 缩放
        try:
            h, w = frame.shape[:2]
            scale = 256 / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
        except Exception:
            pass

        # 6) 写：按旧接口仍传 {save_idx}.png；_cv_imwrite_atomic 内部会改名
        save_path = os.path.join(cache_dir, f"{save_idx}.png")
        self._cv_imwrite_atomic(save_path, frame)

    def _predecode_exact_batch(self, video_path, cache_dir, idx_start, idx_end, step, gen):
        if gen != self.cache_gen or getattr(self, "_shutdown", False):
            return

        cap = cv2.VideoCapture(video_path)
        try:
            for idx in range(idx_start, idx_end):
                if gen != self.cache_gen or getattr(self, "_shutdown", False):
                    break

                out_png = os.path.join(cache_dir, f"{idx}.png")
                try:
                    if os.path.exists(out_png) and os.path.getsize(out_png) > 0:
                        continue
                except Exception:
                    pass

                phys = int(idx) * int(step)
                cap.set(cv2.CAP_PROP_POS_FRAMES, phys)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                # ✅ 关键：直接把“idx.png”给 _cv_imwrite_atomic
                # 它会根据 idx 与 fps 重命名为 “{sec}s_frame_{k}.png”，并原子落盘
                self._cv_imwrite_atomic(out_png, frame)
        finally:
            try: cap.release()
            except: pass

    def _wait_frame_ready(self, cache_dir, idx, timeout=2.0, poll=0.02, stable_checks=2):
        """等待 cache_dir/idx.png 出现并在文件大小层面稳定 stable_checks 次。"""
        target = os.path.join(cache_dir, f"{idx}.png")
        deadline = time.time() + timeout
        last_size, stable = -1, 0
        while time.time() < deadline:
            if os.path.exists(target):
                try:
                    size = os.path.getsize(target)
                except Exception:
                    size = -1
                if size > 0 and size == last_size:
                    stable += 1
                    if stable >= stable_checks:
                        return True
                else:
                    stable = 0
                    last_size = size
            time.sleep(poll)
        return False
    
    def _await_and_notify(self, cache_dir, idx, expect_gen):
        import os, time
        try:
            # 推断 video_idx（用于 _expected_path_for_idx）
            frame_dirs = list(getattr(self, "frame_cache_dir", []) or [])
            video_idx = frame_dirs.index(cache_dir) if cache_dir in frame_dirs else 0
        except Exception:
            video_idx = 0

        # 解析期望路径 + 夹紧索引
        try:
            expect_path, ready, _clamped = self._expected_path_for_idx(cache_dir, video_idx, idx)
            print(f"[await] expect_path={expect_path} ready={ready} clamped={_clamped} orig_idx={idx} gen={expect_gen}")
        except Exception as e:
            print(f"[await error] map expect path fail: {e}")
            return

        # 若尚未 ready，轮询等待“文件稳定”
        hit = bool(ready)
        if not hit:
            timeout         = getattr(self, "_await_timeout_sec", 8.0)
            poll            = getattr(self, "_await_poll_sec",   0.02)
            stable_checks   = getattr(self, "_await_stable_n",   3)

            t0 = time.time()
            last_size = -1
            stable = 0
            while time.time() - t0 <= timeout:
                # 若世代已经变化，立即放弃
                if expect_gen != getattr(self, "cache_gen", expect_gen):
                    print(f"[await abort] gen changed: expect_gen={expect_gen} cur_gen={getattr(self,'cache_gen',-1)}")
                    return
                try:
                    if os.path.exists(expect_path):
                        sz = os.path.getsize(expect_path)
                        if sz > 0 and sz == last_size:
                            stable += 1
                            if stable >= stable_checks:
                                hit = True
                                break
                        else:
                            stable = 0
                            last_size = sz
                except Exception:
                    pass
                time.sleep(poll)

        if not hit:
            print(f"[await timeout] path={expect_path} gen={expect_gen}")
            return

        # ====== 解冻/续播逻辑 ======
        has_set_mode   = hasattr(self, "_missing_by_gen") and (expect_gen in self._missing_by_gen)
        has_count_mode = hasattr(self, "_wait_counter")    and (expect_gen in self._wait_counter)
        freeze_mode = has_set_mode or has_count_mode

        def _unfreeze_and_apply_intent():
            """解冻：是否续播取决于 _resume_after_unfreeze/当前播放态；同步按钮；刷新一帧。"""
            try:
                # 1) 解冻标志
                try:
                    if hasattr(self, "next_frozen"): self.next_frozen = False
                    if hasattr(self, "is_frozen"):   self.is_frozen   = False
                except Exception:
                    pass

                # 2) 读取“是否解冻后续播”的意图：
                #    优先用 slider_value_change 里设置的 _resume_after_unfreeze；
                #    若没设置，则退回当前 is_playing（保持原态）。
                want_resume = None
                try:
                    if hasattr(self, "_resume_after_unfreeze"):
                        want_resume = bool(self._resume_after_unfreeze)
                except Exception:
                    want_resume = None
                if want_resume is None:
                    want_resume = bool(getattr(self, "is_playing", False))

                # 3) 应用挂起意图（如有）
                try:
                    if hasattr(self, "_on_unfreeze_apply_intent"):
                        self._on_unfreeze_apply_intent()
                except Exception as e:
                    print(f"[unfreeze] _on_unfreeze_apply_intent error: {e}")

                resumed = False

                if want_resume:
                    # === 恢复播放 ===
                    self.is_playing = True

                    # 启动/重启计时器以推进帧
                    try:
                        timer = getattr(self, "_play_timer", None)
                        if timer is None:
                            timer = wx.Timer(self)
                            self._play_timer = timer

                            def _tick(evt):
                                # 非播放态/关闭则停表
                                if not getattr(self, "is_playing", False) or getattr(self, "_shutdown", False):
                                    try: self._play_timer.Stop()
                                    except Exception: pass
                                    return
                                # 推进一帧
                                try:
                                    setattr(self, "_from_timer", True)
                                    if hasattr(self, "next_img"):
                                        if not hasattr(self, "play_direction") or not self.play_direction:
                                            self.play_direction = +1
                                        self.next_img(None)
                                    else:
                                        # 最小刷新
                                        try:
                                            if hasattr(self, "_on_ready_refresh"):
                                                self._on_ready_refresh()
                                            elif hasattr(self, "show_img"):
                                                try:
                                                    self.show_img()
                                                except Exception:
                                                    if hasattr(self, "show_img_init"):
                                                        self.show_img_init(); self.show_img()
                                        except Exception as e:
                                            print(f"[timer] refresh fallback error: {e}")
                                except Exception as e:
                                    print(f"[timer] tick error: {e}")
                                finally:
                                    try: setattr(self, "_from_timer", False)
                                    except Exception: pass

                            try:
                                self.Bind(wx.EVT_TIMER, _tick, timer)
                            except Exception:
                                self.Bind(wx.EVT_TIMER, _tick)

                        # 间隔 = fps→render_set['fps']→30
                        try:
                            fps = getattr(self, "fps", None)
                            if not fps:
                                rs = getattr(self, "render_set", {}) or {}
                                fps = rs.get("fps", 30)
                            fps = float(fps)
                            if not (fps > 0): fps = 30.0
                        except Exception:
                            fps = 30.0
                        interval = max(1, int(round(1000.0 / fps)))

                        try:
                            if self._play_timer.IsRunning(): self._play_timer.Stop()
                        except Exception:
                            pass
                        self._play_timer.Start(interval)
                        resumed = True
                        print(f"[unfreeze] timer start @ {interval} ms")
                    except Exception as e:
                        print(f"[unfreeze] timer fail: {e}")

                    # 播放态按钮 → ⏸
                    try:
                        if hasattr(self, "right_arrow_button1") and self.right_arrow_button1:
                            if wx.IsMainThread():
                                self.right_arrow_button1.SetLabel("⏸")
                                try:
                                    if hasattr(self, "Layout"):  self.Layout()
                                    if hasattr(self, "Refresh"): self.Refresh(False)
                                except Exception:
                                    pass
                            else:
                                wx.CallAfter(self.right_arrow_button1.SetLabel, "⏸")
                                wx.CallAfter(getattr(self, "Layout",  lambda: None))
                                wx.CallAfter(getattr(self, "Refresh", lambda *_: None), False)
                    except Exception as e:
                        print(f"[unfreeze] label(⏸) fail: {e}")

                else:
                    # === 保持暂停 ===
                    self.is_playing = False
                    # 停掉计时器（如果之前在跑）
                    try:
                        if hasattr(self, "_play_timer") and self._play_timer and self._play_timer.IsRunning():
                            self._play_timer.Stop()
                            print("[unfreeze] keep paused: timer stopped")
                    except Exception as e:
                        print(f"[unfreeze] stop timer fail: {e}")
                    # 按钮 → ▶
                    try:
                        if hasattr(self, "right_arrow_button1") and self.right_arrow_button1:
                            if wx.IsMainThread():
                                self.right_arrow_button1.SetLabel("▶")
                                try:
                                    if hasattr(self, "Layout"):  self.Layout()
                                    if hasattr(self, "Refresh"): self.Refresh(False)
                                except Exception:
                                    pass
                            else:
                                wx.CallAfter(self.right_arrow_button1.SetLabel, "▶")
                                wx.CallAfter(getattr(self, "Layout",  lambda: None))
                                wx.CallAfter(getattr(self, "Refresh", lambda *_: None), False)
                    except Exception as e:
                        print(f"[unfreeze] label(▶) fail: {e}")

                # 4) 立刻刷新一帧（无论是否续播，都给用户视觉反馈）
                try:
                    if hasattr(self, "_on_ready_refresh"):
                        self._on_ready_refresh()
                    elif hasattr(self, "show_img"):
                        try:
                            self.show_img()
                        except Exception:
                            if hasattr(self, "show_img_init"):
                                self.show_img_init(); self.show_img()
                except Exception as e:
                    print(f"[unfreeze] refresh error: {e}")

                # 5) 用过即弃，避免下次误用
                try:
                    if hasattr(self, "_resume_after_unfreeze"):
                        delattr(self, "_resume_after_unfreeze")
                except Exception:
                    pass

                print(f"[unfreeze] resumed={resumed}, want_resume={want_resume}")
            except Exception as e:
                print(f"[unfreeze] fatal: {e}")
        # 冻结模式：按集合/计数两种方案清零
        if freeze_mode:
            empty = False
            if has_set_mode:
                # 期望集合键：统一为 (cache_dir, clamped_idx)，必要时兼容 (cache_dir, idx)
                key_clamped = (cache_dir, _clamped)
                key_orig    = (cache_dir, idx)

                try:
                    self._missing_lock.acquire()
                    need = self._missing_by_gen.get(expect_gen)

                    if need is not None:
                        # 兼容不可变集合
                        if not isinstance(need, set):
                            need = set(need)

                        before = len(need)
                        removed = 0

                        if key_clamped in need:
                            need.discard(key_clamped)
                            removed += 1
                        if key_orig != key_clamped and key_orig in need:
                            need.discard(key_orig)
                            removed += 1

                        after = len(need)
                        print(f"[await] removed={removed} before={before} after={after} keys={{clamped:{key_clamped}, orig:{key_orig}}}")

                        if not need:
                            empty = True
                            self._missing_by_gen.pop(expect_gen, None)
                        else:
                            # 写回，防止原先为 frozenset 导致“表面删了实际未变”
                            self._missing_by_gen[expect_gen] = need
                finally:
                    try:
                        self._missing_lock.release()
                    except:
                        pass

            elif has_count_mode:
                try:
                    self._missing_lock.acquire()
                    if expect_gen in self._wait_counter and self._wait_counter[expect_gen] > 0:
                        self._wait_counter[expect_gen] -= 1
                        print(f"[await] counter -> {self._wait_counter[expect_gen]}")
                        if self._wait_counter[expect_gen] == 0:
                            empty = True
                            self._wait_counter.pop(expect_gen, None)
                finally:
                    try:
                        self._missing_lock.release()
                    except:
                        pass

            # 只有在集合/计数清空时才真正“解冻”
            if not empty:
                # 仍然在冻结，先别动
                return

            # 主线程则直接调用，否则 CallAfter
            try:
                import wx
                if wx.IsMainThread():
                    _unfreeze_and_apply_intent()
                else:
                    wx.CallAfter(_unfreeze_and_apply_intent)
            except Exception as e:
                # 没有 wx 或者调用失败，直接兜底刷新
                print(f"[await] wx dispatch fail: {e}")
                try:
                    if hasattr(self, "_on_ready_refresh"):
                        self._on_ready_refresh()
                    else:
                        try:
                            self.show_img()
                        except:
                            self.show_img_init(); self.show_img()
                except Exception as e2:
                    print(f"[await] fallback refresh error: {e2}")
            return

        # ====== 非冻结模式：仅刷新（保持你原逻辑但更稳健）======
        if expect_gen == getattr(self, "cache_gen", 0) and not getattr(self, "_shutdown", False):
            def _refresh_and_maybe_autoplay():
                try:
                    if hasattr(self, "_on_ready_refresh"):
                        self._on_ready_refresh()
                    else:
                        try:
                            self.show_img()
                        except:
                            self.show_img_init(); self.show_img()
                except Exception as e:
                    print("[refresh] error:", e)

            try:
                import wx
                wx.CallAfter(_refresh_and_maybe_autoplay)
            except Exception as e:
                print(f"[await] wx CallAfter fail: {e}")
                _refresh_and_maybe_autoplay()
        else:
            print(f"[await expired] {expect_path} expect_gen={expect_gen} cur_gen={getattr(self,'cache_gen',-1)} _shutdown={getattr(self,'_shutdown',False)}")

    def _ensure_batch_ready_or_queue(self, batch_start, batch_end, gen):
        # 映射缓存目录 & 源视频
        frame_cache_dir = [self.video_path] if isinstance(self.video_path, str) else self.video_path
        real_paths = self.real_video_path if isinstance(self.real_video_path, (list, tuple)) else [self.real_video_path]

        # 步长（skip+1）
        try:
            step = int(self.m_textCtrl281.GetValue() or 0)
        except Exception:
            step = int(getattr(self, "skip_frames", 0) or 0)
        if step < 0:
            step = 0
        step = step + 1

        # 先为每个视频提交“定点拆帧”任务（只拆这个批次需要的帧）
        for vid_i, (cache_dir, src_path) in enumerate(zip(frame_cache_dir, real_paths)):
            try:
                max_frame = int(self.ImgManager.img_num_list[vid_i])
            except Exception:
                max_frame = int(self.ImgManager.img_num_list[0])
            s = batch_start
            e = min(batch_end, max_frame)
            if s < e and src_path:
                try:
                    self.executor.submit(self._predecode_exact_batch, src_path, cache_dir, s, e, step, gen)
                except Exception:
                    pass

        # 检查缺帧（要求存在且 size>0）
        missing = []
        for cache_dir, max_frame in zip(frame_cache_dir, self.ImgManager.img_num_list):
            actual_end = min(batch_end, max_frame)
            for idx in range(batch_start, actual_end):
                p = os.path.join(cache_dir, f"{idx}.png")
                if not (os.path.exists(p) and os.path.getsize(p) > 0):
                    missing.append((cache_dir, idx))

        if missing:
            for cache_dir, idx in missing:
                try:
                    self.executor.submit(self._await_and_notify, cache_dir, idx, gen)
                except Exception:
                    pass
            # 提示后直接返回 False，等后台回调再刷新
            self.SetStatusText_(["-1", "-1", "Decoding target frame(s)…", "-1"])
            return False

        return True

    def _clamp_batch_and_action(self):
        """
        把 current_batch_idx/action_count 限制到“所有视频共同可见帧数”的最后一批，
        并保持 action_count 与批次起始对齐（= batch * count_per_action）。
        """
        try:
            if isinstance(self.real_video_path,str):
                cpa = self.count_per_action(type=2)
            else:
                cpa = self.count_per_action(type=1)
        except Exception:
            cpa = 1

        # 多视频时：共同可见帧数 = 各视频帧数的 min；单视频时直接用 img_num_list[0]
        try:
            max_frames = min(int(n) for n in self.ImgManager.img_num_list) if self.ImgManager.img_num_list else int(self.ImgManager.img_num)
        except Exception:
            max_frames = int(self.ImgManager.img_num)

        # 没有帧就直接 0
        if max_frames <= 0:
            self.current_batch_idx = 0
            self.ImgManager.set_action_count(0)
            return

        max_batch = max(0, (max_frames - 1) // cpa)

        # 现有批次如果越界，回落到最后一批
        cur_batch = int(getattr(self, "current_batch_idx", 0))
        if cur_batch > max_batch:
            cur_batch = max_batch

        # action_count 对齐到批次起点
        target_action = cur_batch * cpa
        self.current_batch_idx = cur_batch
        self.ImgManager.set_action_count(target_action)

    def _setup_img_panel(self):
        if getattr(self, "_img_panel_ready", False):
            return
        pnl = self.img_panel
        pnl.SetBackgroundStyle(wx.BG_STYLE_PAINT)         # 禁擦背景
        pnl.SetDoubleBuffered(True)                       # 双缓冲
        pnl.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None) # 再保险
        self._img_panel_ready = True

    def _safe_remove(self, path, max_retries=6, base_delay=0.05):
        for i in range(max_retries):
            try:
                os.remove(path)
                return True
            except PermissionError:
                time.sleep(base_delay * (2 ** i))   # 50ms→100ms→200ms...
            except FileNotFoundError:
                return True
        # 还删不掉 → 先移到回收区，稍后再清
        trash = os.path.join(os.path.dirname(path), ".trash_gc")
        try:
            os.makedirs(trash, exist_ok=True)
            base = os.path.basename(path)
            dst = os.path.join(trash, base)
            if os.path.exists(dst):
                stem, ext = os.path.splitext(base)
                dst = os.path.join(trash, f"{stem}_{int(time.time()*1000)}{ext}")
            shutil.move(path, dst)
            return False
        except Exception:
            return False

    def _cache_dir_for(self, vid_i):
        real_paths = self.real_video_path if isinstance(self.real_video_path, (list, tuple)) else [self.real_video_path]

        # 统一已有的缓存目录列表
        if hasattr(self, "frame_cache_dir") and self.frame_cache_dir:
            fcd = self.frame_cache_dir if isinstance(self.frame_cache_dir, (list, tuple)) else [self.frame_cache_dir]
        elif getattr(self, "video_path", None):
            fcd = self.video_path if isinstance(self.video_path, (list, tuple)) else [self.video_path]
        else:
            fcd = []

        cache_dir = None
        if fcd and vid_i < len(fcd):
            cache_dir = fcd[vid_i]

        # 缺的话就按 real_video_path 懒建一个
        if not cache_dir:
            p = None
            if real_paths and vid_i < len(real_paths):
                p = real_paths[vid_i]
            if p:
                try:
                    # 约定：num_frames=0 只创建/返回缓存目录，不触发解码
                    cache_dir = self.init_video_frame_cache(p, num_frames=0, max_threads=int(getattr(self, "thread", 4)))
                except Exception:
                    # 兜底：放到同目录下的 frames_cache
                    base = os.path.dirname(str(p))
                    cache_dir = os.path.join(base, "frames_cache")
                    try:
                        os.makedirs(cache_dir, exist_ok=True)
                    except Exception:
                        return None

                # 把新目录回填到 frame_cache_dir / video_path，保持一致性
                existing = []
                if hasattr(self, "frame_cache_dir") and self.frame_cache_dir:
                    existing = self.frame_cache_dir if isinstance(self.frame_cache_dir, (list, tuple)) else [self.frame_cache_dir]
                elif getattr(self, "video_path", None):
                    existing = self.video_path if isinstance(self.video_path, (list, tuple)) else [self.video_path]
                # 扩容到 vid_i
                while len(existing) <= vid_i:
                    existing.append(None)
                existing[vid_i] = cache_dir
                self.frame_cache_dir = existing
                self.video_path = existing if len(existing) > 1 else existing[0]

        # 确保目录存在
        if cache_dir and not os.path.isdir(cache_dir):
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                return None

        return cache_dir

    def _on_ready_refresh(self):
        self._is_waiting = False
        #可选：确保布局已准备
        # try: self.show_img_init()
        # except Exception: pass
        self.show_img()
        try: self.SetStatusText_(["Next", "-1", "-1", "-1"])
        except: pass

    def _purge_unexpected_cache_range(self, cache_dir, video_idx, batch_start, batch_end, keep_legacy_idx_names=False):
        """
        清理 cache_dir 中“当前批次 [batch_start, batch_end) 范围内不在预期集合”的缓存帧。
        预期集合使用当前规则（物理帧命名）：
            step = (skip + 1)，skip 优先取 UI 文本框 -> self.skip_frames -> self.skip
            phys = idx * step
            sec  = round(phys / fps, 2)，去尾 0/点
            k    = (phys % round(fps)) + 1
            name = {sec}s_frame_{k}.png
        - keep_legacy_idx_names=False: 旧命名 {idx}.png 视为过期，删除；
        若 True，则视为预期命名的一种并保留。
        只处理 png/jpg/jpeg，跳过 .tmp.* 临时文件。
        返回：删除的文件数量
        """
        import os, re, math
        import numpy as np

        # 基本检查
        if not cache_dir or not os.path.isdir(cache_dir):
            return 0

        # —— 读取 fps（多源兜底）——
        fps = None
        try:
            if hasattr(self, "_cache_fps_map") and cache_dir in self._cache_fps_map:
                fps = float(self._cache_fps_map[cache_dir])
        except Exception:
            fps = None
        if fps is None:
            try:
                vlist = list(getattr(self.ImgManager, "video_fps_list", []) or [])
                if vlist:
                    if video_idx is not None and 0 <= int(video_idx) < len(vlist):
                        fps = float(vlist[int(video_idx)])
                    elif len(vlist) == 1:
                        fps = float(vlist[0])
            except Exception:
                fps = None
        if fps is None:
            # 再退：从目录名尾部推 idx
            try:
                tail = re.search(r'(\d+)$', os.path.basename(str(cache_dir)))
                if tail:
                    vi = int(tail.group(1))
                    fps = float(self.ImgManager.video_fps_list[vi])
            except Exception:
                pass
        if fps is None or not np.isfinite(fps) or fps <= 0:
            fps = 30.0
        fps_int = max(1, int(round(fps)))

        # —— 读取 skip -> step（优先 UI -> skip_frames -> skip）——
        try:
            if hasattr(self, "m_textCtrl281") and self.m_textCtrl281:
                _sv = self.m_textCtrl281.GetValue()
                if str(_sv).strip() != "":
                    _skip = int(_sv)
                else:
                    _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
            else:
                _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
        except Exception:
            _skip = 0
        if _skip < 0: _skip = 0
        step = _skip + 1

        # —— 批次范围夹取（e 为开区间）——
        try:
            img_num_list = list(getattr(self, "img_num_list", []) or []) or list(getattr(self.ImgManager, "img_num_list", []) or [])
            if img_num_list and video_idx is not None and 0 <= int(video_idx) < len(img_num_list):
                n = int(img_num_list[int(video_idx)] or 0)
            else:
                n = int(getattr(self.ImgManager, "img_num", 0) or 0)
        except Exception:
            n = int(getattr(self, "img_num", 0) or 0)

        s = max(0, int(batch_start))
        e = min(int(batch_end), max(0, n))  # 注意：开区间

        # —— 生成 [s, e) 的“应当存在”的名字集合 —— 
        expected_by_idx = {}
        allowed_names = set()
        for i in range(s, e):
            phys = i * step
            t = phys / float(fps)
            sec_str = f"{t:.2f}".rstrip("0").rstrip(".") or "0"
            k = (phys % fps_int) + 1
            new_name = f"{sec_str}s_frame_{k}.png"
            expected_by_idx[i] = {new_name}
            allowed_names.add(new_name)
            if keep_legacy_idx_names:
                old_name = f"{i}.png"
                expected_by_idx[i].add(old_name)
                allowed_names.add(old_name)

        # —— 遍历目录并删除“属于当前批次但不在 allowed 的文件” —— 
        pat_new = re.compile(r'^(\d+(?:\.\d+)?)s_frame_(\d+)\.(?:png|jpg|jpeg)$', re.I)
        pat_old = re.compile(r'^(\d+)\.(?:png|jpg|jpeg)$', re.I)

        removed = 0
        try:
            for name in os.listdir(cache_dir):
                # 跳过临时
                if name.endswith(".tmp.png") or name.endswith(".tmp.jpg") or name.endswith(".tmp.jpeg"):
                    continue
                full = os.path.join(cache_dir, name)

                # —— 旧命名：{idx}.png —— #
                m_old = pat_old.match(name)
                if m_old:
                    try:
                        idx = int(m_old.group(1))
                    except Exception:
                        continue
                    # 只清理当前批次范围内的旧文件
                    if s <= idx < e:
                        if keep_legacy_idx_names:
                            # 在允许集合则保留
                            if name in expected_by_idx.get(idx, set()):
                                continue
                            # 不是预期（极少数）：删
                            try:
                                os.remove(full); removed += 1
                            except Exception:
                                pass
                        else:
                            # 默认：旧命名都视为过期，删
                            try:
                                os.remove(full); removed += 1
                            except Exception:
                                pass
                    continue

                # —— 新命名：{sec}s_frame_{k}.png —— #
                m_new = pat_new.match(name)
                if m_new:
                    # 反推 idx（考虑两位小数带来的四舍五入误差 ±1 帧）
                    try:
                        sec = float(m_new.group(1))
                        kfile = int(m_new.group(2))
                    except Exception:
                        continue
                    phys_base = int(round(sec * fps))
                    matched = False
                    for phys in (phys_base - 1, phys_base, phys_base + 1):
                        if phys < 0: 
                            continue
                        if (phys % fps_int) + 1 != kfile:
                            continue
                        idx = phys // step
                        if s <= idx < e:
                            matched = True
                            # 在当前批次内但不是期望名字 → 删除
                            if name not in expected_by_idx.get(idx, set()):
                                try:
                                    os.remove(full); removed += 1
                                except Exception:
                                    pass
                            break
                    # 不匹配当前批次：认为属于其它批次，跳过
                    continue

                # 其它命名：跳过
                continue
        except Exception as e1:
            print(f"[purge] list fail: {e1!r}")

        print(f"[purge] cache={os.path.basename(cache_dir)} range=[{s},{e}) fps={fps:.3f} step={step} "
            f"legacy={'keep' if keep_legacy_idx_names else 'drop'} removed={removed}")
        return removed

    def _expected_path_for_idx(self, cache_dir, video_idx, idx):        
        # ---------- 1) 取该视频的逻辑长度 n ----------
        n = 0
        # 优先从实例拿（外层通常已算好）
        try:
            lst = list(getattr(self, "img_num_list", []) or [])
            if not lst:
                lst = list(getattr(self.ImgManager, "img_num_list", []) or [])
            if lst:
                if video_idx is not None and 0 <= int(video_idx) < len(lst):
                    n = int(lst[int(video_idx)] or 0)
                else:
                    # video_idx 异常时，用当前最长的作为兜底
                    n = int(max(lst))
        except Exception:
            n = int(getattr(self.ImgManager, "img_num", 0) or 0)

        if n < 0: n = 0
        max_idx = max(0, n - 1)

        # 原始 idx
        try:
            i_raw = int(idx)
        except Exception:
            i_raw = 0
        if i_raw < 0: i_raw = 0

        # 严格夹取
        i = min(i_raw, max_idx)
        if i != i_raw:
            print(f"[expect] clamp idx {i_raw} -> {i} (len={n})")

        # ---------- 2) fps ----------
        fps = None
        try:
            if not hasattr(self, "_cache_fps_map"):
                self._cache_fps_map = {}
            if cache_dir in self._cache_fps_map:
                fps = float(self._cache_fps_map[cache_dir])
        except Exception:
            fps = None

        if fps is None:
            try:
                vlist = list(getattr(self.ImgManager, "video_fps_list", []) or [])
                if video_idx is not None and 0 <= int(video_idx) < len(vlist):
                    fps = float(vlist[int(video_idx)])
                elif len(vlist) == 1:
                    fps = float(vlist[0])
            except Exception:
                fps = None

        if fps is None:
            try:
                tail = re.search(r'(\d+)$', os.path.basename(str(cache_dir) if cache_dir else ""))
                if tail:
                    vi = int(tail.group(1))
                    fps = float(self.ImgManager.video_fps_list[vi])
            except Exception:
                pass

        if fps is None or not np.isfinite(fps) or fps <= 0:
            fps = 30.0  # 最后兜底（不建议走到这里）

        fps_int = max(1, int(round(fps)))

        # ---------- 3) 读取 skip → step（与写盘一致：优先 UI，再到属性） ----------
        try:
            if hasattr(self, "m_textCtrl281") and self.m_textCtrl281:
                _skip_val = self.m_textCtrl281.GetValue()
                if str(_skip_val).strip() != "":
                    _skip = int(_skip_val)
                else:
                    _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
            else:
                _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
        except Exception:
            _skip = 0
        if _skip < 0: _skip = 0
        step = _skip + 1

        # ---------- 4) 新旧命名候选 ----------
        phys_index = i * step
        t = phys_index / float(fps)
        sec_str = f"{t:.2f}".rstrip("0").rstrip(".") or "0"
        k = (phys_index % fps_int) + 1

        new_name = f"{sec_str}s_frame_{k}.png"
        old_name = f"{i}.png"

        new_path = os.path.join(cache_dir, new_name) if cache_dir else new_name
        old_path = os.path.join(cache_dir, old_name) if cache_dir else old_name

        # ---------- 5) 就绪性检测 ----------
        ready_new = False
        try:
            ready_new = os.path.exists(new_path) and os.path.getsize(new_path) > 0
        except Exception:
            ready_new = False

        if ready_new:
            return new_path, True, i

        # 兼容旧名
        try:
            ready_old = os.path.exists(old_path) and os.path.getsize(old_path) > 0
        except Exception:
            ready_old = False

        if ready_old:
            return old_path, True, i

        # 两个都没有
        return new_path, False, i
    
    def _collect_missing_targets(self, batch_start: int, batch_end: int):
        missing = []
        frame_cache_dirs = list(getattr(self, "frame_cache_dir", []) or [])
        for v_idx, cache_dir in enumerate(frame_cache_dirs):
            if not cache_dir:
                continue
            for idx in range(batch_start, batch_end):
                try:
                    expect_path, ready, clamped = self._expected_path_for_idx(cache_dir, v_idx, idx)
                    if not ready:
                        missing.append((cache_dir, idx, expect_path, clamped))
                except Exception as e:
                    print("[_collect_missing_targets] warn:", e)
        return missing

    # def _cv_imwrite_atomic(self, path, img, png_level=1, max_retries=3):
    #     dir_, base = os.path.split(path)
    #     stem, ext = os.path.splitext(base)
    #     ext = (ext or ".png").lower()

    #     # 1) 帧号（从 .../<digits>.png 提取，视为 0-based）
    #     m = re.search(r'(\d+)$', stem)
    #     if not m:
    #         raise ValueError(f"[imwrite_atomic] 无法从文件名解析帧号：path={path}")
    #     frame_index = int(m.group(1))
    #     if frame_index < 0:
    #         raise ValueError(f"[imwrite_atomic] 非法帧号：{frame_index}")

    #     # 2) fps：从 _cache_fps_map 或其它途径获取
    #     fps = None
    #     cache_dir_key = dir_
    #     if not hasattr(self, "_cache_fps_map"):
    #         self._cache_fps_map = {}
    #     if cache_dir_key in self._cache_fps_map:
    #         try:
    #             fps = float(self._cache_fps_map[cache_dir_key])
    #         except Exception:
    #             fps = None

    #     if fps is None:
    #         try:
    #             vlist = list(getattr(self.ImgManager, "video_fps_list", []) or [])
    #             if len(vlist) == 1:
    #                 fps = float(vlist[0])
    #         except Exception:
    #             fps = None

    #     if fps is None:
    #         try:
    #             vid_idx = getattr(self, "current_video_idx", None)
    #             if vid_idx is not None:
    #                 fps = float(self.ImgManager.video_fps_list[int(vid_idx)])
    #         except Exception:
    #             fps = None

    #     if fps is None:
    #         try:
    #             mdir = re.search(r'(\d+)$', os.path.basename(dir_))
    #             if mdir:
    #                 fps = float(self.ImgManager.video_fps_list[int(mdir.group(1))])
    #         except Exception:
    #             fps = None

    #     if fps is None or not np.isfinite(fps) or fps <= 0:
    #         raise ValueError(
    #             f"[imwrite_atomic] 无法获取有效 fps：dir={dir_} base={base} "
    #             f"current_video_idx={getattr(self,'current_video_idx',None)} "
    #             f"video_fps_list={getattr(self.ImgManager,'video_fps_list',None)}"
    #         )

    #     # === 关键：把 skip 纳入命名，用“物理帧号” ===
    #     try:
    #         if hasattr(self, "m_textCtrl281") and self.m_textCtrl281:
    #             _skip_val = self.m_textCtrl281.GetValue()
    #             _skip = int(_skip_val) if str(_skip_val).strip() != "" else int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
    #         else:
    #             _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0)
    #     except Exception:
    #         _skip = 0
    #     if _skip < 0:
    #         _skip = 0
    #     _step = _skip + 1

    #     phys_index = frame_index * _step

    #     # 3) 生成统一文件名（按物理帧）
    #     fps_int = int(round(fps))
    #     if fps_int <= 0:
    #         raise ValueError(f"[imwrite_atomic] fps 非法：{fps}")

    #     t = phys_index / float(fps)
    #     sec_str = f"{t:.2f}".rstrip('0').rstrip('.') or "0"
    #     k = (phys_index % fps_int) + 1
    #     new_basename = f"{sec_str}s_frame_{k}{ext}"
    #     new_path = os.path.join(dir_, new_basename)

    #     # 4) 基本校验/归一化
    #     if img is None or getattr(img, "size", 0) == 0:
    #         raise ValueError(f"[imwrite_atomic] 空图像：{path}")

    #     if getattr(img, "dtype", None) is not np.uint8:
    #         try:
    #             img = np.clip(img, 0, 255).astype(np.uint8)
    #         except Exception as e:
    #             raise ValueError(f"[imwrite_atomic] dtype 归一化失败：{e!r}")

    #     # 4.1) 通道归一（灰度→BGR，RGBA→BGR；避免后续读法不一致）
    #     if img.ndim == 2:
    #         img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    #     elif img.ndim == 3:
    #         c = img.shape[2]
    #         if c == 4:
    #             img = img[:, :, :3]
    #         elif c != 3:
    #             try:
    #                 img = img[:, :, :3]
    #             except Exception:
    #                 raise ValueError(f"[imwrite_atomic] 非预期通道数: {img.shape}")
    #     else:
    #         raise ValueError(f"[imwrite_atomic] 非预期维度: {img.ndim}")

    #     # 4.2) 尺寸规范化：最长边=256，等比缩放，无黑边
    #     H, W = img.shape[:2]
    #     if H <= 0 or W <= 0:
    #         raise ValueError(f"[imwrite_atomic] 非法尺寸：{W}x{H}")

    #     TARGET_MAX = 256
    #     scale = TARGET_MAX / float(max(W, H))
    #     newW = max(1, int(round(W * scale)))
    #     newH = max(1, int(round(H * scale)))
    #     if (newW, newH) != (W, H):
    #         interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    #         img = cv2.resize(img, (newW, newH), interpolation=interp)

    #     # 5) 编码参数
    #     params = []
    #     if ext == ".png":
    #         params = [cv2.IMWRITE_PNG_COMPRESSION, int(png_level)]
    #     elif ext in (".jpg", ".jpeg"):
    #         params = [cv2.IMWRITE_JPEG_QUALITY, 95]

    #     # 6) 原子写（写临时文件→替换），并带退避重试
    #     # 确保目标目录存在（稳妥起见）
    #     try:
    #         os.makedirs(os.path.dirname(os.path.abspath(new_path)), exist_ok=True)
    #     except Exception:
    #         pass

    #     root_no_ext, _ = os.path.splitext(new_path)
    #     tmp = f"{root_no_ext}.tmp{ext}"

    #     ok = False
    #     try:
    #         ok = cv2.imwrite(tmp, img, params)
    #     except Exception:
    #         ok = False

    #     if not ok:
    #         try:
    #             ok, buf = cv2.imencode(ext, img, params)
    #             if ok:
    #                 with open(tmp, "wb") as f:
    #                     f.write(buf.tobytes())
    #         except Exception:
    #             ok = False

    #     if not ok:
    #         try:
    #             if os.path.exists(tmp):
    #                 os.remove(tmp)
    #         except Exception:
    #             pass
    #         raise RuntimeError(f"[imwrite_atomic] 写入临时文件失败：{tmp}")

    #     for i in range(max_retries + 1):
    #         try:
    #             os.replace(tmp, new_path)
    #             return True
    #         except PermissionError:
    #             time.sleep(0.05 * (2 ** i))
    #         except Exception:
    #             break

    #     try:
    #         if os.path.exists(tmp):
    #             os.remove(tmp)
    #     except Exception:
    #         pass
    #     raise RuntimeError(f"[imwrite_atomic] 原子替换失败：{new_path}")

    def _cv_imwrite_atomic(self, path, img, png_level=1, max_retries=3):
        # ---------- 解析入参/基本信息 ----------
        dir_, base = os.path.split(path)
        stem, ext = os.path.splitext(base)
        ext = (ext or ".png").lower()

        # 帧号（从 .../<digits>.png 提取，视为 0-based）
        m = re.search(r'(\d+)$', stem)
        if not m:
            print(f"[imwrite] ERR no_frame_index | path={path}")
            raise ValueError(f"[imwrite_atomic] 无法从文件名解析帧号：path={path}")
        frame_index = int(m.group(1))
        if frame_index < 0:
            print(f"[imwrite] ERR neg_frame_index | frame_index={frame_index} path={path}")
            raise ValueError(f"[imwrite_atomic] 非法帧号：{frame_index}")

        # ---------- 解析 fps（多源回退） ----------
        fps_src = "none"
        fps = None
        cache_dir_key = dir_
        if not hasattr(self, "_cache_fps_map"):
            self._cache_fps_map = {}

        if fps is None and cache_dir_key in self._cache_fps_map:
            try:
                fps = float(self._cache_fps_map[cache_dir_key])
                fps_src = "cache_map"
            except Exception:
                fps = None

        if fps is None:
            try:
                vlist = list(getattr(self.ImgManager, "video_fps_list", []) or [])
                if len(vlist) == 1:
                    fps = float(vlist[0]); fps_src = "fps_list_single"
            except Exception:
                fps = None

        if fps is None:
            try:
                vid_idx = getattr(self, "current_video_idx", None)
                if vid_idx is not None:
                    fps = float(self.ImgManager.video_fps_list[int(vid_idx)])
                    fps_src = f"fps_list_idx[{int(vid_idx)}]"
            except Exception:
                fps = None

        if fps is None:
            try:
                mdir = re.search(r'(\d+)$', os.path.basename(dir_))
                if mdir:
                    fps = float(self.ImgManager.video_fps_list[int(mdir.group(1))])
                    fps_src = f"fps_list_dir_tail[{mdir.group(1)}]"
            except Exception:
                fps = None

        if fps is None or not np.isfinite(fps) or fps <= 0:
            print(f"[imwrite] ERR fps_invalid | dir={dir_} base={base} src={fps_src} "
                f"current_video_idx={getattr(self,'current_video_idx',None)} "
                f"video_fps_list={getattr(self.ImgManager,'video_fps_list',None)}")
            raise ValueError("无法获取有效 fps")

        fps_int = int(round(fps))
        if fps_int <= 0:
            print(f"[imwrite] ERR fps_int_le0 | fps={fps}")
            raise ValueError(f"[imwrite_atomic] fps 非法：{fps}")

        # ---------- 解析 skip（优先 UI，其次属性） ----------
        skip_src = "none"
        try:
            if hasattr(self, "m_textCtrl281") and self.m_textCtrl281:
                _skip_val = self.m_textCtrl281.GetValue()
                if str(_skip_val).strip() != "":
                    _skip = int(_skip_val); skip_src = "ui_text"
                else:
                    _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0); skip_src = "attr_fallback"
            else:
                _skip = int(getattr(self, "skip_frames", getattr(self, "skip", 0)) or 0); skip_src = "attr"
        except Exception:
            _skip = 0; skip_src = "except->0"
        if _skip < 0: _skip = 0
        _step = _skip + 1

        # ---------- 物理索引/命名 ----------
        phys_index = frame_index * _step
        t = phys_index / float(fps)
        sec_str = f"{t:.2f}".rstrip('0').rstrip('.') or "0"
        k = (phys_index % fps_int) + 1
        new_basename = f"{sec_str}s_frame_{k}{ext}"
        new_path = os.path.join(dir_, new_basename)

        print(f"[imwrite] idx | frame_index={frame_index} phys_index={phys_index} "
            f"fps={fps:.6f} fps_int={fps_int} skip={_skip}({skip_src}) step={_step} "
            f"t={t:.6f}s name={new_basename}")

        if img is None or getattr(img, "size", 0) == 0:
            print(f"[imwrite] ERR empty_img | stem={stem} new={new_basename}")
            raise ValueError(f"[imwrite_atomic] 空图像：{path}")

        # ---------- 通道/类型归一 ----------
        orig_dtype = getattr(img, "dtype", None)
        if orig_dtype is not np.uint8:
            try:
                img = np.clip(img, 0, 255).astype(np.uint8)
            except Exception as e:
                print(f"[imwrite] ERR dtype_norm | dtype={orig_dtype} err={e!r}")
                raise ValueError(f"dtype 归一化失败：{e!r}")

        orig_shape = getattr(img, "shape", None)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            ch_info = "GRAY->BGR"
        elif img.ndim == 3:
            c = img.shape[2]
            if c == 4:
                img = img[:, :, :3]; ch_info = "RGBA->BGR"
            elif c == 3:
                ch_info = "BGR"
            else:
                try:
                    img = img[:, :, :3]; ch_info = f"{c}ch->BGR(clip)"
                except Exception:
                    print(f"[imwrite] ERR channels | shape={img.shape}")
                    raise ValueError(f"非预期通道数: {img.shape}")
        else:
            print(f"[imwrite] ERR ndim | ndim={img.ndim}")
            raise ValueError(f"非预期维度: {img.ndim}")

        # ---------- 尺寸规范：最长边缩放到 256（无黑边） ----------
        H, W = img.shape[:2]
        if H <= 0 or W <= 0:
            print(f"[imwrite] ERR size_invalid | W={W} H={H}")
            raise ValueError(f"非法尺寸：{W}x{H}")

        TARGET_MAX = 256
        scale = TARGET_MAX / float(max(W, H))
        newW = max(1, int(round(W * scale)))
        newH = max(1, int(round(H * scale)))

        do_resize = (newW, newH) != (W, H)
        if do_resize:
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            img = cv2.resize(img, (newW, newH), interpolation=interp)

        print(f"[imwrite] size | orig={orig_shape} dtype={orig_dtype} ch={ch_info} "
            f"-> scaled=({newW}x{newH}) scale={scale:.6f} do_resize={do_resize}")

        # ---------- 编码参数 ----------
        if ext == ".png":
            params = [cv2.IMWRITE_PNG_COMPRESSION, int(png_level)]
        elif ext in (".jpg", ".jpeg"):
            params = [cv2.IMWRITE_JPEG_QUALITY, 95]
        else:
            params = []

        # ---------- 原子写 ----------
        try:
            os.makedirs(os.path.dirname(os.path.abspath(new_path)), exist_ok=True)
        except Exception:
            pass

        root_no_ext, _ = os.path.splitext(new_path)
        tmp = f"{root_no_ext}.tmp{ext}"

        ok = False
        try:
            ok = cv2.imwrite(tmp, img, params)
            print(f"[imwrite] tmp_write | ok={ok} tmp={tmp}")
        except Exception as e:
            print(f"[imwrite] EXC tmp_imwrite | err={e!r}")
            ok = False

        if not ok:
            try:
                ok, buf = cv2.imencode(ext, img, params)
                if ok:
                    with open(tmp, "wb") as f:
                        f.write(buf.tobytes())
                print(f"[imwrite] tmp_encode_fallback | ok={ok} tmp={tmp}")
            except Exception as e:
                print(f"[imwrite] EXC tmp_encode | err={e!r}")
                ok = False

        if not ok or (not os.path.exists(tmp)) or (os.path.getsize(tmp) == 0):
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            print(f"[imwrite] ERR tmp_write_fail | tmp={tmp}")
            raise RuntimeError(f"[imwrite_atomic] 写入临时文件失败：{tmp}")

        for i in range(max_retries + 1):
            try:
                os.replace(tmp, new_path)
                print(f"[imwrite] done | path={new_path}")
                return True
            except PermissionError:
                delay = 0.05 * (2 ** i)
                print(f"[imwrite] replace_retry | i={i} sleep={delay:.3f}s path={new_path}")
                time.sleep(delay)
            except Exception as e:
                print(f"[imwrite] EXC replace | i={i} err={e!r} path={new_path}")
                break

        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        print(f"[imwrite] ERR replace_fail | path={new_path}")
        raise RuntimeError(f"[imwrite_atomic] 原子替换失败：{new_path}")

TEMP_DIR = "video_frames"  # 你临时生成内容的目录路径（可以修改）

def cleanup_temp_dir():
    if os.path.exists(TEMP_DIR):
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception as e:
            pass

# 注册退出时自动清理
atexit.register(cleanup_temp_dir)

# 注册中断信号（如 Ctrl+C / kill）
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup_temp_dir(), exit(0)))
signal.signal(signal.SIGTERM, lambda sig, frame: (cleanup_temp_dir(), exit(0)))
