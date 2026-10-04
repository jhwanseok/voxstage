"""Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset
from voxstage.tools import FakeApiExecutor

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


class ShippedDataTest(unittest.TestCase):
    def test_bank_pilot_loads(self):
        faq, scenarios = dataset.load_domain(os.path.join(ROOT, "bank"))
        self.assertEqual(len(faq), 8)
        self.assertEqual({s.capability for s in scenarios}, {"C01", "C04", "C05", "C08", "C09"})

    def test_faq_answers_are_unique(self):
        faq, _ = dataset.load_domain(os.path.join(ROOT, "bank"))
        self.assertEqual(len({e.answer for e in faq}), len(faq))

    def test_scenario_tool_calls_match_the_fake_api(self):
        """Every tool call a scenario expects must be answerable by the domain's tools.yaml."""
        api = FakeApiExecutor.from_yaml(os.path.join(ROOT, "bank", "tools.yaml"))
        _, scenarios = dataset.load_domain(os.path.join(ROOT, "bank"))
        for s in scenarios:
            for t in s.turns:
                for call in t.expect.get("tool_calls", []):
                    self.assertTrue(api.call(call["name"], call["args"]).ok, f"{s.id}: {call}")

    def test_coverage_counts(self):
        counts = dataset.coverage(ROOT)
        self.assertEqual(counts[("bank", "C00")], 8)
        self.assertEqual(counts[("bank", "C08")], 2)
        self.assertEqual(counts[("telecom", "C01")], 0)
        self.assertIn("C05 슬롯 오기입 재채움", dataset.format_coverage(counts))


class ValidationTest(unittest.TestCase):
    def write(self, body, domain="bank", name="x.yaml"):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = os.path.join(self.tmp.name, domain, "scenarios")
        os.makedirs(d)
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    BASE = ("id: bank.C01.900\ndomain: bank\ncapability: C01\ntitle: t\nturns:\n"
            "  - user: {kind: utterance, text: 안녕}\n")

    def test_valid_minimal(self):
        self.assertEqual(dataset.load_scenario(self.write(self.BASE)).id, "bank.C01.900")

    def test_rejects_unknown_capability_and_id_prefix(self):
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE.replace("capability: C01", "capability: C99")))
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE.replace("bank.C01.900", "bank.C02.900")))

    def test_rejects_unquoted_digits(self):
        body = self.BASE.replace("{kind: utterance, text: 안녕}", "{kind: dtmf, digits: 4821}")
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(body))

    def test_rejects_unknown_expect_key_and_bad_variant(self):
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE + "    expect: {replys: [a]}\n"))
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE + "variants:\n  - {turn: 5, texts: [a]}\n"))

    def test_rejects_wrong_domain_directory(self):
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE, domain="shop"))


if __name__ == "__main__":
    unittest.main()
