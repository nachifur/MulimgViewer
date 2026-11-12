"""Repeatable real-input wx delivery benchmark, with fresh per-run disk caches.

The `previous-policy` ablation disables only the new raw-inventory/dual-level
pressure control. It is not a reconstruction of an entire historical build.
No production source or input video is modified.
"""
import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)


def probe_manifest(folder):
    import psutil
    from mulimgviewer.src.video_tools import resolve_video_tools
    tools, env = resolve_video_tools()
    videos = []
    for path in sorted(folder.glob('*.mp4'), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem):
        probe = json.loads(subprocess.check_output([tools['ffprobe'], '-v', 'error',
            '-select_streams', 'v:0', '-show_entries',
            'stream=codec_name,width,height,avg_frame_rate,nb_frames,duration', '-of', 'json', str(path)], env=env))
        stream = probe['streams'][0]
        numerator, denominator = stream['avg_frame_rate'].split('/')
        videos.append(dict(path=str(path.resolve()), size=path.stat().st_size,
            fps=float(numerator) / float(denominator), frames=int(stream['nb_frames']),
            duration=float(stream['duration']), width=stream['width'], height=stream['height'], codec=stream['codec_name']))
    if len(videos) != 24:
        raise ValueError(f'Preset expects 24 input videos, found {len(videos)}')
    return dict(videos=videos, logical_cpus=os.cpu_count(), ram_bytes=psutil.virtual_memory().total,
        memory_reference=psutil.virtual_memory().available, python=sys.executable,
        layout='4,6', preview='320,180', cache_frames=2, cache_multiplier=3,
        manual_interval=.001, warmup_frames=20, measure_frames=200, start_frame=30,
        delivery='hidden wx window; actual display_bitmap completion, not physical monitor refresh',
        baseline='current code with raw-inventory/dual-threshold pressure control disabled')


