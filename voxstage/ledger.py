"""Effort ledger: how much a rule base costs, counted the same for every rule (ADR 0008).

`python -m voxstage.ledger <step>` measures the tree and appends one row per domain and language to
docs/ledger/effort.md, together with the commit it was measured at.

Counted per domain and language: YAML lines and nodes in `flows/`, patterns and regular-expression patterns in
`rules/faq_patterns.yaml`. Counted once for the repo: interpreter lines (interpreter.py, flows.py, expr.py under
voxstage/rules/) and other rule-code lines. Blank lines and comment-only lines are not counted.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from typing import Optional

import yaml

from . import dataset

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INTERPRETER_FILES = ("interpreter.py", "flows.py", "expr.py")
HEADER = ("| Step | Commit | Domain | Lang | Flow YAML lines | Flow nodes | Patterns | Regex patterns "
          "| Interpreter lines | Other rule-code lines |")
RULE = "|---|---|---|---|---|---|---|---|---|---|"


def code_lines(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for ln in f if ln.strip() and not ln.strip().startswith("#"))


def _yaml(path: str):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def measure(root: str = ROOT) -> dict:
    """{'code': {...}, 'packs': [{domain, lang, ...}]} for the tree under `root`."""
    rules_dir = os.path.join(root, "voxstage", "rules")
    interp = other = 0
    for path in sorted(glob.glob(os.path.join(rules_dir, "*.py"))):
        name = os.path.basename(path)
        if name == "__init__.py":
            continue
        if name in INTERPRETER_FILES:
            interp += code_lines(path)
        else:
            other += code_lines(path)
    packs = []
    for d in dataset.DOMAINS:
        for lang in dataset.LANGS:
            base = os.path.join(root, "domains", d, lang)
            if not os.path.isdir(base):
                continue
            flow_files = glob.glob(os.path.join(base, "flows", "*.yaml"))
            lines = nodes = 0
            for p in flow_files:
                with open(p, encoding="utf-8") as f:
                    lines += sum(1 for ln in f if ln.strip() and not ln.strip().startswith("#"))
                nodes += len((_yaml(p) or {}).get("nodes") or {})
            patterns = regex = 0
            pp = os.path.join(base, "rules", "faq_patterns.yaml")
            if os.path.exists(pp):
                data = _yaml(pp) or {}
                entries = data.get("entries", data) if isinstance(data, dict) else data
                entries = entries if isinstance(entries, list) else []
                patterns = len(entries)
                regex = sum(1 for e in entries if isinstance(e, dict) and "regex" in e)
            packs.append({"domain": d, "lang": lang, "flow_lines": lines, "flow_nodes": nodes,
                          "patterns": patterns, "regex": regex})
    return {"code": {"interpreter_lines": interp, "other_rule_lines": other}, "packs": packs}


def commit_hash(root: str = ROOT) -> str:
    try:
        return subprocess.check_output(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def append_rows(path: str, step: str, measurement: dict, commit: str) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fresh = not os.path.exists(path)
    code = measurement["code"]
    rows = [f"| {step} | {commit} | {p['domain']} | {p['lang']} | {p['flow_lines']} | {p['flow_nodes']} "
            f"| {p['patterns']} | {p['regex']} | {code['interpreter_lines']} | {code['other_rule_lines']} |"
            for p in measurement["packs"]]
    with open(path, "a", encoding="utf-8") as f:
        if fresh:
            f.write("# Effort ledger\n\nOne row per domain and language each time a step is measured. "
                    "Every rule counts the same, whenever it was written (ADR 0008).\n\n"
                    + HEADER + "\n" + RULE + "\n")
        f.write("\n".join(rows) + "\n")
    return len(rows)


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m voxstage.ledger <step> [--out FILE]")
        return 2
    step = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, "docs", "ledger", "effort.md")
    n = append_rows(out, step, measure(), commit_hash())
    print(f"appended {n} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
