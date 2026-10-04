"""Vendor factory. Heavy dependencies are imported only when that vendor is selected."""

from __future__ import annotations


def build(kind: str, name: str, **opts):
    if kind == "asr":
        if name == "mock":
            from .mock import MockASR
            return MockASR(**opts)
        if name == "whisper":
            from .whisper_asr import WhisperASR
            return WhisperASR(**opts)
    elif kind == "llm":
        if name == "mock":
            from .mock import MockLLM
            return MockLLM(**opts)
        if name == "gemini":
            from .gemini_llm import GeminiLLM
            return GeminiLLM(**opts)
    elif kind == "tts":
        if name == "mock":
            from .mock import MockTTS
            return MockTTS(**opts)
        if name == "melo":
            from .melo_tts import MeloTTS
            return MeloTTS(**opts)
    raise ValueError(f"unknown {kind} vendor: {name!r}")
