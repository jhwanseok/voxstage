"""Flow files: a state-machine map of nodes with explicit `next` links (ADR 0010).

    id: balance_inquiry
    triggers: {any_of: [balance]}          # the word-group language of the FAQ rules
    start: ask_account
    nodes:
      ask_account: {type: ask, slot: account_last4, prompt: "...", extractor: digits, length: 4, next: lookup}
      lookup: {type: call, tool: get_balance, args: {account_last4: "{account_last4}"}, on_ok: say, on_error: fail}
      say: {type: say, text: "Your balance is {result.balance}.", next: done}
      done: {type: end}

Node types are registered in NODE_TYPES with a compile function (checks and compiles one node) and the list of
nodes it can lead to. Everything is validated when the file is loaded, not during a call.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Callable

import yaml

from ..domain_pack import Pattern, parse_pattern
from .expr import Expr, ExprError, compile_expr

EXTRACTORS = ("text", "digits", "number", "choice")


class FlowError(ValueError):
    """A flow file is malformed. The message names the file and node."""


@dataclass(frozen=True)
class Template:
    parts: tuple   # of str | Expr

    def render(self, env) -> str:
        return "".join(p if isinstance(p, str) else _text(p.evaluate(env)) for p in self.parts)


def _text(value) -> str:
    return "yes" if value is True else "no" if value is False else str(value)


def compile_template(text, where: str, names: frozenset) -> Template:
    """`{expr}` fields; `{{` and `}}` are literal braces."""
    if not isinstance(text, str):
        raise FlowError(f"{where}: must be text")
    parts, buf, i = [], [], 0
    while i < len(text):
        c = text[i]
        if text.startswith("{{", i) or text.startswith("}}", i):
            buf.append(c)
            i += 2
        elif c == "{":
            j = text.find("}", i)
            if j < 0:
                raise FlowError(f"{where}: unclosed `{{` in {text!r}")
            if buf:
                parts.append("".join(buf))
                buf = []
            try:
                parts.append(compile_expr(text[i + 1:j], where, names))
            except ExprError as exc:
                raise FlowError(str(exc)) from exc
            i = j + 1
        elif c == "}":
            raise FlowError(f"{where}: stray `}}` in {text!r}")
        else:
            buf.append(c)
            i += 1
    if buf:
        parts.append("".join(buf))
    return Template(tuple(parts))


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    data: dict   # compiled fields of this node type


@dataclass(frozen=True)
class Flow:
    id: str
    triggers: Pattern
    start: str
    nodes: dict
    path: str
    slots: frozenset


@dataclass(frozen=True)
class NodeType:
    compile: Callable   # (raw: dict, ctx: CompileCtx) -> dict
    edges: Callable     # (data: dict) -> list of node ids this node can lead to
    waits: bool = False  # does the node wait for the caller?


NODE_TYPES: dict = {}


def register_node_type(name: str, *, edges: Callable, waits: bool = False):
    def deco(fn):
        NODE_TYPES[name] = NodeType(fn, edges, waits)
        return fn
    return deco


@dataclass(frozen=True)
class CompileCtx:
    path: str
    flow_id: str
    node_id: str
    names: frozenset
    tools: dict   # tool name -> tuple of param names

    @property
    def where(self) -> str:
        return f"{self.path}: node {self.node_id}"

    def need(self, raw: dict, key: str, kind=str):
        if key not in raw or not isinstance(raw[key], kind) or (kind is str and not raw[key].strip()):
            raise FlowError(f"{self.where}: needs `{key}`")
        return raw[key]

    def only(self, raw: dict, allowed: set):
        extra = set(raw) - allowed - {"type"}
        if extra:
            raise FlowError(f"{self.where}: unknown keys {sorted(extra)}")

    def template(self, text, field: str) -> Template:
        return compile_template(text, f"{self.where}.{field}", self.names)


@register_node_type("say", edges=lambda d: [d["next"]])
def _say(raw, ctx):
    ctx.only(raw, {"text", "next"})
    return {"text": ctx.template(ctx.need(raw, "text"), "text"), "next": ctx.need(raw, "next")}


@register_node_type("ask", edges=lambda d: [d["next"]], waits=True)
def _ask(raw, ctx):
    ctx.only(raw, {"slot", "prompt", "extractor", "length", "choices", "next"})
    extractor = raw.get("extractor", "text")
    if extractor not in EXTRACTORS:
        raise FlowError(f"{ctx.where}: extractor must be one of {EXTRACTORS}")
    choices = raw.get("choices")
    if (extractor == "choice") != bool(choices):
        raise FlowError(f"{ctx.where}: `choices` goes with the choice extractor, and only with it")
    length = raw.get("length")
    if length is not None and (extractor != "digits" or not isinstance(length, int) or length < 1):
        raise FlowError(f"{ctx.where}: `length` is a positive integer for the digits extractor")
    return {"slot": ctx.need(raw, "slot"), "prompt": ctx.template(ctx.need(raw, "prompt"), "prompt"),
            "extractor": extractor, "length": length, "choices": tuple(choices or ()),
            "next": ctx.need(raw, "next")}


@register_node_type("call", edges=lambda d: [d["on_ok"], d["on_error"]])
def _call(raw, ctx):
    ctx.only(raw, {"tool", "args", "on_ok", "on_error"})
    tool = ctx.need(raw, "tool")
    if tool not in ctx.tools:
        raise FlowError(f"{ctx.where}: unknown tool `{tool}` (known: {sorted(ctx.tools)})")
    args = ctx.need(raw, "args", dict)
    if set(args) != set(ctx.tools[tool]):
        raise FlowError(f"{ctx.where}: tool `{tool}` takes {list(ctx.tools[tool])}, got {sorted(args)}")
    return {"tool": tool, "args": {k: ctx.template(str(v), f"args.{k}") for k, v in args.items()},
            "on_ok": ctx.need(raw, "on_ok"), "on_error": ctx.need(raw, "on_error")}


@register_node_type("branch", edges=lambda d: [n for _, n in d["cases"]] + [d["else"]])
def _branch(raw, ctx):
    ctx.only(raw, {"cases", "else"})
    cases = ctx.need(raw, "cases", list)
    if not cases:
        raise FlowError(f"{ctx.where}: `cases` is empty")
    out = []
    for i, c in enumerate(cases):
        if not isinstance(c, dict) or set(c) != {"when", "next"}:
            raise FlowError(f"{ctx.where}: case {i} needs `when` and `next` only")
        try:
            out.append((compile_expr(str(c["when"]), f"{ctx.where}.cases[{i}]", ctx.names), c["next"]))
        except ExprError as exc:
            raise FlowError(str(exc)) from exc
    return {"cases": tuple(out), "else": ctx.need(raw, "else")}


@register_node_type("goto", edges=lambda d: [d["next"]])
def _goto(raw, ctx):
    ctx.only(raw, {"next"})
    return {"next": ctx.need(raw, "next")}


@register_node_type("end", edges=lambda d: [])
def _end(raw, ctx):
    ctx.only(raw, {"action", "reason"})
    action = raw.get("action")
    if action not in (None, "handoff", "end_call"):
        raise FlowError(f"{ctx.where}: action must be handoff or end_call")
    if "reason" in raw and action != "handoff":
        raise FlowError(f"{ctx.where}: `reason` goes with action: handoff")
    return {"action": action, "reason": raw.get("reason", "flow")}


def tool_params(tools_path: str) -> dict:
    with open(tools_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return {name: tuple(body.get("params") or ()) for name, body in spec["tools"].items()}


def load_flow(path: str, tools: dict) -> Flow:
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise FlowError(f"{path}: invalid YAML ({exc})") from exc
    if not isinstance(raw, dict) or set(raw) != {"id", "triggers", "start", "nodes"}:
        raise FlowError(f"{path}: needs exactly id, triggers, start and nodes")
    flow_id = raw["id"]
    raw_nodes = raw["nodes"]
    if not isinstance(raw_nodes, dict) or not raw_nodes:
        raise FlowError(f"{path}: `nodes` must be a non-empty mapping")
    if os.path.splitext(os.path.basename(path))[0] != flow_id:
        raise FlowError(f"{path}: file name must be the flow id `{flow_id}`")
    names = frozenset(n["slot"] for n in raw_nodes.values()
                      if isinstance(n, dict) and n.get("type") == "ask" and isinstance(n.get("slot"), str))
    nodes = {}
    for node_id, body in raw_nodes.items():
        if not isinstance(body, dict) or body.get("type") not in NODE_TYPES:
            raise FlowError(f"{path}: node {node_id}: type must be one of {sorted(NODE_TYPES)}")
        ctx = CompileCtx(path, flow_id, node_id, names, tools)
        nodes[node_id] = Node(node_id, body["type"], NODE_TYPES[body["type"]].compile(body, ctx))
    try:
        triggers = parse_pattern(path, {"id": flow_id, **(raw["triggers"] or {})})
    except ValueError as exc:
        raise FlowError(str(exc)) from exc
    flow = Flow(flow_id, triggers, raw["start"], nodes, path, names)
    _validate_graph(flow)
    return flow


def _validate_graph(flow: Flow) -> None:
    edges = {n.id: NODE_TYPES[n.type].edges(n.data) for n in flow.nodes.values()}
    if flow.start not in flow.nodes:
        raise FlowError(f"{flow.path}: start node `{flow.start}` does not exist")
    for node_id, targets in edges.items():
        for t in targets:
            if t not in flow.nodes:
                raise FlowError(f"{flow.path}: node {node_id} leads to `{t}`, which does not exist")
    seen, stack = set(), [flow.start]
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(edges[n])
    unreachable = sorted(set(flow.nodes) - seen)
    if unreachable:
        raise FlowError(f"{flow.path}: unreachable nodes {unreachable}")
    if not any(n.type == "end" for n in flow.nodes.values()):
        raise FlowError(f"{flow.path}: no `end` node")
    # a loop must wait for the caller somewhere, or a call could never finish
    waiting = {n.id for n in flow.nodes.values() if NODE_TYPES[n.type].waits}
    state: dict = {}

    def visit(n, trail):
        if n in waiting:
            return
        if state.get(n) == "open":
            raise FlowError(f"{flow.path}: loop without waiting for the caller: {' -> '.join(trail + [n])}")
        if state.get(n) == "done":
            return
        state[n] = "open"
        for t in edges[n]:
            visit(t, trail + [n])
        state[n] = "done"

    visit(flow.start, [])
    # every slot used in a template must be filled by an ask node of this flow (checked when compiling names)


def load_flows(flows_dir: str, tools_path: str) -> dict:
    tools = tool_params(tools_path)
    flows = {}
    for path in sorted(glob.glob(os.path.join(flows_dir, "*.yaml"))):
        flow = load_flow(path, tools)
        flows[flow.id] = flow
    return flows
