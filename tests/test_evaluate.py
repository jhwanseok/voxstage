"""Run: python -m unittest discover -s tests -v"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset, evaluate, ledger
from voxstage.dialogue import DialogueManager, DMResult, EndCall, HandOff
from voxstage.evaluate import (Case, RecordingTools, build_cases, canonical_slot, compare, evaluate as run_eval,
                               run_case, summarize, to_markdown, write_report)
from voxstage.reference_managers import null_factory, oracle_factory
from voxstage.tools import FakeApiExecutor

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


class CanonicalSlotTest(unittest.TestCase):
    def test_symbols_words_and_commas_are_ignored(self):
        for raw in ("500", "$500", "500 dollars", "500달러", "500 USD", "₩500", "500원", "500엔"):
            self.assertEqual(canonical_slot(raw), "500", raw)
        self.assertEqual(canonical_slot("$1,250"), "1250")
        self.assertEqual(canonical_slot("1,250.50"), "1250.50")

    def test_everything_else_stays_exact(self):
        self.assertNotEqual(canonical_slot("5000"), canonical_slot("500"))
        self.assertEqual(canonical_slot("five hundred"), "five hundred")
        self.assertEqual(canonical_slot(" blue jacket "), "blue jacket")
        self.assertEqual(canonical_slot("2026-11-15"), "2026-11-15")
        self.assertEqual(canonical_slot("12,34"), "12,34")  # not a thousands grouping


class ScriptedDM(DialogueManager):
    """Test double: replies and slots come from constructor arguments."""
    name = "scripted"

    def __init__(self, reply="", slots=None, flow=None, actions=(), calls=(), tools=None):
        self.reply, self.slots, self.flow, self.actions, self.calls, self.tools = \
            reply, slots or {}, flow, actions, calls, tools

    def respond(self, state, turn_input):
        for name, args in self.calls:
            self.tools.call(name, args)
        return DMResult(self.reply, state.evolve(slots={**state.slots, **self.slots}, flow_id=self.flow),
                        tuple(self.actions))


def make_case(expect, user=None, setup=None):
    turn = dataset.Turn(user=user or {"kind": "utterance", "text": "hi"}, expect=expect)
    return Case("t.C01.001", "scenario", "bank", "en", "C01", (turn,), setup or {}, "base")


def run_with(dm_kwargs, expect, **case_kwargs):
    case = make_case(expect, **case_kwargs)
    return run_case(lambda ctx: ScriptedDM(tools=ctx.tools, **dm_kwargs), case, ROOT)


class CheckTest(unittest.TestCase):
    def failures(self, dm_kwargs, expect):
        return [f["check"] for f in run_with(dm_kwargs, expect)["failures"]]

    def test_flow(self):
        self.assertEqual(self.failures({"flow": "a"}, {"flow": "a"}), [])
        self.assertEqual(self.failures({"flow": "b"}, {"flow": "a"}), ["flow"])

    def test_slots_subset_with_canonical_form(self):
        self.assertEqual(self.failures({"slots": {"amount": "$500", "x": "y"}}, {"slots": {"amount": "500"}}), [])
        self.assertEqual(self.failures({"slots": {"amount": "5000"}}, {"slots": {"amount": "500"}}), ["slots.amount"])
        self.assertEqual(self.failures({}, {"slots": {"amount": "500"}}), ["slots.amount"])

    def test_reply_checks(self):
        ok = {"reply": "Open nine to four"}
        self.assertEqual(self.failures(ok, {"reply_contains": ["nine"], "reply_contains_any": ["x", "four"],
                                            "reply_not_contains": ["closed"]}), [])
        self.assertEqual(self.failures(ok, {"reply_contains": ["nine", "ten"]}), ["reply_contains"])
        self.assertEqual(self.failures(ok, {"reply_contains_any": ["x", "y"]}), ["reply_contains_any"])
        self.assertEqual(self.failures(ok, {"reply_not_contains": ["four"]}), ["reply_not_contains"])

    def test_tool_calls_are_exact_and_ordered(self):
        call = {"name": "get_balance", "args": {"account_last4": "4821"}}
        dm = {"calls": [("get_balance", {"account_last4": "4821"})]}
        self.assertEqual(self.failures(dm, {"tool_calls": [call]}), [])
        self.assertEqual(self.failures({}, {"tool_calls": [call]}), ["tool_calls"])
        self.assertEqual(self.failures(dm, {"tool_calls": []}), ["tool_calls"])
        wrong = {"name": "get_balance", "args": {"account_last4": "7310"}}
        self.assertEqual(self.failures(dm, {"tool_calls": [wrong]}), ["tool_calls"])
        self.assertEqual(self.failures({}, {"tool_calls": []}), [])

    def test_expected_tool_error_must_match(self):
        timeout = {"name": "get_balance", "args": {"account_last4": "0000"}, "error": "timeout"}
        dm = {"calls": [("get_balance", {"account_last4": "0000"})]}
        self.assertEqual(self.failures(dm, {"tool_calls": [timeout]}), [])
        plain = {"name": "get_balance", "args": {"account_last4": "0000"}}
        self.assertEqual(self.failures(dm, {"tool_calls": [plain]}), ["tool_calls"])  # error not expected

    def test_actions_by_class_name(self):
        self.assertEqual(self.failures({"actions": [HandOff("x")]}, {"actions": ["HandOff"]}), [])
        self.assertEqual(self.failures({"actions": [EndCall()]}, {"actions": ["HandOff"]}), ["actions"])
        self.assertEqual(self.failures({}, {"actions": []}), [])

    def test_setup_reaches_state_meta_and_inputs_by_mode(self):
        seen = {}

        class Spy(DialogueManager):
            def respond(self, state, turn_input):
                seen["meta"], seen["input"] = state.meta, turn_input
                return DMResult("", state)

        user = {"kind": "utterance", "text": "thirty", "asr_text": "thirteen"}
        case = make_case({}, user=user, setup={"customer": {"grade": "gold"}})
        run_case(lambda ctx: Spy(), case, ROOT, "clean")
        self.assertEqual((seen["meta"]["customer"], seen["input"].text), ({"grade": "gold"}, "thirty"))
        run_case(lambda ctx: Spy(), case, ROOT, "noisy")
        self.assertEqual(seen["input"].text, "thirteen")
        for user, kind in (({"kind": "dtmf", "digits": "4821"}, "Dtmf"), ({"kind": "button", "button_id": "b"}, "ButtonPress")):
            run_case(lambda ctx: Spy(), make_case({}, user=user), ROOT)
            self.assertEqual(type(seen["input"]).__name__, kind)


class CaseBuildTest(unittest.TestCase):
    def test_variants_and_faq_queries_become_cases(self):
        cases = build_cases(ROOT, "en", ["bank"])
        ids = {c.id for c in cases}
        self.assertIn("bank.C05.001", ids)
        self.assertIn("bank.C05.001#v1.1", ids)
        variant = next(c for c in cases if c.id == "bank.C05.001#v1.1")
        self.assertNotIn("asr_text", variant.turns[1].user)
        self.assertTrue(any(c.kind == "faq" and c.source == "asr_variant" for c in cases))


class FloorAndCeilingTest(unittest.TestCase):
    def test_null_scores_zero_and_oracle_scores_hundred_in_both_languages_and_modes(self):
        for lang in ("en", "ko"):
            for mode in ("clean", "noisy"):
                null = run_eval(null_factory, domains_dir=ROOT, lang=lang, mode=mode, manager_name="null")
                oracle = run_eval(oracle_factory, domains_dir=ROOT, lang=lang, mode=mode, manager_name="oracle")
                self.assertEqual(null["summary"]["overall"]["passed"], 0, (lang, mode))
                total = oracle["summary"]["overall"]
                self.assertEqual(total["passed"], total["total"], (lang, mode, [r["id"] for r in oracle["results"] if not r["passed"]][:3]))
                self.assertEqual(total["total"], null["summary"]["overall"]["total"])

    def test_base_case_counts_are_72_per_language(self):
        for lang in ("en", "ko"):
            cases = build_cases(ROOT, lang)
            base = [c for c in cases if c.source in ("base", "question")]
            self.assertEqual(len(base), 72, lang)


class ReportTest(unittest.TestCase):
    def test_report_round_trip_and_compare(self):
        a = run_eval(null_factory, domains_dir=ROOT, domains=["bank"], manager_name="null")
        b = run_eval(oracle_factory, domains_dir=ROOT, domains=["bank"], manager_name="oracle")
        with tempfile.TemporaryDirectory() as tmp:
            jpath, mpath = write_report(b, tmp)
            with open(jpath, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["summary"], b["summary"])
            with open(mpath, encoding="utf-8") as f:
                self.assertIn("Overall:", f.read())
        diff = compare(a, b)
        self.assertEqual(diff["regressions"], [])
        self.assertEqual(len(diff["fixes"]), len(a["results"]))
        self.assertEqual(compare(b, a)["fixes"], [])
        self.assertIn("bank", b["summary"]["by_domain"])
        self.assertIn("C00", to_markdown(b))
        self.assertEqual(set(b["summary"]["faq_by_source"]), {"question", "paraphrase", "asr_variant"})

    def test_failures_carry_the_reason(self):
        r = run_with({"reply": "no"}, {"reply_contains": ["yes"]})
        self.assertEqual(r["failures"][0], {"turn": 0, "check": "reply_contains", "expected": "yes", "actual": "no"})


class LedgerTest(unittest.TestCase):
    def test_measure_counts_flows_patterns_and_code_without_comments(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "voxstage", "rules"))
            os.makedirs(os.path.join(root, "domains", "bank", "en", "flows"))
            os.makedirs(os.path.join(root, "domains", "bank", "en", "rules"))
            with open(os.path.join(root, "voxstage", "rules", "interpreter.py"), "w") as f:
                f.write("# c\n\nx = 1\ny = 2\n")
            with open(os.path.join(root, "voxstage", "rules", "faq.py"), "w") as f:
                f.write("z = 3\n")
            with open(os.path.join(root, "domains", "bank", "en", "flows", "a.yaml"), "w") as f:
                f.write("id: a\n# c\nnodes:\n  n1: {type: say}\n  n2: {type: end}\n")
            with open(os.path.join(root, "domains", "bank", "en", "rules", "faq_patterns.yaml"), "w") as f:
                f.write("entries:\n  - {id: a, all_of: [x]}\n  - {id: b, regex: 'x.*y'}\n")
            m = ledger.measure(root)
            self.assertEqual(m["code"], {"interpreter_lines": 2, "other_rule_lines": 1})
            self.assertEqual(m["packs"], [{"domain": "bank", "lang": "en", "flow_lines": 4, "flow_nodes": 2,
                                           "patterns": 2, "regex": 1}])
            out = os.path.join(root, "docs", "ledger", "effort.md")
            self.assertEqual(ledger.append_rows(out, "R9", m, "abc1234"), 1)
            ledger.append_rows(out, "R9", m, "abc1234")
            with open(out, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text.count("| R9 | abc1234 | bank | en |"), 2)
            self.assertEqual(text.count("| Step |"), 1)  # header written once

    def test_measure_works_on_the_real_tree(self):
        m = ledger.measure()
        self.assertIn("interpreter_lines", m["code"])


if __name__ == "__main__":
    unittest.main()
