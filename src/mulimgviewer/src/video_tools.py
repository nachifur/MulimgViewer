"""Find FFmpeg executables without relying on a terminal activating Conda."""
import os
import shutil
import sys
from pathlib import Path


def resolve_video_tools():
    """Return absolute commands plus a child-only DLL/library search environment.

    Respect explicit overrides and PATH first. Conda's installed-package cache
    is a last resort for an environment with missing executable links; we do
    not copy files, install packages, or edit the user's system PATH.
    """
    prefixes = [Path(sys.prefix)]
    if os.environ.get('CONDA_PREFIX'):
        prefixes.append(Path(os.environ['CONDA_PREFIX']))
    directories = []
    for prefix in prefixes:
        directories.extend((prefix / 'Library' / 'bin', prefix / 'bin', prefix / 'Scripts', prefix))
    if sys.platform == 'darwin':
        directories.extend((Path('/opt/homebrew/bin'), Path('/usr/local/bin')))
    elif sys.platform.startswith('linux'):
        directories.extend((Path('/usr/local/bin'), Path('/usr/bin')))
    cached = []
    for prefix in prefixes:
        root = prefix.parent.parent if prefix.parent.name == 'envs' else prefix
        # Use the installed build's package record, not an arbitrary other version.
        for record in (prefix / 'conda-meta').glob('ffmpeg-*.json'):
            package = root / 'pkgs' / record.stem
            cached.extend((package / 'Library' / 'bin', package / 'bin'))
    tools = {}
    for name in ('ffmpeg', 'ffprobe'):
        override = os.environ.get(name.upper() + '_BINARY')
        command = shutil.which(override or name)
        if override and command is None:
            raise FileNotFoundError(f'{name.upper()}_BINARY is not executable: {override}')
        if command is None:
            executable = name + ('.exe' if os.name == 'nt' else '')
            for directory in directories + cached:
                command = shutil.which(str(directory / executable))
                if command is not None:
                    break
        if command is None:
            raise FileNotFoundError(
                f'{name} executable not found (Python: {sys.executable}). '
                'Install FFmpeg in this environment or set '
                f'{name.upper()}_BINARY to its executable path.')
        tools[name] = str(Path(command).resolve())
    env = os.environ.copy()
    # Needed for shared FFmpeg builds launched from an IDE rather than an
    # activated Conda terminal. Do not mutate PATH in the application process.
    search = list(dict.fromkeys([str(Path(command).parent) for command in tools.values()]
                                + [str(directory) for directory in directories]))
    env['PATH'] = os.pathsep.join(search + [env.get('PATH', '')])
    return tools, env
