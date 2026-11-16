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

ROOT = Path(__file__).resolve().parents[2]
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

    loaded=Path(sys.modules[MulimgViewer.__module__].__file__).resolve()
    expected=(ROOT/'src/mulimgviewer/src/main.py').resolve()
    if loaded!=expected:
        raise RuntimeError(f'Comparison loaded wrong source: {loaded}; expected {expected}')

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
    if getattr(args,'unpaced',False):
        vm._refresh_playback_interval=lambda *a,**k:None
    sequence = getattr(args, 'sequence', None)
    sequence = [int(value) for value in sequence.split(',')] if sequence else []
    if sequence and (any(mode not in (1,2,3,4) for mode in sequence) or args.duration):
        raise ValueError('Sequence requires modes 1..4 and --duration 0 (fixed frames per phase)')
    phase_results = []
    phase = dict(index=0)
    if getattr(args, 'fixed_admission', False) or getattr(args, 'fixed_plan', None):
        def fixed_admission():
            return vm._admission_optimizer.configure(max(2,int(cfg.thread)),
                vm._pacing_context(), enabled=False)
        vm._admission_limit = fixed_admission
    if getattr(args, 'fixed_plan', None):
        fixed_plan = tuple(int(v) for v in args.fixed_plan.split(','))
        if len(fixed_plan)!=2 or min(fixed_plan)<1:
            raise ValueError('Fixed plan must be positive extract,stitch counts')
        vm._maybe_evaluate_performance = lambda force=False: None
        vm._enforce_thread_budget = lambda: vm._apply_thread_plan(*fixed_plan)
    probe = None
    if getattr(args, 'probe', False):
        sys.path.insert(0,str(ROOT/'auto_test_scripts/performance'))
        from video_pipeline_probe import PipelineProbe
        probe = PipelineProbe(vm)
    mosaic_profiles=[];profile_lock=threading.Lock()
    if getattr(args,'profile_mosaic',False):
        import cProfile
        from mulimgviewer.src.mosaic_pipeline import MosaicPlan
        build=MosaicPlan._build
        def profiled_build(*a,**k):
            profile=cProfile.Profile()
            try:return profile.runcall(build,*a,**k)
            finally:
                with profile_lock:mosaic_profiles.append(profile)
        MosaicPlan._build=profiled_build
    if getattr(args, 'baseline_hotpath', None):
        import importlib.util
        spec = importlib.util.spec_from_file_location('video_hotpath_baseline',args.baseline_hotpath)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        vm._pixel_cache = baseline.PixelCache()
        vm._configure_video_memory()
        from mulimgviewer.src.video_decoder import DecoderSession
        DecoderSession._buffered_image = staticmethod(lambda frame: frame.to_image())
        def baseline_admission():
            indices,_ = vm._playback_video_indices()
            budget=max(2,int(cfg.thread))
            return vm._admission_optimizer.configure(budget,(vm._pacing_context(),tuple(indices)),
                enabled=cfg.video_mode and cfg.power_mode>=3 and len(indices)>=2 and budget>=4,
                warmup=max(8,2*int(cfg.cache_num)*int(cfg.cache_multiplier)+1))
        vm._admission_limit = baseline_admission
    if args.policy == 'previous-policy':
        vm._raw_buffer_inventory = lambda depth: None
    if getattr(args,'comparison_module',None):
        import importlib.util
        import types
        spec=importlib.util.spec_from_file_location('previous_iteration',args.comparison_module)
        previous=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(previous)
        from mulimgviewer.src.video_decoder import DecoderSession
        DecoderSession._buffered_image=staticmethod(previous.image_from_plane)
        vm._trim_video_window=types.MethodType(previous.trim_video_window,vm)
    if 'pixel_cache_limit' in manifest:
        configure_pixels=vm._pixel_cache.configure
        vm._pixel_cache.configure=lambda limit: configure_pixels(int(manifest['pixel_cache_limit']))
        vm._pixel_cache.configure(0)
    if manifest.get('debug_stitch_errors'):
        original_stitch=vm._run_window_stitch
        def checked_stitch(*args,**kwargs):
            try:return original_stitch(*args,**kwargs)
            except Exception:
                import traceback
                traceback.print_exc()
                raise
        vm._run_window_stitch=checked_stitch
    vm._video_tools, vm._video_tools_env = resolve_video_tools()
    cfg.video_mode, cfg.input_mode = True, 1
    cfg.real_video_path = [v['path'] for v in manifest['videos']]
    cfg.video_path = [str(run_dir / 'cache_frames' / f'stream_{index:02}') for index in range(len(manifest['videos']))]
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
    viewer.row_col_img_unit.ChangeValue(manifest.get('unit_layout','1,1'))
    viewer.gap.ChangeValue('2,2,0,0,0,0,0,0')
    viewer.title_show.SetValue(bool(manifest.get('title_show',False)))
    viewer.show_magnifer.SetValue(bool(manifest.get('show_magnifer',False)))
    viewer.show_original.SetValue(True)
    viewer.auto_layout_check.SetValue(False)
    viewer.cache_frames.ChangeValue(str(manifest['cache_frames']))
    viewer.cache_multiplier.ChangeValue(str(manifest['cache_multiplier']))
    viewer.interval.ChangeValue(str(manifest['manual_interval']))
    viewer.power_mode.SetSelection((sequence[0] if sequence else args.mode) - 1)
    if getattr(args,'config',None):
        values=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))['output']
        for name,value in values.items():
            control=getattr(viewer,name,None)
            if isinstance(control,wx.Choice):control.SetSelection(int(value))
            elif isinstance(control,wx.CheckBox):control.SetValue(bool(value))
            elif isinstance(control,wx.TextCtrl):control.ChangeValue(str(value))
        viewer.power_mode.SetSelection((sequence[0] if sequence else args.mode)-1)
    if getattr(args,'parallel',False):
        viewer.parallel_to_sequential.SetValue(False)
        viewer.parallel_sequential.SetValue(False)
    if getattr(args,'manual_interval',None) is not None:
        viewer.interval.ChangeValue(str(args.manual_interval))
    # ChangeValue does not emit a user edit. Explicitly mark this benchmark's
    # requested floor, including when it equals the default/current interval.
    viewer._interval_user_edited = True
    requested_interval = float(viewer.interval.GetValue())
    viewer._commit_video_settings()
    if cfg.manual_interval is None or abs(cfg.manual_interval-requested_interval)>0.001:
        raise RuntimeError('Benchmark manual interval was not applied')
    if manifest.get('magnifier_points'):
        viewer.xy_magnifier=manifest['magnifier_points']
        viewer.color_list=[wx.Colour(255,0,0) for _ in viewer.xy_magnifier]
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
            rss = process.memory_info().rss
            for child in process.children(recursive=True):
                try:
                    rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            samples.append((time.monotonic(), rss))
            if probe is not None:
                probe.sample()
            if state['start'] is not None:
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
        if probe is not None:
            state['probe'] = probe.finish(time.perf_counter())
        app.ExitMainLoop()

    def finish_phase():
        now = time.monotonic()
        group = vm._pipeline_workers
        memory = process.memory_info()
        with group.lock:
            queue_counts = [len(queue) for queue in group.queues]
            handles = [len(items) for items in group.handles]
        with vm._cache_guard:
            pending = [len(vm._pending_extract), len(vm._window_stitches), len(vm._raw_batch_futures)]
        row = dict(index=phase['index'], mode=sequence[phase['index']],
            fps=len(state['frames'])/(now-state['start']),
            cpu_percent=(cpu_total()-state['cpu_start'])/(now-state['start'])/manifest['logical_cpus']*100,
            rss_mib=memory.rss/1024**2, private_mib=getattr(memory,'private',0)/1024**2,
            os_threads=process.num_threads(), python_threads=threading.active_count(),
            pending_maps=pending, queue_counts=queue_counts, handles=handles,
            pixel_cache_bytes=vm._pixel_cache.bytes,
            resident_decoders=sum(d.container is not None for d in vm._decoder_bank.sessions.values()),
            decoder_objects=len(vm._decoder_bank.sessions),
            admission=vm._admission_optimizer.snapshot(), effective_cpu_budget=group.total_budget,
            frames=[state['frames'][0][0],state['frames'][-1][0]],
            elapsed_seconds=now-state['start'])
        phase_results.append(row)
        print(json.dumps(dict(phase_result=row)),flush=True)
        if phase['index']+1 == len(sequence):
            stop()
            return
        cfg.is_playing=False
        viewer.play_timer.Stop()
        phase['index'] += 1
        def restart():
            # Replay identical frame IDs; retain the process, decoder bank,
            # pools and all real policy/reclaim state between modes.
            state.update(initial=False,warm=0,start=None,cpu_start=None,frames=[])
            cfg.batch_idx=manifest['start_frame']
            viewer.ImgManager.set_action_count(cfg.batch_idx)
            viewer.power_mode.SetSelection(sequence[phase['index']]-1)
            viewer.on_power_mode_changed(None)
        wx.CallAfter(restart)

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
                if probe is not None:
                    probe.start()
                if getattr(args,'profile_ready_file',None):
                    Path(args.profile_ready_file).write_text(json.dumps(dict(pid=os.getpid(),started=now)),encoding='utf-8')
            elif state['warm'] > manifest['warmup_frames']:
                state['frames'].append((cfg.batch_idx, now))
                if len(state['frames']) >= manifest['measure_frames']:
                    finish_phase() if sequence else stop()
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
                output_size=state['output_size'], status=cfg.video_last_message,
                cache_error=(repr(vm._cache_update_future.exception()) if vm._cache_update_future is not None and vm._cache_update_future.done() and not vm._cache_update_future.cancelled() else None),
                locks=(dict(state=repr(vm._cache_guard),bank=repr(vm._decoder_bank.lock),
                    group=repr(vm._pipeline_workers.lock),pending=repr(vm._pending_lock),
                    raw={str(k):repr(v) for k,v in list(vm._raw_io_locks.items())},
                    threads={t.name:t.ident for t in threading.enumerate()})
                    if getattr(args,'dump_stacks_after',0) and not state['initial'] else None))), flush=True)
        if state['start'] is not None and args.duration and time.monotonic() - state['start'] >= args.duration:
            stop()
        elif elapsed > args.timeout:
            state['timeout'] = True
            stop()
        else:
            wx.CallLater(50, tick)
    wx.CallAfter(tick)
    wx.CallAfter(vm.update_cache)
    if getattr(args,'dump_stacks_after',0):
        import faulthandler
        faulthandler.dump_traceback_later(args.dump_stacks_after, repeat=True)
    app.MainLoop()
    if getattr(args,'dump_stacks_after',0):
        faulthandler.cancel_dump_traceback_later()
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
    result = dict(policy=args.policy, mode=cfg.power_mode, budget=cfg.thread,
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
        rss_peak_entire_run_mib=max((rss for _,rss in samples),default=0)/1024**2,
        pacing_stats=dict(period=vm._playback_pacer.period, pending=sorted(vm._playback_pacer.pending),
                          samples=list(vm._playback_pacer.samples), prediction=getattr(cfg,'interval_prediction',None)),
        pipeline_stats=dict(
            native_decoder_opens=sum(d.opens for d in vm._decoder_bank.sessions.values()),
            native_decoded_frames=sum(d.decoded for d in vm._decoder_bank.sessions.values()),
            native_seeks=sum(d.seeks for d in vm._decoder_bank.sessions.values()),
            native_fallback_paths=len(vm._decoder_bank.disabled),
            pixel_cache_bytes=vm._pixel_cache.bytes, pixel_cache_limit=vm._pixel_cache.limit,
            decoder_state_limit=vm._decoder_bank.limit,
            active_stage_counts=list(vm._pipeline_workers.active),
            decoder_activity=vm._pipeline_workers.activity_snapshot(),
            downstream_activity=viewer.image_pipeline.processing.snapshot(),
            admission=vm._admission_optimizer.snapshot(),
            effective_cpu_budget=vm._pipeline_workers.total_budget,
            stage_target=getattr(cfg,'stage_allocation_target',None)),
        source_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'src/mulimgviewer/src/main.py', 'src/mulimgviewer/src/video_manager.py',
            'src/mulimgviewer/src/video_playback.py', 'src/mulimgviewer/src/viewer_state.py',
            'src/mulimgviewer/src/configuration.py', 'src/mulimgviewer/src/configuration_controller.py',
            'src/mulimgviewer/src/thread_optimizer.py',
            'src/mulimgviewer/src/playback_pacer.py', 'src/mulimgviewer/src/utils_img.py',
            'src/mulimgviewer/src/pipeline_executor.py', 'src/mulimgviewer/src/video_decoder.py',
            'src/mulimgviewer/src/video_memory.py', 'src/mulimgviewer/src/admission_optimizer.py',
            'src/mulimgviewer/src/custom_pipeline.py', 'src/mulimgviewer/src/mosaic_pipeline.py',
            'src/mulimgviewer/src/dependency_scheduler.py', 'src/mulimgviewer/src/custom_workers.py',
            'src/mulimgviewer/src/image_pipeline.py',
            'src/mulimgviewer/src/cache_layout.py', 'src/mulimgviewer/src/render_metrics.py',
            'src/mulimgviewer/src/resource_policy.py') if (ROOT/name).is_file()},
        run_settings=dict(source_root=str(ROOT),loaded_main=str(loaded),config=getattr(args,'config',None),
                          parallel_to_sequential=cfg.parallel_to_sequential,
                          layout=viewer.row_col.GetValue(),unit=viewer.row_col_one_img.GetValue(),
                          scale=viewer.show_scale.GetValue(),resolution=viewer.img_resolution.GetValue(),
                          cache_frames=cfg.cache_num,cache_multiplier=cfg.cache_multiplier,
                          manual_interval=cfg.manual_interval),
        final_pending_wait_ms=(end-previous)*1000 if previous is not None else None,
        output_size=state['output_size'], final_allocation=[vm._extract_threads, vm._stitch_threads],
        allocation_samples=allocation, paints=state['frames'], latest_status=cfg.video_last_message,
        sequence_results=phase_results,
        experiment=dict(comparison_module=bool(getattr(args,'comparison_module',None)),
                        unpaced=bool(getattr(args,'unpaced',False)),
                        baseline_hotpath=bool(getattr(args,'baseline_hotpath',None)),
                        fixed_admission=getattr(args,'fixed_admission',False),
                        fixed_plan=getattr(args,'fixed_plan',None)),
        probe=state.get('probe'))
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    if mosaic_profiles:
        import pstats
        stats=pstats.Stats(mosaic_profiles[0])
        for profile in mosaic_profiles[1:]:stats.add(profile)
        stats.dump_stats(str(output.with_suffix('.prof')))
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
    if probe is not None:
        probe.close()


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


