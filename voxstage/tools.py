"""Tool (external API) execution behind a port, with a declarative fake backend.

`ToolExecutor` is the port: dialogue managers ask for a tool by name and arguments and get a
`ToolResult` back. `FakeApiExecutor` is the adapter used for experiments: it answers from a
rule table keyed by the call's arguments, so a domain pack ships its "API" as data
(`domains/<name>/tools.yaml`) and the core never imports domain code.
See docs/decisions/0004-dummy-api-tool-executor.md.

Rule table format:

    tools:
      get_fee:
        params: [amount, grade]          # required arguments
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
        for p in spec["params"]:
            if p not in args:
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
        extra = set(body) - {"params", "rules", "default", "risky", "requires", "verifies", "retry"}
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
        out[name] = {"params": list(body.get("params", [])), "rules": rules, "default": default, "risky": risky,
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
