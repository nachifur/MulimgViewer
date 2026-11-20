"""Client-coordinate splitter geometry and DPI-independent sidebar preference."""
import json
import wx


class SidebarLayoutMixin:
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
