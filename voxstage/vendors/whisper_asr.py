"""faster-whisper ASR adapter (runs on Colab T4 or CPU).

NOT streaming: Whisper decodes a finished utterance. So T2 here means
"endpoint -> full-utterance transcript", which is the honest definition for a
final-only ASR. A streaming ASR would have most of this work already done at endpoint.

Model load happens in __init__ and is never inside a timed segment.
"""

from __future__ import annotations

from ..interfaces import ASR


class WhisperASR(ASR):
    def __init__(self, model: str = "small", device: str = "auto", compute_type: str = "auto",
                 language: str = "ko", beam_size: int = 1, **_):
        from faster_whisper import WhisperModel  # imported lazily: heavy, optional dependency

        self.name = f"faster-whisper:{model}"
        self.language = language
        self.beam_size = int(beam_size)
        self._model = WhisperModel(model, device=device, compute_type=compute_type)
        self.last_usage = {}

    def transcribe(self, audio, sample_rate) -> str:
        if sample_rate != 16000:
            raise ValueError("faster-whisper expects 16 kHz audio; resample before the pipeline")
        segments, _info = self._model.transcribe(
            audio, language=self.language, beam_size=self.beam_size,
            vad_filter=False, condition_on_previous_text=False,
        )
        # `segments` is a lazy generator: decoding happens while we consume it,
        # so it must be consumed inside the timed region.
        return " ".join(s.text.strip() for s in segments).strip()
