# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version Oct 26 2018)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc

###########################################################################
## Class SelectImgFrameGui
###########################################################################

class SelectImgFrameGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"Mulimg viewer", pos = wx.DefaultPosition, size = wx.Size( 900,400 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		fgSizer1 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer1.SetFlexibleDirection( wx.BOTH )
		fgSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		gbSizer1 = wx.GridBagSizer( 0, 0 )
		gbSizer1.SetFlexibleDirection( wx.BOTH )
		gbSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_panel1 = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		bSizer1 = wx.BoxSizer( wx.VERTICAL )

		bSizer1_1 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText1 = wx.StaticText( self.m_panel1, wx.ID_ANY, u"Control", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText1.Wrap( -1 )

		bSizer1_1.Add( self.m_staticText1, 0, wx.ALL, 5 )

		self.m_button1 = wx.Button( self.m_panel1, wx.ID_ANY, u"Next", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer1_1.Add( self.m_button1, 0, wx.ALL, 5 )

		self.m_button2 = wx.Button( self.m_panel1, wx.ID_ANY, u"Last", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer1_1.Add( self.m_button2, 0, wx.ALL, 5 )

		self.m_button3 = wx.Button( self.m_panel1, wx.ID_ANY, u"Save", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer1_1.Add( self.m_button3, 0, wx.ALL, 5 )


		bSizer1.Add( bSizer1_1, 1, wx.EXPAND, 5 )

		bSizer1_2 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_slider1 = wx.Slider( self.m_panel1, wx.ID_ANY, 0, 0, 100, wx.DefaultPosition, wx.Size( 215,-1 ), 0 )
		bSizer1_2.Add( self.m_slider1, 0, wx.ALL, 5 )

		self.slider_value = wx.StaticText( self.m_panel1, wx.ID_ANY, u"0", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.slider_value.Wrap( -1 )

		bSizer1_2.Add( self.slider_value, 0, wx.ALL, 5 )

		self.m_button4 = wx.Button( self.m_panel1, wx.ID_ANY, u"refresh", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer1_2.Add( self.m_button4, 0, wx.ALL, 5 )


		bSizer1.Add( bSizer1_2, 1, wx.EXPAND, 5 )


		self.m_panel1.SetSizer( bSizer1 )
		self.m_panel1.Layout()
		bSizer1.Fit( self.m_panel1 )
		gbSizer1.Add( self.m_panel1, wx.GBPosition( 0, 0 ), wx.GBSpan( 1, 1 ), wx.EXPAND |wx.ALL, 5 )

		self.m_panel2 = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		wSizer2 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		wSizer2.SetMinSize( wx.Size( 500,-1 ) )
		fgSizer2 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer2.SetFlexibleDirection( wx.BOTH )
		fgSizer2.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText3 = wx.StaticText( self.m_panel2, wx.ID_ANY, u"Setting", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText3.Wrap( -1 )

		fgSizer2.Add( self.m_staticText3, 0, wx.ALL, 5 )

		m_choice1Choices = [ u"Each img", u"Stitch img", u"Each + Stitch" ]
		self.m_choice1 = wx.Choice( self.m_panel2, wx.ID_ANY, wx.DefaultPosition, wx.Size( 120,-1 ), m_choice1Choices, 0 )
		self.m_choice1.SetSelection( 0 )
		fgSizer2.Add( self.m_choice1, 0, wx.ALL, 5 )

		self.auto_save_all = wx.CheckBox( self.m_panel2, wx.ID_ANY, u"Auto save all !", wx.DefaultPosition, wx.DefaultSize, 0 )
		fgSizer2.Add( self.auto_save_all, 0, wx.ALL, 5 )


		wSizer2.Add( fgSizer2, 1, wx.EXPAND, 5 )

		fgSizer3 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer3.SetFlexibleDirection( wx.BOTH )
		fgSizer3.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText8 = wx.StaticText( self.m_panel2, wx.ID_ANY, u"num per row", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText8.Wrap( -1 )

		fgSizer3.Add( self.m_staticText8, 0, wx.ALL, 5 )

		self.img_num_per_row = wx.TextCtrl( self.m_panel2, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		fgSizer3.Add( self.img_num_per_row, 0, wx.ALL, 5 )

		self.checkBox_orientation = wx.CheckBox( self.m_panel2, wx.ID_ANY, u"Vertical", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		fgSizer3.Add( self.checkBox_orientation, 0, wx.ALL, 5 )


		wSizer2.Add( fgSizer3, 1, wx.EXPAND, 5 )

		fgSizer4 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer4.SetFlexibleDirection( wx.BOTH )
		fgSizer4.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText6 = wx.StaticText( self.m_panel2, wx.ID_ANY, u"num per img", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText6.Wrap( -1 )

		fgSizer4.Add( self.m_staticText6, 0, wx.ALL, 5 )

		self.num_per_img = wx.TextCtrl( self.m_panel2, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		fgSizer4.Add( self.num_per_img, 0, wx.ALL, 5 )

		self.auto_layout = wx.CheckBox( self.m_panel2, wx.ID_ANY, u"Auto layout", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.auto_layout.SetValue(True)
		fgSizer4.Add( self.auto_layout, 0, wx.ALL, 5 )


		wSizer2.Add( fgSizer4, 1, wx.EXPAND, 5 )

		fgSizer5 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer5.SetFlexibleDirection( wx.BOTH )
		fgSizer5.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText5 = wx.StaticText( self.m_panel2, wx.ID_ANY, u"num per column", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText5.Wrap( -1 )

		fgSizer5.Add( self.m_staticText5, 0, wx.ALL, 5 )

		self.img_num_per_column = wx.TextCtrl( self.m_panel2, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		fgSizer5.Add( self.img_num_per_column, 0, wx.ALL, 5 )


		wSizer2.Add( fgSizer5, 1, wx.EXPAND, 5 )


		self.m_panel2.SetSizer( wSizer2 )
		self.m_panel2.Layout()
		wSizer2.Fit( self.m_panel2 )
		gbSizer1.Add( self.m_panel2, wx.GBPosition( 0, 3 ), wx.GBSpan( 1, 1 ), wx.EXPAND |wx.ALL, 5 )


		fgSizer1.Add( gbSizer1, 1, wx.EXPAND, 5 )

		self.m_staticText7 = wx.StaticText( self, wx.ID_ANY, u"Image show area", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText7.Wrap( -1 )

		fgSizer1.Add( self.m_staticText7, 0, wx.ALL, 5 )

		self.m_scrolledWindow1 = wx.ScrolledWindow( self, wx.ID_ANY, wx.DefaultPosition, wx.Size( 100,100 ), wx.HSCROLL|wx.VSCROLL )
		self.m_scrolledWindow1.SetScrollRate( 5, 5 )
		img_Sizer = wx.GridBagSizer( 0, 0 )
		img_Sizer.SetFlexibleDirection( wx.BOTH )
		img_Sizer.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )


		self.m_scrolledWindow1.SetSizer( img_Sizer )
		self.m_scrolledWindow1.Layout()
		fgSizer1.Add( self.m_scrolledWindow1, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( fgSizer1 )
		self.Layout()
		self.m_menubar1 = wx.MenuBar( 0 )
		self.MyMenu = wx.Menu()
		self.m_menu1 = wx.Menu()
		self.m_menuItem1 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"One dir", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem1 )

		self.m_menuItem2 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Detached folder", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem2 )

		self.MyMenu.AppendSubMenu( self.m_menu1, u"Input path" )

		self.m_menuItem3 = wx.MenuItem( self.MyMenu, wx.ID_ANY, u"Out path", wx.EmptyString, wx.ITEM_NORMAL )
		self.MyMenu.Append( self.m_menuItem3 )

		self.m_menubar1.Append( self.MyMenu, u"File" )

		self.m_menu2 = wx.Menu()
		self.menu_next = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Next\tCtrl+N", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_next )

		self.menu_last = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Last\tCtrl+L", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_last )

		self.menu_save = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Save\tCtrl+S", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_save )

		self.menu_up = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Up", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_up )

		self.menu_down = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Down", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_down )

		self.menu_right = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Right", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_right )

		self.menu_left = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"left", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_left )

		self.m_menubar1.Append( self.m_menu2, u"Edit" )

		self.m_menu3 = wx.Menu()
		self.menu_about = wx.MenuItem( self.m_menu3, wx.ID_ANY, u"About", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu3.Append( self.menu_about )

		self.m_menubar1.Append( self.m_menu3, u"Help" )

		self.SetMenuBar( self.m_menubar1 )

		self.m_statusBar1 = self.CreateStatusBar( 4, wx.STB_SIZEGRIP, wx.ID_ANY )

		self.Centre( wx.BOTH )

		# Connect Events
		self.m_button1.Bind( wx.EVT_BUTTON, self.next_img )
		self.m_button2.Bind( wx.EVT_BUTTON, self.last_img )
		self.m_button3.Bind( wx.EVT_BUTTON, self.save_img )
		self.m_slider1.Bind( wx.EVT_SCROLL, self.skip_to_n_img )
		self.m_button4.Bind( wx.EVT_BUTTON, self.refresh )
		self.Bind( wx.EVT_MENU, self.one_dir_input_path, id = self.m_menuItem1.GetId() )
		self.Bind( wx.EVT_MENU, self.detached_dir_input_path, id = self.m_menuItem2.GetId() )
		self.Bind( wx.EVT_MENU, self.out_path, id = self.m_menuItem3.GetId() )
		self.Bind( wx.EVT_MENU, self.next_img, id = self.menu_next.GetId() )
		self.Bind( wx.EVT_MENU, self.last_img, id = self.menu_last.GetId() )
		self.Bind( wx.EVT_MENU, self.save_img, id = self.menu_save.GetId() )
		self.Bind( wx.EVT_MENU, self.up_img, id = self.menu_up.GetId() )
		self.Bind( wx.EVT_MENU, self.down_img, id = self.menu_down.GetId() )
		self.Bind( wx.EVT_MENU, self.right_img, id = self.menu_right.GetId() )
		self.Bind( wx.EVT_MENU, self.left_img, id = self.menu_left.GetId() )
		self.Bind( wx.EVT_MENU, self.about_gui, id = self.menu_about.GetId() )

	def __del__( self ):
		pass


	# Virtual event handlers, overide them in your derived class
	def next_img( self, event ):
		event.Skip()

	def last_img( self, event ):
		event.Skip()

	def save_img( self, event ):
		event.Skip()

	def skip_to_n_img( self, event ):
		event.Skip()

	def refresh( self, event ):
		event.Skip()

	def one_dir_input_path( self, event ):
		event.Skip()

	def detached_dir_input_path( self, event ):
		event.Skip()

	def out_path( self, event ):
		event.Skip()




	def up_img( self, event ):
		event.Skip()

	def down_img( self, event ):
		event.Skip()

	def right_img( self, event ):
		event.Skip()

	def left_img( self, event ):
		event.Skip()

	def about_gui( self, event ):
		event.Skip()


