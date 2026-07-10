"""
dance.py — make Brachiomimus move to music.

Two audio features drive the arm, computed live every tick:
  - loudness (smoothed RMS envelope over the whole signal) -> how big the
    raise/sway/twist/pincer motions are
  - beat (onset detector watching just the bass band, ~20-150Hz) -> on each
    beat the arm flips to the opposite side, twists the other way, and opens
    or closes the gripper, then ramps smoothly toward those new targets until
    the next beat - so it dances *on* the beat rather than twitching.

Beat detection deliberately looks at bass energy rather than the full
signal - hi-hats, cymbals, and vocals spike the broadband energy far more
often than the actual tempo, which reads as chaotic/too-fast on anything
that isn't a wall of noise. Kick drums and basslines are usually what
actually carries a song's beat, so filtering down to that band - plus a
peak-relative threshold that favors the strongest low-end hits - gives
motion that tracks the real beat instead of every little transient.

Tuning: run with --monitor (no arm) to watch detected beats + a live BPM
readout against any source, and adjust --sensitivity until it locks on.

Usage:
    python dance.py --port COM4 --audio-source loopback
    python dance.py --port /dev/ttyUSB0 --audio-source mic
    python dance.py --port COM4 --audio-source file --file song.wav
    python dance.py --monitor --audio-source loopback   # tune, no arm

See MUSIC.md for setup and source selection notes.
"""

import argparse
import collections
import math
import time

import numpy as np

from audio_source import create_source
from lerobot.motors.feetech import FeetechMotorsBus
from wave import CALIBRATION_PATH, MOTORS, REST_POSE, WAVE_READY_POSE, load_calibration

# On shutdown, ramp to this raised/curled pose instead of REST_POSE - REST_POSE
# is flat (all zeros) and lets the arm sag/collapse onto the table once torque
# is enabled again; WAVE_READY_POSE is the same tucked-up raised pose wave.py
# already uses and is known to be a safe, calibrated resting configuration.
CURL_POSE = WAVE_READY_POSE

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024  # ~23ms per block at 44.1kHz
TICK_HZ = 25.0
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
# fires and then ramp smoothly toward their new target (via clamp_step), rather
# than fast-decaying transient pulses - held-and-ramping reads as deliberate
# dancing on the beat, transient pulses read as twitchy/chaotic.
#
#   - sway:   shoulder_pan swings to the opposite side on each beat
#   - twist:  wrist_roll rotates the opposite way on each beat
#   - pincer: gripper toggles between closed and open on each beat, so it
#             opens and closes in time with the music
# All three are scaled by loudness, so quiet passages move gently and loud
# passages move big.
SWAY_JOINT = "shoulder_pan"
SWAY_DEG = 35.0

TWIST_JOINT = "wrist_roll"
TWIST_DEG = 30.0

GRIPPER_JOINT = "gripper"
GRIPPER_OPEN_DEG = 45.0
GRIPPER_CLOSED_DEG = 0.0

# Per-joint overrides to the default MAX_STEP_DEG slew limit.
JOINT_MAX_STEP = {GRIPPER_JOINT: GRIPPER_MAX_STEP_DEG}


class EnvelopeFollower:
    """Smoothed RMS loudness, auto-normalized to a 0.0-1.0 range.

    The ceiling that loudness is normalized against tracks recent peaks on
    its own slow timescale (rising over ~2s, decaying over ~10s) instead of
    snapping straight to the current level - otherwise it would chase every
    new peak instantly and the output would pin at 1.0 for any sustained
    sound, never showing the difference between medium-loud and very-loud.
    """

    def __init__(
        self,
        attack: float = 0.6,
        release: float = 0.15,
        ceiling_rise: float = 0.02,
        ceiling_fall: float = 0.004,
    ):
        self.level = 0.0
        self.ceiling = 1e-4
        self.attack = attack
        self.release = release
        self.ceiling_rise = ceiling_rise
        self.ceiling_fall = ceiling_fall

    def update(self, block: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(block)) + 1e-12))
        coeff = self.attack if rms > self.level else self.release
        self.level += (rms - self.level) * coeff
        ceiling_coeff = self.ceiling_rise if self.level > self.ceiling else self.ceiling_fall
        self.ceiling += (self.level - self.ceiling) * ceiling_coeff
        return min(1.0, self.level / self.ceiling)


def bass_energy(block: np.ndarray, samplerate: int, max_freq: float = 150.0) -> float:
    """Power in the block confined to the bass band (kick drum/bassline
    territory) - what BeatDetector should watch instead of full-band energy."""
    spectrum = np.fft.rfft(block)
    freqs = np.fft.rfftfreq(len(block), d=1.0 / samplerate)
    band = spectrum[freqs <= max_freq]
    if band.size == 0:
        return 0.0
    return float(np.mean(np.abs(band) ** 2))


