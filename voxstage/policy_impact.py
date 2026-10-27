"""How far does one policy edit reach? (R14, decisions R14-1, R14-2 and R14-3)

The shop says its free-shipping threshold in three replies, each reading `{policy.<key> | formatter}` from the
request. The hard-coded counter-example is kept as files (R14-1): `domains_variants/hardcoded/shop/<lang>/flows/`
holds the same three flows with the v1 value written into the text, laid over a copy of `domains/`. Both variants
run the C12 scenarios under v1 and v2, and the report gives, per variant, the C12 passes and the flow files and
lines a move to v2 must edit. For the threshold change of R14-2 (default 50 to 100) it also counts the replies that
still say the old value after the single edit the C12 case points to (the minimum-order reply).

  python -m voxstage.policy_impact [--old 50] [--new 100] [--lang en]
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import tempfile
from typing import Optional

from . import evaluate
from .dialogue import step
from .rules.formatters import FORMATTERS
from .rules.interpreter import build_manager
from .tools import FakeApiExecutor
from .turn import Utterance

VARIANT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "domains_variants", "hardcoded")
ENTRY_FLOW = "free_shipping"   # the reply the C12 case asks about

QUESTIONS = {
    "en": {"free_shipping": "What is the minimum order for free shipping",
           "free_shipping_offer": "Do you offer free shipping",
           "free_shipping_how": "How do I get free shipping"},
    "ko": {"free_shipping": "얼마 이상 사야 배송비 안 내요",
           "free_shipping_offer": "무료 배송 되나요",
           "free_shipping_how": "무료 배송 어떻게 받아요"},
}


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


def literal_lines(pack: str, lang: str, value) -> dict:
    """{flow file: lines} of the shop flows in `pack` that write the value into a text."""
    literal, found = say(value, lang), {}
    for path in glob.glob(os.path.join(pack, "shop", lang, "flows", "*.yaml")):
        with open(path, encoding="utf-8") as f:
            n = sum(1 for line in f if literal in line)
        if n:
            found[os.path.basename(path)] = n
    return found


def measure(lang: str, old, new, domains_dir: str = evaluate.DEFAULT_DOMAINS_DIR,
            variant_dir: str = VARIANT_DIR) -> dict:
    """Both variants after the threshold changes from `old` to `new` and the C12 reply is edited."""
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, vdir in (("referenced", None), ("hardcoded", variant_dir)):
            pack = os.path.join(tmp, name)
            shutil.copytree(domains_dir, pack)
            if vdir:
                shutil.copytree(vdir, pack, dirs_exist_ok=True)
            sites = literal_lines(pack, lang, old)
            passes = {v: c12_passes(pack, lang, v, domains_dir) for v in ("v1", "v2")}
            if sites:   # the one edit the C12 case points to
                entry = os.path.join(pack, "shop", lang, "flows", ENTRY_FLOW + ".yaml")
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
