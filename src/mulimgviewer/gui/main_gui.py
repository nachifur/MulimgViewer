# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 3.10.1-0-g8feb16b3)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc

###########################################################################
## Class MulimgViewerGui
###########################################################################

class MulimgViewerGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"MulimgViewer", pos = wx.DefaultPosition, size = wx.Size( -1,-1 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		fgSizer1 = wx.FlexGridSizer( 2, 1, 0, 0 )
		fgSizer1.SetFlexibleDirection( wx.BOTH )
		fgSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_panel1 = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		wSizer1 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.button_open_all = wx.Button( self.m_panel1, wx.ID_ANY, u"📂️", wx.DefaultPosition, wx.Size( 50,30 ), wx.BORDER_NONE )
		self.button_open_all.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.button_open_all, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_input_modeChoices = [ u"Sequential", u"Parallel auto", u"Parallel manual", u"Image File List" ]
		self.choice_input_mode = wx.Choice( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), choice_input_modeChoices, 0 )
		self.choice_input_mode.SetSelection( 0 )
		wSizer1.Add( self.choice_input_mode, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline4 = wx.StaticLine( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer1.Add( self.m_staticline4, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_button6 = wx.Button( self.m_panel1, wx.ID_ANY, u"📁️", wx.DefaultPosition, wx.Size( 50,30 ), wx.BORDER_NONE )
		self.m_button6.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )
		self.m_button6.SetMinSize( wx.Size( 50,30 ) )

		wSizer1.Add( self.m_button6, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.save_butoon = wx.Button( self.m_panel1, wx.ID_ANY, u"💾️", wx.DefaultPosition, wx.Size( 50,30 ), wx.BORDER_NONE )
		self.save_butoon.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.save_butoon, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline5 = wx.StaticLine( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer1.Add( self.m_staticline5, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_button3 = wx.Button( self.m_panel1, wx.ID_ANY, u"<", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.m_button3.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.m_button3, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_button4 = wx.Button( self.m_panel1, wx.ID_ANY, u">", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.m_button4.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.m_button4, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_button5 = wx.Button( self.m_panel1, wx.ID_ANY, u"⟳", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.m_button5.SetFont( wx.Font( 16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.m_button5, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.slider_value = wx.TextCtrl( self.m_panel1, wx.ID_ANY, u"0", wx.DefaultPosition, wx.Size( 50,-1 ), wx.TE_PROCESS_ENTER )
		wSizer1.Add( self.slider_value, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_CENTER_HORIZONTAL, 5 )

		self.slider_img = wx.Slider( self.m_panel1, wx.ID_ANY, 0, 0, 100, wx.DefaultPosition, wx.Size( 150,30 ), wx.SL_HORIZONTAL )
		wSizer1.Add( self.slider_img, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.slider_value_max = wx.StaticText( self.m_panel1, wx.ID_ANY, u"0", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.slider_value_max.Wrap( -1 )

		wSizer1.Add( self.slider_value_max, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline6 = wx.StaticLine( self.m_panel1, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer1.Add( self.m_staticline6, 0, wx.EXPAND |wx.ALL, 5 )

		self.magnifier = wx.ToggleButton( self.m_panel1, wx.ID_ANY, u"🔍️", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.magnifier.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.magnifier, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.rotation = wx.ToggleButton( self.m_panel1, wx.ID_ANY, u"↷", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.rotation.SetFont( wx.Font( 16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.rotation, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.flip = wx.ToggleButton( self.m_panel1, wx.ID_ANY, u"⏃", wx.DefaultPosition, wx.Size( 50,30 ), 0 )
		self.flip.SetFont( wx.Font( 20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer1.Add( self.flip, 0, wx.ALL, 5 )


		self.m_panel1.SetSizer( wSizer1 )
		self.m_panel1.Layout()
		wSizer1.Fit( self.m_panel1 )
		fgSizer1.Add( self.m_panel1, 1, wx.EXPAND |wx.ALL, 5 )

		self.m_panel3 = wx.Panel( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		fgSizer5 = wx.FlexGridSizer( 1, 2, 0, 0 )
		fgSizer5.SetFlexibleDirection( wx.BOTH )
		fgSizer5.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		fgSizer5.SetMinSize( wx.Size( 1000,600 ) )
		self.m_splitter1 = wx.SplitterWindow( self.m_panel3, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.SP_3D )
		self.scrolledWindow_img = wx.ScrolledWindow( self.m_splitter1, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_img.SetScrollRate( 5, 5 )
		fgSizer4 = wx.FlexGridSizer( 2, 1, 0, 0 )
		fgSizer4.SetFlexibleDirection( wx.BOTH )
		fgSizer4.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		fgSizer4.SetMinSize( wx.Size( 700,600 ) )
		self.m_staticText1 = wx.StaticText( self.scrolledWindow_img, wx.ID_ANY, u"Image show area", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText1.Wrap( -1 )

		fgSizer4.Add( self.m_staticText1, 0, wx.ALL, 5 )

		self.img_panel = wx.Panel( self.scrolledWindow_img, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.BORDER_NONE )
		fgSizer4.Add( self.img_panel, 1, wx.EXPAND |wx.ALL, 5 )


		self.scrolledWindow_img.SetSizer( fgSizer4 )
		self.scrolledWindow_img.Layout()
		fgSizer4.Fit( self.scrolledWindow_img )
		self.scrolledWindow_set = wx.ScrolledWindow( self.m_splitter1, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_set.SetScrollRate( 5, 5 )
		bSizer13 = wx.BoxSizer( wx.VERTICAL )

		self.m_panel4 = wx.Panel( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL )
		fgSizer3 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer3.SetFlexibleDirection( wx.BOTH )
		fgSizer3.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		fgSizer3.SetMinSize( wx.Size( 300,600 ) )
		self.m_staticText38 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Input/Output", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText38.Wrap( -1 )

		self.m_staticText38.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText38, 0, wx.ALL, 5 )

		self.m_staticline3 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline3, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer16 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText21 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"UniformSize", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText21.Wrap( -1 )

		bSizer16.Add( self.m_staticText21, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_normalized_sizeChoices = [ u"Resize", u"Crop", u"Fill" ]
		self.choice_normalized_size = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( 90,-1 ), choice_normalized_sizeChoices, 0 )
		self.choice_normalized_size.SetSelection( 0 )
		bSizer16.Add( self.choice_normalized_size, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer16, 1, wx.EXPAND, 5 )

		bSizer15 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText19 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"OutputMode", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText19.Wrap( -1 )

		bSizer15.Add( self.m_staticText19, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_outputChoices = [ u"1:stitch", u"2:select", u"3:1+2", u"4:magnifer", u"5:1+4", u"6:2+4", u"7:1+2+4" ]
		self.choice_output = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( 90,-1 ), choice_outputChoices, 0 )
		self.choice_output.SetSelection( 0 )
		bSizer15.Add( self.choice_output, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer15, 1, wx.EXPAND, 5 )

		bSizer23 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText28 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"ImgInterp🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText28.Wrap( -1 )

		bSizer23.Add( self.m_staticText28, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		image_interpChoices = [ u"Nearest", u"Cubic", u"Linear" ]
		self.image_interp = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( 90,-1 ), image_interpChoices, 0 )
		self.image_interp.SetSelection( 2 )
		bSizer23.Add( self.image_interp, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer23, 1, wx.EXPAND, 5 )

		bSizer21 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText26 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Parallel+Sequential", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText26.Wrap( -1 )

		bSizer21.Add( self.m_staticText26, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.parallel_sequential = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer21.Add( self.parallel_sequential, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer21, 1, wx.EXPAND, 5 )

		bSizer29 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText37 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Parallel->Sequential", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText37.Wrap( -1 )

		bSizer29.Add( self.m_staticText37, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.parallel_to_sequential = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer29.Add( self.parallel_to_sequential, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer29, 1, wx.EXPAND, 5 )

		wSizer3 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.auto_save_all = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"AutoSaveAll", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer3.Add( self.auto_save_all, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.move_file = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"MoveFile", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer3.Add( self.move_file, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer3, 1, wx.EXPAND, 5 )

		self.m_staticline13 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline13, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer151 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText16 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Layout", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.m_staticText16.Wrap( -1 )

		self.m_staticText16.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		bSizer151.Add( self.m_staticText16, 1, wx.ALL, 5 )

		self.m_staticline19 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		bSizer151.Add( self.m_staticline19, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText34 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Vertical", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText34.Wrap( -1 )

		bSizer151.Add( self.m_staticText34, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer151, 1, wx.EXPAND, 5 )

		self.m_staticline14 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline14, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer18 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText2 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"RowCol", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText2.Wrap( -1 )

		bSizer18.Add( self.m_staticText2, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.row_col = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		bSizer18.Add( self.row_col, 0, wx.ALL, 5 )

		self.img_vertical = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer18.Add( self.img_vertical, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer18, 1, wx.EXPAND, 5 )

		bSizer10 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText4 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"RowCol->OneImg", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText4.Wrap( -1 )

		bSizer10.Add( self.m_staticText4, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.row_col_one_img = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		bSizer10.Add( self.row_col_one_img, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.one_img_vertical = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer10.Add( self.one_img_vertical, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer10, 1, wx.EXPAND, 5 )

		bSizer14 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText331 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"RowCol(ImgUnit)", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText331.Wrap( -1 )

		bSizer14.Add( self.m_staticText331, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.row_col_img_unit = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"3,1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer14.Add( self.row_col_img_unit, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.img_unit_vertical = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer14.Add( self.img_unit_vertical, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer14, 1, wx.EXPAND, 5 )

		bSizer101 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText41 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"RowCol(🔍️)", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText41.Wrap( -1 )

		bSizer101.Add( self.m_staticText41, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.magnifer_row_col = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		bSizer101.Add( self.magnifer_row_col, 0, wx.ALL, 5 )

		self.magnifer_vertical = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer101.Add( self.magnifer_vertical, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer101, 1, wx.EXPAND, 5 )

		bSizer4 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText5 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Gap(XY,One,Unit,🔍️)", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText5.Wrap( -1 )

		bSizer4.Add( self.m_staticText5, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.gap = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"10,10,5,5,3,3,2,2", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer4.Add( self.gap, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer4, 1, wx.EXPAND, 5 )

		wSizer81 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText32 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"ShowUnit", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText32.Wrap( -1 )

		wSizer81.Add( self.m_staticText32, 0, wx.ALL, 5 )

		self.m_staticline18 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer81.Add( self.m_staticline18, 0, wx.EXPAND |wx.ALL, 5 )

		self.show_original = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Img", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_original.SetValue(True)
		wSizer81.Add( self.show_original, 0, wx.ALL, 5 )

		self.show_magnifer = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_magnifer.SetValue(True)
		wSizer81.Add( self.show_magnifer, 0, wx.ALL, 5 )

		self.title_show = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Title", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show.SetValue(True)
		wSizer81.Add( self.title_show, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( wSizer81, 1, wx.EXPAND, 5 )

		wSizer11 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.auto_layout_check = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"AutoWinSize", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer11.Add( self.auto_layout_check, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.one_img = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"OneImg", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer11.Add( self.one_img, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.onetitle = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"OneTitle", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer11.Add( self.onetitle, 0, wx.ALL, 5 )

		self.customfunc = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"CustomFunc", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer11.Add( self.customfunc, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer11, 1, wx.EXPAND, 5 )

		self.m_staticline15 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline15, 0, wx.EXPAND |wx.ALL, 5 )

		wSizer7 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText40 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Box", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText40.Wrap( -1 )

		self.m_staticText40.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer7.Add( self.m_staticText40, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline10 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer7.Add( self.m_staticline10, 0, wx.EXPAND |wx.ALL, 5 )

		self.show_box = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"InImg", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box.SetValue(True)
		wSizer7.Add( self.show_box, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_box_in_crop = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"In🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box_in_crop.SetValue(True)
		wSizer7.Add( self.show_box_in_crop, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticText23 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Width", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText23.Wrap( -1 )

		wSizer7.Add( self.m_staticText23, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.line_width = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"2,2", wx.DefaultPosition, wx.Size( 35,-1 ), 0 )
		wSizer7.Add( self.line_width, 0, wx.ALL, 5 )

		self.select_img_box = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"SelectBox", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer7.Add( self.select_img_box, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		box_positionChoices = [ u"middle bottom", u"left bottom", u"right bottom", u"left top", u"right top" ]
		self.box_position = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( 105,-1 ), box_positionChoices, 0 )
		self.box_position.SetSelection( 0 )
		wSizer7.Add( self.box_position, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer7, 1, wx.EXPAND, 5 )

		self.m_staticline16 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline16, 0, wx.EXPAND |wx.ALL, 5 )

		wSizer2 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText33 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Title", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText33.Wrap( -1 )

		self.m_staticText33.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer2.Add( self.m_staticText33, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline11 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer2.Add( self.m_staticline11, 0, wx.EXPAND |wx.ALL, 5 )

		self.title_auto = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Auto", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_auto.SetValue(True)
		wSizer2.Add( self.title_auto, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_exif = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"EXIF", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_exif.Enable( False )

		wSizer2.Add( self.title_exif, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_parent = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Parent", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_parent.Enable( False )

		wSizer2.Add( self.title_show_parent, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_prefix = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Prefix", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_prefix.SetValue(True)
		self.title_show_prefix.Enable( False )

		wSizer2.Add( self.title_show_prefix, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_name = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Name", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_name.SetValue(True)
		self.title_show_name.Enable( False )

		wSizer2.Add( self.title_show_name, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_suffix = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Suffix", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_suffix.Enable( False )

		wSizer2.Add( self.title_show_suffix, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		title_positionChoices = [ u"left", u"center", u"right" ]
		self.title_position = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( 45,-1 ), title_positionChoices, 0 )
		self.title_position.SetSelection( 0 )
		self.title_position.Enable( False )

		wSizer2.Add( self.title_position, 0, wx.ALL, 5 )

		self.title_down_up = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"Down", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_down_up.Enable( False )

		wSizer2.Add( self.title_down_up, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline20 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer2.Add( self.m_staticline20, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText351 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Font", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText351.Wrap( -1 )

		wSizer2.Add( self.m_staticText351, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_font_size = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"20", wx.DefaultPosition, wx.Size( 40,-1 ), 0 )
		wSizer2.Add( self.title_font_size, 0, wx.ALL, 5 )

		title_fontChoices = []
		self.title_font = wx.Choice( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), title_fontChoices, 0 )
		self.title_font.SetSelection( 0 )
		wSizer2.Add( self.title_font, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer2, 1, wx.EXPAND, 5 )

		self.m_staticline1 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline1, 0, wx.EXPAND |wx.ALL, 5 )

		wSizer6 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText20 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Scale", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText20.Wrap( -1 )

		self.m_staticText20.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer6.Add( self.m_staticText20, 0, wx.ALL, 5 )

		self.m_staticline8 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer6.Add( self.m_staticline8, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText6 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Show", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText6.Wrap( -1 )

		wSizer6.Add( self.m_staticText6, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_scale = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( 50,-1 ), 0 )
		wSizer6.Add( self.show_scale, 0, wx.ALL, 5 )

		self.m_staticText7 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Out", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText7.Wrap( -1 )

		wSizer6.Add( self.m_staticText7, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.output_scale = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( 50,-1 ), 0 )
		wSizer6.Add( self.output_scale, 0, wx.ALL, 5 )

		self.m_staticText18 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"🔍️Show", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText18.Wrap( -1 )

		wSizer6.Add( self.m_staticText18, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.magnifier_show_scale = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( 60,-1 ), 0 )
		wSizer6.Add( self.magnifier_show_scale, 0, wx.ALL, 5 )

		self.m_staticText341 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"🔍️Out", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText341.Wrap( -1 )

		wSizer6.Add( self.m_staticText341, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.magnifier_out_scale = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.Size( 60,-1 ), 0 )
		wSizer6.Add( self.magnifier_out_scale, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer6, 1, wx.EXPAND, 5 )

		self.m_staticline21 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline21, 0, wx.EXPAND |wx.ALL, 5 )

		wSizer10 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText39 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Size", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText39.Wrap( -1 )

		self.m_staticText39.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		wSizer10.Add( self.m_staticText39, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline22 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer10.Add( self.m_staticline22, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText8 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Img", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText8.Wrap( -1 )

		wSizer10.Add( self.m_staticText8, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.img_resolution = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( 60,-1 ), 0 )
		wSizer10.Add( self.img_resolution, 1, wx.ALL, 5 )

		self.m_staticText381 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText381.Wrap( -1 )

		wSizer10.Add( self.m_staticText381, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.magnifer_resolution = wx.TextCtrl( self.m_panel4, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.Size( 60,-1 ), 0 )
		wSizer10.Add( self.magnifer_resolution, 0, wx.ALL, 5 )

		self.keep_magnifer_size = wx.CheckBox( self.m_panel4, wx.ID_ANY, u"🔍️KeepSize", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer10.Add( self.keep_magnifer_size, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( wSizer10, 1, wx.EXPAND, 5 )

		self.m_staticline7 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline7, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText13 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Color/transparency", wx.DefaultPosition, wx.Size( 150,-1 ), 0 )
		self.m_staticText13.Wrap( -1 )

		self.m_staticText13.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText13, 0, wx.ALL, 5 )

		self.m_staticline2 = wx.StaticLine( self.m_panel4, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline2, 0, wx.EXPAND |wx.ALL, 5 )

		wSizer8 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText22 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Draw", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.m_staticText22.Wrap( -1 )

		wSizer8.Add( self.m_staticText22, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.colourPicker_draw = wx.ColourPickerCtrl( self.m_panel4, wx.ID_ANY, wx.Colour( 239, 41, 41 ), wx.DefaultPosition, wx.Size( 40,-1 ), wx.CLRP_DEFAULT_STYLE )
		wSizer8.Add( self.colourPicker_draw, 0, wx.ALL, 5 )

		self.m_staticText17 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Gap", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.m_staticText17.Wrap( -1 )

		wSizer8.Add( self.m_staticText17, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.colourPicker_gap = wx.ColourPickerCtrl( self.m_panel4, wx.ID_ANY, wx.Colour( 255, 255, 255 ), wx.DefaultPosition, wx.Size( 40,-1 ), wx.CLRP_DEFAULT_STYLE )
		wSizer8.Add( self.colourPicker_gap, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer8, 1, wx.EXPAND, 5 )

		bSizer22 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText27 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"AutoDrawColor", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText27.Wrap( -1 )

		bSizer22.Add( self.m_staticText27, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.checkBox_auto_draw_color = wx.CheckBox( self.m_panel4, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.checkBox_auto_draw_color.SetValue(True)
		bSizer22.Add( self.checkBox_auto_draw_color, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer22, 1, wx.EXPAND, 5 )

		bSizer12 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText14 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Background", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText14.Wrap( -1 )

		bSizer12.Add( self.m_staticText14, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.background_slider = wx.Slider( self.m_panel4, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		bSizer12.Add( self.background_slider, 1, wx.ALL, 5 )


		fgSizer3.Add( bSizer12, 1, wx.EXPAND, 5 )

		bSizer11 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText12 = wx.StaticText( self.m_panel4, wx.ID_ANY, u"Foreground", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText12.Wrap( -1 )

		bSizer11.Add( self.m_staticText12, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.foreground_slider = wx.Slider( self.m_panel4, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		bSizer11.Add( self.foreground_slider, 1, wx.ALL, 5 )


		fgSizer3.Add( bSizer11, 1, wx.EXPAND, 5 )


		self.m_panel4.SetSizer( fgSizer3 )
		self.m_panel4.Layout()
		fgSizer3.Fit( self.m_panel4 )
		bSizer13.Add( self.m_panel4, 0, wx.ALL|wx.EXPAND, 5 )


		self.scrolledWindow_set.SetSizer( bSizer13 )
		self.scrolledWindow_set.Layout()
		bSizer13.Fit( self.scrolledWindow_set )
		self.m_splitter1.SplitVertically( self.scrolledWindow_img, self.scrolledWindow_set, -1 )
		fgSizer5.Add( self.m_splitter1, 1, wx.EXPAND, 5 )


		self.m_panel3.SetSizer( fgSizer5 )
		self.m_panel3.Layout()
		fgSizer5.Fit( self.m_panel3 )
		fgSizer1.Add( self.m_panel3, 1, wx.EXPAND |wx.ALL, 5 )


		self.SetSizer( fgSizer1 )
		self.Layout()
		fgSizer1.Fit( self )
		self.m_statusBar1 = self.CreateStatusBar( 4, wx.STB_SIZEGRIP, wx.ID_ANY )
		self.m_menubar1 = wx.MenuBar( 0 )
		self.m_menu1 = wx.Menu()
		self.m_menu11 = wx.Menu()
		self.menu_open_sequential = self.m_menu11.Append( wx.ID_ANY, u"Sequential"+ u"\t" + u"Ctrl+E", u"one dir mul limg", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_sequential )

		self.menu_open_auto = self.m_menu11.Append( wx.ID_ANY, u"Parallel auto"+ u"\t" + u"Ctrl+A", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_auto )

		self.menu_open_manual = self.m_menu11.Append( wx.ID_ANY, u"Parallel manual"+ u"\t" + u"Ctrl+M", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_manual )

		self.menu_open_filelist = self.m_menu11.Append( wx.ID_ANY, u"Image File List"+ u"\t" + u"Ctrl+F", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_filelist )

		self.m_menu1.AppendSubMenu( self.m_menu11, u"Open" )

		self.menu_output = self.m_menu1.Append( wx.ID_ANY, u"Select output path"+ u"\t" + u"Ctrl+O", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.menu_output )

		self.m_menuItem15 = self.m_menu1.Append( wx.ID_ANY, u"Input flist - Parallel manual"+ u"\t" + u"Ctrl+I", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem15 )

		self.m_menuItem16 = self.m_menu1.Append( wx.ID_ANY, u"Save flist - Parallel manual"+ u"\t" + u"Ctrl+P", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem16 )

		self.m_menubar1.Append( self.m_menu1, u"File" )

		self.m_menu2 = wx.Menu()
		self.menu_next = self.m_menu2.Append( wx.ID_ANY, u"Next"+ u"\t" + u"Ctrl+N", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_next )

		self.menu_last = self.m_menu2.Append( wx.ID_ANY, u"Last"+ u"\t" + u"Ctrl+L", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_last )

		self.menu_save = self.m_menu2.Append( wx.ID_ANY, u"Save"+ u"\t" + u"Ctrl+S", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_save )

		self.menu_refresh = self.m_menu2.Append( wx.ID_ANY, u"Refresh"+ u"\t" + u"Ctrl+R", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_refresh )

		self.menu_hidden = self.m_menu2.Append( wx.ID_ANY, u"hidden"+ u"\t" + u"Ctrl+H", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_hidden )

		self.menu_up = self.m_menu2.Append( wx.ID_ANY, u"Up", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_up )

		self.menu_down = self.m_menu2.Append( wx.ID_ANY, u"Down", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_down )

		self.menu_right = self.m_menu2.Append( wx.ID_ANY, u"Right", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_right )

		self.menu_left = self.m_menu2.Append( wx.ID_ANY, u"left", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_left )

		self.menu_delete_box = self.m_menu2.Append( wx.ID_ANY, u"delete_box", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_delete_box )

		self.m_menubar1.Append( self.m_menu2, u"Edit" )

		self.m_menu3 = wx.Menu()
		self.index_table = self.m_menu3.Append( wx.ID_ANY, u"Index table"+ u"\t" + u"F2", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu3.Append( self.index_table )

		self.menu_about = self.m_menu3.Append( wx.ID_ANY, u"About"+ u"\t" + u"F1", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu3.Append( self.menu_about )

		self.m_menubar1.Append( self.m_menu3, u"Help" )

		self.SetMenuBar( self.m_menubar1 )


		self.Centre( wx.BOTH )

		# Connect Events
		self.Bind( wx.EVT_SIZE, self.frame_resize )
		self.button_open_all.Bind( wx.EVT_BUTTON, self.open_all_img )
		self.m_button6.Bind( wx.EVT_BUTTON, self.out_path )
		self.save_butoon.Bind( wx.EVT_BUTTON, self.save_img )
		self.m_button3.Bind( wx.EVT_BUTTON, self.last_img )
		self.m_button4.Bind( wx.EVT_BUTTON, self.next_img )
		self.m_button5.Bind( wx.EVT_BUTTON, self.refresh )
		self.slider_value.Bind( wx.EVT_TEXT_ENTER, self.slider_value_change )
		self.slider_img.Bind( wx.EVT_SCROLL, self.skip_to_n_img )
		self.magnifier.Bind( wx.EVT_TOGGLEBUTTON, self.magnifier_fc )
		self.rotation.Bind( wx.EVT_TOGGLEBUTTON, self.rotation_fc )
		self.flip.Bind( wx.EVT_TOGGLEBUTTON, self.flip_fc )
		self.m_splitter1.Bind( wx.EVT_SPLITTER_SASH_POS_CHANGED, self.split_sash_pos_changed )
		self.m_splitter1.Bind( wx.EVT_SPLITTER_SASH_POS_CHANGING, self.split_sash_pos_changing )
		self.choice_normalized_size.Bind( wx.EVT_CHOICE, self.change_img_stitch_mode )
		self.parallel_sequential.Bind( wx.EVT_CHECKBOX, self.parallel_sequential_fc )
		self.parallel_to_sequential.Bind( wx.EVT_CHECKBOX, self.parallel_to_sequential_fc )
		self.select_img_box.Bind( wx.EVT_CHECKBOX, self.select_img_box_func )
		self.title_auto.Bind( wx.EVT_CHECKBOX, self.title_auto_fc )
		self.title_down_up.Bind( wx.EVT_CHECKBOX, self.title_down_up_fc )
		self.colourPicker_gap.Bind( wx.EVT_COLOURPICKER_CHANGED, self.colour_change )
		self.background_slider.Bind( wx.EVT_SCROLL, self.background_alpha )
		self.foreground_slider.Bind( wx.EVT_SCROLL, self.foreground_alpha )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_img, id = self.menu_open_sequential.GetId() )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_dir_auto, id = self.menu_open_auto.GetId() )
		self.Bind( wx.EVT_MENU, self.one_dir_mul_dir_manual, id = self.menu_open_manual.GetId() )
		self.Bind( wx.EVT_MENU, self.onefilelist, id = self.menu_open_filelist.GetId() )
		self.Bind( wx.EVT_MENU, self.out_path, id = self.menu_output.GetId() )
		self.Bind( wx.EVT_MENU, self.input_flist_parallel_manual, id = self.m_menuItem15.GetId() )
		self.Bind( wx.EVT_MENU, self.save_flist_parallel_manual, id = self.m_menuItem16.GetId() )
		self.Bind( wx.EVT_MENU, self.next_img, id = self.menu_next.GetId() )
		self.Bind( wx.EVT_MENU, self.last_img, id = self.menu_last.GetId() )
		self.Bind( wx.EVT_MENU, self.save_img, id = self.menu_save.GetId() )
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

	def out_path( self, event ):
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

	def change_img_stitch_mode( self, event ):
		event.Skip()

	def parallel_sequential_fc( self, event ):
		event.Skip()

	def parallel_to_sequential_fc( self, event ):
		event.Skip()

	def select_img_box_func( self, event ):
		event.Skip()

	def title_auto_fc( self, event ):
		event.Skip()

	def title_down_up_fc( self, event ):
		event.Skip()

	def colour_change( self, event ):
		event.Skip()

	def background_alpha( self, event ):
		event.Skip()

	def foreground_alpha( self, event ):
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


