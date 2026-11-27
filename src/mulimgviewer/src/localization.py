"""Live desktop translations. English widget text is the fallback message ID."""
import json
from functools import lru_cache
from pathlib import Path

import wx
import wx.adv

from .languages import DEFAULT_LANGUAGE, LANGUAGE_INFO
from .translations_es import MESSAGES as ES
from .translations_zh import MESSAGES as ZH_CN


@lru_cache(maxsize=4)
def catalog(code):
    if code == "en":
        return {}
    if code == "zh_CN":
        return ZH_CN
    if code == "es":
        return ES
    path = Path(__file__).with_name("locales") / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


language = DEFAULT_LANGUAGE


def tr(message):
    return catalog(language).get(message, message)


def bind_window(frame):
    """Capture only interface text. Never rewrite paths, edits, fonts or plugins."""
    bindings = []

    def bind(source, setter):
        if source in ZH_CN:
            bindings.append((source, setter))

    bind(frame.GetTitle(), frame.SetTitle)
    for name, control in vars(frame).items():
        if not isinstance(control, wx.Window):
            continue
        if isinstance(control, (wx.StaticText, wx.Button, wx.CheckBox, wx.adv.HyperlinkCtrl)):
            if not name.endswith("_pane_header"):
                bind(control.GetLabel(), control.SetLabel)
        elif isinstance(control, wx.Choice) and name not in ("customfunc_choice", "title_font"):
            for i, source in enumerate(control.GetStrings()):
                bind(source, lambda text, c=control, n=i: c.SetString(n, text))
        tip = control.GetToolTipText()
        if tip:
            bind(tip, control.SetToolTip)
            if name in ("cache_frames", "cache_multiplier"):
                control._cache_input_tip = tip

    def bind_menu(menu):
        for item in menu.GetMenuItems():
            label = item.GetItemLabel().partition("\t")[0]
            def set_label(text, item=item):
                _, sep, shortcut = item.GetItemLabel().partition("\t")
                item.SetItemLabel(text + sep + shortcut)
            bind(label, set_label)
            if item.GetSubMenu():
                bind_menu(item.GetSubMenu())

    bar = frame.GetMenuBar()
    if bar:
        for i in range(bar.GetMenuCount()):
            bind(bar.GetMenuLabel(i), lambda text, n=i: bar.SetMenuLabel(n, text))
            bind_menu(bar.GetMenu(i))
    frame._ui_translations = bindings
    apply_window(frame)


def apply_window(frame):
    for source, setter in frame._ui_translations:
        setter(tr(source))
    refresh = getattr(frame, "_refresh_language", None)
    if refresh:
        refresh()
    frame.Layout()


def set_language(code):
    global language
    selected = code if isinstance(code, str) and code in LANGUAGE_INFO else DEFAULT_LANGUAGE
    if selected == language:
        return
    language = selected
    for frame in wx.GetTopLevelWindows():
        if hasattr(frame, "_ui_translations") and not frame.IsBeingDeleted():
            apply_window(frame)


def install_language_menu(frame):
    menu = wx.Menu()
    frame._language_items = {}
    for code, (name, _) in LANGUAGE_INFO.items():
        item = menu.AppendRadioItem(wx.ID_ANY, name)
        frame._language_items[code] = item
        frame.Bind(wx.EVT_MENU, lambda event, selected=code: set_language(selected), item)
    frame.main_menu_bar.Append(menu, "Language")
    bind_window(frame)
