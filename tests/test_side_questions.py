"""R7: FAQ side questions at an ask, resuming parked flows, the parked limit. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, RuleError, load_max_parked, parse_pattern
from voxstage.rules.faq import MISSES
from voxstage.rules.flows import load_flows
from voxstage.evaluate import RecordingTools
from voxstage.rules.interpreter import ASK_MISSES, PARKED, FlowManager, build_manager, decide
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")

needs_kiwi = unittest.skipUnless(kiwi_available(), "kiwipiepy missing: pip install 'voxstage[ko]'")

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
    "quick": """
        id: quick
        triggers: {any_of: [quickly]}
        interrupts: {priority: 1, any_of: [rate]}
        start: say
        nodes:
          say: {type: say, text: "The rate is 2 percent.", next: done}
          done: {type: end}
    """,
    "agent": """
        id: agent
        triggers: {any_of: [human]}
        interrupts: {priority: 1, any_of: [agent]}
        start: say
        nodes:
          say: {type: say, text: "Connecting you.", next: done}
          done: {type: end, action: handoff, reason: asked}
    """,
    "help": """
        id: help
        triggers: {any_of: [helpdesk]}
        interrupts: {priority: 1, any_of: [help]}
        start: ask_topic
        nodes:
          ask_topic: {type: ask, slot: topic, prompt: "Help with what?", extractor: choice, choices: [cards, loans], next: done}
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

    def test_spoken_digits_at_a_keypad_only_prompt_get_the_reminder_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("pin"), Utterance("it is 1234, and when do you open"))
        self.assertEqual(r.reply, "use the keypad. We open at 9. Enter your phone number.")
        self.assertEqual((r.trace["decided"], r.state.slots, r.state.meta.get(ASK_MISSES, 0)), ("side_question", {}, 0))

    def test_keypad_input_is_not_an_faq_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("transfer"), Dtmf("12"))
        self.assertEqual((r.trace["faq"], r.state.slots), (None, {"amount": "12"}))


class ResumeTest(unittest.TestCase):
    def test_after_an_action_less_end_the_parked_flow_asks_again_with_its_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("transfer"), Utterance("50"), Utterance("what is the rate"))
        self.assertEqual(r.reply, "The rate is 2 percent. To which account?")
        self.assertEqual((r.state.flow_id, r.state.node_id, r.state.slots), ("transfer", "ask_to", {"amount": "50"}))
        self.assertEqual((r.trace["resumed"], r.state.meta[PARKED]), ({"flow": "transfer", "node": "ask_to"}, []))
        self.assertEqual(r.actions, ())

    def test_the_resumed_flow_takes_its_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("transfer"), Utterance("50"), Utterance("what is the rate"), Utterance("savings"))
        self.assertEqual(r.state.slots, {"amount": "50", "to_account": "savings"})

    def test_newest_parked_flow_resumes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, a, b = talk(m, Utterance("transfer"), Utterance("I need help"), Utterance("what is the rate"),
                            Utterance("loans"))
        self.assertEqual((a.state.flow_id, a.reply), ("help", "The rate is 2 percent. Help with what?"))
        self.assertEqual((b.state.flow_id, b.state.node_id), ("transfer", "ask_amount"))   # help ended: back again
        self.assertEqual(b.reply, "How much?")

    def test_a_hand_off_drops_every_parked_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("transfer"), Utterance("I need help"), Utterance("get me an agent"))
        self.assertEqual(r.trace["parked_dropped"], ["transfer", "help"])
        self.assertEqual((r.state.meta[PARKED], r.state.flow_id, r.reply), ([], "agent", "Connecting you."))


