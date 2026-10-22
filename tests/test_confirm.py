"""R7b: confirmation before risky actions. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, parse_pattern
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, load_flows, risky_tools
from voxstage.rules.interpreter import FlowManager
from voxstage.tools import FakeApiExecutor
from voxstage.turn import ButtonPress, Dtmf, Utterance

TOOLS = """
tools:
  pay:
    params: [amount]
    risky: true
    default: {return: {reference: R1}}
  look:
    params: [amount]
    default: {return: {ok: true}}
"""


def setup_dir(tmp, flow: str) -> str:
    tools = os.path.join(tmp, "tools.yaml")
    with open(tools, "w", encoding="utf-8") as f:
        f.write(TOOLS)
    flows = os.path.join(tmp, "flows")
    os.makedirs(flows)
    with open(os.path.join(flows, "f.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(flow))
    return flows, tools


def load_error(flow: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        flows, tools = setup_dir(tmp, flow)
        try:
            load_flows(flows, tools)
        except FlowError as exc:
            return str(exc)
    raise AssertionError("no FlowError raised")


UNCONFIRMED = """
    id: f
    triggers: {any_of: [pay]}
    start: ask
    nodes:
      ask: {type: ask, slot: amount, prompt: "How much?", extractor: number, next: call}
      call: {type: call, tool: pay, args: {amount: "{amount}"}, on_ok: done, on_error: done}
      done: {type: end}
"""


class RiskyToolTest(unittest.TestCase):
    def test_risky_is_read_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, tools = setup_dir(tmp, UNCONFIRMED)
            self.assertEqual(risky_tools(tools), frozenset({"pay"}))
        with self.assertRaises(ValueError):
            FakeApiExecutor({"tools": {"t": {"params": [], "risky": "yes", "default": {"return": {}}}}})

    def test_a_risky_call_needs_a_confirm_first(self):
        self.assertIn("risky", load_error(UNCONFIRMED))

    def test_a_risky_call_cannot_be_the_start(self):
        msg = load_error("""
            id: f
            triggers: {any_of: [pay]}
            start: pay
            nodes:
              pay: {type: call, tool: pay, args: {amount: "1"}, on_ok: done, on_error: done}
              done: {type: end}
        """)
        self.assertIn("start", msg)

    def test_a_lookup_needs_no_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            flows, tools = setup_dir(tmp, UNCONFIRMED.replace("tool: pay", "tool: look"))
            self.assertIn("f", load_flows(flows, tools))


CONFIRMED = """
    id: f
    triggers: {any_of: [pay]}
    start: ask
    nodes:
      ask: {type: ask, slot: amount, prompt: "How much?", extractor: number, next: check}
      check: {type: confirm, prompt: "Pay {amount}?", on_yes: call, on_no: done}
      call: {type: call, tool: pay, args: {amount: "{amount}"}, on_ok: say, on_error: done}
      say: {type: say, text: "Paid, reference {result.reference}.", next: done}
      done: {type: end}
"""

OTHER = """
    id: other
    buttons: [menu_other]
    triggers: {any_of: [other]}
    interrupts: {priority: 9, any_of: [lost]}
    start: say
    nodes:
      say: {type: say, text: "Other.", next: done}
      done: {type: end}
"""

WORDS = (("yes", "sure", "go ahead"), ("no", "stop"))
POLICY = AskPolicy("not valid.", "use the keypad.", "giving up.", 2, "handoff")


def build(tmp, words=WORDS):
    flows, tools_path = setup_dir(tmp, CONFIRMED)
    with open(os.path.join(flows, "other.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(OTHER))
    pack = DomainPack("bank", "en", {"hours": "We open at 9."},
                      (parse_pattern("t", {"id": "hours", "any_of": ["open"]}),), Fallback("sorry", "bye"),
                      "", "", None, POLICY, frozenset(), wording={"confirm.declined": "Not done."},
                      confirm_words=words)
    tools = RecordingTools(FakeApiExecutor.from_yaml(tools_path))
    return FlowManager(pack, tools, load_flows(flows, tools_path)), tools


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class ConfirmTest(unittest.TestCase):
    def test_the_confirm_prompt_waits(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            _, r = talk(m, Utterance("pay"), Utterance("50"))
        self.assertEqual((r.reply, r.state.node_id, tools.records), ("Pay 50?", "check", []))

    def test_yes_calls_the_tool_once(self):
        for answer in (Utterance("yes please"), Utterance("go ahead"), Dtmf("1")):
            with tempfile.TemporaryDirectory() as tmp:
                m, tools = build(tmp)
                *_, r = talk(m, Utterance("pay"), Utterance("50"), answer)
            self.assertEqual([c["name"] for c in tools.records], ["pay"], answer)
            self.assertEqual((r.reply, r.trace["confirm"]), ("Paid, reference R1.", "yes"))

    def test_no_does_not_call_the_tool(self):
        for answer in (Utterance("no thanks"), Dtmf("2")):
            with tempfile.TemporaryDirectory() as tmp:
                m, tools = build(tmp)
                *_, r = talk(m, Utterance("pay"), Utterance("50"), answer)
            self.assertEqual((tools.records, r.reply, r.trace["confirm"]), ([], "Not done.", "no"))
            self.assertEqual(r.state.node_id, "done")

    def test_both_or_neither_is_unclear(self):
        for answer in (Utterance("yes no"), Utterance("hmm"), Dtmf("3"), ButtonPress("x")):
            with tempfile.TemporaryDirectory() as tmp:
                m, tools = build(tmp)
                *_, r = talk(m, Utterance("pay"), Utterance("50"), answer)
            self.assertEqual((r.trace["confirm"], r.reply, r.state.node_id), ("unclear", "not valid. Pay 50?", "check"))
            self.assertEqual(tools.records, [])

    def test_unclear_three_times_hands_off_without_a_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("hmm"), Utterance("what"), Utterance("eh"))
        self.assertEqual((r.actions, tools.records), ((HandOff("input_failed"),), []))

    def test_nothing_breaks_into_a_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            for turn in (Utterance("I lost my card"), ButtonPress("menu_other"), Utterance("when do you open")):
                *_, r = talk(m, Utterance("pay"), Utterance("50"), turn)
                self.assertEqual((r.state.flow_id, r.state.node_id, r.trace["confirm"]), ("f", "check", "unclear"))
                self.assertNotIn("switch", r.trace)
                self.assertNotIn("We open", r.reply)

    def test_without_confirm_words_speech_is_unclear(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp, words=None)
            *_, r = talk(m, Utterance("pay"), Utterance("50"), Utterance("yes"))
        self.assertEqual(r.trace["confirm"], "unclear")

    def test_a_risky_call_reached_from_elsewhere_too_is_rejected(self):
        msg = load_error(CONFIRMED.replace("on_error: done}\n      say", "on_error: call}\n      say")
                         .replace('args: {amount: "{amount}"}, on_ok: say, on_error: call',
                                  'args: {amount: "{amount}"}, on_ok: say, on_error: done')
                         .replace("next: check}", "next: check}\n      back: {type: goto, next: call}")
                         .replace('on_yes: call, on_no: done', 'on_yes: call, on_no: back'))
        self.assertIn("back", msg)

    def test_confirm_keys_are_checked(self):
        self.assertIn("unknown keys", load_error(CONFIRMED.replace("on_no: done}", "on_no: done, maybe: done}")))
        self.assertIn("needs `on_no`", load_error(CONFIRMED.replace(", on_no: done}", "}")))


if __name__ == "__main__":
    unittest.main()
