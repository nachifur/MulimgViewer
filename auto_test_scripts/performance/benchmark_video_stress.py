"""Reproducible bounded-memory smoke test with distinct 4K decoder contexts."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from mulimgviewer.src.video_tools import resolve_video_tools


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--streams',type=int,default=100)
    parser.add_argument('--mode',type=int,choices=(1,2,3,4),default=1)
    args=parser.parse_args()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    inputs=output/'inputs'
    inputs.mkdir(exist_ok=True)
    source=inputs/'fixture_4k.mp4'
    tools,env=resolve_video_tools()
    subprocess.run([tools['ffmpeg'],'-v','error','-f','lavfi','-i',
        'testsrc2=size=3840x2160:rate=5:duration=1.2','-c:v','libx264',
        '-preset','medium','-threads','1','-g','5','-bf','2','-pix_fmt','yuv420p','-y',str(source)],
        check=True,capture_output=True,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    videos=[]
    for index in range(args.streams):
        path=inputs/('stream_%03d.mp4'%index)
        if not path.exists():
            try:
                os.link(str(source),str(path))
            except OSError:
                import shutil
                shutil.copyfile(str(source),str(path))
        videos.append(dict(path=str(path),size=source.stat().st_size,fps=5.,frames=6,
                           duration=1.2,width=3840,height=2160,codec='h264'))
    manifest=json.loads(args.reference.read_text(encoding='utf-8'))
    side=math.ceil(math.sqrt(args.streams))
    manifest.update(videos=videos,layout='%d,%d'%(side,side),preview='192,108',cache_frames=1,
                    cache_multiplier=3,warmup_frames=1,measure_frames=2,start_frame=0,
                    purpose='Memory smoke test, not a sustained-throughput or long-video benchmark')
    manifest_path=output/'manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'auto_test_scripts/performance/benchmark_video_playback.py'),
        '--manifest',str(manifest_path),'--output',str(output/'result.json'),
        '--mode',str(args.mode),'--policy','current','--duration','30','--timeout','180'],
        check=True,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


if __name__=='__main__':
    main()
