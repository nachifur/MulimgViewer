"""A full-width, keyboard-accessible settings card built by wxFormBuilder."""
import wx


class SettingsSection(wx.Panel):
    """The FBP supplies one header button and one content panel.

    Keep the CollapsiblePane-style API so layout and existing callers can
    expand a section without knowing how its header is drawn.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._header=None
        self._content=None
        self._collapsed=False
        self._hover=False
        self._focused=False

    def Initialise(self):
        if self._header is not None:return
        self._header=next(c for c in self.GetChildren() if isinstance(c,wx.Button))
        self._content=next(c for c in self.GetChildren() if isinstance(c,wx.Panel))
        self._title=self._header.GetLabel()
        self.SetName(self._title.replace('&&','&'))
        font=self._header.GetFont();font.MakeBold();self._header.SetFont(font)
        self._header.Bind(wx.EVT_ENTER_WINDOW,self._enter_header)
        self._header.Bind(wx.EVT_LEAVE_WINDOW,self._leave_header)
        self._header.Bind(wx.EVT_SET_FOCUS,self._focus_header)
        self._header.Bind(wx.EVT_KILL_FOCUS,self._blur_header)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED,self._theme_changed)
        self._update_caption()
        self._style()

    @staticmethod
    def _blend(base,ink,amount):
        return wx.Colour(*(round(a*(1-amount)+b*amount) for a,b in zip(base.Get()[:3],ink.Get()[:3])))

    def _style(self):
        base=wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        ink=wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        border=(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT) if self._focused else self._blend(base,ink,.20))
        self.SetBackgroundColour(border)
        self._content.SetBackgroundColour(base)
        for child in self._content.GetChildren():
            if isinstance(child,(wx.StaticText,wx.CheckBox,wx.Slider)):child.SetBackgroundColour(base)
        self._header.SetBackgroundColour(self._blend(base,ink,.10 if self._hover or self._focused else .06))
        self._header.SetForegroundColour(ink)
        self.Refresh(False);self._header.Refresh(False)

    def _update_caption(self):
        arrow='\u25b8' if self._collapsed else '\u25be'
        self._header.SetLabel('  '+arrow+'  '+self._title)
        action='Expand' if self._collapsed else 'Collapse'
        self._header.SetToolTip(action+' '+self._title.replace('&&','&'))

    def GetPane(self):
        self.Initialise()
        return self._content

    def GetLabel(self):
        self.Initialise()
        return self._title

    def IsCollapsed(self):return self._collapsed

    def Collapse(self,collapse=True):
        self.Initialise()
        collapse=bool(collapse)
        if collapse==self._collapsed:return
        self._collapsed=collapse
        self._content.Show(not collapse)
        self._update_caption()
        self.InvalidateBestSize();self.Layout()

    def Expand(self):self.Collapse(False)

    def _enter_header(self,event):
        self._hover=True;self._style();event.Skip()

    def _leave_header(self,event):
        self._hover=False;self._style();event.Skip()

    def _focus_header(self,event):
        self._focused=True;self._style();event.Skip()

    def _blur_header(self,event):
        self._focused=False;self._style();event.Skip()

    def _theme_changed(self,event):
        self._style();event.Skip()
