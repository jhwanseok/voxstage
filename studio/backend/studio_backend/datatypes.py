"""Type dictionary and session role of a domain (`types.yaml`), and the roles of a flow (ADR 0014, engine R16a).

The shapes follow the engine loader (`voxstage/rules/types.py`, `_flow_roles` in `voxstage/rules/flows.py`) so a save is
refused with a reason the user can act on, before validation. The loader still has the last word.
"""

from __future__ import annotations

import re
from typing import Any

NAME = re.compile(r"^[a-z][a-z0-9_]*$")
TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
SESSION_ROLE = "caller"                                  # the only session role of v1 (decision B)
RESERVED = {"slots", "customer", "policy", "result"}     # names a flow role cannot take
FIELD_KEYS = {"type", "length", "choices", "label"}


def _label_errors(where: str, label: Any) -> list[str]:
    if label is None:
        return []
    if not isinstance(label, dict) or not all(isinstance(k, str) and isinstance(t, str) and t.strip() for k, t in label.items()):
        return [f"{where}: label must map a language to a display name"]
    return []


def check_types(doc: Any, extractors: tuple[str, ...]) -> list[str]:
    """Problems of a `types.yaml` document, empty when the shape is fine. An empty document means no file."""
    if not isinstance(doc, dict):
        return ["types.yaml must be a map"]
    if set(doc) - {"types", "session_roles"}:
        return [f"unknown keys {sorted(set(doc) - {'types', 'session_roles'})}"]
    types = doc.get("types") or {}
    roles = doc.get("session_roles") or {}
    if not isinstance(types, dict) or not isinstance(roles, dict):
        return ["types and session_roles must be maps"]
    if roles and not types:
        return ["a session role needs a type"]
    errs: list[str] = []
    for name, t in types.items():
        where = f"type {name}"
        if not TYPE_NAME.match(str(name)):
            errs.append(f"{where}: a type name starts with a capital letter, letters and digits only")
        if not isinstance(t, dict) or set(t) - {"fields", "label"} or not isinstance(t.get("fields"), dict) or not t["fields"]:
            errs.append(f"{where}: needs at least one field")
            continue
        errs += _label_errors(where, t.get("label"))
        for fname, f in t["fields"].items():
            fw = f"{where}, field {fname}"
            if not NAME.match(str(fname)):
                errs.append(f"{fw}: lower-case letters, digits and _ only, starting with a letter")
            if not isinstance(f, dict) or "type" not in f or set(f) - FIELD_KEYS:
                errs.append(f"{fw}: needs a type (and optionally length, choices, label)")
                continue
            if f["type"] in types:
                errs.append(f"{fw}: a field cannot hold another type (no nesting)")
            elif f["type"] not in extractors:
                errs.append(f"{fw}: type must be one of {list(extractors)}")
            if (f["type"] == "choice") != bool(f.get("choices")):
                errs.append(f"{fw}: a choice needs its choices, and only a choice has them")
            if "length" in f and (f["type"] != "digits" or not isinstance(f["length"], int) or f["length"] < 1):
                errs.append(f"{fw}: length is a whole number of at least 1, for digits only")
            errs += _label_errors(fw, f.get("label"))
    for rname, r in roles.items():
        where = f"session role {rname}"
        if rname != SESSION_ROLE:
            errs.append(f"{where}: the only session role is {SESSION_ROLE}")
        elif not isinstance(r, dict) or set(r) - {"type", "label"} or r.get("type") not in types:
            errs.append(f"{where}: needs a type from the dictionary")
        else:
            errs += _label_errors(where, r.get("label"))
    return errs


