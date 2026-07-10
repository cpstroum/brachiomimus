"""
dance.py — make Brachiomimus move to music.

Two audio features drive the arm, computed live every tick:
  - loudness (smoothed RMS envelope over the whole signal) -> how big the
    raise/sway is
  - beat (onset detector watching just the bass band, ~20-150Hz) ->
    punctuated accents added on top: the gripper snaps open then eases shut,
    the wrist gives a twist, and the shoulder swings to the opposite side

Beat detection deliberately looks at bass energy rather than the full
signal - hi-hats, cymbals, and vocals spike the broadband energy far more
often than the actual tempo, which reads as chaotic/too-fast on anything
that isn't a wall of noise. Kick drums and basslines are usually what
actually carries a song's beat, so filtering down to that band gives
motion that tracks the song's real pace instead of every little transient.

Usage:
    python dance.py --port /dev/ttyUSB0 --audio-source mic
    python dance.py --port COM4 --audio-source loopback
    python dance.py --port COM4 --audio-source file --file song.wav
    python dance.py --dry-run --audio-source file --file song.wav

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
MAX_STEP_DEG = 6.0  # per-tick clamp so no beat pulse can yank the arm

# Arm raised, similar in spirit to wave.py's WAVE_READY_POSE
DANCE_POSE = {
    "shoulder_pan": 0.0,
    "shoulder_lift": -60.0,
    "elbow_flex": 45.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 0.0,
}

# Continuous side-to-side sway: shoulder_pan swings toward +/- SWAY_DEG,
# scaled by loudness. Direction flips on every detected beat, so the swing
# itself lands on the rhythm instead of drifting on its own free-running period.
SWAY_JOINT = "shoulder_pan"
SWAY_DEG = 35.0

# Punctuated accents added on top of the pose for the duration of a beat's
# decaying pulse: a wrist twist plus a gripper "chomp" (open on the beat,
# springs back shut as the pulse decays).
BEAT_PULSES = {
    "wrist_roll": 25.0,
    "gripper": 45.0,
}
BEAT_DECAY_SECONDS = 0.2


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
    """Onset detector: flags a beat when the current energy value spikes
    above the recent local average, gated by a refractory period so a single
    hit's decay tail can't double-trigger. Feed it a narrowband energy (see
    bass_energy) rather than full-signal energy for musically-meaningful hits."""

    def __init__(
        self,
        block_seconds: float,
        history_seconds: float = 1.0,
        sensitivity: float = 1.6,
        refractory_seconds: float = 0.25,
    ):
        self.history: collections.deque[float] = collections.deque(
            maxlen=max(1, int(history_seconds / block_seconds))
        )
        self.sensitivity = sensitivity
        self.refractory_seconds = refractory_seconds
        self._last_beat_time = -math.inf

    def update(self, energy: float, now: float) -> bool:
        is_beat = False
        if self.history:
            average = sum(self.history) / len(self.history)
            if energy > average * self.sensitivity and now - self._last_beat_time > self.refractory_seconds:
                is_beat = True
                self._last_beat_time = now
        self.history.append(energy)
        return is_beat


def blend(a: dict, b: dict, t: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def clamp_step(current: dict, target: dict, max_step: float) -> dict:
    out = {}
    for k, v in target.items():
        delta = max(-max_step, min(max_step, v - current[k]))
        out[k] = current[k] + delta
    return out


def run(port: str, audio_source_kind: str, file_path: str | None, dry_run: bool) -> None:
    source = create_source(audio_source_kind, SAMPLE_RATE, BLOCK_SIZE, file_path)
    source.start()

    envelope = EnvelopeFollower()
    beat = BeatDetector(block_seconds=BLOCK_SIZE / SAMPLE_RATE)

    bus = None
    if not dry_run:
        calibration = load_calibration(CALIBRATION_PATH)
        bus = FeetechMotorsBus(port=port, motors=MOTORS, calibration=calibration)
        bus.connect()
        bus.sync_write("Torque_Enable", 1)

    current_pose = dict(REST_POSE)
    loudness = 0.0
    pulse_level = 0.0
    sway_direction = 1.0
    tick_period = 1.0 / TICK_HZ

    try:
        while True:
            tick_start = time.monotonic()
            block = source.get_block(timeout=tick_period)
            if block is not None:
                loudness = envelope.update(block)
                if beat.update(bass_energy(block, SAMPLE_RATE), tick_start):
                    pulse_level = 1.0
                    sway_direction *= -1.0
                    print("beat")

            pulse_level *= math.exp(-tick_period / BEAT_DECAY_SECONDS)

            target = blend(REST_POSE, DANCE_POSE, loudness)
            target[SWAY_JOINT] += SWAY_DEG * loudness * sway_direction
            for joint, pulse_deg in BEAT_PULSES.items():
                target[joint] += pulse_deg * pulse_level

            current_pose = clamp_step(current_pose, target, MAX_STEP_DEG)

            if dry_run:
                print({k: round(v, 1) for k, v in current_pose.items()})
            else:
                bus.sync_write("Goal_Position", current_pose)

            elapsed = time.monotonic() - tick_start
            time.sleep(max(0.0, tick_period - elapsed))
    except KeyboardInterrupt:
        print("Stopping, returning to rest…")
    finally:
        source.stop()
        if bus is not None:
            pose = current_pose
            for _ in range(20):
                pose = clamp_step(pose, CURL_POSE, MAX_STEP_DEG)
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
    args = parser.parse_args()
    run(args.port, args.audio_source, args.file, args.dry_run)
