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
import re
from dataclasses import dataclass
from typing import Callable

import yaml

from ..domain_pack import Pattern, parse_pattern
from .expr import Expr, ExprError, MissingAttribute, compile_expr
from .formatters import FORMATTERS

EXTRACTORS = ("text", "digits", "number", "choice")


class FlowError(ValueError):
    """A flow file is malformed. The message names the file and node."""


@dataclass(frozen=True)
class Field:
    """`{expr | formatter(arg) | default(value)}`: a value, formatters applied in order, and an explicit default."""
    expr: Expr
    filters: tuple = ()          # of (name, tuple of Expr)
    default: Expr | None = None

    def render(self, env) -> str:
        try:
            value = self.expr.evaluate(env)
        except MissingAttribute:
            if self.default is None:
                raise
            return _text(self.default.evaluate(env))
        for name, args in self.filters:
            value = FORMATTERS[name].fn(value, env.get("_lang", "en"), *[a.evaluate(env) for a in args])
        return _text(value)


@dataclass(frozen=True)
class Template:
    parts: tuple   # of str | Field

    def render(self, env) -> str:
        return "".join(p if isinstance(p, str) else p.render(env) for p in self.parts)


def _text(value) -> str:
    return "yes" if value is True else "no" if value is False else str(value)


def _split_filters(field: str) -> list:
    """Split at `|` outside quotes and parentheses."""
    out, buf, depth, quote = [], [], 0, None
    for c in field:
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(c)
    out.append("".join(buf))
    return [p.strip() for p in out]


_FILTER = re.compile(r"^(\w+)\s*(?:\((.*)\))?$", re.S)


def _compile_field(field: str, where: str, names: frozenset) -> Field:
    head, *rest = _split_filters(field)
    try:
        expr = compile_expr(head, where, names)
        filters, default = [], None
        for item in rest:
            m = _FILTER.match(item)
            if not m:
                raise FlowError(f"{where}: cannot read the filter `{item}`")
            name, arg_text = m.group(1), m.group(2)
            args = tuple(compile_expr(a.strip(), where, names) for a in _split_args(arg_text)) if arg_text else ()
            if name == "default":
                if len(args) != 1 or default is not None:
                    raise FlowError(f"{where}: `default` takes one value, once")
                default = args[0]
                continue
            if name not in FORMATTERS:
                raise FlowError(f"{where}: unknown formatter `{name}` (known: {sorted(FORMATTERS)} and default)")
            f = FORMATTERS[name]
            if not f.min_args <= len(args) <= f.max_args:
                raise FlowError(f"{where}: formatter `{name}` takes {f.min_args} to {f.max_args} arguments")
            filters.append((name, args))
    except ExprError as exc:
        raise FlowError(str(exc)) from exc
    return Field(expr, tuple(filters), default)


def _split_args(text: str) -> list:
    out, buf, depth, quote = [], [], 0, None
    for c in text:
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "," and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(c)
    out.append("".join(buf))
    return out


def compile_template(text, where: str, names: frozenset) -> Template:
    """`{expr}` fields with optional filters; `{{` and `}}` are literal braces."""
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
            parts.append(_compile_field(text[i + 1:j], where, names))
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
    buttons: tuple = ()
    captures: tuple = ()   # of (slot, extractor spec): slots read from the words that started the flow


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
    sensitive: frozenset = frozenset()   # slots that only the keypad may fill (R3-1)

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


def extractor_spec(raw: dict, where: str) -> dict:
    """The extractor, its length and its choices, checked. `choices` is a list of words, or a mapping
    word -> value when the slot value differs from the word the caller says (Korean words, English values)."""
    extractor = raw.get("extractor", "text")
    if extractor not in EXTRACTORS:
        raise FlowError(f"{where}: extractor must be one of {EXTRACTORS}")
    choices = raw.get("choices")
    if (extractor == "choice") != bool(choices):
        raise FlowError(f"{where}: `choices` goes with the choice extractor, and only with it")
    pairs = ()
    if choices:
        if isinstance(choices, dict):
            pairs = tuple((str(w), str(v)) for w, v in choices.items())
        elif isinstance(choices, list) and all(isinstance(c, str) for c in choices):
            pairs = tuple((c, c) for c in choices)
        else:
            raise FlowError(f"{where}: `choices` must be a list of words or a word -> value mapping")
    length = raw.get("length")
    if length is not None and (extractor != "digits" or not isinstance(length, int) or length < 1):
        raise FlowError(f"{where}: `length` is a positive integer for the digits extractor")
    return {"extractor": extractor, "length": length, "choices": pairs}


