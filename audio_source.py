"""
audio_source.py — pluggable real-time audio sources for dance.py.

Three interchangeable sources, all producing the same thing: fixed-size
mono float32 blocks pushed into a queue that the control loop drains.

  - MicSource       — default microphone input
  - LoopbackSource  — the machine's own audio output, captured digitally
                       (WASAPI loopback via sounddevice; no extra dependency)
  - FileSource      — plays a WAV/MP3 through the speakers while analyzing
                       the exact same samples, so the arm reacts in sync
                       with what you actually hear

Swap sources with dance.py's --audio-source flag; no code changes needed.
"""

import queue

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
    """Captures the default output device's audio via WASAPI loopback."""

    def start(self) -> None:
        device_info = sd.query_devices(kind="output")
        channels = device_info["max_output_channels"]

        def callback(indata, frames, time_info, status):
            self._push(np.mean(indata, axis=1).astype(np.float32))

        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=channels,
            device=device_info["index"] if "index" in device_info else None,
            extra_settings=sd.WasapiSettings(loopback=True),
            callback=callback,
        )
        self._stream.start()


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
