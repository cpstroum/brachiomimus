# Teleoperation & recording

Drive Brachiomimus (follower) with Brachius Rex (leader). Recording a
demonstration dataset with a webcam is optional — do it if you're heading
toward training a policy in [training-act.md](training-act.md); skip it if you just
want to puppeteer the arm.

Assumes both arms are already calibrated — see the [Calibration](../README.md#calibration)
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
    --robot.port=COM4 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=COM7 \
    --teleop.id=brachio_rex_leader \
    --display_data=true
```

> Ports (`COM4` follower, `COM7` leader) and the front-camera index (`2`) are
> this setup's real values — substitute your own. On Windows PowerShell the
> line-continuation character is a backtick `` ` `` rather than `\`.
> If LeRobot can't find a calibration for an `--*.id`, pass its folder
> explicitly, e.g.
> `--teleop.calibration_dir "%USERPROFILE%\.cache\huggingface\lerobot\calibration\teleoperators\so_leader"`.

`--display_data=true` opens a window showing the live webcam feed alongside
joint positions. This alone is a complete session — nothing is saved, so
it's a good way to check the camera framing and practice driving Brachiomimus
before committing to a recording, or just to puppeteer it for fun.

## Free up the machine before recording

Recording runs webcam capture, the live display, and video encoding all at once
— memory- and CPU-hungry, especially on a laptop with no dedicated GPU. Notes
from a Surface Pro 7+ (8GB RAM); worth a glance on any hardware:

- **Reboot before a session** — on Windows, closed apps don't reliably release
  memory right away.
- **Disable Chrome's "continue running background apps when Chrome is closed"**
  (`chrome://settings/system`) — it keeps 700MB+ of processes alive for nothing.
- **Watch the Windows Camera Frame Server** in Task Manager — it can balloon in
  memory even before the webcam is plugged in.
- **Plug the external drive** (for `--dataset.root`, below) **into a different
  USB-C controller than the arms and webcam** — sharing a hub can cause bus
  contention that shows up as dropped frames or motor comms errors.

## Record a demonstration dataset (optional)

Pick a task- and version-tagged dataset name up front (e.g.
`brachiomimus-yellowblock-v1`) and give `--dataset.repo_id` and `--dataset.root`
the **same** name. LeRobot refuses to record into a folder that already exists,
so a versioned name lets re-records and other tasks sit side by side instead of
forcing you to delete data to retry.

```bash
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=COM4 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader \
    --teleop.port=COM7 \
    --teleop.id=brachio_rex_leader \
    --display_data=true \
    --dataset.repo_id=cpstroum/brachiomimus-yellowblock-v1 \
    --dataset.root="D:\lerobot\brachiomimus-yellowblock-v1" \
    --dataset.num_episodes=50 \
    --dataset.single_task="Pick up the yellow block and put it in the blue box" \
    --dataset.push_to_hub=false \
    --dataset.vcodec=h264 \
    --dataset.streaming_encoding=true \
    --dataset.encoder_threads=2
```

- `--dataset.single_task` is the natural-language task description saved with
  every episode (keep it **identical** across episodes for the same task — it
  becomes the instruction a policy is conditioned on).
- `--dataset.root` writes the dataset somewhere other than the default cache —
  prefer an external drive (here a `D:` drive). Raw frames before encoding need
  far more space than the final video, so budget accordingly.
- `--dataset.vcodec=h264 --dataset.streaming_encoding=true --dataset.encoder_threads=2`
  encode episodes as they record instead of buffering everything to RAM (matters
  at 50 episodes). `h264` is also much faster/lighter on CPU than the default
  `libsvtav1` (AV1) — worth it without a dedicated GPU.
- If you turn *off* streaming encoding, keep `--dataset.video_encoding_batch_size=1`
  — higher values crash on lerobot 0.4.4 (see
  [learnings](learnings.md#rung-1--recording-datasets)).
- Leave `--dataset.push_to_hub=false` to keep it local; set `true` to back it up
  to the Hub — see [Push the dataset to the Hugging Face Hub](#push-the-dataset-to-the-hugging-face-hub) below.

The 50-episode block-movement dataset used for training here lives on the Hub as
[`cpstroum/so101-brachiomimus-50ep`](https://huggingface.co/datasets/cpstroum/so101-brachiomimus-50ep).

**Adding the wrist camera.** A [wrist-mounted camera](https://makerworld.com/en/models/2445589-camera-module-mount-for-so-101-robot-arm)
is now on the arm (it's what `demos/reach.py` uses). To record with both views,
add it to the camera dict — find its index with `lerobot-find-cameras opencv`:
```
--robot.cameras="{front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}"
```
A close-up of the gripper closing (from `wrist`) plus the overall scene (from
`front`) tends to matter a lot for grasp success.

### Recording workflow

- **Only keep successful episodes.** ACT (behavior cloning) treats everything
  you record as correct — a fumbled grasp teaches the model that fumbling is
  fine. Press `←` to re-record any episode that didn't go cleanly.
- Each cycle alternates a **recorded episode** and an **unrecorded reset**. Do
  the pick-and-place during the episode; use the reset to release the gripper,
  move the object to a slightly *varied* start position, and return the arm to a
  consistent home pose before the next one. That position variation is what lets
  the policy generalize instead of memorizing one trajectory.
- Press `→` the moment the task is done, but **trust the `Recording episode N`
  log line**, not your keypress — there's an encoding delay before recording
  actually resumes.
- Shortcuts (`→` next/end, `←` re-record, `Esc` stop) are a global listener, not
  tied to the viewer window; keep the terminal focused to see the prompts. `Esc`
  is a **clean stop** — it finalizes and encodes what you've recorded so far, it
  doesn't discard.
- To continue later, re-run the same command with `--resume=true`, the **same**
  `--dataset.repo_id`/`--dataset.root`, and `--dataset.num_episodes` set to how
  many *more* episodes you want (not the running total).

### Verify your dataset

- Episode count: check `meta/info.json` → `total_episodes` in the dataset folder
  — the source of truth, don't count in your head.
- One video file per camera for the whole dataset is normal; LeRobot tracks
  episode boundaries by timestamp in the metadata, not as separate files.

## Sanity-check a recorded episode

```bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=COM4 \
    --robot.id=brachiomimus_follower \
    --dataset.repo_id=cpstroum/brachiomimus-yellowblock-v1 \
    --dataset.episode=0
```

This drives Brachiomimus through the recorded actions with no leader
attached — a good way to confirm the dataset actually captured what you
intended before spending time training on it.

## Push the dataset to the Hugging Face Hub

Optional for local use, but **required for this project's training path** —
[training-act.md](training-act.md) runs on HF Jobs and pulls the dataset from
the Hub by repo id, so it has to be uploaded there first. (It's also how the
local `brachiomimus-yellowblock-v1` recording became the Hub dataset
[`cpstroum/so101-brachiomimus-50ep`](https://huggingface.co/datasets/cpstroum/so101-brachiomimus-50ep).)

Log in first:

```bash
hf auth login    # replaces the deprecated `huggingface-cli login`
```

Paste a token with **write** access from <https://huggingface.co/settings/tokens>;
the `repo_id` namespace must be your own account.

**At the end of recording** — flip the flags on `lerobot-record`:
```
    --dataset.push_to_hub=true \
    --dataset.private=true      # optional; omit to publish publicly
```

**An already-recorded dataset, later** — point `LeRobotDataset` at the local
root and push:
```python
from lerobot.datasets.lerobot_dataset import LeRobotDataset

# root is whatever you passed to --dataset.root when recording
ds = LeRobotDataset("cpstroum/so101-brachiomimus-50ep", root=r"D:\lerobot\brachiomimus-yellowblock-v1")
ds.push_to_hub(private=True)    # drop private=True to publish publicly
```

- Datasets are **public by default** — pass `--dataset.private=true` / `private=True`
  to keep it to yourself.
- Pushing never deletes the local copy; you keep both.
- 50 episodes of 640×480 video is a few GB, so expect the upload to take a while.

Dataset ready? Move on to [training-act.md](training-act.md).
