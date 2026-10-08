"""Everything one domain and one language bring to a rule manager.

The pack exposes only what a manager may use at run time: FAQ answers, rule patterns, the fallback policy.
It does not expose paraphrases or recognition-error variants (ADR 0009: held out). Flows, notices and
policy are added by later steps and are `None` until then.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

from . import dataset


class RuleError(ValueError):
    """A rule file is malformed. Raised at load time, naming the file."""


@dataclass(frozen=True)
class Pattern:
    id: str
    all_of: tuple       # of groups; a group is a tuple of synonyms, any of which satisfies it
    any_of: tuple       # words; if non-empty at least one must occur
    none_of: tuple      # words; none may occur
    priority: int = 0
    regex: tuple = ()   # alternative path for rules a word group cannot express (logged in the ledger)


@dataclass(frozen=True)
class Fallback:
    reply: str
    exceed_reply: str
    max_misses: int = 3
    on_exceed: str = "handoff"   # handoff | end_call


@dataclass(frozen=True)
class DomainPack:
    domain: str
    lang: str
    answers: dict                      # faq id -> verbatim answer
    patterns: tuple = ()
    fallback: Optional[Fallback] = None
    tools_path: str = ""
    base_dir: str = ""
    flows: Optional[dict] = field(default=None)

    @classmethod
    def load(cls, domains_dir: str, domain: str, lang: str) -> "DomainPack":
        base = os.path.join(domains_dir, domain, lang)
        faq, _ = dataset.load_domain(os.path.join(domains_dir, domain), lang)
        answers = {e.id: e.answer for e in faq}
        rules_dir = os.path.join(base, "rules")
        pat_path = os.path.join(rules_dir, "faq_patterns.yaml")
        cfg_path = os.path.join(rules_dir, "config.yaml")
        patterns = load_patterns(pat_path, set(answers)) if os.path.exists(pat_path) else ()
        fallback = load_fallback(cfg_path) if os.path.exists(cfg_path) else None
        return cls(domain, lang, answers, patterns, fallback,
                   os.path.join(domains_dir, domain, "tools.yaml"), base)


def _read(path: str):
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise RuleError(f"{path}: invalid YAML ({exc})") from exc


def _words(path: str, where: str, value) -> tuple:
    if not isinstance(value, list) or not all(isinstance(w, str) and w.strip() for w in value):
        raise RuleError(f"{path}: {where} must be a list of non-empty words")
    return tuple(value)


def load_patterns(path: str, faq_ids: set) -> tuple:
    raw = _read(path)
    if not isinstance(raw, dict) or set(raw) != {"entries"} or not isinstance(raw["entries"], list):
        raise RuleError(f"{path}: must be a mapping with an 'entries' list")
    out, seen = [], set()
    for e in raw["entries"]:
        if not isinstance(e, dict) or "id" not in e:
            raise RuleError(f"{path}: every entry needs an id")
        extra = set(e) - {"id", "all_of", "any_of", "none_of", "priority", "regex", "note"}
        if extra:
            raise RuleError(f"{path}: {e['id']}: unknown keys {sorted(extra)}")
        if e["id"] not in faq_ids:
            raise RuleError(f"{path}: {e['id']} is not a FAQ id")
        if e["id"] in seen:
            raise RuleError(f"{path}: duplicate {e['id']}")
        seen.add(e["id"])
        groups = []
        for g in e.get("all_of") or []:
            groups.append(tuple(_words(path, f"{e['id']}.all_of group", g)) if isinstance(g, list)
                          else (_words(path, f"{e['id']}.all_of", [g])[0],))
        any_of = _words(path, f"{e['id']}.any_of", e.get("any_of") or [])
        regex = _words(path, f"{e['id']}.regex", e.get("regex") or [])
        if not groups and not any_of and not regex:
            raise RuleError(f"{path}: {e['id']} needs all_of, any_of or regex")
        prio = e.get("priority", 0)
        if not isinstance(prio, int) or isinstance(prio, bool):
            raise RuleError(f"{path}: {e['id']}: priority must be an integer")
        out.append(Pattern(e["id"], tuple(groups), any_of, _words(path, f"{e['id']}.none_of", e.get("none_of") or []),
                           prio, regex))
    missing = faq_ids - seen
    if missing:
        raise RuleError(f"{path}: no pattern for FAQ entries {sorted(missing)}")
    return tuple(out)


def load_fallback(path: str) -> Fallback:
    raw = _read(path)
    fb = raw.get("fallback") if isinstance(raw, dict) else None
    if not isinstance(fb, dict) or set(raw) != {"fallback"}:
        raise RuleError(f"{path}: needs a top-level 'fallback' mapping only")
    extra = set(fb) - {"reply", "exceed_reply", "max_misses", "on_exceed"}
    if extra:
        raise RuleError(f"{path}: unknown fallback keys {sorted(extra)}")
    for key in ("reply", "exceed_reply"):
        if not isinstance(fb.get(key), str) or not fb[key].strip():
            raise RuleError(f"{path}: fallback.{key} must be a non-empty string")
    n = fb.get("max_misses", 3)
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise RuleError(f"{path}: fallback.max_misses must be an integer >= 1")
    action = fb.get("on_exceed", "handoff")
    if action not in ("handoff", "end_call"):
        raise RuleError(f"{path}: fallback.on_exceed must be handoff or end_call")
    return Fallback(fb["reply"], fb["exceed_reply"], n, action)
