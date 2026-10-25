"""R13: identity gate. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, gate_tools, load_flows
from voxstage.rules.interpreter import FlowManager
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


def tool(**body):
    return {"params": [], **body}


class ToolKeysTest(unittest.TestCase):
    def test_protected_and_verifying_tools(self):
        api = FakeApiExecutor({"tools": {"look": tool(requires="verified"), "check": tool(verifies=True)}})
        self.assertEqual(api.tools["look"]["requires"], "verified")
        self.assertTrue(api.tools["check"]["verifies"])

    def test_bad_keys(self):
        for tools in ({"look": tool(requires="admin"), "check": tool(verifies=True)},
                      {"look": tool(requires="verified"), "check": tool(verifies="yes")},
                      {"both": tool(requires="verified", verifies=True)},
                      {"look": tool(requires="verified")},
                      {"look": tool(requires="verified"), "a": tool(verifies=True), "b": tool(verifies=True)}):
            with self.subTest(tools=sorted(tools)), self.assertRaises(ValueError):
                FakeApiExecutor({"tools": tools})

    def test_a_verifier_without_protected_tools_is_allowed(self):
        FakeApiExecutor({"tools": {"check": tool(verifies=True)}})

    def test_the_domains(self):
        found = {d: gate_tools(os.path.join(ROOT, d, "tools.yaml")) for d in ("bank", "shop", "telecom")}
        self.assertEqual(found, {"bank": (frozenset({"get_balance"}), "verify_identity"),
                                 "shop": (frozenset({"get_order_status"}), "verify_identity"),
                                 "telecom": (frozenset({"get_bill"}), "verify_identity")})


TOOLS = """
tools:
  look: {requires: verified, params: [acct], rules: [{when: {acct: "1234"}, return: {value: 7}}]}
  check: {verifies: true, params: [acct, pin], rules: [{when: {acct: "1234", pin: "2468"}, return: {ok: true}}],
          default: {error: invalid_credentials}}
"""
LOOKUP = """
id: lookup
triggers: {any_of: [balance]}
start: ask_acct
nodes:
  ask_acct: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: look, args: {acct: "{acct}"}, on_ok: say, on_error: fail}
  say: {type: say, text: "It is {result.value}.", next: done}
  fail: {type: say, text: "Sorry.", next: done}
  done: {type: end}
