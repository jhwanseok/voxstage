"""Structured event log. The single source of truth for every measurement."""

from __future__ import annotations

import json
import threading
import time
from typing import Optional


def now() -> float:
    """Monotonic clock used for every duration. Never use wall time for deltas."""
    return time.monotonic()


class EventLog:
    """Append-only JSONL event log.

    Each event: session_id, turn, type, t (monotonic seconds), wall (epoch, for
    humans only), warmup flag, and a free-form data dict.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8") if path else None
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def emit(self, session_id: str, turn: int, etype: str, *, warmup: bool = False,
             t: Optional[float] = None, **data) -> dict:
        ev = {
            "session_id": session_id,
            "turn": turn,
            "type": etype,
            "t": now() if t is None else t,
            "wall": time.time(),
            "warmup": warmup,
            "data": data,
        }
        with self._lock:
            self.events.append(ev)
            if self._fh:
                self._fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
                self._fh.flush()
        return ev

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


def read_events(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
