# Teleoperation & recording

Drive Brachiomimus (follower) with Brachius Rex (leader). Recording a
demonstration dataset with a webcam is optional — do it if you're heading
toward training a policy in [TRAINING.md](TRAINING.md); skip it if you just
want to puppeteer the arm.

Assumes both arms are already calibrated — see the [Calibration](README.md#calibration)
section in the getting-started doc.

Everything below uses LeRobot's built-in CLI (`lerobot-*` commands) rather
than custom scripts — it handles the dataset format, image encoding, and
recording loop for you.

## Camera setup (OpenCV)

Before recording any demonstrations, find and verify your webcam:

```bash
lerobot-find-cameras opencv
```

This lists each detected camera with its index/path (`0`, `1`, `/dev/video0`,
...). Use that value as `index_or_path` in the `--robot.cameras` flag below.

**Windows gotchas:**
- `[ERROR:0@...] obsensor_uvc_stream_channel.cpp ... Camera index out of range` —
  harmless. OpenCV is just probing for Orbbec/RealSense-style sensors across a
  range of indices; it's unrelated to your webcam.
- If one index times out with `Timed out waiting for frame from camera
  OpenCVCamera(N)`, something else likely has that device open (Teams, Zoom,
  the Windows Camera app) or it's the wrong/virtual device — try the other
  indices it found.
- Check `outputs\captured_images` after running the command — it saves a
  snapshot per working camera, so you can open them and see which index is
  actually your webcam before wiring it into the commands below.
- Disable auto white balance / auto exposure in the camera's own settings if
  you can — a fixed value stays consistent session to session, which matters
  more for training than getting the color "right."

Camera framing checklist before recording:
- Brachiomimus's gripper stays fully in frame across its whole range of
  motion (nothing clipped at the edges).
- The camera is rigidly mounted and won't shift between episodes.
- The scene behind the workspace stays the same for the whole dataset.

## Teleoperate

```bash
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=brachius_rex \
    --display_data=true
```

`--display_data=true` opens a window showing the live webcam feed alongside
joint positions. This alone is a complete session — nothing is saved, so
it's a good way to check the camera framing and practice driving Brachiomimus
before committing to a recording, or just to puppeteer it for fun.

## Record a demonstration dataset (optional)

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=brachius_rex \
    --display_data=true \
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --dataset.num_episodes=50 \
    --dataset.single_task="Describe the task in a few words" \
    --dataset.push_to_hub=false
```

- `--dataset.single_task` is the natural-language task description saved with
  every episode (keep it consistent across episodes for the same task).
- Drop `--dataset.push_to_hub=false` (or set it to `true`) once you've logged
  in and want the dataset backed up to the Hub — see
  [Push the dataset to the Hugging Face Hub](#push-the-dataset-to-the-hugging-face-hub) below.
- During recording, LeRobot walks you through each episode and a reset phase;
  check the on-screen prompts for keyboard shortcuts (re-record last episode,
  early-stop, etc).

Recorded locally at `~/.cache/huggingface/lerobot/{repo_id}`.

## Sanity-check a recorded episode

```bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --dataset.episode=0
```

This drives Brachiomimus through the recorded actions with no leader
attached — a good way to confirm the dataset actually captured what you
intended before spending time training on it.

## Push the dataset to the Hugging Face Hub

Backing the dataset up to the Hub is optional — everything already lives
locally under `--dataset.root` (or the default cache). Push it if you want a
remote copy, want to train on another machine, or want to share it.

Either way, log in first:

```bash
hf auth login
```

This replaces the deprecated `huggingface-cli login`. Paste a token with
**write** access from <https://huggingface.co/settings/tokens>. The
`repo_id` namespace must be your own account (`${HF_USER}/...`) for the push
to succeed.

**Option A — push automatically at the end of recording.** Flip the flag on
`lerobot-record` (from the [record command](#record-a-demonstration-dataset-optional)
above):

```bash
    --dataset.repo_id=${HF_USER}/brachiomimus-so101 \
    --dataset.push_to_hub=true \
    --dataset.private=true          # optional; omit to publish publicly
```

LeRobot writes the dataset locally first, then uploads everything (videos +
joint/action data + task metadata) once all episodes are recorded. A failed
upload at the last episode is annoying, so for a first run you may prefer
Option B.

**Option B — push an already-recorded dataset later.** If you recorded with
`--dataset.push_to_hub=false`, point `LeRobotDataset` at the local root and
call `push_to_hub()`:

```python
from lerobot.datasets.lerobot_dataset import LeRobotDataset

# root is whatever you passed to --dataset.root when recording
ds = LeRobotDataset("${HF_USER}/brachiomimus-so101", root="D:/lerobot/brachiomimus-so101")
ds.push_to_hub(private=True)        # drop private=True to publish publicly
```

Notes:
- Datasets are **public by default** — pass `--dataset.private=true` (Option A)
  or `private=True` (Option B) to keep it to yourself.
- Pushing never deletes the local copy; you always keep both.
- 50 episodes of 640×480 video is a few GB, so expect the upload to take a
  while on a typical connection.

Dataset ready? Move on to [TRAINING.md](TRAINING.md).
