"""The complexity curve of S1 (R15): what the rules cost, step by step, against what they pass.

Cost comes from the effort ledger (`docs/ledger/effort.md`), pass rates from running the evaluation harness on the
commit each ledger row names. Pass rates are the step's own dataset in clean mode (the dataset grew with the steps,
so a rate is "how much of what was asked at that time"; a step is measured at the commit where its work ended, see `measure`). A rate is measured once and kept in
`docs/ledger/pass-rates.json`; the report is built from the two files.

  python -m voxstage.complexity measure [--steps R1 R2 ...]   # runs the harness on each ledger commit (slow)
  python -m voxstage.complexity report                         # writes docs/ledger/complexity.md and .png
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Optional

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LEDGER = os.path.join(ROOT, "docs", "ledger", "effort.md")
RATES = os.path.join(ROOT, "docs", "ledger", "pass-rates.json")
REPORT = os.path.join(ROOT, "docs", "ledger", "complexity.md")
FIGURE = os.path.join(ROOT, "docs", "ledger", "complexity.png")
FACTORIES = ("voxstage.rules.interpreter:default_factory", "voxstage.rules.faq:default_factory")
LANGS = ("en", "ko")


def _num(cell: str) -> int:
    cell = cell.strip()
    return int(cell) if cell.isdigit() else 0


def read_ledger(path: str = LEDGER) -> list:
    """The last row of each (step, domain, lang), as dicts, in file order."""
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 12 or not cells[0].startswith("R") or not cells[0][1:2].isdigit():
                continue
            rows[(cells[0], cells[2], cells[3])] = {
                "step": cells[0], "commit": cells[1], "domain": cells[2], "lang": cells[3],
                "flow_lines": _num(cells[4]), "flow_nodes": _num(cells[5]), "patterns": _num(cells[6]),
                "regex": _num(cells[7]), "interpreter": _num(cells[8]), "other_code": _num(cells[9]),
                "rule_entries": _num(cells[10]), "normalize": _num(cells[11])}
    return list(rows.values())


def steps(rows: list) -> list:
    seen = []
    for r in rows:
        if r["step"] not in seen:
            seen.append(r["step"])
    return seen


def totals(rows: list, step: str, lang: str) -> dict:
    """One language's cost at a step: rules (nodes, patterns, regexes, rule-file entries) and lines of code."""
    mine = [r for r in rows if r["step"] == step and r["lang"] == lang]
    shared = mine[0]   # the code is the same for every domain
    rules = sum(r["flow_nodes"] + r["patterns"] + r["regex"] + r["rule_entries"] for r in mine)
    return {"commit": shared["commit"], "nodes": sum(r["flow_nodes"] for r in mine), "rules": rules,
            "flow_lines": sum(r["flow_lines"] for r in mine),
            "code_lines": shared["interpreter"] + shared["other_code"] + shared["normalize"]}


def _run(args: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", **kw)


def overall(report_json: str) -> list:
    with open(report_json, encoding="utf-8") as f:
        results = json.load(f)["results"]
    return [sum(1 for r in results if r["passed"]), len(results)]


def measure(only: Optional[list] = None) -> dict:
    rows = read_ledger()
    rates = json.load(open(RATES, encoding="utf-8")) if os.path.exists(RATES) else {}
    order = steps(rows)
    for i, step in enumerate(order):
        if only and step not in only:
            continue
        # A ledger row names HEAD while the step's work was still uncommitted, so the step ends at the commit the
        # next row names (the last step ends at its own).
        commit = totals(rows, order[min(i + 1, len(order) - 1)], "en")["commit"]
        entry = rates.setdefault(step, {})
        entry["commit"] = commit
        with tempfile.TemporaryDirectory() as tmp:
            tree = os.path.join(tmp, "tree")
            _run(["git", "worktree", "add", "--detach", tree, commit], cwd=ROOT)
            try:
                for lang in LANGS:
                    out = os.path.join(tmp, "out")
                    for factory in FACTORIES + ("null",):
                        done = _run([sys.executable, "-m", "voxstage.evaluate", "run", factory, "--lang", lang,
                                     "--mode", "clean", "--out", out], cwd=tree)
                        if done.returncode == 0:
                            break
                    name = factory.split(":")[-1]
                    report = os.path.join(out, f"{name}-{lang}-clean.json")
                    if done.returncode != 0 or not os.path.exists(report):
                        print(step, commit, lang, "no harness at this commit", flush=True)
                        continue
                    entry[lang] = overall(report)
                    entry["manager"] = factory
                    print(step, commit, lang, entry[lang], flush=True)
            finally:
                _run(["git", "worktree", "remove", "--force", tree], cwd=ROOT)
        with open(RATES, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rates, f, indent=1, ensure_ascii=False)
    return rates


def to_markdown(rows: list, rates: dict) -> str:
    lines = ["# S1 complexity curve", "",
             "Cumulative cost from the effort ledger against the clean-mode pass rate of that step's own dataset "
             "(`voxstage/complexity.py`). Rules = flow nodes + FAQ patterns + regexes + rule-file entries; code lines = "
             "interpreter + other rule code + normalize (shared by both languages).", "",
             "| Step | Lang | Flow nodes | Rules | Flow YAML lines | Code lines | Passed | Cases | Pass rate % |",
             "|---|---|---|---|---|---|---|---|---|"]
    for step in steps(rows):
        for lang in LANGS:
            t = totals(rows, step, lang)
            p, n = (rates.get(step, {}).get(lang) or [None, None])
            rate = f"{100 * p / n:.1f}" if n else "-"
            lines.append(f"| {step} | {lang} | {t['nodes']} | {t['rules']} | {t['flow_lines']} | {t['code_lines']} "
                         f"| {p if n else '-'} | {n or '-'} | {rate} |")
    return "\n".join(lines) + "\n"


def draw(rows: list, rates: dict, path: str = FIGURE) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, lang in zip(axes, LANGS):
        xs, ys, names = [], [], []
        for step in steps(rows):
            p, n = (rates.get(step, {}).get(lang) or [None, None])
            if n:
                t = totals(rows, step, lang)
                xs.append(t["rules"] + t["flow_lines"] + t["code_lines"])
                ys.append(100 * p / n)
                names.append(step)
        ax.plot(xs, ys, marker="o")
        for x, y, s in zip(xs, ys, names):
            ax.annotate(s, (x, y), textcoords="offset points", xytext=(3, 4), fontsize=7)
        ax.set_title(lang)
        ax.set_xlabel("rules + flow lines + code lines (cumulative)")
        ax.grid(alpha=.3)
    axes[0].set_ylabel("clean pass rate of that step's dataset, %")
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m voxstage.complexity")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--steps", nargs="*")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    if args.cmd == "measure":
        measure(args.steps)
        return 0
    rows = read_ledger()
    rates = json.load(open(RATES, encoding="utf-8")) if os.path.exists(RATES) else {}
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_markdown(rows, rates))
    draw(rows, rates)
    print(REPORT, FIGURE, sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
