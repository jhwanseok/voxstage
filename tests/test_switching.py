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


if __name__ == "__main__":
    unittest.main()
