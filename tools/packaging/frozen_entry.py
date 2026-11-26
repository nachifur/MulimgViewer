"""Entry point for the PyInstaller desktop package."""
import os
import sys
from pathlib import Path

from src.mulimgviewer.__main__ import main
from self_check import main as check


if __name__ == "__main__":
    resources = Path(sys._MEIPASS)
    suffix = ".exe" if os.name == "nt" else ""
    for name in ("ffmpeg", "ffprobe"):
        os.environ.setdefault(name.upper() + "_BINARY", str(resources / (name + suffix)))
    if sys.argv[1:] == ["--self-check"]:
        check(runtime_root=Path(sys.executable).parent)
    else:
        main()
