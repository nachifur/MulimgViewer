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
## Class PathSelectFrameGui
###########################################################################

class PathSelectFrameGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Parallel manual choose input directory", pos = wx.DefaultPosition, size = wx.Size( -1,-1 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		fgSizer1 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer1.SetFlexibleDirection( wx.BOTH )
		fgSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		utton_clear_last = wx.BoxSizer( wx.HORIZONTAL )

		self.m_dirPicker1 = wx.DirPickerCtrl( self, wx.ID_ANY, wx.EmptyString, u"Select a folder", wx.DefaultPosition, wx.DefaultSize, wx.DIRP_DEFAULT_STYLE )
		utton_clear_last.Add( self.m_dirPicker1, 0, wx.ALL, 5 )

		self.button_clear_all = wx.Button( self, wx.ID_ANY, u"Clear all path", wx.DefaultPosition, wx.DefaultSize, 0 )
		utton_clear_last.Add( self.button_clear_all, 0, wx.ALL, 5 )

		self.button_clear_last = wx.Button( self, wx.ID_ANY, u"Clear last path ", wx.DefaultPosition, wx.DefaultSize, 0 )
		utton_clear_last.Add( self.button_clear_last, 0, wx.ALL, 5 )


		fgSizer1.Add( utton_clear_last, 1, wx.EXPAND, 5 )

		self.m_richText1 = wx.richtext.RichTextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,300 ), 0|wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER|wx.WANTS_CHARS )
		fgSizer1.Add( self.m_richText1, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( fgSizer1 )
		self.Layout()
		fgSizer1.Fit( self )
		self.m_menubar1 = wx.MenuBar( 0 )
		self.m_menu1 = wx.Menu()
		self.m_menuItem1 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Clear all path"+ u"\t" + u"CTRL+A", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem1 )

		self.m_menuItem2 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Clear last path"+ u"\t" + u"CTRL+Z", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem2 )

		self.menu_close = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Close"+ u"\t" + u"Alt+C", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.menu_close )

		self.m_menubar1.Append( self.m_menu1, u"Edit" )

		self.SetMenuBar( self.m_menubar1 )


		self.Centre( wx.BOTH )

		# Connect Events
		self.Bind( wx.EVT_SIZE, self.frame_resize )
		self.m_dirPicker1.Bind( wx.EVT_DIRPICKER_CHANGED, self.add_dir )
		self.button_clear_all.Bind( wx.EVT_BUTTON, self.clear_all_path )
		self.button_clear_last.Bind( wx.EVT_BUTTON, self.clear_last_path )
		self.Bind( wx.EVT_MENU, self.clear_all_path, id = self.m_menuItem1.GetId() )
		self.Bind( wx.EVT_MENU, self.clear_last_path, id = self.m_menuItem2.GetId() )
		self.Bind( wx.EVT_MENU, self.Close, id = self.menu_close.GetId() )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def frame_resize( self, event ):
		event.Skip()

	def add_dir( self, event ):
		event.Skip()

	def clear_all_path( self, event ):
		event.Skip()

	def clear_last_path( self, event ):
		event.Skip()



	def Close( self, event ):
		event.Skip()


