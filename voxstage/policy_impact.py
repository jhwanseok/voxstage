"""How far does one policy edit reach? (R14, decisions R14-1, R14-2 and R14-3)

The shop says its free-shipping threshold in three replies, each reading `{policy.<key> | formatter}` from the
request. The hard-coded counter-example is not kept in the repository: this tool copies `domains/` to a temporary
folder and writes the v1 value in place of every `{policy.<key>}` in the flows (the formatter applied), so the
variant cannot drift from the real flows. Both variants run the C12 scenarios under v1 and v2, and the report
gives, per variant, the C12 passes and the files and lines that a move to v2 must edit. For the threshold change
of R14-2 (default 50 to 100) it also counts the replies that still say the old value after the single edit the C12
case points to (the minimum-order reply).

  python -m voxstage.policy_impact [--old 50] [--new 100] [--lang en]
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sys
import tempfile
from typing import Optional

from . import dataset, evaluate
from .dialogue import step
from .rules.formatters import FORMATTERS
from .rules.interpreter import build_manager
from .tools import FakeApiExecutor
from .turn import Utterance

ENTRY_FLOW = "free_shipping"   # the reply the C12 case asks about
QUESTIONS = {
    "en": {"free_shipping": "What is the minimum order for free shipping",
           "free_shipping_offer": "Do you offer free shipping",
           "free_shipping_how": "How do I get free shipping"},
    "ko": {"free_shipping": "얼마 이상 사야 배송비 안 내요",
           "free_shipping_offer": "무료 배송 되나요",
           "free_shipping_how": "무료 배송 어떻게 받아요"},
}
FIELD = re.compile(r"\{policy\.(\w+)\s*(?:\|\s*(\w+)(?:\(([^)]*)\))?)?\s*\}")


def write_value(match, policy: dict, lang: str) -> str:
    """The text a `{policy.<key> | formatter(args)}` field speaks for this policy."""
    key, name, args = match.group(1), match.group(2), match.group(3)
    value = policy[key]
    if not name:
        return str(value)
    return FORMATTERS[name].fn(value, lang, *[a.strip().strip("'\"") for a in (args or "").split(",") if a.strip()])


def hardcode(domains_dir: str, dest: str, policy: dict) -> dict:
    """Copy `domains_dir` to `dest`, writing `policy` into the flow texts. Returns {file: lines changed}."""
    shutil.copytree(domains_dir, dest, dirs_exist_ok=True)
    changed = {}
    for path in glob.glob(os.path.join(dest, "*", "*", "flows", "*.yaml")):
        lang = path.split(os.sep)[-3]
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        n = 0
        for i, line in enumerate(lines):
            new = FIELD.sub(lambda m: write_value(m, policy, lang), line)
            if new != line:
                lines[i], n = new, n + 1
        if n:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines))
            changed[os.path.relpath(path, dest).replace(os.sep, "/")] = n
    return changed


def policy_cases(domains_dir: str, lang: str) -> list:
    return [c for c in evaluate.build_cases(domains_dir, lang) if c.capability == "C12" and c.kind == "scenario"
            and c.source == "base"]


def c12_passes(domains_dir: str, lang: str, version: str, policy_dir: Optional[str] = None) -> tuple:
    """(passed, total) of the C12 scenarios whose setup is `version` (v1 or v2); `domains_dir` holds the flows."""
    done = []
    for case in policy_cases(policy_dir or domains_dir, lang):
        if case.setup.get("policy", {}).get("version") == version:
            done.append(evaluate.run_case(lambda ctx: build_manager(domains_dir, ctx.domain, ctx.lang, ctx.tools), case, domains_dir, "clean")["passed"])
    return sum(done), len(done)


def replies(domains_dir: str, lang: str, threshold) -> dict:
    """What the shop says to each of the three questions when the request carries this threshold."""
    tools = FakeApiExecutor.from_yaml(os.path.join(domains_dir, "shop", "tools.yaml"))
    manager = build_manager(domains_dir, "shop", lang, tools)
    out = {}
    for flow, question in QUESTIONS[lang].items():
        state = manager.initial_state(f"impact.{flow}", {"policy": {"free_shipping_threshold": str(threshold)}})
        out[flow] = step(manager, state, Utterance(question, source="typed")).reply
    return out


def say(value, lang: str) -> str:
    return FORMATTERS["money"].fn(value, lang, "USD")


def measure(lang: str, old, new, domains_dir: str = evaluate.DEFAULT_DOMAINS_DIR) -> dict:
    """Both variants after the threshold changes from `old` to `new` and the C12 reply is edited."""
    v1 = {}
    for case in policy_cases(domains_dir, lang):   # the v1 values of every domain's policy
        if case.setup["policy"].get("version") == "v1":
            v1.update(case.setup["policy"])
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("referenced", "hardcoded"):
            pack = os.path.join(tmp, name)
            sites = {f: n for f, n in hardcode(domains_dir, pack, v1).items() if f"/{lang}/" in f} if name == "hardcoded" else {}
            if name == "referenced":
                shutil.copytree(domains_dir, pack)
            entry = os.path.join(pack, "shop", lang, "flows", ENTRY_FLOW + ".yaml")
            passes = {v: c12_passes(pack, lang, v, domains_dir) for v in ("v1", "v2")}
            if sites:   # the one edit the C12 case points to
                with open(entry, encoding="utf-8") as f:
                    text = f.read().replace(say(old, lang), say(new, lang))
                with open(entry, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            after = replies(pack, lang, new)
            result[name] = {"c12": passes, "edit_files": len(sites), "edit_lines": sum(sites.values()),
                            "sites": sorted(sites),
                            "stale": sorted(k for k, r in after.items() if say(old, lang) in r),
                            "current": sorted(k for k, r in after.items() if say(new, lang) in r)}
    return result


def to_markdown(lang: str, old, new, data: dict) -> str:
    lines = [f"# Policy impact ({lang}): C12 under v1 and v2, then the free-shipping threshold {old} to {new}", "",
             "| Variant | C12 under v1 | C12 under v2 | Flow files and lines a move to v2 must edit "
             f"| After the C12 reply is edited for {new}: replies still on {old} |", "|---|---|---|---|---|"]
    for name, d in data.items():
        edit = f"{d['edit_files']} files, {d['edit_lines']} lines" if d["edit_files"] else "0 (one policy value)"
        lines.append(f"| {name} | {d['c12']['v1'][0]} of {d['c12']['v1'][1]} | {d['c12']['v2'][0]} of {d['c12']['v2'][1]} "
                     f"| {edit} | {len(d['stale'])} of 3 ({', '.join(d['stale']) or '-'}) |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m voxstage.policy_impact")
    ap.add_argument("--old", default="50")
    ap.add_argument("--new", default="100")
    ap.add_argument("--lang", default="en", choices=sorted(QUESTIONS))
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    print(to_markdown(args.lang, args.old, args.new, measure(args.lang, args.old, args.new)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
