"""
track.py — make Brachiomimus turn and "look" toward whoever is in view.

Points a webcam at the room (it doesn't need to be mounted on the arm — any
camera pointed at the space works) and uses OpenCV's built-in face detector
to find the largest face each frame. Brachiomimus turns to face it:
shoulder_pan tracks left/right, wrist_flex tracks up/down. No ML training or
eye-in-hand calibration needed - just the Haar cascade that ships with
opencv-python.

When a face first appears, the gripper gives a quick friendly pulse. When no
face is in view, the arm eases back to a centered "watching" pose instead of
snapping.

Usage:
    python -m demos.track --port /dev/ttyACM0
    python -m demos.track --port COM4 --show          # debug window with face box
    python -m demos.track --dry-run --show             # no arm, just watch detection

Requires opencv-python (`pip install opencv-python`), not otherwise a
dependency of this repo.
"""

import argparse
import time

import cv2

from lerobot.motors.feetech import FeetechMotorsBus

from brachiomimus import config
from brachiomimus.hardware import CALIBRATION_PATH, MOTORS, READY_POSE, load_calibration
from brachiomimus.motion import clamp_step
from brachiomimus.vision import face_detector, largest_face

# Centered version of the raised "ready" pose - arm up and alert, facing
# forward, rather than angled out for a wave.
TRACK_READY_POSE = {**READY_POSE, "shoulder_pan": 0.0}

PAN_JOINT = "shoulder_pan"
TILT_JOINT = "wrist_flex"
GRIPPER_JOINT = "gripper"

MAX_STEP_DEG = 6.0  # per-tick slew limit, matches dance.py's feel
LOST_TIMEOUT_S = 1.0  # stop chasing a face this long after losing it

GREET_PULSE_S = 0.4  # how long the gripper stays open on first sighting
GREET_OPEN_DEG = 20.0


def run(
    port: str,
    camera: int,
    dry_run: bool,
    show: bool,
    pan_range: float,
    tilt_range: float,
    invert_pan: bool,
    invert_tilt: bool,
) -> None:
    detector = face_detector()
    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {camera}")

    bus = None
    if not dry_run:
        calibration = load_calibration(CALIBRATION_PATH)
        bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
        bus.connect()
        bus.sync_write("Torque_Enable", 1)

    current_pose = dict(TRACK_READY_POSE)
    last_seen = 0.0
    greet_until = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame read failed, stopping.")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face = largest_face(gray, detector)

            target = dict(TRACK_READY_POSE)
            now = time.monotonic()

            if face is not None:
                if now - last_seen > LOST_TIMEOUT_S:
                    greet_until = now + GREET_PULSE_S
                last_seen = now

                x, y, w, h = face
                fh, fw = gray.shape
                cx, cy = x + w / 2, y + h / 2
                dx = (cx - fw / 2) / (fw / 2)  # -1 (left) .. 1 (right)
                dy = (cy - fh / 2) / (fh / 2)  # -1 (up) .. 1 (down)
                if invert_pan:
                    dx = -dx
                if invert_tilt:
                    dy = -dy

                target[PAN_JOINT] += pan_range * dx
                target[TILT_JOINT] += tilt_range * dy

                if show:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            target[GRIPPER_JOINT] = GREET_OPEN_DEG if now < greet_until else 0.0

            current_pose = clamp_step(current_pose, target, MAX_STEP_DEG)

            if dry_run:
                print({k: round(v, 1) for k, v in current_pose.items()})
            else:
                bus.sync_write("Goal_Position", current_pose)

            if show:
                cv2.imshow("track.py", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("Stopping, returning to rest…")
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()
        if bus is not None:
            pose = current_pose
            for _ in range(20):
                pose = clamp_step(pose, TRACK_READY_POSE, MAX_STEP_DEG)
                bus.sync_write("Goal_Position", pose)
                time.sleep(0.05)
            bus.sync_write("Torque_Enable", 0)
            bus.disconnect()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Make Brachiomimus track faces with a webcam")
    parser.add_argument(
        "--port", default=config.PORT,
        help=f"Serial port the arm is connected to (default: {config.PORT})"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="OpenCV camera index to read from (default: 0)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print computed poses instead of sending them to the arm"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Open a debug window showing the camera feed with the detected face boxed"
    )
    parser.add_argument(
        "--pan-range", type=float, default=45.0,
        help="Max shoulder_pan degrees off-center when a face is at the frame edge (default: 45)"
    )
    parser.add_argument(
        "--tilt-range", type=float, default=20.0,
        help="Max wrist_flex degrees off-center when a face is at the frame edge (default: 20)"
    )
    parser.add_argument(
        "--invert-pan", action="store_true",
        help="Flip left/right tracking direction (camera orientation dependent)"
    )
    parser.add_argument(
        "--invert-tilt", action="store_true",
        help="Flip up/down tracking direction (camera orientation dependent)"
    )
    args = parser.parse_args()
    run(
        args.port, args.camera, args.dry_run, args.show,
        args.pan_range, args.tilt_range, args.invert_pan, args.invert_tilt,
    )
