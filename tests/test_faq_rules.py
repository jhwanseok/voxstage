"""R1: FAQ keyword rules. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset, evaluate
from voxstage.dialogue import EndCall, HandOff, step
from voxstage.domain_pack import DomainPack, Fallback, Pattern, RuleError, load_fallback, load_patterns
from voxstage.reference_managers import null_factory
from voxstage.rules.faq import MISSES, FaqRuleManager
from voxstage.rules.tokenize import EnglishTokenizer, KiwiTokenizer, kiwi_available
from voxstage.turn import ButtonPress, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
needs_kiwi = unittest.skipUnless(kiwi_available(), "kiwipiepy missing: pip install 'voxstage[ko]'")


def pat(id, all_of=(), any_of=(), none_of=(), priority=0, regex=()):
    return Pattern(id, tuple(tuple(g) if isinstance(g, (list, tuple)) else (g,) for g in all_of),
                   tuple(any_of), tuple(none_of), priority, tuple(regex))


def pack(patterns, fallback=None, lang="en"):
    answers = {p.id: f"answer:{p.id}" for p in patterns}
    return DomainPack("bank", lang, answers, tuple(patterns),
                      fallback or Fallback("sorry", "bye now", 3, "handoff"))


def ask(manager, text, state=None):
    state = state or manager.initial_state("s")
    return step(manager, state, Utterance(text))


class EnglishTokenizerTest(unittest.TestCase):
    def test_lowercases_and_drops_punctuation(self):
        a = EnglishTokenizer().analyze("What's your Opening hours?!")
        self.assertEqual(a.tokens, ("what's", "your", "opening", "hours"))

    def test_words_match_whole_tokens_only(self):
        t = EnglishTokenizer()
        a = t.analyze("closing time")
        self.assertTrue(t.has(a, "Closing"))
        self.assertFalse(t.has(a, "clos"))


@needs_kiwi
class KiwiTokenizerTest(unittest.TestCase):
    def test_spacing_does_not_matter_for_noun_compounds(self):
        t = KiwiTokenizer()
        for text in ("영업시간이 어떻게 되나요", "영업 시간 알려주세요", "영업시간 알려줘"):
            a = t.analyze(text)
            self.assertTrue(t.has(a, "영업시간"), text)
            self.assertTrue(t.has(a, "영업") and t.has(a, "시간"), text)

    def test_particles_and_endings_are_not_content(self):
        t = KiwiTokenizer()
        a = t.analyze("카드를 잃어버렸어요")
        self.assertTrue(t.has(a, "카드") and t.has(a, "잃어버리"))
        self.assertFalse(t.has(a, "를"))  # one syllable: only equal to a morpheme, and 를 is a particle

    def test_missing_dependency_message(self):
        import builtins
        real = builtins.__import__

        def fake(name, *a, **k):
            if name == "kiwipiepy":
                raise ImportError("no")
            return real(name, *a, **k)
        builtins.__import__ = fake
        try:
            with self.assertRaises(ImportError) as cm:
                KiwiTokenizer()
        finally:
            builtins.__import__ = real
        self.assertIn("voxstage[ko]", str(cm.exception))


class MatchingTest(unittest.TestCase):
    def test_all_of_any_of_none_of_and_synonym_groups(self):
        m = FaqRuleManager(pack([pat("a", all_of=["return", ["item", "order"]], any_of=["how", "can"], none_of=["address"])]))
        self.assertEqual(m.match("how do I return an order")[0].id, "a")
        self.assertIsNone(m.match("return an order")[0])               # any_of not satisfied
        self.assertIsNone(m.match("how do I return my address order")[0])  # none_of
        self.assertIsNone(m.match("how do I return")[0])                # synonym group not satisfied

    def test_highest_priority_then_specificity_then_file_order(self):
        m = FaqRuleManager(pack([pat("low", all_of=["card"]), pat("specific", all_of=["card", "lost"]),
                                 pat("first", all_of=["lost"]), pat("prio", all_of=["card"], priority=1)]))
        self.assertEqual(m.match("lost card")[0].id, "prio")
        m = FaqRuleManager(pack([pat("low", all_of=["card"]), pat("specific", all_of=["card", "lost"])]))
        self.assertEqual(m.match("lost card")[0].id, "specific")
        m = FaqRuleManager(pack([pat("one", all_of=["card"]), pat("two", all_of=["card"])]))
        pattern, trace = m.match("a card")
        self.assertEqual((pattern.id, trace["ties"]), ("one", ["two"]))

    def test_regex_is_an_alternative_path(self):
        m = FaqRuleManager(pack([pat("r", regex=[r"open.*(saturday|sunday)"])]))
        self.assertEqual(m.match("Are you OPEN on Saturday")[0].id, "r")
        self.assertIsNone(m.match("closed saturday")[0])

    def test_match_returns_verbatim_answer_and_trace(self):
        m = FaqRuleManager(pack([pat("a", all_of=["hours"])]))
        r = ask(m, "your hours?")
        self.assertEqual((r.reply, r.trace["rule"]), ("answer:a", "a"))


class FallbackTest(unittest.TestCase):
    def run_misses(self, n, action):
        m = FaqRuleManager(pack([pat("a", all_of=["hours"])], Fallback("sorry", "bye now", n, action)))
        state, results = m.initial_state("s"), []
        for i in range(n):
            r = ask(m, "something else", state)
            state = r.state
            results.append(r)
        return results

    def test_escalates_after_n_misses_with_either_action(self):
        for n in (2, 3):
            results = self.run_misses(n, "handoff")
            self.assertTrue(all(r.reply == "sorry" and not r.actions for r in results[:-1]))
            self.assertEqual((results[-1].reply, results[-1].actions), ("bye now", (HandOff("no_match"),)))
            self.assertEqual(self.run_misses(n, "end_call")[-1].actions, (EndCall(),))

    def test_a_match_resets_the_counter(self):
        m = FaqRuleManager(pack([pat("a", all_of=["hours"])], Fallback("sorry", "bye now", 2, "handoff")))
        s = ask(m, "blah").state
        self.assertEqual(s.meta[MISSES], 1)
        s = ask(m, "your hours", s).state
        self.assertEqual(s.meta[MISSES], 0)
        r = ask(m, "blah", s)
        self.assertEqual((r.reply, r.actions), ("sorry", ()))  # not escalated: counter restarted

    def test_other_input_kinds_count_as_misses_and_do_not_mutate_state(self):
        m = FaqRuleManager(pack([pat("a", all_of=["hours"])]))
        s0 = m.initial_state("s")
        r = step(m, s0, ButtonPress("menu"))
        self.assertEqual((r.reply, r.state.meta[MISSES]), ("sorry", 1))
        self.assertNotIn(MISSES, s0.meta)

    def test_manager_needs_a_fallback_policy(self):
        with self.assertRaises(ValueError):
            FaqRuleManager(DomainPack("bank", "en", {}, (), None))


class FileValidationTest(unittest.TestCase):
    def write(self, text):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = os.path.join(self.tmp.name, "f.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_patterns_must_cover_exactly_the_faq_ids(self):
        ok = "entries:\n  - {id: a, all_of: [x]}\n"
        self.assertEqual(len(load_patterns(self.write(ok), {"a"})), 1)
        with self.assertRaises(RuleError):
            load_patterns(self.write(ok), {"a", "b"})          # missing b
        with self.assertRaises(RuleError):
            load_patterns(self.write(ok), {"b"})               # unknown a
        with self.assertRaises(RuleError):
            load_patterns(self.write("entries:\n  - {id: a}\n"), {"a"})              # no condition
        with self.assertRaises(RuleError):
            load_patterns(self.write("entries:\n  - {id: a, all_of: [x], foo: 1}\n"), {"a"})
        with self.assertRaises(RuleError):
            load_patterns(self.write("entries:\n  - {id: a, all_of: [x], priority: high}\n"), {"a"})
        with self.assertRaises(RuleError):
            load_patterns(self.write("entries:\n  - {id: a, all_of: [false]}\n"), {"a"})  # YAML booleans

    def test_fallback_config_is_validated(self):
        good = "fallback: {reply: r, exceed_reply: e, max_misses: 2, on_exceed: end_call}\n"
        self.assertEqual(load_fallback(self.write(good)), Fallback("r", "e", 2, "end_call"))
        for bad in ("fallback: {reply: r}\n", "fallback: {reply: r, exceed_reply: e, max_misses: 0}\n",
                    "fallback: {reply: r, exceed_reply: e, on_exceed: hangup}\n",
                    "fallback: {reply: r, exceed_reply: e, extra: 1}\n", "other: 1\n"):
            with self.assertRaises(RuleError, msg=bad):
                load_fallback(self.write(bad))


class HeldOutTest(unittest.TestCase):
    def test_authoring_view_shows_only_id_question_answer(self):
        for d in dataset.DOMAINS:
            for lang in ("en", "ko"):
                faq, _ = dataset.load_domain(os.path.join(ROOT, d), lang)
                view = dataset.authoring_view(os.path.join(ROOT, d), lang)
                self.assertEqual(len(view), len(faq))
                lines = {line for row in view for line in row}  # whole values, not substrings
                for e in faq:
                    for held_out in e.paraphrases + e.asr_variants:
                        self.assertNotIn(held_out, lines, e.id)

    def test_domain_pack_does_not_carry_held_out_text(self):
        p = DomainPack.load(ROOT, "bank", "en")
        faq, _ = dataset.load_domain(os.path.join(ROOT, "bank"), "en")
        blob = repr(p)
        for e in faq:
            for held_out in e.paraphrases + e.asr_variants:
                self.assertNotIn(held_out, blob)

    def test_unanswerable_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "en")
            os.makedirs(d)
            path = os.path.join(d, "faq_unanswerable.yaml")
            with open(path, "w") as f:
                f.write("status: draft\nlang: en\nquestions: [a, b, c, d, e]\n")
            self.assertEqual(dataset.load_unanswerable(path), list("abcde"))
            with open(path, "w") as f:
                f.write("status: draft\nlang: en\nquestions: [a, b]\n")
            with self.assertRaises(dataset.DatasetError):
                dataset.load_unanswerable(path)

    def test_shipped_unanswerable_drafts_load(self):
        for d in dataset.DOMAINS:
            for lang in ("en", "ko"):
                qs = dataset.load_unanswerable(os.path.join(ROOT, d, lang, "faq_unanswerable.yaml"))
                self.assertEqual(len(qs), 5, (d, lang))


class ShippedPacksTest(unittest.TestCase):
    def packs(self):
        for d in dataset.DOMAINS:
            yield d, "en"
            if kiwi_available():
                yield d, "ko"

    def test_each_canonical_question_hits_its_own_entry_and_regex_has_a_note(self):
        for d, lang in self.packs():
            p = DomainPack.load(ROOT, d, lang)
            m = FaqRuleManager(p)
            faq, _ = dataset.load_domain(os.path.join(ROOT, d), lang)
            for e in faq:
                self.assertEqual(m.match(e.question)[0].id, e.id, f"{d}/{lang}")
            for pattern in p.patterns:
                if pattern.regex:
                    import yaml
                    with open(os.path.join(p.base_dir, "rules", "faq_patterns.yaml"), encoding="utf-8") as f:
                        entry = next(x for x in yaml.safe_load(f)["entries"] if x["id"] == pattern.id)
                    self.assertTrue(entry.get("note"), f"{pattern.id}: regex needs a note")

    def test_draft_unanswerable_questions_are_refused(self):
        report = evaluate.evaluate(lambda ctx: FaqRuleManager(DomainPack.load(ROOT, ctx.domain, ctx.lang)),
                                   domains_dir=ROOT, lang="en", include_unanswerable=True, manager_name="faq")
        self.assertEqual(report["summary"]["false_accept"]["total"], 15)

    def test_unanswerable_cases_are_reported_apart_from_the_pass_rate(self):
        plain = evaluate.evaluate(null_factory, domains_dir=ROOT, lang="en", manager_name="null")
        withu = evaluate.evaluate(null_factory, domains_dir=ROOT, lang="en", include_unanswerable=True,
                                  manager_name="null")
        self.assertEqual(plain["summary"]["overall"], withu["summary"]["overall"])
        self.assertNotIn("false_accept", plain["summary"])
        self.assertEqual(withu["summary"]["false_accept"]["false_accepts"], 0)  # empty replies accept nothing


if __name__ == "__main__":
    unittest.main()
