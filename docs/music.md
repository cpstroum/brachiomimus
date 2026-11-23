# Dancing to music

`demos/dance.py` makes Brachiomimus move to whatever's playing on your
computer. Two things drive the motion, computed live from the audio:

- **Loudness:** a smoothed volume envelope sets how big the motion is right
  now (quiet → gentle, loud → big raises, wide swings, full pincer).
- **Beat:** an onset detector watches only the bass band (~20-150Hz, the kick
  drum and bassline). On each beat the arm picks new targets and ramps smoothly
  toward them until the next beat:
  - the **gripper opens and closes** in time with the music (a pincer clench
    on every beat)
  - the **wrist twists** and the **shoulder sways** side to side at half-time
    (every other beat, in opposite directions), so the whole arm doesn't lurch
    on every beat

  It only watches the bass band because hi-hats, cymbals, and vocals spike
  far more often than the real tempo. That's what made my earlier versions
  feel chaotic and too fast, especially on slower songs. A peak-relative
  threshold further favors the strongest low-end hits (kicks/downbeats) over
  weaker off-beat bass notes.

This assumes the follower is already calibrated. See the
[Calibration](../README.md#calibration) section of the README.

## Setup

```bash
pip install sounddevice numpy soundfile soundcard
```

(`lerobot` should already be installed.) You only need `soundcard` for
`--audio-source loopback`. Plain `sounddevice`/PortAudio has no WASAPI loopback
support, so loopback capture goes through `soundcard`, which talks to WASAPI
directly.

## Audio source

`--audio-source` sets where the audio comes from. Use whichever gives the
cleanest signal for your setup:

| Source | What it does | When to use it |
|---|---|---|
| `mic` (default) | Records ambient sound through the microphone | Simplest. Works with anything audible, including a phone or another speaker |
| `loopback` | Captures the computer's own audio output digitally (WASAPI), no mic involved | Cleanest signal. Use this if `mic` picks up USB or electrical noise from the arm on the same machine, or room noise |
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
and the mic picks up buzz or whine from the USB connection, switch to
`loopback` (no mic) or `file` (fully offline).

## Tuning the beat (no arm needed)

If the arm reacts to more than the beat (twitchy, too fast), tune the
detector with **monitor mode**. It listens and prints each beat it detects with
a live BPM estimate, but doesn't move the arm. It works with any source, so you
can tune against **whatever you're playing**, including YouTube in a browser:

```bash
# play your song (YouTube, Spotify, anything), then in another window:
python -m demos.dance --monitor --audio-source loopback
```

Watch the printed BPM. If it's close to the song's real tempo and holds
steady, you're good. If it's too high or jumpy, raise the threshold until it
settles:

```bash
python -m demos.dance --monitor --audio-source loopback --sensitivity 2.5
```

`--sensitivity` defaults to `1.8`. Higher = only the strongest hits count
(fewer, cleaner beats); lower = more sensitive (catches quiet beats but also
more noise). Once the BPM looks right in monitor mode, run for real with the
same `--sensitivity` value plus your `--port`.

There's also `--dry-run`, which prints the full computed pose every tick
(not just on beats) without moving the arm. It's more detail than you usually
need, but handy for seeing the exact joint targets.

## Calmer motion

If it's too wild, turn down `--intensity` (default `1.0`). It scales the
sway and twist (the pincer still fully opens and closes on the beat):

```bash
python -m demos.dance --port COM4 --audio-source loopback --intensity 0.5
```

## Making the pincer close

The gripper opens and closes between two angles **in degrees**. Your arm's
calibrated `0` isn't necessarily closed. On some builds `0` is fully *open*, so
the pincer never seems to close. Find your real values:

```bash
python -m demos.dance --port COM4 --read-gripper
```

This frees just the gripper (the rest of the arm holds still) and prints its
live angle. Squeeze it fully closed and note the number, then open it fully and
note that one. Save them once in **`.env`** (see below) so every run uses them,
or pass them on the command line:

```bash
python -m demos.dance --port COM4 --audio-source loopback \
    --gripper-closed -61.32 --gripper-open 61.2
```

(They can be in either order and either sign; use whatever your arm reads.)

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
your training secret (`WANDB_API_KEY`) lives. See
[training-act.md](training-act.md#authentication-keys-live-in-env). The
committed `.env.example` stays secret-free.

The remaining pose amounts (sway/twist degrees, ramp speeds) are constants
near the top of `demos/dance.py`, and the audio DSP lives in
`brachiomimus/analysis.py`; the `--monitor` and `--read-gripper` helpers live
in `tools/diagnostics.py`.

## Windows notes

- `--audio-source loopback` uses `soundcard` to capture the *default* Windows
  playback device via WASAPI. If nothing registers, check that your music
  player is playing to that device (Windows Sound settings). It isn't tied to
  any particular player; it uses whatever Windows treats as the default output.
- The serial port notes from the rest of the docs apply here too. Find your port with
  `[System.IO.Ports.SerialPort]::GetPortNames()` (see
  [README.md](../README.md#finding-your-serial-port)).

## Stopping

Ctrl+C moves the arm to a raised, tucked pose (the shared `READY_POSE` from
`brachiomimus/hardware.py`, the same one `demos/wave.py` uses) before turning
off torque and exiting. It doesn't use the flat rest pose, because the arm
would sag onto the table once torque cuts.
