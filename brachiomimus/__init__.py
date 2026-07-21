"""brachiomimus — shared core for the SO-101 arm experiments.

This package holds the pieces reused across the runnable behaviors in
`demos/` and the tuning tools in `tools/`:

  - hardware : motor definitions, canonical poses, calibration loading
  - motion   : pose-interpolation / slew-limiting helpers
  - vision   : OpenCV perception primitives (face + colored-blob detection)
  - audio    : real-time audio sources for the music demo
  - analysis : audio DSP (loudness envelope, beat detection, BPM)
  - config   : env/.env-sourced user settings

See the repository README for the "spectrum of experiments" these support.
"""
