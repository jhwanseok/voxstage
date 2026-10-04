"""Energy-based endpointer, evaluated offline in *audio time*.

Why audio time: the test audio is pre-generated, so the true end of speech is
known exactly. T1 = (time the endpointer would have fired) - (true speech end).
For this endpointer that is hangover + frame quantization, which is exactly the
latency a real streaming endpointer with the same settings would add.
"""

from __future__ import annotations

import numpy as np


class EnergyEndpointer:
    def __init__(self, frame_ms: int = 20, threshold_dbfs: float = -45.0, hangover_ms: int = 500):
        self.frame_ms = frame_ms
        self.threshold_dbfs = threshold_dbfs
        self.hangover_ms = hangover_ms
        self.last_clipped = False  # True if the audio ended before the hangover elapsed

    def detect(self, audio: np.ndarray, sample_rate: int) -> float:
        """Return the audio-time (seconds) at which end-of-speech would be declared."""
        duration = len(audio) / sample_rate
        n = int(sample_rate * self.frame_ms / 1000)
        nframes = len(audio) // n
        self.last_clipped = False
        if nframes == 0:
            return duration
        frames = audio[: nframes * n].astype(np.float64).reshape(nframes, n)
        rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
        db = 20 * np.log10(rms + 1e-12)
        speech = np.nonzero(db > self.threshold_dbfs)[0]
        if len(speech) == 0:
            return duration
        speech_end = (speech[-1] + 1) * n / sample_rate
        fire = speech_end + self.hangover_ms / 1000
        if fire > duration:
            self.last_clipped = True
            return duration
        return fire