def worker(args):
    import psutil
    import wx
    from mulimgviewer.src.main import MulimgViewer
    from mulimgviewer.src.resource_monitor import CHILD_CPU
    from mulimgviewer.src.video_tools import resolve_video_tools

    class Viewer(MulimgViewer):
        def check_version(self):
            pass
        def load_configuration(self, *args, **kwargs):
            pass
        def _restore_window_state(self):
            pass

    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    output = Path(args.output).resolve()
    run_dir = output.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(run_dir)
    app = wx.App(False)
    viewer = Viewer(None, lambda *a, **k: None, lambda *a, **k: None)
    viewer.Hide()
    cfg, vm = viewer.shared_config, viewer.video_manager
    if args.policy == 'previous-policy':
        vm._raw_buffer_inventory = lambda depth: None
    vm._video_tools, vm._video_tools_env = resolve_video_tools()
    cfg.video_mode, cfg.input_mode = True, 1
    cfg.real_video_path = [v['path'] for v in manifest['videos']]
    cfg.video_path = [str(run_dir / 'Video_frames' / f'stream_{index:02}') for index in range(24)]
    metadata_started = time.monotonic()
    metadata = [vm._get_meta(v['path']) for v in manifest['videos']]
    metadata_seconds = time.monotonic() - metadata_started
    cfg.video_num_list = [frames for fps, frames in metadata]
    cfg.video_fps_list = [fps for fps, frames in metadata]
    for path in cfg.video_path:
        Path(path).mkdir(parents=True, exist_ok=True)
    viewer.ImgManager.init(cfg.video_path, type=1, video_mode=True,
        video_fps_list=cfg.video_fps_list, video_num_list=cfg.video_num_list, skip=0)
    viewer._resource_memory_reference = manifest['memory_reference']
    viewer.row_col.ChangeValue(manifest['layout'])
    viewer.row_col_one_img.ChangeValue('1,1')
    viewer.img_resolution.ChangeValue(manifest['preview'])
    viewer.row_col_img_unit.ChangeValue('1,1')
    viewer.gap.ChangeValue('2,2,0,0,0,0,0,0')
    viewer.title_show.SetValue(False)
    viewer.show_magnifer.SetValue(False)
    viewer.show_original.SetValue(True)
    viewer.auto_layout_check.SetValue(False)
    viewer.cache_frames.ChangeValue(str(manifest['cache_frames']))
    viewer.cache_multiplier.ChangeValue(str(manifest['cache_multiplier']))
    viewer.interval.ChangeValue(str(manifest['manual_interval']))
    viewer.power_mode.SetSelection(args.mode - 1)
    viewer._commit_video_settings()
    viewer.show_img_init()
    cfg.batch_idx = manifest['start_frame']
    viewer.ImgManager.set_action_count(cfg.batch_idx)

    state = dict(initial=False, warm=0, start=None, cpu_start=None, cpu_end=None,
                 done=False, timeout=False, frames=[], end=None, output_size=None)
    stop_sampler = threading.Event()
    samples, heartbeat, allocation = [], [], []
    process = psutil.Process()
    run_start = time.monotonic()

    def cpu_total():
        children = [] if sys.platform == 'win32' else process.children(recursive=True)
        return time.process_time() + CHILD_CPU.total(children)

    def sample():
        while not stop_sampler.is_set():
            if state['start'] is not None:
                rss = process.memory_info().rss
                for child in process.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                samples.append((time.monotonic(), rss))
                allocation.append((time.monotonic(), vm._extract_threads, vm._stitch_threads,
                    cfg.interval, vm._compute_buffer_depth(), cfg.thread_allocation_recommend))
            stop_sampler.wait(.2)
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    display = viewer.display_bitmap

    def stop():
        cfg.is_playing = False
        viewer.play_timer.Stop()
        state['end'] = time.monotonic()
        state['cpu_end'] = cpu_total()
        app.ExitMainLoop()

    def painted(*params, **kwargs):
        result = display(*params, **kwargs)
        now = time.monotonic()
        state['output_size'] = list(params[1].size)
        if not state['initial']:
            state['initial'] = True
            state['first_frame_seconds'] = now - run_start
            wx.CallAfter(viewer.toggle_play, None)
        elif cfg.is_playing:
            state['warm'] += 1
            if state['warm'] == manifest['warmup_frames']:
                state['start'] = now
                state['cpu_start'] = cpu_total()
            elif state['warm'] > manifest['warmup_frames']:
                state['frames'].append((cfg.batch_idx, now))
                if len(state['frames']) >= manifest['measure_frames']:
                    stop()
        return result
    viewer.display_bitmap = painted

    def tick():
        if state['done']:
            return
        heartbeat.append(time.monotonic())
        elapsed = time.monotonic() - run_start
        if int(elapsed // 15) > state.get('last_progress', -1):
            state['last_progress'] = int(elapsed // 15)
            print(json.dumps(dict(progress=True, elapsed=round(elapsed, 1),
                batch=cfg.batch_idx, warm=state['warm'], measured=len(state['frames']),
                plan=[vm._extract_threads, vm._stitch_threads], interval=cfg.interval,
                output_size=state['output_size'])), flush=True)
        if state['start'] is not None and args.duration and time.monotonic() - state['start'] >= args.duration:
            stop()
        elif elapsed > args.timeout:
            state['timeout'] = True
            stop()
        else:
            wx.CallLater(50, tick)
    wx.CallAfter(tick)
    wx.CallAfter(vm.update_cache)
    app.MainLoop()
    state['done'] = True
    stop_sampler.set()
    sampler.join(timeout=3)
    end = state['end']
    elapsed = end - state['start'] if state['start'] is not None else None
    gaps = []
    previous = state['start']
    for _, timestamp in state['frames']:
        gaps.append(timestamp - previous)
        previous = timestamp
    memory = [rss for timestamp, rss in samples if state['start'] is not None and state['start'] <= timestamp <= end]
    gui = [timestamp for timestamp in heartbeat if state['start'] is not None and state['start'] <= timestamp <= end]
    gui_gaps = [b-a for a, b in zip(gui, gui[1:])]
    frames = [index for index, _ in state['frames']]
    result = dict(policy=args.policy, mode=args.mode, budget=cfg.thread,
        memory_budget=cfg.memory_budget, completed=(not state['timeout'] and state['start'] is not None),
        measured_frames=len(frames), elapsed_seconds=elapsed,
        fps=len(frames) / elapsed if elapsed else None,
        cpu_percent=(state['cpu_end'] - state['cpu_start']) / elapsed / manifest['logical_cpus'] * 100 if elapsed else None,
        rss_avg_mib=statistics.mean(memory)/1024**2 if memory else None,
        rss_peak_mib=max(memory)/1024**2 if memory else None,
        p50_gap_ms=percentile(gaps, .5)*1000 if gaps else None,
        p95_gap_ms=percentile(gaps, .95)*1000 if gaps else None,
        max_gap_ms=max(gaps)*1000 if gaps else None,
        gaps_over_100ms=sum(gap > .1 for gap in gaps), gaps_over_250ms=sum(gap > .25 for gap in gaps),
        gui_p95_gap_ms=percentile(gui_gaps, .95)*1000 if gui_gaps else None,
        gui_max_gap_ms=max(gui_gaps)*1000 if gui_gaps else None,
        continuous=all(b == a+1 for a, b in zip(frames, frames[1:])),
        frame_range=[frames[0], frames[-1]] if frames else [],
        first_frame_seconds=state.get('first_frame_seconds'), timeout=state['timeout'],
        requested_measure_seconds=args.duration,
        metadata_seconds=metadata_seconds,
        fast_seek_streams=sum(vm._fast_seek_paths.values()),
        decode_dimensions_known=len(vm._video_dimensions),
        extract_run_p90_seconds=percentile(list(vm.perf_monitor.extract_run_history), .9),
        stitch_average_seconds=statistics.mean(vm.perf_monitor.stitch_history) if vm.perf_monitor.stitch_history else None,
        warmup_frames=manifest['warmup_frames'],
        source_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'src/mulimgviewer/src/main.py', 'src/mulimgviewer/src/thread_optimizer.py',
            'src/mulimgviewer/src/playback_pacer.py')},
        final_pending_wait_ms=(end-previous)*1000 if previous is not None else None,
        output_size=state['output_size'], final_allocation=[vm._extract_threads, vm._stitch_threads],
        allocation_samples=allocation, paints=state['frames'], latest_status=cfg.video_last_message)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('allocation_samples','paints')}), flush=True)
    viewer._is_closing = True
    viewer._cancel_pending_frame_wait()
    viewer.resource_monitor.close()
    viewer.memory_reclaimer.close()
    viewer.image_pipeline.close()
    vm.shutdown()
    for pool in (vm._cache_executor, vm.executor, vm.stitch_executor, vm._maintenance_executor, vm._display_executor):
        pool.shutdown(wait=True)
    viewer.Destroy()


