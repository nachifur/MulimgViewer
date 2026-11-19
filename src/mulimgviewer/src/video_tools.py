"""Find FFmpeg executables without relying on a terminal activating Conda."""
import os
import shutil
import sys
from pathlib import Path


def application_video_tools_dir():
    """Optional local tools, independent of cwd, Conda and regression reports."""
    return Path(__file__).resolve().parents[3]/'tools'/'ffmpeg'/'bin'


def _prefix_directories(prefix):
    prefix=Path(prefix)
    if sys.platform.startswith('win'):
        return (prefix/'Library'/'bin',prefix/'Scripts',prefix/'bin',prefix)
    return (prefix/'bin',prefix)


def _in_directories(name,directories):
    executable=name+('.exe' if sys.platform.startswith('win') else '')
    for directory in directories:
        command=shutil.which(str(directory/executable))
        if command is not None:return command
    return None


def resolve_video_tools():
    """Return absolute commands plus a child-only DLL/library search environment.

    Explicit overrides win, followed by the interpreter's environment, PATH,
    platform locations, optional portable tools and the matching Conda cache.
    No installation, download or process-wide PATH mutation happens here.
    """
    prefixes = [Path(sys.prefix)]
    # A venv may wrap a Conda Python. A stale CONDA_PREFIX from another shell
    # must not select a different environment ahead of the running interpreter.
    if sys.base_prefix!=sys.prefix:prefixes.append(Path(sys.base_prefix))
    directories = []
    for prefix in prefixes:
        directories.extend(_prefix_directories(prefix))
    system=[]
    if sys.platform == 'darwin':
        system.extend((Path('/opt/homebrew/bin'), Path('/usr/local/bin')))
    elif sys.platform.startswith('linux'):
        system.extend((Path('/usr/local/bin'), Path('/usr/bin')))
    cached = []
    for prefix in prefixes:
        root = prefix.parent.parent if prefix.parent.name == 'envs' else prefix
        # Use the installed build's package record, not an arbitrary other version.
        for record in (prefix / 'conda-meta').glob('ffmpeg-*.json'):
            package = root / 'pkgs' / record.stem
            cached.extend(_prefix_directories(package))
    tools = {}
    for name in ('ffmpeg', 'ffprobe'):
        override = os.environ.get(name.upper() + '_BINARY')
        command = shutil.which(os.path.expanduser(override)) if override else _in_directories(name,directories)
        if override and command is None:
            raise FileNotFoundError(f'{name.upper()}_BINARY is not executable: {override}')
        if command is None:
            command=shutil.which(name)
        if command is None:
            command=_in_directories(name,system+[application_video_tools_dir()]+cached)
        if command is None:
            raise FileNotFoundError(
                f'{name} executable not found (Python: {sys.executable}). '
                'Install FFmpeg in this environment with "conda install -c conda-forge ffmpeg"; '
                'verify both "ffmpeg -version" and "ffprobe -version", or set '
                f'{name.upper()}_BINARY to its executable path.')
        tools[name] = str(Path(command).resolve())
    env = os.environ.copy()
    # Needed for shared FFmpeg builds launched from an IDE rather than an
    # activated Conda terminal. Do not mutate PATH in the application process.
    search = list(dict.fromkeys([str(Path(command).parent) for command in tools.values()]
                                + [str(directory) for directory in directories]))
    env['PATH'] = os.pathsep.join(search + [env.get('PATH', '')])
    return tools, env


def read_video_file_list(filename, *, strict=False, diagnose_empty=False):
    """Read TXT/CSV paths in row order, with optional invalid-cell diagnostics."""
    import csv
    source = Path(filename)
    with source.open('r', encoding='utf-8-sig', newline='') as stream:
        rows=csv.reader(stream) if source.suffix.lower()=='.csv' else ([line] for line in stream.read().splitlines())
        entries=[(row,column,value) for row,values in enumerate(rows,1)
                 for column,value in enumerate(values,1)]
    result=[];issues=[]
    for row,column,value in entries:
        value=value.strip().strip('"')
        if not value:continue
        video=Path(value).expanduser()
        if not video.is_absolute():video=source.parent/video
        reason=None
        try:
            if not video.exists():reason='file not found'
            elif not video.is_file():reason='expected a video file, found a directory'
            elif video.suffix.lower() not in ('.mp4','.avi','.mov'):reason='unsupported video file extension'
        except OSError as error:reason=f'cannot access file: {error}'
        if reason is None:result.append(str(video.absolute()))
        elif strict or diagnose_empty:issues.append(f'row {row}, column {column}: {reason}: {video}')
    if issues and (strict or not result):
        detail='; '.join(issues[:5])
        if len(issues)>5:detail+=f'; {len(issues)-5} more invalid entries'
        raise ValueError(f'Invalid video list: {detail}')
    return result