@register_node_type("ask", edges=lambda d: [d["next"]], waits=True)
def _ask(raw, ctx):
    """Asks for a slot and waits. If the slot is already filled (a capture, or an earlier answer) the ask is skipped."""
    ctx.only(raw, {"slot", "prompt", "extractor", "length", "choices", "next"})
    spec = extractor_spec(raw, ctx.where)
    slot = ctx.need(raw, "slot")
    if slot in ctx.sensitive and spec["extractor"] != "digits":
        raise FlowError(f"{ctx.where}: `{slot}` is a sensitive slot (keypad only), so its extractor must be digits")
    return {"slot": slot, "prompt": ctx.template(ctx.need(raw, "prompt"), "prompt"), **spec,
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


def load_flow(path: str, tools: dict, sensitive: frozenset = frozenset()) -> Flow:
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise FlowError(f"{path}: invalid YAML ({exc})") from exc
    if not isinstance(raw, dict) or not {"id", "triggers", "start", "nodes"} <= set(raw) \
            or set(raw) - {"id", "triggers", "start", "nodes", "buttons", "captures"}:
        raise FlowError(f"{path}: needs id, triggers, start and nodes (and optionally buttons, captures)")
    raw_captures = raw.get("captures") or {}
    if not isinstance(raw_captures, dict):
        raise FlowError(f"{path}: `captures` must map slot names to extractors")
    captures = []
    for slot, body in raw_captures.items():
        if not isinstance(body, dict) or set(body) - {"extractor", "length", "choices"}:
            raise FlowError(f"{path}: capture {slot}: needs extractor (and length or choices)")
        spec = extractor_spec(body, f"{path}: capture {slot}")
        if spec["extractor"] == "text" or slot in sensitive:
            raise FlowError(f"{path}: capture {slot}: a captured slot cannot be free text or sensitive (keypad only)")
        captures.append((slot, spec))
    buttons = raw.get("buttons") or []
    if not isinstance(buttons, list) or not all(isinstance(b, str) and b.strip() for b in buttons):
        raise FlowError(f"{path}: `buttons` must be a list of button ids")
    flow_id = raw["id"]
    raw_nodes = raw["nodes"]
    if not isinstance(raw_nodes, dict) or not raw_nodes:
        raise FlowError(f"{path}: `nodes` must be a non-empty mapping")
    if os.path.splitext(os.path.basename(path))[0] != flow_id:
        raise FlowError(f"{path}: file name must be the flow id `{flow_id}`")
    names = frozenset(n["slot"] for n in raw_nodes.values()
                      if isinstance(n, dict) and n.get("type") == "ask" and isinstance(n.get("slot"), str)) \
        | frozenset(raw_captures)
    nodes = {}
    for node_id, body in raw_nodes.items():
        if not isinstance(body, dict) or body.get("type") not in NODE_TYPES:
            raise FlowError(f"{path}: node {node_id}: type must be one of {sorted(NODE_TYPES)}")
        ctx = CompileCtx(path, flow_id, node_id, names, tools, sensitive)
        nodes[node_id] = Node(node_id, body["type"], NODE_TYPES[body["type"]].compile(body, ctx))
    try:
        triggers = parse_pattern(path, {"id": flow_id, **(raw["triggers"] or {})})
    except ValueError as exc:
        raise FlowError(str(exc)) from exc
    flow = Flow(flow_id, triggers, raw["start"], nodes, path, names, tuple(buttons), tuple(captures))
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


def load_flows(flows_dir: str, tools_path: str, sensitive: frozenset = frozenset()) -> dict:
    tools = tool_params(tools_path)
    flows, owner = {}, {}
    for path in sorted(glob.glob(os.path.join(flows_dir, "*.yaml"))):
        flow = load_flow(path, tools, sensitive)
        flows[flow.id] = flow
        for b in flow.buttons:
            if b in owner:
                raise FlowError(f"{path}: button `{b}` already starts flow `{owner[b]}`")
            owner[b] = flow.id
    return flows
