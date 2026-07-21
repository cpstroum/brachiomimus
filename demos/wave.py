"""
wave.py — make the SO-101 follower arm do a waving motion.

Usage:
    python -m demos.wave [--port /dev/ttyUSB0] [--reps 3]

The script:
  1. Connects to the arm via its USB serial port
  2. Moves to a raised "wave ready" pose
  3. Rocks the wrist left-right N times
  4. Returns to the rest pose and disables torque

Joint names (SO-101, 6 motors):
  shoulder_pan, shoulder_lift, elbow_flex,
  wrist_flex, wrist_roll, gripper
"""

import argparse
import time

from lerobot.motors.feetech import FeetechMotorsBus

from brachiomimus.hardware import (
    CALIBRATION_PATH,
    MOTORS,
    READY_POSE,
    REST_POSE,
    load_calibration,
)

# Raised "ready" hand, rocked left/right to wave.
WAVE_LEFT = {**READY_POSE, "wrist_roll":  40.0}
WAVE_RIGHT = {**READY_POSE, "wrist_roll": -40.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def move_to(bus: FeetechMotorsBus, pose: dict, duration: float = 1.5) -> None:
    bus.sync_write("Goal_Position", pose)
    time.sleep(duration)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def wave(port: str, reps: int) -> None:
    calibration = load_calibration(CALIBRATION_PATH)
    bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
    bus.connect()

    try:
        bus.sync_write("Torque_Enable", 1)

        print("Moving to rest pose …")
        move_to(bus, REST_POSE, duration=2.0)

        print("Raising arm …")
        move_to(bus, READY_POSE, duration=2.0)

        print(f"Waving {reps} times …")
        for _ in range(reps):
            move_to(bus, WAVE_LEFT,  duration=0.5)
            move_to(bus, WAVE_RIGHT, duration=0.5)

        move_to(bus, READY_POSE, duration=0.5)

        print("Returning to rest …")
        move_to(bus, REST_POSE, duration=2.0)

    finally:
        bus.sync_write("Torque_Enable", 0)
        bus.disconnect()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SO-101 wave demo")
    parser.add_argument(
        "--port", default="/dev/ttyUSB0",
        help="Serial port the arm is connected to (default: /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--reps", type=int, default=3,
        help="Number of wave repetitions (default: 3)"
    )
    args = parser.parse_args()
    wave(args.port, args.reps)
