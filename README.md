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
