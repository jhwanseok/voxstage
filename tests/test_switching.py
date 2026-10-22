"""R6: interrupts, parking, declared carry-over and guards. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import ASK_MISSES, PARKED, FlowManager
from voxstage.tools import FakeApiExecutor
from voxstage.turn import ButtonPress, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")

POLICY = AskPolicy("not valid.", "use the keypad.", "giving up.", 2, "handoff")

# `lookup` asks for an order number; `cancel` and `lost` may break into it; `pay` has a guarded ask.
FLOWS = {
    "lookup": """
        id: lookup
        buttons: [menu_lookup]
        triggers: {any_of: [where]}
        start: ask_order
        nodes:
          ask_order: {type: ask, slot: order_id, prompt: "Order number?", extractor: digits, length: 4, next: ask_note}
          ask_note: {type: ask, slot: note, prompt: "Any note?", extractor: text, next: done}
          done: {type: end}
    """,
    "cancel": """
        id: cancel
        buttons: [menu_cancel]
        triggers: {any_of: [cancel]}
        interrupts: {priority: 1, any_of: [cancel]}
        carry: [order_id]
        start: ask_order
        nodes:
          ask_order: {type: ask, slot: order_id, prompt: "Which order to cancel?", extractor: digits, length: 4, next: say}
          say: {type: say, text: "Cancelling {order_id}.", next: done}
          done: {type: end, action: handoff, reason: cancel}
    """,
    "lost": """
        id: lost
        triggers: {all_of: [[card]], any_of: [lost]}
        interrupts: {priority: 5, all_of: [[card]], any_of: [lost]}
        start: say
        nodes:
          say: {type: say, text: "Reporting the lost card.", next: done}
          done: {type: end, action: handoff, reason: card_loss}
    """,
    "pay": """
        id: pay
        triggers: {any_of: [pay]}
        start: confirm
        nodes:
          confirm: {type: ask, slot: ok, prompt: "Confirm the payment?", extractor: choice, choices: [confirm, stop], interruptible: false, next: done}
          done: {type: end}
    """,
}


def write(tmp, flows):
    for name, text in flows.items():
        with open(os.path.join(tmp, f"{name}.yaml"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))


def build(tmp, flows=FLOWS):
    write(tmp, flows)
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), "", "", None, POLICY, frozenset())
    return FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), load_flows(tmp, BANK_TOOLS))


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


def load_error(tmp, text) -> str:
    write(tmp, {"x": text})
    with self_raises() as cm:
        load_flows(tmp, BANK_TOOLS)
    return str(cm.exception)


class self_raises:
    def __enter__(self):
        return self

    def __exit__(self, kind, exc, tb):
        if kind is None:
            raise AssertionError("no FlowError raised")
        if not issubclass(kind, FlowError):
            return False
        self.exception = exc
        return True


BASE = textwrap.dedent("""
    id: x
    triggers: {any_of: [x]}
    start: ask
    nodes:
      ask: {type: ask, slot: s, prompt: "?", extractor: text, next: done}
      done: {type: end}
