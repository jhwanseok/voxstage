"""R13: identity gate. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import (AskPolicy, DomainPack, Fallback, RuleError, VerificationPolicy,
                                  load_verification_policy)
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, gate_tools, load_flows
from voxstage.rules.interpreter import GATED, LOCKED, RUNTIME, VERIFIED, FlowManager, build_manager
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
        self.assertEqual(found, {"bank": (frozenset({"get_balance", "get_visit"}), "verify_identity"),
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


OTHER = """
id: other
triggers: {any_of: [peek]}
start: call
nodes:
  call: {type: call, tool: look, args: {acct: "1234"}, on_ok: say, on_error: done}
  say: {type: say, text: "Peeked {result.value}.", next: done}
  done: {type: end}
"""


def calls(api):
    return [(c["name"], c["error"]) for c in api.records]


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m, self.api = build(self.tmp.name, {"lookup": LOOKUP, "check_id": CHECK, "other": OTHER})

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_protected_call_before_the_check(self):
        a, b = talk(self.m, Utterance("my balance"), Dtmf("1234"))
        self.assertEqual(calls(self.api), [])
        self.assertEqual((b.reply, b.state.flow_id, b.state.node_id), ("Your PIN?", "check_id", "ask_pin"))
        self.assertEqual(b.trace["gate"], {"tool": "look", "flow": "lookup"})
        self.assertEqual(b.state.slots, {"acct": "1234"})   # carried into the check

    def test_from_any_flow(self):
        r, = talk(self.m, Utterance("peek"))
        self.assertEqual((calls(self.api), r.state.flow_id), ([], "check_id"))
        self.assertEqual(r.reply, "Account?")   # nothing to carry: the check asks for the account too

    def test_a_pass_runs_the_stopped_call_in_the_same_turn(self):
        *_, c = talk(self.m, Utterance("my balance"), Dtmf("1234"), Dtmf("2468"))
        self.assertEqual(calls(self.api), [("check", None), ("look", None)])
        self.assertEqual((c.reply, c.state.flow_id, c.state.node_id), ("It is 7.", "lookup", "done"))
        self.assertTrue(c.state.meta[VERIFIED])
        self.assertNotIn(GATED, c.state.meta)

    def test_a_pass_holds_for_the_call(self):
        *_, d = talk(self.m, Utterance("my balance"), Dtmf("1234"), Dtmf("2468"), Utterance("peek"))
        self.assertEqual((d.reply, calls(self.api)[-1]), ("Peeked 7.", ("look", None)))

    def test_wrong_details_are_asked_again_without_saying_which(self):
        *_, c = talk(self.m, Utterance("my balance"), Dtmf("1234"), Dtmf("1111"))
        self.assertEqual(calls(self.api), [("check", "invalid_credentials")])
        self.assertEqual(c.reply, "That doesn't match. Please try again. Your PIN?")
        self.assertEqual((c.state.node_id, c.state.slots), ("ask_pin", {"acct": "1234"}))
        self.assertNotIn("7", c.reply)

    def test_every_answer_of_the_check_is_asked_again(self):
        *_, c = talk(self.m, Utterance("peek"), Dtmf("1234"), Dtmf("1111"))
        self.assertEqual((c.state.node_id, c.state.slots), ("ask_acct", {}))
        self.assertTrue(c.reply.endswith("Account?"))

    def test_lockout_at_the_limit(self):
        out = talk(self.m, Utterance("my balance"), Dtmf("1234"), Dtmf("1111"), Dtmf("2222"), Dtmf("3333"))
        self.assertEqual(out[3].actions, ())
        last = out[4]
        self.assertEqual(last.actions, (HandOff("verification_failed"),))
        self.assertIn("couldn't verify", last.reply)
        self.assertTrue(last.state.meta[LOCKED])
        self.assertEqual(len(calls(self.api)), 3)
        state = last.state
        for text in ("peek",):   # later protected calls are refused too
            r = step(self.m, state, Utterance(text))
            self.assertEqual(r.actions, (HandOff("verification_failed"),))
        self.assertEqual(len(calls(self.api)), 3)

    def test_runtime_keys(self):
        self.assertIn(GATED, RUNTIME)
        self.assertNotIn(VERIFIED, RUNTIME)
        self.assertNotIn(LOCKED, RUNTIME)


class LimitTest(unittest.TestCase):
    def wrong(self, flows, n, **pack_fields):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp, flows, **pack_fields)
            return talk(m, Utterance("my balance"), Dtmf("1234"), *[Dtmf("1111")] * n)

    def test_the_config_default(self):
        out = self.wrong({"lookup": LOOKUP, "check_id": CHECK}, 2, verification=VerificationPolicy(2, "end_call"))
        self.assertEqual(out[-2].actions, ())
        self.assertEqual(len(out[-1].actions), 1)
        self.assertEqual(type(out[-1].actions[0]).__name__, "EndCall")

    def test_a_flow_sets_its_own_limit(self):
        own = LOOKUP.replace("start: ask_acct", "verification: {max_attempts: 1}\nstart: ask_acct")
        out = self.wrong({"lookup": own, "check_id": CHECK}, 1)   # the config default is 3
        self.assertEqual(out[-1].actions, (HandOff("verification_failed"),))
        out = self.wrong({"lookup": LOOKUP, "check_id": CHECK}, 1)
        self.assertEqual(out[-1].actions, ())

    def test_bad_flow_limit(self):
        for own in ("{max_attempts: 0}", "{max_attempts: two}", "{tries: 2}", "3"):
            with self.subTest(own), tempfile.TemporaryDirectory() as tmp, self.assertRaises(FlowError):
                load_flows(*write_pack(tmp, {"check_id": CHECK, "lookup": LOOKUP.replace(
                    "start: ask_acct", f"verification: {own}\nstart: ask_acct")}))

    def test_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.yaml")
            for body, want in (("fallback: {}", VerificationPolicy()),
                               ("verification: {max_attempts: 5, on_exceed: end_call}", VerificationPolicy(5, "end_call"))):
                with open(path, "w") as f:
                    f.write(body)
                self.assertEqual(load_verification_policy(path), want)
            for body in ("verification: {max_attempts: 0}", "verification: {on_exceed: hangup}",
                         "verification: {tries: 3}", "verification: 3"):
                with open(path, "w") as f:
                    f.write(body)
                with self.subTest(body), self.assertRaises(RuleError):
                    load_verification_policy(path)

    def test_shipped_packs(self):
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                pack = DomainPack.load(ROOT, d, lang)
                self.assertEqual(pack.verification, VerificationPolicy(3, "handoff"))
                self.assertIn("verify.locked", pack.wording)


class ShippedGateTest(unittest.TestCase):
    def test_cancel_keeps_the_pass(self):
        api = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, "bank", "tools.yaml")))
        m = build_manager(ROOT, "bank", "en", api)
        *_, r = talk(m, Utterance("my balance"), Dtmf("4821"), Dtmf("2468"), Utterance("cancel"),
                     Utterance("my balance"), Dtmf("4821"))
        self.assertIn("1,250", r.reply)
        self.assertEqual([c["name"] for c in api.records], ["verify_identity", "get_balance", "get_balance"])

    def test_cancel_at_the_check_drops_the_stopped_flow(self):
        api = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, "bank", "tools.yaml")))
        m = build_manager(ROOT, "bank", "en", api)
        *_, r = talk(m, Utterance("my balance"), Dtmf("4821"), Utterance("cancel"))
        self.assertNotIn(GATED, r.state.meta)
        self.assertEqual(api.records, [])


if __name__ == "__main__":
    unittest.main()
