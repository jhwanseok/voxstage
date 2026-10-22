"""R7: FAQ side questions at an ask, resuming parked flows, the parked limit. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, parse_pattern
from voxstage.rules.faq import MISSES
from voxstage.rules.flows import load_flows
from voxstage.rules.interpreter import ASK_MISSES, PARKED, FlowManager, decide
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")

POLICY = AskPolicy("not valid.", "use the keypad.", "giving up.", 2, "handoff")
ANSWERS = {"hours": "We open at 9.", "fee": "Transfers cost 5 dollars."}
PATTERNS = (parse_pattern("t", {"id": "hours", "any_of": ["open", "close"]}),
            parse_pattern("t", {"id": "fee", "any_of": ["fee"]}))

FLOWS = {
    "transfer": """
        id: transfer
        triggers: {any_of: [transfer]}
        start: ask_amount
        nodes:
          ask_amount: {type: ask, slot: amount, prompt: "How much?", extractor: number, next: ask_to}
          ask_to: {type: ask, slot: to_account, prompt: "To which account?", extractor: choice, choices: [savings, checking], next: done}
          done: {type: end}
    """,
    "pin": """
        id: pin
        triggers: {any_of: [pin]}
        start: ask_pin
        nodes:
          ask_pin: {type: ask, slot: phone_number, prompt: "Enter your phone number.", extractor: digits, length: 4, next: done}
          done: {type: end}
    """,
}


def write(tmp, flows):
    for name, text in flows.items():
        with open(os.path.join(tmp, f"{name}.yaml"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))


def build(tmp, flows=FLOWS, faq=True, max_parked=2):
    write(tmp, flows)
    sensitive = frozenset({"phone_number"})
    pack = DomainPack("bank", "en", ANSWERS if faq else {}, PATTERNS if faq else (), Fallback("sorry", "bye"),
                      "", "", None, POLICY, sensitive, max_parked=max_parked)
    return FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), load_flows(tmp, BANK_TOOLS, sensitive))


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class DecideTest(unittest.TestCase):
    def test_answer_wins_then_side_question_then_reprompt(self):
        faq = PATTERNS[0]
        self.assertEqual(decide("50", faq), "answer")
        self.assertEqual(decide("50", None), "answer")
        self.assertEqual(decide(None, faq), "side_question")
        self.assertEqual(decide(None, None), "reprompt")


class SideQuestionTest(unittest.TestCase):
    def test_faq_answer_then_the_pending_question_and_nothing_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, a, r = talk(m, Utterance("transfer"), Utterance("50"), Utterance("when do you close"))
        self.assertEqual(r.reply, "We open at 9. To which account?")
        self.assertEqual((r.state.flow_id, r.state.node_id, r.state.slots), ("transfer", "ask_to", {"amount": "50"}))
        self.assertEqual((r.trace["decided"], r.trace["faq"], r.trace["extracted"]), ("side_question", "hours", None))
        self.assertEqual(r.state.meta, a.state.meta)   # neither the ask nor the FAQ miss counter moved

    def test_a_side_question_does_not_count_as_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, miss, side = talk(m, Utterance("transfer"), Utterance("hmm"), Utterance("is there a fee"))
        self.assertEqual(miss.state.meta[ASK_MISSES], 1)
        self.assertEqual(side.state.meta[ASK_MISSES], 1)
        self.assertNotIn(MISSES, side.state.meta)

    def test_an_answer_that_also_matches_the_faq_is_an_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("transfer"), Utterance("50 dollars, is there a fee"))
        self.assertEqual((r.trace["decided"], r.trace["faq"], r.state.slots), ("answer", "fee", {"amount": "50"}))
        self.assertEqual(r.reply, "To which account?")

    def test_no_answer_and_no_faq_is_a_reprompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("transfer"), Utterance("hmm"))
        self.assertEqual((r.trace["decided"], r.reply), ("reprompt", "not valid. How much?"))

    def test_without_faq_rules_it_is_a_reprompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, faq=False)
            _, r = talk(m, Utterance("transfer"), Utterance("when do you close"))
        self.assertEqual((r.trace["decided"], r.trace["faq"]), ("reprompt", None))

    def test_keypad_only_prompt_still_answers_a_side_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r, d = talk(m, Utterance("pin"), Utterance("when do you open"), Dtmf("1234"))
        self.assertEqual(r.reply, "We open at 9. Enter your phone number.")
        self.assertEqual(d.state.slots, {"phone_number": "1234"})

    def test_keypad_input_is_not_an_faq_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("transfer"), Dtmf("12"))
        self.assertEqual((r.trace["faq"], r.state.slots), (None, {"amount": "12"}))


if __name__ == "__main__":
    unittest.main()
