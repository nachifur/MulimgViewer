# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 4.2.1-0-g80c4cb6)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

from ..src.settings_panel import SettingsSection
import wx
import wx.xrc

###########################################################################
## Class MulimgViewerGui
###########################################################################

class MulimgViewerGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"MulimgViewer", pos = wx.DefaultPosition, size = wx.Size( -1,-1 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		main_layout_sizer = wx.FlexGridSizer( 2, 1, 0, 0 )
		main_layout_sizer.AddGrowableCol( 0 )
		main_layout_sizer.AddGrowableRow( 1 )
		main_layout_sizer.SetFlexibleDirection( wx.BOTH )
		main_layout_sizer.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.playback_toolbar_panel = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL )
		playback_toolbar_sizer = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.button_open_all = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u"📂️", wx.DefaultPosition, wx.Size( 50,30 ), wx.BORDER_NONE )
		self.button_open_all.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.button_open_all.SetToolTip( u"Open an input using the selected input mode." )

		playback_toolbar_sizer.Add( self.button_open_all, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_input_modeChoices = [ u"Sequential", u"Parallel auto", u"Parallel manual", u"Image/Video File List" ]
		self.choice_input_mode = wx.Choice( self.playback_toolbar_panel, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), choice_input_modeChoices, 0 )
		self.choice_input_mode.SetSelection( 0 )
		self.choice_input_mode.SetToolTip( u"Sequential: one source. Parallel auto: discover sources in a folder. Parallel manual: choose sources. File List: read paths from a text or CSV file." )

		playback_toolbar_sizer.Add( self.choice_input_mode, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.input_toolbar_separator = wx.StaticLine( self.playback_toolbar_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		playback_toolbar_sizer.Add( self.input_toolbar_separator, 0, wx.EXPAND |wx.ALL, 5 )

		self.save_butoon = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u"💾️", wx.DefaultPosition, wx.Size( 50,30 ), wx.BORDER_NONE )
		self.save_butoon.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.save_butoon.SetToolTip( u"Save using Save Settings (Ctrl+S). Esc pauses bulk saving; click Save to continue." )

		playback_toolbar_sizer.Add( self.save_butoon, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.save_toolbar_separator = wx.StaticLine( self.playback_toolbar_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		playback_toolbar_sizer.Add( self.save_toolbar_separator, 0, wx.EXPAND |wx.ALL, 5 )

		self.left_arrow_button = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u"<", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.left_arrow_button.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.left_arrow_button.SetToolTip( u"Previous page (Ctrl+L)." )

		playback_toolbar_sizer.Add( self.left_arrow_button, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.play = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u"▶", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.play.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.play.SetToolTip( u"Play / pause. Esc pauses playback." )

		playback_toolbar_sizer.Add( self.play, 0, wx.ALL, 5 )

		self.right_arrow_button = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u">", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.right_arrow_button.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.right_arrow_button.SetToolTip( u"Next page (Ctrl+N)." )

		playback_toolbar_sizer.Add( self.right_arrow_button, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.refresh_button = wx.Button( self.playback_toolbar_panel, wx.ID_ANY, u"⟳", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.refresh_button.SetToolTip( u"Apply display and cache edits together (Ctrl+R)." )

		playback_toolbar_sizer.Add( self.refresh_button, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.slider_value = wx.TextCtrl( self.playback_toolbar_panel, wx.ID_ANY, u"1", wx.DefaultPosition, wx.Size( 50,-1 ), wx.TE_PROCESS_ENTER )
		playback_toolbar_sizer.Add( self.slider_value, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_CENTER_HORIZONTAL, 5 )

		self.slider_img = wx.Slider( self.playback_toolbar_panel, wx.ID_ANY, 1, 1, 100, wx.DefaultPosition, wx.Size( 120,30 ), wx.SL_HORIZONTAL )
		playback_toolbar_sizer.Add( self.slider_img, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.slider_value_max = wx.StaticText( self.playback_toolbar_panel, wx.ID_ANY, u"1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.slider_value_max.Wrap( -1 )

		playback_toolbar_sizer.Add( self.slider_value_max, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.view_toolbar_separator = wx.StaticLine( self.playback_toolbar_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		playback_toolbar_sizer.Add( self.view_toolbar_separator, 0, wx.EXPAND |wx.ALL, 5 )

		self.magnifier = wx.ToggleButton( self.playback_toolbar_panel, wx.ID_ANY, u"🔍️", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.magnifier.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		playback_toolbar_sizer.Add( self.magnifier, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.rotation = wx.ToggleButton( self.playback_toolbar_panel, wx.ID_ANY, u"↷", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.rotation.SetFont( wx.Font( 16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		playback_toolbar_sizer.Add( self.rotation, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.flip = wx.ToggleButton( self.playback_toolbar_panel, wx.ID_ANY, u"⏃", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.flip.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		playback_toolbar_sizer.Add( self.flip, 0, wx.ALL, 5 )


		self.playback_toolbar_panel.SetSizer( playback_toolbar_sizer )
		self.playback_toolbar_panel.Layout()
		playback_toolbar_sizer.Fit( self.playback_toolbar_panel )
		main_layout_sizer.Add( self.playback_toolbar_panel, 1, wx.EXPAND |wx.ALL, 5 )

		self.viewer_container_panel = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		viewer_container_sizer = wx.FlexGridSizer( 1, 1, 0, 0 )
		viewer_container_sizer.AddGrowableCol( 0 )
		viewer_container_sizer.AddGrowableRow( 0 )
		viewer_container_sizer.SetFlexibleDirection( wx.BOTH )
		viewer_container_sizer.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.viewer_settings_splitter = wx.SplitterWindow( self.viewer_container_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.SP_3D|wx.SP_LIVE_UPDATE )
		self.scrolledWindow_img = wx.ScrolledWindow( self.viewer_settings_splitter, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_img.SetScrollRate( 5, 5 )
		image_view_sizer = wx.FlexGridSizer( 2, 1, 0, 0 )
		image_view_sizer.SetFlexibleDirection( wx.BOTH )
		image_view_sizer.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		image_view_sizer.SetMinSize( wx.Size( 700,600 ) )
		self.empty_view_hint = wx.StaticText( self.scrolledWindow_img, wx.ID_ANY, u"Image show area", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.empty_view_hint.Wrap( -1 )

		self.empty_view_hint.SetToolTip( u"Open an image or video input to begin." )

		image_view_sizer.Add( self.empty_view_hint, 0, wx.ALL, 5 )

		self.img_panel = wx.Panel( self.scrolledWindow_img, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		image_view_sizer.Add( self.img_panel, 1, wx.EXPAND |wx.ALL, 5 )


		self.scrolledWindow_img.SetSizer( image_view_sizer )
		self.scrolledWindow_img.Layout()
		image_view_sizer.Fit( self.scrolledWindow_img )
		self.scrolledWindow_set = wx.ScrolledWindow( self.viewer_settings_splitter, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_set.SetScrollRate( 5, 5 )
		settings_sections_sizer = wx.BoxSizer( wx.VERTICAL )

		settings_actions_sizer = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.settings_expand_button = wx.Button( self.scrolledWindow_set, wx.ID_ANY, u"Expand all", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.settings_expand_button.SetToolTip( u"Expand all settings groups." )

		settings_actions_sizer.Add( self.settings_expand_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 2 )

		self.settings_collapse_button = wx.Button( self.scrolledWindow_set, wx.ID_ANY, u"Collapse all", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.settings_collapse_button.SetToolTip( u"Collapse all settings groups." )

		settings_actions_sizer.Add( self.settings_collapse_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 2 )


		settings_sections_sizer.Add( settings_actions_sizer, 0, wx.EXPAND|wx.ALL, 2 )

		self.settings_apply_hint = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Refresh to apply settings (Ctrl + R)", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.settings_apply_hint.Wrap( -1 )

		self.settings_apply_hint.SetToolTip( u"Edit several display settings, then apply them together. Power mode remains live; saving uses click-time settings." )

		settings_sections_sizer.Add( self.settings_apply_hint, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM, 6 )

		self.input_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		input_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.input_settings_pane_header = wx.Button( self.input_settings_pane, wx.ID_ANY, u"Input && Playback", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"input_settings_pane_header" )
		input_settings_pane_card_sizer.Add( self.input_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.input_settings_pane_content = wx.Panel( self.input_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"input_settings_pane_content" )
		input_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		self.video_mode = wx.CheckBox( self.input_settings_pane_content, wx.ID_ANY, u"Video mode", wx.DefaultPosition, wx.DefaultSize, 0 )
		input_settings_pane_sizer.Add( self.video_mode, 0, wx.EXPAND|wx.ALL, 3 )

		playback_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		playback_fields.AddGrowableCol( 1 )
		playback_fields.SetFlexibleDirection( wx.BOTH )
		playback_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.interval_label = wx.StaticText( self.input_settings_pane_content, wx.ID_ANY, u"Interval (s)", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.interval_label.Wrap( -1 )

		playback_fields.Add( self.interval_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.interval = wx.TextCtrl( self.input_settings_pane_content, wx.ID_ANY, u"1.0", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.interval.SetToolTip( u"Requested minimum page interval in seconds. Video playback may use a longer interval when supply is slower." )
		self.interval.SetMinSize( wx.Size( 64,-1 ) )

		playback_fields.Add( self.interval, 0, wx.EXPAND, 0 )

		self.skip_frames_label = wx.StaticText( self.input_settings_pane_content, wx.ID_ANY, u"Skip frames", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.skip_frames_label.Wrap( -1 )

		playback_fields.Add( self.skip_frames_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.row_col13 = wx.TextCtrl( self.input_settings_pane_content, wx.ID_ANY, u"0", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.row_col13.SetToolTip( u"Number of video frames to skip between extracted frames. 0 keeps every frame. Refresh applies changes." )
		self.row_col13.SetMinSize( wx.Size( 64,-1 ) )

		playback_fields.Add( self.row_col13, 0, wx.EXPAND, 0 )


		input_settings_pane_sizer.Add( playback_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.parallel_sequential = wx.CheckBox( self.input_settings_pane_content, wx.ID_ANY, u"Multiple frames per source", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.parallel_sequential.SetToolTip( u"Show multiple consecutive images or frames from each source, using the Per source grid. Refresh applies changes." )

		input_settings_pane_sizer.Add( self.parallel_sequential, 0, wx.EXPAND|wx.ALL, 3 )

		self.parallel_to_sequential = wx.CheckBox( self.input_settings_pane_content, wx.ID_ANY, u"Play sources sequentially", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.parallel_to_sequential.SetToolTip( u"Browse parallel sources one after another. Refresh applies changes." )

		input_settings_pane_sizer.Add( self.parallel_to_sequential, 0, wx.EXPAND|wx.ALL, 3 )


		self.input_settings_pane_content.SetSizer( input_settings_pane_sizer )
		self.input_settings_pane_content.Layout()
		input_settings_pane_sizer.Fit( self.input_settings_pane_content )
		input_settings_pane_card_sizer.Add( self.input_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.input_settings_pane.SetSizer( input_settings_pane_card_sizer )
		self.input_settings_pane.Layout()
		input_settings_pane_card_sizer.Fit( self.input_settings_pane )
		settings_sections_sizer.Add( self.input_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.performance_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		performance_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.performance_settings_pane_header = wx.Button( self.performance_settings_pane, wx.ID_ANY, u"Performance && Cache", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"performance_settings_pane_header" )
		performance_settings_pane_card_sizer.Add( self.performance_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.performance_settings_pane_content = wx.Panel( self.performance_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"performance_settings_pane_content" )
		performance_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		performance_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		performance_fields.AddGrowableCol( 1 )
		performance_fields.SetFlexibleDirection( wx.BOTH )
		performance_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.power_mode_label = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"Power mode", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.power_mode_label.Wrap( -1 )

		performance_fields.Add( self.power_mode_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		power_modeChoices = [ u"1.Eco", u"2.Balanced", u"3.Performance", u"4.Maximum" ]
		self.power_mode = wx.Choice( self.performance_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), power_modeChoices, 0 )
		self.power_mode.SetSelection( 1 )
		self.power_mode.SetMinSize( wx.Size( 64,-1 ) )

		performance_fields.Add( self.power_mode, 0, wx.EXPAND, 0 )

		self.cache_frames_label = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"Cache frames", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_frames_label.Wrap( -1 )

		performance_fields.Add( self.cache_frames_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.cache_frames = wx.TextCtrl( self.performance_settings_pane_content, wx.ID_ANY, u"2", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_frames.SetToolTip( u"Positive integer, minimum 1. Inner cache radius in pages; applies to images and videos. Refresh applies changes." )
		self.cache_frames.SetMinSize( wx.Size( 64,-1 ) )

		performance_fields.Add( self.cache_frames, 0, wx.EXPAND, 0 )

		self.cache_multiplier_label = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"Cache multiplier", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_multiplier_label.Wrap( -1 )

		performance_fields.Add( self.cache_multiplier_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.cache_multiplier = wx.TextCtrl( self.performance_settings_pane_content, wx.ID_ANY, u"1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_multiplier.SetToolTip( u"Positive integer, minimum 1. Outer cache radius = Cache frames x multiplier. Larger windows use more disk space. Refresh applies changes." )
		self.cache_multiplier.SetMinSize( wx.Size( 64,-1 ) )

		performance_fields.Add( self.cache_multiplier, 0, wx.EXPAND, 0 )

		self.cache_format_label = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"Cache format", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_format_label.Wrap( -1 )

		performance_fields.Add( self.cache_format_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		cache_save_formatChoices = [ u"jpg", u"png", u"auto" ]
		self.cache_save_format = wx.Choice( self.performance_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), cache_save_formatChoices, 0 )
		self.cache_save_format.SetSelection( 2 )
		self.cache_save_format.SetToolTip( u"Cache format for all stages. auto: png for png/pdf export with both output scales >= 1; jpg otherwise. Refresh applies changes." )
		self.cache_save_format.SetMinSize( wx.Size( 64,-1 ) )

		performance_fields.Add( self.cache_save_format, 0, wx.EXPAND, 0 )


		performance_settings_pane_sizer.Add( performance_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.cache_quality_follow_save = wx.CheckBox( self.performance_settings_pane_content, wx.ID_ANY, u"Use saved JPG quality", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.cache_quality_follow_save.SetValue(True)
		self.cache_quality_follow_save.SetToolTip( u"Use Save Settings JPG quality for caches. Refresh applies changes." )

		performance_settings_pane_sizer.Add( self.cache_quality_follow_save, 0, wx.EXPAND|wx.ALL, 3 )

		cache_quality_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		cache_quality_fields.AddGrowableCol( 1 )
		cache_quality_fields.SetFlexibleDirection( wx.BOTH )
		cache_quality_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.cache_jpg_quality_label = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"Cache JPG quality", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.cache_jpg_quality_label.Wrap( -1 )

		cache_quality_fields.Add( self.cache_jpg_quality_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		cache_jpg_quality_row = wx.BoxSizer( wx.HORIZONTAL )

		self.cache_jpg_quality = wx.Slider( self.performance_settings_pane_content, wx.ID_ANY, 100, 0, 100, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		self.cache_jpg_quality.SetToolTip( u"Independent cache JPG quality. Ignored while Follow saved JPG quality is enabled. Refresh applies changes." )
		self.cache_jpg_quality.SetMinSize( wx.Size( 64,-1 ) )

		cache_jpg_quality_row.Add( self.cache_jpg_quality, 1, wx.EXPAND, 0 )

		self.cache_quality_value = wx.StaticText( self.performance_settings_pane_content, wx.ID_ANY, u"100", wx.DefaultPosition, wx.Size( -1,-1 ), wx.ALIGN_RIGHT )
		self.cache_quality_value.Wrap( -1 )

		self.cache_quality_value.SetMinSize( wx.Size( 24,-1 ) )

		cache_jpg_quality_row.Add( self.cache_quality_value, 0, wx.LEFT|wx.ALIGN_CENTER_VERTICAL, 4 )


		cache_quality_fields.Add( cache_jpg_quality_row, 0, wx.EXPAND, 0 )


		performance_settings_pane_sizer.Add( cache_quality_fields, 0, wx.EXPAND|wx.ALL, 3 )


		self.performance_settings_pane_content.SetSizer( performance_settings_pane_sizer )
		self.performance_settings_pane_content.Layout()
		performance_settings_pane_sizer.Fit( self.performance_settings_pane_content )
		performance_settings_pane_card_sizer.Add( self.performance_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.performance_settings_pane.SetSizer( performance_settings_pane_card_sizer )
		self.performance_settings_pane.Layout()
		performance_settings_pane_card_sizer.Fit( self.performance_settings_pane )
		settings_sections_sizer.Add( self.performance_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.layout_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		layout_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.layout_settings_pane_header = wx.Button( self.layout_settings_pane, wx.ID_ANY, u"Layout && Display", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"layout_settings_pane_header" )
		layout_settings_pane_card_sizer.Add( self.layout_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.layout_settings_pane_content = wx.Panel( self.layout_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"layout_settings_pane_content" )
		layout_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		image_display_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		image_display_fields.AddGrowableCol( 1 )
		image_display_fields.SetFlexibleDirection( wx.BOTH )
		image_display_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.uniform_size_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Size mode", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.uniform_size_label.Wrap( -1 )

		image_display_fields.Add( self.uniform_size_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		choice_normalized_sizeChoices = [ u"resize", u"crop", u"fill" ]
		self.choice_normalized_size = wx.Choice( self.layout_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), choice_normalized_sizeChoices, 0 )
		self.choice_normalized_size.SetSelection( 0 )
		self.choice_normalized_size.SetMinSize( wx.Size( 64,-1 ) )

		image_display_fields.Add( self.choice_normalized_size, 0, wx.EXPAND, 0 )

		self.zoom_interpolation_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Zoom interpolation", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.zoom_interpolation_label.Wrap( -1 )

		image_display_fields.Add( self.zoom_interpolation_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		image_interpChoices = [ u"nearest", u"cubic", u"linear" ]
		self.image_interp = wx.Choice( self.layout_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), image_interpChoices, 0 )
		self.image_interp.SetSelection( 2 )
		self.image_interp.SetMinSize( wx.Size( 64,-1 ) )

		image_display_fields.Add( self.image_interp, 0, wx.EXPAND, 0 )


		layout_settings_pane_sizer.Add( image_display_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.auto_layout_check = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Fit window to image", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.auto_layout_check.SetToolTip( u"Resize the window to fit the composed image when Refresh is applied." )

		layout_settings_pane_sizer.Add( self.auto_layout_check, 0, wx.EXPAND|wx.ALL, 3 )

		layout_grid_fields = wx.FlexGridSizer( 0, 3, 4, 6 )
		layout_grid_fields.AddGrowableCol( 1 )
		layout_grid_fields.SetFlexibleDirection( wx.BOTH )
		layout_grid_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.layout_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Grid", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.layout_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.layout_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.grid_dimensions_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Rows, cols", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.grid_dimensions_label.Wrap( -1 )

		layout_grid_fields.Add( self.grid_dimensions_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.layout_vertical_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Vertical", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.layout_vertical_label.Wrap( -1 )

		self.layout_vertical_label.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.layout_vertical_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.algorithm_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Algorithms", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.algorithm_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.algorithm_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.show_all_func_layout = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"2,2", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.show_all_func_layout.SetToolTip( u"Rows, columns for stitched algorithm images. Unused cells show the gap colour; algorithms beyond capacity are not processed. Refresh applies changes." )
		self.show_all_func_layout.SetMinSize( wx.Size( 64,-1 ) )

		layout_grid_fields.Add( self.show_all_func_layout, 0, wx.EXPAND, 0 )

		self.func_layout_vertical = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.func_layout_vertical.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.func_layout_vertical, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.page_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Page", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.page_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.page_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.row_col = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.row_col.SetToolTip( u"Rows, columns in the main page grid. -1,-1 chooses an automatic layout. Refresh applies changes." )
		self.row_col.SetMinSize( wx.Size( 64,-1 ) )

		layout_grid_fields.Add( self.row_col, 0, wx.EXPAND, 0 )

		self.img_vertical = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.img_vertical.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.img_vertical, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.source_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Per source", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.source_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.source_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.row_col_one_img = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.row_col_one_img.SetToolTip( u"Rows, columns of consecutive images or frames per source. Used by Multiple frames per source. Refresh applies changes." )
		self.row_col_one_img.SetMinSize( wx.Size( 64,-1 ) )

		layout_grid_fields.Add( self.row_col_one_img, 0, wx.EXPAND, 0 )

		self.one_img_vertical = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.one_img_vertical.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.one_img_vertical, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.image_unit_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Image unit", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.image_unit_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.image_unit_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.row_col_img_unit = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"3,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.row_col_img_unit.SetToolTip( u"Rows, columns for units within an image. Refresh applies changes." )
		self.row_col_img_unit.SetMinSize( wx.Size( 64,-1 ) )

		layout_grid_fields.Add( self.row_col_img_unit, 0, wx.EXPAND, 0 )

		self.img_unit_vertical = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.img_unit_vertical.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.img_unit_vertical, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.magnifier_grid_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Magnifiers", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_grid_label.Wrap( -1 )

		layout_grid_fields.Add( self.magnifier_grid_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.magnifer_row_col = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifer_row_col.SetToolTip( u"Rows, columns for magnified crops. Refresh applies changes." )
		self.magnifer_row_col.SetMinSize( wx.Size( 64,-1 ) )

		layout_grid_fields.Add( self.magnifer_row_col, 0, wx.EXPAND, 0 )

		self.magnifer_vertical = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.magnifer_vertical.SetValue(True)
		self.magnifer_vertical.SetToolTip( u"Fill this grid vertically instead of horizontally" )

		layout_grid_fields.Add( self.magnifer_vertical, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		layout_settings_pane_sizer.Add( layout_grid_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.layout_gaps_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Gaps (X,Y for each level)", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.layout_gaps_label.Wrap( -1 )

		layout_settings_pane_sizer.Add( self.layout_gaps_label, 0, wx.EXPAND|wx.ALL, 3 )

		self.gap = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"10,10,10,10,5,5,3,3,2,2", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.gap.SetToolTip( u"Five horizontal,vertical gap pairs: algorithms / page / source / unit / zoom. Example: 10,10,10,10,5,5,3,3,2,2. Refresh applies changes." )
		self.gap.SetMinSize( wx.Size( 64,-1 ) )

		layout_settings_pane_sizer.Add( self.gap, 0, wx.EXPAND|wx.ALL, 3 )

		visible_content_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		visible_content_fields.AddGrowableCol( 0 )
		visible_content_fields.AddGrowableCol( 1 )
		visible_content_fields.SetFlexibleDirection( wx.BOTH )
		visible_content_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.show_original = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Image", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_original.SetValue(True)
		visible_content_fields.Add( self.show_original, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.show_magnifer = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Magnifier", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_magnifer.SetValue(True)
		visible_content_fields.Add( self.show_magnifer, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_show = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Title", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show.SetValue(True)
		visible_content_fields.Add( self.title_show, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.one_img = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Split image into units", wx.DefaultPosition, wx.DefaultSize, 0 )
		visible_content_fields.Add( self.one_img, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.onetitle = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Shared title", wx.DefaultPosition, wx.DefaultSize, 0 )
		visible_content_fields.Add( self.onetitle, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		layout_settings_pane_sizer.Add( visible_content_fields, 0, wx.EXPAND|wx.ALL, 3 )

		display_scale_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		display_scale_fields.AddGrowableCol( 1 )
		display_scale_fields.SetFlexibleDirection( wx.BOTH )
		display_scale_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.display_scale_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Display scale", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.display_scale_label.Wrap( -1 )

		display_scale_fields.Add( self.display_scale_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.show_scale = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.show_scale.SetToolTip( u"Display-only horizontal,vertical scale. Example: 0.5,0.5. Export uses Output scale independently. Refresh applies changes." )
		self.show_scale.SetMinSize( wx.Size( 64,-1 ) )

		display_scale_fields.Add( self.show_scale, 0, wx.EXPAND, 0 )

		self.magnifier_scale_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Zoom scale", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_scale_label.Wrap( -1 )

		display_scale_fields.Add( self.magnifier_scale_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.magnifier_show_scale = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_show_scale.SetToolTip( u"Magnifier display scale: horizontal,vertical. -1,-1 uses automatic sizing. Refresh applies changes." )
		self.magnifier_show_scale.SetMinSize( wx.Size( 64,-1 ) )

		display_scale_fields.Add( self.magnifier_show_scale, 0, wx.EXPAND, 0 )

		self.image_resolution_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Image size", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.image_resolution_label.Wrap( -1 )

		display_scale_fields.Add( self.image_resolution_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.img_resolution = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.img_resolution.SetToolTip( u"Image width,height in pixels. -1,-1 uses automatic sizing. Refresh applies changes." )
		self.img_resolution.SetMinSize( wx.Size( 64,-1 ) )

		display_scale_fields.Add( self.img_resolution, 0, wx.EXPAND, 0 )

		self.magnifier_resolution_label = wx.StaticText( self.layout_settings_pane_content, wx.ID_ANY, u"Zoom size", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_resolution_label.Wrap( -1 )

		display_scale_fields.Add( self.magnifier_resolution_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.magnifer_resolution = wx.TextCtrl( self.layout_settings_pane_content, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifer_resolution.SetToolTip( u"Magnifier width,height in pixels. -1,-1 uses automatic sizing. Refresh applies changes." )
		self.magnifer_resolution.SetMinSize( wx.Size( 64,-1 ) )

		display_scale_fields.Add( self.magnifer_resolution, 0, wx.EXPAND, 0 )


		layout_settings_pane_sizer.Add( display_scale_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.keep_magnifer_size = wx.CheckBox( self.layout_settings_pane_content, wx.ID_ANY, u"Keep zoom size", wx.DefaultPosition, wx.DefaultSize, 0 )
		layout_settings_pane_sizer.Add( self.keep_magnifer_size, 0, wx.EXPAND|wx.ALL, 3 )


		self.layout_settings_pane_content.SetSizer( layout_settings_pane_sizer )
		self.layout_settings_pane_content.Layout()
		layout_settings_pane_sizer.Fit( self.layout_settings_pane_content )
		layout_settings_pane_card_sizer.Add( self.layout_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.layout_settings_pane.SetSizer( layout_settings_pane_card_sizer )
		self.layout_settings_pane.Layout()
		layout_settings_pane_card_sizer.Fit( self.layout_settings_pane )
		settings_sections_sizer.Add( self.layout_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.custom_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		custom_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.custom_settings_pane_header = wx.Button( self.custom_settings_pane, wx.ID_ANY, u"Custom Functions", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"custom_settings_pane_header" )
		custom_settings_pane_card_sizer.Add( self.custom_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.custom_settings_pane_content = wx.Panel( self.custom_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"custom_settings_pane_content" )
		self.custom_settings_pane_content.Hide()

		custom_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		customfunc_choiceChoices = [ u"Image Enhancement", u"Image Darkening", u"Gaussian Blur" ]
		self.customfunc_choice = wx.Choice( self.custom_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), customfunc_choiceChoices, 0 )
		self.customfunc_choice.SetSelection( 0 )
		self.customfunc_choice.SetMinSize( wx.Size( 64,-1 ) )

		custom_settings_pane_sizer.Add( self.customfunc_choice, 0, wx.EXPAND|wx.ALL, 3 )

		algorithm_display_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		algorithm_display_fields.AddGrowableCol( 0 )
		algorithm_display_fields.AddGrowableCol( 1 )
		algorithm_display_fields.SetFlexibleDirection( wx.BOTH )
		algorithm_display_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.show_custom_func = wx.CheckBox( self.custom_settings_pane_content, wx.ID_ANY, u"Selected", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_custom_func.SetToolTip( u"Display the selected algorithm. Original data is still cached. Refresh applies changes." )

		algorithm_display_fields.Add( self.show_custom_func, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.show_all_func = wx.CheckBox( self.custom_settings_pane_content, wx.ID_ANY, u"All algorithms", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_all_func.SetToolTip( u"Display algorithms that fit the algorithm grid. Refresh applies changes." )

		algorithm_display_fields.Add( self.show_all_func, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		custom_settings_pane_sizer.Add( algorithm_display_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.show_original_panel = wx.CheckBox( self.custom_settings_pane_content, wx.ID_ANY, u"Show original panel", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_original_panel.SetValue(True)
		self.show_original_panel.SetToolTip( u"Include the unprocessed stitched image in custom algorithm comparisons. Applies when Selected or All algorithms is enabled. Refresh applies changes." )

		custom_settings_pane_sizer.Add( self.show_original_panel, 0, wx.EXPAND|wx.ALL, 3 )

		self.custom_algorithm_input_label = wx.StaticText( self.custom_settings_pane_content, wx.ID_ANY, u"Add function (Enter)", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.custom_algorithm_input_label.Wrap( -1 )

		custom_settings_pane_sizer.Add( self.custom_algorithm_input_label, 0, wx.EXPAND|wx.ALL, 3 )

		algorithm_add_row = wx.BoxSizer( wx.HORIZONTAL )

		self.addfunc = wx.TextCtrl( self.custom_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.addfunc.SetToolTip( u"Enter an algorithm name or path, then press Enter to add it." )
		self.addfunc.SetMinSize( wx.Size( 64,-1 ) )

		algorithm_add_row.Add( self.addfunc, 1, wx.EXPAND|wx.RIGHT, 4 )

		self.delfunc = wx.Button( self.custom_settings_pane_content, wx.ID_ANY, u"Remove", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.delfunc.SetToolTip( u"Remove the selected custom algorithm after confirmation." )

		algorithm_add_row.Add( self.delfunc, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		custom_settings_pane_sizer.Add( algorithm_add_row, 0, wx.EXPAND|wx.ALL, 3 )


		self.custom_settings_pane_content.SetSizer( custom_settings_pane_sizer )
		self.custom_settings_pane_content.Layout()
		custom_settings_pane_sizer.Fit( self.custom_settings_pane_content )
		custom_settings_pane_card_sizer.Add( self.custom_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.custom_settings_pane.SetSizer( custom_settings_pane_card_sizer )
		self.custom_settings_pane.Layout()
		custom_settings_pane_card_sizer.Fit( self.custom_settings_pane )
		settings_sections_sizer.Add( self.custom_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.magnifier_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		magnifier_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.magnifier_settings_pane_header = wx.Button( self.magnifier_settings_pane, wx.ID_ANY, u"Magnifier && Boxes", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"magnifier_settings_pane_header" )
		magnifier_settings_pane_card_sizer.Add( self.magnifier_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.magnifier_settings_pane_content = wx.Panel( self.magnifier_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"magnifier_settings_pane_content" )
		self.magnifier_settings_pane_content.Hide()

		magnifier_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		self.show_box = wx.CheckBox( self.magnifier_settings_pane_content, wx.ID_ANY, u"Boxes on images", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box.SetValue(True)
		magnifier_settings_pane_sizer.Add( self.show_box, 0, wx.EXPAND|wx.ALL, 3 )

		self.show_box_in_crop = wx.CheckBox( self.magnifier_settings_pane_content, wx.ID_ANY, u"Boxes on magnifiers", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box_in_crop.SetValue(True)
		magnifier_settings_pane_sizer.Add( self.show_box_in_crop, 0, wx.EXPAND|wx.ALL, 3 )

		magnifier_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		magnifier_fields.AddGrowableCol( 1 )
		magnifier_fields.SetFlexibleDirection( wx.BOTH )
		magnifier_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.box_line_width_label = wx.StaticText( self.magnifier_settings_pane_content, wx.ID_ANY, u"Line widths", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.box_line_width_label.Wrap( -1 )

		magnifier_fields.Add( self.box_line_width_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.line_width = wx.TextCtrl( self.magnifier_settings_pane_content, wx.ID_ANY, u"2,2", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.line_width.SetToolTip( u"Line widths for original images and magnifiers, separated by a comma." )
		self.line_width.SetMinSize( wx.Size( 64,-1 ) )

		magnifier_fields.Add( self.line_width, 0, wx.EXPAND, 0 )

		self.box_position_label = wx.StaticText( self.magnifier_settings_pane_content, wx.ID_ANY, u"Position", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.box_position_label.Wrap( -1 )

		magnifier_fields.Add( self.box_position_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		box_positionChoices = [ u"middle bottom", u"left bottom", u"right bottom", u"left top", u"right top" ]
		self.box_position = wx.Choice( self.magnifier_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), box_positionChoices, 0 )
		self.box_position.SetSelection( 0 )
		self.box_position.SetMinSize( wx.Size( 64,-1 ) )

		magnifier_fields.Add( self.box_position, 0, wx.EXPAND, 0 )

		self.magnifier_fit_label = wx.StaticText( self.magnifier_settings_pane_content, wx.ID_ANY, u"Magnifier fit", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_fit_label.Wrap( -1 )

		magnifier_fields.Add( self.magnifier_fit_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		Magnifier_formatChoices = [ u"equal width height", u"equal width", u"equal height " ]
		self.Magnifier_format = wx.Choice( self.magnifier_settings_pane_content, wx.ID_ANY, wx.Point( -1,-1 ), wx.Size( -1,-1 ), Magnifier_formatChoices, 0 )
		self.Magnifier_format.SetSelection( 0 )
		self.Magnifier_format.SetMinSize( wx.Size( 64,-1 ) )

		magnifier_fields.Add( self.Magnifier_format, 0, wx.EXPAND, 0 )


		magnifier_settings_pane_sizer.Add( magnifier_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.select_img_box = wx.CheckBox( self.magnifier_settings_pane_content, wx.ID_ANY, u"Select individual box", wx.DefaultPosition, wx.DefaultSize, 0 )
		magnifier_settings_pane_sizer.Add( self.select_img_box, 0, wx.EXPAND|wx.ALL, 3 )


		self.magnifier_settings_pane_content.SetSizer( magnifier_settings_pane_sizer )
		self.magnifier_settings_pane_content.Layout()
		magnifier_settings_pane_sizer.Fit( self.magnifier_settings_pane_content )
		magnifier_settings_pane_card_sizer.Add( self.magnifier_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.magnifier_settings_pane.SetSizer( magnifier_settings_pane_card_sizer )
		self.magnifier_settings_pane.Layout()
		magnifier_settings_pane_card_sizer.Fit( self.magnifier_settings_pane )
		settings_sections_sizer.Add( self.magnifier_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.title_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		title_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.title_settings_pane_header = wx.Button( self.title_settings_pane, wx.ID_ANY, u"Titles", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"title_settings_pane_header" )
		title_settings_pane_card_sizer.Add( self.title_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.title_settings_pane_content = wx.Panel( self.title_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"title_settings_pane_content" )
		self.title_settings_pane_content.Hide()

		title_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		self.title_auto = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Auto title", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_auto.SetValue(True)
		title_settings_pane_sizer.Add( self.title_auto, 0, wx.EXPAND|wx.ALL, 3 )

		title_parts_fields = wx.FlexGridSizer( 0, 3, 4, 6 )
		title_parts_fields.AddGrowableCol( 0 )
		title_parts_fields.AddGrowableCol( 1 )
		title_parts_fields.AddGrowableCol( 2 )
		title_parts_fields.SetFlexibleDirection( wx.BOTH )
		title_parts_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.title_show_parent = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Parent", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_parent.Enable( False )

		title_parts_fields.Add( self.title_show_parent, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_show_prefix = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Prefix", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_prefix.SetValue(True)
		self.title_show_prefix.Enable( False )

		title_parts_fields.Add( self.title_show_prefix, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_show_name = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Name", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_name.SetValue(True)
		self.title_show_name.Enable( False )

		title_parts_fields.Add( self.title_show_name, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_show_suffix = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Suffix", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_suffix.Enable( False )

		title_parts_fields.Add( self.title_show_suffix, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_exif = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"EXIF", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_exif.Enable( False )

		title_parts_fields.Add( self.title_exif, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_down_up = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Below", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.title_down_up.Enable( False )
		self.title_down_up.SetToolTip( u"Place titles below images instead of above them. Refresh applies changes." )

		title_parts_fields.Add( self.title_down_up, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		title_settings_pane_sizer.Add( title_parts_fields, 0, wx.EXPAND|wx.ALL, 3 )

		title_format_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		title_format_fields.AddGrowableCol( 1 )
		title_format_fields.SetFlexibleDirection( wx.BOTH )
		title_format_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.title_alignment_label = wx.StaticText( self.title_settings_pane_content, wx.ID_ANY, u"Alignment", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.title_alignment_label.Wrap( -1 )

		title_format_fields.Add( self.title_alignment_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		title_positionChoices = [ u"left", u"center", u"right" ]
		self.title_position = wx.Choice( self.title_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), title_positionChoices, 0 )
		self.title_position.SetSelection( 1 )
		self.title_position.Enable( False )
		self.title_position.SetMinSize( wx.Size( 64,-1 ) )

		title_format_fields.Add( self.title_position, 0, wx.EXPAND, 0 )

		self.title_font_size_label = wx.StaticText( self.title_settings_pane_content, wx.ID_ANY, u"Font size", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.title_font_size_label.Wrap( -1 )

		title_format_fields.Add( self.title_font_size_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.title_font_size = wx.TextCtrl( self.title_settings_pane_content, wx.ID_ANY, u"20", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.title_font_size.SetMinSize( wx.Size( 64,-1 ) )

		title_format_fields.Add( self.title_font_size, 0, wx.EXPAND, 0 )

		self.title_font_label = wx.StaticText( self.title_settings_pane_content, wx.ID_ANY, u"Font", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.title_font_label.Wrap( -1 )

		title_format_fields.Add( self.title_font_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		title_fontChoices = []
		self.title_font = wx.Choice( self.title_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), title_fontChoices, 0 )
		self.title_font.SetSelection( 0 )
		self.title_font.SetMinSize( wx.Size( 64,-1 ) )

		title_format_fields.Add( self.title_font, 0, wx.EXPAND, 0 )


		title_settings_pane_sizer.Add( title_format_fields, 0, wx.EXPAND|wx.ALL, 3 )

		title_rename_row = wx.BoxSizer( wx.HORIZONTAL )

		self.rename = wx.CheckBox( self.title_settings_pane_content, wx.ID_ANY, u"Rename", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.rename.Enable( False )

		title_rename_row.Add( self.rename, 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 6 )

		self.rename_edit_txt = wx.TextCtrl( self.title_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.rename_edit_txt.Enable( False )
		self.rename_edit_txt.SetMinSize( wx.Size( 64,-1 ) )

		title_rename_row.Add( self.rename_edit_txt, 1, wx.EXPAND, 0 )


		title_settings_pane_sizer.Add( title_rename_row, 0, wx.EXPAND|wx.ALL, 3 )


		self.title_settings_pane_content.SetSizer( title_settings_pane_sizer )
		self.title_settings_pane_content.Layout()
		title_settings_pane_sizer.Fit( self.title_settings_pane_content )
		title_settings_pane_card_sizer.Add( self.title_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.title_settings_pane.SetSizer( title_settings_pane_card_sizer )
		self.title_settings_pane.Layout()
		title_settings_pane_card_sizer.Fit( self.title_settings_pane )
		settings_sections_sizer.Add( self.title_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.save_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		save_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.save_settings_pane_header = wx.Button( self.save_settings_pane, wx.ID_ANY, u"Save Settings", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"save_settings_pane_header" )
		save_settings_pane_card_sizer.Add( self.save_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.save_settings_pane_content = wx.Panel( self.save_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"save_settings_pane_content" )
		self.save_settings_pane_content.Hide()

		save_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		output_folder_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		output_folder_fields.AddGrowableCol( 1 )
		output_folder_fields.SetFlexibleDirection( wx.BOTH )
		output_folder_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.output_directory_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"Output folder", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.output_directory_label.Wrap( -1 )

		output_folder_fields.Add( self.output_directory_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.out_path_button = wx.Button( self.save_settings_pane_content, wx.ID_ANY, u"Browse...", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		self.out_path_button.SetToolTip( u"Choose the output directory" )

		output_folder_fields.Add( self.out_path_button, 0, wx.EXPAND, 0 )


		save_settings_pane_sizer.Add( output_folder_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.output_directory = wx.TextCtrl( self.save_settings_pane_content, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.output_directory.SetToolTip( u"Output directory; restored with your configuration" )
		self.output_directory.SetMinSize( wx.Size( 64,-1 ) )

		save_settings_pane_sizer.Add( self.output_directory, 0, wx.EXPAND|wx.ALL, 3 )

		export_format_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		export_format_fields.AddGrowableCol( 1 )
		export_format_fields.SetFlexibleDirection( wx.BOTH )
		export_format_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.output_mode_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"Content", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.output_mode_label.Wrap( -1 )

		export_format_fields.Add( self.output_mode_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		choice_outputChoices = [ u"Stitch", u"Selected images", u"Stitch + selection", u"Magnifiers", u"Stitch + zoom", u"Selection + zoom", u"Stitch + selection + zoom" ]
		self.choice_output = wx.Choice( self.save_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), choice_outputChoices, 0 )
		self.choice_output.SetSelection( 0 )
		self.choice_output.SetToolTip( u"Choose what to export. Magnifiers are skipped when no zoom box exists; the other selected outputs are still saved." )
		self.choice_output.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.choice_output, 0, wx.EXPAND, 0 )

		self.save_format_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"Format", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.save_format_label.Wrap( -1 )

		export_format_fields.Add( self.save_format_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		save_formatChoices = [ u"jpg", u"png", u"pdf" ]
		self.save_format = wx.Choice( self.save_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), save_formatChoices, 0 )
		self.save_format.SetSelection( 0 )
		self.save_format.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.save_format, 0, wx.EXPAND, 0 )

		self.save_jpg_quality_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"JPG quality", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.save_jpg_quality_label.Wrap( -1 )

		export_format_fields.Add( self.save_jpg_quality_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		save_quality_row = wx.BoxSizer( wx.HORIZONTAL )

		self.save_quality = wx.Slider( self.save_settings_pane_content, wx.ID_ANY, 100, 0, 100, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		self.save_quality.SetToolTip( u"JPG quality, 0-100. All generated JPGs use 4:4:4. Save captures the clicked value." )
		self.save_quality.SetMinSize( wx.Size( 64,-1 ) )

		save_quality_row.Add( self.save_quality, 1, wx.EXPAND, 0 )

		self.save_quality_value = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"100", wx.DefaultPosition, wx.Size( -1,-1 ), wx.ALIGN_RIGHT )
		self.save_quality_value.Wrap( -1 )

		self.save_quality_value.SetMinSize( wx.Size( 24,-1 ) )

		save_quality_row.Add( self.save_quality_value, 0, wx.LEFT|wx.ALIGN_CENTER_VERTICAL, 4 )


		export_format_fields.Add( save_quality_row, 0, wx.EXPAND, 0 )

		self.png_compression_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"PNG compression", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.png_compression_label.Wrap( -1 )

		export_format_fields.Add( self.png_compression_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		png_compressionChoices = [ u"Fast", u"Balanced", u"Smaller file" ]
		self.png_compression = wx.Choice( self.save_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), png_compressionChoices, 0 )
		self.png_compression.SetSelection( 1 )
		self.png_compression.SetToolTip( u"All levels preserve pixels. Fast=1, Balanced=6, Smaller file=9. This controls export compression only." )
		self.png_compression.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.png_compression, 0, wx.EXPAND, 0 )

		self.pdf_compression_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"PDF compression", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.pdf_compression_label.Wrap( -1 )

		export_format_fields.Add( self.pdf_compression_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		pdf_compressionChoices = [ u"Lossless", u"Compact (JPG)" ]
		self.pdf_compression = wx.Choice( self.save_settings_pane_content, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), pdf_compressionChoices, 0 )
		self.pdf_compression.SetSelection( 0 )
		self.pdf_compression.SetToolTip( u"Lossless adds no JPG encoding. Compact embeds JPG pictures using saved JPG quality; vector titles are preserved. PNG caches avoid upstream JPG loss." )
		self.pdf_compression.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.pdf_compression, 0, wx.EXPAND, 0 )

		self.output_scale_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"Output scale", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.output_scale_label.Wrap( -1 )

		export_format_fields.Add( self.output_scale_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.output_scale = wx.TextCtrl( self.save_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.output_scale.SetToolTip( u"Export scale: horizontal,vertical. 1,1 preserves the configured image resolution. Save captures the values at click time." )
		self.output_scale.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.output_scale, 0, wx.EXPAND, 0 )

		self.magnifier_output_scale_label = wx.StaticText( self.save_settings_pane_content, wx.ID_ANY, u"Zoom output scale", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_output_scale_label.Wrap( -1 )

		export_format_fields.Add( self.magnifier_output_scale_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.magnifier_out_scale = wx.TextCtrl( self.save_settings_pane_content, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.magnifier_out_scale.SetToolTip( u"Magnifier export scale: horizontal,vertical. Independent of display scale. Save captures the values at click time." )
		self.magnifier_out_scale.SetMinSize( wx.Size( 64,-1 ) )

		export_format_fields.Add( self.magnifier_out_scale, 0, wx.EXPAND, 0 )


		save_settings_pane_sizer.Add( export_format_fields, 0, wx.EXPAND|wx.ALL, 3 )

		export_actions_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		export_actions_fields.AddGrowableCol( 0 )
		export_actions_fields.AddGrowableCol( 1 )
		export_actions_fields.SetFlexibleDirection( wx.BOTH )
		export_actions_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.auto_save_all = wx.CheckBox( self.save_settings_pane_content, wx.ID_ANY, u"Save all pages", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.auto_save_all.SetToolTip( u"Save every page in the background. Esc pauses; click Save to continue. Changed parameters start a new export." )

		export_actions_fields.Add( self.auto_save_all, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.move_file = wx.CheckBox( self.save_settings_pane_content, wx.ID_ANY, u"Move files", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.move_file.SetToolTip( u"Move selected source images instead of copying. Disabled for video inputs." )

		export_actions_fields.Add( self.move_file, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		save_settings_pane_sizer.Add( export_actions_fields, 0, wx.EXPAND|wx.ALL, 3 )


		self.save_settings_pane_content.SetSizer( save_settings_pane_sizer )
		self.save_settings_pane_content.Layout()
		save_settings_pane_sizer.Fit( self.save_settings_pane_content )
		save_settings_pane_card_sizer.Add( self.save_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.save_settings_pane.SetSizer( save_settings_pane_card_sizer )
		self.save_settings_pane.Layout()
		save_settings_pane_card_sizer.Fit( self.save_settings_pane )
		settings_sections_sizer.Add( self.save_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.colour_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		colour_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.colour_settings_pane_header = wx.Button( self.colour_settings_pane, wx.ID_ANY, u"Colour && Transparency", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"colour_settings_pane_header" )
		colour_settings_pane_card_sizer.Add( self.colour_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.colour_settings_pane_content = wx.Panel( self.colour_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"colour_settings_pane_content" )
		self.colour_settings_pane_content.Hide()

		colour_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		colour_fields = wx.FlexGridSizer( 0, 3, 4, 6 )
		colour_fields.AddGrowableCol( 0 )
		colour_fields.AddGrowableCol( 1 )
		colour_fields.AddGrowableCol( 2 )
		colour_fields.SetFlexibleDirection( wx.BOTH )
		colour_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		colourPicker_draw_cell = wx.BoxSizer( wx.VERTICAL )

		self.box_colour_label = wx.StaticText( self.colour_settings_pane_content, wx.ID_ANY, u"Box", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.box_colour_label.Wrap( -1 )

		colourPicker_draw_cell.Add( self.box_colour_label, 0, wx.EXPAND|wx.ALL, 2 )

		self.colourPicker_draw = wx.ColourPickerCtrl( self.colour_settings_pane_content, wx.ID_ANY, wx.Colour( 239, 41, 41 ), wx.DefaultPosition, wx.Size( -1,-1 ), wx.CLRP_DEFAULT_STYLE )
		self.colourPicker_draw.SetMinSize( wx.Size( 64,-1 ) )

		colourPicker_draw_cell.Add( self.colourPicker_draw, 0, wx.EXPAND|wx.ALL, 2 )


		colour_fields.Add( colourPicker_draw_cell, 0, wx.EXPAND, 0 )

		colourPicker_gap_cell = wx.BoxSizer( wx.VERTICAL )

		self.gap_colour_label = wx.StaticText( self.colour_settings_pane_content, wx.ID_ANY, u"Gap", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.gap_colour_label.Wrap( -1 )

		colourPicker_gap_cell.Add( self.gap_colour_label, 0, wx.EXPAND|wx.ALL, 2 )

		self.colourPicker_gap = wx.ColourPickerCtrl( self.colour_settings_pane_content, wx.ID_ANY, wx.Colour( 255, 255, 255 ), wx.DefaultPosition, wx.Size( -1,-1 ), wx.CLRP_DEFAULT_STYLE )
		self.colourPicker_gap.SetMinSize( wx.Size( 64,-1 ) )

		colourPicker_gap_cell.Add( self.colourPicker_gap, 0, wx.EXPAND|wx.ALL, 2 )


		colour_fields.Add( colourPicker_gap_cell, 0, wx.EXPAND, 0 )

		font_color_cell = wx.BoxSizer( wx.VERTICAL )

		self.font_colour_label = wx.StaticText( self.colour_settings_pane_content, wx.ID_ANY, u"Font", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.font_colour_label.Wrap( -1 )

		font_color_cell.Add( self.font_colour_label, 0, wx.EXPAND|wx.ALL, 2 )

		self.font_color = wx.ColourPickerCtrl( self.colour_settings_pane_content, wx.ID_ANY, wx.Colour( 0, 0, 0 ), wx.DefaultPosition, wx.Size( -1,-1 ), wx.CLRP_DEFAULT_STYLE )
		self.font_color.SetMinSize( wx.Size( 64,-1 ) )

		font_color_cell.Add( self.font_color, 0, wx.EXPAND|wx.ALL, 2 )


		colour_fields.Add( font_color_cell, 0, wx.EXPAND, 0 )


		colour_settings_pane_sizer.Add( colour_fields, 0, wx.EXPAND|wx.ALL, 3 )

		self.checkBox_auto_draw_color = wx.CheckBox( self.colour_settings_pane_content, wx.ID_ANY, u"Automatic box colour", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.checkBox_auto_draw_color.SetValue(True)
		colour_settings_pane_sizer.Add( self.checkBox_auto_draw_color, 0, wx.EXPAND|wx.ALL, 3 )

		opacity_fields = wx.FlexGridSizer( 0, 2, 4, 6 )
		opacity_fields.AddGrowableCol( 1 )
		opacity_fields.SetFlexibleDirection( wx.BOTH )
		opacity_fields.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.background_alpha_label = wx.StaticText( self.colour_settings_pane_content, wx.ID_ANY, u"Background opacity", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.background_alpha_label.Wrap( -1 )

		opacity_fields.Add( self.background_alpha_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.background_slider = wx.Slider( self.colour_settings_pane_content, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		self.background_slider.SetToolTip( u"Opacity of the canvas background: 0 transparent, 255 opaque. JPG export flattens transparency onto the chosen gap colour." )
		self.background_slider.SetMinSize( wx.Size( 64,-1 ) )

		opacity_fields.Add( self.background_slider, 0, wx.EXPAND, 0 )

		self.foreground_alpha_label = wx.StaticText( self.colour_settings_pane_content, wx.ID_ANY, u"Image opacity", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.foreground_alpha_label.Wrap( -1 )

		opacity_fields.Add( self.foreground_alpha_label, 0, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.foreground_slider = wx.Slider( self.colour_settings_pane_content, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		self.foreground_slider.SetToolTip( u"Opacity of image content: 0 transparent, 255 opaque." )
		self.foreground_slider.SetMinSize( wx.Size( 64,-1 ) )

		opacity_fields.Add( self.foreground_slider, 0, wx.EXPAND, 0 )


		colour_settings_pane_sizer.Add( opacity_fields, 0, wx.EXPAND|wx.ALL, 3 )


		self.colour_settings_pane_content.SetSizer( colour_settings_pane_sizer )
		self.colour_settings_pane_content.Layout()
		colour_settings_pane_sizer.Fit( self.colour_settings_pane_content )
		colour_settings_pane_card_sizer.Add( self.colour_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.colour_settings_pane.SetSizer( colour_settings_pane_card_sizer )
		self.colour_settings_pane.Layout()
		colour_settings_pane_card_sizer.Fit( self.colour_settings_pane )
		settings_sections_sizer.Add( self.colour_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )

		self.configuration_settings_pane = SettingsSection( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE )
		configuration_settings_pane_card_sizer = wx.BoxSizer( wx.VERTICAL )

		self.configuration_settings_pane_header = wx.Button( self.configuration_settings_pane, wx.ID_ANY, u"Configuration", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BU_LEFT|wx.BORDER_NONE, wx.DefaultValidator, u"configuration_settings_pane_header" )
		configuration_settings_pane_card_sizer.Add( self.configuration_settings_pane_header, 0, wx.EXPAND|wx.ALL, 1 )

		self.configuration_settings_pane_content = wx.Panel( self.configuration_settings_pane, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL|wx.BORDER_NONE, u"configuration_settings_pane_content" )
		self.configuration_settings_pane_content.Hide()

		configuration_settings_pane_sizer = wx.BoxSizer( wx.VERTICAL )

		configuration_buttons = wx.FlexGridSizer( 0, 3, 3, 6 )
		configuration_buttons.AddGrowableCol( 0 )
		configuration_buttons.AddGrowableCol( 1 )
		configuration_buttons.AddGrowableCol( 2 )
		configuration_buttons.SetFlexibleDirection( wx.BOTH )
		configuration_buttons.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.load_config_button = wx.Button( self.configuration_settings_pane_content, wx.ID_ANY, u"Load", wx.Point( -1,-1 ), wx.Size( 50,-1 ), 0 )
		self.load_config_button.SetToolTip( u"Load your manually saved configuration, including fold states and settings width." )

		configuration_buttons.Add( self.load_config_button, 0, wx.EXPAND, 0 )

		self.save_config_button = wx.Button( self.configuration_settings_pane_content, wx.ID_ANY, u"Save", wx.DefaultPosition, wx.Size( 50,-1 ), 0 )
		self.save_config_button.SetToolTip( u"Save a reusable configuration snapshot. The latest session is also saved automatically on close." )

		configuration_buttons.Add( self.save_config_button, 0, wx.EXPAND, 0 )

		self.reset_config_button = wx.Button( self.configuration_settings_pane_content, wx.ID_ANY, u"Reset", wx.DefaultPosition, wx.Size( 50,-1 ), 0 )
		self.reset_config_button.SetToolTip( u"Restore default settings, fold states and automatic sidebar width. Your manual snapshot is kept." )

		configuration_buttons.Add( self.reset_config_button, 0, wx.EXPAND, 0 )


		configuration_settings_pane_sizer.Add( configuration_buttons, 0, wx.EXPAND|wx.ALL, 3 )


		self.configuration_settings_pane_content.SetSizer( configuration_settings_pane_sizer )
		self.configuration_settings_pane_content.Layout()
		configuration_settings_pane_sizer.Fit( self.configuration_settings_pane_content )
		configuration_settings_pane_card_sizer.Add( self.configuration_settings_pane_content, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 1 )


		self.configuration_settings_pane.SetSizer( configuration_settings_pane_card_sizer )
		self.configuration_settings_pane.Layout()
		configuration_settings_pane_card_sizer.Fit( self.configuration_settings_pane )
		settings_sections_sizer.Add( self.configuration_settings_pane, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4 )


		self.scrolledWindow_set.SetSizer( settings_sections_sizer )
		self.scrolledWindow_set.Layout()
		settings_sections_sizer.Fit( self.scrolledWindow_set )
		self.viewer_settings_splitter.SplitVertically( self.scrolledWindow_img, self.scrolledWindow_set, -1 )
		viewer_container_sizer.Add( self.viewer_settings_splitter, 1, wx.EXPAND, 5 )


		self.viewer_container_panel.SetSizer( viewer_container_sizer )
		self.viewer_container_panel.Layout()
		viewer_container_sizer.Fit( self.viewer_container_panel )
		main_layout_sizer.Add( self.viewer_container_panel, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( main_layout_sizer )
		self.Layout()
		main_layout_sizer.Fit( self )
		self.main_status_bar = self.CreateStatusBar( 4, wx.STB_SIZEGRIP, wx.ID_ANY )
		self.main_menu_bar = wx.MenuBar( 0 )
		self.file_menu = wx.Menu()
		self.open_menu = wx.Menu()
		self.menu_open_sequential = wx.MenuItem( self.open_menu, wx.ID_ANY, u"Sequential"+ u"\t" + u"Ctrl+E", u"one dir mul limg", wx.ITEM_NORMAL )
		self.open_menu.Append( self.menu_open_sequential )

		self.menu_open_auto = wx.MenuItem( self.open_menu, wx.ID_ANY, u"Parallel auto"+ u"\t" + u"Ctrl+A", u"one dir mul dir", wx.ITEM_NORMAL )
		self.open_menu.Append( self.menu_open_auto )

		self.menu_open_manual = wx.MenuItem( self.open_menu, wx.ID_ANY, u"Parallel manual"+ u"\t" + u"Ctrl+M", u"one dir mul dir", wx.ITEM_NORMAL )
		self.open_menu.Append( self.menu_open_manual )

		self.menu_open_filelist = wx.MenuItem( self.open_menu, wx.ID_ANY, u"Image File List"+ u"\t" + u"Ctrl+F", u"one dir mul dir", wx.ITEM_NORMAL )
		self.open_menu.Append( self.menu_open_filelist )

		self.file_menu.AppendSubMenu( self.open_menu, u"Open" )

		self.menu_output = wx.MenuItem( self.file_menu, wx.ID_ANY, u"Select output path"+ u"\t" + u"Ctrl+O", wx.EmptyString, wx.ITEM_NORMAL )
		self.file_menu.Append( self.menu_output )

		self.load_parallel_file_list_menu_item = wx.MenuItem( self.file_menu, wx.ID_ANY, u"Input flist - Parallel manual"+ u"\t" + u"Ctrl+I", wx.EmptyString, wx.ITEM_NORMAL )
		self.file_menu.Append( self.load_parallel_file_list_menu_item )

		self.save_parallel_file_list_menu_item = wx.MenuItem( self.file_menu, wx.ID_ANY, u"Save flist - Parallel manual"+ u"\t" + u"Ctrl+P", wx.EmptyString, wx.ITEM_NORMAL )
		self.file_menu.Append( self.save_parallel_file_list_menu_item )

		self.main_menu_bar.Append( self.file_menu, u"File" )

		self.edit_menu = wx.Menu()
		self.menu_next = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Next"+ u"\t" + u"Ctrl+N", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_next )

		self.menu_last = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Last"+ u"\t" + u"Ctrl+L", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_last )

		self.menu_save = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Save"+ u"\t" + u"Ctrl+S", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_save )

		self.menu_pause_tasks = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Pause saving / playback"+ u"\t" + u"Esc", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_pause_tasks )

		self.menu_cancel_save = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Cancel saving", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_cancel_save )

		self.menu_refresh = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Refresh"+ u"\t" + u"Ctrl+R", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_refresh )

		self.menu_hidden = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"hidden"+ u"\t" + u"Ctrl+H", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_hidden )

		self.menu_up = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Up", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_up )

		self.menu_down = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Down", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_down )

		self.menu_right = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"Right", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_right )

		self.menu_left = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"left", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_left )

		self.menu_delete_box = wx.MenuItem( self.edit_menu, wx.ID_ANY, u"delete_box", wx.EmptyString, wx.ITEM_NORMAL )
		self.edit_menu.Append( self.menu_delete_box )

		self.main_menu_bar.Append( self.edit_menu, u"Edit" )

		self.help_menu = wx.Menu()
		self.index_table = wx.MenuItem( self.help_menu, wx.ID_ANY, u"Index table"+ u"\t" + u"F2", wx.EmptyString, wx.ITEM_NORMAL )
		self.help_menu.Append( self.index_table )

		self.menu_about = wx.MenuItem( self.help_menu, wx.ID_ANY, u"About"+ u"\t" + u"F1", wx.EmptyString, wx.ITEM_NORMAL )
		self.help_menu.Append( self.menu_about )

		self.main_menu_bar.Append( self.help_menu, u"Help" )

		self.SetMenuBar( self.main_menu_bar )


		self.Centre( wx.BOTH )

		# Connect Events
		self.Bind( wx.EVT_SIZE, self.frame_resize )
		self.button_open_all.Bind( wx.EVT_BUTTON, self.open_all_img )
		self.save_butoon.Bind( wx.EVT_BUTTON, self.save_img )
		self.left_arrow_button.Bind( wx.EVT_BUTTON, self.last_img )
		self.play.Bind( wx.EVT_BUTTON, self.last_img )
		self.right_arrow_button.Bind( wx.EVT_BUTTON, self.next_img )
		self.refresh_button.Bind( wx.EVT_BUTTON, self.refresh )
		self.slider_value.Bind( wx.EVT_TEXT_ENTER, self.slider_value_change )
		self.slider_img.Bind( wx.EVT_SCROLL, self.skip_to_n_img )
		self.magnifier.Bind( wx.EVT_TOGGLEBUTTON, self.magnifier_fc )
		self.rotation.Bind( wx.EVT_TOGGLEBUTTON, self.rotation_fc )
		self.flip.Bind( wx.EVT_TOGGLEBUTTON, self.flip_fc )
		self.viewer_settings_splitter.Bind( wx.EVT_SPLITTER_SASH_POS_CHANGED, self.split_sash_pos_changed )
		self.viewer_settings_splitter.Bind( wx.EVT_SPLITTER_SASH_POS_CHANGING, self.split_sash_pos_changing )
		self.settings_expand_button.Bind( wx.EVT_BUTTON, self.expand_settings_sections )
		self.settings_collapse_button.Bind( wx.EVT_BUTTON, self.collapse_settings_sections )
		self.input_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.video_mode.Bind( wx.EVT_CHECKBOX, self.on_enable_video_mode )
		self.parallel_sequential.Bind( wx.EVT_CHECKBOX, self.parallel_sequential_fc )
		self.parallel_to_sequential.Bind( wx.EVT_CHECKBOX, self.parallel_to_sequential_fc )
		self.performance_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.layout_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.choice_normalized_size.Bind( wx.EVT_CHOICE, self.change_img_stitch_mode )
		self.custom_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.magnifier_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.select_img_box.Bind( wx.EVT_CHECKBOX, self.select_img_box_func )
		self.title_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.title_auto.Bind( wx.EVT_CHECKBOX, self.title_auto_fc )
		self.title_down_up.Bind( wx.EVT_CHECKBOX, self.title_down_up_fc )
		self.save_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.out_path_button.Bind( wx.EVT_BUTTON, self.out_path )
		self.save_format.Bind( wx.EVT_CHOICE, self.change_img_stitch_mode )
		self.colour_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.colourPicker_gap.Bind( wx.EVT_COLOURPICKER_CHANGED, self.colour_change )
		self.background_slider.Bind( wx.EVT_SCROLL, self.background_alpha )
		self.foreground_slider.Bind( wx.EVT_SCROLL, self.foreground_alpha )
		self.configuration_settings_pane_header.Bind( wx.EVT_BUTTON, self.on_settings_section_changed )
		self.load_config_button.Bind( wx.EVT_BUTTON, self.load_configuration )
		self.save_config_button.Bind( wx.EVT_BUTTON, self.save_configuration )
		self.reset_config_button.Bind( wx.EVT_BUTTON, self.reset_configuration )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_img, id = self.menu_open_sequential.GetId() )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_dir_auto, id = self.menu_open_auto.GetId() )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_dir_manual, id = self.menu_open_manual.GetId() )
		self.Bind( wx.EVT_MENU, self.onefilelist, id = self.menu_open_filelist.GetId() )
		self.Bind( wx.EVT_MENU, self.out_path, id = self.menu_output.GetId() )
		self.Bind( wx.EVT_MENU, self.input_flist_parallel_manual, id = self.load_parallel_file_list_menu_item.GetId() )
		self.Bind( wx.EVT_MENU, self.save_flist_parallel_manual, id = self.save_parallel_file_list_menu_item.GetId() )
		self.Bind( wx.EVT_MENU, self.next_img, id = self.menu_next.GetId() )
		self.Bind( wx.EVT_MENU, self.last_img, id = self.menu_last.GetId() )
		self.Bind( wx.EVT_MENU, self.save_img, id = self.menu_save.GetId() )
		self.Bind( wx.EVT_MENU, self.pause_tasks, id = self.menu_pause_tasks.GetId() )
		self.Bind( wx.EVT_MENU, self.cancel_save_task, id = self.menu_cancel_save.GetId() )
		self.Bind( wx.EVT_MENU, self.refresh, id = self.menu_refresh.GetId() )
		self.Bind( wx.EVT_MENU, self.hidden, id = self.menu_hidden.GetId() )
		self.Bind( wx.EVT_MENU, self.up_img, id = self.menu_up.GetId() )
		self.Bind( wx.EVT_MENU, self.down_img, id = self.menu_down.GetId() )
		self.Bind( wx.EVT_MENU, self.right_img, id = self.menu_right.GetId() )
		self.Bind( wx.EVT_MENU, self.left_img, id = self.menu_left.GetId() )
		self.Bind( wx.EVT_MENU, self.delete_box, id = self.menu_delete_box.GetId() )
		self.Bind( wx.EVT_MENU, self.index_table_gui, id = self.index_table.GetId() )
		self.Bind( wx.EVT_MENU, self.about_gui, id = self.menu_about.GetId() )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def frame_resize( self, event ):
		event.Skip()

	def open_all_img( self, event ):
		event.Skip()

	def save_img( self, event ):
		event.Skip()

	def last_img( self, event ):
		event.Skip()


	def next_img( self, event ):
		event.Skip()

	def refresh( self, event ):
		event.Skip()

	def slider_value_change( self, event ):
		event.Skip()

	def skip_to_n_img( self, event ):
		event.Skip()

	def magnifier_fc( self, event ):
		event.Skip()

	def rotation_fc( self, event ):
		event.Skip()

	def flip_fc( self, event ):
		event.Skip()

	def split_sash_pos_changed( self, event ):
		event.Skip()

	def split_sash_pos_changing( self, event ):
		event.Skip()

	def expand_settings_sections( self, event ):
		event.Skip()

	def collapse_settings_sections( self, event ):
		event.Skip()

	def on_settings_section_changed( self, event ):
		event.Skip()

	def on_enable_video_mode( self, event ):
		event.Skip()

	def parallel_sequential_fc( self, event ):
		event.Skip()

	def parallel_to_sequential_fc( self, event ):
		event.Skip()



	def change_img_stitch_mode( self, event ):
		event.Skip()



	def select_img_box_func( self, event ):
		event.Skip()


	def title_auto_fc( self, event ):
		event.Skip()

	def title_down_up_fc( self, event ):
		event.Skip()


	def out_path( self, event ):
		event.Skip()



	def colour_change( self, event ):
		event.Skip()

	def background_alpha( self, event ):
		event.Skip()

	def foreground_alpha( self, event ):
		event.Skip()


	def load_configuration( self, event ):
		event.Skip()

	def save_configuration( self, event ):
		event.Skip()

	def reset_configuration( self, event ):
		event.Skip()

	def one_dir_mul_img( self, event ):
		event.Skip()

	def one_dir_mul_dir_auto( self, event ):
		event.Skip()

	def one_dir_mul_dir_manual( self, event ):
		event.Skip()

	def onefilelist( self, event ):
		event.Skip()


	def input_flist_parallel_manual( self, event ):
		event.Skip()

	def save_flist_parallel_manual( self, event ):
		event.Skip()




	def pause_tasks( self, event ):
		event.Skip()

	def cancel_save_task( self, event ):
		event.Skip()


	def hidden( self, event ):
		event.Skip()

	def up_img( self, event ):
		event.Skip()

	def down_img( self, event ):
		event.Skip()

	def right_img( self, event ):
		event.Skip()

	def left_img( self, event ):
		event.Skip()

	def delete_box( self, event ):
		event.Skip()

	def index_table_gui( self, event ):
		event.Skip()

	def about_gui( self, event ):
		event.Skip()


