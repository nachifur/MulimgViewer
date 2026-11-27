"""Viewer configuration files, control values, and session lifecycle."""
import copy
import json
import os
import shutil
import tempfile
import time
import wx
from pathlib import Path

from . import localization
from .image_encoding import LEGACY_TO_CURRENT, ORDER
from .path_select import on_video_mode_change
from .render_layout import normalize_gaps
from .utils import get_resource_path


ALIASES = {'show_unit': 'show_original_panel', 'm_checkBox33': 'video_mode', 'row_col12': 'cache_frames',
           'row_col1': 'interval', 'row_col13': 'skip_frames',
           'cache_multipliler': 'cache_multiplier', 'power_model': 'power_mode',
           'm_checkBox31': 'title_show_rename', 'm_textCtrl16': 'title_rename_text',
           'rename': 'title_show_rename', 'rename_edit_txt': 'title_rename_text'}
CONTROL_NAMES = {'rename': 'title_show_rename', 'rename_edit_txt': 'title_rename_text',
                 'row_col13': 'skip_frames'}


def settings_controls(owner):
    """Persist setting-panel values, excluding runtime navigation and file entry."""
    result = {}
    seen = set()
    for name, control in vars(owner).items():
        if name.startswith('_') or name in ('m_textCtrl15', 'addfunc', 'custom_algorithm_input'):
            continue
        if not isinstance(control, (wx.TextCtrl, wx.CheckBox, wx.Choice, wx.ColourPickerCtrl,
                                    wx.SpinCtrl, wx.SpinCtrlDouble, wx.Slider)) or id(control) in seen:
            continue
        parent = control.GetParent()
        while parent is not None and parent is not owner.scrolledWindow_set:
            parent = parent.GetParent()
        # Input mode lives in the toolbar but is still a persisted preference.
        if parent is None and name != 'choice_input_mode':
            continue
        seen.add(id(control))
        result[CONTROL_NAMES.get(name, name)] = control
    return result


def control_value(name, control):
    if isinstance(control, wx.Choice):
        return control.GetSelection() + (1 if name == 'power_mode' else 0)
    if isinstance(control, wx.ColourPickerCtrl):
        return list(control.GetColour().Get(includeAlpha=True))
    return control.GetValue()


