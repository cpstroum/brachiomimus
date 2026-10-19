"""
wave.py — make the SO-101 follower arm do a waving motion.

Usage:
    python -m demos.wave [--port COM4] [--reps 3]

The script:
  1. Connects to the arm via its USB serial port
  2. Moves to a raised "wave ready" pose
  3. Rocks the wrist left-right N times
  4. Returns to that same raised pose and disables torque

Joint names (SO-101, 6 motors):
  shoulder_pan, shoulder_lift, elbow_flex,
  wrist_flex, wrist_roll, gripper
"""

import argparse
import time

from lerobot.motors.feetech import FeetechMotorsBus

from brachiomimus import config
from brachiomimus.hardware import (
    CALIBRATION_PATH,
    MOTORS,
    READY_POSE,
    load_calibration,
)

# Start/finish on the raised, tucked-up READY_POSE rather than the flat
# REST_POSE: REST_POSE (all zeros) lets the arm sag onto the table once torque
# is re-enabled, so it is not a safe pose to leave the arm in. This matches
# what dance.py ramps to on shutdown (its CURL_POSE).
#
# Raised "ready" hand, rocked left/right to wave.
WAVE_LEFT = {**READY_POSE, "wrist_roll":  40.0}
WAVE_RIGHT = {**READY_POSE, "wrist_roll": -40.0}

GRIPPER_JOINT = "gripper"
# The gripper's calibrated zero is not necessarily closed, so the closed angle
# is per-arm and overridable with --gripper-closed. Find yours with
# `python -m demos.dance --read-gripper`.
GRIPPER_CLOSED_DEG = config.GRIPPER_CLOSED_DEG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def move_to(bus: FeetechMotorsBus, pose: dict, duration: float = 1.5) -> None:
    bus.sync_write("Goal_Position", pose)
    time.sleep(duration)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def wave(port: str, reps: int, gripper_closed: float = GRIPPER_CLOSED_DEG) -> None:
    calibration = load_calibration(CALIBRATION_PATH)
    bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
    bus.connect()

    try:
        bus.sync_write("Torque_Enable", 1)

        print("Raising arm …")
        move_to(bus, READY_POSE, duration=2.0)

        print(f"Waving {reps} times …")
        for _ in range(reps):
            move_to(bus, WAVE_LEFT,  duration=0.5)
            move_to(bus, WAVE_RIGHT, duration=0.5)

        # Finish curled up with the pincer closed (not the pose's default 0,
        # which may be open on this arm) — same exit pose as dance.py.
        print("Returning to the raised rest pose …")
        move_to(bus, {**READY_POSE, GRIPPER_JOINT: gripper_closed}, duration=1.0)

    finally:
        bus.sync_write("Torque_Enable", 0)
        bus.disconnect()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SO-101 wave demo")
    parser.add_argument(
        "--port", default=config.PORT,
        help=f"Serial port the arm is connected to (default: {config.PORT})"
    )
    parser.add_argument(
        "--reps", type=int, default=3,
        help="Number of wave repetitions (default: 3)"
    )
    parser.add_argument(
        "--gripper-closed", type=float, default=GRIPPER_CLOSED_DEG,
        help=f"Gripper angle that is FULLY CLOSED on your arm (default: "
             f"{GRIPPER_CLOSED_DEG}), used for the pose the arm is left in. "
             f"If the pincer never closes, this is wrong for your "
             f"calibration - find it with `python -m demos.dance "
             f"--read-gripper`."
    )
    args = parser.parse_args()
    wave(args.port, args.reps, args.gripper_closed)
