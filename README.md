# brachiomimus

My experiments with a pair of SO-101 robot arms, using LeRobot:

- **Brachius Rex**: the leader arm. I drive it by hand (teleoperation).
- **Brachiomimus**: the follower arm. It does the work.

Thank you to Zach for unending patience while we built the arms and battled with
LeRobot. We won.

## The spectrum of experiments

I've tried several ways of getting the arm to do something. Each step up trades
moves I write by hand for behavior the arm learns. The code and docs are
organized around those steps, which I call rungs:

| Rung | Approach | Perception | Control | Generalizes to | Where |
|------|----------|------------|---------|----------------|-------|
| **0: open-loop scripted** | hand-authored motion, no feedback | none | I author every pose | nothing; it does exactly what I wrote | `demos/wave.py`, `demos/dance.py` + [music](docs/music.md) |
| **0.5: classical closed-loop** | perception in the loop, hand-authored control law | OpenCV (faces, color blobs) | visual servoing | new object *positions* in view | `demos/track.py`, `demos/reach.py` |
| **1: imitation (ACT)** | learn one task from my demos | learned | learned | new positions *within* the trained task | [teleoperation](docs/teleoperation.md) → [training](docs/training-act.md) |
| **2: VLA** *(next)* | language-conditioned, pretrained | learned + language | learned | new *instructions* and tasks | [roadmap](docs/vla.md) |

I started by scripting every move (`wave`, `dance`), then added a camera and a
feedback loop (`track`, `reach`), then trained a policy from my own
demonstrations (ACT). Next is a policy that takes language instructions (VLA).
See [docs/vla.md](docs/vla.md) for that plan.

## Repository layout

```
brachiomimus/     shared core (importable package)
  hardware.py       motor defs, canonical poses, calibration loading
  motion.py         pose interpolation / slew-limit helpers
  vision.py         OpenCV perception (face + colored-blob detection)
  audio.py          real-time audio sources for the music demo
  analysis.py       audio DSP (loudness, beat detection, BPM)
  config.py         env/.env-sourced user settings
demos/            runnable behaviors (rungs 0 and 0.5)
  wave.py  dance.py  track.py  reach.py
tools/            tuning / calibration helpers (not behaviors)
  diagnostics.py  probe_color.py
docs/             how-to guides and the roadmap
```

Behaviors and tools import from the `brachiomimus` package, so launch them as
modules from the repo root, e.g. `python -m demos.wave`. Running
`python demos/wave.py` won't find the package.

The ports and IDs in the commands below are mine. Substitute your own (`COM3`
on Windows, `/dev/ttyACM0` on Linux, etc).

