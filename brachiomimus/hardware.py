"""
hardware.py — the SO-101 follower's motor layer, shared by every behavior.

This is the low-level foundation the demos and tools sit on top of: the six
motor definitions, calibration loading, and the canonical arm poses. It was
originally embedded in wave.py; extracting it here removes the "a demo is the
foundation everything imports" wart — wave/dance/track/reach and the
diagnostics tools all pull their motor config from this one place.

Nothing here moves the arm on its own; callers build a FeetechMotorsBus from
MOTORS + load_calibration() and drive it.
"""

import json
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode

CALIBRATION_PATH = (
    Path.home()
    / ".cache/huggingface/lerobot/calibration/robots/so_follower/brachiomimus_follower.json"
)


def load_calibration(path: Path) -> dict[str, MotorCalibration]:
    with open(path) as f:
        data = json.load(f)
    return {
        name: MotorCalibration(**fields)
        for name, fields in data.items()
    }


# ---------------------------------------------------------------------------
# Motor configuration (SO-101, 6 motors)
# ---------------------------------------------------------------------------
MOTORS = {
    "shoulder_pan":  Motor(id=1, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    "shoulder_lift": Motor(id=2, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    "elbow_flex":    Motor(id=3, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    "wrist_flex":    Motor(id=4, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    "wrist_roll":    Motor(id=5, model="sts3215", norm_mode=MotorNormMode.DEGREES),
    "gripper":       Motor(id=6, model="sts3215", norm_mode=MotorNormMode.DEGREES),
}

# ---------------------------------------------------------------------------
# Canonical poses  (degrees, centred on 0 = neutral)
# ---------------------------------------------------------------------------
# Flat/neutral. NOTE: this lets the arm sag onto the table once torque is
# (re)enabled, so it's a starting point, not a safe shutdown pose.
REST_POSE = {
    "shoulder_pan":  0.0,
    "shoulder_lift": 0.0,
    "elbow_flex":    0.0,
    "wrist_flex":    0.0,
    "wrist_roll":    0.0,
    "gripper":       0.0,
}

# Arm raised and tucked up — a known-safe, self-supporting "ready" configuration
# that several behaviors reuse (wave's raised hand, dance's curl-up, track's
# centered watching pose all build on this).
READY_POSE = {
    "shoulder_pan":   20.0,   # swing arm slightly outward
    "shoulder_lift": -90.0,   # lift shoulder up
    "elbow_flex":     30.0,   # bend elbow so forearm points up
    "wrist_flex":      0.0,
    "wrist_roll":      0.0,
    "gripper":         0.0,
}