def matrix(args):
    destination = Path(args.output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest = Path(args.manifest).resolve()
    # Counterbalance ordering to reduce filesystem-cache/order bias.
    orders = [[('current', 3), ('previous-policy', 3), ('previous-policy', 4), ('current', 4)],
              [('previous-policy', 3), ('current', 3), ('current', 4), ('previous-policy', 4)]]
    results = []
    for repeat, order in enumerate(orders, 1):
        for policy, mode in order:
            output = destination / f'{policy.replace("-policy", "")}_{mode}_r{repeat}' / 'result.json'
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists():
                command = [sys.executable, str(Path(__file__).resolve()), '--manifest', str(manifest),
                    '--output', str(output), '--policy', policy, '--mode', str(mode),
                    '--timeout', str(args.timeout), '--duration', str(args.duration)]
                print(json.dumps(dict(start=True, repeat=repeat, policy=policy, mode=mode)), flush=True)
                with output.with_suffix('.log').open('w', encoding='utf-8') as log:
                    process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=args.timeout + 90)
                if process.returncode or not output.exists():
                    raise RuntimeError(f'Benchmark failed: {output.with_suffix(".log")}')
            result = json.loads(output.read_text(encoding='utf-8'))
            result['repeat'] = repeat
            results.append(result)
            print(json.dumps({key: result[key] for key in ('policy','mode','repeat','completed','fps',
                'cpu_percent','rss_avg_mib','p95_gap_ms','measured_frames','elapsed_seconds')}), flush=True)
            (destination / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    summary = []
    for mode in (3, 4):
        row = dict(mode=mode)
        for policy in ('previous-policy', 'current'):
            rows = [result for result in results if result['mode'] == mode and result['policy'] == policy]
            row[policy] = {key: statistics.median(result[key] for result in rows) for key in
                ('fps','cpu_percent','rss_avg_mib','rss_peak_mib','p95_gap_ms','max_gap_ms','gui_max_gap_ms')}
        row['fps_gain_percent'] = (row['current']['fps']/row['previous-policy']['fps']-1)*100
        summary.append(row)
    (destination / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--manifest')
    parser.add_argument('--output', required=True)
    parser.add_argument('--policy', choices=['current', 'previous-policy'], default='current')
    parser.add_argument('--mode', type=int, choices=[3, 4], default=3)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--matrix', action='store_true')
    args = parser.parse_args()
    if args.folder:
        manifest = probe_manifest(args.folder)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in manifest.items() if k != 'videos'}), flush=True)
    elif args.matrix:
        matrix(args)
    else:
        worker(args)


if __name__ == '__main__':
    main()
