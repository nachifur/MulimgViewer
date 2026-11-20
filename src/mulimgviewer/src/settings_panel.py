"""Foldable settings UI; edits never start rendering or cache workers."""
import wx
from .resource_policy import positive_cache_integer
from .settings_section import SettingsSection


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
