# Four power modes: current-code comparison

Application source was NOT modified in this round. The five production source hashes match before/after; all eight workers loaded the same main/optimizer/pacer hashes.

Test: 24 videos from D:/ncfey/Desktop/test_img/test_video; 16 physical / 22 logical CPUs; 31.43 GiB installed RAM. Layout 4x6, preview tile 320x180, output 1930x726, titles and magnifier off. Inner cache radius 2, multiplier 3, at most 13 composite pages per full window. Manual interval 1 ms, frame skip 0. Fixed available-memory reference 8.40 GiB for every mode; this is not installed RAM. Two fresh-process/fresh-application-cache runs per mode in orders 1,2,3,4 and 4,3,2,1. Each run starts at page 30, warms up for 20 delivered switches and then measures 30 seconds. Native OS/file caches are not flushed. Metadata setup and initial cold start are excluded from the measurement.

CPU is application plus FFmpeg CPU time, normalized to all 22 logical CPUs; it is not whole-system usage or a hard mode ceiling. FPS counts completed full composite-page deliveries through the real wx display_bitmap path, never the sum of 24 streams. The wx window is hidden, so this does not measure physical display refresh or visible-window painting overhead. All delivered page IDs were continuous. Input clips are 10.1 / 32.233 seconds long, not long-video validation.

| Mode | Worker budget | RAM budget GiB | Mean CPU | FPS | Median configured interval s | Mean RSS GiB | Mean P95 switch gap s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Eco | 5 | 1.26 | 30.30% | 0.666 | 1.484 | 0.87 | 2.373 |
| Balanced | 11 | 2.52 | 46.36% | 0.850 | 1.064 | 1.21 | 1.968 |
| Performance | 16 | 4.20 | 52.22% | 0.933 | 1.046 | 1.12 | 1.664 |
| Maximum | 22 | 6.30 | 53.11% | 0.999 | 0.946 | 1.62 | 1.680 |

Maximum vs Performance: worker budget +37.5%, RAM budget +50%, FPS +7.17%, CPU +0.89 percentage points.

## Diagnostic limits and evidence

Two repeats characterize this workload, not statistical confidence or a guarantee of linear scaling. Mode changes worker and RAM budgets together, so their individual causal effects are not separated. Background workloads and OS cache state are not controlled. Service-duration histories are rolling samples, not exclusive CPU times or a full stage profiler.

Forward-buffer empty percentage in summary.json means no consecutive ready future composite, NOT percentage of time the GUI was frozen. Allocation changes are changes seen at 200 ms sampling and can undercount very fast changes. Measured plans changed 2-10 times per 30-second window. Actual RSS can exceed a modeled mode budget; current budgets are soft estimates, not OS process quotas.

## Code-backed bottlenecks

- main.py _save_frame: a short-lived FFmpeg process is launched per missing contiguous range; the conservative selection branch has no input seek and decodes from the start. The vframes bound stops at the target end but does not remove the prefix decode. Metadata enabled fast seek for only 12/24 streams in every run.
- main.py _queue_extract_run and _queue_window_stitch: composite readiness depends on whole extraction-run futures across all required videos, not individual frame arrival. Temporary output files are published after FFmpeg exits.
- main.py _rebalance_thread_pools: cancels queued tasks, waits for running extraction/composition work and reconstructs pools, then repopulates the queue. This can interrupt useful overlap; duration/impact still need dedicated timing.
- Hot path: decode video -> encode/write JPEG -> decode JPEG in get_img_list -> resize/compose/deepcopy -> encode/write PNG -> decode PNG in _prepare_video_image -> construct wx bitmap. Python loops, copies and metadata reads coexist with native operations. Do not assume the GIL alone explains the result.
- Same temporal cache window across modes; more RAM budget does not create additional work or automatically store decoded pixels. More workers may increase individual job service time through contention. Physical/SMT/heterogeneous core capacity, storage and memory bandwidth prevent a universal linear budget-to-FPS law.

## Feasible proposals only (not implemented)

1. Keep decoder/container state alive per video; decode sequentially during forward playback. Schedule bounded quanta under the global CPU budget. Random seeks/reverse use a keyframe/PTS-to-frame index and precise verification; retain the conservative fallback. PyAV/libav can expose incremental decode: https://pyav.org/docs/stable/cookbook/basics.html .
2. Publish each complete decoded frame immediately and schedule a composite as soon as its exact source frames exist. Remove whole-run barriers while keeping short contiguous decode batches to amortize startup/seek. Use bounded slots, generation tokens and cleanup outside the existing outer window.
3. Use memory-resident raw-frame and composite buffers for the hot path, keeping both inner/outer temporal windows and the existing disk compatibility path. Disk persistence is asynchronous and bounded. Shared memory can avoid serializing large pixel buffers between processes: https://docs.python.org/3.9/library/multiprocessing.shared_memory.html . Preserve original-resolution sources for magnification, crop, custom algorithms and export; display-sized previews are a separate derived cache.
4. Keep the worker pool alive; adjust global task admission tokens instead of stopping all stages to rebuild pools. Count native decoder/filter threads as well as Python compute tasks. Borrow capacity according to runnable queue pressure and measured marginal useful-throughput gain, not CPU usage alone.
5. Parallelize tile decode/preprocessing across videos and compose independent pages/tiles with cached layout geometry. Avoid unnecessary full-image deep copies and video-frame EXIF rereads. Profile Python versus native work before selecting threads or processes; pass immutable settings and shared pixel buffers, never wx objects, to process workers. ProcessPool can bypass Python GIL limits, with pickling constraints: https://docs.python.org/3.9/library/concurrent.futures.html#processpoolexecutor .
6. Validate each change with stage throughput, useful/duplicate decoded frames, time awaiting exact inputs, productive duty cycle, resize drain time, memory bytes/page and foreground GUI delivery tails. First remove repeat work, I/O round trips and barriers; then tune allocation. Interval follows the improved supply curve without a fixed slowdown margin.

## Scaling model

For aggregate per-composite extraction work E, composition work S, active allocations e and s, and GUI service time D: FPS <= min(e/E, s/S, 1/D, IO_bandwidth/IO_bytes_per_page, memory_bandwidth/memory_bytes_per_page). Subject to e+s<=mode_worker_budget and working_sets+bounded_cache<=mode_memory_budget. E/S depend on contention and are not constants across arbitrary thread counts. Near-linear scaling is feasible only while useful independent work dominates and no other ceiling is hit. Serial work, decoder dependencies and GUI delivery prevent guaranteeing exact linear scaling for all videos/layouts.
