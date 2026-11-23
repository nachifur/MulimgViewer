"""Settings sidebar, collapsible sections and width preferences."""
import json
import wx

from .resources import positive_cache_integer


# Collapsible section widget
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
        # The FBP body visibility is the default fold state.
        self._collapsed=not self._content.IsShown()
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
        base=wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
        ink=wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
        border=(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT) if self._focused else self._blend(base,ink,.13))
        self.SetBackgroundColour(border)
        self._content.SetBackgroundColour(base)
        for child in self._content.GetChildren():
            if isinstance(child,(wx.StaticText,wx.CheckBox,wx.Slider)):child.SetBackgroundColour(base)
        self._header.SetBackgroundColour(self._blend(base,ink,.055 if self._hover or self._focused else .025))
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

    def IsCollapsed(self):
        self.Initialise()
        return self._collapsed

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


# Sidebar controls and layout
class SettingsPanelMixin:
    def _settings_sections(self):
        return {name:control for name,control in vars(self).items()
                if isinstance(control,(SettingsSection,wx.CollapsiblePane))}

    def _capture_settings_sections(self):
        return {name:section.IsCollapsed() for name,section in self._settings_sections().items()}

    def _restore_settings_sections(self,states):
        states=states if isinstance(states,dict) else {}
        for name,section in self._settings_sections().items():
            value=states.get(name,self._gui_section_defaults[name])
            section.Collapse(value if isinstance(value,bool) else self._gui_section_defaults[name])
        self._layout_settings_sections()

    def _initialize_settings_panels(self):
        for widget in (self.save_format,self.pdf_compression,self.cache_save_format):
            widget.Bind(wx.EVT_CHOICE,self._on_save_encoding_change)
        self.cache_quality_follow_save.Bind(wx.EVT_CHECKBOX,self._on_save_encoding_change)
        self.output_directory.Bind(wx.EVT_TEXT,self._on_output_directory_change)
        for widget in (self.save_quality,self.cache_jpg_quality):
            widget.Bind(wx.EVT_SLIDER,self._on_quality_slider)
        for widget in (self.cache_frames,self.cache_multiplier):
            widget.Bind(wx.EVT_KILL_FOCUS,self._on_cache_field_blur)
        self._sync_save_controls()

    def expand_settings_sections(self,event):
        for section in self._settings_sections().values():section.Expand()
        self._layout_settings_sections()

    def collapse_settings_sections(self,event):
        for section in self._settings_sections().values():section.Collapse(True)
        self._layout_settings_sections()

    def _on_quality_slider(self,event):
        self._sync_quality_labels()
        event.Skip()

    def _sync_quality_labels(self):
        self.save_quality_value.SetLabel(str(self.save_quality.GetValue()))
        self.cache_quality_value.SetLabel(str(self._effective_cache_quality()))
        self.cache_quality_value.Enable(self.cache_jpg_quality.IsEnabled())

    def _on_cache_field_blur(self,event):
        field=event.GetEventObject()
        if not hasattr(field,'_cache_input_background'):
            field._cache_input_background=field.GetBackgroundColour()
            tip=field.GetToolTip()
            field._cache_input_tip=tip.GetTip() if tip else 'Integer >= 1'
        try:
            positive_cache_integer(field.GetValue())
        except ValueError:
            base=wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            red,green,blue=base.Get()[:3]
            field.SetBackgroundColour(wx.Colour(round(red*.8+255*.2),round(green*.8),round(blue*.8)))
            field.SetToolTip('Enter a whole number >= 1. The previous effective value is kept until a valid Refresh.')
        else:
            field.SetBackgroundColour(field._cache_input_background)
            field.SetToolTip(field._cache_input_tip)
        field.Refresh(False)
        event.Skip()

    def _on_save_encoding_change(self,event):
        self._sync_save_controls()
        if event is not None:event.Skip()

    def _sync_save_controls(self):
        fmt=self.save_format.GetSelection()
        self.png_compression.Enable(fmt==1)
        self.pdf_compression.Enable(fmt==2)
        self.save_quality.Enable(fmt==0 or (fmt==2 and self.pdf_compression.GetSelection()==1))
        self.cache_jpg_quality.Enable(not self.cache_quality_follow_save.GetValue()
                                      and self.cache_save_format.GetSelection()!=1)
        if hasattr(self,'shared_config'):self.move_file.Enable(not self.video_mode.GetValue())
        self._sync_quality_labels()

    def _effective_cache_quality(self):
        return self.save_quality.GetValue() if self.cache_quality_follow_save.GetValue() else self.cache_jpg_quality.GetValue()

    def _set_output_directory(self,value):
        self.out_path_str=str(value).strip()
        if self.output_directory.GetValue()!=self.out_path_str:
            self.output_directory.ChangeValue(self.out_path_str)
        self.SetStatusText_(['-1','-1','-1','Output: '+(self.out_path_str or 'not set')])

    def _on_output_directory_change(self,event):
        self._set_output_directory(self.output_directory.GetValue())
        if event is not None:event.Skip()

    def on_settings_section_changed(self,event):
        if event is not None:
            section=event.GetEventObject().GetParent()
            if isinstance(section,SettingsSection):section.Collapse(not section.IsCollapsed())
            event.Skip()
        # A section only changes the settings layout, never the viewer size.
        wx.CallAfter(self._layout_settings_sections)

    def _layout_settings_sections(self):
        if getattr(self,'_is_closing',False) or self.IsBeingDeleted():return
        # First establish the available width, then measure wrapped rows.
        # A second pass accounts for the settings scrollbar taking width.
        for _ in range(2):
            self.scrolledWindow_set.Layout()
            for child in self.scrolledWindow_set.GetChildren():
                if isinstance(child,(SettingsSection,wx.CollapsiblePane)):
                    child.GetPane().Layout();child.GetPane().InvalidateBestSize()
                    child.InvalidateBestSize()
            self.scrolledWindow_set.InvalidateBestSize()
            self.scrolledWindow_set.Layout()
            self.scrolledWindow_set.FitInside()

    # Sidebar width and sash events
    def _initialize_sidebar_layout(self):
        self._sidebar_ready=False
        self._sidebar_applying=False
        self._sidebar_layout_pending=False
        self._sidebar_preferred_dip=None
        self.width_setting=self.FromDIP(260)
        self.width_setting_=self.width_setting
        self.split_changing=False
        self.SashPosition=0
        self.init_min_size()
        self.viewer_settings_splitter.SetMinimumPaneSize(self.FromDIP(80))
        self.viewer_settings_splitter.SetSashGravity(1.0)
        self.viewer_settings_splitter.SetToolTip('Drag to resize settings; double-click to restore automatic width.')
        self.viewer_settings_splitter.Bind(wx.EVT_SIZE,self._sidebar_size_changed)
        self.viewer_settings_splitter.Bind(wx.EVT_SPLITTER_DCLICK,self._sidebar_reset_width)
        self.viewer_settings_splitter.Bind(wx.EVT_MOUSE_CAPTURE_LOST,self._sidebar_capture_lost)
        if hasattr(wx,'EVT_DPI_CHANGED'):self.Bind(wx.EVT_DPI_CHANGED,self._sidebar_size_changed)
        # A scrolled settings form must not determine the initial frame height.
        # Retain explicit FBP frame sizes; replace unusably narrow fitted sizes.
        self.SetMinSize(self.FromDIP(wx.Size(480,320)))
        if self.Size.width<self.FromDIP(600):
            size=self.FromDIP(wx.Size(1000,700))
            if wx.Display.GetCount():
                index=wx.Display.GetFromWindow(self)
                area=wx.Display(0 if index==wx.NOT_FOUND else index).GetClientArea()
                size=wx.Size(min(size.width,area.width),min(size.height,area.height))
            self.SetSize(size)
        self.Layout()
        self._sidebar_ready=True
        self._apply_sidebar_width()

    def _sidebar_bounds(self):
        available=max(1,self.viewer_settings_splitter.ClientSize.width-self.viewer_settings_splitter.GetSashSize())
        minimum=min(self.FromDIP(160),max(1,available//2))
        maximum=max(minimum,available-min(self.FromDIP(120),max(1,available//2)))
        return available,minimum,maximum

    def _automatic_sidebar_width(self):
        content=self.scrolledWindow_set.GetSizer().GetMinSize().width
        scrollbar=wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X,self.scrolledWindow_set)
        preferred=max(self.FromDIP(260),content+max(0,scrollbar)+self.FromDIP(8))
        available,minimum,maximum=self._sidebar_bounds()
        return min(maximum,max(minimum,min(preferred,max(minimum,int(available*.45)))))

    def _apply_sidebar_width(self):
        if (not getattr(self,'_sidebar_ready',False) or self._sidebar_applying
                or self.split_changing or getattr(self,'_is_closing',False)):return
        splitter=self.viewer_settings_splitter
        if splitter.ClientSize.width<=self.FromDIP(160):return
        self._sidebar_applying=True
        try:
            if self.hidden_flag:
                if splitter.IsSplit():splitter.Unsplit(self.scrolledWindow_set)
                self.width_setting=0
                self.SashPosition=splitter.ClientSize.width
                return
            available,minimum,maximum=self._sidebar_bounds()
            preferred=(self._automatic_sidebar_width() if self._sidebar_preferred_dip is None
                       else self.FromDIP(self._sidebar_preferred_dip))
            width=min(maximum,max(minimum,preferred))
            position=available-width
            if not splitter.IsSplit():
                self.scrolledWindow_set.Show()
                splitter.SplitVertically(self.scrolledWindow_img,self.scrolledWindow_set,position)
            elif splitter.GetSashPosition()!=position:splitter.SetSashPosition(position)
            splitter.UpdateSize()
            self.SashPosition=splitter.GetSashPosition()
            self.width_setting=self.scrolledWindow_set.Size.width
            self.width_setting_=self.width_setting
            if hasattr(self,'_layout_settings_sections'):self._layout_settings_sections()
        finally:self._sidebar_applying=False

    def _sidebar_size_changed(self,event):
        event.Skip()
        if not getattr(self,'_sidebar_ready',False) or self._sidebar_layout_pending:return
        self._sidebar_layout_pending=True
        wx.CallAfter(self._sidebar_finish_resize)

    def _sidebar_finish_resize(self):
        self._sidebar_layout_pending=False
        if getattr(self,'_is_closing',False):return
        self._apply_sidebar_width()

    def _sidebar_sash_changing(self,event):
        if self._sidebar_applying or self.hidden_flag:
            event.Skip();return
        # Do not lay out parents or change minimum sizes while the mouse owns
        # the native sash. The proposed position is already in splitter pixels.
        self.split_changing=True
        available,minimum,maximum=self._sidebar_bounds()
        event.SetSashPosition(min(available-minimum,max(available-maximum,event.GetSashPosition())))
        event.Skip()

    def _sidebar_sash_changed(self,event):
        if self._sidebar_applying or not self.split_changing:
            event.Skip();return
        available,minimum,maximum=self._sidebar_bounds()
        width=min(maximum,max(minimum,available-event.GetSashPosition()))
        self._sidebar_preferred_dip=self.ToDIP(width)
        self.split_changing=False
        self._apply_sidebar_width()
        self.auto_layout(frame_resize=True)
        event.Skip()

    def _sidebar_capture_lost(self,event):
        self.split_changing=False
        self._sidebar_size_changed(event)

    def _sidebar_reset_width(self,event):
        event.Veto()  # Double-click restores width rather than unsplitting.
        self.split_changing=False
        self._sidebar_preferred_dip=None
        self._apply_sidebar_width()

    def _capture_sidebar_preference(self,data):
        state=data.get('window_state')
        if self._sidebar_preferred_dip is not None:
            if not isinstance(state,dict):state={};data['window_state']=state
            state['sidebar_width_dip']=int(self._sidebar_preferred_dip)
        elif isinstance(state,dict):state['sidebar_width_dip']=None

    def _restore_sidebar_width(self):
        self._sidebar_preferred_dip=None
        try:
            data=json.loads(self.output_config_path.read_text(encoding='utf-8'))
            state=data.get('window_state',{})
            value=state.get('sidebar_width_dip') if isinstance(state,dict) else None
            if isinstance(value,int) and not isinstance(value,bool) and 0<value<=32767:
                self._sidebar_preferred_dip=value
        except (OSError,ValueError,TypeError,AttributeError):pass
        self.Layout()
        self._apply_sidebar_width()
