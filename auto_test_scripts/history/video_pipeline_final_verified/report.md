# Final video-pipeline verification

## Test scope

Windows, 22 logical CPUs, 31.43 GiB RAM. The same 24 user videos and baseline memory reference are used. Layout 4x6; preview 320x180; cache_frames=2, multiplier=3; manual floor 1 ms. Each mode has two counterbalanced repeats (1,2,3,4 then 4,3,2,1), with 20 warmup deliveries and 30 seconds measured. Inputs stop before shorter streams end. FPS counts complete composite pages delivered through real wx display_bitmap; it is not per-source FPS or physical monitor refresh. The window is hidden; interactive desktop behavior can differ.

CPU is application plus registered FFmpeg children, normalized by 22 logical CPUs. All 8 source-module hashes match across all runs and the retained final source. No forced delay or image-quality reduction is used for this comparison. Historical baseline and current results are separate sequential experiments, not simultaneous paired measurements; two repeats cannot establish statistical significance.

## Same-setting comparison

| Mode | Budget | Previous FPS | Current FPS (two runs) | Speedup | Previous CPU | Current CPU | Peak RSS GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Eco | 5 | 0.666 | 1.148 (1.132, 1.164) | 1.72x | 30.30% | 21.20% | 0.73 |
| Balanced | 11 | 0.850 | 2.264 (2.130, 2.398) | 2.66x | 46.36% | 30.51% | 1.45 |
| Performance | 16 | 0.933 | 4.114 (3.867, 4.362) | 4.41x | 52.22% | 24.34% | 1.91 |
| Maximum | 22 | 0.999 | 4.108 (4.298, 3.919) | 4.11x | 53.11% | 23.84% | 1.91 |

Maximum vs Performance: budget +37.5%, memory allowance +50%, measured mean FPS -0.1%. This is not linear scaling. Larger budgets are ceilings, not an instruction to burn CPU; eliminating prefix decode substantially reduces CPU work per useful frame. The remaining plateau is real and is not hidden by modifying interval. This test does not separately quantify storage, native-image processing, memory bandwidth and dependency overhead, so none is claimed as the sole proven remaining bottleneck.

## Implemented work

- Persistent PyAV/libav decode; bounded exact ordinal/keyframe state and conservative FFmpeg fallback. Forward sequential work avoids repeated process startup and repeated prefix decode when retained codec state is available. Under low memory, some contexts are evicted and must reopen; retained keyframe anchors reduce replay. Unknown VFR first jumps can still require one exact prefix scan.
- Every complete source-page batch is published immediately after JPEG persistence; a composite waits only for its own exact inputs, not all frames in a longer extraction run. Ready/pending batches avoid repeat disk probes; stale or missing inputs invalidate readiness and retry.
- Persistent worker pool; live stage reservations, weighted native decoder CPU permits, independent total budget and byte admission. Idle permits can be borrowed without abandoning memory accounting. No productive pool drain/rebuild during tuning.
- Bounded per-video decoder state, small preview/pixel accelerators, lazy original-frame descriptors and canvas admission checks. Original-resolution JPEG and final PNG remain the authoritative disk cache; outer-window cleanup remains active. Large layouts do not retain or deepcopy all original pixels. No unbounded memory-only video mode is added.
- Independent raw-directory locks; slow JPEG rename never holds the GUI state lock. Generation/window checks before and after atomic publication reject obsolete results. Stitching reads extracted images, never video files.
- Measured producer-concurrency search in multi-video Performance/Maximum, within the selected budget. Valid new composite production, not draining old cache stock, is the objective. Trials roll back when useful supply slows and buffers drain. It does not write interval or alter cache radii. Interval retains the existing measured-supply/inventory/ETA prediction and manual floor.

## 100 independent 4K decoder contexts

Synthetic 6-frame H.264 inputs with separate paths/codec contexts; hard links share input storage/OS file-cache content. 10x10 layout, preview 192x108, cache_frames=1, multiplier=3. One warmup and two measured pages. This is a short bounded-memory smoke test, not evidence of long-video sustained FPS or real 100-file storage bandwidth. Peak RSS includes first-frame/warmup playback but excludes the metadata-probing phase.

| Mode | Memory allowance GiB | First frame s | Whole-playback peak RSS GiB | Continuous |
|---|---:|---:|---:|---|
| Eco | 1.26 | 10.94 | 1.14 | True |
| Maximum | 6.30 | 8.36 | 4.96 | True |

Working-set admission and cache limits are software estimates, not a hard operating-system RSS cap. Native codec/allocator/wx overhead remains. A mode downgrade shrinks retained bytes and background-reclaims idle resources without deleting current valid disk caches.

## Regression and reproduction

193 regression tests passed on the final Windows source. Coverage includes exact CFR/VFR frame order, reverse/skip/rotation, fallback vframes limit, cache recovery/cleanup, weighted CPU/byte admission, quota changes without pool replacement, single-tile 100x4K loading, canvas rejection before allocation, and GUI state-lock independence during real blocked JPEG rename. Linux/macOS native execution was not available; implementation uses cross-platform Python/PyAV/Pillow interfaces and retains platform-specific existing resource cleanup paths.

```powershell
python -m unittest test_admission_optimizer test_video_pipeline test_playback_pacer test_resource_monitor test_buffer_policy test_thread_optimizer test_video_interval test_video_cache test_video_gui_async test_performance_cache test_memory_reclaim test_video_tools -q
python tools/benchmark_video_playback.py --manifest benchmarks/video_pipeline_final_verified/manifest.json --output benchmarks/recheck --power-matrix --duration 30 --timeout 120
python tools/benchmark_video_stress.py --output benchmarks/recheck_4k_eco --reference benchmarks/video_pipeline_final_verified/manifest.json --streams 100 --mode 1
python tools/benchmark_video_stress.py --output benchmarks/recheck_4k_maximum --reference benchmarks/video_pipeline_final_verified/manifest.json --streams 100 --mode 4
```

Environment: Python 3.9.23; PyAV 15.1.0; FFmpeg 8.1.1. PyAV is declared in requirements for Python >=3.9; if unavailable/unsupported, the original FFmpeg path remains functional but the native-decoder speed benefit does not apply. Generated frame folders and synthetic fixtures can be removed; retained JSON results contain all measurements and source hashes. Test/benchmark scripts are not imported by normal playback.