""")


class LoadTest(unittest.TestCase):
    def test_interrupts_carry_and_guard_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, FLOWS)
            flows = load_flows(tmp, BANK_TOOLS)
        self.assertEqual(flows["cancel"].interrupts.priority, 1)
        self.assertEqual(flows["cancel"].carry, ("order_id",))
        self.assertIsNone(flows["lookup"].interrupts)
        self.assertFalse(flows["pay"].nodes["confirm"].data["interruptible"])
        self.assertTrue(flows["lookup"].nodes["ask_order"].data["interruptible"])

    def test_carry_names_a_slot_of_the_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = load_error(tmp, BASE + "carry: [order_id]\n")
        self.assertIn("order_id", msg)

    def test_carry_is_a_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("carry", load_error(tmp, BASE + "carry: s\n"))

    def test_interruptible_is_a_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = load_error(tmp, BASE.replace("extractor: text,", "extractor: text, interruptible: maybe,"))
        self.assertIn("interruptible", msg)

    def test_interrupts_is_a_valid_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("interrupts", load_error(tmp, BASE + "interrupts: {priority: 1}\n"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("interrupts", load_error(tmp, BASE + "interrupts: {any_of: [y], when: z}\n"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("interrupts", load_error(tmp, BASE + "interrupts: [y]\n"))


class SwitchTest(unittest.TestCase):
    def test_interrupt_switches_at_an_ask_and_parks_the_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("where is it"), Utterance("I lost my card"))
        self.assertEqual((r.state.flow_id, r.reply), ("lost", "Reporting the lost card."))
        self.assertEqual(r.trace["switch"], {"from": "lookup", "to": "lost", "by": "interrupt"})
        self.assertEqual(r.state.meta[PARKED], [{"flow": "lookup", "node": "ask_order", "slots": {}}])
        self.assertEqual(r.actions[0].reason, "card_loss")

    def test_plain_triggers_do_not_fire_inside_a_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("where is it"), Utterance("I want to pay"))
        self.assertEqual((r.state.flow_id, r.state.node_id), ("lookup", "ask_order"))
        self.assertNotIn("switch", r.trace)
        self.assertEqual(r.state.meta[ASK_MISSES], 1)

    def test_a_valid_answer_is_still_an_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("where is it"), Utterance("1234"))
        self.assertEqual((r.state.node_id, r.state.slots), ("ask_note", {"order_id": "1234"}))

    def test_interrupts_come_before_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)   # the text ask would take any words as the note
            _, _, r = talk(m, Utterance("where is it"), Utterance("1234"), Utterance("please cancel"))
        self.assertEqual(r.state.flow_id, "cancel")

    def test_no_switch_at_a_guarded_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("I want to pay"), Utterance("I lost my card"))
        self.assertEqual((r.state.flow_id, r.state.node_id), ("pay", "confirm"))
        self.assertNotIn(PARKED, r.state.meta)
        self.assertEqual(r.reply, "not valid. Confirm the payment?")

    def test_priority_then_specificity_with_ties_in_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("where is it"), Utterance("cancel it I lost my card"))
            self.assertEqual(r.state.flow_id, "lost")   # priority 5 beats 1
            self.assertEqual(r.trace["interrupt"]["priority"], 5)
        flows = dict(FLOWS, other="""
            id: other
            triggers: {any_of: [stop]}
            interrupts: {priority: 1, any_of: [cancel, stop]}
            start: say
            nodes:
              say: {type: say, text: "Other.", next: done}
              done: {type: end}
        """)
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, flows)
            _, r = talk(m, Utterance("where is it"), Utterance("cancel and stop"))
            self.assertEqual(r.state.flow_id, "other")   # same priority, two words beat one
            self.assertEqual(r.trace["interrupt"]["specificity"], 2)
            _, r = talk(m, Utterance("where is it"), Utterance("cancel"))
            self.assertEqual(r.trace["interrupt"]["ties"], ["other"])

    def test_declared_carry_copies_and_a_same_name_slot_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, _, r = talk(m, Utterance("where is it"), Utterance("1234"), Utterance("cancel it"))
        self.assertEqual(r.trace["carried"], {"order_id": "1234"})
        self.assertEqual(r.reply, "Cancelling 1234.")   # the ask for order_id is skipped
        flows = dict(FLOWS, cancel=FLOWS["cancel"].replace("carry: [order_id]", ""))
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp, flows)
            _, _, r = talk(m, Utterance("where is it"), Utterance("1234"), Utterance("cancel it"))
        self.assertEqual((r.trace["carried"], r.state.slots, r.reply), ({}, {}, "Which order to cancel?"))
        self.assertEqual(r.state.meta[PARKED][0]["slots"], {"order_id": "1234"})

    def test_parked_flows_stack_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("where is it"), Utterance("cancel it"), Utterance("I lost my card"))
        self.assertEqual([p["flow"] for p in r.state.meta[PARKED]], ["lookup", "cancel"])

    def test_after_a_switched_flow_ends_plain_triggers_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("where is it"), Utterance("I lost my card"), Utterance("I want to pay"))
        self.assertEqual(r.state.flow_id, "pay")

    def test_a_switch_resets_the_reprompt_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            *_, r = talk(m, Utterance("where is it"), Utterance("hmm"), Utterance("cancel it"))
        self.assertEqual(r.state.meta[ASK_MISSES], 0)


class ButtonSwitchTest(unittest.TestCase):
    def test_a_button_of_another_flow_switches_at_an_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("where is it"), ButtonPress("menu_cancel"))
        self.assertEqual(r.state.flow_id, "cancel")
        self.assertEqual(r.trace["switch"]["by"], "button")
        self.assertEqual(r.state.meta[PARKED][0]["flow"], "lookup")

    def test_the_own_button_and_unknown_buttons_are_invalid_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            for button in ("menu_lookup", "nothing"):
                _, r = talk(m, Utterance("where is it"), ButtonPress(button))
                self.assertEqual((r.state.flow_id, r.state.meta[ASK_MISSES]), ("lookup", 1))

    def test_no_button_switch_at_a_guarded_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build(tmp)
            _, r = talk(m, Utterance("I want to pay"), ButtonPress("menu_cancel"))
        self.assertEqual((r.state.flow_id, r.state.meta[ASK_MISSES]), ("pay", 1))


if __name__ == "__main__":
    unittest.main()
