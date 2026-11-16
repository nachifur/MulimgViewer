"""One-command functional regression suite with isolated wx processes and reports."""
import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

HOME = Path(__file__).resolve().parent
ROOT = HOME.parent
sys.path[:0] = [str(HOME), str(ROOT/'src')]
from support.reporting import write_reports


def revision():
    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.stdout.strip() if result.returncode == 0 else 'unavailable'
    try:
        changes = git('status', '--porcelain')
        commit = git('rev-parse', 'HEAD')
    except OSError:changes=commit='unavailable'
    # A source digest also identifies uncommitted code being reviewed.
    digest = hashlib.sha256()
    for path in sorted((ROOT/'src').rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.fbp', '.json') and path.name!='session_config.json':
            digest.update(path.relative_to(ROOT).as_posix().encode());digest.update(path.read_bytes())
    tests=hashlib.sha256()
    paths=[HOME/'run_tests.py',HOME/'generate_assets.py',HOME/'coverage.json']
    for folder in ('cases','support','assets'):
        paths.extend(p for p in (HOME/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.txt','.png','.mp4'))
    for path in sorted(paths):
        tests.update(path.relative_to(HOME).as_posix().encode());tests.update(path.read_bytes())
    return dict(commit=commit, dirty=bool(changes), changes=changes, source_sha256=digest.hexdigest(),test_assets_sha256=tests.hexdigest())


def preflight(env):
    for name in ('wx', 'PIL', 'numpy', 'ffmpeg', 'av', 'psutil', 'piexif', 'imageio', 'requests', 'reportlab', 'xlsxwriter'):
        importlib.import_module(name)
    from mulimgviewer.src.video_tools import resolve_video_tools
    commands, tool_env = resolve_video_tools()
    env.update(tool_env)
    env['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(path).parent) for path in commands.values()))+os.pathsep+env.get('PATH', '')
    for path in commands.values():subprocess.run([path, '-version'], check=True, capture_output=True, env=env)
    if platform.system()=='Linux' and not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        raise RuntimeError('GUI tests require a display. On headless Linux run: xvfb-run -a python auto_test_scripts/run_tests.py')
    return {name: str(path) for name,path in commands.items()}


def terminate_tree(process):
    import psutil
    try:
        owner=psutil.Process(process.pid)
        children=owner.children(recursive=True)
        for child in reversed(children):
            try:child.kill()
            except psutil.NoSuchProcess:pass
        owner.kill()
    except psutil.NoSuchProcess:pass
    process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', action='append', default=[], help='Module name/glob; repeat to select several')
    parser.add_argument('--case', action='append', default=[], help='Full test id/glob, e.g. *save*')
    parser.add_argument('--failed', type=Path, help='Rerun failed cases from a prior report.json')
    parser.add_argument('--list', action='store_true', help='List modules without running tests')
    parser.add_argument('--timeout', type=int, default=600, help='Seconds per module; includes GUI setup')
    parser.add_argument('--strict-skips', action='store_true', help='Return failure if any case is skipped')
    args=parser.parse_args()
    if args.timeout<1:parser.error('--timeout must be positive')
    modules=sorted(path.stem for path in (HOME/'cases').glob('test_*.py'))
    selected={}
    if args.failed:
        prior=json.loads(args.failed.read_text(encoding='utf-8'))
        for module in prior['modules']:
            if module['status']=='failed':
                selected[module['name']]=[] if module.get('infrastructure_error') or any(r['status']=='error' for r in module['cases']) else [r['id'] for r in module['cases'] if r['status']=='failed']
        modules=[name for name in modules if name in selected]
    if args.module:modules=[name for name in modules if any(fnmatch.fnmatch(name, pattern.removesuffix('.py')) for pattern in args.module)]
    if args.list:
        print('\n'.join(modules));return 0
    if not modules:parser.error('No test modules matched')
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output=HOME/'reports'/timestamp
    output.mkdir(parents=True)
    started=time.monotonic()
    report=dict(status='RUNNING', started_utc=timestamp, seconds=0., python=sys.version,
        platform=platform.platform(), revision=revision(), modules=[], tools={}, selection=dict(modules=modules,cases=args.case,rerun_failed=bool(args.failed)))
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
    env['PYTHONPATH']=os.pathsep.join([str(HOME/'cases'),str(HOME),str(ROOT/'src'),env.get('PYTHONPATH','')])
    try:report['tools']=preflight(env)
    except Exception as error:
        report['modules'].append(dict(name='environment',status='failed',cases=[],infrastructure_error=str(error)))
        print('ENVIRONMENT ERROR:',error)
    else:
        for index,name in enumerate(modules,1):
            print(f'[{index}/{len(modules)}] {name}', flush=True)
            target=output/(name+'.json')
            runtime=output/'workspaces'/name;runtime.mkdir(parents=True)
            command=[sys.executable,str(HOME/'support/worker.py'),name,str(target)]
            for pattern in selected.get(name,args.case):command+=['--case',pattern]
            with (output/(name+'.log')).open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT)
                timed_out=False
                try:code=process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    terminate_tree(process);code=-1;timed_out=True
                except KeyboardInterrupt:
                    terminate_tree(process)
                    report['modules'].append(dict(name=name,status='failed',cases=[],infrastructure_error='Interrupted by user'))
                    break
            if target.exists():module=json.loads(target.read_text(encoding='utf-8'))
            else:module=dict(name=name,status='failed',cases=[],infrastructure_error='Worker exited without a report')
            if code or timed_out:
                module['status']='failed'
                if timed_out:module['infrastructure_error']=f'Timed out after {args.timeout}s; inspect {name}.log'
                elif not module.get('infrastructure_error') and not any(r['status'] in ('failed','error') for r in module['cases']):
                    module['infrastructure_error']=f'Worker exit code {code}; inspect {name}.log'
            report['modules'].append(module)
            print('  '+module['status'].upper()+f" ({len(module['cases'])} cases)", flush=True)
            report['seconds']=round(time.monotonic()-started,3)
            write_reports(output,report)  # Retain partial results if the next module crashes.
    final_revision=revision()
    if any(report['revision'].get(key)!=final_revision.get(key) for key in ('commit','source_sha256','test_assets_sha256')):
        report['modules'].append(dict(name='changed_during_run',status='failed',cases=[],
            infrastructure_error='Code, tests or fixture inputs changed while the suite was running; rerun against a stable revision.'))
    report['not_run_modules']=[name for name in modules if name not in {m['name'] for m in report['modules']}]
    skipped=sum(r['status'] in ('skipped','expected_failure') for m in report['modules'] for r in m['cases'])
    failed=any(m['status']=='failed' for m in report['modules']) or (args.strict_skips and skipped>0)
    report.update(status='FAILED' if failed else 'PASSED_WITH_SKIPS' if skipped else 'PASSED',seconds=round(time.monotonic()-started,3))
    feature_file=HOME/'coverage.json'
    if feature_file.exists():
        features=json.loads(feature_file.read_text(encoding='utf-8'))
        executed={m['name']:m for m in report['modules']}
        for feature in features.values():
            present=[executed[m] for m in feature['modules'] if m in executed]
            feature['status']=('FAILED' if any(m['status']=='failed' for m in present) else
                'NOT_RUN' if not present else
                'PARTIAL' if len(present)!=len(feature['modules']) or args.case or args.failed else
                'PASSED_WITH_SKIPS' if any(r['status'] in ('skipped','expected_failure') for m in present for r in m['cases']) else 'PASSED')
        report['features']=features
    write_reports(output,report)
    (HOME/'reports/latest.json').write_text(json.dumps(dict(directory=timestamp,status=report['status']),indent=2),encoding='utf-8')
    print(report['status']+' — '+str(output/'report.html'))
    return 1 if failed else 0


if __name__=='__main__':sys.exit(main())
