#!/usr/bin/env python3
"""
Test script for video frame extraction functionality
"""

import sys
import os
import tempfile
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_video_support():
    """Test if video support libraries are available"""
    print("Testing video support libraries...")
    
    try:
        import imageio
        print("✓ imageio available")
        imageio_available = True
    except ImportError:
        print("✗ imageio not available")
        imageio_available = False
    
    try:
        import cv2
        print(f"✓ OpenCV available (version: {cv2.__version__})")
        cv2_available = True
    except ImportError:
        print("✗ OpenCV not available")
        cv2_available = False
    
    return imageio_available or cv2_available

def test_cv2_video_extraction(video_path):
    """Test OpenCV video frame extraction"""
    print(f"\nTesting OpenCV extraction with: {video_path}")
    
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print("✗ Could not open video file")
            return False
        
        # Get video info
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"Video info: {total_frames} frames, {fps:.2f} FPS, {width}x{height}")
        
        # Test reading first few frames
        frame_count = 0
        for i in range(min(5, total_frames)):
            ret, frame = cap.read()
            if ret:
                frame_count += 1
            else:
                break
        
        cap.release()
        print(f"✓ Successfully read {frame_count} frames")
        return True
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Video Processing Test")
    print("=" * 50)
    
    # Test video support
    if not test_video_support():
        print("\n❌ No video support libraries available!")
        sys.exit(1)
    
    # Test with a sample video file (you need to provide a path)
    test_video_path = input("\nEnter path to a test video file (or press Enter to skip): ").strip()
    
    if test_video_path and os.path.exists(test_video_path):
        test_cv2_video_extraction(test_video_path)
    else:
        print("No test video provided or file not found. Skipping extraction test.")
    
    print("\n✅ Video processing test completed!")
