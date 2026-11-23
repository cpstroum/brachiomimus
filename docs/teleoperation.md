# Teleoperation and recording

Drive Brachiomimus (follower) with Brachius Rex (leader). Recording a
demonstration dataset with a webcam is optional. Do it if you plan to train a
policy ([training-act.md](training-act.md)); skip it if you just want to
puppeteer the arm.

This assumes both arms are already calibrated. See the
[Calibration](../README.md#calibration) section of the README.

Everything here uses LeRobot's built-in CLI (`lerobot-*` commands) instead of
custom scripts. It handles the dataset format, image encoding, and recording
loop for you.

## Camera setup (OpenCV)

Before recording any demonstrations, find and check your webcam:

```bash
lerobot-find-cameras opencv
```

This lists each camera it finds with its index or path (`0`, `1`, `/dev/video0`,
...). Use that value as `index_or_path` in the `--robot.cameras` flag below.

**Multiple cameras** (e.g. an overhead or side view plus a wrist-mounted one)
are just another key in the same dict:
```
--robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}"
```
With both, a trained policy sees the gripper closing on the object up close
(from `wrist`) and the whole scene (from `front`). That tends to matter a lot
for grasp success.

**Windows gotchas:**
- `[ERROR:0@...] obsensor_uvc_stream_channel.cpp ... Camera index out of range`
  is harmless. OpenCV is probing for Orbbec/RealSense-style sensors across a
  range of indices; it has nothing to do with your webcam.
- If one index times out with `Timed out waiting for frame from camera
  OpenCVCamera(N)`, something else probably has that device open (Teams, Zoom,
  the Windows Camera app), or it's the wrong or a virtual device. Try the other
  indices it found.
- Check `outputs\captured_images` after running the command. It saves a
  snapshot from each working camera, so you can see which index is your webcam
  before you put it in the commands below.
- If you can, turn off auto white balance and auto exposure in the camera's own
  settings. A fixed value stays the same from session to session, which matters
  more for training than getting the color "right."

Before recording, check the framing:
- Brachiomimus's gripper stays fully in frame across its whole range of
  motion (nothing clipped at the edges).
- The camera is rigidly mounted and won't shift between episodes.
- The background behind the workspace stays the same for the whole dataset.

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

> The ports (`COM4` follower, `COM7` leader) and front-camera index (`2`) are
> my real values. Substitute your own. In Windows PowerShell, the
> line-continuation character is a backtick `` ` `` instead of `\`.
> If LeRobot can't find a calibration for an `--*.id`, pass its folder
> explicitly, e.g.
> `--teleop.calibration_dir "%USERPROFILE%\.cache\huggingface\lerobot\calibration\teleoperators\so_leader"`.

`--display_data=true` opens a window with the live webcam feed next to the
joint positions. Nothing is saved, so this is a good way to check the camera
framing and practice driving Brachiomimus before you record, or just to
puppeteer it for fun.

## Record a demonstration dataset (optional)

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

- `--dataset.single_task` is the plain-language task description saved with
  every episode. Keep it **identical** across episodes for the same task; it
  becomes the instruction a policy is conditioned on.
- `--dataset.root` writes the dataset somewhere other than the default cache.
  I use a `D:` drive with room for 50 episodes of video.
- `--dataset.vcodec=h264 --dataset.streaming_encoding=true --dataset.encoder_threads=2`
  encodes episodes while recording instead of holding everything in RAM. This
  matters at 50 episodes.
- Leave `--dataset.push_to_hub=false` to keep it local, or set `true` to back it
  up to the Hub (you need to be logged in; see the auth note in training-act.md).
- LeRobot walks you through each episode and a reset phase in between. Watch the
  on-screen prompts for keyboard shortcuts (re-record the last episode, stop
  early, etc).

I recorded the 50-episode block-movement dataset in one morning. It's on the Hub
as [`cpstroum/so101-brachiomimus-50ep`](https://huggingface.co/datasets/cpstroum/so101-brachiomimus-50ep).

**Adding the wrist camera.** There's now a
[wrist-mounted camera](https://makerworld.com/en/models/2445589-camera-module-mount-for-so-101-robot-arm)
on the arm (it's what `demos/reach.py` uses). I battled two mis-configured
mounts first: I printed one for the SO100 arm, not my SO101, and I needed
M2/M3 Ruthex inserts for another bad print. To record with both views,
add it to the camera dict and find its index with `lerobot-find-cameras opencv`:
```
--robot.cameras="{front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}"
```

## Sanity-check a recorded episode

```bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=COM4 \
    --robot.id=brachiomimus_follower \
    --dataset.repo_id=cpstroum/brachiomimus-yellowblock-v1 \
    --dataset.episode=0
```

This plays the recorded actions back on Brachiomimus with no leader attached.
Use it to confirm the dataset captured what you meant before you spend time
training on it.

Next: [training-act.md](training-act.md).
