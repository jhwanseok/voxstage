"""What a dialogue turn can receive: speech (already transcribed), keypad digits, or a button.

Design: a tagged union of frozen value objects (see docs/decisions/0001-turn-input-model.md).
Adding an input kind means adding one dataclass, extending `TurnInput`, and handling it in
`describe`. `describe` raises on anything else, so a forgotten case fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class Utterance:
    """Spoken (or typed) text. `source` records where it came from; `confidence` is the
    ASR's own score when the vendor provides one, else None."""

    text: str
    source: str = "asr"  # "asr" | "typed"
    confidence: Optional[float] = None


@dataclass(frozen=True)
class Dtmf:
    """Keypad digits entered during a call. Deterministic: no recognition error."""

    digits: str


@dataclass(frozen=True)
class ButtonPress:
    """A visual/ARS button. `value` carries the payload when the button has one."""

    button_id: str
    value: Optional[str] = None


TurnInput = Union[Utterance, Dtmf, ButtonPress]


def describe(turn_input: TurnInput) -> dict:
    """Log-friendly summary of an input, used as event data."""
    match turn_input:
        case Utterance(text=text, source=source, confidence=confidence):
            return {"kind": "utterance", "text": text, "source": source, "confidence": confidence}
        case Dtmf(digits=digits):
            return {"kind": "dtmf", "digits": digits}
        case ButtonPress(button_id=button_id, value=value):
            return {"kind": "button", "button_id": button_id, "value": value}
        case _:
            raise TypeError(f"unsupported turn input: {type(turn_input).__name__}")
