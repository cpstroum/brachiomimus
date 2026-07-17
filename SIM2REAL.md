# Sim2real: train in simulation, deploy zero-shot on Brachiomimus

Instead of recording dozens of real demonstrations (TELEOPERATION.md +
TRAINING.md) or fine-tuning a 3B-parameter foundation model on a 40GB+ GPU
(GROOT.md, currently paused), this path trains a policy entirely in a
GPU-parallelized simulator via reinforcement learning, then deploys it on
Brachiomimus with **zero real-world demonstrations**. Real episodes only
show up later, if at all, to double-check sim-to-real transfer worked.

## Why Squint instead of lerobot-sim2real

[lerobot-sim2real](https://github.com/StoneT2000/lerobot-sim2real) is the
original reference implementation of this idea (PPO in
[ManiSkill](https://github.com/haosulab/ManiSkill), zero-shot RGB policy
deploy) but it's built and documented around the **SO-100** arm. Its own
README points SO-101 users to
[Squint](https://github.com/aalmuzairee/squint) instead — a faster method
(visual SAC, solves tasks "in minutes") built specifically for **SO-101
with a wrist camera**, which matches Brachiomimus's hardware directly.

Both use ManiSkill under the hood, so the underlying concepts (domain
randomization, camera alignment, greenscreen background capture) carry over
if you ever want to read the original repo's tutorial
(`docs/zero_shot_rgb_sim2real.md`) for more background.

## What you get out of the box

Squint ships 8 pretrained-from-scratch task environments for SO-101:

| Task | What it does | Rough sim training time |
|------|---------------|--------------------------|
| Reach | move gripper to a target position | ~2 min |
| Lift | pick up a cube/can | ~3-4 min |
| Place | put an object in a bin | ~5-6 min |
| Stack | stack objects | ~6-9 min |

These are on an RTX 4090-class GPU — far lighter than the 40GB+ GPU GROOT.md
needed, and no HF/Azure GPU rental should be necessary for this.

## 1. Install

```bash
git clone https://github.com/aalmuzairee/squint.git
cd squint
conda env create -f environment.yaml
conda activate squint
```

## 2. Train in simulation

```bash
python train_squint.py --env_id=SO101LiftCube-v1 --total_timesteps=1_500_000
```

Swap `SO101LiftCube-v1` for whichever of the 8 task IDs you want (e.g.
`SO101ReachCube-v1`, `SO101StackCube-v1` — check the repo for exact IDs).
Checkpoints land wherever the script's run directory defaults to; confirm
with `--help` since Squint is a newer/smaller project and paths may not be
as stable as LeRobot's.

## Wrist camera hardware

Brachiomimus's kit already includes a printed mount for a 32×32mm bare UVC
board camera (`SO101_Wrist_Cam_Hex-Nut_Mount_32x32_UVC_Module` from the
[SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) optional parts —
found unlabeled among the other printed parts, not called out in the
getting-started instructions). That mount wants a bare board camera, not a
housed desktop webcam like the NexiGo N980P used for the side-angle camera
in TELEOPERATION.md — the N980P's case won't fit the snap-clamp.

A good match: an **8MP Sony IMX179 USB board camera, 38mm×38mm** (e.g.
Vetco's VUPN2213), driver-free UVC, autofocus. It's marketed for Pi/Jetson
embedded builds, which is exactly this use case. It's a few mm larger than
the mount's nominal 32×32mm spec, so check the snap-clamp opening/screw hole
tolerance against the board before assuming a perfect fit — but this class
of small square board camera is the right form factor, unlike a housed
webcam.

If a board camera isn't available, fall back to a housed webcam zip-tied or
Velcro'd directly to the wrist link (skip the printed mount) — Squint only
needs an RGB frame from roughly the right viewpoint, not a specific camera
model, so a janky-but-secure mount still works as long as step 3's
calibration accounts for its actual pose.

## 3. Calibrate the real setup (camera + background)

Before deploying, the sim policy needs the real world to visually resemble
the sim it trained in:

- **Camera alignment**: use `deploy_utils/tune_camera.py` to align
  Brachiomimus's real wrist camera pose to match the simulated camera —
  configured in `envs/base_random_env.py`.
- **Background**: capture a plain/greenscreen background image with the
  robot unmounted or moved out of frame, matching the domain-randomization
  setup the policy trained under.

This step is the one place manual tuning actually matters — a mismatched
camera pose or cluttered background is the most common reason a sim-trained
policy fails to transfer.

## 4. Deploy zero-shot on Brachiomimus

```bash
python deploy.py \
    --checkpoint=path/to/ckpt.pt \
    --env_id=SO101LiftCube-v1
```

The repo doesn't document robot-port/ID wiring in the README summary — check
`deploy.py --help` and cross-reference with your `so101_follower` /
`brachiomimus_follower` setup from README.md's Calibration section, since
Squint will need to know which serial port and calibration file to use just
like `lerobot-rollout` does elsewhere in this repo.

## 5. If transfer isn't good enough

Squint's own guidance: get a high success rate in simulation *before*
deploying — if real-world performance lags sim performance a lot, that's
almost always the camera/background calibration in step 3, not the policy
itself. Only fall back to collecting real demonstrations (TRAINING.md) or
fine-tuning (GROOT.md) if pure sim2real genuinely can't hit an acceptable
success rate for your task after calibration is dialed in.
