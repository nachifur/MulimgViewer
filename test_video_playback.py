#!/usr/bin/env python3
"""
Test script for video playback functionality in MulimgViewer
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import wx
from mulimgviewer.src.main import MulimgViewer

class TestApp(wx.App):
    def OnInit(self):
        frame = MulimgViewer(None, self.UpdateUI, self.get_type)
        frame.Show()
        return True
    
    def UpdateUI(self, type_id, path=None, parallel_to_sequential=False):
        """Mock UpdateUI function"""
        print(f"UpdateUI called with type_id: {type_id}, path: {path}")
    
    def get_type(self):
        """Mock get_type function"""
        return -1

if __name__ == "__main__":
    app = TestApp()
    app.MainLoop()