class BeatDetector:
    """Onset detector. Flags a beat only when all of these hold:

      - the energy is a strong multiple of the recent local average
        (`sensitivity`) - an adaptive threshold that tracks the song's level
      - the energy is near the recent *peak* (`peak_ratio` of a slowly
        decaying running maximum) - kicks/downbeats dominate the low end, so
        this is what mostly rejects weaker off-beat bass notes and syncopated
        basslines that a plain average-relative threshold happily fires on.
        This is the main lever against "picking up more than the actual beat"
      - the energy is *rising* vs the previous block - rejects the sustained
        decay tail of a hit, which otherwise re-triggers for several blocks
      - it's been at least `refractory_seconds` since the last beat

    Raise `sensitivity`/`peak_ratio` (via dance.py's --sensitivity) if it's
    still catching too much; lower them if it's missing real beats.

    Feed it a narrowband energy (see bass_energy), not full-signal energy."""

    def __init__(
        self,
        block_seconds: float,
        history_seconds: float = 1.5,
        sensitivity: float = 1.8,
        peak_ratio: float = 0.65,
        refractory_seconds: float = 0.3,
    ):
        self.history: collections.deque[float] = collections.deque(
            maxlen=max(1, int(history_seconds / block_seconds))
        )
        self.sensitivity = sensitivity
        self.peak_ratio = peak_ratio
        self.refractory_seconds = refractory_seconds
        # Peak decays slowly (~1.6s half-life, a couple of beats) so it stays
        # near the last strong hit across the gap to the next one, keeping the
        # peak-relative threshold meaningful between beats.
        self.peak_decay = 0.5 ** (block_seconds / 1.6)
        self._peak = 0.0
        self._last_beat_time = -math.inf
        self._prev_energy = 0.0

    def update(self, energy: float, now: float) -> bool:
        self._peak = max(energy, self._peak * self.peak_decay)
        is_beat = False
        if self.history:
            average = sum(self.history) / len(self.history)
            gap = now - self._last_beat_time
            if (
                energy > average * self.sensitivity
                and energy > self._peak * self.peak_ratio
                and energy > self._prev_energy
                and gap > self.refractory_seconds
            ):
                is_beat = True
                self._last_beat_time = now
        self.history.append(energy)
        self._prev_energy = energy
        return is_beat


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


def estimate_bpm(beat_times: collections.deque[float]) -> float | None:
    """Rolling tempo estimate from recent beat timestamps, using the median
    interval so a stray extra/missed beat doesn't swing the number."""
    if len(beat_times) < 2:
        return None
    intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
    median = sorted(intervals)[len(intervals) // 2]
    return 60.0 / median if median > 0 else None


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


def run(
    port: str,
    audio_source_kind: str,
    file_path: str | None,
    dry_run: bool,
    monitor: bool,
    sensitivity: float,
    gripper_closed: float = GRIPPER_CLOSED_DEG,
    gripper_open_deg: float = GRIPPER_OPEN_DEG,
    intensity: float = 1.0,
) -> None:
    # monitor = beats-only tuning mode: no arm, no per-tick pose spam, just a
    # live BPM readout so you can dial in --sensitivity against any source
    # (including loopback while a browser/YouTube plays). dry_run = full pose
    # pipeline printed each tick but not sent to the arm. Both skip hardware.
    use_bus = not (dry_run or monitor)

    source = create_source(audio_source_kind, SAMPLE_RATE, BLOCK_SIZE, file_path)
    source.start()

    envelope = EnvelopeFollower()
    beat = BeatDetector(block_seconds=BLOCK_SIZE / SAMPLE_RATE, sensitivity=sensitivity)

    bus = None
    if use_bus:
        calibration = load_calibration(CALIBRATION_PATH)
        bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
        bus.connect()
        bus.sync_write("Torque_Enable", 1)

    if monitor:
        print(f"Monitor mode (--sensitivity {sensitivity}): listening for beats, "
              "no arm. Ctrl+C to stop.")

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

            if monitor:
                elapsed = time.monotonic() - loop_start
                time.sleep(max(0.0, tick_period - elapsed))
                continue

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
        "--port", default="/dev/ttyUSB0",
        help="Serial port the arm is connected to (default: /dev/ttyUSB0)"
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
        "--sensitivity", type=float, default=1.8,
        help="Beat detector threshold (default: 1.8). Raise it if the arm "
             "reacts to more than the actual beat; lower it if it misses beats."
    )
    parser.add_argument(
        "--intensity", type=float, default=1.0,
        help="Scale the sway/twist size (default: 1.0). Lower it (e.g. 0.5) "
             "for calmer motion at faster tempos."
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
    else:
        run(
            args.port, args.audio_source, args.file, args.dry_run, args.monitor,
            args.sensitivity, args.gripper_closed, args.gripper_open, args.intensity,
        )
