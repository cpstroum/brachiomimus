"""
dance.py — make Brachiomimus move to music.

Two audio features drive the arm, computed live every tick:
  - loudness (smoothed RMS envelope over the whole signal) -> how big the
    raise/sway/twist/pincer motions are
  - beat (onset detector watching just the bass band, ~20-150Hz) -> the pincer
    opens/closes on every beat while the body sways and twists at half-time,
    each ramping smoothly toward its new target - so it dances *on* the beat
    rather than twitching.

The audio DSP lives in analysis.py; the tuning/calibration helpers behind
--monitor and --read-gripper live in diagnostics.py; per-arm settings (gripper
calibration, default port) come from config.py / a .env file. This module is
the core dance loop.

Usage:
    python dance.py --port COM4 --audio-source loopback
    python dance.py --port /dev/ttyUSB0 --audio-source mic
    python dance.py --port COM4 --audio-source file --file song.wav
    python dance.py --monitor --audio-source loopback   # tune, no arm
    python dance.py --port COM4 --read-gripper           # find gripper angles

See MUSIC.md for setup, source selection, and tuning notes.
"""

import argparse
import collections
import time

import config
from analysis import (
    BLOCK_SIZE,
    SAMPLE_RATE,
    TICK_HZ,
    BeatDetector,
    EnvelopeFollower,
    bass_energy,
    estimate_bpm,
)
from audio_source import create_source
from diagnostics import monitor, read_gripper
from lerobot.motors.feetech import FeetechMotorsBus
from wave import CALIBRATION_PATH, MOTORS, REST_POSE, WAVE_READY_POSE, load_calibration

# On shutdown, ramp to this raised/curled pose instead of REST_POSE - REST_POSE
# is flat (all zeros) and lets the arm sag/collapse onto the table once torque
# is enabled again; WAVE_READY_POSE is the same tucked-up raised pose wave.py
# already uses and is known to be a safe, calibrated resting configuration.
CURL_POSE = WAVE_READY_POSE

MAX_STEP_DEG = 6.0  # per-tick slew limit keeps the big joints smooth/safe
# The gripper is light and should snap open/closed so the pincer reads as a
# clench even on fast songs, where the global slew limit is too slow to
# traverse the full range before the next beat flips it.
GRIPPER_MAX_STEP_DEG = 20.0

# Arm raised, similar in spirit to wave.py's WAVE_READY_POSE
DANCE_POSE = {
    "shoulder_pan": 0.0,
    "shoulder_lift": -60.0,
    "elbow_flex": 45.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 0.0,
}

# Beat-locked motion. These are *held* offsets that only change when a beat
# fires and then ramp smoothly toward their new target (via clamp_step). The
# pincer flips open/closed every beat; the sway and twist move at half-time
# (every other beat, in opposition) so the arm grooves instead of lurching.
# All are scaled by loudness, so quiet passages move gently and loud move big.
SWAY_JOINT = "shoulder_pan"
SWAY_DEG = 35.0

TWIST_JOINT = "wrist_roll"
TWIST_DEG = 30.0

GRIPPER_JOINT = "gripper"
# Gripper closed/open angles are per-arm; defaults come from config/.env and
# are overridable with --gripper-closed / --gripper-open. Find yours with
# --read-gripper.
GRIPPER_CLOSED_DEG = config.GRIPPER_CLOSED_DEG
GRIPPER_OPEN_DEG = config.GRIPPER_OPEN_DEG

# Per-joint overrides to the default MAX_STEP_DEG slew limit.
JOINT_MAX_STEP = {GRIPPER_JOINT: GRIPPER_MAX_STEP_DEG}


