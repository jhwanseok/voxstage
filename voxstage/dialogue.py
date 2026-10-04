"""The DialogueManager contract shared by every stage (rule, hybrid, LLM, agent).

A manager is stateless: `respond(state, turn_input)` returns a reply and a *new* state.
It never mutates the state it was given, so any session can be replayed from the event log
and two managers can be compared on identical inputs
(see docs/decisions/0002-dialogue-manager-contract.md).

Open question (decide before S3): `reply` is a complete string, so an LLM-backed manager
cannot expose first-token timing through this contract yet. See ADR 0002.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from .events import EventLog, now
from .turn import TurnInput, describe


@dataclass(frozen=True)
class DialogueState:
    """All conversation state, as data. Managers return updated copies via `evolve`."""

    session_id: str
    turn: int = 0
    flow_id: Optional[str] = None
    node_id: Optional[str] = None
    slots: dict = field(default_factory=dict)
    history: tuple = ()  # ((role, text), ...) for the LLM-style managers
    meta: dict = field(default_factory=dict)

    def evolve(self, **changes) -> "DialogueState":
        """Copy with changes. Containers are copied so the old state can never be altered."""
        if "slots" in changes:
            changes["slots"] = dict(changes["slots"])
        if "meta" in changes:
            changes["meta"] = dict(changes["meta"])
        return replace(self, **changes)


@dataclass(frozen=True)
class HandOff:
    """Action: transfer to a human agent."""

    reason: str


@dataclass(frozen=True)
class EndCall:
    """Action: the conversation is finished."""


Action = HandOff | EndCall


@dataclass(frozen=True)
class DMResult:
    reply: str
    state: DialogueState
    actions: tuple = ()
    trace: dict = field(default_factory=dict)  # why this reply (rule id, LLM usage, ...)


class DialogueManager:
    """Base contract. Subclasses implement `respond` and must not mutate `state`."""

    name = "dm"

    def initial_state(self, session_id: str) -> DialogueState:
        return DialogueState(session_id=session_id)

    def respond(self, state: DialogueState, turn_input: TurnInput) -> DMResult:
        raise NotImplementedError


def step(dm: DialogueManager, state: DialogueState, turn_input: TurnInput, *,
         log: Optional[EventLog] = None, warmup: bool = False) -> DMResult:
    """Run one dialogue turn and record it. The only place that emits dialogue events.

    Events: `input` (what came in), `dm_request`, `dm_response` (reply, actions, trace,
    state summary). Durations come from the event timestamps, as everywhere else.
    """
    log = log or EventLog()

    def emit(etype, **data):
        return log.emit(state.session_id, state.turn, etype, warmup=warmup, **data)

    started = now()
    emit("input", **describe(turn_input))  # describe() also rejects unknown input types
    emit("dm_request", dm=dm.name)
    result = dm.respond(state, turn_input)
    emit("dm_response", dm=dm.name, reply=result.reply,
         actions=[type(a).__name__ for a in result.actions], trace=result.trace,
         slots=dict(result.state.slots), flow_id=result.state.flow_id,
         node_id=result.state.node_id, wall_s=now() - started)
    # `step` owns the turn counter, so managers never touch it.
    return DMResult(
        reply=result.reply,
        state=result.state.evolve(turn=state.turn + 1),
        actions=result.actions,
        trace=result.trace,
    )
