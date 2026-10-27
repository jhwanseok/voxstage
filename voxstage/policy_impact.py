"""How far does one policy edit reach? (R14, decisions R14-1 and R14-2)

The shop says its free-shipping threshold in three replies. In `domains/` each reads `policy.free_shipping_threshold`
from the request; in `domains_variants/hardcoded/` (an overlay) the same three replies have the old value written
into the text. For a change of the threshold this reports the places to edit and how many replies still say the old
value after the one edit the C12 case points to (the minimum-order reply).

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
from .rules.formatters import money
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


def say(value, lang: str) -> str:
    return money(value, lang, "USD")


def overlay(domains_dir: str, variant_dir: Optional[str], dest: str) -> str:
    """A copy of `domains_dir` in `dest`, with the files of `variant_dir` laid over it."""
    shutil.copytree(domains_dir, dest, dirs_exist_ok=True)
    if variant_dir:
        shutil.copytree(variant_dir, dest, dirs_exist_ok=True)
    return dest


def replies(domains_dir: str, lang: str, threshold) -> dict:
    """What the shop says to each of the three questions when the request carries this threshold."""
    tools = FakeApiExecutor.from_yaml(os.path.join(domains_dir, "shop", "tools.yaml"))
    manager = build_manager(domains_dir, "shop", lang, tools)
    out = {}
    for flow, question in QUESTIONS[lang].items():
        state = manager.initial_state(f"impact.{flow}", {"policy": {"free_shipping_threshold": str(threshold)}})
        out[flow] = step(manager, state, Utterance(question, source="typed")).reply
    return out


def literal_sites(domains_dir: str, lang: str, value) -> list:
    """Flow files of the shop pack that write the value into a text."""
    literal = say(value, lang)
    found = []
    for p in glob.glob(os.path.join(domains_dir, "shop", lang, "flows", "*.yaml")):
        with open(p, encoding="utf-8") as f:
            if literal in f.read():
                found.append(os.path.basename(p))
    return sorted(found)


def measure(lang: str, old, new, domains_dir: str = evaluate.DEFAULT_DOMAINS_DIR,
            variant_dir: str = VARIANT_DIR) -> dict:
    """Both packs after the threshold changes from `old` to `new` and the C12 reply is edited."""
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, vdir in (("referenced", None), ("hardcoded", variant_dir)):
            pack = overlay(domains_dir, vdir, os.path.join(tmp, name))
            sites = literal_sites(pack, lang, old)
            entry = os.path.join(pack, "shop", lang, "flows", ENTRY_FLOW + ".yaml")
            if ENTRY_FLOW + ".yaml" in sites:   # the one edit the C12 case points to
                with open(entry, encoding="utf-8") as f:
                    text = f.read().replace(say(old, lang), say(new, lang))
                with open(entry, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            after = replies(pack, lang, new)
            stale = sorted(k for k, r in after.items() if say(old, lang) in r)
            current = sorted(k for k, r in after.items() if say(new, lang) in r)
            result[name] = {"literal_sites": sites, "stale": stale, "current": current, "replies": after}
    return result


def to_markdown(lang: str, old, new, data: dict) -> str:
    lines = [f"# Policy impact: free-shipping threshold {old} to {new} ({lang})", "",
             "| Variant | Places that write the value | Edited | Replies still on the old value | Replies on the new value |",
             "|---|---|---|---|---|"]
    for name, d in data.items():
        places = ", ".join(d["literal_sites"]) or "none (the value is in the request's policy)"
        edited = "1 flow file (the C12 reply)" if d["literal_sites"] else "1 policy value"
        lines.append(f"| {name} | {places} | {edited} | {len(d['stale'])} of 3 ({', '.join(d['stale']) or '-'}) "
                     f"| {len(d['current'])} of 3 |")
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
