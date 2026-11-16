# Validated playback optimization ? 2026-11-12

Application changes: native strided rgb24 plane -> independently owned Pillow RGB image, avoiding PyAV Python row copies/intermediate byte buffers; O(1) priority/raw LRU accounting; total-concurrency trial context includes stage reservations. Disk JPEG/PNG persistence, memory caps, dual windows, cleanup and manual interval floor are retained. No forced slowdown or quality reduction. RGBX zero-copy was rejected after native heap errors during format stress and is NOT used.

208 regression tests passed. Coverage includes multiple color formats, odd strides, RGB/JPEG byte equivalence, buffer independence/lifetime, fallback and allocation errors, rotation/seek/reverse/skip, concurrent cache limits, live mode changes and GUI responsiveness. Windows executed; Linux/macOS native execution was unavailable.

## Controlled comparison

Same 24 videos; 4x6 layout, 320x180 previews, cache_frames=2, multiplier=3, manual floor 1ms. Each run warms 20 deliveries and measures exactly 150 deliveries (IDs 51..200). Two counterbalanced repeats. Baseline flag restores pre-change conversion, pixel-cache implementation and admission-context behavior in the same frozen source; it is a behavioral ablation, not a complete historical checkout. FPS counts hidden wx delivery, not physical monitor refresh. Final PNG bytes matched across all eight runs.

| Mode | Baseline FPS | Optimized FPS | Gain | CPU before | CPU after |
|---|---:|---:|---:|---:|---:|
| Performance | 4.710 | 5.682 | +20.6% | 26.04% | 30.86% |
| Maximum | 5.032 | 5.791 | +15.1% | 24.71% | 29.50% |

Maximum is only about 1.9% faster than Performance after this change; linear scaling with the extra budget is NOT achieved. Two repeats do not establish statistical significance. Results apply to the recorded inputs/settings/source hashes.

## Bounded-memory and layout validation

100 independent-path 4K H.264 decoder contexts, 10x10 layout, preview 192x108, radius1 multiplier3: short memory smoke test (one warmup, two measured pages), NOT sustained long-video FPS.

| Mode | Playback peak RSS GiB | First frame s |
|---|---:|---:|
| Eco | 1.061 | 8.547 |
| Maximum | 4.531 | 4.547 |

Titles/magnifier enabled with 3x1 unit layout and cache10/multiplier2: 30 identical deliveries and identical final PNG bytes. This flag-only test has no selected magnifier region. Independent unit tests cover actual RGB crop/resize semantics.

An additional real selected-region test exposed an existing initialization defect: ImgManager.crop_points_process accesses title_max_size before it exists (utils_img.py:2160). Both the baseline-behavior trial and optimized trial failed before first image; this is NOT counted as a passed compatibility test. That rendering code is unchanged in this optimization. The issue is recorded for separate follow-up; no rushed change was made when the user requested stopping before the usage limit.

## Reproduction

```powershell
python -m unittest test_video_conversion test_admission_optimizer test_video_pipeline test_playback_pacer test_resource_monitor test_buffer_policy test_thread_optimizer test_video_interval test_video_cache test_video_gui_async test_performance_cache test_memory_reclaim test_video_tools -q
python benchmarks/video_playback_optimized_final_20261112/run.py
```

Test frame folders were removed. JSON measurements, source hashes, baseline cache implementation and scripts are retained. Restart the application to load the changes.
