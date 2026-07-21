# Dancing to music

Make Brachiomimus move along with whatever's playing on your computer, via
`demos/dance.py`. Two things drive the motion, computed live from the audio:

- **Loudness** — a smoothed volume envelope sets how big all the motion is
  right now (quiet → gentle, loud → big raises, wide swings, full pincer).
- **Beat** — an onset detector watches just the bass band (~20-150Hz, kick
  drum/bassline territory). On each beat the arm flips to new held targets
  and then ramps smoothly toward them until the next beat:
  - the **gripper opens and closes** in time with the music (a pincer clench
    on every beat)
  - the **wrist twists** and the **shoulder sways** side to side at half-time
    (every other beat, in opposition), so the arm grooves rather than
    lurching on every beat — the pincer carries the beat, the body keeps time

  It only watches the bass band because hi-hats, cymbals, and vocals spike
  far more often than the real tempo — that was what made earlier versions
  feel chaotic/too-fast, especially on slower songs. A peak-relative
  threshold further favors the strongest low-end hits (kicks/downbeats) over
  weaker off-beat bass notes.

Assumes the follower is already calibrated — see the
[Calibration](../README.md#calibration) section in the getting-started doc.

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
python -m demos.dance --port /dev/ttyACM0 --audio-source mic
python -m demos.dance --port /dev/ttyACM0 --audio-source loopback
python -m demos.dance --port /dev/ttyACM0 --audio-source file --file song.wav

# Windows
python -m demos.dance --port COM4 --audio-source mic
python -m demos.dance --port COM4 --audio-source loopback
python -m demos.dance --port COM4 --audio-source file --file song.wav
```

If you're running everything from the same laptop that powers Brachiomimus
and the mic picks up buzz/whine from the USB connection, switch to
`loopback` (no mic needed) or `file` (fully offline signal) — that's exactly
the tradeoff these three modes exist for.

## Tuning the beat (no arm needed)

If the arm reacts to more than the actual beat (twitchy, too fast), tune the
detector with **monitor mode** — it listens and prints each detected beat
with a live BPM estimate, but doesn't touch the arm. It works with any
source, so you can tune against **whatever you're actually playing**,
including YouTube in a browser:

```bash
# play your song (YouTube, Spotify, anything), then in another window:
python -m demos.dance --monitor --audio-source loopback
```

Watch the printed BPM. If it reads roughly the song's real tempo and holds
steady, you're good. If it's too high / jumpy, raise the threshold until it
settles:

```bash
python -m demos.dance --monitor --audio-source loopback --sensitivity 2.5
```

`--sensitivity` defaults to `1.8`. Higher = only the strongest hits count
(fewer, cleaner beats); lower = more sensitive (catches quiet beats but also
more noise). Once the BPM looks right in monitor mode, run for real with the
same `--sensitivity` value plus your `--port`.

There's also `--dry-run`, which prints the full computed pose every tick
(not just beats) without moving the arm — more detail than you usually need,
but handy if you want to see the exact joint targets.

## Calmer motion

If it feels too wild, turn down `--intensity` (default `1.0`) — it scales the
sway and twist size (the pincer still fully opens/closes on the beat):

```bash
python -m demos.dance --port COM4 --audio-source loopback --intensity 0.5
```

## Making the pincer actually close

The gripper opens/closes between two angles **in degrees**. Your arm's
calibrated `0` isn't necessarily its closed position — on some builds `0` is
fully *open*, so the pincer never appears to close. Find your real values:

```bash
python -m demos.dance --port COM4 --read-gripper
```

This frees just the gripper (the rest of the arm holds still) and prints its
live angle. Squeeze it fully closed and note the number, open it fully and
note that one. Then save them once in **`.env`** (see below) so every run
uses them — or pass them ad-hoc:

```bash
python -m demos.dance --port COM4 --audio-source loopback \
    --gripper-closed -61.32 --gripper-open 61.2
```

(The two can be in either order / either sign — whatever your arm reads.)

## Settings & `.env`

Per-arm settings live in `brachiomimus/config.py` and are read from a `.env` file (and/or
real environment variables), so you don't retype your calibration every run.
The repo ships a committed template, `.env.example`; copy it to `.env` (which is
gitignored) and edit it to match your arm:

```ini
# .env  (copied from .env.example)
BRACHIOMIMUS_GRIPPER_CLOSED_DEG=-61.32
BRACHIOMIMUS_GRIPPER_OPEN_DEG=61.2
BRACHIOMIMUS_PORT=COM4
# BRACHIOMIMUS_SENSITIVITY=1.8
# BRACHIOMIMUS_INTENSITY=1.0
```

Precedence: a CLI flag beats a real environment variable, which beats `.env`,
which beats the built-in default. Because `.env` is gitignored, it's also where
your training secret (`WANDB_API_KEY`) lives — see
[training-act.md](training-act.md#authentication-keys-live-in-env). The
committed `.env.example` stays secret-free.

The remaining pose amounts (sway/twist degrees, ramp speeds) are constants
near the top of `demos/dance.py`, and the audio DSP lives in
`brachiomimus/analysis.py`; the `--monitor` and `--read-gripper` helpers live
in `tools/diagnostics.py`.

## Windows notes

- `--audio-source loopback` uses `soundcard` to capture the *default* Windows
  playback device via WASAPI. If nothing seems to register, check that your
  music player is actually outputting to that device (Windows Sound
  settings) — it isn't tied to any particular player, just whatever Windows
  currently treats as the default output.
- Same serial port notes as the rest of the docs apply — find your port with
  `[System.IO.Ports.SerialPort]::GetPortNames()` (see
  [README.md](../README.md#finding-your-serial-port)).

## Stopping

Ctrl+C ramps the arm to a raised, tucked pose (the shared `READY_POSE` from
`brachiomimus/hardware.py`, the same one `demos/wave.py` uses) before disabling
torque and exiting — not the flat
rest pose, which would let it sag onto the table once torque cuts.
