"""Compare two sets of a bot's files: the file list with unified text diffs, and a summary by meaning (ST2, D2).

A set is {relative path: text}: a publication's files or the draft export. `compare(base, target)` says what is
different when going from `base` to `target`. The summary reads the parsed YAML, so it speaks of FAQ entries, steps and
API connections instead of lines.
"""

from __future__ import annotations

import difflib

from . import yamlio
from .portable import BOT_SETTINGS, SHARED_SETTINGS

# keys of a step that say where it goes next; a change there is "rewired", not an edit of the step's content
EXIT_KEYS = {"next", "on_yes", "on_no", "on_ok", "on_error", "else"}
SETTING_LABELS = {"sensitive_slots": "민감 속성 목록", "readback_slots": "다시 읽어 줄 속성 목록", "types": "속성 형식",
                  "config": "봇 설정", "confirm": "확인 규칙", "commands": "명령어 규칙", "corrections": "정정 규칙",
                  "confusions": "헷갈리는 말 규칙"}


def file_diff(base: dict[str, str], target: dict[str, str]) -> list[dict]:
    """One row per file that differs: status "added" / "removed" / "changed" and the unified diff of its text."""
    rows = []
    for path in sorted(set(base) | set(target)):
        a, b = base.get(path), target.get(path)
        if a == b:
            continue
        status = "added" if a is None else "removed" if b is None else "changed"
        text = "".join(difflib.unified_diff((a or "").splitlines(keepends=True), (b or "").splitlines(keepends=True),
                                            fromfile=f"a/{path}" if a is not None else "/dev/null",
                                            tofile=f"b/{path}" if b is not None else "/dev/null"))
        rows.append({"path": path, "status": status, "unified": text})
    return rows


def _doc(files: dict[str, str], path: str):
    text = files.get(path)
    if text is None:
        return None
    try:
        return yamlio.load(text)
    except Exception:       # a raw file the studio does not model; it is reported as a file, not as meaning
        return None


def _differing(a: dict, b: dict) -> list[str]:
    return [k for k in list(a) + [k for k in b if k not in a] if a.get(k) != b.get(k)]


def _faq(base, target, d, lang) -> dict:
    def entries(files):
        out = {}
        for e in (_doc(files, f"{d}/{lang}/faq.yaml") or {}).get("entries") or []:
            out[e["id"]] = {k: v for k, v in e.items() if k != "id"}
        for e in (_doc(files, f"{d}/{lang}/rules/faq_patterns.yaml") or {}).get("entries") or []:
            out.setdefault(e["id"], {})["pattern"] = {k: v for k, v in e.items() if k != "id"}
        return out
    a, b = entries(base), entries(target)
    changed = []
    for eid in a.keys() & b.keys():
        fields = _differing(a[eid], b[eid])
        if fields:
            changed.append({"id": eid, "question": b[eid].get("question"), "fields": fields})
    return {"added": [{"id": i, "question": b[i].get("question")} for i in b if i not in a],
            "removed": [{"id": i, "question": a[i].get("question")} for i in a if i not in b],
            "changed": sorted(changed, key=lambda c: c["id"])}


def _exits(body: dict) -> dict[str, str]:
    from .service import _edges     # one table of exits for the editor and for this comparison
    return {handle: target for handle, _label, target in _edges("", body or {})}


