# Why extra Maximum budget did not scale linearly

2026-11-12; Windows, Python 3.9.23, PyAV 15.1.0, Pillow 10.3.0, 22 logical CPUs. Application source was unchanged throughout this investigation; source_snapshot.json hashes every top-level src module. Only optional benchmark/probe tools and isolated prototypes were changed.

Inputs/settings match the original four-mode benchmark: the same 24 H.264 files, 4x6 layout, preview 320x180, cache_frames=2, multiplier=3, no titles/magnifier, manual floor 1 ms. Each run warms 20 deliveries and measures 30 seconds; all measured frame IDs precede the end of every source. FPS counts hidden wx composite delivery, not physical display refresh. This does not reproduce all options in the user configuration with cache_frames=10 and magnifier enabled.

## 1. Removing adaptive limits did not restore linear scaling

| Case | Mode | FPS | App CPU % | Mean active permits | Mean CPU cap | Peak active memory / admission budget |
|---|---|---:|---:|---:|---:|---:|
| adaptive | Performance | 4.398 | 26.27 | 10.23 | 11.88 | 32.2% |
| adaptive | Maximum | 4.790 | 26.37 | 11.80 | 16.01 | 27.2% |
| fixed_admission | Maximum | 4.393 | 23.70 | 13.52 | 22.00 | 27.2% |
| fixed_admission | Performance | 4.857 | 26.25 | 12.83 | 16.00 | 32.2% |
| fixed_plan_r1 | Performance | 4.898 | 26.36 | 13.03 | 16.00 | 32.2% |
| fixed_plan_r1 | Maximum | 4.854 | 23.52 | 14.12 | 22.00 | 27.2% |
| fixed_plan_r2 | Maximum | 4.800 | 22.70 | 13.12 | 22.00 | 27.2% |
| fixed_plan_r2 | Performance | 5.225 | 26.26 | 12.82 | 16.00 | 32.2% |

Fixed-admission disables only the total-concurrency search. Fixed-plan also disables stage-allocation changes and reserves extraction/stitch permits 15/1 or 21/1. Existing safe borrowing remains enabled, so these are reservations, not hard per-stage activity ceilings. The two fixed-plan pairs are counterbalanced. Mean fixed-plan FPS: Performance 5.061; Maximum 4.827 (-4.6%). These limited repeats do not establish statistical significance, but they directly reject the claim that automatic total-cap reduction is the only cause of the plateau.

## 2. Primary confirmed serial hotspot: VideoFrame.to_image

The actual call is src/mulimgviewer/src/video_decoder.py:116. py-spy 0.4.3 sampled only the owned, warmed Maximum benchmark process, fixed 21/1 reservations, for 25 seconds at 100 Hz with --gil. Raw stacks and sampler log are retained. There were 2038 GIL-held samples, zero sampler errors; 841 (41.3% of GIL-held samples) had that call as the leaf. This percentage is NOT CPU usage or an exact percentage of all wall time. The nominal GIL-held capture frequency was 81.5% of 2500 opportunities. The benchmark sampler itself accounts for 132 samples and must not be treated as application work.

PyAV 15.1.0 to_image reformats to rgb24, allocates a bytearray, copies each row into it, converts it to bytes, and calls Pillow Image.frombytes. Those Python-buffer operations do not become independent multi-core work merely by increasing the number of Python worker threads. Source: https://github.com/PyAV-Org/PyAV/blob/v15.1.0/av/video/frame.py#L372-L398 . The real-input stack sample and poor isolated scaling support identifying this path as a major bottleneck, not necessarily the sole bottleneck.

## 3. Independent image-operation scaling

These tests ran after GUI runs, using one real decoded frame at index 100 and one real generated composite. Each worker owns its image/frame. Each cell reports operations/second; not composite FPS. Files are on the same workspace volume. Small standalone operations, short timings and fixed warm inputs are not a physical storage benchmark.

| Operation | 1 worker | 4 | 8 | 16 | 22 |
|---|---:|---:|---:|---:|---:|
| to_image | 222.6 | 336.5 | 332.5 | 325.8 | 324.0 |
| jpeg_memory | 250.5 | 250.0 | 269.2 | 265.8 | 276.3 |
| jpeg_file | 186.2 | 635.2 | 931.3 | 963.4 | 930.1 |
| resize | 118.4 | 442.2 | 848.9 | 1152.0 | 1261.4 |
| png_memory | 22.8 | 82.1 | 141.6 | 203.1 | 199.1 |
| png_file | 19.6 | 69.6 | 125.4 | 164.1 | 177.0 |