def apply_value(name, control, value):
    if isinstance(control, wx.Choice):
        if isinstance(value, int) and not isinstance(value, bool):
            selection = value - (1 if name == 'power_mode' else 0)
            if 0 <= selection < control.GetCount():
                control.SetSelection(selection)
    elif isinstance(control, wx.ColourPickerCtrl):
        if isinstance(value, list) and len(value) in (3, 4) and all(
                isinstance(v, int) and 0 <= v <= 255 for v in value):
            control.SetColour(wx.Colour(*value))
    elif isinstance(control, wx.Slider):
        if isinstance(value,int) and not isinstance(value,bool) and control.GetMin()<=value<=control.GetMax():
            control.SetValue(value)
    elif isinstance(control, wx.TextCtrl):
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            control.ChangeValue(str(value))
    elif isinstance(control, wx.CheckBox):
        if isinstance(value, bool):
            control.SetValue(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        control.SetValue(value)


def merge_missing(values, defaults):
    result = copy.deepcopy(values) if isinstance(values, dict) else {}
    for key, value in defaults.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(value, dict):
            result[key] = merge_missing(result[key], value)
    return result


def read_config(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Configuration must be an object')
    except (ValueError, UnicodeError):
        # Retain malformed user data before repairing it from GUI/defaults.
        shutil.copy2(path, path.with_name(path.name + f'.invalid-{time.time_ns()}.bak'))
        return {}
    if 'output' not in data:
        sections = {key: data.pop(key) for key in
                    ('hotkeys', 'exif_display', 'exif_tag_mappings', 'window_state', 'save_format_order', 'settings_sections', 'language') if key in data}
        data = dict(sections, output=data)
    output = data.get('output')
    if not isinstance(output, dict):
        output = data['output'] = {}
    for old, new in ALIASES.items():
        if old in output and new not in output:
            output[new] = output[old]
    # Retire the ambiguous old name after preserving its value.
    output.pop('show_unit',None)
    if isinstance(output.get('gap'), str):
        try:
            output['gap'] = ','.join(map(str, normalize_gaps(output['gap'])))
        except (ValueError, TypeError):
            # Keep malformed user input editable; Refresh reports invalid settings.
            pass
    if output.get('magnifier_show_scale') == '-1.-1':
        # Repair the known malformed spelling of the automatic-size sentinel.
        output['magnifier_show_scale'] = '-1,-1'
    hotkeys=data.get('hotkeys')
    if isinstance(hotkeys,dict) and ('pause_save' in hotkeys or 'cancel_save' in hotkeys):
        hotkeys.pop('pause_save',None)
        hotkeys.pop('cancel_save',None)
        hotkeys.setdefault('pause_tasks','ESC')
    if 'save_format' in output and data.get('save_format_order')!=ORDER:
        value=output['save_format']
        if isinstance(value,int) and not isinstance(value,bool):
            output['save_format']=LEGACY_TO_CURRENT.get(value,0)
        data['save_format_order']=ORDER
    return data


def write_config(path, data):
    if isinstance(data.get('output'),dict) and 'save_format' in data['output']:
        data=copy.deepcopy(data)
        data['save_format_order']=ORDER
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=1, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate_config_roles(directory):
    """Swap legacy file roles once; a journal makes interrupted swaps resumable."""
    directory = Path(directory)
    marker = directory / 'config_schema.json'
    journal = directory / '.config_roles_migration.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('roles_version') == 2:
        # A previous swap finished but may have stopped before journal removal.
        journal.unlink(missing_ok=True)
        return
    if journal.exists():
        documents = json.loads(journal.read_text(encoding='utf-8'))
    else:
        # Before version 2, default held user settings and userdef held defaults.
        documents = {'factory': read_config(directory / 'userdef_config.json'),
                     'user': read_config(directory / 'default_config.json')}
        write_config(journal, documents)
    write_config(directory / 'default_config.json', documents['factory'])
    write_config(directory / 'userdef_config.json', documents['user'])
    write_config(marker, {'roles_version': 2})
    journal.unlink(missing_ok=True)


def synchronize(directory, gui_defaults, hotkeys, section_defaults=None):
    directory = Path(directory)
    migrate_config_roles(directory)
    baseline_path, saved_path = directory / 'default_config.json', directory / 'userdef_config.json'
    fallback = {'output': gui_defaults, 'hotkeys': hotkeys, 'language': localization.DEFAULT_LANGUAGE}
    if section_defaults is not None:
        fallback['settings_sections']=section_defaults
        fallback['window_state']={'sidebar_width_dip':None}
    if 'save_format' in gui_defaults:fallback['save_format_order']=ORDER
    baseline = read_config(baseline_path)
    baseline = merge_missing(baseline, fallback)
    baseline["language"] = localization.DEFAULT_LANGUAGE
    if section_defaults is not None:
        # Reset follows the current FBP; saved and session fold preferences
        # remain independent and are only backfilled for newly added groups.
        baseline['settings_sections']=copy.deepcopy(section_defaults)
    if 'save_format' in gui_defaults:
        baseline['output']['save_format']=gui_defaults['save_format']
        baseline['save_format_order']=ORDER
    saved = read_config(saved_path)
    saved = merge_missing(saved, baseline)
    for path, after in ((baseline_path, baseline), (saved_path, saved)):
        try:
            on_disk = json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError, UnicodeError):
            on_disk = None
        if on_disk != after:
            write_config(path, after)
    # The latest session is independent of the explicit Save/Load snapshot.
    session_path = directory / 'session_config.json'
    session = merge_missing(read_config(session_path), saved)
    try:
        on_disk = json.loads(session_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError, UnicodeError):
        on_disk = None
    if on_disk != session:
        write_config(session_path, session)
    return saved, baseline


# Viewer session and GUI bindings
EDITOR_NAVIGATION_KEYS = {wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_UP, wx.WXK_DOWN,
    wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN, wx.WXK_DELETE, wx.WXK_BACK}


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
            self._capture_sidebar_preference(data)
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
            "pause_tasks": "ESC",
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
            "ESC": wx.WXK_ESCAPE,
            "ESCAPE": wx.WXK_ESCAPE,
        }
        special_keys.update({f'F{i}':getattr(wx,f'WXK_F{i}') for i in range(1,25)})
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
            "pause_tasks": (self.menu_pause_tasks, "Pause saving / playback"),
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
            # Menu labels create native accelerators too. Clearing only the
            # frame's AcceleratorTable leaves these active on some platforms.
            parsed = self.parse_hotkey(self.hotkeys[action])
            reserved = getattr(self, '_editing_accelerators', False) and parsed and parsed[1] in EDITOR_NAVIGATION_KEYS
            base_label = localization.tr(base_label)
            label = base_label if reserved else f"{base_label}\t{hotkey_text}"
            if menu_item.GetItemLabel() != label:
                menu_item.SetItemLabel(label)

    def _sync_accelerator_focus(self):
        if getattr(self, '_is_closing', False):
            return
        focus = wx.Window.FindFocus()
        editing = False
        while focus is not None and focus is not self:
            if isinstance(focus, (wx.TextCtrl, wx.SearchCtrl, wx.ComboBox, wx.SpinCtrl, wx.SpinCtrlDouble)):
                editing = self.IsDescendant(focus)
                break
            focus = focus.GetParent()
        self._editing_accelerators = editing
        self.SetAcceleratorTable(self._editing_acceltbl if editing else self.acceltbl)
        self.update_hotkey_menu_labels()


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
        self._editing_acceltbl = wx.AcceleratorTable([
            entry for entry in entries if entry[1] not in EDITOR_NAVIGATION_KEYS])
        self._sync_accelerator_focus()


    def _configuration_files(self):
        directory = Path(get_resource_path(str(Path("configs"))))
        self.output_config_path = directory / "session_config.json"
        self.ImgManager.exif_config_path = self.output_config_path
        return synchronize(directory, self._gui_config_defaults, self.get_default_hotkeys(),
                           section_defaults=self._gui_section_defaults)


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
        data['output_directory']=self.out_path_str
        current['output'].update(data)
        current['language'] = localization.language
        current['hotkeys'] = self.hotkeys
        current['settings_sections'] = self._capture_settings_sections()
        self._capture_sidebar_preference(current)
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
        localization.set_language(full_config.get('language'))
        full_config['language'] = localization.language
        self._restore_settings_sections(full_config.get('settings_sections'))
        self._sync_title_controls()
        self._sync_save_controls()
        self._set_output_directory(self.output_directory.GetValue())
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
        self._restore_sidebar_width()
        self.ImgManager._full_mappings = None
        self.ImgManager.load_exif_display_config(force_reload=True)
        self.apply_hotkeys(full_config.get('hotkeys', {}))
        if not getattr(self.ImgManager,'img_num',0):self._show_input_status()


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
        self._gui_section_defaults = self._capture_settings_sections()
        self._config_controls = settings_controls(self)
        self._gui_config_defaults = {name: control_value(name, control)
                                     for name, control in self._config_controls.items()}
