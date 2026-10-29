"""The type dictionary of a domain: `domains/<domain>/types.yaml` (ADR 0014, R16a).

    types:
      Person:
        label: {en: Person, ko: 사람}
        fields:
          name:  {type: text, label: {en: Name, ko: 이름}}
          phone: {type: digits, length: 10}
    session_roles:
      caller: {type: Caller}      # filled by the identity gate (decision B)

A field is a scalar read by one of the existing extractors (`type` is the extractor), so a role field is asked and read
by the code that already reads a slot. Types do not nest (decision D). The file is language-neutral; `label` is the
per-language display name (decision P8) and is not used by the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .flows import EXTRACTORS, FlowError, extractor_spec

SESSION_ROLE = "caller"   # the one session role of v1: the gate's result (decision B)


@dataclass(frozen=True)
class FieldType:
    name: str
    spec: dict   # extractor_spec: extractor, length, choices


@dataclass(frozen=True)
class RecordType:
    name: str
    fields: dict   # field name -> FieldType


@dataclass(frozen=True)
class Types:
    types: dict            # type name -> RecordType
    session_roles: dict    # role name -> type name

    def fields_of(self, role_type: str) -> dict:
        return self.types[role_type].fields


def _labels(raw, where: str) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip()
                                            for k, v in raw.items()):
        raise FlowError(f"{where}: `label` maps a language to a display name")


def load_types(path: str) -> Types:
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise FlowError(f"{path}: invalid YAML ({exc})") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("types"), dict) or not raw["types"] \
            or set(raw) - {"types", "session_roles"}:
        raise FlowError(f"{path}: needs `types` (and optionally `session_roles`)")
    types = {}
    for name, body in raw["types"].items():
        where = f"{path}: type {name}"
        if not isinstance(body, dict) or set(body) - {"fields", "label"} or not isinstance(body.get("fields"), dict) \
                or not body["fields"]:
            raise FlowError(f"{where}: needs `fields` (and optionally `label`)")
        _labels(body.get("label"), where)
        fields = {}
        for fname, fbody in body["fields"].items():
            fwhere = f"{where}, field {fname}"
            if not isinstance(fbody, dict) or "type" not in fbody \
                    or set(fbody) - {"type", "length", "choices", "label"}:
                raise FlowError(f"{fwhere}: needs `type` (and optionally length, choices, label)")
            if fbody["type"] in raw["types"]:
                raise FlowError(f"{fwhere}: a field is a scalar; types do not nest (decision D)")
            if fbody["type"] not in EXTRACTORS:
                raise FlowError(f"{fwhere}: `type` must be one of {EXTRACTORS}")
            _labels(fbody.get("label"), fwhere)
            fields[fname] = FieldType(fname, extractor_spec({"extractor": fbody["type"],
                                                             **{k: fbody[k] for k in ("length", "choices") if k in fbody}},
                                                            fwhere))
        types[name] = RecordType(name, fields)
    session = {}
    for role, body in (raw.get("session_roles") or {}).items():
        where = f"{path}: session role {role}"
        if role != SESSION_ROLE:
            raise FlowError(f"{where}: the only session role is `{SESSION_ROLE}`")
        if not isinstance(body, dict) or set(body) - {"type", "label"} or body.get("type") not in types:
            raise FlowError(f"{where}: needs `type`, one of {sorted(types)}")
        _labels(body.get("label"), where)
        session[role] = body["type"]
    return Types(types, session)
