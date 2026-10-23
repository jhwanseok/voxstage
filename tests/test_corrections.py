"""R9: read-back, corrections and the confusion table. Run: python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import EndCall, HandOff, step
from voxstage.evaluate import RecordingTools
from voxstage.rules.interpreter import CORRECTIONS, OFFER, READBACK, build_manager
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance
from voxstage.domain_pack import (PLACEHOLDER_KEYS, CorrectionPolicy, DomainPack, RuleError, load_confusions,
                                  load_correction, load_correction_policy, load_readback_slots, load_registry)

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


def write(tmp, name, text) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class FilesTest(unittest.TestCase):
    def test_readback_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, "r.yaml", "readback_slots:\n  amount: \"money('USD')\"\n  quantity: count\n")
            self.assertEqual(load_readback_slots(ok), {"amount": "money('USD')", "quantity": "count"})
            for bad in ("readback_slots:\n  amount: loud\n", "slots: {}\n", "readback_slots: [amount]\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_readback_slots(write(tmp, "r.yaml", bad))

    def test_corrections_and_confusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_correction(write(tmp, "c.yaml", "correction: {any_of: [wrong]}\n")).id, "correction")
            for bad in ("fix: {any_of: [wrong]}\n", "correction: [wrong]\n", "correction: {priority: 1}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_correction(write(tmp, "c.yaml", bad))
            table = load_confusions(write(tmp, "p.yaml", "pairs: [[13, 30], [15, 50]]\n"))
            self.assertEqual(table, {"13": "30", "30": "13", "15": "50", "50": "15"})
            for bad in ("pairs: [[13, 30], [30, 3]]\n", "pairs: [[13]]\n", "pairs: [[13, 13]]\n", "pairs: [[a, b]]\n",
                        "table: []\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_confusions(write(tmp, "p.yaml", bad))

    def test_correction_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_correction_policy(write(tmp, "c.yaml", "fallback: {}\n")), CorrectionPolicy(2, "handoff"))
            self.assertEqual(load_correction_policy(write(tmp, "c.yaml", "correction: {max_corrections: 1, on_exceed: end_call}\n")),
                             CorrectionPolicy(1, "end_call"))
            for bad in ("correction: {max: 1}\n", "correction: {max_corrections: -1}\n", "correction: {on_exceed: wait}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_correction_policy(write(tmp, "c.yaml", bad))

    def test_every_pack_has_the_r9_files(self):
        expected = {"bank": {"amount"}, "shop": {"quantity"}, "telecom": {"plan_gb"}}
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                pack = DomainPack.load(ROOT, d, lang)
                self.assertEqual(set(pack.readback), expected[d])
                self.assertIsNotNone(pack.correction)
                self.assertEqual(pack.confusions["13"], "30")
                for key in PLACEHOLDER_KEYS:
                    self.assertIn("{value}", pack.wording[key])

    def test_placeholder_wording_must_have_value(self):
        with open(os.path.join(ROOT, "bank", "en", "notices.yaml"), encoding="utf-8") as f:
            text = f.read().replace('readback: "{value}."', 'readback: "Got it."')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuleError) as cm:
                load_registry(write(tmp, "n.yaml", text))
        self.assertIn("readback", str(cm.exception))

    def test_a_pack_without_corrections_does_not_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(ROOT, "bank"), os.path.join(tmp, "bank"))
            os.remove(os.path.join(tmp, "bank", "en", "rules", "corrections.yaml"))
            with self.assertRaises(RuleError):
                DomainPack.load(tmp, "bank", "en")


def domain(name, lang):
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, name, "tools.yaml")))
    return build_manager(ROOT, name, lang, tools), tools


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class ReadBackTest(unittest.TestCase):
    def test_an_answer_is_read_back(self):
        m, _ = domain("bank", "en")
        _, r = talk(m, Utterance("I want to make a transfer"), Utterance("50"))
        self.assertEqual(r.reply, "$50. To which account, savings or checking?")
        self.assertEqual((r.trace["readback"], r.state.meta[READBACK]), (["amount"], "amount"))

    def test_a_capture_is_read_back(self):
        m, _ = domain("bank", "en")
        r, = talk(m, Utterance("Transfer thirteen dollars please"))
        self.assertEqual(r.reply, "$13. To which account, savings or checking?")

    def test_a_slot_not_listed_is_not_read_back(self):
        m, _ = domain("bank", "en")
        _, _, r = talk(m, Utterance("I want to make a transfer"), Utterance("50"), Utterance("savings"))
        self.assertTrue(r.reply.startswith("Shall I send"))
        self.assertNotIn("readback", r.trace)

    @unittest.skipUnless(kiwi_available(), "kiwipiepy missing")
    def test_korean_read_back(self):
        m, _ = domain("bank", "ko")
        r, = talk(m, Utterance("삼십 달러 이체해 주세요"))
        self.assertTrue(r.reply.startswith("30달러요."), r.reply)


class CorrectionTest(unittest.TestCase):
    def start(self, *more):
        m, tools = domain("bank", "en")
        return m, tools, talk(m, Utterance("Transfer thirteen dollars please"), *more)

    def test_one_new_value_replaces_the_read_back_slot(self):
        for words in ("No I said thirty dollars", "No not thirteen thirty", "That's wrong it's thirty dollars"):
            _, _, (_, r) = self.start(Utterance(words))
            self.assertEqual(r.state.slots, {"amount": "30"}, words)
            self.assertEqual(r.reply, "$30. To which account, savings or checking?", words)
            self.assertEqual((r.trace["correction"]["result"], r.state.node_id), ("30", "ask_to"))

    def test_other_slots_stay(self):
        m, _, (_, c, r) = self.start(Utterance("savings"), Utterance("No I said thirty dollars"))
        self.assertEqual(c.state.node_id, "confirm")
        self.assertEqual(r.state.slots, {"amount": "30", "to_account": "savings"})
        self.assertEqual(r.reply, "$30. Shall I send $30 to your savings account?")

    def test_a_bare_no_at_a_confirm_declines(self):
        _, tools, (_, _, r) = self.start(Utterance("savings"), Utterance("no"))
        self.assertEqual((r.state.node_id, tools.records), ("done", []))
        self.assertNotIn("correction", r.trace)

    def test_a_bare_no_at_an_ask_offers_the_partner(self):
        _, _, (_, r) = self.start(Utterance("no that's wrong"))
        self.assertEqual((r.reply, r.state.meta[OFFER]), ("Did you mean $30?", {"slot": "amount", "value": "30"}))
        for answer, expected in ((Utterance("yes"), "30"), (Dtmf("1"), "30")):
            _, _, (_, _, r) = self.start(Utterance("no that's wrong"), answer)
            self.assertEqual((r.state.slots["amount"], r.state.node_id), (expected, "ask_to"))
            self.assertNotIn(OFFER, r.state.meta)
        _, _, (_, _, r) = self.start(Utterance("no that's wrong"), Utterance("no"))
        self.assertEqual((r.state.node_id, r.reply, r.state.slots["amount"]),
                         ("ask_amount", "What amount would you like to transfer?", "13"))

    def test_odd_corrections_ask_the_slot_question_again(self):
        for words in ("No I said thirteen", "No not forty or fifty"):
            _, _, (_, r) = self.start(Utterance(words))
            self.assertEqual((r.state.node_id, r.trace["correction"]["result"]), ("ask_amount", "ask again"), words)
        _, _, (_, _, r) = self.start(Utterance("No I said thirteen"), Utterance("thirty"))
        self.assertEqual((r.state.slots, r.state.node_id), ({"amount": "30"}, "ask_to"))

    def test_without_a_number_partner_it_asks_again(self):
        m, _ = domain("bank", "en")
        _, r = talk(m, Utterance("Transfer two hundred dollars"), Utterance("no that's wrong"))
        self.assertEqual(r.state.node_id, "ask_amount")

    def test_the_correction_limit(self):
        m, _ = domain("bank", "en")
        *rs, r = talk(m, Utterance("Transfer thirteen dollars please"), Utterance("No I said thirty"),
                      Utterance("No I said forty"), Utterance("No I said fifty"))
        self.assertEqual([x.state.meta.get(CORRECTIONS, {}).get("amount") for x in rs[1:]], [1, 2])
        self.assertEqual(r.actions, (HandOff("correction_failed"),))

    def test_no_correction_without_a_read_back(self):
        m, _ = domain("bank", "en")
        _, r = talk(m, Utterance("I want to make a transfer"), Utterance("no not now"))
        self.assertNotIn("correction", r.trace)

    @unittest.skipUnless(kiwi_available(), "kiwipiepy missing")
    def test_korean_corrections(self):
        m, _ = domain("bank", "ko")
        _, r = talk(m, Utterance("십삼 달러 이체해 주세요"), Utterance("아니요 삼십 달러라고 했어요"))
        self.assertEqual(r.state.slots, {"amount": "30"})
        self.assertTrue(r.reply.startswith("30달러요."), r.reply)
        _, r = talk(m, Utterance("십삼 달러 이체해 주세요"), Utterance("십삼 말고 삼십 달러요 삼십"))
        self.assertEqual(r.state.slots, {"amount": "30"})


class C05FlowsTest(unittest.TestCase):
    """The misheard first turn (asr_text) and the correction, as in C05 noisy mode."""

    def test_shop_quantity(self):
        m, tools = domain("shop", "en")
        a, b = talk(m, Utterance("Change the quantity to fifty"), Utterance("No fifteen one five"))
        self.assertEqual((a.reply, a.state.slots), ("50. What is your order number?", {"quantity": "50"}))
        self.assertEqual((b.reply, b.state.slots), ("15. What is your order number?", {"quantity": "15"}))
        *_, r = talk(m, Utterance("Change the quantity to fifty"), Utterance("No fifteen one five"), Dtmf("1001"), Dtmf("1"))
        self.assertEqual([c["args"] for c in tools.records], [{"order_id": "1001", "quantity": "15"}])

    def test_telecom_plan_size_corrected_at_the_confirm(self):
        m, tools = domain("telecom", "en")
        a, b = talk(m, Utterance("I want the fourteen gigabyte plan"), Utterance("No forty not fourteen"))
        self.assertEqual(a.reply, "14. Shall I switch you to the 14 gigabyte plan?")
        self.assertEqual((b.reply, b.state.slots, tools.records),
                         ("40. Shall I switch you to the 40 gigabyte plan?", {"plan_gb": "40"}, []))

    @unittest.skipUnless(kiwi_available(), "kiwipiepy missing")
    def test_korean_shop_quantity(self):
        m, _ = domain("shop", "ko")
        a, b = talk(m, Utterance("수량을 오십 개로 바꿔 주세요"), Utterance("아니요 십오요 일 오 십오 개요"))
        self.assertEqual((a.state.slots, b.state.slots), ({"quantity": "50"}, {"quantity": "15"}))
        self.assertTrue(b.reply.startswith("15요."), b.reply)


if __name__ == "__main__":
    unittest.main()