JPEG to a real file and PNG encoding scale substantially. JPEG into BytesIO plateaus near one CPU core, but production raw JPEGs use real files; do not substitute the BytesIO result for the real-file path. Pillow 10.3.0 has a separate native encode_to_file loop entering an ImagingSection: https://github.com/python-pillow/Pillow/blob/10.3.0/src/encode.c#L158-L199 . Therefore blanket claims that all JPEG/PNG encoding is GIL-serialized, or that the physical disk is proven saturated, are unsupported.

## 4. Memory and runnable-task supply are additional limits

Performance/Maximum both already reach the optional pixel-cache hard cap of 256 MiB; both retain the 24 decoder contexts (24 opens in these runs). The outer temporal window remains 13 composite pages. Thus +50% working-memory allowance does not automatically create more useful cached previews/pages. Maximum peak estimated active-byte admission utilization was about 27%; this is not process RSS, but confirms that this admission gate was not full. More allowance alone cannot fix a serial conversion path.

Detailed mode 3: 50.7% of samples were below the CPU cap; in all those samples there were no queued extraction-video keys. 67.6% of those under-cap samples also had composites waiting for extraction. This shows periods of insufficient runnable work/dependencies inside the bounded lookahead, rather than a full CPU/memory admission gate. It does not prove one specific dependency policy is the sole bottleneck.
Detailed mode 4: 61.8% of samples were below the CPU cap; in all those samples there were no queued extraction-video keys. 50.0% of those under-cap samples also had composites waiting for extraction. This shows periods of insufficient runnable work/dependencies inside the bounded lookahead, rather than a full CPU/memory admission gate. It does not prove one specific dependency policy is the sole bottleneck.

PixelCache._trim and its priority-byte summation also appear in GIL samples. They scan cache entries and are secondary candidates for O(1) priority/LRU bookkeeping. Background metadata/cleanup and instrumentation have costs too; their isolated contributions have not been ablated.

## 5. Isolated copy-reduction prototype, not integrated

Prototype: reformat to rgb0 and map an RGBX Pillow buffer, explicitly retaining the owning AV frame. On ONE representative frame, converted RGB pixels and quality-90 JPEG bytes were identical. The prototype has NOT passed application-level mode/lifetime/rotation/magnifier/crop/export/custom-function/100x4K compatibility testing. No application code was changed.

| Conversion | 1 worker ops/s | 22 workers ops/s |
|---|---:|---:|
| to_image | 215.5 | 325.2 |
| rgbx_buffer | 869.1 | 2695.9 |

At 22 workers the prototype conversion is about 8.3x faster than to_image in this isolated test. This is NOT an 8.3x whole-application FPS claim. It demonstrates a concrete direction to reduce copies and GIL-held work before adding more workers. Disk JPEG/PNG persistence and byte-based memory admission can remain.

Priority for a subsequent implementation: (1) safely remove the conversion copies with a conservative fallback and full image/lifetime compatibility tests; (2) replace scanning pixel-cache accounting with bounded O(1) bookkeeping; (3) coordinate total-cap and stage-allocation experiments so concurrent controller changes do not corrupt comparisons; (4) prioritize exact next-page/slow-source dependencies and evaluate native decoder parallelism under the same weighted CPU/byte budget. Do not silently expand the user outer window or retain all high-resolution frames in RAM.

## Reproduction

```powershell
python benchmarks/video_scaling_diagnosis_20261112/run.py
python benchmarks/video_scaling_diagnosis_20261112/microbench.py
python benchmarks/video_scaling_diagnosis_20261112/prototype_rgbx.py
```

run.py regenerates the per-run caches required by microbench.py. GIL capture additionally needs temporary py-spy 0.4.3 in inputs/profiler (removed after investigation) before running profile_gil.py. Generated video/frame/cache files are removed after measurements; JSON, source hashes, raw GIL stacks and scripts remain. Two invalid intermediate instrumentation trials were discarded; retained detailed trials require positive deliveries and zero native fallbacks.

## Subsequent integration outcome

The RGBX zero-copy candidate above was NOT integrated: later full-format regression exposed a native heap exception in that candidate path. The shipped optimization instead feeds the native strided rgb24 plane to Pillow's raw decoder, producing independently owned RGB pixels without PyAV's Python row loop/intermediate byte buffers. See `../video_playback_optimized_final_20261112/report.md` for the validated application-level comparison; the isolated 8.3x prototype figure is not an application FPS claim.