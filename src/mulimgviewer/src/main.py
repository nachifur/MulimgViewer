"""Application GUI composition, image browsing and shared viewer event coordination."""
import platform
import threading
from pathlib import Path
import os, time, math, sys
import weakref
import numpy as np
import wx
from PIL import Image
from ..gui.main_gui import MulimgViewerGui
from .. import __version__ as VERSION
from .about import About
from .index_table import IndexTable
from .index_catalog import IndexCatalog
from .display_modes import auto_title_fields
from .display_modes import loaded_input_mode
from .custom_func.main import get_available_algorithms
from .custom_func.runtime import capture_algorithms, compiled_source, AlgorithmSession
from .utils import MyTestEvent, get_resource_path
from .utils_img import ImgManager
from .resource_policy import resource_budget, positive_cache_integer
from .image_pipeline import ImagePipeline
from .memory_reclaim import MemoryReclaimer
from .resource_monitor import ResourceMonitor
from .thread_optimizer import AdaptiveThreadAllocator, available_memory_bytes
import shutil
import copy
from PIL import ImageFont


# Public class imports remain available for existing callers of src.main.
from .viewer_state import SharedConfig
from .video_manager import VideoManager, PerformanceMonitor
from .video_playback import VideoPlaybackMixin
from .status_bar import StatusBarMixin
from .navigation import NavigationMixin
from .configuration_controller import ConfigurationMixin


try:
    import winreg
except ImportError:
    winreg = None