def check_flow_roles(roles: Any, types_doc: dict | None) -> list[str]:
    """The `roles` key of a flow header: flow roles of types in the domain's dictionary."""
    types = (types_doc or {}).get("types") or {}
    session = (types_doc or {}).get("session_roles") or {}
    if not types:
        return ["roles need the domain's type dictionary (데이터)"]
    if not isinstance(roles, dict) or not roles:
        return ["roles must map role names to a type"]
    errs = []
    for rname, r in roles.items():
        where = f"role {rname}"
        if not NAME.match(str(rname)):
            errs.append(f"{where}: lower-case letters, digits and _ only, starting with a letter")
            continue
        if rname in session or rname in RESERVED:
            errs.append(f"{where}: the name is taken by a session role or a reserved name")
            continue
        if not isinstance(r, dict) or set(r) - {"type", "default", "label"} or r.get("type") not in types:
            errs.append(f"{where}: type {r.get('type') if isinstance(r, dict) else r!r} is not in the type dictionary")
            continue
        errs += _label_errors(where, r.get("label"))
        d = r.get("default")
        if d is not None:
            src = d.get("from") if isinstance(d, dict) else None
            if not isinstance(d, dict) or set(d) != {"from"} or src not in roles or src == rname \
                    or not isinstance(roles[src], dict) or roles[src].get("type") != r["type"]:
                errs.append(f"{where}: default.from must name another role of this scenario with the same type")
    return errs


def role_types(flow_header: dict, types_doc: dict | None) -> dict[str, str]:
    """role name -> type name, the session role and the flow's roles."""
    out = {n: r.get("type") for n, r in ((types_doc or {}).get("session_roles") or {}).items() if isinstance(r, dict)}
    out.update({n: r.get("type") for n, r in (flow_header.get("roles") or {}).items() if isinstance(r, dict)})
    return out


def references(flow_header: dict, nodes: dict, types_doc: dict | None) -> list[tuple[str, str, str]]:
    """Every (type, field, node id) a flow reads or fills: `ask` with role and field, and `bind` role sources."""
    rt = role_types(flow_header, types_doc)
    out = []
    for nid, n in nodes.items():
        if not isinstance(n, dict):
            continue
        if n.get("role") in rt and n.get("field"):
            out.append((rt[n["role"]], n["field"], nid))
        for src in (n.get("bind") or {}).values():
            if isinstance(src, dict) and src.get("role") in rt and src.get("field"):
                out.append((rt[src["role"]], src["field"], nid))
    return out


def broken_by(old: dict | None, new: dict, flows: list[tuple[str, str, dict, dict]]) -> list[dict]:
    """Uses in flows that a new dictionary would leave dangling: a removed type that a flow role holds, a removed
    field that a flow asks or binds, or a removed session role that a step reads. `flows` holds (bot, flow id,
    header, nodes)."""
    new_types = new.get("types") or {}
    gone_roles = set((old or {}).get("session_roles") or {}) - set(new.get("session_roles") or {})
    out = []
    for bot, fid, header, nodes in flows:
        for nid, n in nodes.items():
            if not isinstance(n, dict):
                continue
            used = {s.get("role") for s in (n.get("bind") or {}).values() if isinstance(s, dict)}
            for rname in sorted(r for r in used if r in gone_roles and r not in (header.get("roles") or {})):
                out.append({"bot": bot, "flow": fid, "node": nid, "role": rname})
        for rname, r in (header.get("roles") or {}).items():
            if isinstance(r, dict) and r.get("type") not in new_types:
                out.append({"bot": bot, "flow": fid, "role": rname, "type": r.get("type")})
        for tname, field, nid in references(header, nodes, new):
            t = new_types.get(tname)
            if t is not None and field not in (t.get("fields") or {}):
                out.append({"bot": bot, "flow": fid, "node": nid, "type": tname, "field": field})
    return out


def usage(doc: dict, flows: list[tuple[str, str, dict, dict]]) -> dict[str, list[dict]]:
    """type name -> where it is used (the session role, flow roles), for the dictionary screen."""
    out: dict[str, list[dict]] = {n: [] for n in (doc.get("types") or {})}
    for rname, r in (doc.get("session_roles") or {}).items():
        if isinstance(r, dict) and r.get("type") in out:
            out[r["type"]].append({"role": rname, "scope": "session"})
    for bot, fid, header, _nodes in flows:
        for rname, r in (header.get("roles") or {}).items():
            if isinstance(r, dict) and r.get("type") in out:
                out[r["type"]].append({"role": rname, "scope": "flow", "bot": bot, "flow": fid})
    return out
