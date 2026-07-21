"""
motion.py — small pose helpers shared across the arm behaviors.

Both are pure dict math over pose dicts (joint name -> degrees); no hardware.
Extracted here because clamp_step was previously copy-pasted verbatim into
dance.py, track.py and reach.py, and blend into dance.py.
"""


def blend(a: dict, b: dict, t: float) -> dict:
    """Linear interpolation between two poses, componentwise: t=0 -> a, t=1 -> b."""
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def clamp_step(
    current: dict, target: dict, max_step: float, overrides: dict | None = None
) -> dict:
    """Move `current` toward `target`, but no joint by more than `max_step`
    degrees this tick — the per-tick slew limit that keeps motion smooth/safe.

    `overrides` optionally sets a different per-joint limit (e.g. dance.py lets
    the light gripper snap faster than the big joints).
    """
    overrides = overrides or {}
    out = {}
    for k, v in target.items():
        limit = overrides.get(k, max_step)
        delta = max(-limit, min(limit, v - current[k]))
        out[k] = current[k] + delta
    return out
