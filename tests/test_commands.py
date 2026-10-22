"""R8: global commands cancel, back and agent. Run: python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import (COMMANDS, WORDING_KEYS, AskPolicy, DomainPack, Fallback, RuleError, load_commands,
                                  parse_pattern)
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import ASK_MISSES, ASKED, MAIN_MENU, PARKED, FlowManager, build_manager
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")


def write(tmp, text) -> str:
    path = os.path.join(tmp, "commands.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text))
    return path


class CommandsFileTest(unittest.TestCase):
    def test_exactly_three_commands_as_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, "cancel: {any_of: [cancel]}\nback: {any_of: [back]}\nagent: {any_of: [agent], priority: 2}\n")
            cancel, back, agent = load_commands(ok)
            self.assertEqual((cancel.id, back.id, agent.id, agent.priority), ("cancel", "back", "agent", 2))
            for bad in ("cancel: {any_of: [x]}\nback: {any_of: [y]}\n",
                        "cancel: {any_of: [x]}\nback: {any_of: [y]}\nagent: {any_of: [z]}\nhelp: {any_of: [h]}\n",
                        "cancel: [x]\nback: {any_of: [y]}\nagent: {any_of: [z]}\n",
                        "cancel: {priority: 1}\nback: {any_of: [y]}\nagent: {any_of: [z]}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_commands(write(tmp, bad))

    def test_every_pack_has_commands_and_their_wording(self):
        self.assertTrue({"command.cancelled", "command.agent"} <= set(WORDING_KEYS))
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                pack = DomainPack.load(ROOT, d, lang)
                self.assertEqual(tuple(p.id for p in pack.commands), COMMANDS)
                self.assertTrue(pack.wording["command.cancelled"] and pack.wording["command.agent"])

    def test_a_pack_without_commands_does_not_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(ROOT, "bank"), os.path.join(tmp, "bank"))
            os.remove(os.path.join(tmp, "bank", "en", "rules", "commands.yaml"))
            with self.assertRaises(RuleError):
                DomainPack.load(tmp, "bank", "en")

    def test_main_menu_is_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "main_menu.yaml"), "w", encoding="utf-8") as f:
                f.write("id: main_menu\ntriggers: {any_of: [menu]}\nstart: done\nnodes:\n  done: {type: end}\n")
            with self.assertRaises(FlowError) as cm:
                load_flows(tmp, BANK_TOOLS)
        self.assertIn("reserved", str(cm.exception))


TOOLS = """
tools:
  pay:
    params: [amount, to]
    risky: true
    default: {return: {reference: R1}}
