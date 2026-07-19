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

**Multiple cameras** (e.g. the overhead/side view plus a wrist-mounted one)
just add another key to the same dict:
```
--robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}"
```
Recording with both means a trained policy sees the gripper closing on an
object up close (from `wrist`) as well as the overall scene (from `front`),
which tends to matter a lot for grasp success.

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
- Drop `--dataset.push_to_hub=false` (or set it to `true`) once you've run
  `huggingface-cli login` and want the dataset backed up to the Hub.
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

Dataset ready? Move on to [TRAINING.md](TRAINING.md).
