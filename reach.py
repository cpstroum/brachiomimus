"""
reach.py — visually servo Brachiomimus's wrist camera onto a colored object,
then reach in and grasp it.

Built for the wrist-mounted (eye-in-hand) camera, not the room-facing one
track.py uses. Detects a colored blob (defaults to a lavender-ish purple; use
--hue-min/--hue-max to retarget) and closes the gripper on it. No depth
estimation or inverse kinematics involved - visual servoing instead works
entirely off what the wrist camera sees getting bigger and more centered as
the arm approaches:

  1. SEARCH — no target in view: slowly sweep shoulder_pan until the blob
     appears.
  2. TRACK  — target in view but not close enough yet: center it with
     shoulder_pan (left/right) and wrist_flex (up/down), and extend
     elbow_flex a little each tick while centered but not yet close (blob
     area is the proxy for distance — bigger blob = closer).
  3. GRASP  — blob fills enough of the frame and is centered: close the
     gripper and hold.
  4. LIFT   — raise back to the ready pose so you can see whether the grasp
     actually took.

IMPORTANT — this needs on-arm tuning before it'll do anything sensible:
  - REACH_READY_POSE below is a guess at a pose that points the wrist
    camera down/forward at a workspace. Jog the arm by hand to a good hover
    position over wherever the lavender sits and replace these numbers.
  - The dx/dy -> joint mapping (which joint moves the image left/right vs
    up/down) depends on how the wrist camera is physically mounted and can
    come out inverted or swapped; use --invert-pan/--invert-tilt, same idea
    as track.py.
  - The default HSV range is a rough guess at lavender under generic
    lighting. Run with --show — it opens both the camera view and the
    color mask — and adjust --hue-min/--hue-max/--sat-min/--val-min until
    only the flowers show up white in the mask.
  - There's no force sensing, so "grasp success" isn't verified - watch the
    lift and judge for yourself. Don't leave it unattended.

Usage:
    python reach.py --port /dev/ttyACM0 --camera 1 --show
    python reach.py --dry-run --show          # tune detection, no arm

Requires opencv-python and numpy, same extra dependency as track.py.
"""

import argparse
import math
import time

import cv2
import numpy as np

import config
from wave import CALIBRATION_PATH, MOTORS, load_calibration
from lerobot.motors.feetech import FeetechMotorsBus

# Arm pose that points the wrist camera down/forward at the workspace in
# front of the base, gripper open. THIS IS A GUESS - jog the arm by hand to
# a good hover position over your workspace and replace these numbers.
REACH_READY_POSE = {
    "shoulder_pan": 0.0,
    "shoulder_lift": -45.0,
    "elbow_flex": 60.0,
    "wrist_flex": -30.0,
    "wrist_roll": 0.0,
    "gripper": 0.0,  # overwritten each tick with the real open/closed angle
}

PAN_JOINT = "shoulder_pan"
TILT_JOINT = "wrist_flex"
ADVANCE_JOINT = "elbow_flex"
GRIPPER_JOINT = "gripper"

MAX_STEP_DEG = 4.0       # slower than track.py's 6 - this is reaching, not just looking
ADVANCE_STEP_DEG = 2.5   # how far elbow_flex extends per tick while approaching
CENTER_TOLERANCE = 0.15  # blob center must be within this fraction of frame center...
CLOSE_AREA_FRACTION = 0.18  # ...and blob must cover this fraction of the frame...
                             # ...before GRASP triggers
NOISE_FLOOR_PX = 200     # ignore blobs smaller than this (fixed, unlike --min-area)

LOST_TIMEOUT_S = 1.5
SEARCH_PERIOD_S = 8.0
SEARCH_SWEEP_LIMIT_DEG = 40.0

GRASP_HOLD_S = 0.6


def clamp_step(current: dict, target: dict, max_step: float) -> dict:
    out = {}
    for k, v in target.items():
        delta = max(-max_step, min(max_step, v - current[k]))
        out[k] = current[k] + delta
    return out


