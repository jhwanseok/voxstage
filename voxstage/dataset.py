"""Loader and validator for domain datasets (FAQ entries and capability scenarios).

A dataset is data only: `domains/<domain>/tools.yaml` (shared by all languages) and, per
language, `domains/<domain>/<lang>/faq.yaml` and `domains/<domain>/<lang>/scenarios/*.yaml`.
Validation is strict on purpose: a typo in a scenario should fail at load time, not turn into
a silently wrong experiment. Format reference: docs/dataset-spec.md.

CLI: python -m voxstage.dataset coverage [domains_dir] [lang]   # capability x domain matrix
"""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass
from typing import Optional

import yaml

DOMAINS = ("bank", "shop", "telecom")
LANGS = ("en", "ko")

CAPABILITIES = {
    "C00": "FAQ answer (baseline)",
    "C01": "Scenario switch",
    "C02": "Return after a side question",
    "C03": "Cancel, back, hand off to an agent",
    "C04": "Button / DTMF input",
    "C05": "Slot re-fill after misrecognition",
    "C06": "Multiple slots, omissions, references",
    "C07": "Number, date, time normalisation",
    "C08": "Answer from attributes and API results",
    "C09": "Condition-specific fixed answer",
    "C10": "External API failure or delay fallback",
    "C11": "Block information before identity check",
    "C12": "Policy-change impact",
}

INPUT_KINDS = {
    "utterance": {"required": {"text"}, "optional": {"asr_text"}},
    "dtmf": {"required": {"digits"}, "optional": set()},
    "button": {"required": {"button_id"}, "optional": {"value"}},
}

ACTION_NAMES = {"HandOff", "EndCall"}
EXPECT_KEYS = {"flow", "slots", "reply_contains", "reply_contains_any", "reply_not_contains",
               "tool_calls", "actions"}
SCENARIO_KEYS = {"id", "lang", "domain", "capability", "title", "setup", "turns", "variants", "tags"}


@dataclass(frozen=True)
class Turn:
    user: dict
    expect: dict


@dataclass(frozen=True)
class Scenario:
    id: str
    lang: str
    domain: str
    capability: str
    title: str
    turns: tuple
    setup: dict
    variants: tuple
    tags: tuple
    path: str


@dataclass(frozen=True)
class FaqEntry:
    id: str
    question: str
    answer: str
    paraphrases: tuple
    asr_variants: tuple


class DatasetError(ValueError):
    pass


def _fail(path: str, msg: str):
    raise DatasetError(f"{path}: {msg}")


def _load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as exc:  # report which file, not just a YAML traceback
            raise DatasetError(f"{path}: invalid YAML ({exc})") from exc


def _check_user(path: str, where: str, user) -> None:
    if not isinstance(user, dict) or user.get("kind") not in INPUT_KINDS:
        _fail(path, f"{where}: user.kind must be one of {sorted(INPUT_KINDS)}")
    rule = INPUT_KINDS[user["kind"]]
    keys = set(user) - {"kind"}
    missing = rule["required"] - keys
    extra = keys - rule["required"] - rule["optional"]
    if missing or extra:
        _fail(path, f"{where}: kind={user['kind']} missing {sorted(missing)}, unexpected {sorted(extra)}")
    for k in keys:
        if not isinstance(user[k], str) or not user[k]:
            _fail(path, f"{where}: {k} must be a non-empty string (quote digits so YAML keeps them as text)")


def _check_expect(path: str, where: str, expect: dict) -> None:
    """Shape checks for `expect`. `tool_calls` is the exact ordered list of calls the manager
    must make (an empty list means none); an entry with `error` expects that failure."""
    if "slots" in expect and not isinstance(expect["slots"], dict):
        _fail(path, f"{where}: slots must be a mapping")
    for key in ("reply_contains", "reply_contains_any", "reply_not_contains"):
        if key in expect and (not isinstance(expect[key], list) or not all(isinstance(x, str) and x for x in expect[key])):
            _fail(path, f"{where}: {key} must be a list of non-empty strings")
    if "actions" in expect:
        bad = [a for a in expect["actions"] if a not in ACTION_NAMES]
        if not isinstance(expect["actions"], list) or bad:
            _fail(path, f"{where}: actions must be a list drawn from {sorted(ACTION_NAMES)}")
    if "tool_calls" in expect:
        calls = expect["tool_calls"]
        if not isinstance(calls, list):
            _fail(path, f"{where}: tool_calls must be a list")
        for c in calls:
            if (not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(c.get("args"), dict)
                    or set(c) - {"name", "args", "error"}):
                _fail(path, f"{where}: each tool call needs name, args and optionally error")
            if not all(isinstance(v, str) for v in c["args"].values()):
                _fail(path, f"{where}: tool call args must be strings (quote numbers)")


