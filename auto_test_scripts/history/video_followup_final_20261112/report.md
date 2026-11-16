# Follow-up: selected magnifier repair and cache-maintenance overhead

2026-11-12. Final production changes are restricted to main.py and utils_img.py. The RGB allocation experiment was reverted; the previously validated owned-RGB conversion is retained.

## Kept changes

- ImgManager initializes title_max_size before the first page. Crop processing consults title offsets only when the stored box requires them. Video render-state publication includes measured title geometry, and private snapshots preserve it for subsequent title-relative crops.
- Cache cleanup bypasses repeated realpath/stat of lexically known active directories. Unknown retirement candidates still undergo resolved-root and reserved-alias checks before any rename/delete. Raw-frame and composite outer-window cleanup remain active.

## Validation

211 regression tests passed on final source, including a real wx selected region before first paint, measured title geometry transfer/snapshot independence, title-relative crop offsets, active-directory zero-realpath checks, obsolete directory retirement and simulated external alias preservation. Existing RGB/JPEG/rotation/seek/ownership, cache/memory and GUI regressions pass. Windows executed; native Linux/macOS runs were unavailable.

24 real videos, titles and magnifier enabled, an actual selected region, 3x1 units, cache_frames=10 and multiplier=2: both conversion/cleanup paths rendered30 continuous deliveries (IDs41..70), output [1930, 822], with identical final PNG bytes. Pixel acceleration was disabled ONLY for deterministic disk-fallback validation. Both paths include the title repair; the former AttributeError before first paint is now resolved. Obsolete prefetched jobs can encounter removed JPEGs during concurrent cleanup; foreground delivery completed without skipped IDs.

## Performance result, without overstating gain

Four Maximum runs, two counterbalanced pairs. Same24 inputs, 4x6, preview320x180, radius2 multiplier3, manual1ms, warm20 then exactly150 deliveries (IDs51..200). Previous behavior restores archived converter/cleanup methods; final source is otherwise identical. All final PNG hashes match.

| Pair | Previous FPS | Final FPS |
|---|---:|---:|
| 1 | 4.406 | 5.010 |
| 2 | 4.494 | 4.156 |

Mean 4.450 -> 4.583 FPS, but one pair improved and one regressed. This does NOT establish a stable FPS gain or linear budget scaling. Do not compare these absolute values directly to earlier5.79-FPS sessions; conditions vary. Reduced filesystem canonicalization is confirmed by regression, but its whole-player throughput benefit remains unproven.

## Rejected experiment

An attempted no-fill RGB allocation showed inconsistent Performance results and substantial Maximum regression; one earlier trial also timed out before the first image. Its cause was not established as a new deadlock. That allocation candidate is NOT shipped. Subsequent shorter cold-start probes passed15 times, but they are not proof that all long-running stalls are eliminated. Rejected measurements/source hashes are retained separately, and none are claimed as final performance.

## Reproduction

```powershell
python -m unittest test_video_conversion test_admission_optimizer test_video_pipeline test_playback_pacer test_resource_monitor test_buffer_policy test_thread_optimizer test_video_interval test_video_cache test_video_gui_async test_performance_cache test_memory_reclaim test_video_tools -q
python benchmarks/video_followup_final_20261112/run.py
```

Generated frame folders were removed; measurements, source hashes and previous-method archive remain. The run script compares only the two Maximum pairs. Disk-backed caches, memory limits, CPU quotas, manual interval floor and the prior RGB optimization remain. No artificial playback slowdown is added. Restart the application to load changes.
