"""Smoke test run from an extracted desktop archive with its own interpreter."""
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

import av
from PIL import Image
from reportlab.pdfgen.canvas import Canvas
import wx
import xlsxwriter

from src.mulimgviewer import __main__ as viewer
from src.mulimgviewer.src.custom_func.main import get_available_algorithms
from src.mulimgviewer.src.video_source import resolve_video_tools


def main(runtime_root=None):
    tools, env = resolve_video_tools()
    prefix = Path(runtime_root or sys.prefix).resolve()
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)
        for tool in tools.values():
            Path(tool).resolve().relative_to(prefix)
        clip = str(path / "clip.mp4")
        subprocess.run([tools["ffmpeg"], "-v", "error", "-f", "lavfi", "-i",
                        "color=red:s=32x32", "-frames:v", "2", "-c:v", "mpeg4", clip],
                       env=env, check=True)
        subprocess.run([tools["ffprobe"], "-v", "error", "-show_streams", clip],
                       env=env, stdout=subprocess.DEVNULL, check=True)
        with av.open(clip) as video:
            image = next(video.decode(video=0)).to_image()
        image.save(path / "frame.png")
        with Image.open(path / "frame.png") as source:
            plugin = Path(viewer.__file__).parent / "src/custom_func/Gaussian Blur/main.py"
            assert "Gaussian Blur" in get_available_algorithms()
            assert runpy.run_path(str(plugin))["process_image"](source, context=None).size == (32, 32)
        pdf = Canvas(str(path / "frame.pdf"))
        pdf.drawImage(str(path / "frame.png"), 0, 0)
        pdf.save()
        with xlsxwriter.Workbook(path / "index.xlsx") as book:
            book.add_worksheet().write(0, 0, "frame.png")
    viewer.file_name = None
    app = viewer.MainAPP()
    frame = app.GetTopWindow()
    assert frame and frame.IsShown() and frame.icon.IsOk()
    wx.CallAfter(frame.Close)
    app.MainLoop()
    print("PASS: native window, icon, FFmpeg, FFprobe, PyAV, PNG, algorithm, PDF and Excel")


if __name__ == "__main__":
    main()
