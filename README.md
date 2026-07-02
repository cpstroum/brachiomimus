# carpaldactyl
Experiments with an SO-101 robotic arm using LeRobot

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

## Wave demo

```bash
# Linux
python wave.py --port /dev/ttyACM0 --reps 3

# Windows
python wave.py --port COM4 --reps 3
```

## Calibration file locations

After running `lerobot-calibrate`, files are saved here:

| Arm | Path |
|-----|------|
| Follower | `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<name>.json` |
| Leader | `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/<name>.json` |

**Tip:** When calibrating, position the arm at the physical midpoint of every joint *before* launching the script — not just when prompted. If a joint is too far off-center, LeRobot will crash with a `Magnitude exceeds 2047` error.

## LeRobot compatibility notes (v0.4.x)

These broke silently when upgrading from older LeRobot versions:

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
~/.cache/huggingface/lerobot/calibration/robots/so_follower/<name>.json
```
```python
import json
from lerobot.motors import MotorCalibration

with open(calibration_path) as f:
    data = json.load(f)
calibration = {name: MotorCalibration(**fields) for name, fields in data.items()}
bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
```
