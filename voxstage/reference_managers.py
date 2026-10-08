"""Reference managers that fix the floor and the ceiling of the scorer (ADR 0008).

`NullDM` answers nothing, so it must score 0 percent. `OracleDM` replays the expected values of the case it is
given, so it must score 100 percent. They are test doubles for the harness, not dialogue systems.
"""

from __future__ import annotations

from .dialogue import DialogueManager, DMResult, EndCall, HandOff


class NullDM(DialogueManager):
    name = "null"

    def respond(self, state, turn_input):
        return DMResult("", state)


class OracleDM(DialogueManager):
    name = "oracle"

    def __init__(self, case, tools):
        self.case, self.tools = case, tools

    def respond(self, state, turn_input):
        expect = self.case.turns[state.turn].expect
        parts = list(expect.get("reply_contains") or []) + list((expect.get("reply_contains_any") or [])[:1])
        reply = " ".join(parts) or "ok"
        for call in expect.get("tool_calls") or []:
            self.tools.call(call["name"], call["args"])
        slots = {**state.slots, **{k: str(v) for k, v in (expect.get("slots") or {}).items()}}
        actions = tuple(HandOff("oracle") if a == "HandOff" else EndCall() for a in expect.get("actions") or [])
        return DMResult(reply, state.evolve(slots=slots, flow_id=expect.get("flow", state.flow_id)), actions)


def null_factory(ctx):
    return NullDM()


def oracle_factory(ctx):
    return OracleDM(ctx.oracle, ctx.tools)
