# Lessons learned

Things that broke, surprised me, or took a while to figure out. I keep them here
so the how-to docs stay short. They're grouped by the rung of the
[spectrum](../README.md#the-spectrum-of-experiments) they came from.

## Rung 0 / 0.5: low-level control (LeRobot v0.4.x compatibility)

These broke silently when I upgraded from older LeRobot versions. They matter
if you're reading or writing the low-level scripts under `demos/` (`wave.py`
and friends) or the shared `brachiomimus/hardware.py`.

**Import path.** `lerobot.common.robot_devices.motors.feetech` no longer
exists. Use:
```python
from lerobot.motors.feetech import FeetechMotorsBus
```

**Motor definitions.** Motors are no longer plain `(id, model)` tuples. Use
the `Motor` dataclass:
```python
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

motors = {
    "shoulder_pan": Motor(id=1, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    # ...
}
```

**Calibration.** Pass calibration explicitly as a `dict[str, MotorCalibration]`
loaded from the JSON file LeRobot saves at:
```
~/.cache/huggingface/lerobot/calibration/robots/so_follower/brachiomimus_follower.json
```
```python
import json
from lerobot.motors import MotorCalibration

with open(calibration_path) as f:
    data = json.load(f)
calibration = {name: MotorCalibration(**fields) for name, fields in data.items()}
bus = FeetechMotorsBus(port=port, motors=motors, calibration=calibration)
```
(In this repo, `brachiomimus/hardware.py` already wraps the last two for you as
`MOTORS` and `load_calibration()`.)

**Calibrating.** Put the arm at the physical midpoint of every joint *before*
launching `lerobot-calibrate`, not just when prompted. If a joint is too far
off-center, LeRobot crashes with `Magnitude exceeds 2047`.

## Rung 0.5: OpenCV vision

**I spent two weeks solid on this approach before switching.** I wanted to see
how far I could get with just a feedback loop and OpenCV. I tried masking the
camera feed on the color banding of a can label, but at a distance there might
only be a few pixels of that color. Then I spent most of my time spiraling
around the approach-grasp loop: a side camera for coarse distance, then a sweep
on the wrist camera to center the can and approach. Without depth sensing, I
often missed it. When I had something like 30 parameters on my function call, I
knew this was a bad strategy.

**OpenCV 5 removed the Haar cascade API.** `track.py`'s face detection uses the
classic `cv2.CascadeClassifier` + `cv2.data.haarcascades`, which OpenCV 5
dropped along with the bundled cascade XML files. Pin OpenCV 4.x
(`opencv-python>=4.8,<5`) to run the face demo. The color-blob path (`reach.py`)
works on 4.x or 5.x.

**Use real HSV values, not textbook ones.** A target's hue under *your* camera
and lighting is often nowhere near the textbook value, especially for muted
objects under a color cast. Sample actual pixels with
`python -m tools.probe_color` instead of guessing, and use a bright,
*saturated* marker in a color that isn't elsewhere in the scene. High
saturation also keeps the low-saturation gripper and pale background out of
the mask.

**No real force sensing, but `reach.py` has a load-based workaround.** Visual
servoing alone can't confirm a grasp. `reach.py`'s GRASP state can end early by
reading the gripper servo's `Present_Load` and comparing it to
`--load-threshold` (off by default at 0). Closing on a rigid object (a can, a
block) stalls the servo well before it reaches the commanded `--gripper-closed`
angle, so the load climbs past what's normal in open air. It's still a guess,
not confirmation: a soft or thin target may never build enough load (it falls
back to the `GRASP_HOLD_S` timer, same as before), and friction could trigger it
early. Tune the threshold with `--show` by watching the live `load=` overlay
while it squeezes the real target. Watch the lift, and don't leave it running
unattended.

## Rung 1: training ACT on HF Jobs

Notes from training the block-movement policy on
[`cpstroum/so101-brachiomimus-50ep`](https://huggingface.co/datasets/cpstroum/so101-brachiomimus-50ep)
(50 episodes, "Pick up the yellow block and put it in the blue box").

**5k steps was not enough.** My first run (`--steps=5000`) twitched in place and
failed eval. My first assumption was that 50 episodes wasn't enough data, and I
dug into the refresh rate of my recording and eval, thinking my laptop was
maxed out. Then I retrained on the exact same 50 episodes for `--steps=30000`
(6×) and it worked. The dataset hadn't been the bottleneck; my patience was!
Batch size stayed at 16 throughout.

**Watch the wall clock, not just the step count.** A `t4-small` Job **timed out**
before finishing 30k steps, because loading the dataset and setting up the
environment takes real minutes before training starts. What fixed it: a bigger
flavor (`a10g-small`), a longer `--timeout` (6h), and `--save_freq=5000` so a
timeout still leaves checkpoints I can recover.

**Always enable W&B.** I use `--wandb.enable=true --wandb.project=so101-brachiomimus`
on every run. The loss curve is the only way to judge a slow cloud run without
spending an eval on it, and comparing curves across runs is how I picked the
step count.

**Publish the policy or you can't eval it.** `--policy.push_to_hub=true` pushes
the trained model to `--policy.repo_id` on the Hub, and eval pulls it with
`--policy.path=<that repo id>`. My early runs skipped this and the policy was
stuck in the Job.

**Keep keys out of the command.** I was already logged in to HF
(`huggingface-cli login`), so no token appears in any command; HF Jobs pulls it
from the `HF_TOKEN` secret. The W&B key lives in the gitignored `.env` and is
passed with `--secrets-file .env` (encrypted server-side), so it never ends up
in shell history, notes, or a commit. My early runs pasted the key inline
(`--secrets WANDB_API_KEY=wandb_...`); I switched to `.env` + `--secrets-file`.

**Eval with record, not rollout.** I capture rollouts with `lerobot-record
--policy.path=...` into an `eval_*` dataset, sometimes with the leader still
attached so I can reset between episodes. Keep eval-dataset and policy versions
matched (`-v2` with `-v2`).

## Repository structure

Launch behaviors and tools as modules from the repo root
(`python -m demos.wave`, `python -m tools.probe_color`) so Python can find the
`brachiomimus` package they import. Running a script by path
(`python demos/wave.py`) only puts the script's own folder on `sys.path`, so
the package import fails. Use `-m`.
