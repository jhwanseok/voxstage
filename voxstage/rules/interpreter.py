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
from .expr import ExprError
from .faq import FaqRuleManager
from .flows import Flow, FlowError, Node, load_flows
from .matching import Matcher
from .tokenize import Tokenizer, for_lang

ASK_MISSES = "ask_misses"   # consecutive unusable answers at the current ask (R3)
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
                "policy": self.meta.get("policy", {}), "result": self.meta.get("result", {})}


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
        return next((c for c in node.data["choices"] if tok.has(analysis, c)), None)
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
        self.matcher = Matcher([f.triggers for f in self.flows.values()], self.tok)
        self.buttons = {b: f.id for f in self.flows.values() for b in f.buttons}
        self.faq = faq if faq is not None else (
            FaqRuleManager(pack, self.tok) if pack.patterns and pack.fallback else None)

    # -- entry point --------------------------------------------------------------------------------
    def respond(self, state, turn_input):
        flow = self.flows.get(state.flow_id) if state.flow_id else None
        if flow is not None and state.node_id in flow.nodes and flow.nodes[state.node_id].type == "ask":
            return self._answer_ask(flow, state, turn_input)
        if isinstance(turn_input, ButtonPress) and turn_input.button_id in self.buttons:
            flow = self.flows[self.buttons[turn_input.button_id]]
            run = Run(self, flow, {}, {**state.meta}, trace={"flow": flow.id, "button": turn_input.button_id})
            return self._run(run, state, flow.start)
        if isinstance(turn_input, Utterance) and self.flows:
            trigger, trace = self.matcher.match(turn_input.text)
            if trigger is not None:
                flow = self.flows[trigger.id]
                run = Run(self, flow, {}, {**state.meta}, trace={"flow": flow.id, "trigger": trace})
                return self._run(run, state, flow.start)
        if self.faq is not None:
            return self.faq.respond(state, turn_input)
        reply = "I can't help with that."
        return DMResult(reply, state, trace={"rule": "no_flow"})

    def _answer_ask(self, flow: Flow, state, turn_input):
        node = flow.nodes[state.node_id]
        slot = node.data["slot"]
        keypad_only = slot in self.pack.sensitive_slots
        spoken_at_keypad = keypad_only and isinstance(turn_input, Utterance)
        value = None if spoken_at_keypad else extract(node, turn_input, self.tok)
        run = Run(self, flow, dict(state.slots), {**state.meta}, trace={"flow": flow.id, "ask": node.id})
        if value is None:
            return self._unusable(flow, node, state, run, spoken_at_keypad)
        run.slots[slot] = value
        run.trace["extracted"] = {slot: value}
        return self._run(run, state, node.data["next"])

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
            except ExprError as exc:
                raise FlowRuntimeError(f"{run.flow.path}: node {node_id}: {exc}") from exc
            if isinstance(outcome, (Wait, Done)):
                run.meta[ASK_MISSES] = 0
                new = state.evolve(flow_id=run.flow.id, node_id=outcome.node_id, slots=run.slots, meta=run.meta)
                return DMResult(" ".join(run.out), new, tuple(run.actions), run.trace)
            node_id = outcome
        raise FlowRuntimeError(f"{run.flow.path}: more than {MAX_NODES_PER_TURN} nodes in one turn")


def build_manager(domains_dir: str, domain: str, lang: str, tools: ToolExecutor) -> FlowManager:
    pack = DomainPack.load(domains_dir, domain, lang)
    flows = load_flows(f"{pack.base_dir}/flows", pack.tools_path, pack.sensitive_slots)
    return FlowManager(pack, tools, flows)


def default_factory(ctx):
    """`python -m voxstage.evaluate run voxstage.rules.interpreter:default_factory`"""
    from ..evaluate import DEFAULT_DOMAINS_DIR
    return build_manager(DEFAULT_DOMAINS_DIR, ctx.domain, ctx.lang, ctx.tools)
