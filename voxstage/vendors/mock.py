"""Mock vendors with realistic, seeded latency distributions.

Purpose: develop and test the whole measurement stack with zero API cost.
`time_scale` shrinks sleeps (tests use 0.01) without changing the distributions' shape.
"""

from __future__ import annotations

import random
import time
from typing import Iterator

import numpy as np

from ..interfaces import ASR, LLM, TTS, AudioChunk


class _Jitter:
    def __init__(self, seed: int, time_scale: float):
        self.rng = random.Random(seed)
        self.scale = time_scale

    def sleep(self, median_s: float, sigma: float = 0.25) -> None:
        time.sleep(self.rng.lognormvariate(np.log(median_s), sigma) * self.scale)


class MockASR(ASR):
    def __init__(self, seed: int = 1, time_scale: float = 1.0, median_ms: float = 250, **_):
        self.name = "mock-asr"
        self._j = _Jitter(seed, time_scale)
        self._median = median_ms / 1000

    def transcribe(self, audio, sample_rate) -> str:
        self._j.sleep(self._median)
        return "모의 인식 결과입니다"


class MockLLM(LLM):
    RESPONSE = "네, 알겠습니다. 요청하신 내용을 확인해서 바로 안내해 드릴게요. 추가로 필요한 것이 있으면 말씀해 주세요."

    def __init__(self, seed: int = 2, time_scale: float = 1.0, first_token_ms: float = 450, **_):
        self.name = "mock-llm"
        self._j = _Jitter(seed, time_scale)
        self._first = first_token_ms / 1000
        self.last_usage = {}

    def stream(self, messages) -> Iterator[str]:
        self._j.sleep(self._first, 0.35)
        text = self.RESPONSE
        step = 3
        for i in range(0, len(text), step):
            if i:
                self._j.sleep(0.02, 0.3)
            yield text[i:i + step]
        self.last_usage = {"input_tokens": sum(len(m["content"]) for m in messages) // 2,
                           "output_tokens": len(text) // 2}


class MockTTS(TTS):
    def __init__(self, seed: int = 3, time_scale: float = 1.0, first_chunk_ms: float = 180,
                 sample_rate: int = 24000, **_):
        self.name = "mock-tts"
        self._j = _Jitter(seed, time_scale)
        self._first = first_chunk_ms / 1000
        self._sr = sample_rate
        self.last_usage = {}

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        self._j.sleep(self._first, 0.3)
        n = int(self._sr * 0.05 * max(1, len(text) // 4))
        yield AudioChunk(np.zeros(n, dtype=np.float32), self._sr)
        self._j.sleep(0.03)
        yield AudioChunk(np.zeros(n, dtype=np.float32), self._sr)