"""

FLOWS = {
    "pay": """
        id: pay
        triggers: {any_of: [pay]}
        start: ask_amount
        nodes:
          ask_amount: {type: ask, slot: amount, prompt: "How much?", extractor: number, next: intro}
          intro: {type: say, text: "Noted.", next: ask_to}
          ask_to: {type: ask, slot: to, prompt: "To whom?", extractor: text, next: check}
          check: {type: confirm, prompt: "Pay {amount} to {to}?", on_yes: call, on_no: done}
          call: {type: call, tool: pay, args: {amount: "{amount}", to: "{to}"}, on_ok: done, on_error: done}
          done: {type: end}
    """,
    "lost": """
        id: lost
        triggers: {any_of: [lost]}
        interrupts: {priority: 9, any_of: [lost, cancel]}
        start: ask_card
        nodes:
          ask_card: {type: ask, slot: card, prompt: "Which card?", extractor: digits, length: 4, next: done}
          done: {type: end}
    """,
}

COMMAND_PATTERNS = tuple(parse_pattern("t", {"id": n, "any_of": w}) for n, w in
                         (("cancel", ["cancel", "never mind"]), ("back", ["go back"]), ("agent", ["agent"])))
WORDING = {"command.cancelled": "Cancelled.", "command.agent": "Connecting.", "flow.no_flow": "Nothing to do.",
           "confirm.declined": "Not done."}


def build(tmp, commands=COMMAND_PATTERNS):
    with open(os.path.join(tmp, "tools.yaml"), "w", encoding="utf-8") as f:
        f.write(TOOLS)
    flows_dir = os.path.join(tmp, "flows")
    os.makedirs(flows_dir)
    for name, text in FLOWS.items():
        with open(os.path.join(flows_dir, f"{name}.yaml"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text))
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), "", "", None,
                      AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset(),
                      wording=WORDING, confirm_words=(("yes",), ("no",)), commands=commands)
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(tmp, "tools.yaml")))
    return FlowManager(pack, tools, load_flows(flows_dir, os.path.join(tmp, "tools.yaml"))), tools


def talk(m, *inputs, setup=None):
    state, out = m.initial_state("s", setup), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class CancelTest(unittest.TestCase):
    def test_cancel_clears_the_talk_and_keeps_the_request(self):
        setup = {"customer": {"grade": "gold"}, "now": "2026-10-22"}
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("hmm"), Utterance("never mind"), setup=setup)
        self.assertEqual((r.reply, r.state.flow_id, r.state.node_id, r.state.slots), ("Cancelled.", MAIN_MENU, None, {}))
        self.assertEqual(r.state.meta, setup)
        self.assertEqual(r.actions, ())

    def test_cancel_drops_parked_flows_without_resuming(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, a, r = talk(m, Utterance("pay"), Utterance("I lost it"), Utterance("cancel"))
        self.assertEqual(a.state.flow_id, "lost")
        self.assertEqual((r.state.flow_id, r.trace["parked_dropped"], r.state.meta.get(PARKED)), (MAIN_MENU, ["pay"], None))

    def test_cancel_at_a_confirm_calls_no_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, c, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("Ann"), Utterance("cancel"))
        self.assertEqual(c.state.node_id, "check")
        self.assertEqual((r.state.flow_id, tools.records), (MAIN_MENU, []))

    def test_after_cancel_the_next_words_start_as_at_the_beginning(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("cancel"), Utterance("pay"))
        self.assertEqual((r.state.flow_id, r.state.node_id), ("pay", "ask_amount"))

    def test_cancel_outside_a_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            r, = talk(m, Utterance("cancel"))
        self.assertEqual((r.reply, r.state.flow_id), ("Cancelled.", MAIN_MENU))

    def test_commands_come_before_interrupts(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("pay"), Utterance("cancel"))   # `lost` interrupts on cancel too
        self.assertEqual((r.state.flow_id, r.trace["command"]), (MAIN_MENU, "cancel"))
        self.assertNotIn("switch", r.trace)

    def test_keypad_input_is_never_a_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("pay"), Dtmf("50"))
        self.assertEqual(r.state.slots, {"amount": "50"})


class AgentTest(unittest.TestCase):
    def test_agent_hands_off_and_drops_parked_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("I lost it"), Utterance("get me an agent"))
        self.assertEqual((r.reply, r.actions), ("Connecting.", (HandOff("caller_request"),)))
        self.assertEqual((r.trace["parked_dropped"], r.state.meta[PARKED]), (["pay"], []))
        self.assertEqual(tools.records, [])


class BackTest(unittest.TestCase):
    def test_back_asks_the_previous_question_with_the_slot_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, a, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("go back"))
        self.assertEqual(a.reply, "Noted. To whom?")
        self.assertEqual((r.reply, r.state.node_id, r.state.slots), ("How much?", "ask_amount", {"amount": "50"}))
        self.assertEqual((r.trace["back_to"], r.state.meta[ASKED]), ("ask_amount", []))

    def test_the_new_answer_replaces_the_old_and_the_flow_goes_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("go back"), Utterance("70"))
        self.assertEqual((r.state.slots, r.state.node_id, r.reply), ({"amount": "70"}, "ask_to", "Noted. To whom?"))

    def test_back_at_a_confirm_goes_to_the_last_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("Ann"), Utterance("go back"))
        self.assertEqual((r.state.node_id, r.reply, tools.records), ("ask_to", "To whom?", []))

    def test_back_twice_walks_back_two_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("Ann"), Utterance("go back"), Utterance("go back"))
        self.assertEqual(r.state.node_id, "ask_amount")

    def test_back_at_the_first_question_asks_it_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("pay"), Utterance("go back"))
        self.assertEqual((r.state.node_id, r.reply, r.state.meta[ASK_MISSES]), ("ask_amount", "How much?", 0))

    def test_back_outside_a_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            r, = talk(m, Utterance("go back"))
        self.assertEqual((r.reply, r.state.flow_id), ("Nothing to do.", None))

    def test_history_belongs_to_its_flow_across_a_switch_and_a_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, s, back_in_lost = talk(m, Utterance("pay"), Utterance("50"), Utterance("lost"), Utterance("go back"))
            self.assertEqual((s.state.meta[ASKED], s.state.meta[PARKED][0]["asked"]), ([], ["ask_amount"]))
            self.assertEqual(back_in_lost.state.node_id, "ask_card")   # nothing answered in `lost` yet
            *_, resumed, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("lost"), Dtmf("1234"), Utterance("go back"))
        self.assertEqual((resumed.state.node_id, resumed.state.meta[ASKED]), ("ask_to", ["ask_amount"]))
        self.assertEqual(r.state.node_id, "ask_amount")


def domain(name, lang):
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, name, "tools.yaml")))
    return build_manager(ROOT, name, lang, tools), tools


class DomainCommandTest(unittest.TestCase):
    def test_change_address_back_then_agent(self):
        m, tools = domain("shop", "en")
        a, b, c, d = talk(m, Utterance("I want to change my delivery address"), Dtmf("1001"), Utterance("Go back"),
                          Utterance("I'd rather speak to a person"))
        self.assertEqual((a.state.flow_id, b.reply), ("change_address", "What is the new delivery address?"))
        self.assertEqual((c.state.node_id, c.state.slots), ("ask_order", {"order_id": "1001"}))
        self.assertEqual((d.actions, tools.records), ((HandOff("caller_request"),), []))

    def test_change_address_confirms_before_the_update(self):
        m, tools = domain("shop", "en")
        *_, c, r = talk(m, Utterance("I want to change my delivery address"), Dtmf("1001"), Utterance("12 Oak Street"),
                        Utterance("yes"))
        self.assertIn("12 Oak Street", c.reply)
        self.assertEqual([x["args"] for x in tools.records], [{"order_id": "1001", "address": "12 Oak Street"}])

    def test_shop_cancel_with_an_order_reference_goes_to_cancel_order(self):
        m, _ = domain("shop", "en")
        _, r = talk(m, Utterance("Where is my order"), Utterance("Actually I want to cancel it"))
        self.assertEqual(r.state.flow_id, "cancel_order")
        _, r = talk(m, Utterance("Where is my order"), Utterance("never mind"))
        self.assertEqual(r.state.flow_id, MAIN_MENU)

    def test_bank_cancel_then_agent(self):
        m, _ = domain("bank", "en")
        _, b, c = talk(m, Utterance("I want to make a transfer"), Utterance("Actually forget it cancel that"),
                       Utterance("Can I talk to a real person"))
        self.assertEqual((b.state.flow_id, b.state.slots, b.actions), (MAIN_MENU, {}, ()))
        self.assertEqual(c.actions, (HandOff("caller_request"),))

    @unittest.skipUnless(kiwi_available(), "kiwipiepy missing")
    def test_korean_commands(self):
        m, _ = domain("telecom", "ko")
        _, b, c = talk(m, Utterance("요금제 변경하려고요"), Utterance("아 됐어요 그냥 안 할게요"), Utterance("상담원 연결해 주세요"))
        self.assertEqual((b.state.flow_id, c.actions), (MAIN_MENU, (HandOff("caller_request"),)))
        m, _ = domain("shop", "ko")
        _, _, c = talk(m, Utterance("배송지 좀 바꾸려고요"), Dtmf("1001"), Utterance("아 뒤로 갈게요"))
        self.assertEqual((c.state.node_id, c.state.slots), ("ask_order", {"order_id": "1001"}))
        _, r = talk(m, Utterance("제 주문 어디쯤 왔어요"), Utterance("아 그냥 그거 취소할게요"))
        self.assertEqual(r.state.flow_id, "cancel_order")


if __name__ == "__main__":
    unittest.main()
