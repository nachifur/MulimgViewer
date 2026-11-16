# Custom kernel interface follow-up (2026-11-14)

CPU plugins can now declare API v2, processing_mode=image and implement process_image(image, *, context). Each image independently acquires the shared CPU/RAM permit before loading pixels; full-resolution PNG results remain disk-backed. All four shipped instances and the Add template were converted, and their obsolete saving loops/imports removed.

GPU/vectorized plugins can instead implement process_batch(images, *, context), with optional setup() and teardown(context). A session shares one successful initialization; device locks/model eviction and legacy main(images, path, names) remain supported. The image task scheduler reevaluates priorities against the current playback position; shared atomic reservations allow idle decoder CPU lanes to serve downstream computation without a separate duplicate budget.

Final diagnostic: 24 videos, same copied config as report.md, 1x24 sources, unit 3x1, scale .1, four algorithm panes (original plus three algorithms), cache_frames=4, cache_multiplier=2, Maximum, manual floor .001s, 45s measurement after three warm-up frames, probe enabled. Original inputs/processed PNG pixels remain full-resolution.

```json
{
  "fps": 0.46650079971562286,
  "cpu_percent": 30.634625365524382,
  "rss_peak_mib": 1710.08203125,
  "first_frame_seconds": 9.0,
  "p50_gap_ms": 1046.9999999913853,
  "p95_gap_ms": 8812.000000005355,
  "max_gap_ms": 9641.00000000326,
  "continuous": true,
  "latest_status": "",
  "production_fps": 0.4887690807256679
}
```

CPU utilization increased in these diagnostics, but long-tail gaps remain and steady-state linear scaling has not been demonstrated. Earlier runs differed in duration/profiling and are not a controlled percentage-speedup baseline. kernel_v2 and kernel_budget are intermediate diagnostic versions; kernel_priority records the final production version. Test caches were removed; configs, JSON/log/probe artifacts remain. No user configuration was changed by the benchmarks.

Implementation and user examples: docs/custom-functions.md (API v2 section). Pure Python CPU-bound loops still encounter the GIL; no automatic process backend was added. External native libraries/ML runtimes must cooperate with their declared thread and memory policy.

Validation: all 413 regression tests passed in 166.736 seconds. Both generated GUI files match their FBP sources, the Add-generated template compiles, and git diff --check passed. Regression log messages for cache-root replacement refusal and test model failure are expected injected failure/safety cases. No real GPU model was benchmarked; its initialization, batch inputs, context reuse and release hooks were tested with a stateful simulated plugin.
