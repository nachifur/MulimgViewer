# Repeated power-mode recovery investigation

Test date: 2026-11-12. Windows, 22 logical CPUs, the same 24 user videos. Same process retained across phases; each phase replays IDs 30 onward, warms 30 deliveries and measures exactly IDs 61..90. cache_frames=10, multiplier=2; 4x6 layout, preview 320x180; titles and magnifier disabled; manual floor 1 ms. This is a controlled recovery test, not an exact reproduction of all user GUI settings or a multi-hour leak test. FPS is completed composite wx delivery in a hidden window, not physical monitor refresh. Phase records are the authoritative metrics.

## Confirmed defects and fixes

1. Equal extraction/stitch reservations previously returned after updating tooltip metadata. A changed global CPU cap, byte budget and admission optimizer ceiling could remain at the previous policy. Regression reproduced expected CPU budget 12 versus actual 4. Equal reservations now reconfigure shared admission without replacing workers or canceling useful tasks.

2. Explicit pause/resume did not restart the concurrency observation interval. Elapsed pause time could be included in the next producer-rate comparison. Resume now abandons unfinished trials, restores the measured best limit and remeasures the incumbent. It preserves disk caches and pools. Cache-miss waits are deliberately NOT excluded: they are real supply delays. A deterministic test excludes a simulated 1000-second pause; a wx test checks actual resume restores the best cap without pool replacement.

## Seven alternating phases in one process (about 4.5 minutes)

This experiment includes fix 1 and predates fix 2; its independent source snapshot is retained. Each Maximum is separated by an Eco phase.

| Phase | Mode | FPS | RSS GiB | Private GiB | OS threads | Decoder objects | Queued extract/stitch |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | Maximum | 4.354 | 1.474 | 2.122 | 52 | 24 | [0, 0] |
| 2 | Eco | 0.723 | 0.686 | 1.331 | 52 | 24 | [475, 0] |
| 3 | Maximum | 3.840 | 1.559 | 2.202 | 52 | 24 | [0, 0] |
| 4 | Eco | 0.751 | 0.616 | 1.261 | 50 | 24 | [475, 0] |
| 5 | Maximum | 4.788 | 1.536 | 2.181 | 50 | 24 | [0, 0] |
| 6 | Eco | 0.690 | 0.650 | 1.296 | 50 | 24 | [475, 0] |
| 7 | Maximum | 4.683 | 1.786 | 2.437 | 50 | 24 | [8, 1] |

Maximum FPS does not decline monotonically. OS threads and decoder-object counts do not accumulate. Eco queue counts repeat rather than growing each cycle, and reduce again in Maximum. Memory fluctuates: Maximum endpoint RSS ranges about 1.47..1.79 GiB. Endpoints are sampled while production is active and have differing active-job counts; native allocator retention, live buffers and bounded caches cannot be distinguished from leaks using RSS alone. This short experiment does NOT exclude slow native/Python leaks over hours.

## Final-source repeated Maximum replays

All explicit playback starts invoke the new observation reset. The three replays are in one fresh process, with identical measured IDs and no mode-budget change between starts. There is no timed long pause in this real-input run; long-pause exclusion is verified by the deterministic unit test.

| Replay | FPS | RSS GiB | Private GiB | OS threads | Decoder objects |
|---|---:|---:|---:|---:|---:|
| 1 | 4.507 | 1.526 | 2.170 | 52 | 24 |
| 2 | 4.729 | 1.767 | 2.415 | 54 | 24 |
| 3 | 3.459 | 1.734 | 2.379 | 51 | 24 |

The final-source replay did show a decrease from 4.729 to 3.459 FPS while endpoint RSS decreased from about 1.77 to 1.73 GiB. This is evidence of real throughput variability, not proof of a leak. Admission probes and extraction/stitch quota changes are present in the logs, but no controlled ablation isolates their contribution; they must not be asserted as the sole cause. The two confirmed state bugs are fixed, but all long-running performance variation has NOT been resolved by this investigation.

196 regression tests passed on the final source. No persistent decoding cache is cleared by these fixes. Raw JPEG/final PNG remain disk backed, byte caps and outer-window cleanup remain in effect. Initial ready inventory, decoder rewarming after a downgrade and adaptive concurrency trials can still produce transient FPS differences; none alone establishes a memory leak.

## Reproduction

```powershell
python tools/benchmark_video_playback.py --manifest benchmarks/video_mode_recovery_20261112/manifest.json --output benchmarks/recovery_recheck/mode_sequence/result.json --sequence 4,1,4,1,4,1,4 --duration 0 --timeout 600
python tools/benchmark_video_playback.py --manifest benchmarks/video_mode_recovery_20261112/manifest.json --output benchmarks/recovery_recheck/mode_resume/result.json --sequence 4,4,4 --duration 0 --timeout 180
```

For an hours-long investigation, collect stable measurements at equivalent frame ranges and queue/active-job states, including RSS/private bytes, decoder contexts, futures/queue depth and actual producer/delivery rate. Consistent private-memory/object growth after equivalent work drains is stronger evidence than an isolated RSS rise. Synthetic or short replay tests cannot prove absence of all leaks.
