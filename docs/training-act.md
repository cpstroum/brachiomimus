# Training a policy

Train a policy on a dataset recorded in [teleoperation.md](teleoperation.md),
then run it on Brachiomimus.

## Train

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

## Run the trained policy

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

No leader arm needed here — the policy drives Brachiomimus directly from
camera + joint observations.