def power_matrix(args):
    """Two counterbalanced repeats on one frozen source and input snapshot."""
    destination=Path(args.output).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    manifest=Path(args.manifest).resolve()
    names=('main','thread_optimizer','playback_pacer','utils_img','pipeline_executor','video_decoder','video_memory','admission_optimizer')
    initial={name:hashlib.sha256((ROOT/'src/mulimgviewer/src'/f'{name}.py').read_bytes()).hexdigest() for name in names}
    input_hash=hashlib.sha256(manifest.read_bytes()).hexdigest()
    results=[]
    for repeat,order in enumerate(((1,2,3,4),(4,3,2,1)),1):
        for mode in order:
            output=destination/f'mode_{mode}_r{repeat}'/'result.json'
            output.parent.mkdir(parents=True,exist_ok=True)
            print(json.dumps(dict(start=True,mode=mode,repeat=repeat)),flush=True)
            command=[sys.executable,str(Path(__file__).resolve()),'--manifest',str(manifest),
                     '--output',str(output),'--mode',str(mode),'--policy','current',
                     '--duration',str(args.duration),'--timeout',str(args.timeout)]
            with output.with_suffix('.log').open('w',encoding='utf-8') as log:
                process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,
                    timeout=args.timeout+90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if process.returncode or not output.exists():
                raise RuntimeError('Benchmark failed: '+str(output.with_suffix('.log')))
            row=json.loads(output.read_text(encoding='utf-8'))
            if not row['completed'] or row['timeout'] or not row['continuous']:
                raise RuntimeError('Incomplete benchmark: '+str(output))
            row['repeat']=repeat
            results.append(row)
            (destination/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps({key:row[key] for key in ('mode','repeat','fps','cpu_percent','rss_avg_mib','p95_gap_ms')}),flush=True)
    final={name:hashlib.sha256((ROOT/'src/mulimgviewer/src'/f'{name}.py').read_bytes()).hexdigest() for name in names}
    assert initial==final,'Production source changed during comparison'
    assert input_hash==hashlib.sha256(manifest.read_bytes()).hexdigest(),'Input manifest changed'
    (destination/'source_snapshot.json').write_text(json.dumps(dict(source_hashes=final,input_sha256=input_hash),indent=2),encoding='utf-8')


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--manifest')
    parser.add_argument('--output', required=True)
    parser.add_argument('--policy', choices=['current', 'previous-policy'], default='current')
    parser.add_argument('--mode', type=int, choices=[1, 2, 3, 4], default=3)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--dump-stacks-after',type=float,default=0)
    parser.add_argument('--comparison-module', help='Benchmark-only previous converter and cleanup methods')
    parser.add_argument('--baseline-hotpath', help='Benchmark-only archived pre-change pixel-cache module')
    parser.add_argument('--profile-ready-file')
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--profile-mosaic',action='store_true',help='Benchmark-only per-worker cProfile diagnostics')
    parser.add_argument('--unpaced',action='store_true',help='Diagnostic only: consume ready frames immediately at the manual floor')
    parser.add_argument('--fixed-admission', action='store_true')
    parser.add_argument('--fixed-plan', help='Benchmark-only fixed extract,stitch reservations')
    parser.add_argument('--sequence', help='Same-process power modes, e.g. 4,1,4; requires --duration 0')
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--power-matrix', action='store_true')
    parser.add_argument('--source-root',type=Path,help='Read-only comparison with another source tree')
    parser.add_argument('--config',help='Apply output controls from a JSON config before playback')
    parser.add_argument('--parallel',action='store_true',help='Disable both serial conversion options')
    parser.add_argument('--manual-interval',type=float,help='Override the user interval for throughput measurement')
    args = parser.parse_args()
    if args.config:args.config=str(Path(args.config).resolve())
    if args.source_root:
        ROOT=args.source_root.resolve()
        if not (ROOT/'src/mulimgviewer/src/main.py').is_file():
            parser.error('Comparison source root is missing main.py; refusing installed-source fallback')
        sys.path.insert(0,str(ROOT/'src'))
    if args.folder:
        manifest = probe_manifest(args.folder)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in manifest.items() if k != 'videos'}), flush=True)
    elif args.power_matrix:
        power_matrix(args)
    elif args.matrix:
        matrix(args)
    else:
        worker(args)


if __name__ == '__main__':
    main()