"""
CHECK = """
id: check_id
role: verification
carry: [acct]
start: ask_acct
nodes:
  ask_acct: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: ask_pin}
  ask_pin: {type: ask, slot: pin, prompt: "Your PIN?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: check, args: {acct: "{acct}", pin: "{pin}"}, on_ok: done, on_error: wrong}
  wrong: {type: say, text: "That doesn't match. Please try again.", next: ask_acct}
  done: {type: end}
"""


def write_pack(tmp: str, flows: dict, tools: str = TOOLS) -> tuple:
    os.makedirs(os.path.join(tmp, "flows"), exist_ok=True)
    with open(os.path.join(tmp, "tools.yaml"), "w") as f:
        f.write(textwrap.dedent(tools))
    for name, body in flows.items():
        with open(os.path.join(tmp, "flows", f"{name}.yaml"), "w") as f:
            f.write(textwrap.dedent(body))
    return os.path.join(tmp, "flows"), os.path.join(tmp, "tools.yaml")


class VerificationFlowLoadTest(unittest.TestCase):
    def load(self, flows: dict):
        with tempfile.TemporaryDirectory() as tmp:
            return load_flows(*write_pack(tmp, flows))

    def test_loads(self):
        flows = self.load({"lookup": LOOKUP, "check_id": CHECK})
        self.assertEqual(flows["check_id"].role, "verification")
        self.assertIsNone(flows["check_id"].triggers)
        self.assertIsNone(flows["lookup"].role)

    def test_load_errors(self):
        bad = {
            "no verification flow": ("no flow has", {"lookup": LOOKUP}),
            "two verification flows": ("more than one", {"lookup": LOOKUP, "check_id": CHECK,
                                       "check_two": CHECK.replace("id: check_id", "id: check_two")}),
            "a trigger on it": ("no triggers", {"lookup": LOOKUP, "check_id": CHECK.replace(
                "role: verification", "role: verification\ntriggers: {any_of: [pin]}")}),
            "unknown role": ("can only be", {"lookup": LOOKUP, "check_id": CHECK.replace("role: verification",
                                                                                          "role: helper")}),
            "no verifying call": ("verifies: true", {"lookup": LOOKUP, "check_id": CHECK.replace(
                "on_ok: done, on_error: wrong", "on_ok: done, on_error: done").replace(
                'call: {type: call, tool: check, args: {acct: "{acct}", pin: "{pin}"}', 'call: {type: goto')
                .replace("on_ok: done, on_error: done}", "next: done}").replace(
                '  wrong: {type: say, text: "That doesn\'t match. Please try again.", next: ask_acct}\n', "")}),
        }
        for name, (message, flows) in bad.items():
            with self.subTest(name), self.assertRaisesRegex(FlowError, message):
                self.load(flows)

    def test_no_protected_call_inside(self):
        body = CHECK.replace("on_ok: done", "on_ok: peek").replace(
            "  done: {type: end}", "  peek: {type: call, tool: look, args: {acct: \"{acct}\"}, on_ok: done, "
                                   "on_error: done}\n  done: {type: end}")
        with self.assertRaises(FlowError):
            self.load({"lookup": LOOKUP, "check_id": body})


def build(tmp: str, flows: dict, tools: str = TOOLS, **pack_fields):
    flows_dir, tools_path = write_pack(tmp, flows, tools)
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), tools_path, "", None,
                      AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset({"pin"}),
                      **pack_fields)
    api = RecordingTools(FakeApiExecutor.from_yaml(tools_path))
    return FlowManager(pack, api, load_flows(flows_dir, tools_path)), api


def talk(m, *inputs, setup=None):
    state, out = m.initial_state("s", setup), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


OPEN_TOOLS = """
tools:
  look: {params: [acct], rules: [{when: {acct: "1234"}, return: {value: 7}}], default: {error: not_found}}
"""
PREFILLED = LOOKUP.replace("start: ask_acct", "prefill: {acct: customer.acct}\n"
                           "captures: {acct: {extractor: digits, length: 4, cue: [account]}}\nstart: ask_acct")


class PrefillTest(unittest.TestCase):
    def test_the_record_fills_an_empty_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp, {"lookup": PREFILLED}, OPEN_TOOLS)
            r, = talk(m, Utterance("my balance"), setup={"customer": {"acct": "1234"}})
        self.assertEqual((r.state.slots, r.reply), ({"acct": "1234"}, "It is 7."))

    def test_words_win_over_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp, {"lookup": PREFILLED}, OPEN_TOOLS)
            r, = talk(m, Utterance("balance of account 5678"), setup={"customer": {"acct": "1234"}})
        self.assertEqual(r.state.slots, {"acct": "5678"})

    def test_without_a_record_the_slot_is_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp, {"lookup": PREFILLED}, OPEN_TOOLS)
            r, = talk(m, Utterance("my balance"))
        self.assertEqual((r.state.node_id, r.reply), ("ask_acct", "Account?"))

    def test_bad_prefill(self):
        for prefill in ("{acct: slots.acct}", "{nope: customer.acct}", "[acct]"):
            with self.subTest(prefill), tempfile.TemporaryDirectory() as tmp, self.assertRaises(FlowError):
                load_flows(*write_pack(tmp, {"lookup": LOOKUP.replace(
                    "start: ask_acct", f"prefill: {prefill}\nstart: ask_acct")}, OPEN_TOOLS))


if __name__ == "__main__":
    unittest.main()
