# Custom-algorithm playback optimization

Input: 24 videos from `D:/ncfey/Desktop/test_img/test_video`; copied user config in `config.json`.
Layout: 1x24 sources, unit 3x1, scale 0.1, automatic resolution, original plus Image Enhancement / Image Darkening / Gaussian Blur in a 4x1 algorithm grid. Cache frames 4, multiplier 2. Maximum mode, 22 logical CPUs; configured memory budget ~6.45 GiB. The benchmark overrides the manual interval to 0.001s and keeps both serial switches disabled, without editing user configuration.

| Measurement | Before | Verified |
|---|---:|---:|
| Actual bitmap presentations/s | 0.332 | 0.500 |
| Application + decoder CPU, normalized to all CPUs | 30.07% | 24.81% |
| Peak sampled RSS (MiB) | 3457.3 | 2927.4 |
| First frame (s) | 14.062 | 5.984 |
| P95 playback gap (ms) | 3583.2 | 2972.5 |

These are single short diagnostic runs, with cProfile/probe enabled and 3 warm-up frames: the first measured 12 seconds and the verified run 20 seconds. The sample sizes are small; absolute FPS and gains must not be treated as guaranteed steady-state GUI performance. Both runs presented continuous frame IDs. CPU is not forced higher: removing redundant work improves playback while lowering CPU and RAM here. The remaining full-resolution algorithms and PNG writes still impose throughput limits; linear scaling is not established.

## Confirmed bottlenecks and changes

- Custom children were capped by the stitch reservation even when decoder lanes could be borrowed. Child capacity now follows admitted parent lanes, deducting active decoder memory from the shared working budget.
- A same-algorithm lock waiter already occupied a CPU/RAM permit. It now waits before loading pixels or acquiring work permits; device/stateful protections remain. Bundled stateless Pillow algorithms explicitly permit safe concurrent calls.
- Every processed full-resolution PNG was decoded again just to resize it for display. Exact previews are retained in the existing byte-bounded pixel cache, while the durable full-resolution PNG remains on disk. No algorithm inputs are downscaled.
- One public-cache IO lock serialized unrelated algorithms. Locks now separate algorithm/layer trees. Canonical directory checks are reused only within one locked publication, and repeated input metadata is shared across algorithms in a batch.
- Stream writes avoid repeated Pillow filename resolution. Lossless PNG RLE encoding reduces compression work without changing pixels. Known bundled algorithms declare a 12-byte/input-pixel work estimate; unknown plugins retain the 16-byte default plus declared fixed working memory.

The initial mosaic profile spent 156.3 aggregate worker seconds for 76 mosaics; the later optimized diagnostic spent 29.9 for 71. These are overlapping, nested worker timings, not directly additive or an end-to-end speedup factor. Intermediate runs are retained to show that faster mosaics alone did not immediately raise presentation FPS.

## Reproduction

```powershell
python tools/benchmark_video_playback.py --manifest benchmarks/custom_pipeline_20261114/manifest.json --config benchmarks/custom_pipeline_20261114/config.json --output benchmarks/custom_pipeline_20261114/repeat/result.json --mode 4 --parallel --manual-interval .001 --duration 20 --timeout 180 --probe --profile-mosaic
```

FFmpeg/ffprobe must resolve through the installed environment. Result files record production source hashes and effective layout/cache settings; `summary.json` records current bundled plugin hashes. Raw test caches are disposable; measured JSON/logs/profiles are retained.

## Final supply-driven pacing follow-up

The final production version additionally removes the second smoothing layer, uses only directional output requests for throughput measurement, avoids applying parent queue/wait latency as a fresh custom-job duration, and detects an unfinished active production group's slowdown. The manual interval remains a hard floor. Already displayed reverse frames remain cached; unvisited historical algorithm pages are deferred during playback and filled on pause/direction change. Header metadata shares the pixel byte budget, avoiding repeated pinned-result header opens/existence checks.

An attempt to reserve multiple parent CPU lanes was rejected after it reduced throughput. Temporary incorrect callback placement caused two no-supply experiments; these are invalid and excluded. A Windows directory sharing failure in another experiment is also excluded; bounded background retry now handles transient sharing errors. Earlier intermediate numbers in this report are diagnostic history, not final speedup evidence.

Final test: 30 seconds, same copied config/24 input videos, Maximum, manual floor 0.001s, probe enabled, cProfile disabled. Native algorithms still process full-resolution inputs and write lossless full-resolution PNGs to disk.

- Produced 14 pages: 0.467 pages/s.
- Presented 13 pages: 0.433 FPS, continuous frame IDs, no pipeline error.
- Average process+decoder CPU: 23.79% of all logical CPUs; peak sampled RSS: 2798.7 MiB.
- Median switch gap: 1985.0 ms; P95: 3653.4 ms. Tail gaps remain; uniformly smooth or linear scaling is not established.
- Final prediction: {"reason": "measured-supply", "buffered": 1, "production_period": 2.2500717501960774, "measured_period": 2.2500717501960774, "next_eta": 2.2500717501960774}.

The displayed rate is close to measured supply in this short final run. The before diagnostics used cProfile and a different duration, so do not interpret these numbers as a controlled percentage speedup. Native algorithm work and filesystem traffic still constrain the supply rate. Real GPU models were not benchmarked; legacy/device/stateful protections have regression coverage.

Reproduce the final check with the earlier command, omitting `--profile-mosaic` and setting `--duration 30`. The copied configuration is not written back to the user's config. Failed/temporary frame caches are removed; JSON, logs and profiles are retained for inspection.

Validation: all 402 regression tests passed (529.238 s). Both generated GUI files match their FBP sources; git diff --check passed. The cleanup replacement refusal and test model failure lines in the regression log are expected injected safety/failure cases. Disposable benchmark frame caches were removed after measurements.
