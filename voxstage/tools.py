"""Tool (external API) execution behind a port, with a declarative fake backend.

`ToolExecutor` is the port: dialogue managers ask for a tool by name and arguments and get a
`ToolResult` back. `FakeApiExecutor` is the adapter used for experiments: it answers from a
rule table keyed by the call's arguments, so a domain pack ships its "API" as data
(`domains/<name>/tools.yaml`) and the core never imports domain code.
See docs/decisions/0004-dummy-api-tool-executor.md.

Rule table format:

    tools:
      get_fee:
        params: [amount, grade]          # the old form: every name required, untyped
        rules:                           # first rule whose `when` matches wins
          - when: {grade: gold}
            return: {fee: 0}
          - when: {grade: basic}
            return: {fee: 500}
          - when: {grade: outage}
            error: timeout               # simulate a failing API
          - when: {grade: slow}
            delay_ms: 8000               # a slow answer (R12-5)
            return: {fee: 500}
        default:                         # optional; used when no rule matches
          error: not_found
      get_balance:
        params:                          # the typed form (R16b, ADR 0014): type, length, choices, required
          account_last4: {type: digits, length: 4}
          note: {type: text, required: false}   # may be left out of the call
        returns: {balance: number, currency: text}   # the response; `boolean` is allowed here
        requires: verified               # refused until the caller passed the check (R13-1)
      verify_identity:
        verifies: true                   # the check itself; exactly one when any tool is protected
      get_order_status:
        retry: 1                         # a timeout is tried once more (R12-1); never on a risky tool
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import yaml


PARAM_TYPES = ("text", "digits", "number", "choice", "date", "month_start", "day", "time_window", "duration")
RETURN_TYPES = PARAM_TYPES + ("boolean",)


class Signature(tuple):
    """The parameter names of a tool (a tuple, as before) with the typed spec behind them (R16b):
    `.params` name -> {type, length, choices, required}; `.returns` field -> {type, length, choices}, or None when
    the tool declares no response schema; `.typed` is false for the old list form of `params`."""

    requires = None   # the tool's `requires`, set by the loader of flows

    def __new__(cls, params: dict, returns, typed: bool = False):
        self = super().__new__(cls, tuple(params))
        self.params, self.returns, self.typed = params, returns, typed
        return self


def _type_spec(where: str, body, allowed: tuple, keys: set) -> dict:
    if isinstance(body, str):
        body = {"type": body}
    if body is None:
        body = {}
    if not isinstance(body, dict) or set(body) - keys:
        raise ValueError(f"{where}: a type name or a mapping with {sorted(keys)}")
    kind = body.get("type")
    if kind is not None and kind not in allowed:
        raise ValueError(f"{where}: `type` must be one of {allowed}")
    length, choices = body.get("length"), body.get("choices")
    if length is not None and (kind != "digits" or not isinstance(length, int) or isinstance(length, bool) or length < 1):
        raise ValueError(f"{where}: `length` is a positive integer for a digits value")
    if (kind == "choice") != (choices is not None):
        raise ValueError(f"{where}: `choices` goes with type choice, and only with it")
    if choices is not None and (not isinstance(choices, list) or not choices
                                or not all(isinstance(c, (str, int)) and not isinstance(c, bool) for c in choices)):
        raise ValueError(f"{where}: `choices` is a non-empty list of values")
    return {"type": kind, "length": length, "choices": tuple(str(c) for c in choices) if choices else ()}


def _signature(name: str, body: dict) -> Signature:
    raw = body.get("params", [])
    if isinstance(raw, list):
        if not all(isinstance(p, str) and p for p in raw) or len(set(raw)) != len(raw):
            raise ValueError(f"tool {name}: `params` is a list of distinct names or a mapping name -> type")
        params = {p: {"type": None, "length": None, "choices": (), "required": True} for p in raw}
    elif isinstance(raw, dict):
        params = {}
        for p, pbody in raw.items():
            where = f"tool {name}, param {p}"
            spec = _type_spec(where, {k: v for k, v in pbody.items() if k != "required"} if isinstance(pbody, dict)
                              else pbody, PARAM_TYPES, {"type", "length", "choices"})
            required = pbody.get("required", True) if isinstance(pbody, dict) else True
            if not isinstance(required, bool):
                raise ValueError(f"{where}: `required` is true or false")
            params[p] = {**spec, "required": required}
    else:
        raise ValueError(f"tool {name}: `params` is a list of names or a mapping name -> type")
    returns = None
    if body.get("returns") is not None:
        raw_returns = body["returns"]
        if not isinstance(raw_returns, dict) or not raw_returns:
            raise ValueError(f"tool {name}: `returns` maps a returned field to its type")
        returns = {f: _type_spec(f"tool {name}, returns {f}", t, RETURN_TYPES, {"type", "length", "choices"})
                   for f, t in raw_returns.items()}
    return Signature(params, returns, isinstance(raw, dict))


def value_fits(value, spec: dict) -> bool:
    """Does a value satisfy a type spec ({type, length, choices}); an untyped spec accepts anything."""
    kind = spec.get("type")
    if kind is None or kind == "text":
        return True
    if kind == "boolean":
        return isinstance(value, bool)
    text = str(value)
    if kind == "digits":
        return text.isdigit() and (spec.get("length") is None or len(text) == spec["length"])
    if kind == "number":
        if isinstance(value, bool):
            return False
        try:
            float(text)
        except ValueError:
            return False
        return True
    if kind == "choice":
        return text in spec.get("choices", ())
    return True   # date, month_start, day, time_window, duration: read by an extractor; any text passes here


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    delay_ms: int = 0   # how long the answer took (simulated, R12-5); the dialogue manager decides what is too slow


class ToolExecutor:
    """Port. Implementations: the fake backend here; a real HTTP client could be added later."""

    name = "tools"

    def call(self, tool: str, args: dict) -> ToolResult:
        raise NotImplementedError


class FakeApiExecutor(ToolExecutor):
    name = "fake_api"

    def __init__(self, spec: dict):
        self.tools = _validate_spec(spec)
        self.calls: list[tuple[str, dict]] = []  # every call made, for tool-call accuracy checks

    @classmethod
    def from_yaml(cls, path: str) -> "FakeApiExecutor":
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def call(self, tool: str, args: dict) -> ToolResult:
        self.calls.append((tool, dict(args)))
        spec = self.tools.get(tool)
        if spec is None:
            return ToolResult(False, error="unknown_tool")
        for p, ps in spec["signature"].params.items():
            if ps["required"] and p not in args:
                return ToolResult(False, error=f"missing_param:{p}")
        for rule in spec["rules"]:
            if all(str(args.get(k)) == str(v) for k, v in rule["when"].items()):
                return _to_result(rule)
        if spec["default"] is not None:
            return _to_result(spec["default"])
        return ToolResult(False, error="no_rule")


def _to_result(rule: dict) -> ToolResult:
    delay = int(rule.get("delay_ms", 0))
    if "error" in rule:
        return ToolResult(False, error=str(rule["error"]), delay_ms=delay)
    return ToolResult(True, data=dict(rule["return"]), delay_ms=delay)


def _validate_spec(spec) -> dict:
    if not isinstance(spec, dict) or not isinstance(spec.get("tools"), dict):
        raise ValueError("tool spec must be a mapping with a 'tools' mapping")
    out = {}
    for name, body in spec["tools"].items():
        body = body or {}
        extra = set(body) - {"params", "returns", "rules", "default", "risky", "requires", "verifies", "retry"}
        if extra:
            raise ValueError(f"tool {name}: unknown keys {sorted(extra)}")
        rules = body.get("rules", [])
        for i, rule in enumerate(rules):
            _check_outcome(f"tool {name} rule {i}", rule, allow_when=True)
        default = body.get("default")
        if default is not None:
            _check_outcome(f"tool {name} default", default, allow_when=False)
        risky = body.get("risky", False)
        if not isinstance(risky, bool):
            raise ValueError(f"tool {name}: 'risky' must be true or false")
        requires = body.get("requires")
        if requires not in (None, "verified"):
            raise ValueError(f"tool {name}: 'requires' can only be 'verified'")
        verifies = body.get("verifies", False)
        if not isinstance(verifies, bool):
            raise ValueError(f"tool {name}: 'verifies' must be true or false")
        if requires and verifies:
            raise ValueError(f"tool {name}: a tool cannot both require verification and verify the caller")
        retry = body.get("retry", 0)
        if retry not in (0, 1) or isinstance(retry, bool):
            raise ValueError(f"tool {name}: 'retry' must be 0 or 1")
        if retry and risky:   # a timed-out change may have gone through: never repeat it (R12-1)
            raise ValueError(f"tool {name}: a risky tool cannot be retried")
        signature = _signature(name, body)
        for i, rule in enumerate(rules):
            _check_against_signature(f"tool {name} rule {i}", rule, signature, with_when=True)
        if default is not None:
            _check_against_signature(f"tool {name} default", default, signature, with_when=False)
        out[name] = {"params": list(signature), "signature": signature, "rules": rules, "default": default, "risky": risky,
                     "requires": requires, "verifies": verifies, "retry": retry}
    verifiers = [n for n, t in out.items() if t["verifies"]]
    if any(t["requires"] for t in out.values()) and len(verifiers) != 1:
        raise ValueError(f"protected tools need exactly one tool with 'verifies: true', found {verifiers}")
    return out


def _check_outcome(where: str, rule, *, allow_when: bool) -> None:
    if not isinstance(rule, dict):
        raise ValueError(f"{where}: must be a mapping")
    allowed = {"return", "error", "delay_ms"} | ({"when"} if allow_when else set())
    extra = set(rule) - allowed
    if extra:
        raise ValueError(f"{where}: unknown keys {sorted(extra)}")
    if ("return" in rule) == ("error" in rule):
        raise ValueError(f"{where}: needs exactly one of 'return' or 'error'")
    delay = rule.get("delay_ms", 0)
    if not isinstance(delay, int) or isinstance(delay, bool) or delay < 0:
        raise ValueError(f"{where}: 'delay_ms' must be an integer >= 0")
    if allow_when and not isinstance(rule.get("when"), dict):
        raise ValueError(f"{where}: 'when' must be a mapping")


def _check_against_signature(where: str, rule: dict, signature: Signature, *, with_when: bool) -> None:
    """The fake API cannot drift from the spec (P6): `when` names declared params with fitting values; `return` names
    declared response fields with fitting values."""
    if with_when and signature.typed:   # the old list form never named its `when` keys
        for k, v in rule["when"].items():
            if k not in signature.params:
                raise ValueError(f"{where}: `when` names `{k}`, which is not a param (params: {list(signature)})")
            if not value_fits(v, signature.params[k]):
                raise ValueError(f"{where}: `when.{k}` = {v!r} does not fit its type {signature.params[k]['type']}")
    if "return" in rule and signature.returns is not None:
        if not isinstance(rule["return"], dict):
            raise ValueError(f"{where}: `return` must be a mapping")
        for k, v in rule["return"].items():
            if k not in signature.returns:
                raise ValueError(f"{where}: `return` has `{k}`, which `returns` does not declare "
                                 f"(declared: {list(signature.returns)})")
            if not value_fits(v, signature.returns[k]):
                raise ValueError(f"{where}: `return.{k}` = {v!r} does not fit its type {signature.returns[k]['type']}")
