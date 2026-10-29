"""Type dictionary and session roles of a domain (`types.yaml`), and the roles of a flow (ADR 0014 parts 1, 2, 4).

The studio checks shape only: names, references inside the document, no nesting (Q55), labels as {lang: text} (Q54).
The engine loader decides the rest at validation, so a field type the studio does not list yet is kept, not refused.
"""

from __future__ import annotations

import re
from typing import Any

TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SCOPES = ("flow", "session")


def field_spec(v: Any) -> dict:
    """`name: text` and `name: {type: text, length: 8}` are the same field."""
    return {"type": v} if isinstance(v, str) else dict(v or {})


def _label_errors(where: str, label: Any) -> list[str]:
    if label is None:
        return []
    if not isinstance(label, dict) or not all(isinstance(k, str) and isinstance(t, str) for k, t in label.items()):
        return [f"{where}: label must map a language to a text"]
    return []


def check_types(doc: Any) -> list[str]:
    """Problems of a `types.yaml` document, empty when the shape is fine."""
    if not isinstance(doc, dict):
        return ["types.yaml must be a map"]
    errs: list[str] = []
    types = doc.get("types") or {}
    if not isinstance(types, dict):
        return ["types must be a map"]
    for name, t in types.items():
        where = f"type {name}"
        if not TYPE_NAME.match(str(name)):
            errs.append(f"{where}: a type name starts with a capital letter, letters and digits only")
        if not isinstance(t, dict):
            errs.append(f"{where}: must be a map")
            continue
        errs += _label_errors(where, t.get("label"))
        has_fields, has_scalar = "fields" in t, "scalar" in t
        if has_fields == has_scalar:
            errs.append(f"{where}: give either fields or scalar")
            continue
        if has_scalar:
            if not isinstance(t["scalar"], str) or t["scalar"] in types:
                errs.append(f"{where}: scalar is a field type, not another type")
            continue
        fields = t["fields"]
        if not isinstance(fields, dict) or not fields:
            errs.append(f"{where}: needs at least one field")
            continue
        for fname, fv in fields.items():
            fw = f"{where}, field {fname}"
            if not NAME.match(str(fname)):
                errs.append(f"{fw}: lower-case letters, digits and _ only, starting with a letter")
            if not isinstance(fv, (str, dict)):
                errs.append(f"{fw}: must be a field type or a map")
                continue
            spec = field_spec(fv)
            ftype = spec.get("type")
            if not isinstance(ftype, str) or not ftype:
                errs.append(f"{fw}: needs a type")
            elif ftype in types:
                errs.append(f"{fw}: a field cannot hold another type (no nesting)")
            if "fields" in spec:
                errs.append(f"{fw}: a field cannot hold other fields (no nesting)")
            if ftype == "choice" and not (isinstance(spec.get("values"), list) and spec["values"]):
                errs.append(f"{fw}: a choice needs its values")
            if "length" in spec and not (isinstance(spec["length"], int) and spec["length"] >= 1):
                errs.append(f"{fw}: length must be a whole number of at least 1")
            errs += _label_errors(fw, spec.get("label"))
    roles = doc.get("roles") or {}
    if not isinstance(roles, dict):
        return errs + ["roles must be a map"]
    for rname, r in roles.items():
        errs += _role_errors(f"session role {rname}", rname, r, types, roles, "session")
    return errs


def _role_errors(where: str, rname: Any, r: Any, types: dict, roles: dict, scope: str) -> list[str]:
    if not NAME.match(str(rname)):
        return [f"{where}: lower-case letters, digits and _ only, starting with a letter"]
    if not isinstance(r, dict):
        return [f"{where}: must be a map"]
    errs = _label_errors(where, r.get("label"))
    if r.get("type") not in types:
        errs.append(f"{where}: type {r.get('type')!r} is not in the type dictionary")
    elif "fields" not in types[r["type"]]:
        errs.append(f"{where}: a role holds a type with fields")
    if r.get("scope", scope) != scope:
        errs.append(f"{where}: scope must be {scope} here")
    d = r.get("default")
    if d is not None:
        if not isinstance(d, dict) or d.get("from") not in roles or d.get("from") == rname:
            errs.append(f"{where}: default.from must name another role")
        elif roles[d["from"]].get("type") != r.get("type"):
            errs.append(f"{where}: default.from must be a role of the same type")
    return errs


def check_flow_roles(roles: Any, types_doc: dict | None) -> list[str]:
    """The `roles` key of a flow header: flow-scoped roles of types in the domain's dictionary."""
    if not isinstance(roles, dict):
        return ["roles must be a map"]
    types = (types_doc or {}).get("types") or {}
    session_roles = (types_doc or {}).get("roles") or {}
    errs = []
    for rname, r in roles.items():
        if rname in session_roles:
            errs.append(f"role {rname}: the name is taken by a session role")
            continue
        errs += _role_errors(f"role {rname}", rname, r, types, {**session_roles, **roles}, "flow")
    return errs


def role_types(flow_header: dict, types_doc: dict | None) -> dict[str, str]:
    """role name -> type name, flow roles over session roles."""
    out = {n: r.get("type") for n, r in ((types_doc or {}).get("roles") or {}).items() if isinstance(r, dict)}
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
    field that a flow asks or binds, or a removed session role that a step reads. `flows` holds (bot slug, flow id, header, nodes)."""
    new_types = new.get("types") or {}
    gone_roles = set((old or {}).get("roles") or {}) - set(new.get("roles") or {})
    out = []
    for bot, fid, header, nodes in flows:
        for nid, n in nodes.items():
            if not isinstance(n, dict):
                continue
            used = {n.get("role")} | {s.get("role") for s in (n.get("bind") or {}).values() if isinstance(s, dict)}
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
    """type name -> where it is used (session roles, flow roles), for the dictionary screen."""
    out: dict[str, list[dict]] = {n: [] for n in (doc.get("types") or {})}
    for rname, r in (doc.get("roles") or {}).items():
        if isinstance(r, dict) and r.get("type") in out:
            out[r["type"]].append({"role": rname, "scope": "session"})
    for bot, fid, header, _nodes in flows:
        for rname, r in (header.get("roles") or {}).items():
            if isinstance(r, dict) and r.get("type") in out:
                out[r["type"]].append({"role": rname, "scope": "flow", "bot": bot, "flow": fid})
    return out
