"""MeloTTS (MIT licensed) Korean adapter.

NOT streaming: one call returns the whole sentence's audio, so T4 here is
sentence-level synthesis time, not a true "first packet" time. That is exactly
why sentence chunking in the pipeline matters: it bounds how much text must be
synthesized before the first audio exists.

Install on Colab can be fiddly (Korean text frontend dependencies); see README.
"""

from __future__ import annotations

import numpy as np

from ..interfaces import TTS, AudioChunk


class MeloTTS(TTS):
    def __init__(self, device: str = "auto", speed: float = 1.0, language: str = "KR", **_):
        from melo.api import TTS as _Melo  # imported lazily: heavy, optional dependency

        self.name = "melotts:" + language
        self._model = _Melo(language=language, device=device)
        self._speaker = list(self._model.hps.data.spk2id.values())[0]
        self._sr = int(self._model.hps.data.sampling_rate)
        self._speed = float(speed)
        self.last_usage = {}

    def synthesize(self, text: str):
        audio = self._model.tts_to_file(text, self._speaker, None, speed=self._speed)
        yield AudioChunk(np.asarray(audio, dtype=np.float32), self._sr)
