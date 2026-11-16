"""Explicitly regenerate tiny copyright-free fixtures; never run by normal tests."""
import json
from pathlib import Path
import subprocess
import sys

HOME=Path(__file__).resolve().parent
sys.path[:0]=[str(HOME),str(HOME.parent/'src')]
from PIL import Image
from support.fixture_recipe import WIDTH, HEIGHT, FPS, frame, expected_pair, pixel_hash


def main():
    from mulimgviewer.src.video_tools import resolve_video_tools
    tools,env=resolve_video_tools()
    root=HOME/'assets';root.mkdir(exist_ok=True)
    manifest=dict(version=1,size=[WIDTH,HEIGHT],fps=FPS,images={},videos={},goldens={})
    for source,count in ((1,8),(2,5)):
        frames=[]
        for index in range(count):
            with frame(source,index) as image:
                frames.append(image.tobytes())
                if index<3:
                    path=root/f'images/source_{source:03d}/frame_{index+1:06d}.png'
                    path.parent.mkdir(parents=True,exist_ok=True);image.save(path,optimize=True)
                    manifest['images'][path.relative_to(root).as_posix()]=pixel_hash(image)
        target=root/f'videos/source_{source:03d}.mp4';target.parent.mkdir(exist_ok=True)
        subprocess.run([tools['ffmpeg'],'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{WIDTH}x{HEIGHT}',
            '-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264rgb','-crf','0','-preset','veryslow',
            '-threads','1','-g','4','-bf','2','-movflags','+faststart','-y',str(target)],
            input=b''.join(frames),env=env,check=True,capture_output=True)
        hashes=[]
        for index in range(count):
            with frame(source,index) as image:hashes.append(pixel_hash(image))
        manifest['videos'][target.relative_to(root).as_posix()]=dict(source=source,frames=count,rgb_sha256=hashes)
    for name,arguments in (('parallel',(1,0,2,0)),('sequential',(1,0,1,1))):
        path=root/f'expected/{name}.png';path.parent.mkdir(exist_ok=True)
        with expected_pair(*arguments) as image:
            image.save(path,optimize=True);manifest['goldens'][path.relative_to(root).as_posix()]=pixel_hash(image)
    path=root/'special/alpha.png';path.parent.mkdir(exist_ok=True)
    with frame(1,0) as image:
        with image.convert('RGBA') as alpha:alpha.putalpha(128);alpha.save(path,optimize=True)
    listings=root/'lists';listings.mkdir(exist_ok=True)
    (listings/'images.txt').write_text('../images/source_001/frame_000001.png\n../images/source_002/frame_000001.png\n',encoding='utf-8')
    (listings/'videos.txt').write_text('../videos/source_001.mp4\n../videos/source_002.mp4\n',encoding='utf-8')
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Fixture bytes:',sum(p.stat().st_size for p in root.rglob('*') if p.is_file()))


if __name__=='__main__':main()