def find_blob(frame, hue_min, hue_max, sat_min, val_min):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (hue_min, sat_min, val_min), (hue_max, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < NOISE_FLOOR_PX:
        return None, mask
    x, y, w, h = cv2.boundingRect(largest)
    return (x, y, w, h, area), mask


def run(
    port: str,
    camera: int,
    dry_run: bool,
    show: bool,
    hue_min: int,
    hue_max: int,
    sat_min: int,
    val_min: int,
    min_area_fraction: float,
    invert_pan: bool,
    invert_tilt: bool,
    gripper_closed: float,
    gripper_open_deg: float,
    repeat: bool,
) -> None:
    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {camera}")

    bus = None
    if not dry_run:
        calibration = load_calibration(CALIBRATION_PATH)
        bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
        bus.connect()
        bus.sync_write("Torque_Enable", 1)

    current_pose = {**REACH_READY_POSE, GRIPPER_JOINT: gripper_open_deg}
    state = "search"
    last_seen = time.monotonic()
    search_start = time.monotonic()
    grasp_start = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame read failed, stopping.")
                break

            fh, fw = frame.shape[:2]
            blob, mask = find_blob(frame, hue_min, hue_max, sat_min, val_min)
            now = time.monotonic()

            if blob is not None:
                last_seen = now
                x, y, w, h, area = blob
                if show:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                if state == "search":
                    state = "track"
            elif state == "track" and now - last_seen > LOST_TIMEOUT_S:
                print("Lost the target, searching again…")
                state = "search"
                search_start = now

            target = dict(current_pose)

            if state == "search":
                offset = SEARCH_SWEEP_LIMIT_DEG * math.sin(2 * math.pi * (now - search_start) / SEARCH_PERIOD_S)
                target[PAN_JOINT] = REACH_READY_POSE[PAN_JOINT] + offset
                target[TILT_JOINT] = REACH_READY_POSE[TILT_JOINT]
                target[ADVANCE_JOINT] = REACH_READY_POSE[ADVANCE_JOINT]
                target[GRIPPER_JOINT] = gripper_open_deg

            elif state == "track":
                x, y, w, h, area = blob
                cx, cy = x + w / 2, y + h / 2
                dx = (cx - fw / 2) / (fw / 2)
                dy = (cy - fh / 2) / (fh / 2)
                if invert_pan:
                    dx = -dx
                if invert_tilt:
                    dy = -dy
                area_fraction = area / (fw * fh)

                target[PAN_JOINT] = current_pose[PAN_JOINT] - dx * MAX_STEP_DEG * 2
                target[TILT_JOINT] = current_pose[TILT_JOINT] - dy * MAX_STEP_DEG * 2
                target[GRIPPER_JOINT] = gripper_open_deg

                centered = abs(dx) < CENTER_TOLERANCE and abs(dy) < CENTER_TOLERANCE
                if area_fraction >= min_area_fraction and centered:
                    state = "grasp"
                    grasp_start = now
                elif centered:
                    target[ADVANCE_JOINT] = current_pose[ADVANCE_JOINT] + ADVANCE_STEP_DEG

            elif state == "grasp":
                target[GRIPPER_JOINT] = gripper_closed
                if grasp_start and now - grasp_start > GRASP_HOLD_S:
                    state = "lift"

            elif state == "lift":
                target = {**REACH_READY_POSE, GRIPPER_JOINT: gripper_closed}
                if all(abs(current_pose[k] - target[k]) < 1.0 for k in target):
                    if repeat:
                        print("Lifted. Searching for next target…")
                        state = "search"
                        search_start = now
                    else:
                        print("Lifted. Done.")
                        break

            current_pose = clamp_step(current_pose, target, MAX_STEP_DEG)

            if dry_run:
                print(state, {k: round(v, 1) for k, v in current_pose.items()})
            else:
                bus.sync_write("Goal_Position", current_pose)

            if show:
                cv2.putText(frame, state, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("reach.py", frame)
                cv2.imshow("reach.py mask", mask)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(0.03)
    except KeyboardInterrupt:
        print("Stopping…")
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()
        if bus is not None:
            pose = current_pose
            for _ in range(25):
                pose = clamp_step(pose, {**REACH_READY_POSE, GRIPPER_JOINT: gripper_closed}, MAX_STEP_DEG)
                bus.sync_write("Goal_Position", pose)
                time.sleep(0.05)
            bus.sync_write("Torque_Enable", 0)
            bus.disconnect()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visually servo Brachiomimus onto a colored object and grasp it")
    parser.add_argument("--port", default=config.PORT, help=f"Serial port the arm is connected to (default: {config.PORT})")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV index of the WRIST camera (default: 0)")
    parser.add_argument("--dry-run", action="store_true", help="Print computed poses instead of sending them to the arm")
    parser.add_argument("--show", action="store_true", help="Open debug windows: camera view with the detected blob boxed, and the color mask")
    parser.add_argument("--hue-min", type=int, default=125, help="HSV hue lower bound, 0-179 (default: 125, roughly lavender)")
    parser.add_argument("--hue-max", type=int, default=155, help="HSV hue upper bound, 0-179 (default: 155)")
    parser.add_argument("--sat-min", type=int, default=40, help="HSV saturation lower bound, 0-255 (default: 40)")
    parser.add_argument("--val-min", type=int, default=60, help="HSV value/brightness lower bound, 0-255 (default: 60)")
    parser.add_argument("--min-area", type=float, default=CLOSE_AREA_FRACTION, help=f"Fraction of frame the blob must fill before grasping (default: {CLOSE_AREA_FRACTION})")
    parser.add_argument("--invert-pan", action="store_true", help="Flip left/right centering direction (wrist camera mount dependent)")
    parser.add_argument("--invert-tilt", action="store_true", help="Flip up/down centering direction (wrist camera mount dependent)")
    parser.add_argument("--gripper-closed", type=float, default=config.GRIPPER_CLOSED_DEG, help="Gripper angle that is FULLY CLOSED on your arm - see --read-gripper in dance.py")
    parser.add_argument("--gripper-open", type=float, default=config.GRIPPER_OPEN_DEG, help="Gripper angle that is fully open")
    parser.add_argument("--repeat", action="store_true", help="After lifting, go back to SEARCH instead of exiting")
    args = parser.parse_args()
    run(
        args.port, args.camera, args.dry_run, args.show,
        args.hue_min, args.hue_max, args.sat_min, args.val_min,
        args.min_area, args.invert_pan, args.invert_tilt,
        args.gripper_closed, args.gripper_open, args.repeat,
    )
