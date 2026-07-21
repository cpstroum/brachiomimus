# brachiomimus

Experiments with a pair of SO-101 robotic arms using LeRobot:

- **Brachius Rex** — the leader arm (teleoperator, human-driven)
- **Brachiomimus** — the follower arm (does the actual work)

This doc is the getting-started path: get the follower talking to your
computer, calibrated, and moving on its own. Once that's working:

- **[TELEOPERATION.md](TELEOPERATION.md)** — drive Brachiomimus with Brachius
  Rex and record a demonstration dataset with a webcam
- **[TRAINING.md](TRAINING.md)** — train a policy on that dataset and run it
  on the robot
- **[MUSIC.md](MUSIC.md)** — make Brachiomimus dance to music playing on your
  computer

Ports/IDs in the commands below are examples — substitute your own (`COM3`
on Windows, `/dev/ttyACM0` on Linux, etc).

## Finding your serial port

**Windows (PowerShell):**
```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```
Plug in the arm, run it again, and the new entry is your port (e.g. `COM3`).

**Linux:**
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```
Feetech-based arms typically appear as `/dev/ttyACM0`. Run `dmesg | tail -20` if unsure.

## Calibration

After running `lerobot-calibrate`, files are saved here:

| Arm | Name | Path |
|-----|------|------|
| Follower | Brachiomimus | `~/.cache/huggingface/lerobot/calibration/robots/so101_follower/brachiomimus_follower.json` |
| Leader | Brachius Rex | `~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/brachius_rex.json` |

Calibrate the follower:
```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=brachiomimus_follower
```

Calibrate the leader:
```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/ttyACM1 --teleop.id=brachius_rex
```

**Tip:** When calibrating, position the arm at the physical midpoint of every
joint *before* launching the script — not just when prompted. If a joint is
too far off-center, LeRobot will crash with a `Magnitude exceeds 2047` error.

## Wave demo — direct scripted control of Brachiomimus

A standalone demo that drives Brachiomimus (the follower) straight through a
hand-rolled `FeetechMotorsBus`, bypassing LeRobot's robot/teleoperator
classes entirely. No leader arm or camera involved — just the follower doing
a scripted wave. Good first check that calibration took and the arm responds.

```bash
# Linux
python wave.py --port /dev/ttyACM0 --reps 3

# Windows
python wave.py --port COM4 --reps 3
```

## Face tracking demo — Brachiomimus watches the room

Points a plain webcam (not eye-in-hand — anywhere in the room works) at the
space and turns the arm to face whoever it sees, using OpenCV's built-in
Haar cascade face detector. No ML training or camera calibration involved.

> **OpenCV 5 caveat:** this uses the classic `cv2.CascadeClassifier` Haar
> API, which OpenCV 5 removed (along with the bundled cascade files). Run
> it on OpenCV **4.x** — `pip install "opencv-python>=4.8,<5"`. `reach.py`
> below has no such constraint.

```bash
python track.py --port /dev/ttyACM0
python track.py --port COM4 --show      # debug window with the face boxed
python track.py --dry-run --show        # try it with no arm connected
```

If the arm pans or tilts the wrong way for your camera's orientation, add
`--invert-pan` / `--invert-tilt`.

## Reach demo — grasp a colored object with the wrist camera

Uses a **wrist-mounted** camera (not the room-facing one from the tracking
demo above) to visually servo onto a colored blob — defaults to a
lavender-ish purple — and grasp it. No inverse kinematics or depth
estimation: it centers the blob with `shoulder_pan`/`wrist_flex` and
extends `elbow_flex` a bit each tick, using the blob getting bigger as the
"getting closer" signal, then closes the gripper once it fills enough of
the frame.

Install the vision dependencies first (on top of your working LeRobot
environment): `pip install -r requirements.txt`.

```bash
python reach.py --port /dev/ttyACM0 --camera 1 --show
python reach.py --dry-run --show      # tune detection with no arm connected
```

**This needs on-arm tuning before it'll do anything useful** — see the
docstring in `reach.py` for what to jog in by hand (the hover pose) and
what to dial in with `--show` (the HSV color range, and
`--invert-pan`/`--invert-tilt` if centering moves the wrong way). There's
no force sensing, so it doesn't verify the grasp actually took — watch the
lift and judge for yourself, and don't leave it unattended.

**Pick a good target.** Detection is color-based, so it wants a distinct,
*saturated* color. Muted natural objects (dried lavender) under a color
cast detect poorly. The reliable trick: tie a scrap of brightly colored
yarn at the spot you want grabbed, in a hue that's absent from the rest of
the scene, and detect that — high saturation also keeps the gripper and any
pale background out of the mask. Use `probe_color.py` to read the marker's
real HSV (click it in the feed), then set `--hue-min/--hue-max/--sat-min/
--val-min` to bracket it. For a thin marker, lower `--min-area` so the grasp
still triggers. (There's also a `--white` mode for a white-string target,
but it needs a dark backdrop and can latch onto a shiny gripper — a colored
marker is safer.)

## Lessons learned: LeRobot compatibility notes (v0.4.x)

These broke silently when upgrading from older LeRobot versions — relevant
if you're writing your own low-level scripts like `wave.py`:

**Import path** — `lerobot.common.robot_devices.motors.feetech` no longer exists. Use:
```python
from lerobot.motors.feetech import FeetechMotorsBus
```

**Motor definitions** — motors are no longer plain `(id, model)` tuples. Use the `Motor` dataclass:
```python
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

motors = {
    "shoulder_pan": Motor(id=1, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    # ...
}
```

**Calibration** — pass calibration explicitly as a `dict[str, MotorCalibration]` loaded from the JSON file LeRobot saves at:
```
~/.cache/huggingface/lerobot/calibration/robots/so101_follower/brachiomimus_follower.json
```
```python
import json
from lerobot.motors import MotorCalibration

with open(calibration_path) as f:
    data = json.load(f)
calibration = {name: MotorCalibration(**fields) for name, fields in data.items()}
bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
```
