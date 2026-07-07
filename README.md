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

## Training a policy (leader + follower + webcam)

Everything below uses LeRobot's built-in CLI (`lerobot-*` commands) rather than
custom scripts — it handles the dataset format, image encoding, and training
loop for you. Substitute your own ports, arm IDs, and `$HF_USER`.

### 1. Find your webcam

```bash
lerobot-find-cameras opencv
```

This lists each detected camera with its index/path (`0`, `1`, `/dev/video0`,
...). Use that value as `index_or_path` below.

### 2. Calibrate the leader arm

Same idea as the follower calibration already documented above, but for the
teleoperator:

```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/ttyACM1 --teleop.id=brachiomimus_leader
```

Saved to `~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/brachiomimus_leader.json`.

### 3. Teleoperate (sanity check before recording)

```bash
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=brachiomimus_leader \
    --display_data=true
```

`--display_data=true` opens a window showing the live webcam feed alongside
joint positions — confirm the camera is framed on the workspace before
recording.

### 4. Record a demonstration dataset

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=brachiomimus_leader \
    --display_data=true \
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --dataset.num_episodes=50 \
    --dataset.single_task="Describe the task in a few words" \
    --dataset.push_to_hub=false
```

- `--dataset.single_task` is the natural-language task description saved with
  every episode (keep it consistent across episodes for the same task).
- Drop `--dataset.push_to_hub=false` (or set it to `true`) once you've run
  `huggingface-cli login` and want the dataset backed up to the Hub.
- During recording, LeRobot walks you through each episode and a reset phase;
  check the on-screen prompts for keyboard shortcuts (re-record last episode,
  early-stop, etc).

Recorded locally at `~/.cache/huggingface/lerobot/{repo_id}`.

### 5. Sanity-check a recorded episode

```bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --dataset.episode=0
```

This drives the follower arm through the recorded actions with no leader
attached — a good way to confirm the dataset actually captured what you
intended before spending time training on it.

### 6. Train a policy

```bash
lerobot-train \
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --policy.type=act \
    --output_dir=outputs/train/act_brachiomimus \
    --job_name=act_brachiomimus \
    --policy.device=cuda \
    --wandb.enable=false
```

Use `--policy.device=mps` on Apple Silicon or `cpu` if you have no GPU (much
slower). Checkpoints land in `outputs/train/act_brachiomimus/checkpoints/`.

### 7. Run the trained policy on the robot

```bash
lerobot-rollout \
    --strategy.type=base \
    --policy.path=outputs/train/act_brachiomimus/checkpoints/last/pretrained_model \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --task="Describe the task in a few words" \
    --duration=60
```

No leader arm needed here — the policy is driving the follower directly from
camera + joint observations.
