"""
probe_color.py — click on the camera feed to read the HSV value under the
cursor, so you can set reach.py's --hue-min/--hue-max/--sat-min/--val-min
from real pixels instead of guessing.

Colour-based detection lives or dies on knowing what H/S/V your target
actually produces under *your* camera and lighting - especially for a muted
target (dried flowers) under a colour cast, where the values are nowhere
near the "textbook" hue. Click the target a few times, read off the numbers,
and pick ranges that bracket them.

Standalone: no arm, no LeRobot, just OpenCV + numpy.

Usage:
    python probe_color.py --camera 3

Click anywhere in the window to print the average HSV over a small patch at
that spot (and the min/max across the patch, so you can see the spread).
Click several points on the target, plus a few on the background you want to
exclude, then choose:
    --hue-min / --hue-max  to bracket the target's H but miss the background's
    --sat-min              just below the target's lowest S
    --val-min              just below the target's lowest V
Press q to quit.
"""

import argparse

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Click to sample HSV from a camera feed")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default: 0)")
    parser.add_argument(
        "--patch", type=int, default=5,
        help="Half-size in px of the averaging patch, so 5 -> 11x11 (default: 5)"
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {args.camera}")

    param = {"frame": None, "pt": None}

    def on_click(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN or param["frame"] is None:
            return
        frame = param["frame"]
        h, w = frame.shape[:2]
        r = args.patch
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV).reshape(-1, 3)
        mean = hsv.mean(axis=0)
        lo = hsv.min(axis=0)
        hi = hsv.max(axis=0)
        print(
            f"({x:>3},{y:>3})  mean H={mean[0]:3.0f} S={mean[1]:3.0f} V={mean[2]:3.0f}   "
            f"spread H[{lo[0]}-{hi[0]}] S[{lo[1]}-{hi[1]}] V[{lo[2]}-{hi[2]}]"
        )
        param["pt"] = (x, y)

    cv2.namedWindow("probe_color")
    cv2.setMouseCallback("probe_color", on_click, param)

    print("Click the target to sample HSV. Press q to quit.")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Camera frame read failed, stopping.")
            break
        param["frame"] = frame
        if param["pt"]:
            cv2.drawMarker(frame, param["pt"], (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
        cv2.imshow("probe_color", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
