# Tiny reference media

All pictures are generated locally from integer arithmetic in
`support/fixture_recipe.py`; no downloaded or private user content is included.
All these assets may be redistributed under the repository license.

- `images/source_001`, `images/source_002`: 3 lossless PNG frames per source.
- `videos`: 64 × 48, 4 FPS, 8 and 5 frames respectively. Lossless H.264 RGB
  in compact MP4 containers, with B frames and keyframe spacing 4.
- `lists`: relative-path image/video File Lists; work from any checkout path.
- `special/alpha.png`: half-transparent RGBA input.
- `expected`: independently assembled pixel-exact reference mosaics.
- `manifest.json`: dimensions, frame counts and RGB SHA-256 for decoded frames.

The complete media set is approximately 36 KB. Normal tests **read** it; they
never regenerate expectations from the implementation under test. Rotation,
EXIF editing and moving tests use private copies, never these reference files.
Tests verify both the manifest and the independent frame recipe. PNG checks
compare decoded pixels, not compressed bytes; JPG checks allow compression,
and PDF tests check containers, embedding and titles rather than unstable bytes.

Only when intentionally changing the fixtures, run from the application Python:

```sh
python auto_test_scripts/generate_assets.py
```

This command requires FFmpeg with `libx264rgb`; review changes to the recipe,
manifest, inputs and expected images together. A codec version can change MP4
bytes without changing the decoded RGB reference pixels.