def _flow(a: dict, b: dict) -> dict:
    an, bn = a.get("nodes") or {}, b.get("nodes") or {}
    steps_changed, rewired = [], []
    for sid in an.keys() & bn.keys():
        x, y = an[sid] or {}, bn[sid] or {}
        fields = [k for k in _differing(x, y) if k not in EXIT_KEYS]
        if fields:
            steps_changed.append({"id": sid, "type": y.get("type"), "fields": fields})
        ex, ey = _exits(x), _exits(y)
        for handle in sorted(set(ex) | set(ey)):
            if ex.get(handle) != ey.get(handle):
                rewired.append({"step": sid, "handle": handle, "before": ex.get(handle), "after": ey.get(handle)})
    header = [k for k in _differing({k: v for k, v in a.items() if k not in ("nodes", "start", "id")},
                                    {k: v for k, v in b.items() if k not in ("nodes", "start", "id")})]
    out = {"steps_added": [{"id": s, "type": (bn[s] or {}).get("type")} for s in bn if s not in an],
           "steps_removed": [{"id": s, "type": (an[s] or {}).get("type")} for s in an if s not in bn],
           "steps_changed": sorted(steps_changed, key=lambda c: c["id"]), "rewired": rewired, "header": header,
           "start": [a.get("start"), b.get("start")] if a.get("start") != b.get("start") else None}
    return out


def _flows(base, target, d, lang) -> dict:
    prefix = f"{d}/{lang}/flows/"

    def docs(files):
        return {p[len(prefix):-5]: _doc(files, p) or {} for p in files if p.startswith(prefix) and p.endswith(".yaml")}
    a, b = docs(base), docs(target)
    changed = []
    for fid in sorted(a.keys() & b.keys()):
        detail = _flow(a[fid], b[fid])
        if any(detail.values()):
            changed.append({"id": fid, **detail})
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)), "changed": changed}


def _tools(base, target, d) -> dict:
    def tools(files):
        return (_doc(files, f"{d}/tools.yaml") or {}).get("tools") or {}
    a, b = tools(base), tools(target)
    changed = []
    for name in a.keys() & b.keys():
        x, y = a[name] or {}, b[name] or {}
        fields = _differing(x, y) if isinstance(x, dict) and isinstance(y, dict) else ["body"]
        if fields:
            changed.append({"name": name, "fields": fields})
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "changed": sorted(changed, key=lambda c: c["name"])}


def _settings(base, target, d, lang) -> list[dict]:
    out = []
    paths = {f"{d}/{rel}": ("shared", kind) for kind, rel in SHARED_SETTINGS.items()}
    paths.update({f"{d}/{lang}/{rel}": ("bot", kind) for kind, rel in BOT_SETTINGS.items()})
    for path, (scope, kind) in paths.items():
        if base.get(path) == target.get(path):
            continue
        a, b = _doc(base, path), _doc(target, path)
        status = "added" if path not in base else "removed" if path not in target else "changed"
        keys = _differing(a, b) if isinstance(a, dict) and isinstance(b, dict) else []
        out.append({"kind": kind, "label": SETTING_LABELS[kind], "scope": scope, "path": path, "status": status,
                    "keys": keys})
    return out


def summary(base: dict[str, str], target: dict[str, str], domain: str, lang: str) -> dict:
    modelled = {f"{domain}/tools.yaml", f"{domain}/{lang}/faq.yaml", f"{domain}/{lang}/rules/faq_patterns.yaml"}
    modelled |= {f"{domain}/{rel}" for rel in SHARED_SETTINGS.values()}
    modelled |= {f"{domain}/{lang}/{rel}" for rel in BOT_SETTINGS.values()}
    flow_prefix = f"{domain}/{lang}/flows/"
    other = [{"path": r["path"], "status": r["status"]} for r in file_diff(base, target)
             if r["path"] not in modelled and not r["path"].startswith(flow_prefix)]
    out = {"faq": _faq(base, target, domain, lang), "flows": _flows(base, target, domain, lang),
           "tools": _tools(base, target, domain), "settings": _settings(base, target, domain, lang), "other": other}
    out["empty"] = not (any(out["faq"].values()) or any(out["flows"].values()) or any(out["tools"].values())
                        or out["settings"] or other)
    return out


def compare(base: dict[str, str], target: dict[str, str], domain: str, lang: str) -> dict:
    """What changes going from `base` to `target`."""
    return {"files": file_diff(base, target), "summary": summary(base, target, domain, lang)}
