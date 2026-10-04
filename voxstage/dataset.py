"""Loader and validator for domain datasets (FAQ entries and capability scenarios).

A dataset is data only: `domains/<domain>/faq.yaml`, `tools.yaml`, `scenarios/*.yaml`.
Validation is strict on purpose: a typo in a scenario should fail at load time, not turn into
a silently wrong experiment. Format reference: docs/dataset-spec.md.

CLI: python -m voxstage.dataset coverage [domains_dir]   # capability x domain matrix
"""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass
from typing import Optional

import yaml

DOMAINS = ("bank", "shop", "telecom")

CAPABILITIES = {
    "C00": "FAQ 응답 (기준선)",
    "C01": "시나리오 전환",
    "C02": "곁가지 후 복귀",
    "C03": "취소·뒤로가기·상담사 연결",
    "C04": "버튼·DTMF 입력",
    "C05": "슬롯 오기입 재채움",
    "C06": "다중 슬롯·생략·지시어",
    "C07": "숫자·날짜·시간 정규화",
    "C08": "속성과 API 결과로 답변 생성",
    "C09": "조건별 고정 답변",
    "C10": "외부 API 실패·지연 폴백",
    "C11": "본인확인 전 정보 제공 차단",
    "C12": "정책 변경 영향 범위",
}

INPUT_KINDS = {
    "utterance": {"required": {"text"}, "optional": {"asr_text"}},
    "dtmf": {"required": {"digits"}, "optional": set()},
    "button": {"required": {"button_id"}, "optional": {"value"}},
}

EXPECT_KEYS = {"flow", "slots", "reply_contains", "reply_contains_any", "reply_not_contains",
               "tool_calls", "actions"}
SCENARIO_KEYS = {"id", "domain", "capability", "title", "setup", "turns", "variants", "tags"}


@dataclass(frozen=True)
class Turn:
    user: dict
    expect: dict


@dataclass(frozen=True)
class Scenario:
    id: str
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


def load_scenario(path: str) -> Scenario:
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        _fail(path, "must be a mapping")
    extra = set(raw) - SCENARIO_KEYS
    if extra:
        _fail(path, f"unknown keys {sorted(extra)}")
    for key in ("id", "domain", "capability", "title", "turns"):
        if key not in raw:
            _fail(path, f"missing '{key}'")
    if raw["domain"] not in DOMAINS:
        _fail(path, f"domain must be one of {DOMAINS}")
    if raw["capability"] not in CAPABILITIES:
        _fail(path, f"capability must be one of {sorted(CAPABILITIES)}")
    if not str(raw["id"]).startswith(f"{raw['domain']}.{raw['capability']}."):
        _fail(path, f"id must start with '{raw['domain']}.{raw['capability']}.'")
    if os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path)))) != raw["domain"]:
        _fail(path, "file is not under domains/<domain>/scenarios/ matching its domain")
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
        parsed.append(Turn(user=t["user"], expect=expect))
    variants = raw.get("variants") or []
    for v in variants:
        if (not isinstance(v, dict) or not isinstance(v.get("turn"), int)
                or not 0 <= v["turn"] < len(turns) or not isinstance(v.get("texts"), list) or not v["texts"]):
            _fail(path, "each variant needs a valid 'turn' index and a non-empty 'texts' list")
        if turns[v["turn"]]["user"]["kind"] != "utterance":
            _fail(path, f"variant for turn {v['turn']}: only utterance turns can have text variants")
    return Scenario(id=raw["id"], domain=raw["domain"], capability=raw["capability"],
                    title=raw["title"], turns=tuple(parsed), setup=raw.get("setup") or {},
                    variants=tuple(variants), tags=tuple(raw.get("tags") or ()), path=path)


def load_faq(path: str) -> list[FaqEntry]:
    raw = _load_yaml(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        _fail(path, "must be a mapping with an 'entries' list")
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


def load_domain(domain_dir: str) -> tuple[list[FaqEntry], list[Scenario]]:
    faq_path = os.path.join(domain_dir, "faq.yaml")
    faq = load_faq(faq_path) if os.path.exists(faq_path) else []
    scenarios = [load_scenario(p) for p in sorted(glob.glob(os.path.join(domain_dir, "scenarios", "*.yaml")))]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise DatasetError(f"{domain_dir}: duplicate scenario ids")
    return faq, scenarios


def coverage(domains_dir: str) -> dict:
    """{(domain, capability): count}. C00 counts FAQ entries, the others count scenarios."""
    counts = {(d, c): 0 for d in DOMAINS for c in CAPABILITIES}
    for d in DOMAINS:
        path = os.path.join(domains_dir, d)
        if not os.path.isdir(path):
            continue
        faq, scenarios = load_domain(path)
        counts[(d, "C00")] = len(faq)
        for s in scenarios:
            counts[(d, s.capability)] += 1
    return counts


def format_coverage(counts: dict) -> str:
    lines = ["| 기능 | " + " | ".join(DOMAINS) + " |", "|---|" + "---|" * len(DOMAINS)]
    for cap, name in CAPABILITIES.items():
        cells = [str(counts[(d, cap)]) if counts[(d, cap)] else "-" for d in DOMAINS]
        lines.append(f"| {cap} {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "coverage":
        root = sys.argv[2] if len(sys.argv) > 2 else "domains"
        print(format_coverage(coverage(root)))
    else:
        print(__doc__)
