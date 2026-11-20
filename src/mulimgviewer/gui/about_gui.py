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
import wx.adv

###########################################################################
## Class AboutGui
###########################################################################

class AboutGui ( wx.Frame ):

	def __init__( self, parent ):
		wx.Frame.__init__ ( self, parent, id = wx.ID_ANY, title = u"About MulimgViewer", pos = wx.DefaultPosition, size = wx.Size( 540,380 ), style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL )

		self.SetSizeHints( wx.Size( 420,280 ), wx.DefaultSize )
		self.SetBackgroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_3DFACE ) )

		about_layout_sizer = wx.BoxSizer( wx.VERTICAL )

		self.product_title = wx.StaticText( self, wx.ID_ANY, u"MulimgViewer", wx.DefaultPosition, wx.Size( -1,-1 ), 0 )
		self.product_title.Wrap( -1 )

		self.product_title.SetFont( wx.Font( 14, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "Arial" ) )

		about_layout_sizer.Add( self.product_title, 0, wx.LEFT|wx.RIGHT|wx.TOP, 12 )

		self.about_txt = wx.richtext.RichTextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size( -1,-1 ), wx.TE_READONLY|wx.VSCROLL|wx.BORDER_SIMPLE|wx.WANTS_CHARS )
		self.about_txt.SetToolTip( u"Software and runtime information. Select text to copy it." )
		self.about_txt.SetMinSize( wx.Size( -1,120 ) )

		about_layout_sizer.Add( self.about_txt, 1, wx.EXPAND|wx.ALL, 12 )

		about_footer_sizer = wx.BoxSizer( wx.HORIZONTAL )

		about_links_sizer = wx.WrapSizer( wx.HORIZONTAL, wx.WRAPSIZER_DEFAULT_FLAGS )

		self.project_link = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"GitHub", u"https://github.com/nachifur/MulimgViewer", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		about_links_sizer.Add( self.project_link, 0, wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, 10 )

		self.license_link = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"License", u"https://github.com/nachifur/MulimgViewer/blob/master/LICENSE", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		about_links_sizer.Add( self.license_link, 0, wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, 10 )

		self.releases_link = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"Releases", u"https://github.com/nachifur/MulimgViewer/releases", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
		about_links_sizer.Add( self.releases_link, 0, wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, 10 )


		about_footer_sizer.Add( about_links_sizer, 1, wx.ALIGN_CENTER_VERTICAL, 0 )

		self.close_button = wx.Button( self, wx.ID_CANCEL, u"Close", wx.Point( -1,-1 ), wx.Size( -1,-1 ), 0 )
		self.close_button.SetToolTip( u"Close this window (Esc)." )

		about_footer_sizer.Add( self.close_button, 0, wx.ALIGN_CENTER_VERTICAL, 0 )


		about_layout_sizer.Add( about_footer_sizer, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 12 )


		self.SetSizer( about_layout_sizer )
		self.Layout()

		self.Centre( wx.BOTH )

		# Connect Events
		self.close_button.Bind( wx.EVT_BUTTON, self.on_close )

	def __del__( self ):
		pass


	# Virtual event handlers, override them in your derived class
	def on_close( self, event ):
		event.Skip()


