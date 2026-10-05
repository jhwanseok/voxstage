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
    def test_every_shipped_domain_covers_every_capability(self):
        shipped = [d for d in dataset.DOMAINS if os.path.isdir(os.path.join(ROOT, d))]
        self.assertIn("bank", shipped)
        for d in shipped:
            faq, scenarios = dataset.load_domain(os.path.join(ROOT, d))
            self.assertEqual(len(faq), 8, d)
            self.assertTrue(all(s.lang == "en" and s.domain == d for s in scenarios), d)
            self.assertEqual({s.capability for s in scenarios}, set(dataset.CAPABILITIES) - {"C00"}, d)
            # the cases that need a pair (a positive and a negative, or two policy versions)
            for cap in ("C08", "C09", "C11", "C12"):
                self.assertGreaterEqual(sum(s.capability == cap for s in scenarios), 2, f"{d} {cap}")

    def shipped(self):
        return [d for d in dataset.DOMAINS if os.path.isdir(os.path.join(ROOT, d))]

    def test_faq_answers_are_unique(self):
        for d in self.shipped():
            faq, _ = dataset.load_domain(os.path.join(ROOT, d))
            self.assertEqual(len({e.answer for e in faq}), len(faq), d)

    def test_scenario_tool_calls_match_the_fake_api(self):
        """Every tool call a scenario expects must be answerable by the domain's tools.yaml."""
        for d in self.shipped():
            api = FakeApiExecutor.from_yaml(os.path.join(ROOT, d, "tools.yaml"))  # shared across languages
            _, scenarios = dataset.load_domain(os.path.join(ROOT, d))
            for s in scenarios:
                for t in s.turns:
                    for call in t.expect.get("tool_calls", []):
                        result = api.call(call["name"], call["args"])
                        if "error" in call:
                            self.assertEqual(result.error, call["error"], f"{s.id}: {call}")
                        else:
                            self.assertTrue(result.ok, f"{s.id}: {call}")

    def test_dataset_is_english_and_contains_no_korean(self):
        """English first (ADR 0006): no Hangul in any English data file."""
        import glob
        files = glob.glob(os.path.join(ROOT, "*", "en", "**", "*.yaml"), recursive=True)
        files += glob.glob(os.path.join(ROOT, "*", "tools.yaml"))
        for path in files:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertFalse(any("\uac00" <= ch <= "\ud7a3" for ch in text), path)

    def test_asr_variants_differ_from_the_question_and_paraphrases(self):
        for d in self.shipped():
            faq, _ = dataset.load_domain(os.path.join(ROOT, d))
            for e in faq:
                for v in e.asr_variants:
                    self.assertNotEqual(v.lower(), e.question.lower(), e.id)
                    self.assertNotIn(v, e.paraphrases, e.id)

    def test_negative_c09_phrase_is_part_of_the_required_notice(self):
        """Guards drift between the positive and negative fixed-answer cases of a domain."""
        for d in self.shipped():
            _, scenarios = dataset.load_domain(os.path.join(ROOT, d))
            c09 = [s for s in scenarios if s.capability == "C09"]
            required = [p for s in c09 for t in s.turns for p in t.expect.get("reply_contains", [])]
            forbidden = [p for s in c09 for t in s.turns for p in t.expect.get("reply_not_contains", [])]
            self.assertTrue(required and forbidden, d)
            for f in forbidden:
                self.assertTrue(any(f in r for r in required), f"{d}: {f!r}")

    def test_policy_and_clock_setup_are_well_formed(self):
        from datetime import datetime
        for d in self.shipped():
            _, scenarios = dataset.load_domain(os.path.join(ROOT, d))
            for s in scenarios:
                if "now" in s.setup:
                    datetime.fromisoformat(s.setup["now"])
            versions = sorted(s.setup["policy"]["version"] for s in scenarios if s.capability == "C12")
            self.assertEqual(versions, ["v1", "v2"], d)

    def test_coverage_counts(self):
        counts = dataset.coverage(ROOT)
        self.assertEqual(counts[("bank", "C00")], 8)
        self.assertEqual(counts[("bank", "C08")], 2)
        self.assertEqual(counts[("telecom", "C01")], 1)
        self.assertEqual(sum(counts.values()), 3 * (8 + 16))  # 24 cases per domain
        self.assertIn("C05", dataset.format_coverage(counts))


class ValidationTest(unittest.TestCase):
    def write(self, body, domain="bank", name="x.yaml", lang="en"):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = os.path.join(self.tmp.name, domain, lang, "scenarios")
        os.makedirs(d)
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    BASE = ("id: bank.C01.900\nlang: en\ndomain: bank\ncapability: C01\ntitle: t\nturns:\n"
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

    def test_rejects_missing_or_mismatched_lang(self):
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE.replace("lang: en\n", "")))
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE, lang="ko"))  # file says en, sits in ko/

    def test_rejects_bad_tool_calls_and_actions(self):
        for extra in ("    expect: {tool_calls: [{name: t, args: {k: 5}}]}\n",
                      "    expect: {tool_calls: [{name: t}]}\n",
                      "    expect: {actions: [Explode]}\n"):
            with self.assertRaises(dataset.DatasetError, msg=extra):
                dataset.load_scenario(self.write(self.BASE + extra))
        ok = self.BASE + "    expect: {tool_calls: [], actions: [HandOff]}\n"
        self.assertEqual(dataset.load_scenario(self.write(ok)).turns[0].expect["tool_calls"], [])

    def test_rejects_wrong_domain_directory(self):
        with self.assertRaises(dataset.DatasetError):
            dataset.load_scenario(self.write(self.BASE, domain="shop"))


if __name__ == "__main__":
    unittest.main()