def load_scenario(path: str) -> Scenario:
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        _fail(path, "must be a mapping")
    extra = set(raw) - SCENARIO_KEYS
    if extra:
        _fail(path, f"unknown keys {sorted(extra)}")
    for key in ("id", "lang", "domain", "capability", "title", "turns"):
        if key not in raw:
            _fail(path, f"missing '{key}'")
    if raw["lang"] not in LANGS:
        _fail(path, f"lang must be one of {LANGS}")
    if raw["domain"] not in DOMAINS:
        _fail(path, f"domain must be one of {DOMAINS}")
    if raw["capability"] not in CAPABILITIES:
        _fail(path, f"capability must be one of {sorted(CAPABILITIES)}")
    if not str(raw["id"]).startswith(f"{raw['domain']}.{raw['capability']}."):
        _fail(path, f"id must start with '{raw['domain']}.{raw['capability']}.'")
    parts = os.path.abspath(path).split(os.sep)
    if len(parts) < 5 or parts[-2] != "scenarios" or parts[-3] != raw["lang"] or parts[-4] != raw["domain"]:
        _fail(path, "file must be under domains/<domain>/<lang>/scenarios/ matching its domain and lang")
    turns = raw["turns"]
    if not isinstance(turns, list) or not turns:
        _fail(path, "turns must be a non-empty list")
    parsed = []
    for i, t in enumerate(turns):
        if not isinstance(t, dict) or set(t) - {"user", "expect"} or "user" not in t:
            _fail(path, f"turn {i}: needs 'user' and optional 'expect' only")
        _check_user(path, f"turn {i}", t["user"])
        expect = t.get("expect") or {}
        bad = set(expect) - EXPECT_KEYS
        if bad:
            _fail(path, f"turn {i}: unknown expect keys {sorted(bad)}")
        _check_expect(path, f"turn {i}", expect)
        parsed.append(Turn(user=t["user"], expect=expect))
    variants = raw.get("variants") or []
    for v in variants:
        if (not isinstance(v, dict) or not isinstance(v.get("turn"), int)
                or not 0 <= v["turn"] < len(turns) or not isinstance(v.get("texts"), list) or not v["texts"]):
            _fail(path, "each variant needs a valid 'turn' index and a non-empty 'texts' list")
        if turns[v["turn"]]["user"]["kind"] != "utterance":
            _fail(path, f"variant for turn {v['turn']}: only utterance turns can have text variants")
    return Scenario(id=raw["id"], lang=raw["lang"], domain=raw["domain"], capability=raw["capability"],
                    title=raw["title"], turns=tuple(parsed), setup=raw.get("setup") or {},
                    variants=tuple(variants), tags=tuple(raw.get("tags") or ()), path=path)


def load_faq(path: str) -> list[FaqEntry]:
    raw = _load_yaml(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        _fail(path, "must be a mapping with 'lang' and an 'entries' list")
    if raw.get("lang") not in LANGS or set(raw) - {"lang", "entries"}:
        _fail(path, f"needs 'lang' (one of {LANGS}) and 'entries' only")
    if os.path.basename(os.path.dirname(os.path.abspath(path))) != raw["lang"]:
        _fail(path, "faq.yaml must sit in the directory named after its lang")
    out, seen = [], set()
    for e in raw["entries"]:
        extra = set(e) - {"id", "question", "answer", "paraphrases", "asr_variants"}
        if extra:
            _fail(path, f"entry {e.get('id')}: unknown keys {sorted(extra)}")
        for key in ("id", "question", "answer"):
            if not e.get(key):
                _fail(path, f"entry missing '{key}'")
        if e["id"] in seen:
            _fail(path, f"duplicate id {e['id']}")
        seen.add(e["id"])
        para, asr = e.get("paraphrases") or [], e.get("asr_variants") or []
        if len(para) < 3 or len(asr) < 1:
            _fail(path, f"entry {e['id']}: needs >=3 paraphrases and >=1 asr_variants")
        if not all(isinstance(x, str) and x for x in para + asr):
            _fail(path, f"entry {e['id']}: variants must be non-empty strings")
        out.append(FaqEntry(e["id"], e["question"], e["answer"], tuple(para), tuple(asr)))
    return out


def load_domain(domain_dir: str, lang: str = "en") -> tuple[list[FaqEntry], list[Scenario]]:
    base = os.path.join(domain_dir, lang)
    faq_path = os.path.join(base, "faq.yaml")
    faq = load_faq(faq_path) if os.path.exists(faq_path) else []
    scenarios = [load_scenario(p) for p in sorted(glob.glob(os.path.join(base, "scenarios", "*.yaml")))]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise DatasetError(f"{domain_dir}: duplicate scenario ids")
    return faq, scenarios


def coverage(domains_dir: str, lang: str = "en") -> dict:
    """{(domain, capability): count}. C00 counts FAQ entries, the others count scenarios."""
    counts = {(d, c): 0 for d in DOMAINS for c in CAPABILITIES}
    for d in DOMAINS:
        path = os.path.join(domains_dir, d)
        if not os.path.isdir(path):
            continue
        faq, scenarios = load_domain(path, lang)
        counts[(d, "C00")] = len(faq)
        for s in scenarios:
            counts[(d, s.capability)] += 1
    return counts


def format_coverage(counts: dict) -> str:
    lines = ["| Capability | " + " | ".join(DOMAINS) + " |", "|---|" + "---|" * len(DOMAINS)]
    for cap, name in CAPABILITIES.items():
        cells = [str(counts[(d, cap)]) if counts[(d, cap)] else "-" for d in DOMAINS]
        lines.append(f"| {cap} {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "coverage":
        root = sys.argv[2] if len(sys.argv) > 2 else "domains"
        lang = sys.argv[3] if len(sys.argv) > 3 else "en"
        print(format_coverage(coverage(root, lang)))
    else:
        print(__doc__)
