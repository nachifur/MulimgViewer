# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 4.2.1-0-g80c4cb6)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

from .virtual_index_list import VirtualIndexList
import wx
import wx.xrc

###########################################################################
## Class IndexTableGui
###########################################################################

class IndexTableGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Image / Video Index", pos = wx.DefaultPosition, size = wx.Size( 950,520 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.Size( 750,440 ), wx.DefaultSize )

		bSizer2 = wx.BoxSizer( wx.VERTICAL )

		self.m_panel1 = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		wSizer4 = wx.FlexGridSizer( 5, 1, 0, 0 )
		wSizer4.AddGrowableCol( 0 )
		wSizer4.AddGrowableRow( 3 )
		wSizer4.SetFlexibleDirection( wx.BOTH )
		wSizer4.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.summary = wx.StaticText( self.m_panel1, wx.ID_ANY, u"Index", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.summary.Wrap( -1 )

		wSizer4.Add( self.summary, 0, wx.ALL|wx.EXPAND, 5 )

		self.m_panel2 = wx.Panel( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		index_layout = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		view_choiceChoices = [ u"Visual items", u"Pages", u"Sources" ]
		self.view_choice = wx.Choice( self.m_panel2, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), view_choiceChoices, 0 )
		self.view_choice.SetSelection( 0 )
		index_layout.Add( self.view_choice, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_search_txt = wx.SearchCtrl( self.m_panel2, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( 240,-1 ), wx.TE_PROCESS_ENTER )
		self.m_search_txt.ShowSearchButton( True )
		self.m_search_txt.ShowCancelButton( True )
		index_layout.Add( self.m_search_txt, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.b_last_txt = wx.Button( self.m_panel2, wx.ID_ANY, u"<", wx.DefaultPosition, wx.Size( 50,-1 ), wx.BORDER_NONE )
		self.b_last_txt.SetFont( wx.Font( wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		index_layout.Add( self.b_last_txt, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.b_next_txt = wx.Button( self.m_panel2, wx.ID_ANY, u">", wx.DefaultPosition, wx.Size( 50,-1 ), wx.BORDER_NONE )
		self.b_next_txt.SetFont( wx.Font( wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		index_layout.Add( self.b_next_txt, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.refresh_button = wx.Button( self.m_panel2, wx.ID_ANY, u"Refresh", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		index_layout.Add( self.refresh_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.export_button = wx.Button( self.m_panel2, wx.ID_ANY, u"Export", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		index_layout.Add( self.export_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.locate_main_button = wx.Button( self.m_panel2, wx.ID_ANY, u"Go to current ID", wx.Point( -1,-1 ), wx.Size( -1,-1 ), wx.BORDER_NONE )
		self.locate_main_button.SetToolTip( u"Locate the last clicked image on the displayed page; otherwise locate its first image" )

		index_layout.Add( self.locate_main_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.jump_button = wx.Button( self.m_panel2, wx.ID_ANY, u"Go to image", wx.Point( -1,-1 ), wx.Size( -1,-1 ), wx.BORDER_NONE )
		self.jump_button.SetToolTip( u"Go to the selected image and update the main status bar" )

		index_layout.Add( self.jump_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		self.m_panel2.SetSizer( index_layout )
		self.m_panel2.Layout()
		index_layout.Fit( self.m_panel2 )
		wSizer4.Add( self.m_panel2, 1, wx.EXPAND |wx.ALL, 5 )

		self.match_label = wx.StaticText( self.m_panel1, wx.ID_ANY, u"Select a row to inspect its paths; double-click to open its page", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.match_label.Wrap( -1 )

		wSizer4.Add( self.match_label, 0, wx.ALL|wx.EXPAND, 5 )

		self.index_details_splitter = wx.SplitterWindow( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.SP_3D|wx.SP_LIVE_UPDATE )
		self.index_details_splitter.SetSashGravity( 1.0 )
		self.index_details_splitter.Bind( wx.EVT_IDLE, self.index_details_splitterOnIdle )
		self.index_details_splitter.SetMinimumPaneSize( 80 )

		self.index_details_splitter.SetToolTip( u"Drag the divider to resize the index and path details" )
		self.index_details_splitter.SetMinSize( wx.Size( -1,220 ) )

		self.index_list_panel = wx.Panel( self.index_details_splitter, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		self.index_list_panel.SetMinSize( wx.Size( -1,120 ) )

		index_list_panel_layout = wx.BoxSizer( wx.VERTICAL )

		self.index_table = VirtualIndexList( self.index_list_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL )
		self.index_table.SetMinSize( wx.Size( -1,120 ) )

		index_list_panel_layout.Add( self.index_table, 1, wx.EXPAND, 0 )


		self.index_list_panel.SetSizer( index_list_panel_layout )
		self.index_list_panel.Layout()
		index_list_panel_layout.Fit( self.index_list_panel )
		self.index_details_panel = wx.Panel( self.index_details_splitter, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		self.index_details_panel.SetMinSize( wx.Size( -1,80 ) )

		index_details_panel_layout = wx.BoxSizer( wx.VERTICAL )

		self.path_details = wx.TextCtrl( self.index_details_panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TE_MULTILINE|wx.TE_READONLY )
		self.path_details.SetMinSize( wx.Size( -1,80 ) )

		index_details_panel_layout.Add( self.path_details, 1, wx.EXPAND, 0 )


		self.index_details_panel.SetSizer( index_details_panel_layout )
		self.index_details_panel.Layout()
		index_details_panel_layout.Fit( self.index_details_panel )
		self.index_details_splitter.SplitHorizontally( self.index_list_panel, self.index_details_panel, -110 )
		wSizer4.Add( self.index_details_splitter, 1, wx.ALL|wx.EXPAND, 5 )

		path_actions = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.copy_source_button = wx.Button( self.m_panel1, wx.ID_ANY, u"Copy original source", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		path_actions.Add( self.copy_source_button, 0, wx.ALL|wx.EXPAND, 5 )

		self.copy_frame_button = wx.Button( self.m_panel1, wx.ID_ANY, u"Copy image / frame path", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		path_actions.Add( self.copy_frame_button, 0, wx.ALL|wx.EXPAND, 5 )


		wSizer4.Add( path_actions, 0, wx.EXPAND, 5 )


		self.m_panel1.SetSizer( wSizer4 )
		self.m_panel1.Layout()
		wSizer4.Fit( self.m_panel1 )
		bSizer2.Add( self.m_panel1, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( bSizer2 )
		self.Layout()

		self.Centre( wx.BOTH )

		# Connect Events
		self.Bind( wx.EVT_CLOSE, self.close )
		self.view_choice.Bind( wx.EVT_CHOICE, self.change_view )
		self.m_search_txt.Bind( wx.EVT_SEARCHCTRL_CANCEL_BTN, self.clear_search )
		self.m_search_txt.Bind( wx.EVT_SEARCHCTRL_SEARCH_BTN, self.search_txt )
		self.m_search_txt.Bind( wx.EVT_TEXT_ENTER, self.search_txt )
		self.b_last_txt.Bind( wx.EVT_BUTTON, self.last_txt )
		self.b_next_txt.Bind( wx.EVT_BUTTON, self.next_txt )
		self.refresh_button.Bind( wx.EVT_BUTTON, self.refresh_index )
		self.export_button.Bind( wx.EVT_BUTTON, self.export_index )
		self.locate_main_button.Bind( wx.EVT_BUTTON, self.locate_main_image )
		self.jump_button.Bind( wx.EVT_BUTTON, self.jump_selected )
		self.index_table.Bind( wx.EVT_LIST_ITEM_ACTIVATED, self.activate_row )
		self.index_table.Bind( wx.EVT_LIST_ITEM_SELECTED, self.select_row )
		self.copy_source_button.Bind( wx.EVT_BUTTON, self.copy_source_path )
		self.copy_frame_button.Bind( wx.EVT_BUTTON, self.copy_frame_path )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def close( self, event ):
		event.Skip()

	def change_view( self, event ):
		event.Skip()

	def clear_search( self, event ):
		event.Skip()

	def search_txt( self, event ):
		event.Skip()


	def last_txt( self, event ):
		event.Skip()

	def next_txt( self, event ):
		event.Skip()

	def refresh_index( self, event ):
		event.Skip()

	def export_index( self, event ):
		event.Skip()

	def locate_main_image( self, event ):
		event.Skip()

	def jump_selected( self, event ):
		event.Skip()

	def activate_row( self, event ):
		event.Skip()

	def select_row( self, event ):
		event.Skip()

	def copy_source_path( self, event ):
		event.Skip()

	def copy_frame_path( self, event ):
		event.Skip()

	def index_details_splitterOnIdle( self, event ):
		self.index_details_splitter.SetSashPosition( -110 )
		self.index_details_splitter.Unbind( wx.EVT_IDLE )