**Settings and secrets:** copy `.env.example` to `.env` (gitignored) and fill in
your arm's calibration. `.env` is also where the W&B key for cloud training
lives. See [docs/training-act.md](docs/training-act.md#authentication-keys-live-in-env).

## Finding your serial port

**Windows (PowerShell):**
```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```
Plug in the arm and run it again. The new entry is your port (e.g. `COM3`).

**Linux:**
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```
Feetech-based arms usually show up as `/dev/ttyACM0`. Run `dmesg | tail -20` if you're not sure.

## Calibration

After running `lerobot-calibrate`, the files are saved here:

| Arm | Name | Port | Calibration file |
|-----|------|------|------------------|
| Follower | Brachiomimus | `COM4` | `~/.cache/huggingface/lerobot/calibration/robots/so_follower/brachiomimus_follower.json` |
| Leader | Brachius Rex | `COM7` | `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/brachio_rex_leader.json` |

(LeRobot writes under `so_follower` / `so_leader`, not `so101_*`. The ports are
how Windows enumerates them on my setup: `COM4` for the follower, `COM7` for the
leader. On Linux they'd be `/dev/ttyACM*`.)

Calibrate the follower:
```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=COM4 --robot.id=brachiomimus_follower
```

Calibrate the leader:
```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=COM7 --teleop.id=brachio_rex_leader
```

**Tip:** put the arm at the physical midpoint of every joint *before* you launch
the script, not just when it prompts you. If a joint is too far off-center,
LeRobot crashes with a `Magnitude exceeds 2047` error.

## Rung 0: wave (direct scripted control)

This drives Brachiomimus through a hand-rolled `FeetechMotorsBus` and skips
LeRobot's robot and teleoperator classes entirely. No leader arm, no camera;
the follower just waves. It's my first check that calibration took and the arm
responds.

```bash
python -m demos.wave --port /dev/ttyACM0 --reps 3   # Linux
python -m demos.wave --port COM4 --reps 3           # Windows
```

Dancing to music (also rung 0) is in [docs/music.md](docs/music.md).

## Rung 0.5: track (Brachiomimus watches the room)

Point a plain webcam at the space (it doesn't need to be on the arm; anywhere in
the room works) and the arm turns to face a target it sees. There are two
`--target` modes:

- `face` (default) uses OpenCV's built-in Haar cascade face detector.
- `color` uses the same HSV color-blob detection as `reach` below, so it can
  follow any colored marker instead of a face.

Neither one needs ML training or camera calibration.

> **OpenCV 5 caveat:** `--target face` uses the classic
> `cv2.CascadeClassifier` Haar API, which OpenCV 5 removed along with the
> bundled cascade files. Run it on OpenCV **4.x**: `pip install
> "opencv-python>=4.8,<5"`. `--target color` (and `reach` below) works on
> either version.

```bash
python -m demos.track --port /dev/ttyACM0
python -m demos.track --port COM4 --show      # debug window with the target boxed
python -m demos.track --dry-run --show        # try it with no arm connected
python -m demos.track --dry-run --show --target color   # track a colored marker instead of a face
```

If the arm pans or tilts the wrong way for your camera's orientation, add
`--invert-pan` / `--invert-tilt`. In `--target color` mode, tune
`--hue-min`/`--hue-max`/`--sat-min`/`--val-min` the same way as `reach`
below (`python -m tools.probe_color` reads a marker's real HSV).

## Rung 0.5: reach (grasp a colored object with the wrist camera)

This uses a **wrist-mounted** camera (not the room camera from `track`) to steer
onto a colored blob and grab it. The default color is a lavender-ish purple.
There's no inverse kinematics or depth estimation. It centers the blob with
`shoulder_pan`/`wrist_flex`, extends `elbow_flex` a little each tick, treats
the blob getting bigger as "getting closer," and closes the gripper once the
blob fills enough of the frame.

Install the vision dependencies first, on top of your working LeRobot
environment: `pip install -r requirements.txt`.

```bash
python -m demos.reach --port /dev/ttyACM0 --camera 1 --show
python -m demos.reach --dry-run --show      # tune detection with no arm connected
```

**This needs tuning on the arm before it does anything useful.** The docstring
in `demos/reach.py` covers what to jog in by hand (the hover pose) and what to
dial in with `--show` (the HSV color range, and `--invert-pan`/`--invert-tilt`
if centering moves the wrong way). There's no real force sensing, so it can't
fully confirm the grasp worked. Watch the lift yourself and don't leave it
running unattended.

**Pick a good target.** Detection is color-based, so it needs a distinct,
*saturated* color. Muted natural objects (I tried dried lavender) detect poorly
under a color cast. What worked: tie a scrap of brightly colored yarn where you
want it to grab, in a color that isn't anywhere else in the scene, and detect
that. High saturation also keeps the gripper and any pale background out of
the mask. Run `python -m tools.probe_color` and click the marker to read its
real HSV, then set `--hue-min/--hue-max/--sat-min/--val-min` around it. For a
thin marker, lower `--min-area` so the grasp still triggers. (There's also a
`--white` mode for a white string, but it needs a dark backdrop and can latch
onto a shiny gripper. A colored marker is safer.)

**Find the load threshold.** For a rigid target (a can, a block),
`--load-threshold` can end the grasp early once the gripper servo's reported
load shows it has stalled against the object, instead of always waiting the
fixed `GRASP_HOLD_S` time. It's off (`0`) by default, so this is optional
tuning; you don't need it for a working grasp. To pick a value:
1. Run with `--show` and leave `--load-threshold` at 0 so nothing triggers early.
2. Let it grab the real target and watch the "load=" number in the debug
   overlay while the gripper closes.
3. Note the load in open air (closing on nothing) and the load once it stalls
   against the object. Pick a threshold clearly above the first and well
   below the second.
4. Re-run with `--load-threshold <that number>`. It should lift sooner when it
   has something, and still fall back to `GRASP_HOLD_S` if it closes on air.

## Rungs 1 and 2: learned policies

- **[docs/teleoperation.md](docs/teleoperation.md)**: drive Brachiomimus with
  Brachius Rex and record a demonstration dataset with a webcam
- **[docs/training-act.md](docs/training-act.md)**: train an ACT policy on that
  dataset and run it on the robot (rung 1)
- **[docs/vla.md](docs/vla.md)**: my plan for language-conditioned policies (rung 2)

## Lessons learned

Things that broke or took me a while to figure out (LeRobot version changes,
OpenCV, training settings) are in **[docs/learnings.md](docs/learnings.md)**,
grouped by rung.
