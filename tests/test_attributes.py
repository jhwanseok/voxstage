"""R4: formatters, attribute sources, missing values, captures. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import DomainPack, Fallback
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, compile_template, load_flows
from voxstage.rules.formatters import FORMATTERS, FormatError, formatter
from voxstage.rules.interpreter import FlowManager, build_manager
from voxstage.rules.expr import MissingAttribute
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
needs_kiwi = unittest.skipUnless(kiwi_available(), "kiwipiepy missing: pip install 'voxstage[ko]'")
NAMES = frozenset({"n"})


def render(text, env=None, lang="en"):
    return compile_template(text, "t", NAMES).render({"_lang": lang, "result": {}, "customer": {}, **(env or {})})


class FormatterTest(unittest.TestCase):
    def test_money_count_date_in_both_languages(self):
        env = {"n": 1250, "result": {"fee": 5, "currency": "USD", "eta": "2026-10-08"}}
        self.assertEqual(render("{n | money('USD')}", env), "$1,250")
        self.assertEqual(render("{n | money('USD')}", env, "ko"), "1,250달러")
        self.assertEqual(render("{n | money('KRW')}", env), "1,250 won")
        self.assertEqual(render("{n | money('KRW')}", env, "ko"), "1,250원")
        self.assertEqual(render("{result.fee | money(result.currency)}", env), "$5")
        self.assertEqual(render("{12.5 | money('USD')}"), "$12.50")
        self.assertEqual(render("{n | count}", env), "1,250")
        self.assertEqual(render("{result.eta | date}", env), "October 8, 2026")
        self.assertEqual(render("{result.eta | date}", env, "ko"), "2026년 10월 8일")

    def test_bad_values_fail_visibly(self):
        for text, env in (("{n | money('EUR')}", {"n": 1}), ("{n | count}", {"n": "many"}),
                          ("{n | date}", {"n": "last tuesday"})):
            with self.assertRaises(FormatError, msg=text):
                render(text, env)

    def test_unknown_formatter_and_wrong_argument_count_fail_at_load(self):
        for bad in ("{n | shout}", "{n | money}", "{n | count(1)}", "{n | default}", "{n | default(1, 2)}",
                    "{n | }", "{n | money('USD') | default(1) | default(2)}"):
            with self.assertRaises(FlowError, msg=bad):
                compile_template(bad, "t", NAMES)

    def test_a_new_formatter_is_one_registered_function(self):
        @formatter("shout")
        def shout(value, lang):
            return str(value).upper()
        self.addCleanup(FORMATTERS.pop, "shout")
        self.assertEqual(render("{n | shout}", {"n": "hi"}), "HI")

    def test_filter_syntax_is_not_confused_by_quotes_or_pipes_in_text(self):
        self.assertEqual(render("{'a|b' | default('x')}"), "a|b")


class DefaultTest(unittest.TestCase):
    def test_a_missing_field_raises_unless_the_flow_gives_a_default(self):
        with self.assertRaises(MissingAttribute):
            render("{result.balance}")
        self.assertEqual(render("{result.balance | money('USD') | default('unknown')}"), "unknown")
        self.assertEqual(render("{result.balance | default(0)}"), "0")
        self.assertEqual(render("{result.balance | default(0)}", {"result": {"balance": 7}}), "7")


FLOWS = {
    "f": """
        id: f
        triggers: {any_of: [fee]}
        start: look
        nodes:
          look: {type: call, tool: get_transfer_fee, args: {amount: "5", grade: "{customer.grade}"}, on_ok: say, on_error: bad}
          say: {type: say, text: "Fee {result.fee | money(result.currency)}.", next: done}
          bad: {type: say, text: "no", next: done}
          done: {type: end}
    """,
    "g": """
        id: g
        triggers: {any_of: [plan]}
        captures: {plan: {extractor: choice, choices: {gold: g, silver: s}}}
        start: ask
        nodes:
          ask: {type: ask, slot: plan, prompt: "Which plan?", extractor: choice, choices: {gold: g, silver: s}, next: say}
          say: {type: say, text: "Plan {plan}.", next: done}
          done: {type: end}
    """,
}


def build(tmp, name, setup=None):
    with open(os.path.join(tmp, f"{name}.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(FLOWS[name]))
    tools = os.path.join(ROOT, "bank", "tools.yaml")
    flows = load_flows(tmp, tools)
    pack = DomainPack("bank", "en", {}, (), Fallback("s", "b"))
    m = FlowManager(pack, FakeApiExecutor.from_yaml(tools), flows)
    return m, m.initial_state("s", setup)


class MissingAttributeTest(unittest.TestCase):
    def test_request_meta_present_gives_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, s = build(tmp, "f", {"customer": {"grade": "gold"}})
            r = step(m, s, Utterance("what is the fee"))
            self.assertEqual((r.reply, r.actions), ("Fee $0.", ()))

    def test_request_meta_missing_apologises_and_hands_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, s = build(tmp, "f")
            r = step(m, s, Utterance("what is the fee"))
            self.assertEqual(r.reply, m.pack.missing_reply)
            self.assertEqual(r.actions, (HandOff("missing_attribute"),))
            self.assertIn("no field `grade`", r.trace["error"])
            self.assertEqual(r.trace["failed"], "look")

    def test_an_api_result_without_the_field_fails_the_same_way(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, s = build(tmp, "f", {"customer": {"grade": "unknown_grade"}})   # tool returns not_found
            r = step(m, s, Utterance("what is the fee"))
            self.assertEqual(r.reply, "no")   # the flow's own error branch, no invented number


class CaptureTest(unittest.TestCase):
    def test_capture_fills_the_slot_and_the_ask_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, s = build(tmp, "g")
            r = step(m, s, Utterance("tell me about the gold plan"))
            self.assertEqual((r.reply, r.state.slots), ("Plan g.", {"plan": "g"}))
            self.assertEqual(r.trace["skipped_asks"], ["ask"])

    def test_without_the_word_the_caller_is_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, s = build(tmp, "g")
            a = step(m, s, Utterance("which plan do I have"))
            self.assertEqual(a.reply, "Which plan?")
            b = step(m, a.state, Utterance("silver please"))
            self.assertEqual(b.reply, "Plan s.")

    def test_a_sensitive_slot_cannot_be_captured_from_speech(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = FLOWS["g"].replace("captures: {plan:", "captures: {birth_date:").replace("slot: plan", "slot: birth_date")
            with open(os.path.join(tmp, "g.yaml"), "w", encoding="utf-8") as f:
                f.write(textwrap.dedent(body))
            with self.assertRaises(FlowError):
                load_flows(tmp, os.path.join(ROOT, "bank", "tools.yaml"), frozenset({"birth_date"}))


def manager(domain, lang):
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, domain, "tools.yaml")))
    return build_manager(ROOT, domain, lang, tools), tools


def say(domain, lang, text, customer=None, *more):
    m, tools = manager(domain, lang)
    state = m.initial_state("s", {"customer": customer} if customer else None)
    r = step(m, state, Utterance(text))
    for t in more:
        r = step(m, r.state, Utterance(t))
    return r, tools


class ShippedFlowsTest(unittest.TestCase):
    def test_shop_shipping_fee_depends_on_tier(self):
        for tier, words in (("gold", "free"), ("basic", "$6")):
            r, tools = say("shop", "en", "How much is shipping", {"tier": tier})
            self.assertIn(words, r.reply)
            self.assertEqual(tools.records[0]["args"], {"tier": tier})

    def test_telecom_plan_price_uses_the_captured_plan_and_the_contract(self):
        for contract, price in (("yearly", "$20"), ("monthly", "$25")):
            r, tools = say("telecom", "en", "How much is the plus plan", {"contract": contract})
            self.assertIn(price, r.reply)
            self.assertEqual(tools.records[0]["args"], {"plan": "plus", "contract": contract})

    def test_bank_fee_with_digits_in_the_question(self):
        for grade, words in (("gold", "no fee"), ("basic", "$5")):
            r, tools = say("bank", "en", "What is the fee to transfer 500 dollars", {"grade": grade})
            self.assertIn(words, r.reply)
            self.assertEqual(tools.records[0]["args"], {"amount": "500", "grade": grade})

    def test_bank_fee_asks_when_the_amount_is_only_spoken_in_words(self):
        r, _ = say("bank", "en", "What is the fee if I transfer five hundred dollars", {"grade": "gold"})
        self.assertEqual(r.reply, "How much would you like to transfer?")   # spoken numbers arrive with R11

    def test_missing_customer_attribute_hands_off_in_a_shipped_flow(self):
        r, tools = say("shop", "en", "How much is shipping")
        self.assertEqual(r.actions, (HandOff("missing_attribute"),))
        self.assertEqual(tools.records, [])

    def test_lookup_flows_speak_formatted_values(self):
        r, _ = say("shop", "en", "where is my order", None, "1001")
        self.assertIn("October 8, 2026", r.reply)

    @needs_kiwi
    def test_korean_twins(self):
        r, _ = say("shop", "ko", "배송비 얼마예요", {"tier": "basic"})
        self.assertIn("6달러", r.reply)
        r, _ = say("shop", "ko", "배송비 얼마예요", {"tier": "gold"})
        self.assertIn("무료", r.reply)
        r, tools = say("telecom", "ko", "플러스 요금제는 얼마예요", {"contract": "yearly"})
        self.assertIn("20달러", r.reply)
        self.assertEqual(tools.records[0]["args"], {"plan": "plus", "contract": "yearly"})
        r, _ = say("bank", "ko", "500 달러 이체하면 수수료가 얼마예요", {"grade": "basic"})
        self.assertIn("5달러", r.reply)
        r, _ = say("shop", "ko", "제 주문 어디쯤 왔어요", None, "1001")
        self.assertIn("2026년 10월 8일", r.reply)


if __name__ == "__main__":
    unittest.main()
