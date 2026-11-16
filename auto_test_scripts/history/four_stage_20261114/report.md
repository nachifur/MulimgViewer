# Four-stage scheduler diagnostic (2026-11-14)

Input: 24 videos from D:/ncfey/Desktop/test_img/test_video. Configuration copied from userdef_config.json: source layout 1x6, per-source layout 1x1, unit layout 3x1, scale .1, automatic resolution, show_all_func=true, algorithm canvas 2x1, show_unit=false, cache_frames=4, multiplier=2. Only the first two visible CPU algorithms execute. Maximum, 22 logical CPU slots, ~6.30 GiB policy RAM budget, manual interval floor .001s.

Each run uses a fresh disk cache, 3 warm-up presentations and 20 measured seconds, probe enabled. These are short diagnostic runs, not a controlled multi-repeat steady-state claim. Input videos are 24; the configured source layout remains 1x6. Full-resolution algorithm processing and lossless disk PNGs are retained.

| Version | FPS | CPU (whole machine) | Peak RSS MiB | P95 switch gap ms | First frame s |
|---|---:|---:|---:|---:|---:|
| before | 0.549 | 25.84% | 1875.0 | 6539.0 | 7.891 |
| after | 0.648 | 26.55% | 1729.7 | 2512.8 | 2.766 |
| final | 0.648 | 16.50% | 1706.1 | 4300.2 | 4.984 |
| release | 0.649 | 17.35% | 1699.0 | 3143.6 | 5.438 |

The initial revision and two follow-ups all produced ~0.65 FPS versus ~0.55 before. The release diagnostic has ~17.35% CPU, so this work does NOT establish higher CPU utilization or fully saturated hardware. Metadata/open times and CPU samples varied across runs; cache/phase alignment and host variation remain substantial. Long-tail stalls persist. Do not present the single-run FPS ratio as a universal or linear speedup.

Implementation:
- Integer minimax solver uses per-final-page work and CPU/RAM/concurrency limits. Work units include native decoder slots and per-image/per-algorithm normalization. Low budgets time-share; idle targets lend capacity.
- Real downstream children hold atomic shared reservations. Metadata-only coordinators have a bounded separate count, rather than duplicate CPU/RAM charges. Downgrades preserve shared callbacks and wait for running work safely.
- Memory-blocked large waiters do not block smaller fitting jobs. A serial algorithm does not occupy idle workers waiting for its own lock.
- Compose's permit now extends through PNG save/publication. This fixes missing work in allocation statistics and prevents final encoders running outside the shared admission budget.
- Tooltip second line is actual Decode/Process/Stitch/Compose occupancy, sampled consistently under budget then executor locks; it remains a four-line tooltip. Actual counts are occupied task/native slots, not OS thread counts or fixed reservations.
- Input/layout/algorithm changes reset the work profile. Critical directional buffers can rebalance promptly rather than waiting for a full cache. Single-slot reuse omits Compose; CPU/GPU concurrency and ordered-plugin safeguards remain.

The release run recorded target Decode=4, Process=16, Stitch=1, Compose=1; actual ending Process=22 used borrowed idle lanes. This is one observed target, not a fixed universal split. Subsequent mode-switch callback and input-profile guards were covered by targeted tests; the fixed-mode/current-input benchmark path is unchanged by those guards. Individual JSON files retain exact source hashes.

Validation: full regression ran 447 tests in 269.407s: OK with 10 skips (optional removed GPU example / unavailable symlink capability). Subsequent critical-feedback, mode-switch and input-profile checks passed 69 targeted tests in 11.120s. The integer solver is compared with exhaustive search. Live wx tests cover image/video output, final PNG admission, reverse playback, budget downgrade, and tooltip display. Both generated GUIs match FBP; git diff --check passed. Test frame caches were removed; configs, manifests, JSON and logs remain.

User configurations and input videos were not modified. No real GPU model was benchmarked. See docs/four-stage-scheduling.md for the model, constraints and limits.

## Longer current-version check

A final 60-second measurement (same copied config, 3 warm-up frames, Maximum,
manual floor .001s, probe enabled) checks whether short playback samples merely
consume accumulated caches. It runs the final input-profile, critical-feedback,
and mode-switch guards. There is no matching 60-second historical baseline.

```json
{
  "fps": 0.5828767465483381,
  "cpu_percent": 16.888995665510794,
  "rss_peak_mib": 1806.53515625,
  "p95_gap_ms": 10639.500000007682,
  "max_gap_ms": 15858.99999999674,
  "continuous": true,
  "latest_status": "",
  "duration": 60.04700000002049,
  "production_fps": 0.5829364284357436,
  "generated_pages": 35,
  "displayed_pages": 35,
  "target": {
    "decode": 3,
    "process": 17,
    "stitch": 1,
    "compose": 1
  }
}
```

The longer run still has substantial tail stalls and low CPU utilization. The
four-stage model/admission changes and actual-stage tooltip are implemented,
but hardware saturation, uniformly smooth playback and linear scaling have
NOT been achieved. The earlier ~0.65 FPS figures are short diagnostics, not a
sustainable-rate guarantee. PNG/file-path work and Python/native concurrency
constraints still require care; thread allocation alone cannot ensure 100% CPU.

The last targeted check passed 69 tests (11.120s), including critical-buffer
rebalancing, live power switches retaining atomic callbacks, input-model reset,
full compose publication admission, and per-algorithm queue limits.
