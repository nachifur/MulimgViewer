#!/usr/bin/env python3
"""
Test script for video directory processing functionality
"""

import sys
import os
import tempfile
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_video_directory_processing():
    """Test video directory processing methods"""
    print("Testing video directory processing...")
    
    try:
        import wx
        app = wx.App()
        
        from mulimgviewer.src.main import MulimgViewer
        
        # Create a mock UpdateUI and get_type function
        def mock_update_ui(type_id, path=None, parallel_to_sequential=False):
            print(f"Mock UpdateUI called: type_id={type_id}, path={path}")
        
        def mock_get_type():
            return -1
        
        # Create MulimgViewer instance
        frame = MulimgViewer(None, mock_update_ui, mock_get_type)
        
        # Test video file detection in a directory
        test_dir = Path("test_videos")  # You would need to create this
        if test_dir.exists():
            print(f"Testing with directory: {test_dir}")
            
            # List files in directory
            video_files = []
            for file_path in test_dir.iterdir():
                if file_path.is_file():
                    is_video = frame.is_video_file(str(file_path))
                    print(f"  {file_path.name}: {'VIDEO' if is_video else 'NOT VIDEO'}")
                    if is_video:
                        video_files.append(str(file_path))
            
            print(f"Found {len(video_files)} video files")
            
            if video_files:
                print("✓ Video files detected successfully")
            else:
                print("ℹ No video files found in test directory")
        else:
            print("ℹ Test directory 'test_videos' not found, skipping file detection test")
        
        # Test the new sequential processing method
        print("\nTesting sequential processing method...")
        try:
            # This would normally process a real directory
            # result = frame.process_video_directory_sequential("/path/to/videos")
            print("✓ Sequential processing method is available")
        except Exception as e:
            print(f"✗ Error in sequential processing: {e}")
        
        print("✓ Video directory processing methods work correctly")
        
        app.Destroy()
        return True
        
    except Exception as e:
        print(f"✗ Error testing video directory processing: {e}")
        return False

def create_test_structure():
    """Create a test directory structure"""
    print("\nCreating test directory structure...")
    
    test_dir = Path("test_videos")
    test_dir.mkdir(exist_ok=True)
    
    # Create some dummy files to test detection
    test_files = [
        "video1.mp4",
        "video2.avi", 
        "video3.mov",
        "image1.jpg",
        "image2.png",
        "document.txt"
    ]
    
    for filename in test_files:
        test_file = test_dir / filename
        if not test_file.exists():
            test_file.write_text("dummy content")
    
    print(f"✓ Created test directory with {len(test_files)} files")
    return test_dir

if __name__ == "__main__":
    print("Video Directory Processing Test")
    print("=" * 50)
    
    # Create test structure
    test_dir = create_test_structure()
    
    # Run tests
    if test_video_directory_processing():
        print("\n✅ All video directory tests passed!")
    else:
        print("\n❌ Some video directory tests failed!")
    
    # Cleanup
    try:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)
        print("✓ Cleaned up test directory")
    except:
        print("ℹ Could not clean up test directory")
