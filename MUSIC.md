# Dancing to music

Make Brachiomimus move along with whatever's playing on your computer, via
`dance.py`. Two things drive the motion, computed live from the audio:

- **Loudness** — a smoothed volume envelope sets how big/extended the raise
  and side-to-side sway are right now (quiet → near rest, loud → fully
  raised and swinging wide).
- **Beat** — an onset detector watches just the bass band (~20-150Hz, kick
  drum/bassline territory) and flags a hit whenever that spikes above the
  recent local average. It deliberately ignores hi-hats, cymbals, and vocals
  — those spike far more often than the actual tempo and made everything
  feel chaotic/too-fast, especially on slower songs. Each hit: flips which
  way the next sway swings, gives the wrist a twist, and pops the gripper
  open before it eases back shut.

Assumes the follower is already calibrated — see the
[Calibration](README.md#calibration) section in the getting-started doc.

## Setup

```bash
pip install sounddevice numpy soundfile soundcard
```

(`lerobot` should already be installed from the getting-started steps.)
`soundcard` is only needed for `--audio-source loopback` — plain
`sounddevice`/PortAudio has no WASAPI loopback support, so loopback capture
goes through `soundcard` instead, which talks to WASAPI directly.

## Audio source

`--audio-source` picks where the audio comes from — pick whichever gives the
cleanest signal for your setup:

| Source | What it does | When to use it |
|---|---|---|
| `mic` (default) | Records ambient sound through the microphone | Simplest — works with anything audible, including a phone or another speaker |
| `loopback` | Captures the computer's own audio output digitally (WASAPI), no mic involved | Cleanest signal — use this if `mic` picks up USB/electrical noise from the arm sharing the same machine, or room noise |
| `file` | Plays a WAV file through the speakers while analyzing the exact same samples | For testing with a known track, or if you'd rather not deal with live capture at all |

```bash
# Linux
python dance.py --port /dev/ttyACM0 --audio-source mic
python dance.py --port /dev/ttyACM0 --audio-source loopback
python dance.py --port /dev/ttyACM0 --audio-source file --file song.wav

# Windows
python dance.py --port COM4 --audio-source mic
python dance.py --port COM4 --audio-source loopback
python dance.py --port COM4 --audio-source file --file song.wav
```

If you're running everything from the same laptop that powers Brachiomimus
and the mic picks up buzz/whine from the USB connection, switch to
`loopback` (no mic needed) or `file` (fully offline signal) — that's exactly
the tradeoff these three modes exist for.

## Dry run (no arm required)

```bash
python dance.py --dry-run --audio-source file --file song.wav
```

Runs the full audio → loudness/beat → pose pipeline and prints the computed
pose every tick (plus a `beat` line each time the beat detector fires)
instead of sending anything to the arm. Good for checking that the beat
detector is actually tracking the song's rhythm, and for tuning
`BEAT_PULSE_DEG` / `MAX_STEP_DEG` in `dance.py` before connecting to hardware.

## Windows notes

- `--audio-source loopback` uses `soundcard` to capture the *default* Windows
  playback device via WASAPI. If nothing seems to register, check that your
  music player is actually outputting to that device (Windows Sound
  settings) — it isn't tied to any particular player, just whatever Windows
  currently treats as the default output.
- Same serial port notes as the rest of the docs apply — find your port with
  `[System.IO.Ports.SerialPort]::GetPortNames()` (see
  [README.md](README.md#finding-your-serial-port)).

## Stopping

Ctrl+C ramps the arm to a raised, tucked pose (the same one `wave.py` uses
for `WAVE_READY_POSE`) before disabling torque and exiting — not the flat
rest pose, which would let it sag onto the table once torque cuts.
