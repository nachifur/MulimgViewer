# Power tooltip diagnostics (2026-11-14)

Input: 24 videos in D:/ncfey/Desktop/test_img/test_video. Config: copied config.json, row_col=1,6; unit=1,1; algorithm grid=2,1; show_unit=false; first two algorithms visible; scale=.1; cache_frames=4; multiplier=2. Maximum, 22 CPU slots, ~6.30 GiB total mode memory budget. Native decode and full-resolution lossless algorithm PNGs remain enabled. Each run measures 20 seconds after three warm-up frames, probe enabled, hidden wx display completion.

The first manual_1s/manual_1ms runs are invalid as an interval-floor comparison: the benchmark had not marked ChangeValue as a user edit, and recorded manual_interval=None. The benchmark now marks the edit and asserts the requested floor was accepted. Corrected runs:

```json
[
  {
    "fps": 0.39968025579529864,
    "cpu_percent": 23.535858812945808,
    "rss_peak_mib": 1756.27734375,
    "continuous": true,
    "latest_status": "",
    "case": "verified_1s",
    "manual_interval": 1.0,
    "production_fps": 0.7496841205957869,
    "decoder": {
      "decode_now": 0,
      "decode_average": 1.1128999999928055,
      "decode_peak": 22,
      "decode_completed": 72,
      "decode_queued": 0,
      "admitted": 22
    }
  },
  {
    "fps": 0.55,
    "cpu_percent": 24.169034090909093,
    "rss_peak_mib": 1898.64453125,
    "continuous": true,
    "latest_status": "",
    "case": "verified_1ms",
    "manual_interval": 0.001,
    "production_fps": 0.5500535477128697,
    "decoder": {
      "decode_now": 0,
      "decode_average": 1.1919999999983701,
      "decode_peak": 22,
      "decode_completed": 24,
      "decode_queued": 0,
      "admitted": 22
    }
  }
]
```

The instantaneous decoder occupancy is zero at both corrected endpoints, despite recent peaks of 22 and finished extraction tasks. Short bursts were missed by the old instantaneous-only tooltip. The new history records scheduler transitions, time-weighted occupancy, peak and completed-task counts; it does not count OS threads or only codec-internal execution. High-resolution timing/explicit peak events handle sub-tick tasks; power changes reset this history along with CPU/RSS monitoring. These final telemetry refinements were made after the diagnostic runs; producer scheduling was not changed by those refinements.

CPU averages use whole-machine capacity; downstream activity counts actual shared WorkBudget permits rather than parent page coordinators. Base reservations can lend idle capacity. No full processed-cache scan now runs on tooltip refresh. Supply and ready-ahead buffer plus the actual interval/manual floor distinguish consumption throttling from a producer bottleneck.

In the 1ms run actual display (0.55 FPS) matches measured final output supply (~0.55 FPS); CPU averages ~24.2%. Probe PNG-save calls consume ~55 aggregate thread-CPU seconds, while extraction consumes ~8.2, over the 20-second measured window. Nested timers overlap and must not be added. This implicates substantial downstream encoding/file-path work, not absent decode workers; it does not independently prove physical-disk saturation or establish a steady-state/linear scaling result. Long-tail stalls remain. The two short runs vary with cache/phase alignment; do not infer a universal percentage improvement from changing the interval alone.

User configuration was not modified. Own per-run frame caches were removed; JSON/logs/config/manifest remain. Telemetry and interval/resource regressions are recorded in the test log in the system temporary directory.
Validation: 100 targeted resource-monitor, decoder admission/history, custom-pipeline, interval, optimizer and live wx tooltip tests passed in 9.403 seconds. git diff --check passed.
