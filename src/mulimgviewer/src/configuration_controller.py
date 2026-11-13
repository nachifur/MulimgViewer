"""GUI configuration, session restoration, window geometry and hotkey handling."""
from pathlib import Path
import wx
from .path_select import on_video_mode_change
from .utils import get_resource_path
from .configuration import (settings_controls, control_value, apply_value,
                            synchronize, read_config, write_config, merge_missing)
import json


class ConfigurationMixin:
    """GUI configuration lifecycle; never owns playback workers or caches."""

    def _save_window_state(self):
        try:
            if self.IsMaximized():
                x, y = self._normal_window_pos
                w, h = self._normal_window_size
                maximized = True
            else:
                pos = self.GetPosition()
                size = self.GetSize()
                x, y = pos[0], pos[1]
                w, h = size[0], size[1]
                maximized = False
            if self.output_config_path.exists():
                with open(self.output_config_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            else:
                data = {}
            data["window_state"] = {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "maximized": maximized,
            }
            write_config(self.output_config_path, data)
        except Exception:
            pass


    def _restore_window_state(self):
        if not self.output_config_path.exists():
            return
        try:
            with open(self.output_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            window_state = data.get("window_state")
            if not isinstance(window_state, dict):
                return
            x = int(window_state["x"])
            y = int(window_state["y"])
            w = int(window_state["w"])
            h = int(window_state["h"])
            maximized = bool(window_state.get("maximized", False))
            self.SetSize((w, h))
            self.SetPosition((x, y))
            self._normal_window_pos = (x, y)
            self._normal_window_size = (w, h)
            if maximized:
                wx.CallAfter(self.Maximize, True)
        except Exception:
            pass


    def get_default_hotkeys(self):
        return {
            "next_img": "CTRL+N",
            "last_img": "CTRL+L",
            "save_img": "CTRL+S",
            "refresh": "CTRL+R",
            "hidden": "CTRL+H",
            "move_up": "UP",
            "move_down": "DOWN",
            "move_left": "LEFT",
            "move_right": "RIGHT",
            "delete_box": "DELETE",
        }


    def parse_hotkey(self, key_name):
        if key_name is None:
            return None
        tokens = [token.strip().upper() for token in str(key_name).split("+") if token.strip()]
        if not tokens:
            return None
        key_token = tokens[-1]
        modifier_tokens = tokens[:-1]
        modifier_map = {
            "CTRL": wx.ACCEL_CTRL,
            "CONTROL": wx.ACCEL_CTRL,
            "ALT": wx.ACCEL_ALT,
            "SHIFT": wx.ACCEL_SHIFT,
        }
        modifiers = wx.ACCEL_NORMAL
        used_modifiers = set()
        for token in modifier_tokens:
            if token not in modifier_map or token in used_modifiers:
                return None
            used_modifiers.add(token)
            modifiers |= modifier_map[token]
        special_keys = {
            "UP": wx.WXK_UP,
            "ARROWUP": wx.WXK_UP,
            "DOWN": wx.WXK_DOWN,
            "ARROWDOWN": wx.WXK_DOWN,
            "LEFT": wx.WXK_LEFT,
            "ARROWLEFT": wx.WXK_LEFT,
            "RIGHT": wx.WXK_RIGHT,
            "ARROWRIGHT": wx.WXK_RIGHT,
            "DELETE": wx.WXK_DELETE,
        }
        if key_token in special_keys:
            keycode = special_keys[key_token]
        elif len(key_token) == 1 and "A" <= key_token <= "Z":
            keycode = ord(key_token)
        else:
            return None
        return modifiers, keycode


    def normalize_hotkeys(self, hotkeys):
        defaults = self.get_default_hotkeys()
        if not isinstance(hotkeys, dict):
            return defaults.copy()
        normalized = defaults.copy()
        for action in defaults:
            value = hotkeys.get(action)
            if isinstance(value, str) and value.strip():
                normalized[action] = value.strip().upper()
        parsed_shortcuts = []
        for key_name in normalized.values():
            parsed = self.parse_hotkey(key_name)
            if parsed is None:
                return defaults.copy()
            parsed_shortcuts.append(parsed)
        if len(parsed_shortcuts) != len(set(parsed_shortcuts)):
            return defaults.copy()
        return normalized


    def get_hotkey_menu_items(self):
        return {
            "next_img": (self.menu_next, "Next"),
            "last_img": (self.menu_last, "Last"),
            "save_img": (self.menu_save, "Save"),
            "refresh": (self.menu_refresh, "Refresh"),
            "hidden": (self.menu_hidden, "Hidden"),
            "move_up": (self.menu_up, "Up"),
            "move_down": (self.menu_down, "Down"),
            "move_left": (self.menu_left, "Left"),
            "move_right": (self.menu_right, "Right"),
            "delete_box": (self.menu_delete_box, "Delete box"),
        }


    def format_hotkey_for_menu(self, key_name):
        tokens = [token.strip().upper() for token in str(key_name).split("+") if token.strip()]
        display_map = {
            "CTRL": "Ctrl",
            "CONTROL": "Ctrl",
            "ALT": "Alt",
            "SHIFT": "Shift",
            "UP": "Up",
            "ARROWUP": "Up",
            "DOWN": "Down",
            "ARROWDOWN": "Down",
            "LEFT": "Left",
            "ARROWLEFT": "Left",
            "RIGHT": "Right",
            "ARROWRIGHT": "Right",
            "DELETE": "Delete",
        }
        return "+".join(display_map.get(token, token.title() if len(token) > 1 else token) for token in tokens)


    def update_hotkey_menu_labels(self):
        for action, (menu_item, base_label) in self.get_hotkey_menu_items().items():
            hotkey_text = self.format_hotkey_for_menu(self.hotkeys[action])
            menu_item.SetItemLabel(f"{base_label}\t{hotkey_text}")


    def apply_hotkeys(self, hotkeys):
        hotkeys = self.normalize_hotkeys(hotkeys)
        entries = []
        for action, (menu_item, _) in self.get_hotkey_menu_items().items():
            parsed = self.parse_hotkey(hotkeys[action])
            if parsed is None:
                continue
            modifiers, keycode = parsed
            entries.append((modifiers, keycode, menu_item.GetId()))
        self.hotkeys = hotkeys
        self.acceltbl = wx.AcceleratorTable(entries)
        self.SetAcceleratorTable(self.acceltbl)
        self.update_hotkey_menu_labels()


    def _configuration_files(self):
        directory = Path(get_resource_path(str(Path("configs"))))
        self.output_config_path = directory / "session_config.json"
        self.ImgManager.exif_config_path = self.output_config_path
        return synchronize(directory, self._gui_config_defaults, self.get_default_hotkeys())


    def _capture_configuration(self):
        self._commit_video_settings()
        saved, baseline = self._configuration_files()
        current = merge_missing(read_config(self.output_config_path), saved)
        data = {name: control_value(name, control)
                for name, control in self._config_controls.items()}
        # Invalid edits never replace the effective validated cache settings.
        data.update(cache_frames=str(self.shared_config.cache_num),
                    cache_multiplier=str(self.shared_config.cache_multiplier))
        # Automatic pacing must not overwrite the user's requested interval.
        if self.shared_config.video_mode and self.shared_config.manual_interval is not None:
            data['interval'] = str(self.shared_config.manual_interval)
        current['output'].update(data)
        current['hotkeys'] = self.hotkeys
        return current


    def _save_session_configuration(self):
        current = self._capture_configuration()
        write_config(self.output_config_path, current)


    def save_configuration(self, event):
        current = self._capture_configuration()
        write_config(Path(get_resource_path(str(Path("configs")))) / "userdef_config.json", current)


    def load_configuration(self, event, config_name="userdef_config.json"):
        saved, baseline = self._configuration_files()
        if config_name == "userdef_config.json":
            full_config = saved
        elif config_name == "default_config.json":
            full_config = baseline
        else:
            full_config = merge_missing(read_config(
                Path(get_resource_path(str(Path("configs")))) / config_name), baseline)
        for name, control in self._config_controls.items():
            # Reset first so invalid values cannot inherit a previous session's UI.
            apply_value(name, control, self._gui_config_defaults[name])
            apply_value(name, control, full_config['output'].get(name))
        self._interval_user_edited = True
        self.shared_config.interval_recommend = None
        self.shared_config.manual_interval = None
        if self.shared_config.video_mode != self.video_mode.GetValue():
            self.on_enable_video_mode(None)
        else:
            on_video_mode_change(self.video_mode.GetValue())
        self._commit_video_settings()
        # The active session follows Load/Reset, while the manual snapshot stays
        # unchanged until the user explicitly presses Save.
        write_config(self.output_config_path, full_config)
        self.ImgManager._full_mappings = None
        self.ImgManager.load_exif_display_config(force_reload=True)
        self.apply_hotkeys(full_config.get('hotkeys', {}))


    def reset_configuration(self, event):
        self.load_configuration(event, config_name="default_config.json")


    def _initialize_configuration_paths(self):
        self.output_config_path = Path(get_resource_path(str(Path("configs")))) / "session_config.json"
        self.ImgManager.exif_config_path = self.output_config_path

    def _initialize_hotkeys(self):
        self.hotkeys = self.get_default_hotkeys()
        try:
            with open(self.output_config_path, "r", encoding="utf-8") as f:
                self.hotkeys = self.normalize_hotkeys(json.load(f).get("hotkeys", {}))
        except Exception:
            pass
        self.apply_hotkeys(self.hotkeys)

    def _capture_configuration_defaults(self):
        # Capture pristine GUI values before loading the saved session.
        self._config_controls = settings_controls(self)
        self._gui_config_defaults = {name: control_value(name, control)
                                     for name, control in self._config_controls.items()}
