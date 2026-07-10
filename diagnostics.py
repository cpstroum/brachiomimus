"""
diagnostics.py — tuning and calibration helpers, kept out of the core dancer.

Neither of these makes the arm dance; they're the tools you reach for while
setting dance.py up:

  - monitor()      : listen and print detected beats + a live BPM estimate,
                     no arm involved, so you can dial in --sensitivity against
                     any source (including loopback while YouTube plays)
  - read_gripper() : release the gripper and print its live angle so you can
                     read off your arm's closed/open values

Run via dance.py's --monitor / --read-gripper flags.
"""

import collections
import time

from analysis import (
    BLOCK_SIZE,
    SAMPLE_RATE,
    TICK_HZ,
    BeatDetector,
    bass_energy,
    estimate_bpm,
)
from audio_source import create_source
from lerobot.motors.feetech import FeetechMotorsBus
from wave import CALIBRATION_PATH, MOTORS, load_calibration

GRIPPER_JOINT = "gripper"


def monitor(audio_source_kind: str, file_path: str | None, sensitivity: float) -> None:
    """Beats-only tuning mode: no arm, prints each detected beat with a live
    BPM estimate. Drains every audio block per tick (same as the dance loop)
    and times beats off an audio-sample clock so the BPM is jitter-free."""
    source = create_source(audio_source_kind, SAMPLE_RATE, BLOCK_SIZE, file_path)
    source.start()

    beat = BeatDetector(block_seconds=BLOCK_SIZE / SAMPLE_RATE, sensitivity=sensitivity)
    beat_times: collections.deque[float] = collections.deque(maxlen=8)
    block_seconds = BLOCK_SIZE / SAMPLE_RATE
    audio_time = 0.0
    tick_period = 1.0 / TICK_HZ

    print(f"Monitor mode (--sensitivity {sensitivity}): listening for beats, "
          "no arm. Ctrl+C to stop.")
    try:
        while True:
            loop_start = time.monotonic()
            block = source.get_block(timeout=tick_period)
            while block is not None:
                audio_time += block_seconds
                if beat.update(bass_energy(block, SAMPLE_RATE), audio_time):
                    beat_times.append(audio_time)
                    bpm = estimate_bpm(beat_times)
                    print(f"beat  ({bpm:.0f} BPM)" if bpm else "beat")
                block = source.get_block(timeout=0.0)
            time.sleep(max(0.0, tick_period - (time.monotonic() - loop_start)))
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        source.stop()


def read_gripper(port: str) -> None:
    """Release the gripper (holding the rest of the arm still) and print its
    live angle, so you can hand-move it to fully closed and fully open and read
    off the two numbers to pass to --gripper-closed / --gripper-open.

    Needed because the gripper's calibrated zero isn't necessarily its closed
    position - on some arms 0 deg is fully open."""
    calibration = load_calibration(CALIBRATION_PATH)
    bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
    bus.connect()
    try:
        # Hold the arm wherever it is now, then free only the gripper.
        present = bus.sync_read("Present_Position")
        bus.sync_write("Goal_Position", present)
        bus.sync_write("Torque_Enable", 1)
        bus.sync_write("Torque_Enable", {GRIPPER_JOINT: 0})
        print("Gripper released. Squeeze it fully CLOSED, read the angle; then")
        print("fully OPEN, read that angle. Pass them to --gripper-closed /")
        print("--gripper-open. Ctrl+C when done.")
        while True:
            pos = bus.sync_read("Present_Position")
            print(f"  gripper: {pos[GRIPPER_JOINT]:7.1f} deg   ", end="\r", flush=True)
            time.sleep(0.15)
    except KeyboardInterrupt:
        print()
    finally:
        bus.sync_write("Torque_Enable", 0)
        bus.disconnect()
        print("Done.")
