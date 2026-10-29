"""대화로 테스트: run a validated draft on typed text with the engine's own dialogue manager.

The studio only reads the engine here (`build_manager`, `FakeApiExecutor`, the turn input types). Sessions live in this
process: at most `MAX_SESSIONS`, the oldest dropped first, and any idle longer than `IDLE_SECONDS`.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from voxstage.dialogue import EndCall, HandOff
from voxstage.rules.interpreter import build_manager
from voxstage.tools import FakeApiExecutor, ToolExecutor, ToolResult
from voxstage.turn import ButtonPress, Dtmf, Utterance

from .validation import write_tree

MAX_SESSIONS = 20
IDLE_SECONDS = 30 * 60
SHOWN_META = ("ask_misses", "verified", "caller", "calls", "parked")


class RecordingTools(ToolExecutor):
    """The fake API of API 연결, keeping each call of the current turn with its arguments and result."""

    def __init__(self, inner: FakeApiExecutor):
        self.inner, self.turn_calls = inner, []

    def call(self, tool: str, args: dict) -> ToolResult:
        result = self.inner.call(tool, args)
        self.turn_calls.append({"tool": tool, "args": dict(args), "ok": result.ok,
                                "data": dict(result.data) if result.ok else None,
                                "error": None if result.ok else result.error})
        return result


@dataclass
class ChatSession:
    id: str
    bot: str
    root: str
    manager: object
    tools: RecordingTools
    state: object
    draft_revision: int
    shared_revision: int
    flows: dict = field(default_factory=dict)   # flow id -> nodes, to show how each call's params were bound
    touched: float = field(default_factory=time.monotonic)


_SESSIONS: "OrderedDict[str, ChatSession]" = OrderedDict()
_LOCK = threading.Lock()


def _drop(s: ChatSession) -> None:
    shutil.rmtree(s.root, ignore_errors=True)


def _sweep() -> None:
    now = time.monotonic()
    for sid in [k for k, s in _SESSIONS.items() if now - s.touched > IDLE_SECONDS]:
        _drop(_SESSIONS.pop(sid))
    while len(_SESSIONS) >= MAX_SESSIONS:
        _drop(_SESSIONS.popitem(last=False)[1])


def start(bot_slug: str, domain: str, lang: str, files: dict[str, str], flows: dict, setup: dict,
          draft_revision: int, shared_revision: int) -> ChatSession:
    root = tempfile.mkdtemp(prefix="studio-chat-")
    try:
        write_tree(root, files)
        tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(root, domain, "tools.yaml")))
        manager = build_manager(root, domain, lang, tools)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    sid = uuid.uuid4().hex[:12]
    s = ChatSession(sid, bot_slug, root, manager, tools, manager.initial_state(sid, setup), draft_revision,
                    shared_revision, flows)
    with _LOCK:
        _sweep()
        _SESSIONS[sid] = s
    return s


def get(sid: str, bot_slug: str) -> ChatSession | None:
    with _LOCK:
        s = _SESSIONS.get(sid)
        if s is None or s.bot != bot_slug:
            return None
        s.touched = time.monotonic()
        _SESSIONS.move_to_end(sid)
        return s


def end(sid: str) -> None:
    with _LOCK:
        s = _SESSIONS.pop(sid, None)
    if s is not None:
        _drop(s)


def _plain(v):
    """JSON-safe copy of engine data (tuples, dates and dataclasses become lists and text)."""
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


def _action(a) -> dict:
    if isinstance(a, HandOff):
        return {"kind": "handoff", "reason": a.reason}
    if isinstance(a, EndCall):
        return {"kind": "end_call"}
    return {"kind": type(a).__name__}


def _bound(s: ChatSession, flow_ids: list, call: dict) -> dict | None:
    """How the call step that made this call names its params (`bind` or `args`), from the flows it ran in."""
    for fid in flow_ids:
        for nid, n in (s.flows.get(fid) or {}).items():
            if isinstance(n, dict) and n.get("type") == "call" and n.get("tool") == call["tool"]:
                return {"node": nid, "bind": n.get("bind") or {}, "args": n.get("args") or {}}
    return None


def turn(s: ChatSession, kind: str, text: str) -> dict:
    if kind == "digits":
        turn_input = Dtmf(text)
    elif kind == "button":
        turn_input = ButtonPress(text)
    else:
        turn_input = Utterance(text, source="typed")
    before = s.state
    s.tools.turn_calls = []
    result = s.manager.respond(before, turn_input)
    s.state = after = result.state
    flows = [f for f in (before.flow_id, after.flow_id) if f]
    calls = [{**c, "step": _bound(s, flows, c)} for c in s.tools.turn_calls]
    changed = sorted(k for k, v in after.slots.items() if before.slots.get(k) != v)
    return _plain({
        "reply": result.reply,
        "actions": [_action(a) for a in result.actions],
        "before": {"flow": before.flow_id, "node": before.node_id},
        "after": {"flow": after.flow_id, "node": after.node_id},
        "attributes": dict(after.slots),
        "changed": changed,
        "calls": calls,
        "meta": {k: after.meta[k] for k in SHOWN_META if k in after.meta},
        "trace": result.trace,
        "turn": after.turn,
    })
