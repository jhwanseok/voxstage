"""Run: python -m unittest discover -s tests -v   (no pytest, no network, no GPU)"""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import metrics
from voxstage.endpointer import EnergyEndpointer
from voxstage.events import EventLog, read_events
from voxstage.make_audio import LEAD_S, SR, TAIL_S, last_active_s, synthetic_speech
from voxstage.pipeline import Pipeline, SentenceChunker
from voxstage.vendors import build


def make_clip(seconds=2.0, seed=0):
    speech = synthetic_speech(seconds, SR, seed)
    truth_end = LEAD_S + last_active_s(speech, SR)
    audio = np.concatenate([np.zeros(int(LEAD_S * SR), np.float32), speech,
                            np.zeros(int(TAIL_S * SR), np.float32)])
    return audio, truth_end


class EndpointerTest(unittest.TestCase):
    def test_t1_is_hangover_plus_small_quantization(self):
        audio, truth = make_clip()
        ep = EnergyEndpointer(hangover_ms=500)
        detected = ep.detect(audio, SR)
        t1_ms = (detected - truth) * 1000
        self.assertFalse(ep.last_clipped)
        self.assertGreaterEqual(t1_ms, 480)
        self.assertLessEqual(t1_ms, 560)

    def test_clipped_when_tail_shorter_than_hangover(self):
        audio, _ = make_clip()
        short = audio[: int((LEAD_S + 2.0 + 0.1) * SR)]
        ep = EnergyEndpointer(hangover_ms=500)
        ep.detect(short, SR)
        self.assertTrue(ep.last_clipped)


class ChunkerTest(unittest.TestCase):
    def test_splits_on_sentence_end_but_not_decimals(self):
        c = SentenceChunker(min_chars=4)
        out = []
        for piece in ["가격은 3.", "5달러입니다. ", "다음 문장이", "에요!"]:
            out += c.feed(piece)
        tail = c.flush()
        self.assertEqual(out[0], "가격은 3.5달러입니다.")
        self.assertEqual(out[1], "다음 문장이에요!")
        self.assertIsNone(tail)

    def test_short_sentences_merge_until_min_chars(self):
        c = SentenceChunker(min_chars=10)
        self.assertEqual(c.feed("네. "), [])
        self.assertEqual(c.feed("알겠습니다 지금 확인할게요. "), ["네. 알겠습니다 지금 확인할게요."])

    def test_trailing_period_waits_for_next_char(self):
        # A '.' at the very end of the buffer could be a decimal point, so it is held
        # back until the next character arrives (or flush). '!' and '?' cut immediately.
        c = SentenceChunker(min_chars=4)
        self.assertEqual(c.feed("확인했습니다."), [])
        self.assertEqual(c.feed(" 다음"), ["확인했습니다."])
        c2 = SentenceChunker(min_chars=4)
        self.assertEqual(c2.feed("확인했습니다!"), ["확인했습니다!"])


class EndToEndMockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def run_turns(self, n=6, warmup=1):
        log = EventLog(self.path)
        pipe = Pipeline(build("asr", "mock", time_scale=0.01), build("llm", "mock", time_scale=0.01),
                        build("tts", "mock", time_scale=0.01), log=log)
        audio, truth = make_clip()
        for i in range(warmup):
            pipe.run_turn("warm", i, audio, SR, truth, warmup=True)
        results = [pipe.run_turn("s1", i, audio, SR, truth) for i in range(n)]
        log.close()
        return results

    def test_all_segments_computed_and_consistent(self):
        results = self.run_turns()
        self.assertTrue(all(r.ok for r in results))
        events = read_events(self.path)
        computed = metrics.compute_turns(events)
        self.assertEqual(len(computed["turns"]), 6)
        self.assertEqual(computed["warmup_turns"], 1)
        self.assertEqual(computed["errors"], [])
        t = computed["turns"][0]
        for name in ("T1", "T2", "T3", "T3b", "T4", "E2E"):
            self.assertIn(name, t)
            self.assertGreaterEqual(t[name], 0)
        self.assertNotIn("T5", t)  # NullSink: playback is not measured
        # E2E must be explained by the attributed segments (small glue gaps only)
        self.assertLess(abs(t["unattributed"]), 20)
        self.assertGreater(t["E2E"], t["T1"])

    def test_report_files_written(self):
        self.run_turns()
        out = self.tmp.name
        summary = metrics.write_report(out)
        self.assertEqual(summary["n_ok"], 6)
        for f in ("summary.json", "report.md", "latency_hist.png"):
            self.assertTrue(os.path.exists(os.path.join(out, f)), f)
        with open(os.path.join(out, "report.md"), encoding="utf-8") as f:
            self.assertIn("p95", f.read())

    def test_failed_turn_is_recorded_not_raised(self):
        class BoomLLM(build("llm", "mock", time_scale=0.01).__class__):
            def stream(self, messages):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
                yield ""

        log = EventLog(self.path)
        pipe = Pipeline(build("asr", "mock", time_scale=0.01), BoomLLM(time_scale=0.01),
                        build("tts", "mock", time_scale=0.01), log=log)
        audio, truth = make_clip()
        res = pipe.run_turn("s1", 0, audio, SR, truth)
        log.close()
        self.assertFalse(res.ok)
        computed = metrics.compute_turns(read_events(self.path))
        self.assertEqual(len(computed["turns"]), 0)
        self.assertEqual(computed["errors"][0]["stage"], "llm")

    def test_events_are_valid_jsonl_with_monotonic_time(self):
        self.run_turns(n=2, warmup=0)
        rows = read_events(self.path)
        ts = [r["t"] for r in rows if r["session_id"] == "s1" and r["turn"] == 0]
        self.assertEqual(ts, sorted(ts))


if __name__ == "__main__":
    unittest.main()
