"""Regenerate GUI modules from FBP; --check validates without changing outputs."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generator',default=shutil.which('wxformbuilder') or r'D:\Program Files\wxFormBuilder\wxFormBuilder.exe')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for name in ('main_gui','index_table_gui'):
        source=ROOT/'src/mulimgviewer/gui'/f'{name}.fbp'
        if args.check:
            with tempfile.TemporaryDirectory() as directory:
                project=ET.parse(source)
                project.getroot().find('object').find("property[@name='path']").text='.'
                target=Path(directory)/source.name
                project.write(target,encoding='utf-8',xml_declaration=True)
                subprocess.run([args.generator,'-g',str(target)],check=True,cwd=directory)
                actual=(source.parent/f'{name}.py').read_text(encoding='utf-8-sig').replace('\r\n','\n')
                expected=(Path(directory)/f'{name}.py').read_text(encoding='utf-8-sig').replace('\r\n','\n')
                if actual!=expected:raise SystemExit(f'{name}.py differs from FBP output')
        else:
            subprocess.run([args.generator,'-g',str(source)],check=True,cwd=source.parent)
        print(name+': generated output verified' if args.check else name+': regenerated')

if __name__=='__main__':main()
