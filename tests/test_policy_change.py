"""R14: policy values in replies. Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import policy_impact
from voxstage.dialogue import HandOff, step
from voxstage.evaluate import DEFAULT_DOMAINS_DIR
from voxstage.rules.interpreter import build_manager
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Utterance

CASES = {   # domain, lang -> (question, policy key, [(value, expected text)], flow id)
    ("bank", "en"): ("How many free transfers do I get each month", "free_transfers_per_month", [("3", "3 free"), ("5", "5 free")], "free_transfers"),
    ("bank", "ko"): ("한 달에 무료 이체가 몇 번이에요", "free_transfers_per_month", [("3", "3번"), ("5", "5번")], "free_transfers"),
    ("shop", "en"): ("What is the minimum order for free shipping", "free_shipping_threshold", [("50", "$50"), ("75", "$75")], "free_shipping"),
    ("shop", "ko"): ("얼마 이상 사야 배송비 안 내요", "free_shipping_threshold", [("50", "50달러"), ("75", "75달러")], "free_shipping"),
    ("telecom", "en"): ("How long is the grace period for a late payment", "late_payment_grace_days", [("10", "10 days"), ("14", "14 days")], "grace_period"),
    ("telecom", "ko"): ("요금을 늦게 내면 유예 기간이 며칠이에요", "late_payment_grace_days", [("10", "10일"), ("14", "14일")], "grace_period"),
}


def ask(domains_dir, domain, lang, text, policy):
    tools = FakeApiExecutor.from_yaml(os.path.join(domains_dir, domain, "tools.yaml"))
    m = build_manager(domains_dir, domain, lang, tools)
    state = m.initial_state("t", {"policy": policy} if policy is not None else {})
    return step(m, state, Utterance(text, source="typed"))


class PolicyFlowTest(unittest.TestCase):
    def test_reply_follows_the_policy_value(self):
        for (domain, lang), (text, key, values, flow) in CASES.items():
            for value, expected in values:
                with self.subTest(domain=domain, lang=lang, value=value):
                    r = ask(DEFAULT_DOMAINS_DIR, domain, lang, text, {key: value})
                    self.assertEqual(r.state.flow_id, flow)
                    self.assertIn(expected, r.reply)

    def test_missing_value_apologises_and_hands_off(self):
        for (domain, lang), (text, key, _, _) in CASES.items():
            with self.subTest(domain=domain, lang=lang):
                r = ask(DEFAULT_DOMAINS_DIR, domain, lang, text, {})
                self.assertTrue(any(isinstance(a, HandOff) for a in r.actions))

    def test_shop_questions_reach_their_own_flow(self):
        for lang, questions in policy_impact.QUESTIONS.items():
            for flow, text in questions.items():
                with self.subTest(lang=lang, flow=flow):
                    r = ask(DEFAULT_DOMAINS_DIR, "shop", lang, text, {"free_shipping_threshold": "50"})
                    self.assertEqual(r.state.flow_id, flow)

    def test_policy_flows_are_twins(self):
        for flow in ("free_transfers", "grace_period", "free_shipping", "free_shipping_offer", "free_shipping_how"):
            domain = {"free_transfers": "bank", "grace_period": "telecom"}.get(flow, "shop")
            shapes = []
            for lang in ("en", "ko"):
                tools = FakeApiExecutor.from_yaml(os.path.join(DEFAULT_DOMAINS_DIR, domain, "tools.yaml"))
                f = build_manager(DEFAULT_DOMAINS_DIR, domain, lang, tools).flows[flow]
                shapes.append({k: (n.type, n.data.get("next")) for k, n in f.nodes.items()})
            self.assertEqual(shapes[0], shapes[1], flow)


class ImpactTest(unittest.TestCase):
    def test_hardcoded_variant_ignores_the_policy(self):
        for lang in ("en", "ko"):
            with self.subTest(lang=lang):
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    pack = policy_impact.overlay(DEFAULT_DOMAINS_DIR, policy_impact.VARIANT_DIR, tmp)
                    got = policy_impact.replies(pack, lang, 100)
                self.assertTrue(all(policy_impact.say(50, lang) in r for r in got.values()))

    def test_one_edit_reaches_three_replies_only_by_reference(self):
        for lang in ("en", "ko"):
            with self.subTest(lang=lang):
                d = policy_impact.measure(lang, 50, 100)
                self.assertEqual(d["referenced"]["literal_sites"], [])
                self.assertEqual(d["referenced"]["stale"], [])
                self.assertEqual(len(d["referenced"]["current"]), 3)
                self.assertEqual(len(d["hardcoded"]["literal_sites"]), 3)
                self.assertEqual(d["hardcoded"]["stale"], ["free_shipping_how", "free_shipping_offer"])
                self.assertEqual(d["hardcoded"]["current"], ["free_shipping"])


if __name__ == "__main__":
    unittest.main()
