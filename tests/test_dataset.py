"""Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset
from voxstage.tools import FakeApiExecutor

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


HANGUL = lambda text: any("\uac00" <= ch <= "\ud7a3" for ch in text)
SHIPPED_LANGS = ("en", "ko")


class ShippedDataTest(unittest.TestCase):
    def shipped(self):
        return [d for d in dataset.DOMAINS if os.path.isdir(os.path.join(ROOT, d))]

    def each(self):
        """Every (domain, lang, faq, scenarios) that ships. Languages share ids and structure."""
        for d in self.shipped():
            for lang in SHIPPED_LANGS:
                faq, scenarios = dataset.load_domain(os.path.join(ROOT, d), lang)
                yield d, lang, faq, scenarios

    def test_every_shipped_domain_covers_every_capability(self):
        self.assertIn("bank", self.shipped())
        for d, lang, faq, scenarios in self.each():
            where = f"{d}/{lang}"
            self.assertEqual(len(faq), 8, where)
            self.assertTrue(all(s.lang == lang and s.domain == d for s in scenarios), where)
            self.assertEqual({s.capability for s in scenarios}, set(dataset.CAPABILITIES) - {"C00"}, where)
            # the cases that need a pair (a positive and a negative, or two policy versions)
            for cap in ("C08", "C09", "C11", "C12"):
                self.assertGreaterEqual(sum(s.capability == cap for s in scenarios), 2, f"{where} {cap}")

    def test_languages_are_twins(self):
        """ko mirrors en: same ids, and the same flow/slots/tool_calls/actions per turn.
        Only the language-bearing parts (utterances, expected wording, variants) may differ."""
        for d in self.shipped():
            en_faq, en_sc = dataset.load_domain(os.path.join(ROOT, d), "en")
            ko_faq, ko_sc = dataset.load_domain(os.path.join(ROOT, d), "ko")
            self.assertEqual([e.id for e in en_faq], [e.id for e in ko_faq], d)
            self.assertEqual(sorted(s.id for s in en_sc), sorted(s.id for s in ko_sc), d)
            ko_by_id = {s.id: s for s in ko_sc}
            for en in en_sc:
                ko = ko_by_id[en.id]
                self.assertEqual((en.capability, en.setup), (ko.capability, ko.setup), en.id)
                self.assertEqual(len(en.turns), len(ko.turns), en.id)
                for te, tk in zip(en.turns, ko.turns):
                    self.assertEqual(te.user["kind"], tk.user["kind"], en.id)
                    if te.user["kind"] != "utterance":
                        self.assertEqual(te.user, tk.user, en.id)  # buttons and digits are language-free
                    for key in ("flow", "slots", "tool_calls", "actions"):
                        self.assertEqual(te.expect.get(key), tk.expect.get(key), f"{en.id} {key}")
                    for key in ("reply_contains", "reply_not_contains"):  # same constraints, not same words
                        self.assertEqual(bool(te.expect.get(key)), bool(tk.expect.get(key)), f"{en.id} {key}")

    def test_faq_answers_are_unique(self):
        for d, lang, faq, _ in self.each():
            self.assertEqual(len({e.answer for e in faq}), len(faq), f"{d}/{lang}")

    def test_scenario_tool_calls_match_the_fake_api(self):
        """Every tool call a scenario expects must be answerable by the domain's tools.yaml."""
        for d, lang, _, scenarios in self.each():
            api = FakeApiExecutor.from_yaml(os.path.join(ROOT, d, "tools.yaml"))  # shared across languages
            for s in scenarios:
                for t in s.turns:
                    for call in t.expect.get("tool_calls", []):
                        result = api.call(call["name"], call["args"])
                        if "error" in call:
                            self.assertEqual(result.error, call["error"], f"{s.id}: {call}")
                        else:
                            self.assertTrue(result.ok, f"{s.id}: {call}")

    def test_language_files_use_their_own_script(self):
        """en files contain no Hangul (ADR 0006); ko utterances and FAQ text do contain Hangul.
        tools.yaml is shared and language-free."""
        import glob
        files = glob.glob(os.path.join(ROOT, "*", "en", "**", "*.yaml"), recursive=True)
        files += glob.glob(os.path.join(ROOT, "*", "tools.yaml"))
        for path in files:
            with open(path, encoding="utf-8") as f:
                self.assertFalse(HANGUL(f.read()), path)
        for d in self.shipped():
            faq, scenarios = dataset.load_domain(os.path.join(ROOT, d), "ko")
            for e in faq:
                self.assertTrue(HANGUL(e.question) and HANGUL(e.answer), e.id)
            for s in scenarios:
                for t in s.turns:
                    if t.user["kind"] == "utterance":
                        self.assertTrue(HANGUL(t.user["text"]), s.id)

    def test_asr_variants_differ_from_the_question_and_paraphrases(self):
        for d, lang, faq, _ in self.each():
            for e in faq:
                for v in e.asr_variants:
                    self.assertNotEqual(v.lower(), e.question.lower(), e.id)
                    self.assertNotIn(v, e.paraphrases, e.id)

    def test_negative_c09_phrase_is_part_of_the_required_notice(self):
        """Guards drift between the positive and negative fixed-answer cases of a domain."""
        for d, lang, _, scenarios in self.each():
            c09 = [s for s in scenarios if s.capability == "C09"]
            required = [p for s in c09 for t in s.turns for p in t.expect.get("reply_contains", [])]
            forbidden = [p for s in c09 for t in s.turns for p in t.expect.get("reply_not_contains", [])]
            self.assertTrue(required and forbidden, f"{d}/{lang}")
            for f in forbidden:
                self.assertTrue(any(f in r for r in required), f"{d}/{lang}: {f!r}")

    def test_policy_and_clock_setup_are_well_formed(self):
        from datetime import datetime
        for d, lang, _, scenarios in self.each():
            for s in scenarios:
                if "now" in s.setup:
                    datetime.fromisoformat(s.setup["now"])
            versions = sorted(s.setup["policy"]["version"] for s in scenarios if s.capability == "C12")
            self.assertEqual(versions, ["v1", "v2"], f"{d}/{lang}")

    def test_coverage_counts(self):
        for lang in SHIPPED_LANGS:
            counts = dataset.coverage(ROOT, lang)
            self.assertEqual(counts[("bank", "C00")], 8, lang)
            self.assertEqual(counts[("bank", "C08")], 2, lang)
            self.assertEqual(counts[("telecom", "C01")], 1, lang)
            self.assertEqual(sum(counts.values()), 3 * (8 + 16), lang)  # 24 cases per domain
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
