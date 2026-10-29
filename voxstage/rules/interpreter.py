"""The flow interpreter: runs `flows/*.yaml` for any domain (R2, ADR 0003 and 0010).

`FlowManager` is a DialogueManager. It picks a flow from the caller's words (the triggers use the FAQ rules'
word-group language), runs nodes until it must wait for the caller or the flow ends, and falls back to the FAQ
rules when no flow applies. Node types are run by handlers in a registry, so a later step adds a node type
without touching this loop.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import voxstage_normalize as normalize
from ..dialogue import DialogueManager, DMResult, EndCall, HandOff
from ..domain_pack import DomainPack
from ..tools import ToolExecutor, ToolResult
from ..turn import ButtonPress, Dtmf, Utterance
from .expr import ExprError, MissingAttribute
from .formatters import FORMATTERS, FormatError
from .faq import FaqRuleManager
from .flows import (VERIFICATION, Flow, FlowError, Node, compile_template, gate_tools, load_flows, retry_tools,
                    risky_tools, verification_flow)
from .matching import Matcher
from .types import SESSION_ROLE, load_types
from .tokenize import Tokenizer, for_lang

ASK_MISSES = "ask_misses"   # consecutive unusable answers at the current ask (R3)
PARKED = "parked"           # flows set aside by a switch, newest last: {flow, node, slots, asked} (R6-1)
ASKED = "asked"             # answered asks of the running flow, oldest first, for `back` (R8-1)
MAIN_MENU = "main_menu"     # reserved flow_id after `cancel`: no flow runs (R8-3)
READBACK = "readback"       # the slot read back most recently, the one a correction changes (R9-1, R9-2)
CORRECTIONS = "corrections"  # corrections per slot, for the limit (R9-3)
OFFER = "offer"             # a confusion partner offered after a bare no: {slot, value} (R9-2)
FORM_SLOT = "form_slot"     # the slot a waiting form asks for (R10-3)
FORM_SAID = "form_said"     # say_when_ready items already said, per form node (R10-3)
DATE_CHOICES = "date_choices"   # the two readings of an ambiguous date, asked at the current ask (R11-2)
GATED = "gated"             # the flow stopped at a protected call while the caller is checked (R13)
VERIFIED = "verified"       # the caller passed the identity check; holds for the call (R13-2)
CALLER = "caller"           # the session role: the fields the identity check proved (ADR 0014, decision B)
CALLS = "calls"             # the data each `call` step of the running flow returned, by step id (ADR 0014)
LOCKED = "verification_locked"   # too many failed checks: no protected call for the rest of the call (R13-2)
FAILURES = "verify_failures"     # failed identity checks in this call
TOOL_FAILURES = "tool_failures"  # system errors of tools in this call, after retries (R12-4)
TIMEOUT = "timeout"              # the system error: retried, counted, unknown outcome for a risky tool (R12)
RUNTIME = (ASK_MISSES, PARKED, ASKED, DATE_CHOICES, READBACK, CORRECTIONS, OFFER, FORM_SLOT, FORM_SAID, "result",
           "faq_misses", GATED, CALLS)   # VERIFIED, LOCKED, FAILURES and TOOL_FAILURES belong to the call, kept by `cancel`
FRESH = {ASKED: [], FORM_SAID: {}, FORM_SLOT: None, CALLS: {}}   # what a flow that starts begins with   # meta written while talking; `cancel` clears it
MAX_NODES_PER_TURN = 100   # a safety net; load-time validation already rules out loops that never wait


class FlowRuntimeError(RuntimeError):
    """A flow could not run (missing data, a tool the flow was not validated against)."""


@dataclass
class Wait:
    node_id: str


@dataclass
class Done:
    node_id: str


@dataclass
class Run:
    """Working copy of one turn: handlers read and change these, the manager turns them into a new state."""
    manager: "FlowManager"
    flow: Flow
    slots: dict
    meta: dict
    out: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    trace: dict = field(default_factory=dict)

    def env(self) -> dict:
        roles: dict = {}
        for key, value in self.slots.items():   # `visitor.name` is the field `name` of the role `visitor` (ADR 0014)
            if "." in key:
                role, fld = key.split(".", 1)
                roles.setdefault(role, {})[fld] = value
        if self.meta.get(CALLER):
            roles[SESSION_ROLE] = self.meta[CALLER]
        return {**self.slots, **roles, "slots": self.slots, "customer": self.meta.get("customer", {}),
                "policy": self.meta.get("policy", {}), "result": self.meta.get("result", {}),
                "_lang": self.manager.pack.lang}


HANDLERS: dict = {}


def handler(node_type: str):
    def deco(fn: Callable):
        HANDLERS[node_type] = fn
        return fn
    return deco


@handler("say")
def run_say(run: Run, node: Node):
    run.out.append(node.data["text"].render(run.env()))
    return node.data["next"]


@handler("ask")
def run_ask(run: Run, node: Node):
    if node.data["slot"] in run.slots:   # already known (a capture or an earlier answer): do not ask again
        run.trace.setdefault("skipped_asks", []).append(node.id)
        return node.data["next"]
    run.out.append(node.data["prompt"].render(run.env()))
    return Wait(node.id)


@handler("form")
def run_form(run: Run, node: Node):
    """Say what has become sayable, then ask the first slot that is still empty (R10-3)."""
    said = {k: list(v) for k, v in (run.meta.get(FORM_SAID) or {}).items()}
    done = said.setdefault(node.id, [])
    env = run.env()
    for i, item in enumerate(node.data["say_when_ready"]):
        if i not in done and all(n in run.slots for n in item["needs"]):
            done.append(i)
            if "say" in item:
                run.out.append(item["say"].render(env))
            else:
                for notice, cond in item["notices"]:
                    if cond is None or cond.evaluate(env):
                        run.out.append(notice.text)
                        run.trace.setdefault("notices", []).append(notice.id)
    run.meta[FORM_SAID] = said
    forced = run.meta.get(FORM_SLOT)
    for spec in node.data["slots"]:
        if spec["slot"] not in run.slots or spec["slot"] == forced:
            run.meta[FORM_SLOT] = spec["slot"]
            run.out.append(spec["prompt"].render(env))
            return Wait(node.id)
    run.meta[FORM_SLOT] = None
    return node.data["next"]


def as_question(node: Node, meta: dict) -> Node:
    """A waiting form behaves as an `ask` for the slot it asks (R10-3); other nodes are returned as they are."""
    if node.type != "form":
        return node
    slot = meta.get(FORM_SLOT) or node.data["slots"][0]["slot"]
    spec = next(sp for sp in node.data["slots"] if sp["slot"] == slot)
    return Node(node.id, "ask", {**spec, "next": node.id})


@handler("confirm")
def run_confirm(run: Run, node: Node):
    run.out.append(node.data["prompt"].render(run.env()))
    return Wait(node.id)


def call_args(run: Run, node: Node) -> dict:
    """The arguments of a call: templates of `args`, and the sources of `bind` (ADR 0014). A source with no value
    yet is a missing attribute, like a template field with none (R4-2)."""
    env = run.env()
    args = {k: t.render(env) for k, t in node.data["args"].items()}
    for param, (kind, a, b) in node.data["bind"].items():
        if kind == "const":
            args[param] = a
            continue
        source = env.get(a) if kind == "role" else (run.meta.get(CALLS) or {}).get(a)
        if not isinstance(source, dict) or b not in source:
            raise MissingAttribute(f"`{a}.{b}` has no value yet")
        args[param] = str(source[b])
    return args


@handler("call")
def run_call(run: Run, node: Node):
    manager, tool = run.manager, node.data["tool"]
    if tool in manager.protected and not run.meta.get(VERIFIED):   # not before the check, in any flow (R13-1)
        return manager.gate(run, node)
    args = call_args(run, node)
    result = manager.call_tool(run, tool, args)
    run.meta["result"] = dict(result.data) if result.ok else {"error": result.error}
    if result.ok:
        run.meta[CALLS] = {**(run.meta.get(CALLS) or {}), node.id: dict(result.data)}
    if tool == manager.verifier and run.flow.role == VERIFICATION:
        if result.ok:
            run.meta[VERIFIED] = True
            run.meta[CALLER] = {f: args[f] for f in manager.caller_fields if f in args}
        elif result.error != TIMEOUT:   # a system error says nothing about the caller (R12)
            locked = manager.failed_check(run, node)
            if locked is not None:
                return locked
    return node.data["on_ok"] if result.ok else manager.tool_failed(run, node, result)


@handler("branch")
def run_branch(run: Run, node: Node):
    env = run.env()
    for cond, target in node.data["cases"]:
        if cond.evaluate(env):
            return target
    return node.data["else"]


@handler("notices")
def run_notices(run: Run, node: Node):
    env, spoken = run.env(), []
    for notice, cond in node.data["items"]:
        if cond is None or cond.evaluate(env):
            run.out.append(notice.text)
            spoken.append(notice.id)
    run.trace["notices"] = spoken
    return node.data["next"]


@handler("goto")
def run_goto(run: Run, node: Node):
    return node.data["next"]


@handler("end")
def run_end(run: Run, node: Node):
    action = node.data["action"]
    if action == "handoff":
        run.actions.append(HandOff(node.data["reason"]))
    elif action == "end_call":
        run.actions.append(EndCall())
    return Done(node.id)


def decide(extracted: Optional[str], faq) -> str:
    """What a turn at a waiting `ask` is (decision R7-4). Both results are known before this is called, so the
    outcome never depends on which one was ready first: a usable answer wins, then an FAQ side question (R7-1)."""
    if extracted is not None:
        return "answer"
    if faq is not None:
        return "side_question"
    return "reprompt"


# --- slot extraction ----------------------------------------------------------------------------------
CLOCKED = ("date", "month_start")   # extractors that need the scenario clock, `meta["now"]` (R11-2)
# Values that cannot be mistaken for the answer to another question; these captures also run on later turns (R10-1)
DISTINCT = ("choice", "date", "month_start", "day", "time_window", "duration")


def cue_windows(text: str, cues: tuple) -> list:
    """The words around each cue word: two before, two after ("order 1001", "5580으로 끝나는", "천일 주문에서")."""
    words, out = text.split(), []
    for i, w in enumerate(words):
        plain = w.lower().strip(".,!?")
        if any(plain == c or (not c.isascii() and plain.startswith(c)) for c in cues):
            out.append(" ".join(words[max(0, i - 2):i + 3]))
    return out


def extract(node: Node, turn_input, tok: Tokenizer, now=None):
    """The slot value for an `ask` node, or None when the input does not contain one. A `date` can also come back as
    `normalize.Ambiguous` (two real readings, R11-2). Spoken numbers, days and dates are read by `normalize` (R11)."""
    kind, length = node.data["extractor"], node.data["length"]
    if isinstance(turn_input, Dtmf):
        text = turn_input.digits
    elif isinstance(turn_input, Utterance):
        text = turn_input.text
    else:
        return None
    if kind == "text":
        return text.strip() or None
    lang = tok.lang
    if kind == "digits":
        groups = re.findall(r"\d+", text)
        digits = "".join(groups) if len(groups) == 1 else (groups[0] if groups else "")
        if not digits and isinstance(turn_input, Utterance):   # said digit by digit: "four eight two one"
            digits = normalize.digit_string(text, lang) or ""
        return digits if digits and (length is None or len(digits) == length) else None
    if kind == "number":
        found = normalize.numbers(text, lang)
        return str(found[0]) if found else None
    if kind in CLOCKED:
        if now is None:
            raise MissingAttribute(f"the `{kind}` extractor needs the clock (`now` in the request meta)")
        found = normalize.date(text, lang, now) if kind == "date" else normalize.month_start(text, lang, now)
        if isinstance(found, normalize.Ambiguous):
            return found
        return found.iso if found else None
    if kind == "day":
        day = normalize.day_of_month(text, lang)
        return str(day) if day else None
    if kind == "time_window":
        return normalize.time_window(text, lang)
    if kind == "duration":
        days = normalize.duration_days(text, lang)
        return str(days) if days else None
    if kind == "choice":
        analysis = tok.analyze(text)
        return next((value for word, value in node.data["choices"] if tok.has(analysis, word)), None)
    return None


class FlowManager(DialogueManager):
    name = "flows"

    def __init__(self, pack: DomainPack, tools: ToolExecutor, flows: Optional[dict] = None,
                 tokenizer: Optional[Tokenizer] = None, faq: Optional[FaqRuleManager] = None, types=None):
        self.pack, self.tools, self.types = pack, tools, types
        # the fields of the session role `caller` that the identity check fills (ADR 0014, decision B)
        self.caller_fields = (tuple(types.fields_of(types.session_roles[SESSION_ROLE]))
                              if types and SESSION_ROLE in types.session_roles else ())
        self.tok = tokenizer or for_lang(pack.lang)
        self.flows = flows if flows is not None else (pack.flows or {})
        for flow in self.flows.values():
            for node in flow.nodes.values():
                if node.type not in HANDLERS:
                    raise FlowError(f"{flow.path}: node {node.id}: no handler registered for `{node.type}`")
                if node.type == "confirm" and pack.confirm_words is None:
                    raise FlowError(f"{flow.path}: node {node.id}: a confirm node needs rules/confirm.yaml in the pack")
        self.matcher = Matcher([f.triggers for f in self.flows.values() if f.triggers is not None], self.tok)
        self.buttons = {b: f.id for f in self.flows.values() for b in f.buttons}
        self.commands = Matcher(pack.commands, self.tok) if pack.commands else None
        self.readback = {slot: compile_template("{value | " + call + "}", f"readback_slots.yaml: {slot}",
                                                frozenset({"value"}))
                         for slot, call in pack.readback.items()}
        self.faq = faq if faq is not None else (
            FaqRuleManager(pack, self.tok) if pack.patterns and pack.fallback else None)
        self.protected, self.verifier = gate_tools(pack.tools_path) if pack.tools_path else (frozenset(), None)
        self.check = verification_flow(self.flows)
        self.risky = risky_tools(pack.tools_path) if pack.tools_path else frozenset()
        self.retry = retry_tools(pack.tools_path) if pack.tools_path else frozenset()

    # -- entry point --------------------------------------------------------------------------------
    def respond(self, state, turn_input):
        try:
            return self._respond(state, turn_input)
        except MissingAttribute as exc:   # e.g. a date extractor without a clock: fail visibly (R4-2)
            return DMResult(self.pack.missing_reply, state, (HandOff("missing_attribute"),),
                            {"failed": state.node_id, "error": str(exc)})

    def _respond(self, state, turn_input):
        if isinstance(turn_input, Utterance) and self.commands is not None:   # first, in every state (R8-5)
            command, match = self.commands.match(turn_input.text)
            if command is not None:
                return self._command(command.id, state, {"command": command.id, "command_match": match})
        flow = self.flows.get(state.flow_id) if state.flow_id else None
        current = as_question(flow.nodes[state.node_id], state.meta) \
            if flow is not None and state.node_id in flow.nodes else None
        waiting = current is not None and current.type in ("ask", "confirm")
        if waiting and state.meta.get(OFFER):   # the answer to "did you mean 30?" (R9-2)
            return self._answer_offer(flow, state, turn_input)
        if waiting and isinstance(turn_input, Utterance):   # corrections come right after the commands (R9-4)
            corrected = self._correction(flow, state, turn_input)
            if corrected is not None:
                return corrected
        if waiting and current.type == "confirm":
            return self._answer_confirm(flow, state, turn_input)   # nothing breaks in here (R7-12)
        if waiting and current.type == "ask":
            if current.data["interruptible"]:   # interrupts first, then the answer (R6-5)
                switched = self._switch(flow, state, turn_input)
                if switched is not None:
                    return switched
            return self._answer_ask(flow, state, turn_input)
        if isinstance(turn_input, ButtonPress) and turn_input.button_id in self.buttons:
            flow = self.flows[self.buttons[turn_input.button_id]]
            run = Run(self, flow, self._prefill(flow, {}, state.meta), {**state.meta, **FRESH},
                      trace={"flow": flow.id, "button": turn_input.button_id})
            return self._run(run, state, flow.start)
        if isinstance(turn_input, Utterance) and self.flows:
            trigger, trace = self.matcher.match(turn_input.text)
            if trigger is not None:
                flow = self.flows[trigger.id]
                captured = self._capture(flow, turn_input, state.meta.get("now"))
                run = Run(self, flow, self._prefill(flow, captured, state.meta), {**state.meta, **FRESH},
                          trace={"flow": flow.id, "trigger": trace, "captured": dict(captured)})
                return self._run(run, state, flow.start)
        if self.faq is not None:
            return self.faq.respond(state, turn_input)
        return DMResult(self.pack.wording.get("flow.no_flow", "I can't help with that."), state,
                        trace={"rule": "no_flow"})

    def _command(self, name: str, state, trace: dict) -> DMResult:
        """cancel, back and agent (R8-3, R8-1, R8-4). None of them calls a tool."""
        wording = self.pack.wording
        if name == "cancel":   # keep what came with the request, clear what the talk produced
            if state.meta.get(PARKED):
                trace["parked_dropped"] = [p["flow"] for p in state.meta[PARKED]]
            meta = {k: v for k, v in state.meta.items() if k not in RUNTIME}
            new = state.evolve(flow_id=MAIN_MENU, node_id=None, slots={}, meta=meta)
            return DMResult(wording.get("command.cancelled", "All right, I have cancelled that."), new, trace=trace)
        if name == "agent":
            meta = dict(state.meta)
            if meta.get(PARKED):
                trace["parked_dropped"] = [p["flow"] for p in meta[PARKED]]
                meta[PARKED] = []
            return DMResult(wording.get("command.agent", "I'll connect you to an agent."), state.evolve(meta=meta),
                            (HandOff("caller_request"),), trace)
        flow = self.flows.get(state.flow_id) if state.flow_id else None
        node = flow.nodes.get(state.node_id) if flow is not None else None
        node = as_question(node, state.meta) if node is not None else None
        if node is None or node.type not in ("ask", "confirm"):   # back with nothing to go back in
            return DMResult(wording.get("flow.no_flow", "I can't help with that."), state, trace=trace)
        asked = list(state.meta.get(ASKED, ()))
        entry = asked.pop() if asked else None   # at the first question: the same question
        meta = {**state.meta, ASKED: asked, ASK_MISSES: 0}
        if entry is None:
            target = node
        else:   # "form#slot" for a question asked by a form
            node_id, _, slot = entry.partition("#")
            if slot:
                meta[FORM_SLOT] = slot
            target = as_question(flow.nodes[node_id], meta)
        run = Run(self, flow, dict(state.slots), meta, trace={**trace, "flow": flow.id, "back_to": entry or node.id})
        new = state.evolve(node_id=target.id, meta=run.meta)   # the slot stays until a new answer (R8-1)
        return DMResult(target.data["prompt"].render(run.env()), new, trace=run.trace)

    def _switch(self, flow: Flow, state, turn_input) -> Optional[DMResult]:
        """Another flow breaks in: a button of another flow (R6-6), or the `interrupts:` of another flow (R6-4).
        The running flow is parked (R6-1); only the new flow's `carry` slots are copied from it (R6-2)."""
        trace: dict = {}
        if isinstance(turn_input, ButtonPress) and self.buttons.get(turn_input.button_id, flow.id) != flow.id:
            target, by = self.flows[self.buttons[turn_input.button_id]], "button"
            trace["button"] = turn_input.button_id
        elif isinstance(turn_input, Utterance):
            others = [f.interrupts for f in self.flows.values() if f.interrupts is not None and f.id != flow.id]
            if not others:
                return None
            hit, match = Matcher(others, self.tok).match(turn_input.text)   # priority, then specificity (R6-3)
            if hit is None:
                return None
            target, by = self.flows[hit.id], "interrupt"
            trace["interrupt"] = match
        else:
            return None
        parked = [*state.meta.get(PARKED, ()), {"flow": flow.id, "node": state.node_id, "slots": dict(state.slots),
                                                "asked": list(state.meta.get(ASKED, ())),
                                                "form_slot": state.meta.get(FORM_SLOT),
                                                "form_said": dict(state.meta.get(FORM_SAID) or {})}]
        if len(parked) > self.pack.max_parked:   # the oldest goes; nothing is said (R7-3)
            trace["parked_dropped"] = [p["flow"] for p in parked[:-self.pack.max_parked]]
            parked = parked[-self.pack.max_parked:]
        carried = {slot: state.slots[slot] for slot in target.carry if slot in state.slots}
        captured = self._capture(target, turn_input, state.meta.get("now"))
        run = Run(self, target, self._prefill(target, {**carried, **captured}, state.meta),
                  {**state.meta, **FRESH, PARKED: parked, ASK_MISSES: 0},
                  trace={"flow": target.id, "switch": {"from": flow.id, "to": target.id, "by": by}, **trace,
                         "carried": carried, "captured": captured})
        return self._run(run, state, target.start)

    @staticmethod
    def _prefill(flow: Flow, slots: dict, meta: dict) -> dict:
        """Slots still empty when a flow starts take the caller's record (`prefill:`, R13); what was said wins."""
        customer = meta.get("customer") or {}
        return {**{slot: str(customer[attr]) for slot, attr in flow.prefill if attr in customer}, **slots}

    def _capture(self, flow: Flow, turn_input, now=None, later: bool = False, skip: Optional[str] = None) -> dict:
        """Slots the first utterance already contains ("How much is the plus plan" fills `plan`)."""
        out = {}
        if not isinstance(turn_input, Utterance):
            return out
        for slot, spec in flow.captures:
            if slot == skip or (later and spec["extractor"] not in DISTINCT and not spec.get("cue")):
                continue   # a bare number never fills another slot after the first words (R10-1)
            node = Node(f"capture:{slot}", "capture", spec)
            if spec.get("cue"):
                value = next((v for v in (extract(node, Utterance(w), self.tok, now)
                                          for w in cue_windows(turn_input.text, spec["cue"])) if v is not None), None)
            else:
                value = extract(node, turn_input, self.tok, now)
            if value is not None and not isinstance(value, normalize.Ambiguous):   # two readings: the ask will ask
                out[slot] = value
        return out

    def _answer_ask(self, flow: Flow, state, turn_input):
        node = as_question(flow.nodes[state.node_id], state.meta)
        slot = node.data["slot"]
        keypad_only = slot in self.pack.sensitive_slots
        spoken_at_keypad = keypad_only and isinstance(turn_input, Utterance)
        value = None if spoken_at_keypad else extract(node, turn_input, self.tok, state.meta.get("now"))
        choices = state.meta.get(DATE_CHOICES)
        if choices:   # the caller was asked which of two dates (R11-2): keypad 1 / 2 or one of the dates
            if isinstance(turn_input, Dtmf) and turn_input.digits in ("1", "2"):
                value = choices[int(turn_input.digits) - 1]
            elif value not in choices:
                value = None
        elif isinstance(value, normalize.Ambiguous):
            return self._ask_which_date(node, state, value)
        faq = None   # evaluated every turn, so turns where both match show in the trace (R7-4)
        if self.faq is not None and isinstance(turn_input, Utterance):
            faq, _ = self.faq.match(turn_input.text)
        changed = self._other_slots(flow, state, turn_input, slot) if isinstance(turn_input, Utterance) else {}
        if value is not None:   # the words went to the asked slot first; only choice words also fill others
            kinds = {s_: spec["extractor"] for s_, spec in flow.captures}
            changed = {k: v for k, v in changed.items() if kinds.get(k) == "choice"}
        if value is None and changed:   # only other slots were given: take them, ask again, not a miss (R10-1)
            return self._take_other_slots(flow, state, changed)
        decided = decide(value, faq)
        run = Run(self, flow, {**state.slots, **changed}, {**state.meta},
                  trace={"flow": flow.id, "ask": node.id, "faq": faq.id if faq else None, "decided": decided})
        if changed:
            run.trace["captured"] = dict(changed)
        if decided == "side_question":   # answer it, ask the pending question again; nothing else moves (R7-2)
            run.trace["extracted"] = None
            parts = [self.faq.pack.answers[faq.id], node.data["prompt"].render(run.env())]
            if spoken_at_keypad and re.search(r"\d", turn_input.text) and self.pack.ask is not None:
                parts.insert(0, self.pack.ask.keypad_reply)   # digits were spoken: remind first (R7-11, R3-1)
                run.trace["keypad_only"] = True
            return DMResult(" ".join(parts), state, trace=run.trace)
        if decided == "reprompt":
            return self._unusable(flow, node, state, run, spoken_at_keypad)
        run.slots[slot] = value
        run.trace["extracted"] = {slot: value}
        run.meta.pop(DATE_CHOICES, None)
        asked_as = f"{node.id}#{slot}" if flow.nodes[node.id].type == "form" else node.id
        run.meta[ASKED] = [*state.meta.get(ASKED, ()), asked_as]   # for `back` (R8-1)
        run.meta[FORM_SLOT] = None
        return self._run(run, state, node.data["next"])

    def confirm_answer(self, turn_input) -> str:
        """yes, no or unclear: keypad 1 and 2, or exactly one kind of word from `rules/confirm.yaml`."""
        if isinstance(turn_input, Dtmf):
            return {"1": "yes", "2": "no"}.get(turn_input.digits, "unclear")
        if not isinstance(turn_input, Utterance) or self.pack.confirm_words is None:
            return "unclear"
        analysis = self.tok.analyze_answer(turn_input.text)
        yes_words, no_words = self.pack.confirm_words
        yes = any(self.tok.has(analysis, w) for w in yes_words)
        no = any(self.tok.has(analysis, w) for w in no_words)
        return "yes" if yes and not no else "no" if no and not yes else "unclear"

    def _answer_confirm(self, flow: Flow, state, turn_input):
        node = flow.nodes[state.node_id]
        if isinstance(turn_input, Utterance):   # "make it fourteen days": change the slot, confirm again (R10-1)
            changed = self._other_slots(flow, state, turn_input, None)
            if changed:
                return self._take_other_slots(flow, state, changed)
        answer = self.confirm_answer(turn_input)
        run = Run(self, flow, dict(state.slots), {**state.meta}, trace={"flow": flow.id, "confirm": answer})
        role = node.data["role_default"]
        if answer == "yes":
            if role:   # the same person: copy the source role's fields (ADR 0014)
                source = {r: d for r, _, d in flow.roles}[role]
                run.slots.update({f"{role}.{k.split('.', 1)[1]}": v for k, v in state.slots.items()
                                  if k.startswith(source + ".")})
                run.trace["role_default"] = {"role": role, "from": source}
            return self._run(run, state, node.data["on_yes"])
        if answer == "no":   # the risky tool is not called
            if not role:
                run.out.append(self.pack.wording.get("confirm.declined", "All right, I have not done it."))
            return self._run(run, state, node.data["on_no"])
        return self._unusable(flow, node, state, run, False)

    def _other_slots(self, flow: Flow, state, turn_input, asked: Optional[str]) -> dict:
        """Captured values for slots other than the asked one that differ from what is filled (R10-1)."""
        found = self._capture(flow, turn_input, state.meta.get("now"), later=True, skip=asked)
        return {k: v for k, v in found.items() if state.slots.get(k) != v}

    def _take_other_slots(self, flow: Flow, state, changed: dict) -> DMResult:
        """Set the slots, read back what is listed, and ask the current question (or confirm) again."""
        node = as_question(flow.nodes[state.node_id], state.meta)
        run = Run(self, flow, {**state.slots, **changed}, {**state.meta, ASK_MISSES: 0},
                  trace={"flow": flow.id, "captured": dict(changed)})
        run.out.append(node.data["prompt"].render(run.env()))
        self._read_back(run, state.slots)
        return DMResult(" ".join(run.out), state.evolve(slots=run.slots, meta=run.meta), trace=run.trace)

    def _ask_which_date(self, node: Node, state, found) -> DMResult:
        """Two real readings: name both, numbered, and wait; this is not a miss (R11-2)."""
        lang = self.pack.lang
        write = FORMATTERS["date"].fn
        lead = self.pack.wording.get("date.ambiguous", "Which date do you mean?")
        reply = f"{lead} 1: {write(found.first, lang)}, 2: {write(found.second, lang)}."
        meta = {**state.meta, DATE_CHOICES: [found.first, found.second]}
        trace = {"flow": state.flow_id, "ask": node.id, "ambiguous": [found.first, found.second], "rule": found.rule}
        return DMResult(reply, state.evolve(meta=meta), trace=trace)

    def _unusable(self, flow: Flow, node: Node, state, run: Run, spoken_at_keypad: bool):
        """No usable answer: re-ask, and after the configured number of re-prompts hand off or end the call."""
        policy = self.pack.ask
        misses = int(state.meta.get(ASK_MISSES, 0)) + 1
        new = state.evolve(meta={**state.meta, ASK_MISSES: misses})
        run.trace.update(extracted=None, misses=misses, keypad_only=spoken_at_keypad)
        if policy is None:   # no policy in the pack: just ask again
            return DMResult(node.data["prompt"].render(run.env()), new, trace=run.trace)
        if misses > policy.max_reprompts:
            action = HandOff("input_failed") if policy.on_exceed == "handoff" else EndCall()
            return DMResult(policy.exceed_reply, new, (action,), {**run.trace, "escalated": policy.on_exceed})
        lead = policy.keypad_reply if spoken_at_keypad else policy.invalid_reply
        return DMResult(f"{lead} {node.data['prompt'].render(run.env())}", new, trace=run.trace)

    # -- tool failures (R12) ------------------------------------------------------------------------------
    def call_tool(self, run: Run, tool: str, args: dict) -> ToolResult:
        """One call, and once more after a timeout when the tool declares `retry: 1`. An answer slower than
        `timeout_ms` is a timeout (R12-1, R12-5)."""
        policy = self.pack.tool_policy
        for attempt in range(2 if tool in self.retry else 1):
            result = self.tools.call(tool, args)
            if result.delay_ms > policy.timeout_ms:
                result = ToolResult(False, error=TIMEOUT, delay_ms=result.delay_ms)
            record = {"tool": tool, "args": args, "error": result.error}
            if result.delay_ms:
                record["delay_ms"] = result.delay_ms
            run.trace.setdefault("calls", []).append(record)
            if result.error != TIMEOUT:
                break
            if attempt == 0 and tool in self.retry:
                run.trace.setdefault("call_policy", []).append("retried")
        return result

    def tool_failed(self, run: Run, node: Node, result: ToolResult):
        """Where a failed call goes: a risky timeout and the failure limit hand off; otherwise the flow's
        `on_error`, or `call.failed` and the end (R12-2 to R12-4)."""
        wording, policy = self.pack.wording, self.pack.tool_policy
        if result.error == TIMEOUT:
            if node.data["tool"] in self.risky:   # it may have gone through: a person must look (R12-3)
                run.trace.setdefault("call_policy", []).append("unconfirmed")
                run.out.append(wording.get("call.unconfirmed", "I can't confirm whether that went through. "
                                                               "Please don't try again; let me connect you to an agent."))
                run.actions.append(HandOff("outcome_unknown"))
                return Done(node.id)
            failures = int(run.meta.get(TOOL_FAILURES, 0)) + 1
            run.meta[TOOL_FAILURES] = failures
            if failures >= policy.max_failures:
                run.trace.setdefault("call_policy", []).append("exceeded")
                run.out.append(wording.get("call.exceed", "It still isn't working. Let me connect you to an agent."))
                run.actions.append(HandOff("tool_failed") if policy.on_exceed == "handoff" else EndCall())
                return Done(node.id)
            if run.flow.role == VERIFICATION:   # not a failed check; the stopped flow is dropped
                run.meta.pop(GATED, None)
                return self._default_failure(run, node)
        if node.data["on_error"] is None:
            return self._default_failure(run, node)
        return node.data["on_error"]

    def _default_failure(self, run: Run, node: Node) -> Done:
        run.trace.setdefault("call_policy", []).append("default wording")
        run.out.append(self.pack.wording.get("call.failed", "I can't do that right now. Please try again later."))
        return Done(node.id)

    # -- identity gate (R13) ------------------------------------------------------------------------------
    def gate(self, run: Run, node: Node):
        """A protected call before the check: keep the running flow aside and run the verification flow, or, when
        the call is locked, refuse and hand off. Nothing is called (R13-1, R13-2)."""
        if run.meta.get(LOCKED) or self.check is None:
            run.trace["gate"] = {"tool": node.data["tool"], "result": "locked"}
            return self._lock(run, node)
        run.meta[GATED] = {"flow": run.flow.id, "node": node.id, "slots": dict(run.slots),
                           "asked": list(run.meta.get(ASKED, ())), "form_slot": run.meta.get(FORM_SLOT),
                           "form_said": dict(run.meta.get(FORM_SAID) or {})}
        carried = {slot: run.slots[slot] for slot in self.check.carry if slot in run.slots}
        run.trace["gate"] = {"tool": node.data["tool"], "flow": run.flow.id}
        run.flow, run.slots = self.check, self._prefill(self.check, carried, run.meta)
        run.meta.update(FRESH)
        return self.check.start

    def failed_check(self, run: Run, node: Node):
        """A failed check: count it; at the limit lock the call, else empty the answers so they are asked again."""
        failures = int(run.meta.get(FAILURES, 0)) + 1
        run.meta[FAILURES] = failures
        gated = run.meta.get(GATED)
        own = self.flows[gated["flow"]].max_attempts if gated and gated["flow"] in self.flows else None
        limit = own if own is not None else self.pack.verification.max_attempts
        run.trace["verification"] = {"failures": failures, "limit": limit}
        if failures >= limit:
            run.meta[LOCKED] = True
            run.meta.pop(GATED, None)
            run.trace["verification"]["result"] = "locked"
            return self._lock(run, node)
        for entry in run.meta.get(ASKED, ()):   # the caller enters the details again; nothing says which was wrong
            asked = run.flow.nodes[entry.partition("#")[0]]
            run.slots.pop(entry.partition("#")[2] or asked.data["slot"], None)
        run.meta[ASKED] = []
        return None

    def _lock(self, run: Run, node: Node) -> Done:
        run.out.append(self.pack.wording.get("verify.locked", "I couldn't verify your identity. "
                                                                 "Let me connect you to an agent."))
        exceed = self.pack.verification.on_exceed
        run.actions.append(HandOff("verification_failed") if exceed == "handoff" else EndCall())
        return Done(node.id)

    # -- corrections (R9) ---------------------------------------------------------------------------------
    def _correction(self, flow: Flow, state, turn_input) -> Optional[DMResult]:
        """"No, I said thirty": the slot read back most recently takes the number that differs from its value."""
        slot = state.meta.get(READBACK)
        if self.pack.correction is None or slot not in state.slots or slot not in flow.slots:
            return None
        analysis = self.tok.analyze_answer(turn_input.text)   # keeps 아니요 (R9-5)
        if Matcher((self.pack.correction,), self.tok).score(self.pack.correction, turn_input.text, analysis) is None:
            return None
        node = as_question(flow.nodes[state.node_id], state.meta)
        found = [str(n) for n in normalize.numbers(turn_input.text, self.pack.lang)]
        if node.type == "confirm" and not found:   # a bare no at a confirm is a decline, not a correction
            return None
        current = state.slots[slot]
        new = list(dict.fromkeys(n for n in found if n != current))
        trace = {"flow": flow.id, "correction": {"slot": slot, "from": current, "heard": found}}
        counts = dict(state.meta.get(CORRECTIONS, {}))
        counts[slot] = counts.get(slot, 0) + 1
        meta = {**state.meta, CORRECTIONS: counts}
        policy = self.pack.correction_policy
        if policy is not None and counts[slot] > policy.max_corrections:   # (R9-3)
            action = HandOff("correction_failed") if policy.on_exceed == "handoff" else EndCall()
            trace["correction"]["result"] = "limit"
            reply = self.pack.ask.exceed_reply if self.pack.ask else "Let me connect you to an agent."
            return DMResult(reply, state.evolve(meta=meta), (action,), trace)
        if len(new) == 1:
            trace["correction"]["result"] = new[0]
            return self._set_corrected(flow, state.evolve(meta=meta), slot, new[0], trace)
        partner = self.pack.confusions.get(current) if not found else None
        if partner is not None:   # a bare no: offer the confusable partner once
            trace["correction"]["result"] = "offer"
            meta[OFFER] = {"slot": slot, "value": partner}
            shown = self.readback[slot].render({"value": partner, "_lang": self.pack.lang}) if slot in self.readback else partner
            reply = self.pack.wording.get("correction.offer", "Did you mean {value}?").replace("{value}", shown)
            return DMResult(reply, state.evolve(meta=meta), trace=trace)
        trace["correction"]["result"] = "ask again"
        return self._ask_slot_again(flow, state.evolve(meta=meta), slot, trace)

    def _answer_offer(self, flow: Flow, state, turn_input) -> DMResult:
        offer = state.meta[OFFER]
        meta = {k: v for k, v in state.meta.items() if k != OFFER}
        trace = {"flow": flow.id, "offer": dict(offer)}
        if self.confirm_answer(turn_input) == "yes":
            return self._set_corrected(flow, state.evolve(meta=meta), offer["slot"], offer["value"], trace)
        return self._ask_slot_again(flow, state.evolve(meta=meta), offer["slot"], trace)   # (R9-3)

    def _set_corrected(self, flow: Flow, state, slot: str, value: str, trace: dict) -> DMResult:
        """The slot takes the new value; it is read back and the current question is asked again with it."""
        run = Run(self, flow, {**state.slots, slot: value}, {**state.meta, ASK_MISSES: 0}, trace=trace)
        node = as_question(flow.nodes[state.node_id], state.meta)
        run.out.append(node.data["prompt"].render(run.env()))
        self._read_back(run, state.slots)
        new = state.evolve(slots=run.slots, meta=run.meta)
        return DMResult(" ".join(run.out), new, trace=run.trace)

    def _ask_slot_again(self, flow: Flow, state, slot: str, trace: dict) -> DMResult:
        """An odd correction: the slot's own question again; the old value stays until a new answer (R9-3)."""
        meta = {**state.meta, ASK_MISSES: 0}
        ask = next((n for n in flow.nodes.values() if n.type == "ask" and n.data["slot"] == slot), None)
        if ask is None:   # a form question (R10-3)
            form = next((n for n in flow.nodes.values() if n.type == "form"
                         and any(sp["slot"] == slot for sp in n.data["slots"])), None)
            if form is not None:
                meta[FORM_SLOT] = slot
                ask = as_question(form, meta)
        if ask is None:
            ask = as_question(flow.nodes[state.node_id], state.meta)
        run = Run(self, flow, dict(state.slots), meta, trace={**trace, "ask_again": ask.id})
        new = state.evolve(node_id=ask.id, meta=run.meta)
        return DMResult(ask.data["prompt"].render(run.env()), new, trace=run.trace)

    def _read_back(self, run: Run, before: dict) -> None:
        """Every read-back slot whose value changed this turn leads the reply with its value (R9-1)."""
        said = []
        for slot, template in self.readback.items():
            if slot in run.slots and run.slots[slot] != before.get(slot):
                value = template.render({"value": run.slots[slot], "_lang": self.pack.lang})
                said.append(self.pack.wording.get("readback", "{value}.").replace("{value}", value))
                run.meta[READBACK] = slot
                run.trace.setdefault("readback", []).append(slot)
        run.out[:0] = said

    def _run(self, run: Run, state, node_id: str):
        for _ in range(MAX_NODES_PER_TURN):
            node = run.flow.nodes[node_id]
            try:
                outcome = HANDLERS[node.type](run, node)
            except (MissingAttribute, FormatError) as exc:   # fail visibly: apology, then a person (decision R4-2)
                run.trace.update(failed=node_id, error=str(exc))
                self._drop_parked(run)
                new = state.evolve(flow_id=run.flow.id, node_id=node_id, slots=run.slots, meta=run.meta)
                return DMResult(self.pack.missing_reply, new, (HandOff("missing_attribute"),), run.trace)
            except ExprError as exc:
                raise FlowRuntimeError(f"{run.flow.path}: node {node_id}: {exc}") from exc
            if isinstance(outcome, Done) and run.flow.role == VERIFICATION and not run.actions \
                    and run.meta.get(VERIFIED) and run.meta.get(GATED):   # checked: the stopped call goes on (R13)
                gated = run.meta.pop(GATED)
                run.flow, run.slots = self.flows[gated["flow"]], dict(gated["slots"])
                run.meta.update({ASKED: gated["asked"], FORM_SLOT: gated["form_slot"], FORM_SAID: gated["form_said"]})
                run.trace["resumed_after_check"] = {"flow": gated["flow"], "node": gated["node"]}
                node_id = gated["node"]
                continue
            if isinstance(outcome, (Wait, Done)):
                self._read_back(run, state.slots if state.flow_id == run.flow.id else {})
            if isinstance(outcome, Done) and run.meta.get(PARKED):
                if run.actions:   # a person or the end of the call takes over: nothing to come back to (R7-5)
                    self._drop_parked(run)
                else:
                    return self._resume(run, state)
            if isinstance(outcome, (Wait, Done)):
                run.meta[ASK_MISSES] = 0
                new = state.evolve(flow_id=run.flow.id, node_id=outcome.node_id, slots=run.slots, meta=run.meta)
                return DMResult(" ".join(run.out), new, tuple(run.actions), run.trace)
            node_id = outcome
        raise FlowRuntimeError(f"{run.flow.path}: more than {MAX_NODES_PER_TURN} nodes in one turn")


    def _drop_parked(self, run: Run) -> None:
        if run.meta.get(PARKED):
            run.trace["parked_dropped"] = run.trace.get("parked_dropped", []) + [p["flow"] for p in run.meta[PARKED]]
            run.meta[PARKED] = []

    def _resume(self, run: Run, state) -> DMResult:
        """The switched-in flow ended without an action: the newest parked flow asks its pending question again,
        with the slots it had (R7-5, R7-2)."""
        *rest, top = run.meta[PARKED]
        flow = self.flows[top["flow"]]
        meta = {**run.meta, PARKED: rest, ASK_MISSES: 0, ASKED: list(top.get("asked", ())),
                FORM_SLOT: top.get("form_slot"), FORM_SAID: dict(top.get("form_said") or {})}
        node = as_question(flow.nodes[top["node"]], meta)
        back = Run(self, flow, dict(top["slots"]), meta)
        run.out.append(node.data["prompt"].render(back.env()))
        run.trace["resumed"] = {"flow": flow.id, "node": node.id}
        new = state.evolve(flow_id=flow.id, node_id=node.id, slots=top["slots"], meta=meta)
        return DMResult(" ".join(run.out), new, tuple(run.actions), run.trace)


def build_manager(domains_dir: str, domain: str, lang: str, tools: ToolExecutor) -> FlowManager:
    pack = DomainPack.load(domains_dir, domain, lang)
    types_path = os.path.join(domains_dir, domain, "types.yaml")
    types = load_types(types_path) if os.path.exists(types_path) else None
    flows = load_flows(f"{pack.base_dir}/flows", pack.tools_path, pack.sensitive_slots, pack.notices, types)
    return FlowManager(pack, tools, flows, types=types)


def default_factory(ctx):
    """`python -m voxstage.evaluate run voxstage.rules.interpreter:default_factory`"""
    from ..evaluate import DEFAULT_DOMAINS_DIR
    return build_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, ctx.tools)
