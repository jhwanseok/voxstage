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
from voxstage.rules.interpreter import FlowManager
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


if __name__ == "__main__":
    unittest.main()
