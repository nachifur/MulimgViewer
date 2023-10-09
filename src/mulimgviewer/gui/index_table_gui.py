# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 3.10.1-0-g8feb16b3)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc
import wx.richtext

###########################################################################
## Class IndexTableGui
###########################################################################

class IndexTableGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Index Table", pos = wx.DefaultPosition, size = wx.Size( -1,-1 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		fgSizer2 = wx.FlexGridSizer( 2, 1, 0, 0 )
		fgSizer2.SetFlexibleDirection( wx.BOTH )
		fgSizer2.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		wSizer1 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_search_txt = wx.SearchCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( 100,-1 ), wx.TE_PROCESS_ENTER )
		self.m_search_txt.ShowSearchButton( True )
		self.m_search_txt.ShowCancelButton( False )
		wSizer1.Add( self.m_search_txt, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.b_last_txt = wx.Button( self, wx.ID_ANY, u"<", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.b_last_txt.SetMinSize( wx.Size( 50,-1 ) )

		wSizer1.Add( self.b_last_txt, 0, wx.ALL, 5 )

		self.b_next_txt = wx.Button( self, wx.ID_ANY, u">", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.b_next_txt.SetMinSize( wx.Size( 50,-1 ) )

		wSizer1.Add( self.b_next_txt, 0, wx.ALL, 5 )


		fgSizer2.Add( wSizer1, 1, wx.EXPAND, 5 )

		self.index_table = wx.richtext.RichTextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0|wx.HSCROLL|wx.VSCROLL|wx.WANTS_CHARS )
		self.index_table.SetMinSize( wx.Size( 500,400 ) )

		fgSizer2.Add( self.index_table, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( fgSizer2 )
		self.Layout()
		fgSizer2.Fit( self )

		self.Centre( wx.BOTH )

		# Connect Events
		self.Bind( wx.EVT_SIZE, self.frame_resize )
		self.m_search_txt.Bind( wx.EVT_SEARCHCTRL_SEARCH_BTN, self.search_txt )
		self.m_search_txt.Bind( wx.EVT_TEXT_ENTER, self.search_txt )
		self.b_last_txt.Bind( wx.EVT_BUTTON, self.last_txt )
		self.b_next_txt.Bind( wx.EVT_BUTTON, self.next_txt )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def frame_resize( self, event ):
		event.Skip()

	def search_txt( self, event ):
		event.Skip()


	def last_txt( self, event ):
		event.Skip()

	def next_txt( self, event ):
		event.Skip()


