"""Build a native offline desktop archive and test its extracted launcher."""
import argparse
import lzma
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"
LAUNCHER = "MulimgViewer.cmd" if WINDOWS else "MulimgViewer.command"


def stage(prefix):
    app = prefix / "viewer"
    app.mkdir()
    # Ship maintained runtime files, excluding private algorithms, settings and caches.
    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "src/mulimgviewer"], cwd=ROOT
    ).decode("utf-8").split("\0")
    resources = {Path(name) for name in files if name}
    resources.update(Path("src/mulimgviewer") / name for name in ("mulimgviewer.png", "mulimgviewer.svg"))
    for path in sorted(resources):
        if path.suffix not in {".py", ".json", ".png", ".svg", ".ttf", ".ttc"}:
            continue
        if path.name in {"session_config.json", "userdef_config.json"}:
            continue
        target = app / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    for name in ("LICENSE", "MulimgViewer.py"):
        shutil.copy2(ROOT / name, app)
    shutil.copy2(ROOT / "tools/packaging/self_check.py", app)



def pack_and_verify(prefix, work, output, compact=False):
    import conda_pack

    stage(prefix)
    shutil.copy2(ROOT / "tools/packaging" / LAUNCHER, prefix)
    (prefix / LAUNCHER).chmod(0o755)
    suffix = ".tar.xz" if compact else (".zip" if WINDOWS else ".tar.gz")
    arch = platform.machine().lower().replace("amd64", "x86_64")
    os_name = "macOS" if MAC else platform.system()
    archive = work / f"MulimgViewer-{os_name}-{arch}{suffix}"
    env = conda_pack.CondaEnv.from_prefix(str(prefix))
    # Exclude build-time SDK files only in native SDK directories. Keep Python
    # packages intact: plugins can import modules the viewer does not import.
    for pattern in ("*.pyc", "include/*", "lib/*.a", "Library/include/*",
                    "Library/lib/*.lib", "libs/*.lib"):
        env = env.exclude(pattern)
    if WINDOWS:
        env = env.exclude("*.pdb")
    if compact:
        # Compress one tar stream so similar files share a dictionary.
        raw = work / "runtime.tar"
        env.pack(output=str(raw), format="tar")
        with raw.open("rb") as source, lzma.open(archive, "wb", preset=6) as target:
            shutil.copyfileobj(source, target)
        raw.unlink()
    else:
        env.pack(output=str(archive), compress_level=9)
    extracted = work / "verification copy"
    shutil.unpack_archive(archive, extracted)
    clean = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "FFMPEG_BINARY", "FFPROBE_BINARY", "CONDA_PREFIX"):
        clean.pop(key, None)
    # A missing DLL or codec must not be supplied by the developer's environment.
    clean["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32") if WINDOWS else os.defpath
    cmd = ["cmd.exe", "/d", "/c", LAUNCHER] if WINDOWS else ["./" + LAUNCHER]
    subprocess.run([*cmd, "--self-check"], cwd=extracted, env=clean, check=True, timeout=180)
    output.mkdir(parents=True, exist_ok=True)
    archive.replace(output / archive.name)
    print(f"Verified: {output / archive.name} ({(output / archive.name).stat().st_size / 2**20:.1f} MiB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/desktop")
    parser.add_argument("--compact", action="store_true", help="Build a solid-compressed tar.xz archive")
    parser.add_argument("--backend", choices=("pyinstaller", "conda"), default="pyinstaller")
    args = parser.parse_args()
    conda = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not conda:
        parser.error("Activate Conda before running this script.")
    from importlib.util import find_spec
    if args.backend == "conda" and find_spec("conda_pack") is None:
        parser.error(f'Install the build dependency first: conda install -p "{sys.prefix}" -c conda-forge conda-pack')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output if args.backend == "conda" else None,
                                     prefix="miv-build-") as tmp:
        work = Path(tmp)
        prefix = work / "runtime"
        solve_env = dict(os.environ, CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY="false")
        spec = ROOT / "environment.yml"
        if args.backend == "pyinstaller":
            spec = work / "environment.yml"
            spec.write_text((ROOT / "environment.yml").read_text(encoding="utf-8").rstrip()
                            + "\n  - pip\n  - pip:\n      - pyinstaller==6.22.3\n", encoding="utf-8")
            solve_env["PYTHONNOUSERSITE"] = "1"
            solve_env.pop("PYTHONPATH", None)
            solve_env.pop("PYTHONHOME", None)
        subprocess.run([conda, "env", "create", "--no-default-packages", "-p", str(prefix), "-f",
                        str(spec)], cwd=ROOT, env=solve_env, check=True)
        if args.backend == "pyinstaller":
            command = [conda, "run", "--no-capture-output", "-p", str(prefix), "python",
                       str(ROOT / "tools/packaging/freeze_desktop.py"), "--output", str(output)]
            if args.compact:
                command.append("--compact")
            subprocess.run(command, cwd=ROOT, env=solve_env, check=True)
            return
        if MAC:
            subprocess.run([conda, "install", "-y", "-p", str(prefix),
                            "-c", "conda-forge", "python.app"], env=solve_env, check=True)
        pack_and_verify(prefix, work, output, args.compact)


if __name__ == "__main__":
    main()
