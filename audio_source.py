"""
audio_source.py — pluggable real-time audio sources for dance.py.

Three interchangeable sources, all producing the same thing: fixed-size
mono float32 blocks pushed into a queue that the control loop drains.

  - MicSource       — default microphone input
  - LoopbackSource  — the machine's own audio output, captured digitally via
                       WASAPI loopback (needs the `soundcard` package —
                       plain `sounddevice`/PortAudio has no loopback support)
  - FileSource      — plays a WAV/MP3 through the speakers while analyzing
                       the exact same samples, so the arm reacts in sync
                       with what you actually hear

Swap sources with dance.py's --audio-source flag; no code changes needed.
"""

import queue
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioSource:
    samplerate: int

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def get_block(self, timeout: float = 1.0) -> np.ndarray | None:
        raise NotImplementedError


class _QueueSource(AudioSource):
    """Shared plumbing: a bounded queue fed by a sounddevice callback."""

    def __init__(self, samplerate: int, blocksize: int):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        self._stream: sd.Stream | None = None

    def get_block(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _push(self, block: np.ndarray) -> None:
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            # Real-time audio: drop rather than block the audio thread.
            pass

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class MicSource(_QueueSource):
    def start(self) -> None:
        def callback(indata, frames, time_info, status):
            self._push(np.mean(indata, axis=1).astype(np.float32))

        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=1,
            callback=callback,
        )
        self._stream.start()


class LoopbackSource(_QueueSource):
    """Captures the default output device's audio via WASAPI loopback.

    PortAudio (what `sounddevice` wraps) has no loopback support, so this
    uses `soundcard` instead, which talks to WASAPI directly and exposes the
    default speaker as a recordable "loopback microphone".
    """

    def __init__(self, samplerate: int, blocksize: int):
        super().__init__(samplerate, blocksize)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import soundcard as sc

        speaker = sc.default_speaker()
        mic = sc.get_microphone(id=speaker.id, include_loopback=True)

        def capture() -> None:
            with mic.recorder(samplerate=self.samplerate, blocksize=self.blocksize) as recorder:
                while not self._stop_event.is_set():
                    data = recorder.record(numframes=self.blocksize)
                    self._push(np.mean(data, axis=1).astype(np.float32))

        self._thread = threading.Thread(target=capture, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None


class FileSource(_QueueSource):
    """Plays a file through the speakers and analyzes the same samples."""

    def __init__(self, samplerate: int, blocksize: int, path: str):
        super().__init__(samplerate, blocksize)
        self.path = path
        self._file = sf.SoundFile(path)
        if self._file.samplerate != samplerate:
            raise ValueError(
                f"{path} is {self._file.samplerate}Hz; expected {samplerate}Hz. "
                "Resample the file or pass --samplerate to match it."
            )

    def start(self) -> None:
        def callback(outdata, frames, time_info, status):
            data = self._file.read(frames, dtype="float32", always_2d=True)
            if len(data) < frames:
                outdata[: len(data)] = data
                outdata[len(data) :] = 0
                raise sd.CallbackStop
            outdata[:] = data
            self._push(np.mean(data, axis=1))

        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=self._file.channels,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        super().stop()
        self._file.close()


def create_source(
    kind: str, samplerate: int, blocksize: int, file_path: str | None = None
) -> AudioSource:
    if kind == "mic":
        return MicSource(samplerate, blocksize)
    if kind == "loopback":
        return LoopbackSource(samplerate, blocksize)
    if kind == "file":
        if not file_path:
            raise ValueError("--file is required when --audio-source=file")
        return FileSource(samplerate, blocksize, file_path)
    raise ValueError(f"Unknown audio source: {kind!r}")
