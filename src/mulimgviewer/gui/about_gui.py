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
import wx.adv

###########################################################################
## Class AboutGui
###########################################################################

class AboutGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"About", pos = wx.DefaultPosition, size = wx.Size( 490,350 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )

		fgSizer1 = wx.FlexGridSizer( 0, 1, 0, 0 )
		fgSizer1.SetFlexibleDirection( wx.BOTH )
		fgSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

		self.about_txt = wx.richtext.RichTextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( 490,250 ), 0|wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER|wx.WANTS_CHARS )
		fgSizer1.Add( self.about_txt, 1, wx.EXPAND |wx.ALL, 5 )

		wSizer1 = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.m_hyperlink1 = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"Github", u"https://github.com/nachifur/MulimgViewer", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		wSizer1.Add( self.m_hyperlink1, 0, wx.ALL, 5 )

		self.m_hyperlink2 = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"License", u"https://github.com/nachifur/MulimgViewer/blob/master/LICENSE", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		wSizer1.Add( self.m_hyperlink2, 0, wx.ALL, 5 )

		self.m_hyperlink3 = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"Download", u"https://github.com/nachifur/MulimgViewer/releases", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		wSizer1.Add( self.m_hyperlink3, 0, wx.ALL, 5 )


		fgSizer1.Add( wSizer1, 1, wx.EXPAND, 5 )


		self.SetSizer( fgSizer1 )
		self.Layout()

		self.Centre( wx.BOTH )

	def __del__( self ):
		pass


