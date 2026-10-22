"""The flow interpreter: runs `flows/*.yaml` for any domain (R2, ADR 0003 and 0010).

`FlowManager` is a DialogueManager. It picks a flow from the caller's words (the triggers use the FAQ rules'
word-group language), runs nodes until it must wait for the caller or the flow ends, and falls back to the FAQ
rules when no flow applies. Node types are run by handlers in a registry, so a later step adds a node type
without touching this loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..dialogue import DialogueManager, DMResult, EndCall, HandOff
from ..domain_pack import DomainPack
from ..tools import ToolExecutor
from ..turn import ButtonPress, Dtmf, Utterance
from .expr import ExprError, MissingAttribute
from .formatters import FormatError
from .faq import FaqRuleManager
from .flows import Flow, FlowError, Node, load_flows
from .matching import Matcher
from .tokenize import Tokenizer, for_lang

ASK_MISSES = "ask_misses"   # consecutive unusable answers at the current ask (R3)
PARKED = "parked"           # flows set aside by a switch, newest last: {flow, node, slots, asked} (R6-1)
ASKED = "asked"             # answered asks of the running flow, oldest first, for `back` (R8-1)
MAIN_MENU = "main_menu"     # reserved flow_id after `cancel`: no flow runs (R8-3)
RUNTIME = (ASK_MISSES, PARKED, ASKED, "result", "faq_misses")   # meta written while talking; `cancel` clears it
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
        return {**self.slots, "slots": self.slots, "customer": self.meta.get("customer", {}),
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


@handler("confirm")
def run_confirm(run: Run, node: Node):
    run.out.append(node.data["prompt"].render(run.env()))
    return Wait(node.id)


@handler("call")
def run_call(run: Run, node: Node):
    args = {k: t.render(run.env()) for k, t in node.data["args"].items()}
    result = run.manager.tools.call(node.data["tool"], args)
    run.trace.setdefault("calls", []).append({"tool": node.data["tool"], "args": args, "error": result.error})
    run.meta["result"] = dict(result.data) if result.ok else {"error": result.error}
    return node.data["on_ok"] if result.ok else node.data["on_error"]


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
def extract(node: Node, turn_input, tok: Tokenizer) -> Optional[str]:
    """The slot value for an `ask` node, or None when the input does not contain one."""
    kind, length = node.data["extractor"], node.data["length"]
    if isinstance(turn_input, Dtmf):
        text = turn_input.digits
    elif isinstance(turn_input, Utterance):
        text = turn_input.text
    else:
        return None
    if kind == "text":
        return text.strip() or None
    if kind == "digits":
        groups = re.findall(r"\d+", text)
        digits = "".join(groups) if len(groups) == 1 else (groups[0] if groups else "")
        return digits if digits and (length is None or len(digits) == length) else None
    if kind == "number":
        m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
        return m.group(0) if m else None
    if kind == "choice":
        analysis = tok.analyze(text)
        return next((value for word, value in node.data["choices"] if tok.has(analysis, word)), None)
    return None


class FlowManager(DialogueManager):
    name = "flows"

    def __init__(self, pack: DomainPack, tools: ToolExecutor, flows: Optional[dict] = None,
                 tokenizer: Optional[Tokenizer] = None, faq: Optional[FaqRuleManager] = None):
        self.pack, self.tools = pack, tools
        self.tok = tokenizer or for_lang(pack.lang)
        self.flows = flows if flows is not None else (pack.flows or {})
        for flow in self.flows.values():
            for node in flow.nodes.values():
                if node.type not in HANDLERS:
                    raise FlowError(f"{flow.path}: node {node.id}: no handler registered for `{node.type}`")
                if node.type == "confirm" and pack.confirm_words is None:
                    raise FlowError(f"{flow.path}: node {node.id}: a confirm node needs rules/confirm.yaml in the pack")
        self.matcher = Matcher([f.triggers for f in self.flows.values()], self.tok)
        self.buttons = {b: f.id for f in self.flows.values() for b in f.buttons}
        self.commands = Matcher(pack.commands, self.tok) if pack.commands else None
        self.faq = faq if faq is not None else (
            FaqRuleManager(pack, self.tok) if pack.patterns and pack.fallback else None)

    # -- entry point --------------------------------------------------------------------------------
    def respond(self, state, turn_input):
        if isinstance(turn_input, Utterance) and self.commands is not None:   # first, in every state (R8-5)
            command, match = self.commands.match(turn_input.text)
            if command is not None:
                return self._command(command.id, state, {"command": command.id, "command_match": match})
        flow = self.flows.get(state.flow_id) if state.flow_id else None
        if flow is not None and state.node_id in flow.nodes and flow.nodes[state.node_id].type == "confirm":
            return self._answer_confirm(flow, state, turn_input)   # nothing breaks in here (R7-12)
        if flow is not None and state.node_id in flow.nodes and flow.nodes[state.node_id].type == "ask":
            if flow.nodes[state.node_id].data["interruptible"]:   # interrupts first, then the answer (R6-5)
                switched = self._switch(flow, state, turn_input)
                if switched is not None:
                    return switched
            return self._answer_ask(flow, state, turn_input)
        if isinstance(turn_input, ButtonPress) and turn_input.button_id in self.buttons:
            flow = self.flows[self.buttons[turn_input.button_id]]
            run = Run(self, flow, {}, {**state.meta, ASKED: []}, trace={"flow": flow.id, "button": turn_input.button_id})
            return self._run(run, state, flow.start)
        if isinstance(turn_input, Utterance) and self.flows:
            trigger, trace = self.matcher.match(turn_input.text)
            if trigger is not None:
                flow = self.flows[trigger.id]
                captured = self._capture(flow, turn_input)
                run = Run(self, flow, captured, {**state.meta, ASKED: []},
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
        if node is None or node.type not in ("ask", "confirm"):   # back with nothing to go back in
            return DMResult(wording.get("flow.no_flow", "I can't help with that."), state, trace=trace)
        asked = list(state.meta.get(ASKED, ()))
        target = flow.nodes[asked.pop()] if asked else node   # at the first question: the same question
        run = Run(self, flow, dict(state.slots), {**state.meta, ASKED: asked, ASK_MISSES: 0},
                  trace={**trace, "flow": flow.id, "back_to": target.id})
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
                                                "asked": list(state.meta.get(ASKED, ()))}]
        if len(parked) > self.pack.max_parked:   # the oldest goes; nothing is said (R7-3)
            trace["parked_dropped"] = [p["flow"] for p in parked[:-self.pack.max_parked]]
            parked = parked[-self.pack.max_parked:]
        carried = {slot: state.slots[slot] for slot in target.carry if slot in state.slots}
        captured = self._capture(target, turn_input)
        run = Run(self, target, {**carried, **captured}, {**state.meta, PARKED: parked, ASK_MISSES: 0, ASKED: []},
                  trace={"flow": target.id, "switch": {"from": flow.id, "to": target.id, "by": by}, **trace,
                         "carried": carried, "captured": captured})
        return self._run(run, state, target.start)

    def _capture(self, flow: Flow, turn_input) -> dict:
        """Slots the first utterance already contains ("How much is the plus plan" fills `plan`)."""
        out = {}
        if not isinstance(turn_input, Utterance):
            return out
        for slot, spec in flow.captures:
            value = extract(Node(f"capture:{slot}", "capture", spec), turn_input, self.tok)
            if value is not None:
                out[slot] = value
        return out

    def _answer_ask(self, flow: Flow, state, turn_input):
        node = flow.nodes[state.node_id]
        slot = node.data["slot"]
        keypad_only = slot in self.pack.sensitive_slots
        spoken_at_keypad = keypad_only and isinstance(turn_input, Utterance)
        value = None if spoken_at_keypad else extract(node, turn_input, self.tok)
        faq = None   # evaluated every turn, so turns where both match show in the trace (R7-4)
        if self.faq is not None and isinstance(turn_input, Utterance):
            faq, _ = self.faq.match(turn_input.text)
        decided = decide(value, faq)
        run = Run(self, flow, dict(state.slots), {**state.meta},
                  trace={"flow": flow.id, "ask": node.id, "faq": faq.id if faq else None, "decided": decided})
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
        run.meta[ASKED] = [*state.meta.get(ASKED, ()), node.id]   # for `back` (R8-1)
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
        answer = self.confirm_answer(turn_input)
        run = Run(self, flow, dict(state.slots), {**state.meta}, trace={"flow": flow.id, "confirm": answer})
        if answer == "yes":
            return self._run(run, state, node.data["on_yes"])
        if answer == "no":   # the risky tool is not called
            run.out.append(self.pack.wording.get("confirm.declined", "All right, I have not done it."))
            return self._run(run, state, node.data["on_no"])
        return self._unusable(flow, node, state, run, False)

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
        node = flow.nodes[top["node"]]
        meta = {**run.meta, PARKED: rest, ASK_MISSES: 0, ASKED: list(top.get("asked", ()))}
        back = Run(self, flow, dict(top["slots"]), meta)
        run.out.append(node.data["prompt"].render(back.env()))
        run.trace["resumed"] = {"flow": flow.id, "node": node.id}
        new = state.evolve(flow_id=flow.id, node_id=node.id, slots=top["slots"], meta=meta)
        return DMResult(" ".join(run.out), new, tuple(run.actions), run.trace)


def build_manager(domains_dir: str, domain: str, lang: str, tools: ToolExecutor) -> FlowManager:
    pack = DomainPack.load(domains_dir, domain, lang)
    flows = load_flows(f"{pack.base_dir}/flows", pack.tools_path, pack.sensitive_slots, pack.notices)
    return FlowManager(pack, tools, flows)


def default_factory(ctx):
    """`python -m voxstage.evaluate run voxstage.rules.interpreter:default_factory`"""
    from ..evaluate import DEFAULT_DOMAINS_DIR
    return build_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, ctx.tools)
