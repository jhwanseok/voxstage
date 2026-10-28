"""Bot defaults: the engine's `rules/config.yaml` plus values the studio keeps for itself.

Engine part: the sections and limits are the ones `voxstage/domain_pack.py` checks at load (`load_fallback`,
`load_ask_policy`, `load_max_parked`, `load_correction_policy`, `load_verification_policy`, `load_tool_policy`); the
same checks run here so a bad value is refused on save, and the loader still has the last word at validation.

Studio-only part (`bot.studio_settings`, never exported): values the engine does not read yet, such as the hand-off
number and the values of `{policy.<key>}` (the engine takes those from the request's `setup.policy`, R14).
"""

from __future__ import annotations

import re
from typing import Any

ACTIONS = ("handoff", "end_call")

# section -> {key: (minimum, default)}; `on_exceed` is listed apart because it is a choice, not a count
ENGINE_FIELDS: dict[str, dict[str, tuple[int, int]]] = {
    "fallback": {"max_misses": (1, 3)},
    "ask": {"max_reprompts": (0, 2)},
    "switch": {"max_parked": (1, 2)},
    "correction": {"max_corrections": (0, 2)},
    "verification": {"max_attempts": (1, 3)},
    "tools": {"max_failures": (1, 2), "timeout_ms": (1, 5000)},
}
HAS_ACTION = ("fallback", "ask", "correction", "verification", "tools")

POLICY_REF = re.compile(r"\{\s*policy\.(\w+)")


class SettingsError(ValueError):
    pass


def engine_view(body: dict | None) -> dict:
    """The config as the form shows it: every section and key, the engine default where the file is silent."""
    body = body if isinstance(body, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for section, keys in ENGINE_FIELDS.items():
        raw = body.get(section) if isinstance(body.get(section), dict) else {}
        out[section] = {k: raw.get(k, default) for k, (_, default) in keys.items()}
        if section in HAS_ACTION:
            out[section]["on_exceed"] = raw.get("on_exceed", "handoff")
    return out


def check_engine(values: dict) -> dict:
    """Refuse what the loader would refuse; returns the clean sections."""
    if not isinstance(values, dict):
        raise SettingsError("engine settings must be a mapping")
    unknown = set(values) - set(ENGINE_FIELDS)
    if unknown:
        raise SettingsError(f"unknown sections {sorted(unknown)}")
    clean: dict[str, dict[str, Any]] = {}
    for section, keys in ENGINE_FIELDS.items():
        raw = values.get(section) or {}
        allowed = set(keys) | ({"on_exceed"} if section in HAS_ACTION else set())
        extra = set(raw) - allowed
        if extra:
            raise SettingsError(f"{section}: unknown keys {sorted(extra)}")
        sec: dict[str, Any] = {}
        for k, (minimum, default) in keys.items():
            v = raw.get(k, default)
            if not isinstance(v, int) or isinstance(v, bool) or v < minimum:
                raise SettingsError(f"{section}.{k} must be an integer >= {minimum}")
            sec[k] = v
        if section in HAS_ACTION:
            action = raw.get("on_exceed", "handoff")
            if action not in ACTIONS:
                raise SettingsError(f"{section}.on_exceed must be handoff or end_call")
            sec["on_exceed"] = action
        clean[section] = sec
    return clean


def merge_config(current: dict | None, clean: dict) -> dict:
    """Write the form's values into the stored config; section order of the file is kept, new sections go last."""
    out = dict(current) if isinstance(current, dict) else {}
    for section, values in clean.items():
        prev = out.get(section) if isinstance(out.get(section), dict) else {}
        out[section] = {**prev, **values}
    return out


def check_studio_only(values: dict | None) -> dict:
    values = values or {}
    if not isinstance(values, dict) or set(values) - {"handoff_number", "policy"}:
        raise SettingsError("studio settings take handoff_number and policy only")
    number = values.get("handoff_number")
    if number is not None:
        if not isinstance(number, str) or not re.fullmatch(r"[0-9+\-() ]{0,30}", number):
            raise SettingsError("handoff_number: digits, spaces and + - ( ) only, at most 30 characters")
        number = number.strip() or None
    policy = values.get("policy") or {}
    if not isinstance(policy, dict) or not all(isinstance(k, str) and re.fullmatch(r"\w+", k) for k in policy):
        raise SettingsError("policy: a mapping of value names")
    policy = {k: str(v) for k, v in policy.items() if v is not None and str(v).strip() != ""}
    return {"handoff_number": number, "policy": policy}


def policy_refs(flows) -> list[dict]:
    """Keys of `{policy.<key>}` used by the bot's flows, with the flows that use them."""
    seen: dict[str, list[str]] = {}

    def walk(v, fid):
        if isinstance(v, str):
            for key in POLICY_REF.findall(v):
                if fid not in seen.setdefault(key, []):
                    seen[key].append(fid)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x, fid)
        elif isinstance(v, list):
            for x in v:
                walk(x, fid)

    for f in flows:
        walk(f.nodes, f.flow_id)
    return [{"key": k, "flows": sorted(v)} for k, v in sorted(seen.items())]