def blend(a: dict, b: dict, t: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def clamp_step(current: dict, target: dict, max_step: float, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    out = {}
    for k, v in target.items():
        limit = overrides.get(k, max_step)
        delta = max(-limit, min(limit, v - current[k]))
        out[k] = current[k] + delta
    return out


def run(
    port: str,
    audio_source_kind: str,
    file_path: str | None,
    dry_run: bool,
    sensitivity: float,
    gripper_closed: float = GRIPPER_CLOSED_DEG,
    gripper_open_deg: float = GRIPPER_OPEN_DEG,
    intensity: float = 1.0,
) -> None:
    source = create_source(audio_source_kind, SAMPLE_RATE, BLOCK_SIZE, file_path)
    source.start()

    envelope = EnvelopeFollower()
    beat = BeatDetector(block_seconds=BLOCK_SIZE / SAMPLE_RATE, sensitivity=sensitivity)

    bus = None
    if not dry_run:
        calibration = load_calibration(CALIBRATION_PATH)
        bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
        bus.connect()
        bus.sync_write("Torque_Enable", 1)

    current_pose = dict(REST_POSE)
    loudness = 0.0
    beat_count = 0
    beat_times: collections.deque[float] = collections.deque(maxlen=8)
    block_seconds = BLOCK_SIZE / SAMPLE_RATE
    audio_time = 0.0
    tick_period = 1.0 / TICK_HZ

    try:
        while True:
            loop_start = time.monotonic()

            # Analyze *every* audio block that arrived since the last tick, not
            # just one. The stream produces ~43 blocks/s but we command the
            # motors at TICK_HZ (~25/s); draining the queue here keeps beat
            # detection from missing the block a kick onset lands in. Beat
            # timing uses an audio clock (block count) rather than wall time, so
            # it stays accurate regardless of loop scheduling jitter.
            block = source.get_block(timeout=tick_period)
            while block is not None:
                loudness = envelope.update(block)
                audio_time += block_seconds
                if beat.update(bass_energy(block, SAMPLE_RATE), audio_time):
                    beat_count += 1
                    beat_times.append(audio_time)
                    bpm = estimate_bpm(beat_times)
                    print(f"beat  ({bpm:.0f} BPM)" if bpm else "beat")
                block = source.get_block(timeout=0.0)

            # Held motion states derived from the beat count, so they only
            # change on a beat and then ramp smoothly toward the new target.
            # The pincer opens/closes on *every* beat; the sway and twist move
            # at half-time (every other beat) and in opposition to each other,
            # so the arm grooves rather than lurching on every single beat -
            # much calmer at faster tempos while the pincer still hits the beat.
            pincer_open = beat_count % 2 == 1
            sway_direction = 1.0 if beat_count % 4 < 2 else -1.0
            twist_direction = -sway_direction

            target = blend(REST_POSE, DANCE_POSE, loudness)
            target[SWAY_JOINT] += SWAY_DEG * loudness * intensity * sway_direction
            target[TWIST_JOINT] += TWIST_DEG * loudness * intensity * twist_direction
            # Closed is always *fully* closed; open scales from closed->open with
            # loudness, so quiet passages only part the pincer a little.
            if pincer_open:
                target[GRIPPER_JOINT] = gripper_closed + (gripper_open_deg - gripper_closed) * loudness
            else:
                target[GRIPPER_JOINT] = gripper_closed

            current_pose = clamp_step(current_pose, target, MAX_STEP_DEG, JOINT_MAX_STEP)

            if dry_run:
                print({k: round(v, 1) for k, v in current_pose.items()})
            else:
                bus.sync_write("Goal_Position", current_pose)

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.0, tick_period - elapsed))
    except KeyboardInterrupt:
        print("Stopping, returning to rest…")
    finally:
        source.stop()
        if bus is not None:
            # Curl up with the pincer closed (not the pose's default 0, which
            # may be open on this arm).
            curl_target = {**CURL_POSE, GRIPPER_JOINT: gripper_closed}
            pose = current_pose
            for _ in range(20):
                pose = clamp_step(pose, curl_target, MAX_STEP_DEG)
                bus.sync_write("Goal_Position", pose)
                time.sleep(0.05)
            bus.sync_write("Torque_Enable", 0)
            bus.disconnect()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Make Brachiomimus dance to music")
    parser.add_argument(
        "--port", default=config.PORT,
        help=f"Serial port the arm is connected to (default: {config.PORT})"
    )
    parser.add_argument(
        "--audio-source", choices=["mic", "loopback", "file"], default="mic",
        help="Where to read audio from (default: mic)"
    )
    parser.add_argument(
        "--file", default=None,
        help="Path to a WAV file to play + analyze (required when --audio-source=file)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print computed poses instead of sending them to the arm"
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="Beats-only tuning mode: no arm, prints each detected beat with a "
             "live BPM estimate. Works with any --audio-source (e.g. loopback "
             "while YouTube plays) so you can dial in --sensitivity."
    )
    parser.add_argument(
        "--sensitivity", type=float, default=config.SENSITIVITY,
        help=f"Beat detector threshold (default: {config.SENSITIVITY}). Raise it "
             "if the arm reacts to more than the actual beat; lower it if it "
             "misses beats."
    )
    parser.add_argument(
        "--intensity", type=float, default=config.INTENSITY,
        help=f"Scale the sway/twist size (default: {config.INTENSITY}). Lower it "
             "(e.g. 0.5) for calmer motion at faster tempos."
    )
    parser.add_argument(
        "--gripper-closed", type=float, default=GRIPPER_CLOSED_DEG,
        help=f"Gripper angle that is FULLY CLOSED on your arm (default: "
             f"{GRIPPER_CLOSED_DEG}). If the pincer never closes, this is "
             f"wrong for your calibration - find it with --read-gripper."
    )
    parser.add_argument(
        "--gripper-open", type=float, default=GRIPPER_OPEN_DEG,
        help=f"Gripper angle that is fully open (default: {GRIPPER_OPEN_DEG})."
    )
    parser.add_argument(
        "--read-gripper", action="store_true",
        help="Release the gripper and print its live angle so you can read off "
             "your closed/open values, then exit. Needs --port."
    )
    args = parser.parse_args()
    if args.read_gripper:
        read_gripper(args.port)
    elif args.monitor:
        monitor(args.audio_source, args.file, args.sensitivity)
    else:
        run(
            args.port, args.audio_source, args.file, args.dry_run,
            args.sensitivity, args.gripper_closed, args.gripper_open, args.intensity,
        )
