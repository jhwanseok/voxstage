"""One-turn voice pipeline: audio -> endpoint -> ASR -> LLM(stream) -> sentence chunks -> TTS -> sink.

Every stage emits events; measurement lives in voxstage.metrics, not here.

v0 limitation (on purpose): stages run sequentially in one thread. The first
sentence's timings are exact; later sentences are synthesized after the first
finishes, so they do not model overlap between LLM streaming and TTS playback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .cost import PriceTable
from .endpointer import EnergyEndpointer
from .events import EventLog
from .interfaces import ASR, LLM, TTS, NullSink, Sink

DEFAULT_SYSTEM_PROMPT = "당신은 친절한 음성 비서입니다. 항상 한국어로, 두 문장 이내로 짧게 답하세요."


class SentenceChunker:
    """Cuts a token stream into speakable sentences.

    The first sentence boundary decides when TTS can start, so min_chars is a
    latency/quality knob: too small -> choppy prosody, too large -> late audio.
    """

    def __init__(self, min_chars: int = 8):
        self.min_chars = min_chars
        self.buf = ""

    def _find_cut(self) -> Optional[int]:
        b = self.buf
        for i, ch in enumerate(b):
            hard = ch in "!?。！？\n"
            # "3.5" must not split: a '.' counts only when followed by whitespace
            soft = ch == "." and i + 1 < len(b) and b[i + 1].isspace()
            if (hard or soft) and len(b[: i + 1].strip()) >= self.min_chars:
                return i + 1
        return None

    def feed(self, delta: str) -> list[str]:
        self.buf += delta
        out = []
        while (cut := self._find_cut()) is not None:
            sent = self.buf[:cut].strip()
            self.buf = self.buf[cut:]
            if sent:
                out.append(sent)
        return out

    def flush(self) -> Optional[str]:
        tail = self.buf.strip()
        self.buf = ""
        return tail or None


@dataclass
class TurnResult:
    transcript: str = ""
    response: str = ""
    ok: bool = True
    error: Optional[str] = None
    sentences: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, asr: ASR, llm: LLM, tts: TTS, *, sink: Optional[Sink] = None,
                 endpointer: Optional[EnergyEndpointer] = None, log: Optional[EventLog] = None,
                 prices: Optional[PriceTable] = None, system_prompt: str = DEFAULT_SYSTEM_PROMPT,
                 min_sentence_chars: int = 8):
        self.asr, self.llm, self.tts = asr, llm, tts
        self.sink = sink or NullSink()
        self.endpointer = endpointer or EnergyEndpointer()
        self.log = log or EventLog()
        self.prices = prices or PriceTable()
        self.system_prompt = system_prompt
        self.min_sentence_chars = min_sentence_chars

    # -- helpers ---------------------------------------------------------
    def _cost(self, emit, kind: str, usage: dict) -> None:
        emit("cost", kind=kind, usage=usage, shadow_usd=self.prices.usd(kind, usage))

    def _speak(self, emit, sentence: str, idx: int) -> None:
        if idx == 0:
            emit("llm_first_sentence", chars=len(sentence))
        emit("tts_request", sentence_idx=idx, chars=len(sentence))
        first = True
        for chunk in self.tts.synthesize(sentence):
            if first:
                emit("tts_first_chunk", sentence_idx=idx, samples=int(len(chunk.pcm)),
                     sample_rate=chunk.sample_rate)
            self.sink.play(chunk)
            if first and idx == 0:
                emit("playback_start", sink=self.sink.name, measured=self.sink.measures_playback)
            first = False
        self._cost(emit, "tts", {"chars": len(sentence), **getattr(self.tts, "last_usage", {})})

    # -- main ------------------------------------------------------------
    def run_turn(self, session_id: str, turn: int, audio: np.ndarray, sample_rate: int,
                 truth_end_s: float, *, warmup: bool = False,
                 history: Optional[list[dict]] = None) -> TurnResult:
        def emit(etype, **data):
            return self.log.emit(session_id, turn, etype, warmup=warmup, **data)

        result = TurnResult()
        stage = "endpoint"
        try:
            detected_s = self.endpointer.detect(audio, sample_rate)
            emit("endpoint", truth_end_s=truth_end_s, detected_s=detected_s,
                 clipped=self.endpointer.last_clipped)

            stage = "asr"
            audio_seconds = len(audio) / sample_rate
            emit("asr_request", audio_seconds=audio_seconds)
            result.transcript = self.asr.transcribe(audio, sample_rate)
            emit("asr_final", text=result.transcript)
            self._cost(emit, "asr", {"audio_seconds": audio_seconds, **getattr(self.asr, "last_usage", {})})

            stage = "llm"
            messages = ([{"role": "system", "content": self.system_prompt}]
                        + list(history or [])
                        + [{"role": "user", "content": result.transcript}])
            emit("llm_request", n_messages=len(messages))
            chunker = SentenceChunker(self.min_sentence_chars)
            parts: list[str] = []
            seen_first = False
            idx = 0
            for delta in self.llm.stream(messages):
                if not seen_first:
                    emit("llm_first_token")
                    seen_first = True
                parts.append(delta)
                for sent in chunker.feed(delta):
                    stage = "tts"
                    result.sentences.append(sent)
                    self._speak(emit, sent, idx)
                    idx += 1
                    stage = "llm"
            tail = chunker.flush()
            if tail:
                stage = "tts"
                result.sentences.append(tail)
                self._speak(emit, tail, idx)
            result.response = "".join(parts)
            emit("llm_done", chars=len(result.response))
            self._cost(emit, "llm", dict(getattr(self.llm, "last_usage", {})))
            emit("turn_end")
        except Exception as exc:  # a failed turn is data, not a crash
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            emit("error", stage=stage, error=result.error)
        return result
