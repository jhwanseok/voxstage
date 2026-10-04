"""Shadow cost: what this run *would* cost at paid prices, even on free tiers.

All prices default to 0 (free tier / local). Fill a PriceTable (or pass
--prices prices.json) with current published prices to get a real estimate.
Prices change often, so none are hard-coded here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PriceTable:
    asr_per_audio_second: float = 0.0
    llm_per_1k_input_tokens: float = 0.0
    llm_per_1k_output_tokens: float = 0.0
    tts_per_1k_chars: float = 0.0

    @classmethod
    def load(cls, path: Optional[str]) -> "PriceTable":
        if not path:
            return cls()
        with open(path, encoding="utf-8") as f:
            return cls(**json.load(f))

    def to_dict(self) -> dict:
        return asdict(self)

    def usd(self, kind: str, usage: dict) -> float:
        if kind == "asr":
            return usage.get("audio_seconds", 0.0) * self.asr_per_audio_second
        if kind == "llm":
            return (usage.get("input_tokens", 0) / 1000 * self.llm_per_1k_input_tokens
                    + usage.get("output_tokens", 0) / 1000 * self.llm_per_1k_output_tokens)
        if kind == "tts":
            return usage.get("chars", 0) / 1000 * self.tts_per_1k_chars
        return 0.0
