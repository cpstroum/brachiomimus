# Rung 2: VLA (language-conditioned policies)

> Status: **planned, not built yet.** This is where I'm headed after ACT
> (rung 1). See the [spectrum of experiments](../README.md#the-spectrum-of-experiments)
> for how the rungs fit together.

## The idea: language before sim2real

Right now the arm is trained to move a block. I want to be able to *ask* it to
"stack the blocks" or "put the block in the bowl": follow a **language
instruction**, and handle new tasks, not just new positions within one task.

That takes a different kind of model than ACT. It does **not** need simulation
or sim2real transfer. I already have a working real-world pipeline
(teleoperate → record → train), and a pretrained **VLA (vision-language-action)**
model reuses all of it. Sim2real is useful later, for scaling data or for skills
that aren't safe to teleoperate, but it isn't the next step.

## Where the pieces fit

- **ACT** (rung 1) is trained from scratch with **no** language model inside.
  It learns the mapping from what it sees to how it moves, from my demos. It can
  handle new object *positions*, but not new instructions or tasks. It can't
  "stack the blocks" unless I demonstrated stacking.
- **VLA** is a *category* of policy: a pretrained vision-language model with an
  action head attached, so it already understands language and images before
  it ever sees my robot. Fine-tuning one on my LeRobot-format demos should give
  instruction-following across tasks and better handling of new objects and
  scenes.
- Specific VLAs are options within that category:

| Model | Who | Fit for SO-101 / single GPU | Note |
|-------|-----|------------------------------|------|
| **SmolVLA** | HuggingFace / LeRobot | Best first step | ~450M, built for cheap arms and community SO-10x datasets; uses the same `lerobot-train` CLI as ACT (`--policy.type=smolvla`) |
| **π0 / openpi** | Physical Intelligence | Heavier | Flow-matching VLA on a PaliGemma backbone |
| **GR00T N1.5** | NVIDIA | Heavier | Two parts: a VLM for reasoning plus a fast diffusion action head; built for humanoids, works on arms |
| **MolmoAct** | Ai2 | Heavier | Writes out explicit spatial reasoning before it acts; open weights and data |

## What a VLA does and doesn't get me

**Does:** understands words like "block," "bowl," and "stack"; one policy for
many instructions; better at new positions, distractors, and some new objects.

**Doesn't (with hobby-sized datasets):** reliably do a skill it has never seen
demonstrated in any form. I still need demonstrations of stacking and of
putting things in the bowl. The VLA can mix and extend those to new
arrangements; ACT would need a separate policy per task and still wouldn't
follow the prompt.

## Next step

Start with **SmolVLA**, since it's the smallest change from my current ACT
workflow, and see whether it follows instructions before trying π0, GR00T, or
MolmoAct.

Most of the work before any training run is **designing the dataset**: pick 2
or 3 tasks with language labels (e.g. move the block, stack, put in bowl),
decide how much to vary the objects and positions, and make sure every episode
is labeled with its instruction. Then measure instruction-following and
handling of new positions separately.
