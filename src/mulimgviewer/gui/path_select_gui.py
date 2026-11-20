# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 4.2.1-0-g80c4cb6)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc
import wx.richtext

###########################################################################
## Class PathSelectFrameGui
###########################################################################

class PathSelectFrameGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Parallel sources", pos = wx.DefaultPosition, size = wx.Size( 520,360 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.Size( 440,320 ), wx.DefaultSize )
		self.SetBackgroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_3DFACE ) )

		path_selection_layout = wx.BoxSizer( wx.VERTICAL )

		self.source_hint = wx.StaticText( self, wx.ID_ANY, u"One folder per line, in display order.", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.source_hint.Wrap( -1 )

		self.source_hint.SetToolTip( u"Apply and return loads the list. Cancel keeps the current input. Closing this window also applies the list. Ctrl+Enter applies; Esc cancels." )

		path_selection_layout.Add( self.source_hint, 0, wx.LEFT|wx.RIGHT|wx.TOP, 12 )

		path_actions_sizer = wx.BoxSizer( wx.HORIZONTAL )

		self.browse_button = wx.Button( self, wx.ID_ANY, u"Add sources...", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.browse_button.SetToolTip( u"Add image folders or video files." )

		path_actions_sizer.Add( self.browse_button, 0, wx.RIGHT, 6 )

		self.button_clear_last = wx.Button( self, wx.ID_ANY, u"Remove last", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.button_clear_last.SetToolTip( u"Remove the last source (Ctrl+Shift+Backspace)." )

		path_actions_sizer.Add( self.button_clear_last, 0, wx.RIGHT, 6 )

		self.button_clear_all = wx.Button( self, wx.ID_ANY, u"Clear all", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.button_clear_all.SetToolTip( u"Clear the list (Ctrl+Shift+Delete)." )

		path_actions_sizer.Add( self.button_clear_all, 0, 0, 0 )


		path_selection_layout.Add( path_actions_sizer, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 12 )

		self.paths_text = wx.richtext.RichTextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0|wx.VSCROLL|wx.HSCROLL|wx.BORDER_SIMPLE|wx.WANTS_CHARS )
		self.paths_text.SetToolTip( u"One folder or video file per line. You can paste paths, edit them, and change their order. Ctrl+A selects text; Ctrl+Z undoes edits." )
		self.paths_text.SetMinSize( wx.Size( -1,100 ) )

		path_selection_layout.Add( self.paths_text, 1, wx.EXPAND|wx.ALL, 12 )

		path_footer_sizer = wx.BoxSizer( wx.HORIZONTAL )

		self.source_count = wx.StaticText( self, wx.ID_ANY, u"0 sources", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.source_count.Wrap( -1 )

		path_footer_sizer.Add( self.source_count, 1, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.cancel_button = wx.Button( self, wx.ID_CANCEL, u"Cancel", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.cancel_button.SetToolTip( u"Return without applying the list (Esc)." )

		path_footer_sizer.Add( self.cancel_button, 0, wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, 6 )

		self.apply_button = wx.Button( self, wx.ID_OK, u"Apply and return", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.apply_button.SetToolTip( u"Apply the list and return (Ctrl+Enter). Closing this window also applies the list." )

		path_footer_sizer.Add( self.apply_button, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		path_selection_layout.Add( path_footer_sizer, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 12 )


		self.SetSizer( path_selection_layout )
		self.Layout()

		self.Centre( wx.BOTH )

		# Connect Events
		self.browse_button.Bind( wx.EVT_BUTTON, self.on_browse )
		self.button_clear_last.Bind( wx.EVT_BUTTON, self.clear_last_path )
		self.button_clear_all.Bind( wx.EVT_BUTTON, self.clear_all_path )
		self.paths_text.Bind( wx.EVT_TEXT, self.on_paths_changed )
		self.cancel_button.Bind( wx.EVT_BUTTON, self.on_cancel )
		self.apply_button.Bind( wx.EVT_BUTTON, self.on_apply )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def on_browse( self, event ):
		event.Skip()

	def clear_last_path( self, event ):
		event.Skip()

	def clear_all_path( self, event ):
		event.Skip()

	def on_paths_changed( self, event ):
		event.Skip()

	def on_cancel( self, event ):
		event.Skip()

	def on_apply( self, event ):
		event.Skip()


