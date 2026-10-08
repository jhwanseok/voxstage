"""Scores a DialogueManager on the dataset (text mode). See docs/decisions/0008-evaluation-harness.md.

A manager is built per case by a factory `factory(ctx) -> DialogueManager`. `ctx.tools` is the recording
tool port the manager must use. `ctx.oracle` carries the expected values and is meant for `OracleDM` only;
a real manager's factory must not read it.

Checks per turn: flow, slots (expected is a subset of actual, compared after a canonical form),
reply_contains, reply_contains_any, reply_not_contains, tool_calls (exact, ordered), actions.
A case passes when every check of every turn passes.

CLI:
  python -m voxstage.evaluate run <null|oracle|module:callable> [--lang en|ko] [--mode clean|noisy] [--out DIR]
  python -m voxstage.evaluate compare a.json b.json
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import dataset
from .dialogue import DialogueManager, step
from .tools import FakeApiExecutor, ToolExecutor, ToolResult
from .turn import ButtonPress, Dtmf, Utterance

DEFAULT_DOMAINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "domains")

# --- canonical form for `slots` (ADR 0008) ------------------------------------------------------
# One place to change: symbols and words that may be attached to a number.
CURRENCY_SYMBOLS = "$€£¥₩"
CURRENCY_WORDS = ("dollars", "dollar", "usd", "달러", "불", "won", "krw", "원", "yen", "jpy", "엔")
_NUMBER = r"(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
_SLOT_NUMBER = re.compile(
    rf"^(?:[{re.escape(CURRENCY_SYMBOLS)}])?\s*{_NUMBER}\s*(?:{'|'.join(map(re.escape, CURRENCY_WORDS))})?$",
    re.IGNORECASE)


def canonical_slot(value: Any) -> str:
    """Exact string, except that a number with a currency symbol or word and thousands commas
    is reduced to its digits. Anything else is only stripped."""
    text = str(value).strip()
    m = _SLOT_NUMBER.match(text)
    if m:
        return m.group("num").replace(",", "") + (m.group("frac") or "")
    return text


# --- recording tool port ------------------------------------------------------------------------
class RecordingTools(ToolExecutor):
    """Wraps any ToolExecutor and records every call with its outcome."""

    name = "recording"

    def __init__(self, inner: ToolExecutor):
        self.inner = inner
        self.records: list[dict] = []

    def call(self, tool: str, args: dict) -> ToolResult:
        result = self.inner.call(tool, args)
        self.records.append({"name": tool, "args": dict(args), "error": result.error})
        return result


# --- cases ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Case:
    id: str
    kind: str          # "scenario" | "faq"
    domain: str
    lang: str
    capability: str
    turns: tuple       # of dataset.Turn
    setup: dict
    source: str = ""   # faq: question | paraphrase | asr_variant ; scenario variants: "variant"


@dataclass
class Context:
    domain: str
    lang: str
    tools: RecordingTools
    setup: dict
    oracle: Optional[Case] = None  # for OracleDM only


ManagerFactory = Callable[[Context], DialogueManager]


def _variant_cases(s: dataset.Scenario) -> list[Case]:
    out = []
    for v in s.variants:
        for n, text in enumerate(v["texts"], 1):
            turns = list(s.turns)
            user = {k: val for k, val in turns[v["turn"]].user.items() if k != "asr_text"}
            user["text"] = text
            turns[v["turn"]] = dataset.Turn(user=user, expect=turns[v["turn"]].expect)
            out.append(Case(f"{s.id}#v{v['turn']}.{n}", "scenario", s.domain, s.lang, s.capability,
                            tuple(turns), s.setup, "variant"))
    return out


def build_cases(domains_dir: str = DEFAULT_DOMAINS_DIR, lang: str = "en",
                domains: Optional[list] = None, include_unanswerable: bool = False) -> list[Case]:
    cases: list[Case] = []
    for d in domains or dataset.DOMAINS:
        path = os.path.join(domains_dir, d)
        if not os.path.isdir(path):
            continue
        faq, scenarios = dataset.load_domain(path, lang)
        for e in faq:
            queries = [("question", e.question)] + [("paraphrase", t) for t in e.paraphrases] \
                + [("asr_variant", t) for t in e.asr_variants]
            for n, (source, text) in enumerate(queries):
                turn = dataset.Turn(user={"kind": "utterance", "text": text},
                                    expect={"reply_contains": [e.answer]})
                cases.append(Case(f"{e.id}#{source}.{n}", "faq", d, lang, "C00", (turn,), {}, source))
        for s in scenarios:
            cases.append(Case(s.id, "scenario", s.domain, s.lang, s.capability, s.turns, s.setup, "base"))
            cases.extend(_variant_cases(s))
        un_path = os.path.join(path, lang, "faq_unanswerable.yaml")
        if include_unanswerable and os.path.exists(un_path):
            # Out-of-scope questions: the reply must not be any FAQ answer (a false accept otherwise).
            answers = [e.answer for e in faq]
            for n, text in enumerate(dataset.load_unanswerable(un_path)):
                turn = dataset.Turn(user={"kind": "utterance", "text": text},
                                    expect={"reply_not_contains": answers})
                cases.append(Case(f"{d}.unanswerable.{n}", "unanswerable", d, lang, "C00", (turn,), {},
                                  "unanswerable_draft"))
    return cases


# --- running ---------------------------------------------------------------------------------------
def _to_input(user: dict, mode: str):
    match user["kind"]:
        case "utterance":
            if mode == "noisy" and user.get("asr_text"):
                return Utterance(user["asr_text"], source="asr")
            return Utterance(user["text"], source="typed" if mode == "clean" else "asr")
        case "dtmf":
            return Dtmf(str(user["digits"]))
        case "button":
            return ButtonPress(user["button_id"], user.get("value"))
    raise ValueError(f"unknown input kind {user['kind']!r}")


def _check_turn(expect: dict, reply: str, state, calls: list[dict], actions: list[str]) -> list[dict]:
    fails = []

    def fail(check, expected, actual):
        fails.append({"check": check, "expected": expected, "actual": actual})

    if "flow" in expect and state.flow_id != expect["flow"]:
        fail("flow", expect["flow"], state.flow_id)
    for key, want in (expect.get("slots") or {}).items():
        have = state.slots.get(key)
        if have is None or canonical_slot(have) != canonical_slot(want):
            fail(f"slots.{key}", want, have)
    for phrase in expect.get("reply_contains") or []:
        if phrase not in reply:
            fail("reply_contains", phrase, reply)
    any_of = expect.get("reply_contains_any")
    if any_of and not any(p in reply for p in any_of):
        fail("reply_contains_any", any_of, reply)
    for phrase in expect.get("reply_not_contains") or []:
        if phrase in reply:
            fail("reply_not_contains", phrase, reply)
    if "tool_calls" in expect:
        want = [{"name": c["name"], "args": {k: str(v) for k, v in c["args"].items()}, "error": c.get("error")}
                for c in expect["tool_calls"]]
        have = [{"name": c["name"], "args": {k: str(v) for k, v in c["args"].items()}, "error": c["error"]}
                for c in calls]
        if want != have:
            fail("tool_calls", want, have)
    if "actions" in expect and list(expect["actions"]) != actions:
        fail("actions", list(expect["actions"]), actions)
    return fails


def run_case(factory: ManagerFactory, case: Case, domains_dir: str, mode: str = "clean") -> dict:
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(domains_dir, case.domain, "tools.yaml")))
    ctx = Context(case.domain, case.lang, tools, copy.deepcopy(case.setup), oracle=case)
    manager = factory(ctx)
    state = manager.initial_state(case.id, copy.deepcopy(case.setup))
    failures = []
    for index, turn in enumerate(case.turns):
        before = len(tools.records)
        result = step(manager, state, _to_input(turn.user, mode))
        state = result.state
        actions = [type(a).__name__ for a in result.actions]
        for f in _check_turn(turn.expect, result.reply, result.state, tools.records[before:], actions):
            failures.append({"turn": index, **f})
    return {"id": case.id, "kind": case.kind, "domain": case.domain, "lang": case.lang,
            "capability": case.capability, "source": case.source, "passed": not failures,
            "failures": failures}


def evaluate(factory: ManagerFactory, *, domains_dir: str = DEFAULT_DOMAINS_DIR, lang: str = "en",
             mode: str = "clean", domains: Optional[list] = None, manager_name: str = "",
             include_unanswerable: bool = False) -> dict:
    results = [run_case(factory, c, domains_dir, mode)
               for c in build_cases(domains_dir, lang, domains, include_unanswerable)]
    return {"manager": manager_name, "lang": lang, "mode": mode, "summary": summarize(results),
            "results": results}


def _rate(rows: list) -> dict:
    n = len(rows)
    ok = sum(r["passed"] for r in rows)
    return {"passed": ok, "total": n, "rate": round(100 * ok / n, 1) if n else None}


def summarize(results: list) -> dict:
    def group(key, rows=results):
        keys = sorted({r[key] for r in rows})
        return {k: _rate([r for r in rows if r[key] == k]) for k in keys}

    unanswerable = [r for r in results if r["kind"] == "unanswerable"]
    results = [r for r in results if r["kind"] != "unanswerable"]
    faq = [r for r in results if r["kind"] == "faq"]
    out = {"overall": _rate(results), "by_capability": group("capability", results),
           "by_domain": group("domain", results), "by_lang": group("lang", results),
           "faq_by_source": group("source", faq) if faq else {}}
    if unanswerable:  # the file is a draft until the owner approves it; reported apart from the pass rate
        wrong = sum(not r["passed"] for r in unanswerable)
        out["false_accept"] = {"false_accepts": wrong, "total": len(unanswerable),
                               "rate": round(100 * wrong / len(unanswerable), 1), "status": "draft, not reviewed"}
    return out


# --- reports -----------------------------------------------------------------------------------------
def to_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [f"# Evaluation: {report['manager'] or 'manager'} ({report['lang']}, {report['mode']})", "",
             f"Overall: {s['overall']['passed']}/{s['overall']['total']} ({s['overall']['rate']}%)", "",
             "| Capability | Passed | Total | Rate % |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['passed']} | {v['total']} | {v['rate']} |" for k, v in s["by_capability"].items()]
    lines += ["", "| Domain | Passed | Total | Rate % |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['passed']} | {v['total']} | {v['rate']} |" for k, v in s["by_domain"].items()]
    if "false_accept" in s:
        fa = s["false_accept"]
        lines += ["", f"False accepts on the unanswerable list ({fa['status']}): "
                      f"{fa['false_accepts']}/{fa['total']} ({fa['rate']}%)"]
    if s["faq_by_source"]:
        lines += ["", "| FAQ query source | Passed | Total | Rate % |", "|---|---|---|---|"]
        lines += [f"| {k} | {v['passed']} | {v['total']} | {v['rate']} |" for k, v in s["faq_by_source"].items()]
    failing = [r for r in report["results"] if not r["passed"]]
    lines += ["", f"## Failing cases ({len(failing)})", ""]
    for r in failing[:200]:
        for f in r["failures"][:3]:
            lines.append(f"- `{r['id']}` turn {f['turn']} {f['check']}: expected {f['expected']!r}, got {f['actual']!r}")
    if len(failing) > 200:
        lines.append(f"- ... {len(failing) - 200} more in the JSON report")
    return "\n".join(lines) + "\n"


def write_report(report: dict, out_dir: str) -> tuple:
    os.makedirs(out_dir, exist_ok=True)
    stem = f"{report['manager'] or 'manager'}-{report['lang']}-{report['mode']}"
    jpath, mpath = os.path.join(out_dir, stem + ".json"), os.path.join(out_dir, stem + ".md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(to_markdown(report))
    return jpath, mpath


def compare(a: dict, b: dict) -> dict:
    """Case ids that pass in `a` and fail in `b` (regressions) and the other way round (fixes)."""
    pa = {r["id"]: r["passed"] for r in a["results"]}
    pb = {r["id"]: r["passed"] for r in b["results"]}
    common = sorted(set(pa) & set(pb))
    return {"regressions": [i for i in common if pa[i] and not pb[i]],
            "fixes": [i for i in common if not pa[i] and pb[i]],
            "only_in_a": sorted(set(pa) - set(pb)), "only_in_b": sorted(set(pb) - set(pa))}


# --- CLI ---------------------------------------------------------------------------------------------
def load_factory(name: str) -> ManagerFactory:
    from . import reference_managers
    if name == "null":
        return reference_managers.null_factory
    if name == "oracle":
        return reference_managers.oracle_factory
    module, _, attr = name.partition(":")
    if not attr:
        raise SystemExit("manager must be null, oracle, or module:callable")
    return getattr(importlib.import_module(module), attr)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m voxstage.evaluate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("manager")
    r.add_argument("--lang", default="en", choices=dataset.LANGS)
    r.add_argument("--mode", default="clean", choices=("clean", "noisy"))
    r.add_argument("--domains-dir", default=DEFAULT_DOMAINS_DIR)
    r.add_argument("--out", default=None)
    r.add_argument("--unanswerable", action="store_true", help="also run the draft out-of-scope questions")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        report = evaluate(load_factory(args.manager), domains_dir=args.domains_dir, lang=args.lang,
                          mode=args.mode, manager_name=args.manager.split(":")[-1],
                          include_unanswerable=args.unanswerable)
        if args.out:
            print(*write_report(report, args.out), sep="\n")
        else:
            print(to_markdown(report))
        return 0
    with open(args.a, encoding="utf-8") as fa, open(args.b, encoding="utf-8") as fb:
        diff = compare(json.load(fa), json.load(fb))
    print(json.dumps(diff, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
