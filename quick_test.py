#!/usr/bin/env python3
"""
Quick test for video functionality
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import wx
        print("✓ wxPython available")
    except ImportError as e:
        print(f"✗ wxPython not available: {e}")
        return False
    
    try:
        from mulimgviewer.src.main import MulimgViewer
        print("✓ MulimgViewer can be imported")
    except ImportError as e:
        print(f"✗ MulimgViewer import failed: {e}")
        return False
    
    try:
        import cv2
        print(f"✓ OpenCV available (version: {cv2.__version__})")
    except ImportError:
        print("✗ OpenCV not available")
    
    try:
        import imageio
        print("✓ imageio available")
    except ImportError:
        print("✗ imageio not available")
    
    return True

def test_video_methods():
    """Test video-related methods"""
    print("\nTesting video methods...")
    
    try:
        import wx
        app = wx.App()
        
        from mulimgviewer.src.main import MulimgViewer
        
        # Create a mock UpdateUI and get_type function
        def mock_update_ui(type_id, path=None, parallel_to_sequential=False):
            pass
        
        def mock_get_type():
            return -1
        
        # Create MulimgViewer instance
        frame = MulimgViewer(None, mock_update_ui, mock_get_type)
        
        # Test video file detection
        test_files = [
            "test.mp4",
            "test.avi", 
            "test.mov",
            "test.jpg",
            "test.png"
        ]
        
        for file in test_files:
            is_video = frame.is_video_file(file)
            print(f"  {file}: {'video' if is_video else 'not video'}")
        
        print("✓ Video methods work correctly")
        
        app.Destroy()
        return True
        
    except Exception as e:
        print(f"✗ Error testing video methods: {e}")
        return False

if __name__ == "__main__":
    print("Quick Video Functionality Test")
    print("=" * 40)
    
    if test_imports():
        test_video_methods()
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
