# Sim2real vs. real-episode training: a comparison

Two ways to get a working policy on Brachiomimus, run side by side to see
which is actually worth the effort for this hardware:

- **Sim2real** ([SIM2REAL.md](SIM2REAL.md)) — train in simulation, deploy
  zero-shot, no real episodes, but requires wrist camera hardware +
  calibration.
- **Real training** ([TRAINING.md](TRAINING.md)) — record real demos with
  the existing side-angle camera, train ACT from scratch, no sim tooling.

Pick a comparable task for both (e.g. lift/grasp a cube) so the comparison
means something.

## Setup time

| | Sim2real | Real training |
|---|---|---|
| Time to first working attempt | | |
| One-time setup (mount, camera calibration, ManiSkill/Squint install) | | |
| Per-run overhead (recording episodes vs. re-running eval) | | |

## Task performance

| | Sim2real | Real training |
|---|---|---|
| Task | | |
| Episodes/timesteps used | | |
| Success rate (n attempts) | | |
| Failure modes observed | | |

## Friction log

Freeform notes on what actually slowed things down — camera calibration
mismatch, teleop demo quality, sim-to-real visual gap, training compute
wait, etc. This is the part that'll actually decide which approach is worth
it going forward.

-
