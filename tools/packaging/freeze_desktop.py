"""Build and verify an native PyInstaller onedir archive."""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_desktop import ROOT, stage


def video_binaries():
    prefix = Path(sys.prefix)
    if os.name != "nt":
        # PyInstaller follows Mach-O/ELF shared library dependencies.
        return [prefix / "bin" / name for name in ("ffmpeg", "ffprobe")]

    import pefile

    directory = prefix / "Library/bin"
    pending = [directory / "ffmpeg.exe", directory / "ffprobe.exe"]
    files = {}
    tables = [pefile.DIRECTORY_ENTRY[key] for key in (
        "IMAGE_DIRECTORY_ENTRY_IMPORT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT")]
    while pending:
        path = pending.pop()
        if path in files:
            continue
        files[path] = None
        with pefile.PE(str(path), fast_load=True) as binary:
            binary.parse_data_directories(directories=tables)
            for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
                for item in getattr(binary, table, []):
                    dependency = directory / item.dll.decode("ascii")
                    if dependency.is_file():
                        pending.append(dependency)
    return list(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mulimg-freeze-") as tmp:
        work = Path(tmp)
        stage(work)
        app = work / "viewer"
        entry = app / "frozen_entry.py"
        shutil.copy2(Path(__file__).with_name(entry.name), entry)
        command = [sys.executable, "-m", "PyInstaller", "--onedir", "--noupx",
                   "--name", "MulimgViewer", "--distpath", str(work / "dist"),
                   "--workpath", str(work / "work"), "--specpath", str(work),
                   "--paths", str(app)]
        for path in video_binaries():
            command.extend(["--add-binary", f"{path}{os.pathsep}."])
        for path in sorted((app / "src/mulimgviewer").rglob("*")):
            plugin_source = "custom_func" in path.parts and path.parent.name != "custom_func"
            if path.is_file() and (path.suffix != ".py" or plugin_source):
                destination = path.parent.relative_to(app)
                command.extend(["--add-data", f"{path}{os.pathsep}{destination}"])
        subprocess.run([*command, str(entry)], cwd=app, check=True)
        directory = work / "dist/MulimgViewer"
        shutil.copy2(ROOT / "LICENSE", directory)
        basename = f"MulimgViewer-{platform.system()}-{platform.machine()}"
        if args.compact:
            archive = work / (basename + ".tar.xz")
            with tarfile.open(archive, "w:xz", preset=6) as tar:
                tar.add(directory, arcname="MulimgViewer")
        else:
            fmt = "zip" if os.name == "nt" else "gztar"
            archive = Path(shutil.make_archive(str(work / basename), fmt, directory.parent, directory.name))
        extracted = work / "clean install"
        shutil.unpack_archive(archive, extracted)
        root = extracted / "MulimgViewer"
        exe = root / ("MulimgViewer.exe" if os.name == "nt" else "MulimgViewer")
        env = dict(os.environ)
        for key in ("CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH", "FFMPEG_BINARY", "FFPROBE_BINARY"):
            env.pop(key, None)
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32") if os.name == "nt" else os.defpath
        subprocess.run([str(exe), "--self-check"], cwd=root, env=env, timeout=180, check=True)
        with tempfile.TemporaryDirectory(dir=output) as staging:
            staged = Path(staging) / archive.name
            shutil.copyfile(archive, staged)
            staged.replace(output / archive.name)
        print(f"Verified {output / archive.name}", flush=True)


if __name__ == "__main__":
    main()
