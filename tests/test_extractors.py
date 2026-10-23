"""R11: extractors that read spoken numbers, days, dates and times in flows. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback
from voxstage.rules.flows import FlowError, load_flows
from voxstage.domain_pack import WORDING_KEYS
from voxstage.evaluate import RecordingTools
from voxstage.rules.interpreter import ASK_MISSES, DATE_CHOICES, FlowManager, build_manager
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")
NOW = "2026-10-05T09:00:00"

FLOW = """
    id: plan
    triggers: {any_of: [plan]}
    captures: {when: {extractor: date}, window: {extractor: time_window}, count: {extractor: number}}
    start: ask_count
    nodes:
      ask_count: {type: ask, slot: count, prompt: "How many?", extractor: number, next: ask_code}
      ask_code: {type: ask, slot: code, prompt: "Your code?", extractor: digits, length: 4, next: ask_when}
      ask_when: {type: ask, slot: when, prompt: "When?", extractor: date, next: ask_day}
      ask_day: {type: ask, slot: day, prompt: "Which day of the month?", extractor: day, next: ask_from}
      ask_from: {type: ask, slot: start, prompt: "From which month?", extractor: month_start, next: ask_window}
      ask_window: {type: ask, slot: window, prompt: "Morning or afternoon?", extractor: time_window, next: done}
      done: {type: end}
"""


def build(tmp, flow=FLOW):
    with open(os.path.join(tmp, "plan.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(flow))
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), "", "", None,
                      AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset(),
                      missing_reply="Sorry, connecting you.")
    return FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), load_flows(tmp, BANK_TOOLS))


def talk(m, *inputs, now=NOW):
    state, out = m.initial_state("s", {"now": now} if now else None), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class ExtractorTest(unittest.TestCase):
    def test_every_new_extractor_in_one_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("a plan please"), Utterance("twenty five hundred"), Utterance("four eight two one"),
                         Utterance("on the fifteenth of next month"), Utterance("the twentieth"),
                         Utterance("starting next month"), Utterance("in the afternoon"))
        self.assertEqual(r.state.slots, {"count": "2500", "code": "4821", "when": "2026-11-15", "day": "20",
                                         "start": "2026-11-01", "window": "afternoon"})

    def test_captures_read_spoken_values_from_the_first_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            r, = talk(m, Utterance("a plan for two tomorrow morning"))
        self.assertEqual((r.state.slots, r.state.node_id),
                         ({"count": "2", "when": "2026-10-06", "window": "morning"}, "ask_code"))

    def test_keypad_digits_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("plan"), Dtmf("12"), Dtmf("4821"))
        self.assertEqual(r.state.slots, {"count": "12", "code": "4821"})

    def test_a_date_without_a_clock_fails_visibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, FLOW.replace("captures: {when: {extractor: date}, window", "captures: {window"))
            *_, r = talk(m, Utterance("plan"), Utterance("2"), Utterance("4821"), Utterance("tomorrow"), now=None)
        self.assertEqual((r.reply, r.actions), ("Sorry, connecting you.", (HandOff("missing_attribute"),)))

    def test_a_capture_without_a_clock_fails_visibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            r, = talk(m, Utterance("plan tomorrow"), now=None)
        self.assertEqual(r.actions, (HandOff("missing_attribute"),))

    def test_unknown_extractor_is_a_load_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "plan.yaml"), "w", encoding="utf-8") as f:
                f.write(textwrap.dedent(FLOW).replace("extractor: time_window, next", "extractor: hour, next"))
            with self.assertRaises(FlowError):
                load_flows(tmp, BANK_TOOLS)


WHEN = """
    id: plan
    triggers: {any_of: [plan]}
    start: ask_when
    nodes:
      ask_when: {type: ask, slot: when, prompt: "When?", extractor: date, next: done}
      done: {type: end}