class MulimgViewer(NavigationMixin, StatusBarMixin, VideoPlaybackMixin, ConfigurationMixin, MulimgViewerGui):
    """Compose generated widgets with playback/configuration event handlers.

    Mixins precede the generated GUI so Bind calls resolve concrete handlers,
    rather than the generated no-op event stubs. Image navigation and common
    resource settings remain here; VideoManager owns background video work.
    """

    def __init__(self, parent, UpdateUI, get_type, default_path=None):
        self.shared_config = SharedConfig()
        super().__init__(parent)
        try:
            img_sizer = self.scrolledWindow_img.GetSizer()
            if isinstance(img_sizer, wx.FlexGridSizer):
                pass
        except Exception:
            pass
        self.create_ImgManager()
        self.video_manager = VideoManager(owner=self,shared_config=self.shared_config,ImgManager=self.ImgManager)
        self.image_stitch_executor = None  # Image-mode stitch thread pool
        self.image_pipeline = ImagePipeline(self.video_manager.disk_cache_dir,
                                            self._image_frame_ready, wx.CallAfter)
        self.memory_reclaimer = MemoryReclaimer()
        owner_ref = weakref.ref(self)
        def metrics_ready():
            def update():
                owner = owner_ref()
                if owner is not None and not getattr(owner, '_is_closing', False):
                    owner._refresh_power_tooltip()
            wx.CallAfter(update)
        self.resource_monitor = ResourceMonitor(notify=metrics_ready)
        self._image_stitch_lock = threading.Lock()  # Lock for image stitching state
        self.shift_pressed=False
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self._initialize_configuration_paths()
        pos = self.GetPosition()
        size = self.GetSize()
        self._normal_window_pos = (pos[0], pos[1])
        self._normal_window_size = (size[0], size[1])
        self._is_closing = False
        self._parallel_switch_dirty = False

        self._initialize_hotkeys()
        # self.img_Sizer = self.scrolledWindow_img.GetSizer()
        self.Bind(wx.EVT_CLOSE, self.close)
        # self.Bind(wx.EVT_PAINT, self.OnPaint)

        # parameter
        self.out_path_str = ""
        self.img_name = []
        self.selected_img_id = 0
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
        self._init_status_bar()
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
        self._from_timer = False     # Distinguish timer-triggered actions from user clicks

        # Draw color to box
        self.colourPicker_draw.Bind(
            wx.EVT_COLOURPICKER_CHANGED, self.draw_color_change)

        # Check the software version
        self.myEVT_MY_TEST = wx.NewEventType()
        EVT_MY_TEST = wx.PyEventBinder(self.myEVT_MY_TEST, 1)
        self.Bind(EVT_MY_TEST, self.EVT_MY_TEST_OnHandle)
        self.version = VERSION
        self.check_version()

        self._bind_legacy_control_aliases()
        self.refresh_algorithm_list()
        self._capture_configuration_defaults()

        # open default path
        if default_path:
            try:
                self.ImgManager.init(default_path, type=2)  # one_dir_mul_img
                self.show_img_init()
                self.ImgManager.set_action_count(0)
                self.show_img()
            except:
                pass
        self.load_configuration(None, config_name="session_config.json")
        self.Bind(wx.EVT_CONTEXT_MENU, self.on_right_click)
        self.custom_algorithms = []
        self._bind_compat_events()
        self._bind_settings_wheel_guard()

        def _bind_accel_guard_recursive(parent):
            for child in parent.GetChildren():
                if isinstance(child, (wx.TextCtrl, wx.SpinCtrl, wx.SpinCtrlDouble)):
                    child.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                    child.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
                _bind_accel_guard_recursive(child)
        _bind_accel_guard_recursive(self)
        self._restore_window_state()

    def _bind_legacy_control_aliases(self):
        # Keep older handwritten logic working after GUI control renames.
        alias_map = {
            "title_show_rename": "m_checkBox31",
            "title_rename_text": "m_textCtrl16",
            "custom_algorithm_input": "addfunc",
            "m_textCtrl28": "interval",
            "m_textCtrl30": "cache_frames",
            "m_textCtrl281": "row_col13",
            "right_arrow_button1": "play",
        }
        for legacy_name, current_name in alias_map.items():
            if not hasattr(self, legacy_name) and hasattr(self, current_name):
                setattr(self, legacy_name, getattr(self, current_name))

    def _bind_compat_events(self):
        self.power_mode.Bind(wx.EVT_ENTER_WINDOW, self._show_thread_pipeline_status)
        self.power_mode.Bind(wx.EVT_CHOICE, self.on_power_mode_changed)
        self.interval.Bind(wx.EVT_TEXT, self._on_interval_text_edited)
        if hasattr(self, "title_exif"):
            self.title_exif.Bind(wx.EVT_CHECKBOX, self.on_title_exif_changed)

        if hasattr(self, "title_rename_text"):
            self.title_rename_text.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
            self.title_rename_text.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
        if hasattr(self, "title_show_rename"):
            self.title_show_rename.Bind(wx.EVT_CHECKBOX, self.title_rename_fc)

        if hasattr(self, "show_all_func"):
            self.show_all_func.Bind(wx.EVT_CHECKBOX, self.on_show_all_func_changed)
        if hasattr(self, "show_custom_func"):
            self.show_custom_func.Bind(wx.EVT_CHECKBOX, self.on_show_custom_func_changed)

        if hasattr(self, "custom_algorithm_input"):
            self.custom_algorithm_input.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
            self.custom_algorithm_input.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
            self.custom_algorithm_input.Bind(wx.EVT_CHAR_HOOK, self._handle_custom_algorithm_key)
        if hasattr(self, "delfunc"):
            self.delfunc.Bind(wx.EVT_BUTTON, self.remove_custom_algorithm)
        self.customfunc_choice.Bind(wx.EVT_CHOICE, self._custom_settings_changed)
        if hasattr(self, "play"):
            try:
                self.play.Unbind(wx.EVT_BUTTON)
            except Exception:
                pass
            self.play.Bind(wx.EVT_BUTTON, self.toggle_play)
        for field_name in ("slider_value", "show_all_func_layout"):
            if hasattr(self, field_name):
                field = getattr(self, field_name)
                field.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)

        video_field_handlers = [
            ("interval", self.on_interval_changed),
            ("cache_frames", self.on_cache_num_change),
            ("cache_multiplier", self.on_cache_num_change),
            ("m_textCtrl281", self.on_skip_changed),
        ]
        for field_name, handler in video_field_handlers:
            if hasattr(self, field_name):
                field = getattr(self, field_name)
                field.Bind(wx.EVT_SET_FOCUS, self.disable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, self.enable_accel)
                field.Bind(wx.EVT_KILL_FOCUS, handler)
                # ★ 回车直接提交: 单行 TextCtrl 默认不处理回车, 必须显式加上
                #   TE_PROCESS_ENTER, 否则 EVT_TEXT_ENTER 永远不触发。
                #   有了它, 输入框里按回车就等于"改好了", 不用再点别处失焦。
                try:
                    field.SetStyle(field.GetStyle() | wx.TE_PROCESS_ENTER)
                    field.Bind(wx.EVT_TEXT_ENTER, self.on_video_field_enter)
                except Exception:
                    pass

    def _handle_custom_algorithm_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.add_custom_algorithm(event)
            return
        event.Skip()

    def _rebuild_threads(self, n):
        # Legacy refresh/configuration entry: honor power_mode's shared budget.
        self.video_manager.update_thread_count()

    # ========== 视频设置数值框的提交 ==========
    # ★ 这些框以前只靠 EVT_KILL_FOCUS 才写回 shared_config, 而 refresh() 是直接读
    #   shared_config 的。于是"改了生不生效"完全取决于一个看不见的事件:
    #     - 从菜单/快捷键刷新时输入框不会失焦, 改动被静默丢弃;
    #     - 输入非法内容时 int() 会在事件处理里抛异常, 值悄悄保持旧的, 而输入框
    #       一直显示着你打的字 —— 看上去就是"改了没反应";
    #     - 生效了也没有任何回显, 光标 "|" 一直留在框里, 分不清到底提交没有。
    #   现在统一走 _commit_video_settings(): 读框 -> 校验 -> 归一化 -> 写回框里,
    #   保证输入框显示的永远是当前真正生效的值, refresh() 开头也会主动提交一次。
    def _commit_video_settings(self):
        """把视频设置里的数值输入框提交到 shared_config, 并把框里的文本归一化。"""

        self.shared_config.parallel_to_sequential = bool(self.parallel_to_sequential.GetValue())
        self.shared_config.parallel_sequential = bool(self.parallel_sequential.GetValue())

        def _read_number(field, default, minimum, integer=True):
            try:
                raw = str(field.GetValue()).strip()
            except Exception:
                raw = ""
            value = default
            if raw:
                try:
                    value = int(float(raw)) if integer else float(raw)
                except (TypeError, ValueError, OverflowError):
                    value = default
            try:
                if not math.isfinite(value):
                    value = default
                value = max(minimum, value)
            except (TypeError, ValueError):
                value = default
            return value

        # ---- 播放间隔 ----
        interval = _read_number(self.interval, 1.0,
                                0.001 if self.shared_config.video_mode else 0.05, integer=False)
        if self.shared_config.video_mode:
            interval = math.ceil(interval * 1000 - 1e-9) / 1000.0
            if (getattr(self, '_interval_user_edited', False)
                    or abs(float(self.shared_config.interval) - interval) > 1e-9):
                self.shared_config.manual_interval = interval
            self._interval_user_edited = False
            manual = self.shared_config.manual_interval
            if manual is not None:
                interval = max(manual, self.shared_config.interval_recommend or 0.0)
        if abs(float(self.shared_config.interval) - interval) > 1e-9:
            self.shared_config.interval = interval
            # 播放中改间隔, 立即重启 timer 让新值生效
            if getattr(self.shared_config, "is_playing", False):
                try:
                    if self.shared_config.video_mode:
                        if not getattr(self, '_play_timer_suspended', False):
                            self._schedule_next_video_tick()
                    else:
                        self.play_timer.Start(max(1, math.ceil(interval * 1000)), oneShot=False)
                except Exception:
                    pass

        # Global performance policy applies to images and videos alike.
        self._apply_resource_policy()

        # ---- Cached Frames (缓存帧数) ----
        invalid_cache_fields = set()
        errors = []
        for field, attribute, label in ((self.cache_frames, 'cache_num', 'Cache frames'),
                                         (self.cache_multiplier, 'cache_multiplier', 'Cache multiplier')):
            if not hasattr(field, '_cache_input_background'):
                field._cache_input_background = field.GetBackgroundColour()
                tip = field.GetToolTip()
                field._cache_input_tip = tip.GetTip() if tip else 'Integer >= 1'
            try:
                value = positive_cache_integer(field.GetValue())
            except ValueError:
                invalid_cache_fields.add(id(field))
                effective = getattr(self.shared_config, attribute)
                message = f'{label}: enter an integer >= 1; current effective value: {effective}'
                errors.append(message)
                field.SetBackgroundColour(wx.Colour(255, 225, 225))
                field.SetToolTip(message)
            else:
                setattr(self.shared_config, attribute, value)
                field.SetBackgroundColour(field._cache_input_background)
                field.SetToolTip(field._cache_input_tip)
            field.Refresh()
        self._performance_input_errors = errors
        if errors:
            self.SetStatusText_(['-1', '-1', '***Invalid parameter: ' + '; '.join(errors) + '***', '-1'])

        # ---- Skip Frame (跳过帧数) ----
        skip = _read_number(self.m_textCtrl281, 0, 0)
        self.shared_config.skip_frames = skip
        self.ImgManager.skip = skip

        # 归一化: 输入框里显示的必须是当前真正生效的值
        for field, value in ((self.interval, self.shared_config.interval),
                              (self.cache_frames, self.shared_config.cache_num),
                              (self.cache_multiplier, self.shared_config.cache_multiplier),
                              (self.m_textCtrl281, self.shared_config.skip_frames)):
            try:
                if id(field) in invalid_cache_fields:
                    continue
                text = str(value)
                if str(field.GetValue()).strip() != text:
                    if field is self.interval:
                        field.ChangeValue(text)
                    else:
                        field.SetValue(text)
            except Exception:
                pass

    def _blur_settings_field(self):
        """刷新/回车提交后, 如果光标还停在设置区的输入框里, 把焦点挪走。

        否则输入框一直闪着 "|" 光标, 看着就像刚才那次修改没提交上去。
        """
        try:
            focus = wx.Window.FindFocus()
        except Exception:
            return
        if focus is None:
            return
        settings = getattr(self, "scrolledWindow_set", None)
        node = focus
        while node is not None:
            if node is settings:
                break
            node = node.GetParent()
        else:
            return
        target = getattr(self, "refresh_button", None)
        if target is None:
            return
        try:
            target.SetFocus()
        except Exception:
            pass

    def on_video_field_enter(self, event):
        """在视频设置的数值框里按回车: 立刻提交, 并把光标收掉。"""
        self._commit_video_settings()
        self._blur_settings_field()
        if event is not None:
            event.Skip()

    def on_cache_num_change(self, event):
        self._commit_video_settings()
        if getattr(self.ImgManager, 'type', None) is not None:
            self.show_img()
        if event is not None:
            event.Skip()

    def on_skip_changed(self, event):
        self._commit_video_settings()
        if event is not None:
            event.Skip()

    def on_thread_change(self, event):
        self._commit_video_settings()
        if event is not None:
            event.Skip()

    def _apply_resource_policy(self):
        mode = self.power_mode.GetSelection() + 1
        key = mode, bool(self.shared_config.video_mode)
        previous_key = getattr(self, '_resource_policy_key', None)
        if key == previous_key:
            return
        # Keep a common reference when comparing modes. Sampling only free RAM
        # again after our own caches warmed could make Maximum's budget smaller.
        if not hasattr(self, '_resource_memory_reference'):
            self._resource_memory_reference = available_memory_bytes()
        policy = resource_budget(mode, self.shared_config.video_mode,
                                 available=self._resource_memory_reference)
        self.shared_config.power_mode = policy.mode
        self.shared_config.thread = policy.workers
        self.shared_config.memory_budget = policy.memory
        processing=getattr(self.image_pipeline,'processing',None)
        if processing is not None:
            lanes=max(1,policy.workers-self.video_manager._extract_threads) if self.shared_config.video_mode else policy.workers
            processing.configure(lanes,policy.memory)
        self.video_manager._configure_video_memory()
        self._resource_policy_key = key
        self.resource_monitor.reset()
        self.video_manager._playback_pacer.reset()
        self.video_manager._pacing_model_period = None
        if self.shared_config.video_mode:
            with self.video_manager._cache_guard:
                self.video_manager._thread_allocator = AdaptiveThreadAllocator(throughput_first=True)
                self.video_manager._optimizer_seen = {}
                self.video_manager._pending_thread_plan = None
                self.video_manager._cooldown_deadline = 0.0
            self.video_manager.update_thread_count()
        self._show_resource_tooltip()
        if previous_key is not None and mode < previous_key[0]:
            self._request_memory_reclaim()
        else:
            self.memory_reclaimer.cancel()

    def _request_memory_reclaim(self):
        """Wait for old work off-GUI, join retired pools, then return free RAM."""
        vm, pipeline = self.video_manager, self.image_pipeline
        with vm._cache_guard:
            old_work = list(set(vm._pending_extract.values()) | set(vm._window_stitches.values()))
        with pipeline.lock:
            old_work.extend(pipeline.running.values())
        owner_ref = weakref.ref(self)
        def ready():
            owner = owner_ref()
            if owner is None or getattr(owner, '_is_closing', False):
                return True
            if any(not future.done() for future in old_work):
                return False
            if (owner.shared_config.video_mode
                    and vm._extract_threads + vm._stitch_threads > owner.shared_config.thread):
                # A concurrent layout invalidation can cancel a queued resize.
                # Reissue the smaller budget without requiring another GUI edit.
                vm.update_thread_count()
                return False
            with vm._cache_guard:
                if vm._pending_thread_plan is not None:
                    return False
            with pipeline.lock:
                if (not owner.shared_config.video_mode and pipeline.window is not None
                        and (pipeline.budget != owner.shared_config.thread
                             or pipeline.memory != owner.shared_config.memory_budget
                             or pipeline.workers != pipeline.desired_workers)):
                    return False
            return True
        def retire():
            vm._pipeline_workers.trim_idle()
            vm._decoder_bank.trim()
            old_work.clear()  # Do not retain Future result/exception pixel buffers.
            with vm._cache_guard:
                pools = getattr(vm, '_retired_pools', [])
                vm._retired_pools = []
            with pipeline.lock:
                pools += pipeline.retired_pools
                pipeline.retired_pools = []
            for pool in pools:
                pool.shutdown(wait=True)
            pools.clear()
        def allow_trim():
            owner = owner_ref()
            if owner is None or getattr(owner, '_is_closing', False) or owner.shared_config.is_playing:
                return False
            with vm._cache_guard:
                video_busy = bool(vm._pending_extract or vm._window_stitches
                                  or getattr(vm, '_display_delivery_pending', False))
            with pipeline.lock:
                return not video_busy and not pipeline.running and pipeline.display_key is None
        self.memory_reclaimer.request(ready, retire, allow_trim)

    def on_power_mode_changed(self, event):
        self._commit_video_settings()
        if getattr(self.ImgManager, 'type', None) is not None:
            if self.shared_config.video_mode:
                self.video_manager.update_cache()
            self.show_img()
        if event is not None:
            event.Skip()

    def _show_resource_tooltip(self):
        if self.shared_config.video_mode:
            self.video_manager._publish_thread_allocation()
        else:
            pipeline = self.image_pipeline
            self.shared_config.thread_allocation = dict(budget=self.shared_config.thread,
                extract=0, stitch=pipeline.workers or pipeline.desired_workers)
            self._refresh_power_tooltip()

    def _refresh_power_tooltip(self):
        if getattr(self, '_is_closing', False):
            return
        cfg = self.shared_config
        if cfg.video_mode:
            vm = self.video_manager
            decode=vm._extract_threads
            downstream=vm._stitch_threads
        else:
            pipeline = self.image_pipeline
            decode=0
            downstream=pipeline.processing.budget.limit
        text=f"Budget: {cfg.thread} workers\nPlan: Decode: {decode} | Process / Stitch / Compose: {downstream} shared"
        stages=self.image_pipeline.processing.snapshot()['stages']
        active_decode=self.video_manager._pipeline_workers.active[0] if cfg.video_mode and getattr(self.video_manager,'_pipeline_workers',None) else 0
        text+=f"\nActive: decode {active_decode} | process {stages.get(0,0)} | stitch {stages.get(1,0)} | compose {stages.get(2,0)}"
        monitor = getattr(self, 'resource_monitor', None)
        stats = monitor.read_snapshot() if monitor is not None else {}
        cpu, memory, fps = stats.get('cpu'), stats.get('memory'), stats.get('fps')
        if cpu is None or memory is None:
            text += '\nCPU / RAM avg (10s): sampling...' if stats.get('available', True) else '\nCPU / RAM: unavailable (psutil)'
        else:
            usage = f'{memory / 1024**3:.2f} GiB' if memory >= 1024**3 else f'{memory / 1024**2:.0f} MiB'
            text += f'\nCPU avg (10s): {cpu:.1f}%; RAM avg: {usage}'
        text += ('\nPlayback: paused' if not cfg.is_playing else
                 f'\nPlayback: {fps:.1f} FPS' if fps is not None else '\nPlayback: sampling...')
        tooltip = self.power_mode.GetToolTip()
        if tooltip is None:
            self.power_mode.SetToolTip(text)
        elif tooltip.GetTip() != text:
            tooltip.SetTip(text)


    # def on_interval_changed(self, event):
    #     self.shared_config.interval = float(self.interval.GetValue() or 1.0)
    #b1 修改


    def parallel_sequential_fc(self, event):
        self.shared_config.parallel_sequential = self.parallel_sequential.GetValue()
        if self.parallel_sequential.Value:
            self.parallel_to_sequential.Value = False
            self.shared_config.parallel_to_sequential =False
        if self.shared_config.video_mode:
            self._parallel_switch_dirty = True
        else:
            # ★ 图片模式：不再立刻重建 + 重绘。
            #   这里只把状态标记为"待应用"，等用户手动刷新（⟳ / 菜单 Refresh）时
            #   由 _apply_parallel_switch() 统一重建并显示，避免切换瞬间就重扫目录、重拼接。
            self._parallel_switch_dirty = True
            self._notify_parallel_switch_pending()

    def _notify_parallel_switch_pending(self):
        """提示用户: 并行/串行读取方式已改变, 需要手动刷新后生效。"""
        if getattr(self.shared_config, "video_mode", False):
            return
        try:
            self.SetStatusText_([
                "-1", "-1",
                "***Parallel setting changed, press Refresh to apply***", "-1"])
        except Exception:
            pass


    def _init_image_stitch_executor(self):
        """The bounded image pipeline creates its pool lazily in the background."""
        pass

    def _shutdown_image_stitch_executor(self):
        """Shut down the image-mode stitch pool."""
        if hasattr(self, 'image_pipeline'):
            if getattr(self, '_is_closing', False):
                self.image_pipeline.close()
                self.memory_reclaimer.close()
                self.resource_monitor.close()
            else:
                self.image_pipeline.invalidate()
        if self.image_stitch_executor is not None:
            self.image_stitch_executor.shutdown(wait=False)
            self.image_stitch_executor = None

    def parallel_to_sequential_fc(self, event):
        value = self.parallel_to_sequential.GetValue()
        self.shared_config.parallel_to_sequential = value
        if value:
            self.parallel_sequential.Value = False
            self.shared_config.parallel_sequential = False
        if self.shared_config.video_mode:
            self._parallel_switch_dirty = True
        else:
            # ★ 图片模式：同样不在切换瞬间重建 + 重绘，改为标记待应用，
            #   由用户手动刷新时通过 _apply_parallel_switch() 统一处理。
            self._parallel_switch_dirty = True
            self._notify_parallel_switch_pending()

    def _apply_parallel_switch(self):
        """应用 parallel / parallel+sequential 开关的变化。

        视频模式: 重新计算总帧数与每批帧数。
        图片模式: 按新的读取顺序（parallel_to_sequential / parallel_sequential）
                  重新初始化 ImgManager，并清空图片模式的渲染缓存。
        """
        if not getattr(self.shared_config, "video_mode", False):
            self._apply_parallel_switch_image()
            return

        nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None]
        if not nums:
            return

        if self.shared_config.parallel_to_sequential:
            self.ImgManager.img_num = sum(nums)
        else:
            self.ImgManager.img_num = max(nums)

        new_count = self._sync_video_count_per_action()
        if new_count:
            self.shared_config.count_per_action = new_count

        count = max(1, int(self.shared_config.count_per_action or 1))
        img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
        if img_num > 0:
            max_batches = (img_num + count - 1) // count
        else:
            max_batches = 1
        self.ImgManager.max_action_num = max(1, max_batches)

        max_idx = self.ImgManager.max_action_num - 1
        self.shared_config.batch_idx = min(self.shared_config.batch_idx, max(0, max_idx))
        self.ImgManager.action_count = self.shared_config.batch_idx
        self.ImgManager.img_count = self.shared_config.batch_idx * self.ImgManager.count_per_action

        self.shared_config.cache_img = []
        if hasattr(self.video_manager, "_last_batch"):
            self.video_manager._last_batch = None

    def _apply_parallel_switch_image(self):
        """图片模式下应用 parallel / parallel+sequential 的变化。

        手动刷新时调用：按新的读取方式重新初始化 ImgManager，
        并清空图片模式的渲染缓存，让随后的 show_img_init()/show_img()
        按新布局重新拼接显示。
        """
        img_mgr = getattr(self, "ImgManager", None)
        if (
            not img_mgr
            or not getattr(img_mgr, "input_path", None)
            or getattr(img_mgr, "type", None) not in (0, 1)
        ):
            return
        try:
            img_mgr.init(
                img_mgr.input_path,
                img_mgr.type,
                parallel_to_sequential=bool(self.shared_config.parallel_to_sequential),
                action_count=0,
                img_count=0,
                video_mode=False,
                skip=getattr(img_mgr, "skip", 0),
            )
            img_mgr.set_action_count(0)
            self.shared_config.batch_idx = 0
            self.shared_config.image_cache_img = []
            self.shared_config.image_cache_paths = []
        except Exception as ex:
            if getattr(self.shared_config, "debug_image", False):
                print(f"[ImageMode] apply parallel switch failed: {ex}")

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
                    pass
                else:
                    evt = MyTestEvent(self.myEVT_MY_TEST)
                    evt.SetEventArgs(output["tag_name"])
                    wx.PostEvent(self, evt)
        except:
            pass

    def _get_system_font_display_name(self, font_path):
        try:
            font = ImageFont.truetype(str(font_path), 12)
            family, style = font.getname()
        except Exception:
            return None
        family = family.strip() if family else ""
        style = style.strip() if style else ""
        if not family:
            family = font_path.stem.replace("-", " ").replace("_", " ")
        if style and style.lower() not in ["regular", "normal", "roman"]:
            return f"{family} {style}"
        return family

    def _collect_font_items_from_dirs(self, font_dirs):
        font_items = []
        seen_names = set()
        seen_paths = set()
        valid_suffixes = {".ttf", ".otf", ".ttc"}
        for font_dir in font_dirs:
            font_dir = Path(font_dir)
            if not font_dir.exists():
                continue
            try:
                for font_path in font_dir.rglob("*"):
                    if not font_path.is_file():
                        continue
                    if font_path.suffix.lower() not in valid_suffixes:
                        continue
                    path_str = str(font_path)
                    path_key = path_str.lower()
                    if path_key in seen_paths:
                        continue
                    display_name = self._get_system_font_display_name(font_path)
                    if not display_name:
                        continue
                    name_key = display_name.lower()
                    if name_key in seen_names:
                        continue
                    seen_paths.add(path_key)
                    seen_names.add(name_key)
                    font_items.append((display_name, path_str))
            except Exception:
                continue
        return sorted(font_items, key=lambda item: item[0].lower())


    def set_title_font(self):
        self.title_font.Clear()
        sys_platform = platform.system()
        font_items = []
        if sys_platform.find("Windows") >= 0 and winreg is not None:
            font_dir = Path(r"C:\Windows\Fonts")
            font_enum = wx.FontEnumerator()
            font_names = sorted(set(font_enum.GetFacenames()), key=str.lower)
            registry_fonts = {}
            reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    i = 0
                    while True:
                        try:
                            display_name, font_file, _ = winreg.EnumValue(key, i)
                            i += 1
                            if not isinstance(font_file, str):
                                continue
                            font_path = font_dir / font_file
                            if not font_path.is_file():
                                continue
                            if font_path.suffix.lower() not in [".ttf", ".otf", ".ttc"]:
                                continue
                            clean_name = display_name.replace(" (TrueType)", "").replace(" (OpenType)", "")
                            registry_fonts[clean_name.lower()] = (clean_name, str(font_path))
                        except OSError:
                            break
            except Exception:
                registry_fonts = {}
            for name in font_names:
                item = registry_fonts.get(name.lower())
                if item:
                    font_items.append(item)
        elif sys_platform.find("Linux") >= 0:
            font_dirs = [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
                Path.home() / ".local" / "share" / "fonts",
            ]
            font_items = self._collect_font_items_from_dirs(font_dirs)
        elif sys_platform.find("Darwin") >= 0:
            font_dirs = [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts",
            ]
            font_items = self._collect_font_items_from_dirs(font_dirs)
        if font_items:
            for display_name, _ in font_items:
                self.title_font.Append(display_name)

            self.font_paths = [font_path for _, font_path in font_items]
            self.title_font.SetSelection(0)
            return
        font_path = Path("font") / "using"
        font_path = Path(get_resource_path(str(font_path)))
        files_name = [f.stem for f in font_path.iterdir()]
        files_name = np.sort(np.array(files_name)).tolist()
        for file_name in files_name:
            file_name = file_name.split("_", 1)[1]
            file_name = file_name.replace("-", " ")
            self.title_font.Append(file_name)
        if files_name:
            self.title_font.SetSelection(0)
        font_paths = [str(f) for f in font_path.iterdir()]
        self.font_paths = np.sort(np.array(font_paths)).tolist()

    def frame_resize(self, event):
        if not self.IsMaximized() and not self.IsIconized():
            pos = self.GetPosition()
            size = self.GetSize()
            self._normal_window_pos = (pos[0], pos[1])
            self._normal_window_size = (size[0], size[1])
        self.auto_layout(frame_resize=True)

    def open_all_img(self, event):
        previous_batch = self.shared_config.batch_idx
        previous_input_mode = self.shared_config.input_mode
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
        if input_mode == 0:
            selected = self.one_dir_mul_img(event)
            if selected is False:
                self.shared_config.batch_idx = previous_batch
                self.shared_config.input_mode = previous_input_mode
        elif input_mode == 1:
            selected = self.one_dir_mul_dir_auto(event)
            if selected is False:
                self.shared_config.batch_idx = previous_batch
                self.shared_config.input_mode = previous_input_mode
        elif input_mode == 2:
            self.one_dir_mul_dir_manual(event)
        elif input_mode == 3:
            if self.onefilelist() is False:
                self.shared_config.batch_idx = previous_batch
                self.shared_config.input_mode = previous_input_mode

    def one_dir_mul_dir_auto(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=1)
            if not selected:
                return False
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Parallel auto choose input dir", "",
                           wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return False
                self.ImgManager.init(dlg.GetPath(), type=0, parallel_to_sequential=self.parallel_to_sequential.Value)
            finally:
                dlg.Destroy()
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        if self.shared_config.video_mode:
            # ★ show_img_init() 会因布局参数变化清空视频缓存，
            #   必须在它之后重新抽帧+拼接, 否则首帧缺失只会显示 "Waiting for batch 0"。
            self.video_manager.update_cache()
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(1)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])
        return True

    def close(self, event):
        if self._is_closing:
            return
        self._is_closing = True
        try:
            self._save_session_configuration()
        except (OSError, ValueError) as exc:
            print(f"[Config] Unable to save last session: {exc}")
        self._save_window_state()

        # ★ 修复：先停止所有后台任务，避免 rmtree 失败或线程残留
        try:
            self.play_timer.Stop()
        except Exception:
            pass
        # 标记为不再播放，避免 timer 回调中再次启动任务
        try:
            self.shared_config.is_playing = False
        except Exception:
            pass

        # 取消未开始的 pending frame wait，避免回调访问已销毁的窗口
        try:
            if hasattr(self, "_cancel_pending_frame_wait"):
                self._cancel_pending_frame_wait()
        except Exception:
            pass

        # Release thread pools
        if hasattr(self, "video_manager"):
            self.video_manager.shutdown()

        # Release the image-mode stitch pool
        self._shutdown_image_stitch_executor()

        if hasattr(self, 'show_bmp_in_panel'):
            del self.show_bmp_in_panel
        if hasattr(self, 'ImgManager'):
            if hasattr(self.ImgManager, 'clear_cache'):
                self.ImgManager.clear_cache()

        import gc
        gc.collect()

        # ★ 修复：用 try/except 包装 rmtree，避免目录被线程持有时抛出未捕获异常
        # Wait off the GUI thread before recursively removing the cache tree.
        # Both media pipelines must be stopped before scheduling deletion.
        pipeline=self.image_pipeline
        vm=self.video_manager
        if pipeline.closed and getattr(vm,'_closed',False):
            from .cache_shutdown import schedule_cache_removal
            root=Path(vm.cache_dir).absolute()
            if root!=pipeline.directory.parent.absolute():
                raise ValueError('Image and video cache roots differ; refusing recursive cleanup')
            pools=(pipeline.coordinator,pipeline.pool,pipeline.display,*pipeline.retired_pools,
                   vm._cache_executor,vm.executor,vm.stitch_executor,vm._maintenance_executor,vm._display_executor)
            self._cache_cleanup_future=schedule_cache_removal(root,pools,
                (getattr(pipeline.processing,'cleanup_future',None),))

        if hasattr(self, "indextablegui") and self.indextablegui:
            self.indextablegui.Destroy()
        if hasattr(self, "aboutgui") and self.aboutgui:
            self.aboutgui.Destroy()

        # ★ 修复：Destroy 自身
        try:
            self.Destroy()
        except Exception:
            pass

        # ★ 修复：通知主循环退出，确保程序完全终止
        try:
            wx.Exit()
        except Exception:
            pass


    def one_dir_mul_dir_manual(self, event):
        self.SetStatusText_(["Input", "", "", "-1"])
        # ★ 打开 "Parallel manual" 选择窗口时, 路径列表一律为空。
        #   以前这里会把 ImgManager.input_path(当前已打开的目录, 顺序/并行自动模式选中的那个)
        #   或者上一次手动选择的结果传过去, 于是选择框里会出现"这次并没有选"的路径。
        #   用户以为只挑了新目录, 关闭时旧目录却被一起提交,
        #   在图片/视频模式之间来回切换时尤其容易把路径带错。
        #   现在不预填: 列表里看到的就是这次真正要用的路径集合。
        if self.shared_config.video_mode:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value ,video_manager = self.video_manager,shared_config=self.shared_config)
        else:
            self.UpdateUI(1, None, self.parallel_to_sequential.Value)
        self.SetStatusText_(["Input", "-1", "-1", "-1"])

    #b5
    def last_img(self, event):
        if self.shared_config.video_mode and self.shared_config.is_playing and not getattr(self, "_from_timer", False):
            self.shared_config.play_direction = -1
            self.last_direction = self.shared_config.play_direction
            return
        if (not self.shared_config.video_mode and
                self.shared_config.is_playing and
                not getattr(self, "_from_timer", False)):
            self.shared_config.play_direction = -1
            self.last_direction = -1
            return

        if self.shared_config.batch_idx <= 0:
            if getattr(self.shared_config, "is_playing", False):
                self.shared_config.is_playing = False
                try:
                    self.play_timer.Stop()
                except Exception:
                    pass
                try:
                    self.right_arrow_button1.SetLabel("▶")
                except Exception:
                    pass
                self.shared_config.play_direction = 1
                self.last_direction = 1
            return

        if self.shared_config.video_mode:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = -1
                self.last_direction = self.shared_config.play_direction
            if self.shared_config.batch_idx > 0:
                self.shared_config.batch_idx -= 1

            # CallAfter defers lightweight scheduling on the GUI thread.
            wx.CallAfter(self.video_manager.update_cache)

        if self.shared_config.video_mode:
            if self.ImgManager.img_count != 0:
                self.ImgManager.subtract()
            self.shared_config.batch_idx = max(0, self.shared_config.batch_idx)
        else:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = -1
                self.last_direction = -1
            if self.shared_config.batch_idx > 0:
                self.shared_config.batch_idx -= 1
            if self.ImgManager.img_count != 0:
                self.ImgManager.subtract()
            self.shared_config.batch_idx = max(0, self.ImgManager.action_count)

        if not getattr(self, "_from_timer", False):
            self.show_img_init()

        self.show_img()
        self.SetStatusText_(["Last", "-1", "-1", "-1"])



    def save_img(self, event):
        from .export_controller import save_viewer
        save_viewer(self,event)

    def refresh(self, event):
        self._custom_settings_dirty=False
        if getattr(self, "_parallel_switch_dirty", False):
            self._apply_parallel_switch()
            self._parallel_switch_dirty = False
        # ★ 先把设置区数值框的内容提交进来, 再往下走。
        #   以前 refresh() 直接读 shared_config, 而数值框只在"失去焦点"时才写回,
        #   所以用菜单/快捷键(Ctrl+R)刷新时, 刚改的 Cached Frames 会被静默丢弃。
        self._commit_video_settings()
        self.show_img_init()
        if getattr(self.shared_config, "video_mode", False):
            self._last_refresh_batch = None
            vm = getattr(self, "video_manager", None)
            if vm is not None and hasattr(vm, "_last_batch"):
                vm._last_batch = None
        if self.shared_config.video_mode:
            new_thr = int(getattr(self.shared_config, 'thread', 1) or 1)
            last_thr = getattr(self, '_last_thread', None)
            if last_thr != new_thr:
                self._rebuild_threads(new_thr)
                self._last_thread = new_thr

            # ★ 修复：skip_frames 改变后，重新计算 video_num_list
            vm = getattr(self, 'video_manager', None)
            if vm is not None:
                self.shared_config.video_num_list = []
                self.shared_config.video_fps_list = []
                for vp in getattr(self.shared_config, "real_video_path", []):
                    try:
                        vm.calc_max_extractable_frames_single(vp)
                    except Exception:
                        self.shared_config.video_num_list.append(0)
                        self.shared_config.video_fps_list.append(0)
                # ★ 同步更新 ImgManager 内部状态，避免 set_count_per_action 等使用陈旧值
                self.ImgManager.video_num_list = list(self.shared_config.video_num_list)
                self.ImgManager.video_fps_list = list(self.shared_config.video_fps_list)
                self.ImgManager.img_num_list = list(self.shared_config.video_num_list)
                if self.shared_config.parallel_to_sequential:
                    self.ImgManager.img_num = sum(int(x) for x in self.shared_config.video_num_list if x)
                else:
                    self.ImgManager.img_num = max(int(x) for x in self.shared_config.video_num_list if int(x) > 0) if any(int(x) > 0 for x in self.shared_config.video_num_list) else 0

            nums = [int(x) for x in getattr(self.shared_config, "video_num_list", []) if x is not None and int(x) > 0]
            if not nums:
                self.ImgManager.max_action_num = 1
                self.shared_config.batch_idx = 0
                self.SetStatusText_(["-1", "-1", "***Error: no valid videos loaded, please reselect input***", "-1"])
                return

            if self.shared_config.parallel_to_sequential:
                img_num = sum(nums)
            else:
                img_num = max(nums)

            count = max(1, int(self.shared_config.count_per_action or 1))
            if img_num % count:
                max_action_num = int(img_num / count) + 1
            else:
                max_action_num = int(img_num / count)

            self.ImgManager.max_action_num = max(1, max_action_num)

            if self.shared_config.batch_idx >= self.ImgManager.max_action_num:
                self.shared_config.batch_idx = self.ImgManager.max_action_num - 1

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

            if self.ImgManager.action_count >= self.ImgManager.max_action_num:
                self.ImgManager.action_count = self.ImgManager.max_action_num-1
                self.shared_config.batch_idx = self.ImgManager.action_count

            # 视频模式：读取文本框值并跳转到对应位置
            try:
                target = int(self.slider_value.GetValue().strip()) - 1
            except (ValueError, AttributeError):
                target = self.shared_config.batch_idx

            # 限制目标在有效范围内
            max_allowed = max(0, self.ImgManager.max_action_num - 1)
            clamped = min(max(0, target), max_allowed)

            # 更新状态
            self.shared_config.batch_idx = clamped
            self.ImgManager.action_count = clamped

        if self.ImgManager.img_num != 0:
            # 图片模式：读取文本框值并跳转到对应位置
            if not getattr(self.shared_config, "video_mode", False):
                try:
                    target = int(self.slider_value.GetValue().strip()) - 1
                except (ValueError, AttributeError):
                    target = self.ImgManager.action_count

                # 重新计算 max_action_num（以防图片数量变化）
                count = max(1, self.ImgManager.count_per_action)
                img_num = int(getattr(self.ImgManager, "img_num", 0) or 0)
                if img_num > 0:
                    max_batches = (img_num + count - 1) // count
                else:
                    max_batches = 1
                self.ImgManager.max_action_num = max(1, max_batches)

                # 限制目标在有效范围内
                max_allowed = max(0, self.ImgManager.max_action_num - 1)
                clamped = min(max(0, target), max_allowed)

                # 更新状态
                self.shared_config.batch_idx = clamped
                self.ImgManager.action_count = clamped
                self.ImgManager.img_count = clamped * self.ImgManager.count_per_action

            self.show_img(preserve_text_value=True)
        else:
            self.SetStatusText_(["-1", "", "***Error: First, need to select the input dir***", "-1"])
        # ★ 刷新完把设置区输入框的光标收掉, 否则框里一直闪着 "|",
        #   看上去就像刚才那次修改没提交成功。
        if getattr(self.shared_config, "video_mode", False):
            self._blur_settings_field()
        self.SetStatusText_(["Refresh", "-1", "-1", "-1"])

    def _invalidate_render_cache(self):
        """Clear current cache to force restitching (shared by video/image modes)."""
        self.shared_config.image_cache_img = []
        self.shared_config.image_cache_paths = []
        if hasattr(self, 'image_pipeline'):
            self.image_pipeline.invalidate()
        self._image_reference_resolution_origin = None
        cache = getattr(self.shared_config, "cache_img", None)
        if isinstance(cache, list):
            for i in range(len(cache)):
                cache[i] = None
        self._last_refresh_batch = None
        vm = getattr(self, "video_manager", None)
        if vm is not None:
            vm._invalidate_stitch_cache()
        if vm is not None and hasattr(vm, "_last_batch"):
            vm._last_batch = None


    def one_dir_mul_img(self, event):
        self.SetStatusText_(
            ["Sequential choose input dir", "", "", "-1"])
        if self.shared_config.video_mode:
            selected = self.video_manager.select_video(type=0)
            if not selected:
                return False
        else:
            # Initialize the image stitch pool
            self._init_image_stitch_executor()

            dlg = wx.DirDialog(None, "Choose input dir", "",
                               wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)

            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return False
                self.ImgManager.init(dlg.GetPath(), type=2)
            finally:
                dlg.Destroy()
        if self.shared_config.video_mode:
            if self.shared_config.video_path == []:
                return
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        if self.shared_config.video_mode:
            # ★ show_img_init() 会因布局参数变化清空视频缓存，
            #   必须在它之后重新抽帧+拼接, 否则首帧缺失只会显示 "Waiting for batch 0"。
            self.video_manager.update_cache()
        self.show_img()
        self._reset_image_view_origin()
        self.choice_input_mode.SetSelection(0)

        self.SetStatusText_(
            ["Sequential choose input dir", "-1", "-1", "-1"])
        return True

    def onefilelist(self, event=None):
        self.SetStatusText_(["Choose the File List", "", "", "-1"])
        self._init_image_stitch_executor()
        wildcard = "List file (*.txt; *.csv)|*.txt; *.csv|All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "Choose the File List", "", "", wildcard,
                            wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            path = dlg.GetPath()
        finally:
            dlg.Destroy()
        if self.shared_config.video_mode:
            return self._open_video_file_list(path)
        return self._open_image_file_list(path)

    def _open_image_file_list(self, path):
        # Validate on a shallow metadata copy so a bad list preserves the
        # current manager (also referenced by the video/cache controllers).
        candidate = copy.copy(self.ImgManager)
        try:
            candidate.init(path, type=3)
        except (OSError, ValueError, UnicodeError) as error:
            self.SetStatusText_(['Input', '-1', f'Unable to read image list: {error}', '-1'])
            return False
        if not len(candidate.path_list):
            self.SetStatusText_(['Input', '-1', 'No valid image files in this list', '-1'])
            return False
        self.ImgManager.__dict__.update(candidate.__dict__)
        self.shared_config.input_mode = 3
        self.choice_input_mode.SetSelection(3)
        self.show_img_init()
        self.ImgManager.set_action_count(0)
        self.show_img()
        self.choice_input_mode.SetSelection(3)
        return True

    def input_flist_parallel_manual(self, event):
        # Initialize the image stitch pool
        self._init_image_stitch_executor()

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
            self.SetStatusText_(["-1", "-1", "-1", "Output: " + self.out_path_str])

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
                self._invalidate_render_cache()
                self.refresh(event)
                self.SetStatusText_(
                    ["delete "+str(self.box_id)+"-th box",  "-1", "-1", "-1"])
        else:
            self.xy_magnifier = []
            self._invalidate_render_cache()
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
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
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
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
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
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
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
                self._invalidate_render_cache()
                self.refresh(event)
        else:
            size = self.scrolledWindow_img.GetVirtualSize()
            self.position[0] = int(
                self.scrolledWindow_img.GetScrollPos(wx.HORIZONTAL)/self.Uint[0])
            self.position[1] = int(
                self.scrolledWindow_img.GetScrollPos(wx.VERTICAL)/self.Uint[1])
            if self.position[0] > 0:
                self.position[0] -= speed
                self.scrolledWindow_img.Scroll(
                    self.position[0]*self.Uint[0], self.position[1]*self.Uint[1])
        self.SetStatusText_(["Left",  "-1", "-1", "-1"])



    def img_left_click(self, event):
        if not len(getattr(self.ImgManager, 'xy_grid', [])):
            return

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
        self._remember_main_selection(id)
        self.update_status_bar_for_current_page(id)

    def img_left_dclick(self, event):
        if self.select_img_box.Value:
            pass
        else:
            self.start_flag = 0
            self.xy_magnifier = []
            self.color_list = []
            self.box_position.SetSelection(0)
            self._invalidate_render_cache()

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
        if not hasattr(self, "show_bmp_in_panel") or self.show_bmp_in_panel is None:
            return
        if not hasattr(self.ImgManager, "xy_grid") or len(getattr(self.ImgManager, "xy_grid", [])) == 0:
            return
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        xy_grid = self.ImgManager.xy_grid[id]
        try:
            w, h = self.show_bmp_in_panel.size
            px = max(0, min(int(x), max(0, w - 1)))
            py = max(0, min(int(y), max(0, h - 1)))
            RGBA = self.show_bmp_in_panel.getpixel((px, py))
        except Exception:
            RGBA = (-1, -1, -1, -1)
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        self.SetStatusText_([str(x)+","+str(y)+"/"+str(RGBA), "-1", "-1", "-1"])

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
                self._invalidate_render_cache()
                self.refresh(event)

    def img_right_click(self, event):
        x, y = event.GetPosition()
        id = self.get_img_id_from_point([x, y])
        if hasattr(self.ImgManager, '_show_all_func_enabled') and self.ImgManager._show_all_func_enabled:
            xy_grid_array = np.array(self.ImgManager.xy_grid)
            xy_cur = np.array([[x, y]])
            xy_cur = np.repeat(xy_cur, xy_grid_array.shape[0], axis=0)
            res_ = xy_cur - xy_grid_array
            id_list = []
            for i in range(xy_grid_array.shape[0]):
                if res_[i][0] >= 0 and res_[i][1] >= 0:
                    id_list.append(i)
                else:
                    id_list.append(0)
            actual_grid_id = max(id_list)
            xy_grid = self.ImgManager.xy_grid[actual_grid_id]
        else:
            xy_grid = self.ImgManager.xy_grid[id]
        x = x-xy_grid[0]
        y = y-xy_grid[1]
        menu_triggered = getattr(event, 'menu_triggered', False)

        if not menu_triggered:
            self.on_right_click(event)
            return

        if self.select_img_box.Value:
            # move box
            if self.box_id != -1:
                show_scale = self.show_scale.GetLineText(0).split(',')
                show_scale = [float(x) for x in show_scale]
                points = self.move_box_point(x, y, show_scale)
                self.xy_magnifier[self.box_id] = points+show_scale+[
                    self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]]
                self._invalidate_render_cache()
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

                self._invalidate_render_cache()
                self.refresh(event)
                self.SetStatusText_(["Magnifier", "-1", "-1", "-1"])
        self.on_right_click(event)

    def on_right_click(self, event):
        # Right-click Menu​
        menu = wx.Menu()
        refresh_id = wx.Window.NewControlId()
        menu.Append(refresh_id, "🔄 refresh")
        menu.Bind(wx.EVT_MENU, self.refresh, id=refresh_id)

        prev_id = wx.Window.NewControlId()
        menu.Append(prev_id, "⬅️ Previous Page")
        menu.Bind(wx.EVT_MENU, self.last_img, id=prev_id)

        next_id = wx.Window.NewControlId()
        menu.Append(next_id, "➡️ Next Page")
        menu.Bind(wx.EVT_MENU, self.next_img, id=next_id)

        save_single_id = wx.Window.NewControlId()
        menu.Append(save_single_id, "💾 Save")
        def save_current_page(evt):
            # Default Save
            self.save_img(evt)
        menu.Bind(wx.EVT_MENU, save_current_page, id=save_single_id)

        if (self.ImgManager.type == 0 or self.ImgManager.type == 1) and (self.parallel_sequential.Value):
            save_column_id = wx.Window.NewControlId()
            menu.Append(save_column_id, "📄 save(only select current location)")
            def save_selected_column(evt):
                # save current location images in all folders
                if not self.out_path_str:
                    self.out_path(evt)
                    if not self.out_path_str:
                        return
                x, y = event.GetPosition()
                clicked_grid_id = self.get_img_id_from_point([x, y])
                # Retrieve ID information
                if hasattr(self, 'current_page_img_paths') and clicked_grid_id < len(self.current_page_img_paths):
                    target_path = self.current_page_img_paths[clicked_grid_id]
                else:
                    actual_img_index = self.ImgManager.xy_grids_id_list[clicked_grid_id] \
                        if hasattr(self.ImgManager, 'xy_grids_id_list') and clicked_grid_id < len(self.ImgManager.xy_grids_id_list) \
                        else clicked_grid_id

                    if not hasattr(self.ImgManager, 'flist') or actual_img_index >= len(self.ImgManager.flist):
                        self.SetStatusText_(["Cannot get clicked image", "-1", "-1", "-1"])
                        return
                    target_path = self.ImgManager.flist[actual_img_index]
                if not target_path or not os.path.exists(target_path):
                    self.SetStatusText_(["Invalid image path", "-1", "-1", "-1"])
                    return
                target_name = os.path.basename(target_path)
                type_ = self.choice_output.GetSelection()
                if self.show_custom_func.Value:
                    self.ImgManager.layout_params[32] = True
                    self.ImgManager.save_img(self.out_path_str, type_)
                    self.ImgManager.layout_params[32] = False
                self.ImgManager.save_img(self.out_path_str, type_)
                self.ImgManager.save_stitch_img_and_customfunc_img(self.out_path_str, self.show_custom_func.Value)

                # Call the default save function
                select_folder = os.path.join(self.out_path_str, "select_images")
                # override it with the new folder selection logic
                if os.path.exists(select_folder):
                    shutil.rmtree(select_folder)
                os.makedirs(select_folder, exist_ok=True)
                all_dirs = sorted(set(os.path.dirname(p) for p in self.ImgManager.flist))
                success_count = 0
                for folder_path in all_dirs:
                    if not os.path.exists(folder_path):
                        continue
                    try:
                        target_file = os.path.join(folder_path, target_name)
                        if os.path.exists(target_file) and os.path.isfile(target_file):
                            folder_name = os.path.basename(folder_path)
                            sub_dir = os.path.join(select_folder, folder_name)
                            os.makedirs(sub_dir, exist_ok=True)
                            shutil.copy2(target_file, os.path.join(sub_dir, target_name))
                            success_count += 1
                    except:
                        pass
                status_msg = f"Save completed! select_images updated with {success_count} images (clicked: {target_name})" \
                    if success_count > 0 \
                    else f"Save completed, but no matching images found for {target_name}"
                self.SetStatusText_([status_msg, "-1", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, save_selected_column, id=save_column_id)

        if self.magnifier.Value:
            new_box_id = wx.Window.NewControlId()
            menu.Append(new_box_id, "🔍 Create zoom box here")

            def create_magnifier_box(evt):
                event.menu_triggered = True
                x, y = event.GetPosition()
                id = self.get_img_id_from_point([x, y])
                xy_grid = self.ImgManager.xy_grid[id]
                x = x-xy_grid[0]
                y = y-xy_grid[1]

                if self.magnifier.Value:
                    self.color_list.append(self.colourPicker_draw.GetColour())
                    try:
                        show_scale = self.show_scale.GetLineText(0).split(',')
                        show_scale = [float(x) for x in show_scale]
                        if len(self.xy_magnifier) == 0:
                            default_size = 50
                            points = self.ImgManager.ImgF.sort_box_point(
                                [x-default_size//2, y-default_size//2, x+default_size//2, y+default_size//2],
                                show_scale, self.ImgManager.img_resolution_origin, first_point=True)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        else:
                            points = self.move_box_point(x, y, show_scale)
                            self.xy_magnifier.append(
                                points+show_scale+[self.ImgManager.title_setting[2] and self.ImgManager.title_setting[1]])
                        self._invalidate_render_cache()
                        self.refresh(evt)
                        self.SetStatusText_(["Create a zoom box", "-1", "-1", "-1"])
                    except Exception as e:
                        self.SetStatusText_(["-1", f"Failed to create zoom box: {str(e)}", "-1", "-1"])
            menu.Bind(wx.EVT_MENU, create_magnifier_box, id=new_box_id)

        if len(self.xy_magnifier) > 0:
            clear_all_id = wx.Window.NewControlId()
            menu.Append(clear_all_id, "🗑️ Clear all zoom boxes")
            menu.Bind(wx.EVT_MENU, self.img_left_dclick, id=clear_all_id)

        if self.select_img_box.Value:
            box_menu = wx.Menu()

            if self.box_id != -1:
                move_box_id = wx.Window.NewControlId()
                box_menu.Append(move_box_id, f"Move box {self.box_id} to this position")

                def move_box_to_position(evt):
                    event.menu_triggered = True
                    self.img_right_click(event)
                    self._invalidate_render_cache()
                    self.refresh(evt)
                    self.SetStatusText_([f"Move box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, move_box_to_position, id=move_box_id)
                delete_box_id = wx.Window.NewControlId()
                box_menu.Append(delete_box_id, f"Delete box {self.box_id}")
                def delete_specific_box(evt):
                    if self.select_img_box.Value and self.box_id != -1:
                        self.xy_magnifier.pop(self.box_id)
                        if len(self.xy_magnifier) == 0:
                            self.box_position.SetSelection(0)
                        self._invalidate_render_cache()
                        self.refresh(evt)
                        self.SetStatusText_([f"Delete box {self.box_id}", "-1", "-1", "-1"])
                box_menu.Bind(wx.EVT_MENU, delete_specific_box, id=delete_box_id)
            menu.AppendSubMenu(box_menu, f"Selection box" + (f" ({self.box_id})" if self.box_id != -1 else ""))

        if hasattr(self, 'title_rename_text'):
            new_title = self.title_rename_text.GetValue().strip()
            if new_title:
                inject_title_id = wx.Window.NewControlId()
                display_title = new_title[:20] + "..." if len(new_title) > 20 else new_title
                menu.Append(inject_title_id, f"📝 Inject title: {display_title}")
                def inject_title_directly(evt):
                    x, y = event.GetPosition()
                    id = self.get_img_id_from_point([x, y])
                    success = self.handle_title_injection(id)
                    if success:
                        self.SetStatusText_(["Title injected successfully", "-1", "-1", "-1"])
                    else:
                        self.SetStatusText_(["Failed to inject title", "-1", "-1", "-1"])
                menu.Bind(wx.EVT_MENU, inject_title_directly, id=inject_title_id)
                menu.AppendSeparator()
        try:
            mouse_screen_pos = wx.GetMousePosition()
            client_pos = self.ScreenToClient(mouse_screen_pos)
        except:
            client_pos = wx.Point(100, 100)

        self.PopupMenu(menu, client_pos)
        menu.Destroy()

    #--exif--
    def on_title_exif_changed(self, event):
        if hasattr(self, 'ImgManager') and hasattr(self.ImgManager, 'layout_params'):
            if len(self.ImgManager.layout_params) > 17:
                self.ImgManager.layout_params[17][11] = self.title_exif.Value
                self.ImgManager.load_exif_display_config(force_reload=True)

    def inject_new_title(self, new_title, img_id=None):
        try:
            if img_id is not None:
                current_index = img_id
            else:
                current_index = getattr(self, 'selected_img_id', self.ImgManager.action_count)
            if hasattr(self.ImgManager, 'xy_grids_id_list') and current_index < len(self.ImgManager.xy_grids_id_list):
                actual_img_index = self.ImgManager.xy_grids_id_list[current_index]
            else:
                actual_img_index = current_index
            if actual_img_index < len(self.ImgManager.flist):
                img_path = self.ImgManager.flist[actual_img_index]
                success = self.ImgManager.update_image_exif_37510(img_path, new_title)
                if success:
                    self._invalidate_render_cache()
                    self.refresh(None)
                    self.SetStatusText("✅ Title updated successfully!")

                    if hasattr(self, 'title_rename_text'):
                        self.title_rename_text.SetValue("")
                    self.SetStatusText_([f"The title has been injected into {current_index+1} images: {new_title}", "-1", "-1", "-1"])
                    return True
                else:
                    raise Exception("Failed to write EXIF")
            else:
                raise Exception(f"Picture index {actual_img_index} out of range")

        except Exception as exc:
            self.SetStatusText_([f"Inject title failed: {exc}", "-1", "-1", "-1"])
            return False

    def handle_title_injection(self, img_id = None):
        if not hasattr(self, 'title_rename_text'):
            return False
        new_title = self.title_rename_text.GetValue().strip()
        if not new_title:
            return False
        return bool(self.inject_new_title(new_title, img_id))

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
            # Check whether Shift and 'S' are pressed together
        elif event.GetKeyCode() == ord('S'):
            if self.shift_pressed == True:
                # React when Shift + S is pressed
                if self.key_status["shift_s"] == 0:
                    self.key_status["shift_s"] = 1
                elif self.key_status["shift_s"] == 1:
                    self.key_status["shift_s"] = 0
        event.Skip()

    def key_up_detect(self, event):
        if event.GetKeyCode() == wx.WXK_CONTROL:
            if self.key_status["ctrl"] == 1:
                self.key_status["ctrl"] = 0
        elif event.GetKeyCode() == wx.WXK_SHIFT:
            self.shift_pressed = False
        event.Skip()

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

    def _list_file_signature(self):
        """图片列表文件(type 3)的内容指纹: 路径 + 字节数 + 修改时间。

        列表文件是用户在外部用编辑器改的, 同一个路径对应的内容随时可能变,
        所以"要不要作废缓存"不能只看路径, 必须带上内容指纹。
        """
        img_mgr = getattr(self, "ImgManager", None)
        if img_mgr is None or getattr(img_mgr, "type", None) != 3:
            return None
        try:
            list_path = Path(str(getattr(img_mgr, "input_path", "")))
            if not list_path.is_file():
                return None
            stat = list_path.stat()
            return (str(list_path), int(stat.st_size), int(stat.st_mtime_ns))
        except Exception:
            return None

    def _reload_list_file_if_changed(self):
        """列表文件在外部被改过 -> 重新读取一遍, 并返回当前指纹。

        场景: 用 "Image File List" 打开 1.txt, 之后在外部改了 1.txt 里的图片路径,
        再重新选择同一个 1.txt (或者直接按刷新) —— 页面必须显示新路径的图片。

        以前 ImgManager 只在第一次 init 时读一次列表, 之后即使重新选择同一个文件
        也不会重读; 再叠加上拼接结果被缓存住, 于是页面看上去"完全没变化"。
        这里用文件指纹(大小+修改时间)判断内容是否变化, 变了就重读。
        """
        signature = self._list_file_signature()
        if signature is None:
            return None
        last = getattr(self, "_list_file_last_signature", None)
        self._list_file_last_signature = signature
        if last is None or last == signature:
            # 第一次拿到指纹(刚 init 完) 或者 文件内容没变 -> 不需要重读
            return signature
        try:
            candidate = copy.copy(self.ImgManager)
            # An image file list remains flat even if a parallel option was
            # left enabled by a previous folder/video input.
            candidate.init(self.ImgManager.input_path, type=3)
            if not len(candidate.path_list):
                return signature
            self.ImgManager.__dict__.update(candidate.__dict__)
            self.ImgManager.set_action_count(0)
            self.shared_config.batch_idx = 0
            self._debug_image(
                f"[ImageList] list file changed, reloaded: {self.ImgManager.input_path}")
        except Exception as ex:
            if getattr(self.shared_config, "debug_image", False):
                print(f"[ImageList] reload list file failed: {ex}")
        return signature

    def show_img_init(self):
        self.ImgManager._algorithm_cache_root=str(self.image_pipeline.processing.visible.root)
        if getattr(self.ImgManager, 'type', None) is None:
            return
        # ★ 图片模式下待应用的 parallel / parallel+sequential 切换在这里统一生效。
        #   勾选开关时不做任何重建（避免切换瞬间就重扫目录 + 重拼接），
        #   而是在下一次真正重绘之前（手动刷新 / 翻页 / 放大框变化等）才应用，
        #   保证数据模型与界面开关始终一致，不会出现 count_per_action 与 flist 错位。
        if (getattr(self, "_parallel_switch_dirty", False)
                and not getattr(self.shared_config, "video_mode", False)):
            self._parallel_switch_dirty = False
            self._apply_parallel_switch_image()

        # ★ 列表文件(type 3)可能在外部被改过: 先比指纹, 变了就重新读取一遍。
        #   这一步放在 set_img_layout() 之前, 保证后面的布局/批数计算用的是最新列表。
        list_signature = self._reload_list_file_if_changed()

        layout_params = self.set_img_layout()
        if not layout_params:
            return
        try:
            registry = capture_algorithms(get_available_algorithms())
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            self.SetStatusText_(['-1', '-1', f'Unable to load custom algorithms: {error}', '-1'])
            return
        self.ImgManager._custom_algorithm_registry = registry
        self.ImgManager._cache_original_paths=tuple(self.shared_config.real_video_path) if self.shared_config.video_mode else ()
        self.ImgManager._cache_input_mode=loaded_input_mode(self.ImgManager,self.shared_config)
        recipe = (registry, layout_params[32], layout_params[37], layout_params[38], layout_params[39])
        if recipe != getattr(self, '_custom_algorithm_recipe', None):
            self._custom_algorithm_recipe = recipe
            self.ImgManager._custom_algorithm_session = AlgorithmSession(registry) if registry is not None else None
            monitor=self.video_manager.perf_monitor
            with monitor._lock:
                monitor.stitch_history.clear();monitor.stitch_by_plan.clear()
            self.video_manager._playback_pacer.reset()
            self.video_manager._pacing_model_period=None
        # ★ 修复：图片模式 + 视频模式 都要在 layout 变化时清空缓存与磁盘缓存文件
        vm = getattr(self, "video_manager", None)
        layout_token = repr((layout_params, hash(registry), tuple(self.ImgManager.gap_color)))
        if not getattr(self.shared_config, "video_mode", False):
            # ★ 缓存 token 里带上列表文件的内容指纹:
            #   以前 token 只有 (布局, 类型, 输入路径), 同一个 1.txt 改内容再重新选择时
            #   token 不变 -> 内存缓存和磁盘 PNG 都不作废 -> 页面还是旧的拼接图。
            image_token = (layout_token, getattr(self.ImgManager, "type", None),
                           repr(getattr(self.ImgManager, "input_path", None)),
                           list_signature)
            if image_token != getattr(self, "_image_layout_token", None):
                with self._image_stitch_lock:
                    self._debug_image(f"[ImageCache] reset, previous_batches={len(self.shared_config.image_cache_img)}")
                    # 清空内存缓存
                    self.shared_config.image_cache_img = []
                    self.shared_config.image_cache_paths = []
                    self._image_layout_token = image_token
                    # Invalidation is state-only; scanning/deleting PNGs stays
                    # on the image coordinator, never under a GUI-held lock.
                    self.image_pipeline.invalidate()
        else:
            # 视频模式：layout 参数变化时清空 cache_img 与磁盘缓存，
            # 避免旧尺寸的拼接帧被后续 show_img/update_cache 错误复用
            if layout_token != getattr(self, "_video_layout_token", None):
                try:
                    if vm is not None:
                        vm._invalidate_stitch_cache()
                    elif not hasattr(self.shared_config, "cache_img") or self.shared_config.cache_img is None:
                        self.shared_config.cache_img = []
                    else:
                        for i in range(len(self.shared_config.cache_img)):
                            self.shared_config.cache_img[i] = None
                except Exception:
                    pass
                # 强制 video_manager 在下次 update_cache 中重建窗口
                self._video_layout_token = layout_token
                try:
                    self._last_refresh_batch = None
                    if vm is not None and hasattr(vm, "_last_batch"):
                        vm._last_batch = None
                except Exception:
                    pass

        count_per_action = getattr(self.shared_config, "count_per_action", 1)
        if self.shared_config.video_mode:
            synced = self._sync_video_count_per_action()
            if synced is not None:
                count_per_action = synced

        if layout_params:
            self.ImgManager.layout_params = layout_params
            self.ImgManager._show_all_func_expanded_row_col = None
            self._image_reference_resolution_origin = None

            # Key: skip generic recompute in video mode to avoid resetting count_per_action back to 1
            if not self.shared_config.video_mode:
                if self.ImgManager.type == 0 or self.ImgManager.type == 1:
                    if self.parallel_to_sequential.Value:
                        count_per_action = (
                            layout_params[0][0] * layout_params[0][1] *
                            layout_params[1][0] * layout_params[1][1]
                        )
                    else:
                        if self.parallel_sequential.Value:
                            count_per_action = layout_params[1][0] * layout_params[1][1]
                        else:
                            count_per_action = 1
                elif self.ImgManager.type == 2 or self.ImgManager.type == 3:
                    count_per_action = (
                        layout_params[0][0] * layout_params[0][1] *
                        layout_params[1][0] * layout_params[1][1]
                    )

            self.ImgManager.set_count_per_action(count_per_action)

        self.shared_config.count_per_action = count_per_action
        return True


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
                             self.title_exif.Value,                     # 11
                             self.title_show_rename.Value]              # 12

            if title_setting[0]:
                title_setting[2:7] = auto_title_fields(
                    self.ImgManager.type, self.shared_config.video_mode,
                    len(self.shared_config.real_video_path),
                    self.parallel_to_sequential.Value, self.parallel_sequential.Value)
        except:
            self.SetStatusText_(
                ["-1", "-1", "***Error: setting***", "-1"])
            return False
        else:
            params=[row_col,                                # 0
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
                    self.show_unit.Value,                   # 36
                    self.customfunc_choice.GetSelection(),  # 37
                    self.show_all_func.Value,               # 38
                    self.show_all_func_layout.Value,        # 39
                    self.func_layout_vertical.Value ]       # 40
            if getattr(self,'_custom_settings_dirty',False) and len(self.ImgManager.layout_params)>40:
                for index in (32,36,37,38,39,40):params[index]=self.ImgManager.layout_params[index]
            return params

    def show_img(self, preserve_text_value=False):
        pending = getattr(self, '_pending_index_selection', None)
        if pending and pending['page'] != int(self.shared_config.batch_idx):
            self._pending_index_selection = None
        self._setup_img_panel()

        # ========== 视频模式 ==========
        if getattr(self.shared_config, "video_mode", False):
            b = int(self.shared_config.batch_idx)

            # 从磁盘加载图像（cache_entry 现在是文件路径字符串）
            # ★ 走 _video_cached_batch_path: 磁盘缓存按窗口清理过, 内存里记下的路径
            #   可能已经失效, 这里统一判定为"无缓存", 交给下面的重建流程, 避免 Load cache failed。
            cache_entry = self._video_cached_batch_path(b)

            # 当前批次未就绪且暂停时，安排后台重建；完成回调负责显示。
            #   典型场景：从图片模式切到视频模式、或刚选完视频时，
            #   show_img_init() 会因布局参数变化清空视频缓存，
            #   导致首帧缺失而一直停在 "Waiting for batch N"，必须手动刷新才恢复。
            if cache_entry is None and not getattr(self.shared_config, "is_playing", False):
                cache_entry = self._rebuild_video_cache_for_batch(b)

            if cache_entry is not None:
                # cache_entry 是文件路径字符串
                try:
                    self.shared_config.video_last_message = ""
                    self._request_video_display(b, cache_entry)

                    # 更新状态栏（保留 FPS 计算逻辑，但不显示）
                    self.SetStatusText_(["-1", "-1", "", "-1"])

                    # 更新滑块
                    if hasattr(self, "slider_img") and self.slider_img:
                        try:
                            max_val = max(0, self.ImgManager.max_action_num - 1)
                            self.slider_img.SetRange(1, max_val + 1)
                            self.slider_img.SetValue(b + 1)
                        except Exception:
                            pass

                    # 更新页数文本框
                    if hasattr(self, "slider_value") and self.slider_value:
                        try:
                            self.slider_value.ChangeValue(str(b + 1))
                        except Exception:
                            pass
                    if hasattr(self, "slider_value_max") and self.slider_value_max:
                        try:
                            self.slider_value_max.SetLabel(str(max(1, self.ImgManager.max_action_num)))
                        except Exception:
                            pass

                    self._cancel_pending_frame_wait()

                except Exception as ex:
                    self.SetStatusText_(["-1", "-1", f"***Load cache failed: {ex}***", "-1"])
            else:
                # 缓存未就绪
                msg = getattr(self.shared_config, "video_last_message", "")
                if not msg:
                    msg = f"Waiting for batch {b}..."

                self.SetStatusText_(["Waiting", "-1", msg, "-1"])

                # 更新滑块
                if hasattr(self, "slider_img") and self.slider_img:
                    try:
                        max_val = max(0, self.ImgManager.max_action_num - 1)
                        self.slider_img.SetRange(1, max_val + 1)
                        self.slider_img.SetValue(b + 1)
                    except Exception:
                        pass

                # 更新页数文本框
                if hasattr(self, "slider_value") and self.slider_value:
                    try:
                        self.slider_value.ChangeValue(str(b + 1))
                    except Exception:
                        pass
                if hasattr(self, "slider_value_max") and self.slider_value_max:
                    try:
                        self.slider_value_max.SetLabel(str(max(1, self.ImgManager.max_action_num)))
                    except Exception:
                        pass

                # 如果是播放模式，调度等待回调
                if getattr(self.shared_config, "is_playing", False):
                    self._schedule_frame_wait()

            # 清除可能残留的 "frame batch" 文本（第1列）
            self.m_statusBar1.SetStatusText("", 1)
            return

        # ========== 图片模式：后台拼接、磁盘缓存、后台准备显示 ==========
        if self.ImgManager.max_action_num > 0:
            current_batch = max(0, min(int(getattr(self.shared_config, "batch_idx", 0)),
                                       self.ImgManager.max_action_num - 1))
            self.shared_config.batch_idx = current_batch

            # 更新滑块位置、最大值和文本框
            if hasattr(self, "slider_img") and self.slider_img:
                try:
                    max_val = max(0, self.ImgManager.max_action_num - 1)
                    self.slider_img.SetRange(1, max_val + 1)
                    if self.slider_img.GetValue() != current_batch + 1:
                        self.slider_img.SetValue(current_batch + 1)
                except Exception:
                    pass
            # 只在不需要保留文本框值时才更新
            if hasattr(self, "slider_value") and self.slider_value and not preserve_text_value:
                try:
                    self.slider_value.ChangeValue(str(current_batch + 1))
                except Exception:
                    pass
            if hasattr(self, "slider_value_max") and self.slider_value_max:
                try:
                    self.slider_value_max.SetLabel(str(max(1, self.ImgManager.max_action_num)))
                except Exception:
                    pass

            # 更新图片缓存
            self._update_image_cache(current_batch)

            if self.shared_config.is_playing:
                self._suspend_play_timer_for_wait()
            if not self.image_pipeline.prepare_display(current_batch, self._deliver_image_frame):
                self.SetStatusText_(["Waiting", "-1",
                    f"Waiting for batch {current_batch}...", "-1"])
            elif self.image_pipeline.displayed_key is not None:
                if self.image_pipeline.displayed_key[1] == current_batch:
                    self._resume_play_timer_after_wait()
        else:
            # 无图像数据
            self.SetStatusText_(["-1", "-1", "No images", "-1"])

    def _get_image_flist(self, batch_idx: int):
        count = max(1, self.ImgManager.count_per_action)
        orig_action = self.ImgManager.action_count
        orig_img_count = getattr(self.ImgManager, "img_count", 0)
        orig_flist = getattr(self.ImgManager, "flist", None)

        try:
            self.ImgManager.action_count = batch_idx
            self.ImgManager.img_count = batch_idx * count
            flist = self.ImgManager.get_flist()
            return list(flist) if flist else []
        finally:
            self.ImgManager.action_count = orig_action
            self.ImgManager.img_count = orig_img_count
            if orig_flist is not None:
                self.ImgManager.flist = orig_flist

    def _update_image_cache(self, batch_idx: int):
        if self.ImgManager.max_action_num <= 0:
            return
        self._apply_resource_policy()
        # Snapshot GUI inputs once per render context. Each batch then clones
        # this template without copying dataset filenames or touching live state.
        context = (getattr(self, '_image_layout_token', None),
                   id(self.shared_config.image_cache_img),
                   id(self.ImgManager.name_list), id(self.ImgManager.path_list),
                   repr(self.xy_magnifier), bool(self.ImgManager.layout_params[32]))
        if context != getattr(self, '_image_snapshot_key', None):
            self._image_snapshot_key = context
            self._image_snapshot = self.ImgManager.video_stitch_snapshot()
        self.image_pipeline.request(self._image_snapshot, copy.deepcopy(self.xy_magnifier),
            bool(self.ImgManager.layout_params[32]), context, batch_idx,
            self.ImgManager.max_action_num, self.shared_config.cache_num,
            self.shared_config.cache_multiplier, self.shared_config.thread,
            self.shared_config.memory_budget, self.shared_config.play_direction)

    def _image_frame_ready(self, batch, generation, error=None):
        if (getattr(self, '_is_closing', False) or self.shared_config.video_mode
                or generation != self.image_pipeline.generation
                or batch != int(self.shared_config.batch_idx)):
            return
        self._show_resource_tooltip()
        if error:
            self.SetStatusText_(['-1', '-1', f'***{error}***', '-1'])
            self._resume_play_timer_after_wait()
            return
        self.image_pipeline.prepare_display(batch, self._deliver_image_frame)

    def _deliver_image_frame(self, batch, generation, pixels, state, error):
        if (getattr(self, '_is_closing', False) or self.shared_config.video_mode
                or generation != self.image_pipeline.generation
                or batch != int(self.shared_config.batch_idx)):
            return
        if error:
            self.SetStatusText_(['-1', '-1', f'***Load cache failed: {error}***', '-1'])
            return
        image, rgba = pixels
        for name, value in state.items():
            setattr(self.ImgManager, name, value)
        self.ImgManager.img = image
        self.ImgManager.action_count = batch
        self.ImgManager.img_count = batch * self.ImgManager.count_per_action
        self.current_page_img_paths = copy.deepcopy(state.get('flist', []))
        self.show_bmp_in_panel, self.img_size = image, image.size
        self.display_bitmap(False, image, prepared_rgba=rgba)
        if self.shared_config.is_playing:
            self.resource_monitor.frame_presented(batch, self.shared_config.play_direction)
        self._status_display_batch = batch
        self._apply_pending_index_selection()
        self.update_status_bar_for_current_page()
        self._show_resource_tooltip()
        self._resume_play_timer_after_wait()

    def _compact_row_col_for_count(self, count):
        if count <= 1:
            return [1, 1]
        row = int(math.sqrt(count))
        while row > 1 and count % row != 0:
            row -= 1
        col = int(math.ceil(count / row))
        return [min(row, col), max(row, col)]

    def _calc_reference_resolution_origin(self, flist):
        widths = []
        heights = []
        for path in flist:
            try:
                with Image.open(path) as img:
                    widths.append(img.size[0])
                    heights.append(img.size[1])
            except Exception:
                pass
        if not widths or not heights:
            return None

        widths = np.sort(widths)
        heights = np.sort(heights)
        if self.ImgManager.img_stitch_mode == 2:
            width = max(widths)
            height = max(heights)
        elif self.ImgManager.img_stitch_mode == 1:
            width = np.min(widths)
            height = np.min(heights)
        else:
            if len(widths) > 3:
                width = np.mean(widths[1:-1])
                height = np.mean(heights[1:-1])
            else:
                width = np.mean(widths)
                height = np.mean(heights)
        return [int(width), int(height)]

    def compose_current_frame(self, batch_idx=0, flist=None):
        """
        Only generate the stitched result for the current frame; do not touch UI state.
        Returns: (pil_img, flag)
        - pil_img: PIL.Image or None
        - flag: 0 means success; other values follow ImgManager.stitch_images semantics
        """
        original_row_col = None
        original_resolution_setting = None
        full_capacity = None
        try:
            if flist is not None and not getattr(self.shared_config, "video_mode", False):
                row_col = self.ImgManager.layout_params[0]
                row_col_one_img = self.ImgManager.layout_params[1]
                one_img_capacity = max(1, row_col_one_img[0] * row_col_one_img[1])
                full_capacity = max(1, row_col[0] * row_col[1] * one_img_capacity)
                # 【修复】禁用自动压缩：原本当 len(flist) < full_capacity 时会强制用最小包围盒
                # 改写 RowCol（例如 3 张图 + RowCol=2,2 → 被改成 [1,3]），
                # 导致用户在 parallel manual / 末尾 batch 等场景无法使用自己设置的布局。
                # 这里直接关闭该压缩逻辑，UI 上设的 RowCol 永远生效。
                if False and 0 < len(flist) < full_capacity:
                    original_row_col = row_col.copy()
                    compact_count = int(math.ceil(len(flist) / one_img_capacity))
                    self.ImgManager.layout_params[0] = self._compact_row_col_for_count(compact_count)
                    self.ImgManager._show_all_func_expanded_row_col = None

                    resolution_setting = self.ImgManager.layout_params[6]
                    if -1 in resolution_setting:
                        reference_resolution = getattr(self, "_image_reference_resolution_origin", None)
                        if reference_resolution is None:
                            reference_flist = self._get_image_flist(0)
                            if len(reference_flist) >= full_capacity:
                                reference_resolution = self._calc_reference_resolution_origin(
                                    reference_flist[:full_capacity])
                        if reference_resolution is not None:
                            original_resolution_setting = resolution_setting.copy()
                            self.ImgManager.layout_params[6] = reference_resolution

            if self.show_custom_func.Value:
                self.ImgManager.layout_params[32] = True
                self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier), flist=flist)
                self.ImgManager.layout_params[32] = False

            stitch_start = time.time()
            flag = self.ImgManager.stitch_images(0, copy.deepcopy(self.xy_magnifier), flist=flist)
            stitch_duration = time.time() - stitch_start
            if flag != 0:
                return None, flag

            pil_img = self.ImgManager.show_stitch_img_and_customfunc_img(self.show_custom_func.Value)
            if (flist is not None and full_capacity is not None
                    and len(flist) >= full_capacity and -1 in self.ImgManager.layout_params[6]):
                self._image_reference_resolution_origin = self.ImgManager.img_resolution_origin.copy()
        finally:
            if original_resolution_setting is not None:
                self.ImgManager.layout_params[6] = original_resolution_setting
            if original_row_col is not None:
                self.ImgManager.layout_params[0] = original_row_col
                self.ImgManager._show_all_func_expanded_row_col = None

        self.show_bmp_in_panel = pil_img
        self.img_size = pil_img.size

        video_mode = getattr(self.shared_config, "video_mode", False)
        cache_list = self.shared_config.cache_img if video_mode else self.shared_config.image_cache_img
        path_cache = self.shared_config.image_cache_paths if not video_mode else None
        need = batch_idx + 1 - len(cache_list)
        if need > 0:
            cache_list.extend([None] * need)
            if path_cache is not None:
                path_cache.extend([None] * need)
        cache_list[batch_idx] = pil_img

        if not video_mode:
            store_list = flist if flist is not None else getattr(self.ImgManager, "flist", None)
            if path_cache is not None:
                path_cache[batch_idx] = list(store_list) if store_list else None

        if video_mode:
            vm = getattr(self, "video_manager", None)
            if vm and pil_img is not None:
                vm.perf_monitor.record_stitch(stitch_duration)

        return pil_img, 0

    #b3 修改3：display_bitmap —— 移除 Thaw 后多余的 Refresh，以及视频播放时跳过重复 layout
    # def display_bitmap(self, video_mode, pil_img):
    #     dbg_batch = int(getattr(self.shared_config, "batch_idx", -1))
    #
    #     if pil_img is None and video_mode:
    #         cache = getattr(self.shared_config, "cache_img", [])
    #         b = int(getattr(self.shared_config, "batch_idx", 0))
    #         if not (0 <= b < len(cache)) or cache[b] is None:
    #             return
    #         pil_img = cache[b]
    #
    #     try:
    #         if video_mode and pil_img is not None:
    #             arr = np.array(pil_img.convert("RGBA"), dtype=np.uint8)
    #
    #             bg_rgb = np.array(self.ImgManager.gap_color[:3], dtype=np.int16)
    #             rgb = arr[:, :, :3].astype(np.int16)
    #             alpha = arr[:, :, 3].astype(np.int16)
    #
    #             tol = 6
    #             alpha_min = 8
    #
    #             diff = np.max(np.abs(rgb - bg_rgb), axis=2)
    #             content = (diff > tol) & (alpha > alpha_min)
    #
    #             if np.any(content):
    #                 h, w = content.shape
    #                 row_hits = content.sum(axis=1)
    #                 col_hits = content.sum(axis=0)
    #
    #                 row_thr = max(12, int(w * 0.01))
    #                 col_thr = max(12, int(h * 0.01))
    #
    #                 ys_thr = np.where(row_hits > row_thr)[0]
    #                 xs_thr = np.where(col_hits > col_thr)[0]
    #
    #                 ys_any = np.where(content.any(axis=1))[0]
    #                 xs_any = np.where(content.any(axis=0))[0]
    #
    #                 if ys_any.size > 0 and xs_any.size > 0:
    #                     y0 = int(ys_thr[0]) if ys_thr.size > 0 else int(ys_any[0])
    #                     x0 = int(xs_thr[0]) if xs_thr.size > 0 else int(xs_any[0])
    #
    #                     y1 = int(ys_any[-1]) + 1
    #                     x1 = int(xs_any[-1]) + 1
    #
    #                     arr = arr[y0:y1, x0:x1]
    #                     pil_img = Image.fromarray(arr, mode="RGBA")
    #     except Exception:
    #         pass
    #
    #     bmp = self.ImgManager.ImgF.PIL2wx(pil_img)
    #     self._set_placeholder_visible(False)
    #
    #     if hasattr(self, "img_last") and self.img_last:
    #         self.img_last.SetBitmap(bmp)
    #     else:
    #         self.img_last = wx.StaticBitmap(self.img_panel, bitmap=bmp)
    #     self._ensure_img_bindings()
    #
    #     if not hasattr(self, "img_panel_sizer"):
    #         self.img_panel_sizer = wx.BoxSizer(wx.VERTICAL)
    #         self.img_panel.SetSizer(self.img_panel_sizer)
    #     else:
    #         try:
    #             self.img_panel_sizer.Clear(False)
    #         except Exception:
    #             pass
    #
    #     self.img_panel_sizer.Add(self.img_last, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP, 0)
    #
    #     # Key fix: use PIL logical size for layout, not bmp.GetSize() HiDPI physical pixels
    #     logical_w, logical_h = pil_img.size
    #     logical_size = wx.Size(int(logical_w), int(logical_h))
    #
    #     self.img_last.SetPosition((0, 0))
    #     self.img_last.SetSize(logical_size)
    #     self.img_last.SetMinSize(logical_size)
    #
    #     self.img_panel.SetPosition((0, 0))
    #     self.img_panel.SetSize(logical_size)
    #     self.img_panel.SetMinSize(logical_size)
    #
    #     try:
    #         self.scrolledWindow_img.Freeze()
    #     except Exception:
    #         pass
    #
    #     self.img_panel.Layout()
    #     self.scrolledWindow_img.Layout()
    #     self.scrolledWindow_img.SetVirtualSize(logical_size)
    #     self.scrolledWindow_img.Scroll(0, 0)
    #     self.position = [0, 0]
    #
    #     try:
    #         self.scrolledWindow_img.Thaw()
    #     except Exception:
    #         pass
    #
    #     wx.CallAfter(self.scrolledWindow_img.Scroll, 0, 0)
    #     self.scrolledWindow_img.Refresh()

    def display_bitmap(self, video_mode, pil_img, prepared_rgba=None):
        dbg_batch = int(getattr(self.shared_config, "batch_idx", -1))

        if pil_img is None and video_mode:
            cache = getattr(self.shared_config, "cache_img", [])
            b = int(getattr(self.shared_config, "batch_idx", 0))
            if not (0 <= b < len(cache)) or cache[b] is None:
                return
            pil_img = cache[b]

        # Display the full canvas, including configured blank layout slots.
        # Source selection and index coordinates use this same canvas origin.
        logical_w, logical_h = pil_img.size
        logical_size = wx.Size(int(logical_w), int(logical_h))

        # ★ 判断尺寸是否变化，不变则跳过整个 sizer/layout 重建
        last_size = getattr(self, "_last_display_logical_size", None)
        size_changed = (last_size != logical_size)
        self._last_display_logical_size = logical_size

        # ★ Freeze 必须在一切 layout 操作之前，否则无效
        bmp = (wx.Bitmap.FromBufferRGBA(logical_w, logical_h, prepared_rgba)
               if prepared_rgba is not None else self.ImgManager.ImgF.PIL2wx(pil_img))
        frozen = False
        try:
            if size_changed:
                self.scrolledWindow_img.Freeze()
                frozen = True
        except Exception:
            pass

        self._set_placeholder_visible(False)

        if hasattr(self, "img_last") and self.img_last:
            self.img_last.SetBitmap(bmp)
        else:
            self.img_last = wx.StaticBitmap(self.img_panel, bitmap=bmp)
            size_changed = True  # 新控件必须走一次完整 layout
        self._ensure_img_bindings()

        if size_changed:
            # 只在尺寸变化时才重建 sizer 和 layout
            if not hasattr(self, "img_panel_sizer"):
                self.img_panel_sizer = wx.BoxSizer(wx.VERTICAL)
                self.img_panel.SetSizer(self.img_panel_sizer)
            else:
                try:
                    self.img_panel_sizer.Clear(False)
                except Exception:
                    pass
            self.img_panel_sizer.Add(self.img_last, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP, 0)

            self.img_last.SetPosition((0, 0))
            self.img_last.SetSize(logical_size)
            self.img_last.SetMinSize(logical_size)

            self.img_panel.SetPosition((0, 0))
            self.img_panel.SetSize(logical_size)
            self.img_panel.SetMinSize(logical_size)

            self.img_panel.Layout()
            self.scrolledWindow_img.Layout()
            self.scrolledWindow_img.SetVirtualSize(logical_size)
            self.scrolledWindow_img.Scroll(0, 0)

        self.position = [0, 0]

        try:
            if frozen:
                self.scrolledWindow_img.Thaw()
        except Exception:
            pass
        # ★ 删除 Refresh()：Thaw() 本身触发延迟重绘，再调 Refresh() 造成第二次绘制
        # ★ 删除 CallAfter(Scroll, 0,0)：show_img 里已有此调用，不需要在这里重复

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
        if not getattr(self.shared_config, "video_mode", False):
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

    def about_gui(self, event, update=False, new_version=None):
        self.aboutgui = About(self, self.version,
                              update=update, new_version=new_version)
        self.aboutgui.Show(True)

    def index_table_gui(self, event):
        if not self.ImgManager.img_num:
            self.SetStatusText_(["-1", "", "First select an input", "-1"])
            return
        if self.indextablegui:
            self.indextablegui.Close()
        def catalog():
            model = IndexCatalog(self.ImgManager, self.shared_config, self.parallel_sequential.Value)
            model.context = self._index_context()
            return model
        self.indextablegui = IndexTable(self, catalog(), self.out_path_str,
            on_jump=lambda batch: self._jump_to_index_item(batch), refresh=catalog,
            on_jump_item=self._jump_to_index_item, on_locate=self._index_location,
            auto_export=bool(self.ImgManager.dataset_mode and self.out_path_str))

    def _debug_image(self, message):
        if getattr(self.shared_config, "debug_image", False):
            print(message)

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

    def title_rename_fc(self, event):
        if hasattr(self.ImgManager, 'layout_params') and len(self.ImgManager.layout_params) > 17:
            if len(self.ImgManager.layout_params[17]) > 12:
                self.ImgManager.layout_params[17][12] = self.title_show_rename.Value

    def title_auto_fc(self, event):
        titles = [self.title_down_up, self.title_show_parent,
                  self.title_show_name, self.title_show_suffix, self.title_show_prefix,
                  self.title_position, self.title_exif, self.m_checkBox31, self.m_textCtrl16]
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
                self._invalidate_render_cache()
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

    def _bind_settings_wheel_guard(self):
        # Controls that should handle the wheel event.
        swallow_types = (wx.Choice, wx.ComboBox, wx.SpinCtrl, wx.SpinCtrlDouble)

        # Reroute wheel events back to the settings scrolled window.
        def reroute_wheel(event):
            clone = event.Clone()
            clone.SetEventObject(self.scrolledWindow_set)
            clone.ResumePropagation(wx.EVENT_PROPAGATE_MAX)
            self.scrolledWindow_set.GetEventHandler().ProcessEvent(clone)

        # Recursively bind wheel rerouting on relevant child controls.
        def walk(win):
            for child in win.GetChildren():
                if isinstance(child, swallow_types):
                    child.Bind(wx.EVT_MOUSEWHEEL, reroute_wheel)
                if child.GetChildren():
                    walk(child)

        walk(self.scrolledWindow_set)


    def add_custom_algorithm(self, event):
        algorithm_path = self.custom_algorithm_input.GetValue().strip()
        if not algorithm_path:
            event.Skip() if hasattr(event, "Skip") else None
            return

        source_path = Path(algorithm_path)
        if not source_path.exists():
            wx.MessageBox(f"Path does not exist: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
            return
        if not source_path.is_dir():
            wx.MessageBox(f"Path must be a folder: {algorithm_path}", "Path Error", wx.OK | wx.ICON_ERROR)
            return
        if not (source_path / "main.py").exists():
            wx.MessageBox(f"main.py file missing in algorithm folder: {algorithm_path}", "File Missing", wx.OK | wx.ICON_ERROR)
            return

        algorithm_name = source_path.name
        existing = [self.customfunc_choice.GetString(i) for i in range(self.customfunc_choice.GetCount())]
        if algorithm_name in existing:
            wx.MessageBox(f"Algorithm '{algorithm_name}' already exists!", "Duplicate Algorithm", wx.OK | wx.ICON_WARNING)
            return

        try:
            self.copy_algorithm_from_path(source_path, algorithm_name)
            self._clear_custom_algorithm_modules()
            self.refresh_algorithm_list()
            available_algorithms = get_available_algorithms()
            if algorithm_name in available_algorithms:
                self.customfunc_choice.SetSelection(available_algorithms.index(algorithm_name))
            self.custom_algorithm_input.SetValue("")
            self._custom_settings_changed()
            self.Layout()
            wx.MessageBox(f"Algorithm '{algorithm_name}' added successfully!", "Add Success", wx.OK | wx.ICON_INFORMATION)
        except Exception as exc:
            wx.MessageBox(f"Failed to add algorithm: {exc}", "Add Failed", wx.OK | wx.ICON_ERROR)

    def copy_algorithm_from_path(self, source_path, algorithm_name):
        target_folder = Path(__file__).parent / "custom_func" / algorithm_name
        if target_folder.exists():
            shutil.rmtree(str(target_folder))
        shutil.copytree(str(source_path), str(target_folder))

    def _clear_custom_algorithm_modules(self):
        compiled_source.cache_clear()

    def remove_custom_algorithm(self, event):
        selected_index = self.customfunc_choice.GetSelection()
        if selected_index == wx.NOT_FOUND:
            wx.MessageBox("Please select an algorithm to remove first!", "No Algorithm Selected", wx.OK | wx.ICON_WARNING)
            return

        selected_algorithm = self.customfunc_choice.GetString(selected_index)
        dlg = wx.MessageDialog(
            self,
            f"Are you sure you want to remove algorithm '{selected_algorithm}'?",
            "Confirm Removal",
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if dlg.ShowModal() == wx.ID_YES:
            try:
                self.remove_custom_algorithm_folder(selected_algorithm)
                self._clear_custom_algorithm_modules()
                self.refresh_algorithm_list()
                self._custom_settings_changed()
                wx.MessageBox(f"Algorithm '{selected_algorithm}' removed successfully!", "Remove Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as exc:
                wx.MessageBox(f"Failed to remove algorithm: {exc}", "Remove Failed", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def remove_custom_algorithm_folder(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        if algorithm_folder.exists():
            shutil.rmtree(str(algorithm_folder))

    def create_custom_algorithm_template(self, algorithm_name):
        algorithm_folder = Path(__file__).parent / "custom_func" / algorithm_name
        desktop_algorithm_folder = Path.home() / "Desktop" / algorithm_name
        if desktop_algorithm_folder.exists() and (desktop_algorithm_folder / "main.py").exists():
            try:
                if algorithm_folder.exists():
                    shutil.rmtree(str(algorithm_folder))
                shutil.copytree(str(desktop_algorithm_folder), str(algorithm_folder))
                return
            except Exception:
                pass
        if not algorithm_folder.exists():
            os.makedirs(str(algorithm_folder))
        template_content = f"""'''
{algorithm_name} Algorithm
Custom algorithm - Implement your image processing logic here
'''
from PIL import Image
from pathlib import Path
import os

def custom_process_img(img):
    \"\"\"
    Custom image processing function
    input: image(pillow)
    output: image(pillow)

    Implement your image processing algorithm here
    Examples:
    - img = img.convert('L')  # Convert to grayscale
    - img = img.transpose(Image.FLIP_LEFT_RIGHT)  # Horizontal flip
    \"\"\"
    return img

def main(img_list, save_path, name_list=None, algorithm_name="{algorithm_name}"):
    \"\"\"
    Batch process image list
    \"\"\"
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        save_path = Path(save_path) / "algorithms" / algorithm_name / "processed"
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        img = custom_process_img(img)

        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list) and i < len(name_list):
                img_path = save_path / name_list[i]
            else:
                img_path = save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
"""
        template_path = algorithm_folder / "main.py"
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template_content)

    def refresh_algorithm_list(self):
        try:
            self._clear_custom_algorithm_modules()
            available_algorithms = get_available_algorithms()
            current_selection = self.customfunc_choice.GetSelection()
            current_algorithm = ""
            if current_selection != wx.NOT_FOUND:
                current_algorithm = self.customfunc_choice.GetString(current_selection)
            self.customfunc_choice.Clear()
            for algorithm in available_algorithms:
                self.customfunc_choice.Append(algorithm)
            if current_algorithm and current_algorithm in available_algorithms:
                self.customfunc_choice.SetSelection(available_algorithms.index(current_algorithm))
            elif available_algorithms:
                self.customfunc_choice.SetSelection(0)
        except Exception:
            pass

    def on_show_all_func_changed(self, event):
        if self.show_all_func.GetValue():
            self.show_custom_func.SetValue(False)
        self._custom_settings_changed(event,defer=True)

    def on_show_custom_func_changed(self, event):
        if self.show_custom_func.GetValue():
            self.show_all_func.SetValue(False)
        self._custom_settings_changed(event,defer=True)

    def _custom_settings_changed(self, event=None,defer=False):
        if event is not None or defer:
            self._custom_settings_dirty=True
            self.SetStatusText_(['-1','-1','Algorithm settings changed; press Refresh to apply','-1'])
            return
        self._custom_settings_dirty=False
        self._invalidate_render_cache()
        if getattr(self.ImgManager, 'type', None) is not None:
            if self.show_img_init():
                self.show_img()

    #b3 修改1：next_img 和 last_img —— timer 播放时跳过 show_img_init    b5
    def next_img(self, event):
        if self.shared_config.video_mode and self.shared_config.is_playing and not getattr(self, "_from_timer", False):
            self.shared_config.play_direction = 1
            self.last_direction = self.shared_config.play_direction
            return
        if (not self.shared_config.video_mode and
                self.shared_config.is_playing and
                not getattr(self, "_from_timer", False)):
            self.shared_config.play_direction = 1
            self.last_direction = 1
            return

        max_batch_idx = self.ImgManager.max_action_num - 1
        if self.shared_config.batch_idx >= max_batch_idx:
            if getattr(self.shared_config, "is_playing", False):
                self.shared_config.is_playing = False
                try:
                    self.play_timer.Stop()
                except Exception:
                    pass
                try:
                    self.right_arrow_button1.SetLabel("▶")
                except Exception:
                    pass
                self.shared_config.play_direction = 1
                self.last_direction = 1
            return

        if self.shared_config.video_mode:
            if self.shared_config.is_playing:
                self.shared_config.play_direction = 1
            self.last_direction = self.shared_config.play_direction
            if self.shared_config.batch_idx < int(self.ImgManager.img_num) - 1:
                self.shared_config.batch_idx += 1

            # ★ 修改：异步更新缓存，让UI立即响应而不是阻塞
            wx.CallAfter(self.video_manager.update_cache)

        if getattr(self.ImgManager, "img_count", 0) < int(self.ImgManager.img_num) - 1:
            self.ImgManager.add()

        self.shared_config.batch_idx = min(self.shared_config.batch_idx, self.ImgManager.max_action_num - 1)
        if not self.shared_config.video_mode:
            self.shared_config.batch_idx = min(self.ImgManager.action_count, self.ImgManager.max_action_num - 1)

        if not getattr(self, "_from_timer", False):
            self.show_img_init()

        self.show_img()
        self.SetStatusText_(["Next", "-1", "-1", "-1"])

    def _setup_img_panel(self):
        # Prevent white-background flicker during repaint
        if getattr(self, "_img_panel_ready", False):
            return
        pnl = self.img_panel
        pnl.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        pnl.SetDoubleBuffered(True)
        pnl.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self._img_panel_ready = True

    def _set_placeholder_visible(self, visible: bool):
        if not hasattr(self, "m_staticText1") or not self.m_staticText1:
            return
        if getattr(self, '_placeholder_visible', None) == bool(visible):
            return
        try:
            if visible:
                self.m_staticText1.Show()
            else:
                self.m_staticText1.Hide()
            self.scrolledWindow_img.GetSizer().Layout()
            self.scrolledWindow_img.Layout()
            self._placeholder_visible = bool(visible)
        except Exception:
            pass

    def _reset_image_view_origin(self):
        try:
            self.position = [0, 0]
            self.scrolledWindow_img.Scroll(0, 0)
        except Exception:
            pass

    def _ensure_img_bindings(self):
        if not getattr(self, "img_last", None):
            return
        if getattr(self, '_img_bindings_target', None) is self.img_last:
            return
        self.img_last.Bind(wx.EVT_LEFT_DOWN, self.img_left_click)
        self.img_last.Bind(wx.EVT_LEFT_DCLICK, self.img_left_dclick)
        self.img_last.Bind(wx.EVT_MOTION, self.img_left_move)
        self.img_last.Bind(wx.EVT_LEFT_UP, self.img_left_release)
        self.img_last.Bind(wx.EVT_RIGHT_DOWN, self.img_right_click)
        self.img_last.Bind(wx.EVT_MOUSEWHEEL, self.img_wheel)
        self.img_last.Bind(wx.EVT_KEY_DOWN, self.key_down_detect)
        self.img_last.Bind(wx.EVT_KEY_UP, self.key_up_detect)
        self._img_bindings_target = self.img_last

    def disable_accel(self, event):
        self.SetAcceleratorTable(wx.NullAcceleratorTable)
        event.Skip()

    def enable_accel(self, event):
        self.SetAcceleratorTable(self.acceltbl)
        event.Skip()
