# Fine-tuning GR00T N1.7 on Brachiomimus

[NVIDIA Isaac GR00T](https://github.com/NVIDIA/Isaac-GR00T) N1.7 is a
vision-language-action foundation model. It's zero-shot capable on the
embodiments it was pretrained on (humanoid/bimanual platforms), but
Brachiomimus (SO-101, single 6-DoF arm) isn't one of them — so this is a
**fine-tuning** path, not a drop-in inference path. It's the same idea as
[TRAINING.md](TRAINING.md)'s ACT policy, just with GR00T as the base model
instead of training ACT from scratch.

## Can I reuse my existing episodes?

Yes. A dataset recorded with `lerobot-record` (see
[TELEOPERATION.md](TELEOPERATION.md)) is already close to what GR00T wants —
it expects "GR00T-flavored LeRobot v2" (parquet state/action per timestep +
mp4 videos + episode metadata). You don't need to re-record anything.

What's missing is a `meta/modality.json` file, which GR00T uses and LeRobot's
own recorder doesn't produce. It maps the flat state/action arrays in your
dataset to named joints and declares your camera views. You write this once
per embodiment (i.e. once for Brachiomimus, not once per dataset).

If your existing dataset was recorded with an older LeRobot version (v3
layout), GR00T's repo ships a conversion helper
(`scripts/lerobot_conversion/convert_v3_to_v2.py`) — check your dataset's
`meta/info.json` for a version field if fine-tuning complains about the
schema.

## Compute

Fine-tuning needs **40GB+ VRAM on a single GPU minimum** (A100/H100/L40-class)
even for the default lightweight fine-tune (projector + action head only,
~35GB peak). Full fine-tuning with `--tune-llm`/`--tune-visual` pushes to
80GB+ per GPU. This is well beyond what `act` in TRAINING.md needs — that one
can train locally or on a small GPU; GR00T can't.

Concretely, on Azure this rules out `NCasT4_v3` (T4, 16GB/GPU) — a single T4
can't hold the 3B model plus activations, and stacking multiple T4s doesn't
fix it since the default fine-tune isn't set up to shard across small GPUs
like that. You'd want `NC A100 v4`, `ND A100 v4`, or `NC H100 v5` series
instead (40–80GB/GPU). If your existing HF GPU tier already gets you to
40GB+, that's the lower-friction option since the workflow there is already
proven.

## 1. Set up Isaac-GR00T

```bash
git clone https://github.com/NVIDIA/Isaac-GR00T.git
cd Isaac-GR00T
# follow the repo's own install instructions (conda/uv env, CUDA-matched torch, etc.)
```

This is a separate repo/environment from your `lerobot-*` CLI setup — keep
it alongside, not inside, brachiomimus.

## 2. Write `meta/modality.json` for Brachiomimus

Point this at your recorded dataset directory
(`~/.cache/huggingface/lerobot/{repo_id}/meta/modality.json`). Brachiomimus
is a single 6-motor SO-101 arm with one `front` camera, so treat it as one
`"single_arm"` state/action group of 5 joints plus a separate `"gripper"`
group, matching the joint order used everywhere else in this repo
(`shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper`):

```json
{
  "state": {
    "single_arm": { "start": 0, "end": 5 },
    "gripper": { "start": 5, "end": 6 }
  },
  "action": {
    "single_arm": { "start": 0, "end": 5 },
    "gripper": { "start": 5, "end": 6 }
  },
  "video": {
    "front": { "original_key": "observation.images.front" }
  },
  "annotation": {
    "human.task_description": { "original_key": "task" }
  }
}
```

Use NVIDIA's `examples/SO100/so100_config.py` as the reference — SO-101 is
the same joint layout as SO-100, so start from that config rather than
writing one from scratch.

## 3. Fine-tune

```bash
CUDA_VISIBLE_DEVICES=0 uv run python \
    gr00t/experiment/launch_finetune.py \
    --base-model-path nvidia/GR00T-N1.7-3B \
    --dataset-path ~/.cache/huggingface/lerobot/${HF_USER}/brachiomimus-so101 \
    --embodiment-tag NEW_EMBODIMENT \
    --modality-config-path examples/SO100/so100_config.py \
    --num-gpus 1 \
    --global-batch-size 32 \
    --max-steps 2000
```

Verify these flags against `launch_finetune.py --help` in your checked-out
copy of the repo before running — check exact argument names, they move
between GR00T releases. Checkpoints land under an `--output-dir`-style flag;
confirm the default location from `--help` too.

NVIDIA's own walkthrough fine-tunes on just 5 demo episodes as a smoke test
before scaling up — worth doing the same with a small slice of your dataset
first to confirm the modality config is wired correctly before committing a
long run.

## 4. Evaluate

Open-loop eval against held-out episodes (predicted vs. recorded actions,
no robot needed):

```bash
uv run python gr00t/eval/open_loop_eval.py \
    --checkpoint-path <path-to-finetuned-checkpoint> \
    --dataset-path ~/.cache/huggingface/lerobot/${HF_USER}/brachiomimus-so101
```

## 5. Run on Brachiomimus

For actually driving the arm, the LeRobot CLI exposes GR00T as a policy type
(`--policy.type=groot`), so once you have a fine-tuned checkpoint you should
be able to point `lerobot-rollout` at it the same way TRAINING.md does for
`act`:

```bash
lerobot-rollout \
    --strategy.type=base \
    --policy.type=groot \
    --policy.path=<path-to-finetuned-checkpoint> \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=brachiomimus_follower \
    --robot.cameras="{front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
    --task="Describe the task in a few words" \
    --duration=60
```

Confirm `--policy.type=groot` is available in your installed LeRobot version
(`lerobot-rollout --help`) — GR00T support was added there separately from
the Isaac-GR00T repo itself.
