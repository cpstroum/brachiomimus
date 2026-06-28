"""
wave.py — make the SO-101 follower arm do a waving motion.

Usage:
    python wave.py [--port /dev/ttyUSB0] [--reps 3]

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


# ---------------------------------------------------------------------------
# Motor configuration
# ---------------------------------------------------------------------------
MOTORS = {
    "shoulder_pan":  (1, "sts3215"),
    "shoulder_lift": (2, "sts3215"),
    "elbow_flex":    (3, "sts3215"),
    "wrist_flex":    (4, "sts3215"),
    "wrist_roll":    (5, "sts3215"),
    "gripper":       (6, "sts3215"),
}

# ---------------------------------------------------------------------------
# Poses  (values in degrees, centred on 0 = neutral)
# ---------------------------------------------------------------------------
REST_POSE = {
    "shoulder_pan":  0.0,
    "shoulder_lift": 0.0,
    "elbow_flex":    0.0,
    "wrist_flex":    0.0,
    "wrist_roll":    0.0,
    "gripper":       0.0,
}

# Arm raised and angled out so it looks like a raised hand
WAVE_READY_POSE = {
    "shoulder_pan":   20.0,   # swing arm slightly outward
    "shoulder_lift":  90.0,   # lift shoulder up
    "elbow_flex":    -30.0,   # bend elbow so forearm points up
    "wrist_flex":      0.0,
    "wrist_roll":      0.0,
    "gripper":         0.0,
}

WAVE_LEFT = {**WAVE_READY_POSE, "wrist_roll":  40.0}
WAVE_RIGHT = {**WAVE_READY_POSE, "wrist_roll": -40.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pose_to_list(bus: FeetechMotorsBus, pose: dict) -> list[float]:
    """Return pose values in motor-index order."""
    return [pose[name] for name in bus.motors]


def move_to(bus: FeetechMotorsBus, pose: dict, duration: float = 1.5) -> None:
    """
    Command all joints to the target pose and wait for `duration` seconds.
    FeetechMotorsBus.write() expects values in the same order as bus.motors.
    """
    values = pose_to_list(bus, pose)
    bus.write("Goal_Position", values)
    time.sleep(duration)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def wave(port: str, reps: int) -> None:
    bus = FeetechMotorsBus(port=port, motors=MOTORS)
    bus.connect()

    try:
        # Enable torque on all motors
        bus.write("Torque_Enable", [1] * len(MOTORS))

        print("Moving to rest pose …")
        move_to(bus, REST_POSE, duration=2.0)

        print("Raising arm …")
        move_to(bus, WAVE_READY_POSE, duration=2.0)

        print(f"Waving {reps} times …")
        for _ in range(reps):
            move_to(bus, WAVE_LEFT,  duration=0.5)
            move_to(bus, WAVE_RIGHT, duration=0.5)

        # End neutral within the raised pose, then lower
        move_to(bus, WAVE_READY_POSE, duration=0.5)

        print("Returning to rest …")
        move_to(bus, REST_POSE, duration=2.0)

    finally:
        bus.write("Torque_Enable", [0] * len(MOTORS))
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
