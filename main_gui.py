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


		self.m_panel1.SetSizer( wSizer1 )
		self.m_panel1.Layout()
		wSizer1.Fit( self.m_panel1 )
		fgSizer1.Add( self.m_panel1, 1, wx.EXPAND |wx.ALL, 5 )

		fgSizer5 = wx.FlexGridSizer( 1, 2, 0, 0 )
		fgSizer5.SetFlexibleDirection( wx.BOTH )
		fgSizer5.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		fgSizer5.SetMinSize( wx.Size( 950,600 ) )
		self.scrolledWindow_img = wx.ScrolledWindow( self, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_img.SetScrollRate( 5, 5 )
		fgSizer4 = wx.FlexGridSizer( 2, 1, 0, 0 )
		fgSizer4.SetFlexibleDirection( wx.BOTH )
		fgSizer4.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText1 = wx.StaticText( self.scrolledWindow_img, wx.ID_ANY, u"Image show area", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText1.Wrap( -1 )

		fgSizer4.Add( self.m_staticText1, 0, wx.ALL, 5 )

		self.img_panel = wx.Panel( self.scrolledWindow_img, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TAB_TRAVERSAL )
		fgSizer4.Add( self.img_panel, 1, wx.EXPAND |wx.ALL, 5 )


		self.scrolledWindow_img.SetSizer( fgSizer4 )
		self.scrolledWindow_img.Layout()
		fgSizer4.Fit( self.scrolledWindow_img )
		fgSizer5.Add( self.scrolledWindow_img, 1, wx.ALL|wx.EXPAND, 5 )

		self.scrolledWindow_set = wx.ScrolledWindow( self, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), wx.HSCROLL|wx.VSCROLL )
		self.scrolledWindow_set.SetScrollRate( 5, 5 )
		fgSizer3 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer3.SetFlexibleDirection( wx.BOTH )
		fgSizer3.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.m_staticText16 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Settting", wx.DefaultPosition, wx.Size( 100,-1 ), 0 )
		self.m_staticText16.Wrap( -1 )

		self.m_staticText16.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText16, 0, wx.ALL, 5 )

		self.m_staticline3 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline3, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer16 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText21 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Correct size", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText21.Wrap( -1 )

		bSizer16.Add( self.m_staticText21, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_normalized_sizeChoices = [ u"Resize", u"Crop", u"Fill" ]
		self.choice_normalized_size = wx.Choice( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, choice_normalized_sizeChoices, 0 )
		self.choice_normalized_size.SetSelection( 0 )
		bSizer16.Add( self.choice_normalized_size, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer16, 1, wx.EXPAND, 5 )

		bSizer15 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText19 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Output mode", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText19.Wrap( -1 )

		bSizer15.Add( self.m_staticText19, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		choice_outputChoices = [ u"1:stitch", u"2:select", u"3:1+2", u"4:magnifer", u"5:1+4", u"6:2+4", u"7:1+2+4" ]
		self.choice_output = wx.Choice( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), choice_outputChoices, 0 )
		self.choice_output.SetSelection( 0 )
		bSizer15.Add( self.choice_output, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer15, 1, wx.EXPAND, 5 )

		bSizer23 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText28 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Image interp🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText28.Wrap( -1 )

		bSizer23.Add( self.m_staticText28, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		image_interpChoices = [ u"Nearest", u"Cubic", u"Linear" ]
		self.image_interp = wx.Choice( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, image_interpChoices, 0 )
		self.image_interp.SetSelection( 0 )
		bSizer23.Add( self.image_interp, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer23, 1, wx.EXPAND, 5 )

		bSizer1 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText2 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Row", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText2.Wrap( -1 )

		bSizer1.Add( self.m_staticText2, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.img_num_per_column = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer1.Add( self.img_num_per_column, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer1, 1, wx.EXPAND, 5 )

		bSizer2 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText3 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Num per img", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText3.Wrap( -1 )

		bSizer2.Add( self.m_staticText3, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.num_per_img = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer2.Add( self.num_per_img, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer2, 1, wx.EXPAND, 5 )

		bSizer3 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText4 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Column", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText4.Wrap( -1 )

		bSizer3.Add( self.m_staticText4, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.img_num_per_row = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer3.Add( self.img_num_per_row, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer3, 1, wx.EXPAND, 5 )

		bSizer4 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText5 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Gap (x,y)", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText5.Wrap( -1 )

		bSizer4.Add( self.m_staticText5, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.gap = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"10,10,2,10,2", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer4.Add( self.gap, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer4, 1, wx.EXPAND, 5 )

		bSizer18 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText23 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Draw line width", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText23.Wrap( -1 )

		bSizer18.Add( self.m_staticText23, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.line_width = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"2", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer18.Add( self.line_width, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer18, 1, wx.EXPAND, 5 )

		bSizer9 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText10 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Vertical", wx.DefaultPosition, wx.Size( 80,-1 ), 0 )
		self.m_staticText10.Wrap( -1 )

		bSizer9.Add( self.m_staticText10, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.checkBox_orientation = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer9.Add( self.checkBox_orientation, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer9, 1, wx.EXPAND, 5 )

		bSizer10 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText11 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Auto layout", wx.DefaultPosition, wx.Size( 80,-1 ), 0 )
		self.m_staticText11.Wrap( -1 )

		bSizer10.Add( self.m_staticText11, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.auto_layout_check = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer10.Add( self.auto_layout_check, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer10, 1, wx.EXPAND, 5 )

		bSizer8 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText9 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Auto save all ", wx.DefaultPosition, wx.Size( 80,-1 ), 0 )
		self.m_staticText9.Wrap( -1 )

		bSizer8.Add( self.m_staticText9, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.auto_save_all = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer8.Add( self.auto_save_all, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer8, 1, wx.EXPAND, 5 )

		bSizer19 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText24 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Move file", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText24.Wrap( -1 )

		bSizer19.Add( self.m_staticText24, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.move_file = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer19.Add( self.move_file, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer19, 1, wx.EXPAND, 5 )

		bSizer21 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText26 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Parallel+Sequential", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText26.Wrap( -1 )

		bSizer21.Add( self.m_staticText26, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.parallel_sequential = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer21.Add( self.parallel_sequential, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer21, 1, wx.EXPAND, 5 )

		bSizer25 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText30 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Select box", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText30.Wrap( -1 )

		bSizer25.Add( self.m_staticText30, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.select_img_box = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer25.Add( self.select_img_box, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer25, 1, wx.EXPAND, 5 )

		self.m_staticline9 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline9, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText35 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Show", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText35.Wrap( -1 )

		self.m_staticText35.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText35, 0, wx.ALL, 5 )

		self.m_staticline10 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline10, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer27 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText32 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Show original", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText32.Wrap( -1 )

		bSizer27.Add( self.m_staticText32, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_original = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_original.SetValue(True)
		bSizer27.Add( self.show_original, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer27, 1, wx.EXPAND, 5 )

		bSizer24 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText29 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Show box in original", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText29.Wrap( -1 )

		bSizer24.Add( self.m_staticText29, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_box = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box.SetValue(True)
		bSizer24.Add( self.show_box, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer24, 1, wx.EXPAND, 5 )

		bSizer26 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText31 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Show box in 🔍️", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText31.Wrap( -1 )

		bSizer26.Add( self.m_staticText31, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_box_in_crop = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.show_box_in_crop.SetValue(True)
		bSizer26.Add( self.show_box_in_crop, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer26, 1, wx.EXPAND, 5 )

		wSizer2 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_staticText33 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Title", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText33.Wrap( -1 )

		wSizer2.Add( self.m_staticText33, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline11 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer2.Add( self.m_staticline11, 0, wx.EXPAND |wx.ALL, 5 )

		self.title_auto = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Auto", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_auto.SetValue(True)
		wSizer2.Add( self.title_auto, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Show", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show.SetValue(True)
		wSizer2.Add( self.title_show, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_down_up = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Down", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer2.Add( self.title_down_up, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_parent = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Parent", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer2.Add( self.title_show_parent, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_name = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Name", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.title_show_name.SetValue(True)
		wSizer2.Add( self.title_show_name, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_show_suffix = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, u"Suffix", wx.DefaultPosition, wx.DefaultSize, 0 )
		wSizer2.Add( self.title_show_suffix, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.m_staticline12 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_VERTICAL )
		wSizer2.Add( self.m_staticline12, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText351 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Font", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText351.Wrap( -1 )

		wSizer2.Add( self.m_staticText351, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.title_font_size = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"20", wx.DefaultPosition, wx.Size( 40,-1 ), 0 )
		wSizer2.Add( self.title_font_size, 0, wx.ALL, 5 )

		title_fontChoices = []
		self.title_font = wx.Choice( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.Size( -1,-1 ), title_fontChoices, 0 )
		self.title_font.SetSelection( 0 )
		wSizer2.Add( self.title_font, 0, wx.ALL, 5 )


		fgSizer3.Add( wSizer2, 1, wx.EXPAND, 5 )

		self.m_staticline1 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline1, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText20 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Scale", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText20.Wrap( -1 )

		self.m_staticText20.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText20, 0, wx.ALL, 5 )

		self.m_staticline8 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline8, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer7 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText8 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Truth resolution", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText8.Wrap( -1 )

		bSizer7.Add( self.m_staticText8, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.img_resolution = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer7.Add( self.img_resolution, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer7, 1, wx.EXPAND, 5 )

		bSizer5 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText6 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Show scale", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText6.Wrap( -1 )

		bSizer5.Add( self.m_staticText6, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.show_scale = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer5.Add( self.show_scale, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer5, 1, wx.EXPAND, 5 )

		bSizer6 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText7 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Output scale", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText7.Wrap( -1 )

		bSizer6.Add( self.m_staticText7, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.output_scale = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"1,1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer6.Add( self.output_scale, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer6, 1, wx.EXPAND, 5 )

		bSizer14 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText18 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"🔍️ Scale", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText18.Wrap( -1 )

		bSizer14.Add( self.m_staticText18, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.magnifier_scale = wx.TextCtrl( self.scrolledWindow_set, wx.ID_ANY, u"-1,-1", wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer14.Add( self.magnifier_scale, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer14, 1, wx.EXPAND, 5 )

		bSizer20 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText25 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"🔍️ Keep size", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText25.Wrap( -1 )

		bSizer20.Add( self.m_staticText25, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.keep_magnifer_size = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		bSizer20.Add( self.keep_magnifer_size, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer20, 1, wx.EXPAND, 5 )

		self.m_staticline7 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline7, 0, wx.EXPAND |wx.ALL, 5 )

		self.m_staticText13 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Color/transparency", wx.DefaultPosition, wx.Size( 150,-1 ), 0 )
		self.m_staticText13.Wrap( -1 )

		self.m_staticText13.SetFont( wx.Font( 12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString ) )

		fgSizer3.Add( self.m_staticText13, 0, wx.ALL, 5 )

		self.m_staticline2 = wx.StaticLine( self.scrolledWindow_set, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
		fgSizer3.Add( self.m_staticline2, 0, wx.EXPAND |wx.ALL, 5 )

		bSizer22 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText27 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Auto draw color", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText27.Wrap( -1 )

		bSizer22.Add( self.m_staticText27, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.checkBox_auto_draw_color = wx.CheckBox( self.scrolledWindow_set, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0 )
		self.checkBox_auto_draw_color.SetValue(True)
		bSizer22.Add( self.checkBox_auto_draw_color, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )


		fgSizer3.Add( bSizer22, 1, wx.EXPAND, 5 )

		bSizer17 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText22 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Draw  color", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.m_staticText22.Wrap( -1 )

		bSizer17.Add( self.m_staticText22, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.colourPicker_draw = wx.ColourPickerCtrl( self.scrolledWindow_set, wx.ID_ANY, wx.Colour( 239, 41, 41 ), wx.DefaultPosition, wx.DefaultSize, wx.CLRP_DEFAULT_STYLE )
		bSizer17.Add( self.colourPicker_draw, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer17, 1, wx.EXPAND, 5 )

		bSizer13 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText17 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Gap color", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.m_staticText17.Wrap( -1 )

		bSizer13.Add( self.m_staticText17, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.colourPicker_gap = wx.ColourPickerCtrl( self.scrolledWindow_set, wx.ID_ANY, wx.Colour( 255, 255, 255 ), wx.DefaultPosition, wx.DefaultSize, wx.CLRP_DEFAULT_STYLE )
		bSizer13.Add( self.colourPicker_gap, 0, wx.ALL, 5 )


		fgSizer3.Add( bSizer13, 1, wx.EXPAND, 5 )

		bSizer12 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText14 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Background", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText14.Wrap( -1 )

		bSizer12.Add( self.m_staticText14, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.background_slider = wx.Slider( self.scrolledWindow_set, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		bSizer12.Add( self.background_slider, 1, wx.ALL, 5 )


		fgSizer3.Add( bSizer12, 1, wx.EXPAND, 5 )

		bSizer11 = wx.BoxSizer( wx.HORIZONTAL )

		self.m_staticText12 = wx.StaticText( self.scrolledWindow_set, wx.ID_ANY, u"Foreground", wx.DefaultPosition, wx.DefaultSize, 0 )
		self.m_staticText12.Wrap( -1 )

		bSizer11.Add( self.m_staticText12, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

		self.foreground_slider = wx.Slider( self.scrolledWindow_set, wx.ID_ANY, 255, 0, 255, wx.DefaultPosition, wx.Size( -1,-1 ), wx.SL_HORIZONTAL )
		bSizer11.Add( self.foreground_slider, 1, wx.ALL, 5 )


		fgSizer3.Add( bSizer11, 1, wx.EXPAND, 5 )


		self.scrolledWindow_set.SetSizer( fgSizer3 )
		self.scrolledWindow_set.Layout()
		fgSizer3.Fit( self.scrolledWindow_set )
		fgSizer5.Add( self.scrolledWindow_set, 1, wx.ALL|wx.EXPAND, 5 )


		fgSizer1.Add( fgSizer5, 1, wx.EXPAND, 5 )


		self.SetSizer( fgSizer1 )
		self.Layout()
		fgSizer1.Fit( self )
		self.m_statusBar1 = self.CreateStatusBar( 4, wx.STB_SIZEGRIP, wx.ID_ANY )
		self.m_menubar1 = wx.MenuBar( 0 )
		self.m_menu1 = wx.Menu()
		self.m_menu11 = wx.Menu()
		self.menu_open_sequential = wx.MenuItem( self.m_menu11, wx.ID_ANY, u"Sequential"+ u"\t" + u"Ctrl+E", u"one dir mul limg", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_sequential )

		self.menu_open_auto = wx.MenuItem( self.m_menu11, wx.ID_ANY, u"Parallel auto"+ u"\t" + u"Ctrl+A", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_auto )

		self.menu_open_manual = wx.MenuItem( self.m_menu11, wx.ID_ANY, u"Parallel manual"+ u"\t" + u"Ctrl+M", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_manual )

		self.menu_open_filelist = wx.MenuItem( self.m_menu11, wx.ID_ANY, u"Image File List"+ u"\t" + u"Ctrl+F", u"one dir mul dir", wx.ITEM_NORMAL )
		self.m_menu11.Append( self.menu_open_filelist )

		self.m_menu1.AppendSubMenu( self.m_menu11, u"Open" )

		self.menu_output = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Select output path"+ u"\t" + u"Ctrl+O", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.menu_output )

		self.m_menuItem15 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Input flist - Parallel manual"+ u"\t" + u"Ctrl+I", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem15 )

		self.m_menuItem16 = wx.MenuItem( self.m_menu1, wx.ID_ANY, u"Save flist - Parallel manual"+ u"\t" + u"Ctrl+P", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu1.Append( self.m_menuItem16 )

		self.m_menubar1.Append( self.m_menu1, u"File" )

		self.m_menu2 = wx.Menu()
		self.menu_next = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Next"+ u"\t" + u"Ctrl+N", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_next )

		self.menu_last = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Last"+ u"\t" + u"Ctrl+L", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_last )

		self.menu_save = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Save"+ u"\t" + u"Ctrl+S", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_save )

		self.menu_refresh = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Refresh"+ u"\t" + u"Ctrl+R", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_refresh )

		self.menu_up = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Up", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_up )

		self.menu_down = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Down", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_down )

		self.menu_right = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"Right", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_right )

		self.menu_left = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"left", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_left )

		self.menu_delete_box = wx.MenuItem( self.m_menu2, wx.ID_ANY, u"delete_box", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu2.Append( self.menu_delete_box )

		self.m_menubar1.Append( self.m_menu2, u"Edit" )

		self.m_menu3 = wx.Menu()
		self.index_table = wx.MenuItem( self.m_menu3, wx.ID_ANY, u"Index table"+ u"\t" + u"F2", wx.EmptyString, wx.ITEM_NORMAL )
		self.m_menu3.Append( self.index_table )

		self.menu_about = wx.MenuItem( self.m_menu3, wx.ID_ANY, u"About"+ u"\t" + u"F1", wx.EmptyString, wx.ITEM_NORMAL )
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
		self.choice_normalized_size.Bind( wx.EVT_CHOICE, self.change_img_stitch_mode )
		self.select_img_box.Bind( wx.EVT_CHECKBOX, self.select_img_box_func )
		self.title_down_up.Bind( wx.EVT_CHECKBOX, self.title_down_up_func )
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
		self.Bind( wx.EVT_MENU, self.up_img, id = self.menu_up.GetId() )
		self.Bind( wx.EVT_MENU, self.down_img, id = self.menu_down.GetId() )
		self.Bind( wx.EVT_MENU, self.right_img, id = self.menu_right.GetId() )
		self.Bind( wx.EVT_MENU, self.left_img, id = self.menu_left.GetId() )
		self.Bind( wx.EVT_MENU, self.delete_box, id = self.menu_delete_box.GetId() )
		self.Bind( wx.EVT_MENU, self.index_table_gui, id = self.index_table.GetId() )
		self.Bind( wx.EVT_MENU, self.about_gui, id = self.menu_about.GetId() )

	def __del__( self ):
		pass


	# Virtual event handlers, overide them in your derived class
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

	def change_img_stitch_mode( self, event ):
		event.Skip()

	def select_img_box_func( self, event ):
		event.Skip()

	def title_down_up_func( self, event ):
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


