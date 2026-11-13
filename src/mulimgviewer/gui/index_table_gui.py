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
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Image / Video Index", pos = wx.DefaultPosition, size = wx.Size( 1150,650 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.Size( 750,400 ), wx.DefaultSize )

		index_layout = wx.BoxSizer( wx.VERTICAL )

		self.summary = wx.StaticText( self, wx.ID_ANY, u"Index", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.summary.Wrap( -1 )

		index_layout.Add( self.summary, 0, wx.ALL|wx.EXPAND, 5 )

		index_toolbar = wx.BoxSizer( wx.HORIZONTAL )

		view_choiceChoices = [ u"Sources", u"Pages", u"Visual items" ]
		self.view_choice = wx.Choice( self, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), view_choiceChoices, 0 )
		self.view_choice.SetSelection( 2 )
		index_toolbar.Add( self.view_choice, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_search_txt = wx.SearchCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( 240,-1 ), wx.TE_PROCESS_ENTER )
		self.m_search_txt.ShowSearchButton( True )
		self.m_search_txt.ShowCancelButton( True )
		index_toolbar.Add( self.m_search_txt, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.b_last_txt = wx.Button( self, wx.ID_ANY, u"<", wx.DefaultPosition, wx.Size( -1,30 ), wx.BORDER_NONE )
		self.b_last_txt.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		index_toolbar.Add( self.b_last_txt, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.b_next_txt = wx.Button( self, wx.ID_ANY, u">", wx.DefaultPosition, wx.Size( -1,30 ), wx.BORDER_NONE )
		self.b_next_txt.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		index_toolbar.Add( self.b_next_txt, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.refresh_button = wx.Button( self, wx.ID_ANY, u"Refresh", wx.DefaultPosition, wx.Size( -1,30 ), wx.BORDER_NONE )
		index_toolbar.Add( self.refresh_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.export_button = wx.Button( self, wx.ID_ANY, u"Export", wx.DefaultPosition, wx.Size( -1,30 ), wx.BORDER_NONE )
		index_toolbar.Add( self.export_button, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		index_layout.Add( index_toolbar, 0, wx.ALL|wx.EXPAND, 5 )

		self.match_label = wx.StaticText( self, wx.ID_ANY, u"Select a row to inspect its paths; double-click to open its page", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.match_label.Wrap( -1 )

		index_layout.Add( self.match_label, 0, wx.ALL|wx.EXPAND, 5 )

		self.index_table = VirtualIndexList( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL )
		index_layout.Add( self.index_table, 1, wx.ALL|wx.EXPAND, 5 )

		self.path_details = wx.TextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,90 ), wx.TE_MULTILINE|wx.TE_READONLY )
		index_layout.Add( self.path_details, 0, wx.ALL|wx.EXPAND, 5 )

		path_actions = wx.BoxSizer( wx.HORIZONTAL )

		self.copy_frame_button = wx.Button( self, wx.ID_ANY, u"Copy image / frame path", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		path_actions.Add( self.copy_frame_button, 0, wx.ALL|wx.EXPAND, 5 )

		self.copy_source_button = wx.Button( self, wx.ID_ANY, u"Copy original source", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		path_actions.Add( self.copy_source_button, 0, wx.ALL|wx.EXPAND, 5 )

		self.jump_button = wx.Button( self, wx.ID_ANY, u"Go to page", wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		path_actions.Add( self.jump_button, 0, wx.ALL|wx.EXPAND, 5 )


		index_layout.Add( path_actions, 0, wx.ALL|wx.EXPAND, 5 )


		self.SetSizer( index_layout )
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
		self.index_table.Bind( wx.EVT_LIST_ITEM_ACTIVATED, self.activate_row )
		self.index_table.Bind( wx.EVT_LIST_ITEM_SELECTED, self.select_row )
		self.copy_frame_button.Bind( wx.EVT_BUTTON, self.copy_frame_path )
		self.copy_source_button.Bind( wx.EVT_BUTTON, self.copy_source_path )
		self.jump_button.Bind( wx.EVT_BUTTON, self.jump_selected )

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

	def activate_row( self, event ):
		event.Skip()

	def select_row( self, event ):
		event.Skip()

	def copy_frame_path( self, event ):
		event.Skip()

	def copy_source_path( self, event ):
		event.Skip()

	def jump_selected( self, event ):
		event.Skip()


