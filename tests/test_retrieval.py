"""S2-1: embedding FAQ retrieval. Most tests use a stub embedder, so they run without the model; the ones that need
the real model are skipped when it is not in the local cache. Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset, retrieval
from voxstage.evaluate import DEFAULT_DOMAINS_DIR
from voxstage.rules.faq import _pack
from voxstage.turn import Utterance
from voxstage.dialogue import step

DIM = 64


class StubEmbedder:
    """Bag of words hashed into 64 dimensions, normalised: sentences that share words are similar."""

    def __init__(self):
        self.seen = []

    def _vec(self, text):
        v = np.zeros(DIM)
        for w in text.lower().split():
            v[sum(ord(c) * (i + 1) for i, c in enumerate(w)) % DIM] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_queries(self, texts):
        self.seen += [("q", t) for t in texts]
        return np.array([self._vec(t) for t in texts])

    def encode_passages(self, texts):
        self.seen += [("p", t) for t in texts]
        return np.array([self._vec(t) for t in texts])


ENTRIES = [("a", "opening hours of the branch"), ("b", "lost debit card block"), ("c", "transfer limit per day")]


class MatcherTest(unittest.TestCase):
    def test_accepts_above_the_threshold_and_rejects_below(self):
        m = retrieval.EmbeddingMatcher(ENTRIES, StubEmbedder(), threshold=0.5)
        pattern, trace = m.match("opening hours of the branch")
        self.assertEqual(pattern.id, "a")
        self.assertEqual(trace["matched"], "a")
        self.assertGreater(trace["retrieval"]["score"], 0.99)
        pattern, trace = m.match("weather tomorrow sunny")
        self.assertIsNone(pattern)
        self.assertIsNone(trace["matched"])
        self.assertEqual(trace["retrieval"]["rejected"], "below_threshold")

    def test_the_margin_rejects_a_close_runner_up(self):
        entries = [("a", "card lost block"), ("b", "card lost stolen block")]
        m = retrieval.EmbeddingMatcher(entries, StubEmbedder(), threshold=0.1, margin=0.5)
        pattern, trace = m.match("card lost block")
        self.assertIsNone(pattern)
        self.assertEqual(trace["retrieval"]["rejected"], "below_margin")
        self.assertEqual(retrieval.EmbeddingMatcher(entries, StubEmbedder(), threshold=0.1, margin=0.0)
                         .match("card lost block")[0].id, "a")

    def test_the_same_signature_as_the_rule_matcher(self):
        pack = _pack(DEFAULT_DOMAINS_DIR, "bank", "en")
        rules = retrieval.FaqRuleManager(pack).matcher
        rule_result = rules.match("What are your opening hours")
        emb_result = retrieval.EmbeddingMatcher(ENTRIES, StubEmbedder(), 0.5).match("opening hours of the branch")
        for pattern, trace in (rule_result, emb_result):
            self.assertTrue(hasattr(pattern, "id"))
            self.assertIn("matched", trace)

    def test_hybrid_asks_the_rules_first(self):
        class Rules:
            def match(self, text):
                return (retrieval.Pattern("rule_hit", (), (), ()), {"matched": "rule_hit"}) if "hello" in text else (None, {"matched": None})

        emb = retrieval.EmbeddingMatcher(ENTRIES, StubEmbedder(), 0.5)
        hybrid = retrieval.HybridMatcher(Rules(), emb)
        pattern, trace = hybrid.match("hello transfer limit per day")
        self.assertEqual((pattern.id, trace["by"]), ("rule_hit", "rules"))
        pattern, trace = hybrid.match("transfer limit per day")
        self.assertEqual((pattern.id, trace["by"]), ("c", "embeddings"))
        pattern, trace = hybrid.match("completely unrelated words")
        self.assertEqual((pattern, trace["by"]), (None, "none"))


class PrefixTest(unittest.TestCase):
    def test_e5_prefixes_are_applied_in_one_place(self):
        seen = []

        class Spy(retrieval.SentenceEmbedder):
            def _encode(self, texts):
                seen.extend(texts)
                return np.zeros((len(texts), 2))

        spy = Spy(retrieval.MODELS["e5-small"])
        spy.encode_queries(["how are you"])
        spy.encode_passages(["opening hours"])
        self.assertEqual(seen, ["query: how are you", "passage: opening hours"])
        seen.clear()
        bge = Spy(retrieval.MODELS["bge-m3"])
        bge.encode_queries(["x"])
        self.assertEqual(seen, ["x"])


class ManagerTest(unittest.TestCase):
    def manager(self, threshold=0.99):
        pack = _pack(DEFAULT_DOMAINS_DIR, "bank", "en")
        matcher = retrieval.EmbeddingMatcher([(i, q) for i, q, _ in dataset.authoring_view(
            os.path.join(DEFAULT_DOMAINS_DIR, "bank"), "en")], StubEmbedder(), threshold)
        return retrieval.FaqEmbeddingManager(pack, matcher, "faq_embed_stub")

    def test_an_answer_and_the_s1_fallback_counter(self):
        m = self.manager()
        state = m.initial_state("t", {})
        r = step(m, state, Utterance("What are your opening hours", source="typed"))
        self.assertIn("9 a.m.", r.reply)
        self.assertEqual(r.state.meta["faq_misses"], 0)
        for n in (1, 2):
            r = step(m, r.state, Utterance("zebra giraffe", source="typed"))
            self.assertEqual(r.state.meta["faq_misses"], n)
        r = step(m, r.state, Utterance("zebra giraffe", source="typed"))
        self.assertEqual([type(a).__name__ for a in r.actions], ["HandOff"])


class SelectionTest(unittest.TestCase):
    def test_zero_false_accepts_come_first_then_the_most_correct(self):
        # (best id, s1, s2, expected id) for in-scope; (best id, s1, s2) for out-of-scope
        inside = [("a", 0.90, 0.5, "a"), ("a", 0.80, 0.5, "a"), ("b", 0.86, 0.5, "c")]
        outside = [("a", 0.82, 0.5), ("b", 0.70, 0.5)]
        chosen = retrieval.choose(inside, outside)
        self.assertEqual(chosen["false_accepts"], 0)
        self.assertGreater(chosen["threshold"], 0.82)
        self.assertEqual(chosen["correct"], 1)   # only the 0.90 one passes the threshold that excludes 0.82

    def test_ties_go_to_the_larger_threshold_and_the_smaller_margin(self):
        chosen = retrieval.choose([("a", 0.9, 0.1, "a")], [])
        self.assertEqual((chosen["threshold"], chosen["margin"], chosen["correct"]), (0.9, 0.0, 1))


class HeldOutTest(unittest.TestCase):
    def test_the_module_never_names_a_held_out_field(self):
        with open(retrieval.__file__, encoding="utf-8") as f:
            source = f.read()
        for word in ("paraphrases", "asr_variants", "asr_text", "variants"):
            self.assertNotIn(word, source.replace("`faq_calibration.yaml`", ""), word)

    def test_the_calibration_files_load_and_use_new_wording(self):
        for domain in dataset.DOMAINS:
            for lang in dataset.LANGS:
                view = dataset.authoring_view(os.path.join(DEFAULT_DOMAINS_DIR, domain), lang)
                ids = {i for i, _, _ in view}
                canonical = {q.lower() for _, q, _ in view}
                inside, outside = retrieval.load_calibration(
                    os.path.join(DEFAULT_DOMAINS_DIR, domain, lang, "faq_calibration.yaml"))
                self.assertEqual({i for i, _ in inside}, ids, (domain, lang))
                texts = [t for _, t in inside] + outside
                self.assertFalse({t.lower() for t in texts} & canonical, (domain, lang))
                un = dataset.load_unanswerable(os.path.join(DEFAULT_DOMAINS_DIR, domain, lang, "faq_unanswerable.yaml"))
                self.assertFalse({t.lower() for t in outside} & {t.lower() for t in un}, "calibration is not the test list")

    def test_the_config_matches_the_calibration_files(self):
        config = retrieval.load_config()["models"]["e5-small"]
        for lang in dataset.LANGS:
            self.assertEqual(config[lang]["calibration_hash"], retrieval.calibration_hash(DEFAULT_DOMAINS_DIR, lang),
                             "the calibration files changed after the threshold was chosen")


@unittest.skipUnless(retrieval.available("e5-small"), "skipped, multilingual-e5-small is not in the local cache")
class ModelSmokeTest(unittest.TestCase):
    def test_the_canonical_question_retrieves_its_own_entry(self):
        for lang in dataset.LANGS:
            m = retrieval.embedding_matcher(DEFAULT_DOMAINS_DIR, "bank", lang, "e5-small")
            for faq_id, question, _ in dataset.authoring_view(os.path.join(DEFAULT_DOMAINS_DIR, "bank"), lang):
                pattern, _ = m.match(question)
                self.assertEqual(pattern.id if pattern else None, faq_id, (lang, question))


if __name__ == "__main__":
    unittest.main()
