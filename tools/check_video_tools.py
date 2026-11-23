"""Verify executable lookup and launch from the selected Python environment."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from mulimgviewer.src.video_source import resolve_video_tools


def main():
    print(f'Python: {sys.executable}')
    try:
        commands,env=resolve_video_tools()
        for name,command in commands.items():
            print(f'{name}: {command}')
            result=subprocess.run([command,'-version'],env=env,capture_output=True,
                text=True,errors='replace',timeout=15)
            if result.returncode:
                raise RuntimeError(f'{name} failed ({result.returncode}): {result.stderr[:500]}')
            lines=result.stdout.splitlines()
            if not lines or not lines[0].startswith(name+' version '):
                raise RuntimeError(f'{name} did not report a valid version')
            print(lines[0])
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        print(f'FAILED: {error}',file=sys.stderr)
        return 1
    print('PASSED: ffmpeg and ffprobe are available.')
    return 0


if __name__=='__main__':sys.exit(main())
