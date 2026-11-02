"""Slot lists of a domain (ST3): `sensitive_slots.yaml` (keypad only) and `readback_slots.yaml` (read back after filling).

Both files are language-free and shared by the bots of the domain. The engine refuses a sensitive attribute that a
scenario asks with an extractor other than `digits` (`_ask` in `voxstage/rules/flows.py`), so only attributes asked as
digits are offered, and the same check runs on save. The format of a read-back attribute is one of the engine's
formatter calls (`load_readback_slots`).
"""

from __future__ import annotations

import os
import re
import tempfile

from voxstage import domain_pack
from voxstage.domain_pack import RuleError
from voxstage.rules.formatters import FORMATTERS

from . import wording

CURRENCIES = ("KRW", "USD")      # the engine's `money` table (voxstage/rules/formatters.py)
FORMAT_LABELS = {"count": "숫자(세 자리마다 쉼표)", "date": "날짜", "money('KRW')": "금액(원)", "money('USD')": "금액(달러)"}
FORMAT_CALL = re.compile(r"^(\w+)(?:\(\s*'([A-Za-z]+)'\s*\))?$")
ATTRIBUTE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$")


def formats() -> list[dict]:
    """The formatter calls the form offers: every engine formatter without arguments, and `money` per currency."""
    out = []
    for name in sorted(FORMATTERS):
        if FORMATTERS[name].max_args == 0:
            out.append(name)
        elif name == "money":
            out += [f"money('{c}')" for c in CURRENCIES]
    return [{"call": c, "label": FORMAT_LABELS.get(c, c)} for c in out]


def check_format(call: str) -> str | None:
    """None when the engine can use the call, else why not."""
    m = FORMAT_CALL.match(call.strip()) if isinstance(call, str) else None
    if m is None:
        return "형식을 고르세요."
    name, arg = m.groups()
    if name not in FORMATTERS:
        return f"모르는 형식입니다({name})."
    f = FORMATTERS[name]
    if (arg is None and f.min_args > 0) or (arg is not None and f.max_args == 0):
        return "형식의 인자가 맞지 않습니다."
    if name == "money" and arg.upper() not in CURRENCIES:
        return f"통화는 {', '.join(CURRENCIES)} 중에서 고르세요."
    return None


def asked_attributes(flows: list[tuple[str, str, dict, dict]], types_doc: dict | None) -> dict[str, dict]:
    """attribute -> {"extractors": set, "flows": [(bot, flow)]}: every attribute the domain's scenarios ask, with the
    extractor of each ask (a role's field takes the extractor of its type unless the step names its own)."""
    types = (types_doc or {}).get("types") or {}
    session = (types_doc or {}).get("session_roles") or {}
    out: dict[str, dict] = {}
    for bot, fid, header, nodes in flows:
        roles = {**{n: r for n, r in session.items() if isinstance(r, dict)},
                 **{n: r for n, r in (header.get("roles") or {}).items() if isinstance(r, dict)}}
        for n in nodes.values():
            if not isinstance(n, dict):
                continue
            specs = []   # (slot, extractor)
            if n.get("type") == "ask":
                if n.get("role") and n.get("field"):
                    ft = ((types.get((roles.get(n["role"]) or {}).get("type")) or {}).get("fields") or {}).get(n["field"]) or {}
                    specs.append((f"{n['role']}.{n['field']}", n.get("extractor") or ft.get("type")))
                elif isinstance(n.get("slot"), str):
                    specs.append((n["slot"], n.get("extractor", "text")))
            elif n.get("type") == "form":
                specs += [(s["slot"], s.get("extractor", "text")) for s in n.get("slots") or []
                          if isinstance(s, dict) and isinstance(s.get("slot"), str)]
            for slot, ex in specs:
                e = out.setdefault(slot, {"extractors": set(), "flows": []})
                e["extractors"].add(ex)
                if (bot, fid) not in e["flows"]:
                    e["flows"].append((bot, fid))
    for name in set(header_captures(flows)):
        out.setdefault(name, {"extractors": set(), "flows": []})["extractors"].add("capture")
    return out


def header_captures(flows) -> list[str]:
    return [c for _b, _f, header, _n in flows for c in (header.get("captures") or {})]


def candidates(asked: dict[str, dict]) -> dict[str, list[str]]:
    """Attributes the lists may take: sensitive only where every ask is `digits`; read back any asked attribute."""
    return {"sensitive": sorted(a for a, e in asked.items() if e["extractors"] == {"digits"}),
            "readback": sorted(asked)}


def check_lists(sensitive: list, readback: list, current: dict, asked: dict[str, dict]) -> dict:
    """`{sensitive: [names], readback: {name: call}}` for the stored files, or WordingError with per-field problems.
    An entry already stored stays allowed when no scenario asks it; a new one must be an attribute that fits."""
    problems: list[dict] = []
    clean_sensitive, seen = [], set()
    for name in sensitive:
        if not isinstance(name, str) or not ATTRIBUTE.match(name):
            problems.append({"field": f"sensitive.{name}", "message": "속성 이름이 올바르지 않습니다."})
            continue
        if name in seen:
            continue
        seen.add(name)
        ex = (asked.get(name) or {}).get("extractors")
        if ex and ex != {"digits"}:
            problems.append({"field": f"sensitive.{name}", "message": "키패드로만 받는 속성은 숫자(digits) 형식이어야 합니다. "
                             "시나리오에서 이 속성을 숫자 형식으로 받도록 바꾸거나 목록에서 빼세요."})
        elif not ex and name not in current.get("sensitive", []):
            problems.append({"field": f"sensitive.{name}", "message": "시나리오가 받지 않는 속성입니다."})
        clean_sensitive.append(name)
    clean_readback, seen = {}, set()
    for item in readback:
        name = item.get("slot") if isinstance(item, dict) else None
        call = item.get("format") if isinstance(item, dict) else None
        if not isinstance(name, str) or not ATTRIBUTE.match(name):
            problems.append({"field": f"readback.{name}", "message": "속성 이름이 올바르지 않습니다."})
            continue
        if name in seen:
            problems.append({"field": f"readback.{name}", "message": "같은 속성이 두 번 있습니다."})
            continue
        seen.add(name)
        why = check_format(call)
        if why:
            problems.append({"field": f"readback.{name}", "message": why})
        elif name not in asked and name not in current.get("readback", {}):
            problems.append({"field": f"readback.{name}", "message": "시나리오가 받지 않는 속성입니다."})
        else:
            clean_readback[name] = call.strip()
    if problems:
        raise wording.WordingError(problems)
    # the engine's loader has the last word
    with tempfile.TemporaryDirectory(prefix="studio-slots-") as root:
        for kind, body in (("sensitive_slots", {"sensitive_slots": clean_sensitive}),
                           ("readback_slots", {"readback_slots": clean_readback})):
            if not body[kind]:
                continue   # an empty list is no file
            path = os.path.join(root, f"{kind}.yaml")
            wording._write(path, body)
            try:
                (domain_pack.load_sensitive_slots if kind == "sensitive_slots" else domain_pack.load_readback_slots)(path)
            except RuleError as exc:
                raise wording.WordingError([{"field": "", "message": wording._clean_path(str(exc), path, f"{kind}.yaml")}])
    return {"sensitive": clean_sensitive, "readback": clean_readback}
