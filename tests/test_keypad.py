"""R3: buttons, keypad input, sensitive slots and the re-prompt policy. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import EndCall, HandOff, step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, RuleError, load_ask_policy, load_sensitive_slots
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import ASK_MISSES, FlowManager
from voxstage.tools import FakeApiExecutor
from voxstage.turn import ButtonPress, Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")

POLICY = AskPolicy("not valid.", "use the keypad.", "giving up.", 2, "handoff")

FLOW = """
    id: {id}
    buttons: {buttons}
    triggers: {{any_of: [{word}]}}
    start: ask
    nodes:
      ask: {{type: ask, slot: {slot}, prompt: "Enter it.", extractor: {extractor}{length}, next: done}}
      done: {{type: end}}
"""


LEN = lambda e: ", length: 4" if e == "digits" else ""


def build(tmp, policy=POLICY, sensitive=frozenset(), slot="account_last4", extractor="digits", buttons="[menu]"):
    path = os.path.join(tmp, "f.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(FLOW.format(id="f", buttons=buttons, word="go", slot=slot, extractor=extractor, length=LEN(extractor))))
    flows = load_flows(tmp, BANK_TOOLS, frozenset(sensitive))
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), "", "", None, policy, frozenset(sensitive))
    return FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), flows)


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class ButtonTest(unittest.TestCase):
    def test_button_starts_the_flow_that_declares_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            r, = talk(m, ButtonPress("menu"))
            self.assertEqual((r.state.flow_id, r.state.node_id, r.reply), ("f", "ask", "Enter it."))
            self.assertEqual(r.trace["button"], "menu")

    def test_unknown_button_is_not_a_flow_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            r, = talk(m, ButtonPress("other"))
            self.assertIsNone(r.state.flow_id)

    def test_a_button_id_belongs_to_one_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a", "b"):
                with open(os.path.join(tmp, f"{name}.yaml"), "w", encoding="utf-8") as f:
                    f.write(textwrap.dedent(FLOW.format(id=name, buttons="[menu]", word=name, slot="s", extractor="text", length="")))
            with self.assertRaises(FlowError) as cm:
                load_flows(tmp, BANK_TOOLS)
            self.assertIn("menu", str(cm.exception))


class KeypadTest(unittest.TestCase):
    def test_digits_and_spoken_digits_both_fill_an_ordinary_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            for answer in (Dtmf("4821"), Utterance("it is 4821")):
                _, r = talk(m, ButtonPress("menu"), answer)
                self.assertEqual(r.state.slots, {"account_last4": "4821"})

    def test_sensitive_slot_rejects_speech_and_accepts_the_keypad(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, sensitive={"account_last4"})
            _, spoken, keyed = talk(m, ButtonPress("menu"), Utterance("4821"), Dtmf("4821"))
            self.assertEqual(spoken.reply, "use the keypad. Enter it.")
            self.assertEqual(spoken.state.slots, {})
            self.assertTrue(spoken.trace["keypad_only"])
            self.assertEqual(keyed.state.slots, {"account_last4": "4821"})

    def test_sensitive_slot_needs_the_digits_extractor_at_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FlowError) as cm:
                build(tmp, sensitive={"birth_date"}, slot="birth_date", extractor="text")
            self.assertIn("sensitive", str(cm.exception))


class RepromptTest(unittest.TestCase):
    def test_two_reprompts_then_hand_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, a, b, c = talk(m, ButtonPress("menu"), Dtmf("12"), Dtmf("ab"), Dtmf("1"))
            self.assertEqual((a.reply, a.actions), ("not valid. Enter it.", ()))
            self.assertEqual((b.reply, b.actions), ("not valid. Enter it.", ()))
            self.assertEqual((c.reply, c.actions), ("giving up.", (HandOff("input_failed"),)))
            self.assertEqual([x.state.meta[ASK_MISSES] for x in (a, b, c)], [1, 2, 3])

    def test_end_call_setting_and_custom_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, policy=AskPolicy("x.", "k.", "bye.", 0, "end_call"))
            _, a = talk(m, ButtonPress("menu"), Dtmf("1"))
            self.assertEqual((a.reply, a.actions), ("bye.", (EndCall(),)))

    def test_a_valid_answer_resets_the_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, a, ok = talk(m, ButtonPress("menu"), Dtmf("1"), Dtmf("4821"))
            self.assertEqual(a.state.meta[ASK_MISSES], 1)
            self.assertEqual(ok.state.meta[ASK_MISSES], 0)

    def test_speech_at_a_keypad_only_prompt_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, sensitive={"account_last4"})
            *_, last = talk(m, ButtonPress("menu"), Utterance("4821"), Utterance("4821"), Utterance("4821"))
            self.assertEqual((last.reply, last.actions), ("giving up.", (HandOff("input_failed"),)))

    def test_without_a_policy_the_prompt_is_simply_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, policy=None)
            _, a = talk(m, ButtonPress("menu"), Dtmf("1"))
            self.assertEqual((a.reply, a.actions), ("Enter it.", ()))


class ConfigFilesTest(unittest.TestCase):
    def write(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "c.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def test_ask_policy_is_validated(self):
        words = {"ask.invalid": "a", "ask.keypad_only": "b", "ask.exceed": "c"}
        good = "ask: {max_reprompts: 1, on_exceed: end_call}\n"
        self.assertEqual(load_ask_policy(self.write(good), words), AskPolicy("a", "b", "c", 1, "end_call"))
        for bad in ("ask: {max_reprompts: -1}\n", "ask: {on_exceed: hangup}\n", "ask: {extra: 1}\n",
                    "ask: {invalid_reply: a}\n"):
            with self.assertRaises(RuleError, msg=bad):
                load_ask_policy(self.write(bad), words)

    def test_sensitive_slots_file(self):
        self.assertEqual(load_sensitive_slots(self.write("sensitive_slots: [birth_date]\n")), frozenset({"birth_date"}))
        with self.assertRaises(RuleError):
            load_sensitive_slots(self.write("other: 1\n"))

    def test_shipped_domains_declare_both(self):
        for d in ("bank", "shop", "telecom"):
            pack = DomainPack.load(ROOT, d, "en")
            self.assertTrue(pack.sensitive_slots and pack.ask is not None, d)


if __name__ == "__main__":
    unittest.main()