class ParkedLimitTest(unittest.TestCase):
    def test_beyond_the_limit_the_oldest_is_dropped_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, max_parked=1)
            *_, r = talk(m, Utterance("transfer"), Utterance("I need help"), Utterance("what is the rate"))
        self.assertEqual(r.trace["parked_dropped"], ["transfer"])
        self.assertEqual(r.reply, "The rate is 2 percent. Help with what?")   # help resumes, transfer is gone
        self.assertEqual((r.state.flow_id, r.state.meta[PARKED]), ("help", []))

    def test_within_the_limit_nothing_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, max_parked=2)
            *_, r = talk(m, Utterance("transfer"), Utterance("I need help"), Utterance("what is the rate"))
        self.assertNotIn("parked_dropped", r.trace)
        self.assertEqual([p["flow"] for p in r.state.meta[PARKED]], ["transfer"])

    def test_switch_config(self):
        cases = {"fallback: {max_misses: 3}\n": 2,
                 "fallback: {max_misses: 3}\nswitch: {max_parked: 3}\n": 3}
        bad = ["fallback: {max_misses: 3}\nswitch: {max_parked: 0}\n",
               "fallback: {max_misses: 3}\nswitch: {max_parked: two}\n",
               "fallback: {max_misses: 3}\nswitch: {depth: 2}\n",
               "fallback: {max_misses: 3}\nswitch: [2]\n"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.yaml")
            for text, n in cases.items():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.assertEqual(load_max_parked(path), n)
            for text in bad:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                with self.assertRaises(RuleError):
                    load_max_parked(path)

    def test_every_domain_sets_the_limit(self):
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                self.assertEqual(load_max_parked(os.path.join(ROOT, d, lang, "rules", "config.yaml")), 2)


def domain(name, lang, tools=None):
    tools = tools or FakeApiExecutor.from_yaml(os.path.join(ROOT, name, "tools.yaml"))
    return build_manager(ROOT, name, lang, tools)


class DomainContentTest(unittest.TestCase):
    def test_transfer_calls_make_transfer_with_both_slots(self):
        tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, "bank", "tools.yaml")))
        *_, c, r = talk(domain("bank", "en", tools), Utterance("I want to make a transfer"), Utterance("50"),
                        Utterance("savings"), Utterance("yes"))
        self.assertEqual(c.reply, "Shall I send $50 to your savings account?")   # risky: confirmed first (R7-12)
        self.assertEqual([(c["name"], c["args"]) for c in tools.records],
                         [("make_transfer", {"amount": "50", "to_account": "savings"})])
        self.assertIn("TR1001", r.reply)

    def test_bank_c02_first_two_turns(self):
        a, b = talk(domain("bank", "en"), Utterance("I want to make a transfer"), Utterance("Wait what time do you close"))
        self.assertEqual(a.state.flow_id, "transfer")
        self.assertIn("amount", a.reply)
        self.assertIn("9 a.m. to 4 p.m.", b.reply)
        self.assertEqual((b.state.flow_id, b.state.node_id, b.trace["decided"]), ("transfer", "ask_amount", "side_question"))

    def test_return_request_both_orders(self):
        m = domain("shop", "en")
        r, = talk(m, Utterance("I want to return a laptop"))
        self.assertIn(m.pack.notices[0].text, r.reply)
        self.assertTrue(r.reply.endswith("What is your order number?"))
        a, b, c = talk(m, Utterance("I want to return an item"), Dtmf("1001"), Utterance("a laptop"))
        self.assertEqual((a.reply, b.reply), ("What is your order number?", "What would you like to return?"))
        self.assertIn(m.pack.notices[0].text, c.reply)
        self.assertEqual(c.state.slots, {"order_id": "1001", "item": "electronics"})

    def test_change_plan_with_and_without_captures(self):
        m = domain("telecom", "en")
        r, = talk(m, Utterance("I want to downgrade to the basic plan"))
        self.assertEqual(r.state.slots, {"plan": "basic", "direction": "downgrade"})
        self.assertIn(m.pack.notices[0].text, r.reply)
        a, b = talk(m, Utterance("I want to change my plan"), Utterance("The plus plan"))
        self.assertEqual(a.reply, "Which plan would you like, basic or plus?")
        self.assertEqual((b.state.slots, b.state.node_id), ({"plan": "plus"}, "ask_direction"))

    @needs_kiwi
    def test_korean_twins(self):
        a, b, c = talk(domain("shop", "ko"), Utterance("반품하고 싶은데요"), Utterance("아 잠깐만요 근데 배송은 보통 며칠 걸려요"), Dtmf("1001"))
        self.assertIn("주문번호", a.reply)
        self.assertEqual(b.trace["decided"], "side_question")
        self.assertEqual(c.state.slots, {"order_id": "1001"})
        tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, "bank", "tools.yaml")))
        *_, c, r = talk(domain("bank", "ko", tools), Utterance("이체하려고 하는데요"), Utterance("50"),
                        Utterance("저축 계좌로요"), Utterance("네"))
        self.assertIn("저축 계좌로 보낼까요", c.reply)
        self.assertIn("저축 계좌로 보냈습니다", r.reply)
        *_, r = talk(domain("bank", "ko", tools), Utterance("이체하려고 하는데요"), Utterance("50"),
                     Utterance("입출금 계좌요"), Utterance("아니요 취소할게요"))
        self.assertEqual((r.reply, len(tools.records)), ("알겠습니다. 진행하지 않았어요.", 1))


if __name__ == "__main__":
    unittest.main()
