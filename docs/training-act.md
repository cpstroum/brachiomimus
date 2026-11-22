# Training an ACT policy

Train an [ACT](../README.md#the-spectrum-of-experiments) policy (rung 1) on a
dataset recorded in [teleoperation.md](teleoperation.md), then run it on
Brachiomimus.

I train on **Hugging Face Jobs** (a cloud GPU) instead of locally. The SO-101
dataset trains faster on a rented A10G than on my laptop, and the trained policy
lands straight on the Hub. There's a local option at the end.

## Authentication (keys live in `.env`)

No API keys go in the command. They're read from your gitignored `.env`
(copied from [`.env.example`](../.env.example)), so nothing sensitive ends up in
your notes or shell history:

- **Weights & Biases:** put your key in `.env` as `WANDB_API_KEY=...` (get it
  from <https://wandb.ai/authorize>). The Job reads it via `--secrets-file .env`,
  which encrypts the values server-side. **Always enable W&B.** The loss curve
  is how you tell a good run from a bad one, and these runs are too slow to
  judge blind.
- **Hugging Face:** log in once with `huggingface-cli login`. The Job pulls your
  token via `--secrets HF_TOKEN` without it appearing in the command. (Only add
  `HF_TOKEN=...` to `.env` if you need to pass one explicitly.)

`--secrets-file .env` sends every key in the file to the Job as an encrypted
secret; the non-secret `BRACHIOMIMUS_*` lines just go unused there. Run the
command from the repo root so it finds `.env`.

## Train on HF Jobs

```powershell
hf jobs run `
  --flavor a10g-small `
  --timeout 6h `
  --secrets HF_TOKEN `
  --secrets-file .env `
  huggingface/lerobot-gpu:latest `
  -- `
  python -m lerobot.scripts.lerobot_train `
    --dataset.repo_id=cpstroum/so101-brachiomimus-50ep `
    --dataset.revision=main `
    --policy.type=act `
    --steps=30000 `
    --batch_size=16 `
    --policy.device=cuda `
    --save_freq=5000 `
    --wandb.enable=true `
    --wandb.project=so101-brachiomimus `
    --policy.repo_id=cpstroum/so101-brachiomimus-block-movement-v2 `
    --policy.push_to_hub=true `
    --log_freq=100
```

The flags I changed between runs (more in
[learnings](learnings.md#rung-1-training-act-on-hf-jobs)):

- `--flavor a10g-small`: the GPU. A `t4-small` **timed out** on 30k steps once
  data loading and environment setup used up part of the clock. `a10g-small`
  with a `6h` timeout finishes with room to spare.
- `--steps=30000`: at 5k steps the policy twitched in place and failed eval.
  About 30k (6×) worked.
- `--wandb.enable=true --wandb.project=so101-brachiomimus`: always on.
- `--policy.push_to_hub=true`: publishes the trained policy to
  `--policy.repo_id` on the Hub, so eval can pull it by name (below).
- `--save_freq=5000`: saves a checkpoint every 5k steps so a timeout doesn't
  lose everything.

**Local option** (single GPU, slower):
```bash
lerobot-train \
    --dataset.repo_id=cpstroum/so101-brachiomimus-50ep \
    --policy.type=act \
    --steps=30000 \
    --batch_size=16 \
    --policy.device=cuda \
    --wandb.enable=true \
    --wandb.project=so101-brachiomimus \
    --output_dir=outputs/train/act_brachiomimus
```
Use `--policy.device=mps` on Apple Silicon, or `cpu` if you have no GPU (much
slower). Checkpoints land under `outputs/train/act_brachiomimus/checkpoints/`.

## Evaluate

I evaluate by **recording rollouts with the policy driving**: `lerobot-record`
with `--policy.path` pointing at the trained policy on the Hub (not
`lerobot-rollout`):

```powershell
lerobot-record `
  --robot.type=so101_follower `
  --robot.port=COM4 `
  --robot.id=brachiomimus_follower `
  --robot.cameras="{ front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}}" `
  --teleop.type=so101_leader `
  --teleop.port=COM7 `
  --teleop.id=brachio_rex_leader `
  --display_data=true `
  --dataset.repo_id=cpstroum/eval_so101_block_movement-v2 `
  --dataset.single_task="Pick up the yellow block and put it in the blue box" `
  --dataset.num_episodes=10 `
  --policy.path=cpstroum/so101-brachiomimus-block-movement-v2
```

- `--policy.path` pulls the trained policy from the Hub by repo id and lets it
  drive the arm from the camera and joint observations.
- Keeping the leader connected (`--teleop.*`) lets you take over or reset
  between the 10 eval episodes. Drop those lines for hands-off eval.
- Use the **same** `--dataset.single_task` string the policy was trained on.
- Keep eval-dataset and policy versions matched (`...-v2` eval for the `-v2`
  policy) so you can tell which checkpoint each recording tested.

If the result isn't good, record more or cleaner demonstrations
([teleoperation.md](teleoperation.md)), raise the step count, and retrain. For
what comes after ACT (language-conditioned, multi-task), see [vla.md](vla.md).
