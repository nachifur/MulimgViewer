"""GUI-derived settings and additive, atomic JSON configuration persistence."""
import copy
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import wx

ALIASES = {'m_checkBox33': 'video_mode', 'row_col12': 'cache_frames',
           'row_col1': 'interval', 'row_col13': 'skip_frames',
           'cache_multipliler': 'cache_multiplier', 'power_model': 'power_mode'}
CONTROL_NAMES = {'m_checkBox31': 'title_show_rename', 'm_textCtrl16': 'title_rename_text',
                 'row_col13': 'skip_frames'}


def settings_controls(owner):
    """Persist setting-panel values, excluding runtime navigation and file entry."""
    result = {}
    seen = set()
    for name, control in vars(owner).items():
        if name.startswith('_') or name in ('m_textCtrl15', 'custom_algorithm_input'):
            continue
        if not isinstance(control, (wx.TextCtrl, wx.CheckBox, wx.Choice, wx.ColourPickerCtrl,
                                    wx.SpinCtrl, wx.SpinCtrlDouble)) or id(control) in seen:
            continue
        parent = control.GetParent()
        while parent is not None and parent is not owner.m_panel4:
            parent = parent.GetParent()
        if parent is None:
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
                    ('hotkeys', 'exif_display', 'exif_tag_mappings', 'window_state') if key in data}
        data = dict(sections, output=data)
    output = data.get('output')
    if not isinstance(output, dict):
        output = data['output'] = {}
    for old, new in ALIASES.items():
        if old in output and new not in output:
            output[new] = output[old]
    return data


def write_config(path, data):
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


def synchronize(directory, gui_defaults, hotkeys):
    directory = Path(directory)
    migrate_config_roles(directory)
    baseline_path, saved_path = directory / 'default_config.json', directory / 'userdef_config.json'
    fallback = {'output': gui_defaults, 'hotkeys': hotkeys}
    baseline = read_config(baseline_path)
    baseline = merge_missing(baseline, fallback)
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
