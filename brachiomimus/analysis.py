"""
analysis.py — audio signal processing for the dancer.

Pure DSP: no hardware, no motion. Turns raw audio blocks into the two features
that drive the arm — a smoothed loudness value and beat onsets — plus a tempo
estimate for the tuning tools. Imported by both dance.py (core) and
diagnostics.py (tuning/calibration helpers).
"""

import collections
import math

import numpy as np

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024  # ~23ms per block at 44.1kHz
TICK_HZ = 25.0     # how often the control/monitor loop acts


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


def estimate_bpm(beat_times: "collections.deque[float]") -> float | None:
    """Rolling tempo estimate from recent beat timestamps, using the median
    interval so a stray extra/missed beat doesn't swing the number."""
    if len(beat_times) < 2:
        return None
    intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
    median = sorted(intervals)[len(intervals) // 2]
    return 60.0 / median if median > 0 else None
