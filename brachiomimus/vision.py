"""
vision.py — classical OpenCV perception primitives (no ML training).

The shared perception layer the closed-loop demos are built on:

  - face_detector() / largest_face() : Haar-cascade face finding, used by
    track.py to make the arm look at whoever's in the room.
  - find_blob() : HSV color-blob detection, used by reach.py to visually
    servo the wrist camera onto a colored marker.

Both return simple bounding boxes so callers can compute how off-center /
how large the target is and drive the arm accordingly. Needs opencv-python
and numpy (the vision demos' extra dependencies).

NOTE: face_detector() uses the classic cv2.CascadeClassifier API, which
OpenCV 5 removed along with the bundled cascade XML files — run the face
demo on OpenCV 4.x. The blob path has no such constraint.
"""

import cv2
import numpy as np

# Ignore blobs smaller than this many pixels — camera-sensor speckle in the
# color mask, not a real target.
NOISE_FLOOR_PX = 200


def face_detector() -> "cv2.CascadeClassifier":
    """The frontal-face Haar cascade that ships with opencv-python (4.x)."""
    return cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )


def largest_face(gray, detector) -> tuple[int, int, int, int] | None:
    """Return the biggest detected face as (x, y, w, h), or None if none."""
    faces = detector.detectMultiScale(
        gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def find_blob(frame, lower, upper, min_pixels: int = NOISE_FLOOR_PX):
    """Find the largest HSV-thresholded color blob in a BGR frame.

    Returns ((x, y, w, h, area), mask) for the largest blob above min_pixels,
    or (None, mask) if nothing qualifies. `lower`/`upper` are HSV bounds; the
    mask is returned too so callers can show it while tuning thresholds.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < min_pixels:
        return None, mask
    x, y, w, h = cv2.boundingRect(largest)
    return (x, y, w, h, area), mask
