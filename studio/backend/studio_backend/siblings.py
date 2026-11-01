"""Sibling check (ST2, D3): compare the structure of a bot's scenarios with the same-id scenarios of the other-language
bots of its domain. Only structure is compared: step ids and kinds, where steps lead, which API a step calls and which
attribute feeds each of its parameters. Wording, constants and extractor settings differ by language on purpose, so
they are never compared. The result is a list of warnings; nothing in validation or publishing depends on it.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Bot, Flow

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _binding(value) -> str:
    """How a parameter gets its value, without the value itself: a constant, attributes in a template, a call result."""
    if isinstance(value, dict):
        if "call" in value:
            return f"call:{value['call']}.{value.get('field')}"
        if "const" in value:
            return "const"
        return ",".join(f"{k}:{v}" for k, v in sorted(value.items()))
    names = PLACEHOLDER.findall(value) if isinstance(value, str) else []
    return "attributes:" + ",".join(names) if names else "const"


def step_shape(body: dict) -> dict:
    from .service import _edges     # the same table of exits the editor draws
    body = body or {}
    params = {k: _binding(v) for k, v in (body.get("args") or {}).items()}
    params.update({k: _binding(v) for k, v in (body.get("bind") or {}).items()})
    shape = {"kind": body.get("type"), "exits": {h: t for h, _label, t in _edges("", body)}}
    if body.get("tool"):
        shape["tool"] = body["tool"]
    if params:
        shape["params"] = params
    if body.get("slot"):
        shape["attribute"] = body["slot"]
    return shape


def first_difference(here: Flow, there: Flow) -> dict | None:
    """The first structural difference, looking at the start, then the steps in the order of this bot's flow."""
    if here.start != there.start:
        return {"kind": "start", "here": here.start, "there": there.start}
    order = list(here.node_order or here.nodes) + [n for n in (there.node_order or there.nodes) if n not in here.nodes]
    for sid in order:
        a, b = here.nodes.get(sid), there.nodes.get(sid)
        if a is None:
            return {"kind": "step_only_there", "step": sid}
        if b is None:
            return {"kind": "step_only_here", "step": sid}
        x, y = step_shape(a), step_shape(b)
        if x["kind"] != y["kind"]:
            return {"kind": "step_kind", "step": sid, "here": x["kind"], "there": y["kind"]}
        for handle in sorted(set(x["exits"]) | set(y["exits"])):
            if x["exits"].get(handle) != y["exits"].get(handle):
                return {"kind": "exit", "step": sid, "exit": handle,
                        "here": x["exits"].get(handle), "there": y["exits"].get(handle)}
        if x.get("tool") != y.get("tool"):
            return {"kind": "tool", "step": sid, "here": x.get("tool"), "there": y.get("tool")}
        px, py = x.get("params", {}), y.get("params", {})
        for param in sorted(set(px) | set(py)):
            if px.get(param) != py.get(param):
                return {"kind": "binding", "step": sid, "parameter": param, "here": px.get(param), "there": py.get(param)}
        if x.get("attribute") != y.get("attribute"):
            return {"kind": "attribute", "step": sid, "here": x.get("attribute"), "there": y.get("attribute")}
    return None


def check(session: Session, bot: Bot) -> dict:
    """Warnings per sibling bot (same domain, other language), from the drafts."""
    mine = {f.flow_id: f for f in session.scalars(select(Flow).where(Flow.bot_id == bot.id))}
    out = []
    for sib in session.scalars(select(Bot).where(Bot.domain_id == bot.domain_id, Bot.id != bot.id).order_by(Bot.lang)):
        theirs = {f.flow_id: f for f in session.scalars(select(Flow).where(Flow.bot_id == sib.id))}
        warnings = []
        for fid in sorted(set(mine) | set(theirs)):
            if fid not in theirs:
                warnings.append({"flow": fid, "kind": "only_here"})
            elif fid not in mine:
                warnings.append({"flow": fid, "kind": "only_there"})
            else:
                diff = first_difference(mine[fid], theirs[fid])
                if diff:
                    warnings.append({"flow": fid, "kind": "structure_differs", "difference": diff})
        out.append({"bot": sib.slug, "lang": sib.lang, "compared": len(set(mine) & set(theirs)), "warnings": warnings})
    return {"siblings": out, "warning_count": sum(len(s["warnings"]) for s in out)}