"""


class AmbiguousDateTest(unittest.TestCase):
    def test_two_readings_are_named_and_not_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, WHEN)
            _, r = talk(m, Utterance("plan"), Utterance("next Tuesday"))
        self.assertEqual(r.reply, "Which date do you mean? 1: October 6, 2026, 2: October 13, 2026.")
        self.assertEqual((r.state.node_id, r.state.slots, r.state.meta.get(ASK_MISSES, 0)), ("ask_when", {}, 0))
        self.assertEqual(r.state.meta[DATE_CHOICES], ["2026-10-06", "2026-10-13"])
        self.assertIn("two readings", r.trace["rule"])

    def test_answered_by_keypad_or_by_one_of_the_dates(self):
        for answer, expected in ((Dtmf("2"), "2026-10-13"), (Dtmf("1"), "2026-10-06"),
                                 (Utterance("October 13"), "2026-10-13"), (Utterance("the 6th"), "2026-10-06")):
            with tempfile.TemporaryDirectory() as tmp:
                m = build(tmp, WHEN)
                *_, r = talk(m, Utterance("plan"), Utterance("next Tuesday"), answer)
            self.assertEqual(r.state.slots, {"when": expected}, answer)
            self.assertNotIn(DATE_CHOICES, r.state.meta)

    def test_another_date_or_nothing_follows_the_reprompt_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, WHEN)
            *_, a, b = talk(m, Utterance("plan"), Utterance("next Tuesday"), Utterance("on Friday"), Dtmf("3"))
        self.assertEqual((a.state.slots, a.state.meta[ASK_MISSES], a.reply), ({}, 1, "not valid. When?"))
        self.assertEqual((b.state.meta[ASK_MISSES], b.state.meta[DATE_CHOICES]), (2, ["2026-10-06", "2026-10-13"]))

    def test_one_reading_is_taken_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, WHEN)
            _, r = talk(m, Utterance("plan"), Utterance("next Monday"))
        self.assertEqual(r.state.slots, {"when": "2026-10-12"})

    def test_the_wording_is_required_everywhere(self):
        self.assertIn("date.ambiguous", WORDING_KEYS)
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                self.assertTrue(DomainPack.load(ROOT, d, lang).wording["date.ambiguous"])


def domain(name, lang):
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, name, "tools.yaml")))
    return build_manager(ROOT, name, lang, tools), tools


class C07FlowsTest(unittest.TestCase):
    CASES = [
        ("bank", "en", ["Schedule a transfer of twenty five hundred dollars for the fifteenth of next month", "savings"],
         "schedule_transfer", {"amount": "2500", "date": "2026-11-15", "to_account": "savings"}),
        ("shop", "en", ["Deliver two of them tomorrow morning"],
         "schedule_delivery", {"quantity": "2", "delivery_date": "2026-10-06", "delivery_window": "morning"}),
        ("telecom", "en", ["Move my bill date to the twentieth starting next month"],
         "change_bill_date", {"bill_day": "20", "effective_from": "2026-11-01"}),
        ("bank", "ko", ["다음 달 십오일에 이천오백 달러 예약 이체 걸어 주세요", "저축 계좌요"],
         "schedule_transfer", {"amount": "2500", "date": "2026-11-15", "to_account": "savings"}),
        ("shop", "ko", ["두 개 내일 오전에 보내 주세요"],
         "schedule_delivery", {"quantity": "2", "delivery_date": "2026-10-06", "delivery_window": "morning"}),
        ("telecom", "ko", ["다음 달부터 청구일을 이십 일로 바꿔 주세요"],
         "change_bill_date", {"bill_day": "20", "effective_from": "2026-11-01"}),
    ]

    def test_each_flow_confirms_then_calls_with_the_normalised_values(self):
        for name, lang, words, tool, args in self.CASES:
            if lang == "ko" and not kiwi_available():
                continue
            m, tools = domain(name, lang)
            *_, before, after = talk(m, *[Utterance(w) for w in words], Dtmf("1"))
            self.assertEqual(before.state.node_id, "confirm", (name, lang))
            self.assertEqual([(c["name"], c["args"]) for c in tools.records], [(tool, args)], (name, lang))


if __name__ == "__main__":
    unittest.main()
