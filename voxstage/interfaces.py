"""Vendor-neutral interfaces. A vendor must be swappable without touching the pipeline.

Audio convention: mono float32 numpy arrays in [-1, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass
class AudioChunk:
    pcm: np.ndarray  # float32 mono
    sample_rate: int


class ASR:
    name = "asr"
    last_usage: dict = {}

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Final transcript for a finished utterance (called after endpointing)."""
        raise NotImplementedError


class LLM:
    name = "llm"
    last_usage: dict = {}

    def stream(self, messages: list[dict]) -> Iterator[str]:
        """Yield text deltas. messages: [{"role": "system|user|assistant", "content": str}]"""
        raise NotImplementedError


class TTS:
    name = "tts"
    last_usage: dict = {}

    def synthesize(self, text: str) -> Iterator[AudioChunk]:
        """Yield audio chunks. A non-streaming vendor yields one chunk per call."""
        raise NotImplementedError


class Sink:
    """Where audio goes. `measures_playback` is False when nothing is actually played."""

    name = "sink"
    measures_playback = False

    def play(self, chunk: AudioChunk) -> None:
        raise NotImplementedError


class NullSink(Sink):
    """Discards audio. Headless runs (CI, Colab) use this, so T5 is reported as unmeasured."""

    name = "null"
    measures_playback = False

    def play(self, chunk: AudioChunk) -> None:
        return None
