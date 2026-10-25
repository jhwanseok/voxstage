"""R12: tool failures and delays. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import EndCall, HandOff, step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, ToolPolicy
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import GATED, TOOL_FAILURES, VERIFIED, FlowManager
from voxstage.tools import FakeApiExecutor, ToolExecutor, ToolResult
from voxstage.turn import Dtmf, Utterance

TOOLS = """
tools:
  look:
    retry: 1
    params: [acct]
    rules:
      - {when: {acct: "1111"}, error: timeout}
      - {when: {acct: "2222"}, delay_ms: 8000, return: {value: 2}}
      - {when: {acct: "3333"}, delay_ms: 100, return: {value: 3}}
      - {when: {acct: "1234"}, return: {value: 7}}
    default: {error: not_found}
  plain:
    params: [acct]
    rules: [{when: {acct: "1111"}, error: timeout}]
    default: {error: not_found}
  change:
    risky: true
    params: [acct]
    rules:
      - {when: {acct: "1111"}, error: timeout}
      - {when: {acct: "5555"}, error: refused}
    default: {return: {ok: true}}
"""
LOOKUP = """
id: lookup
triggers: {any_of: [balance]}
start: ask
nodes:
  ask: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: look, args: {acct: "{acct}"}, on_ok: say, on_error: fail}
  say: {type: say, text: "It is {result.value}.", next: done}
  fail: {type: say, text: "I'm unable to look that up.", next: done}
  done: {type: end}
"""
BARE = """
id: bare
triggers: {any_of: [usage]}
start: ask
nodes:
  ask: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: plain, args: {acct: "{acct}"}, on_ok: done}
  done: {type: end}
"""
CHANGE = """
id: change_it
triggers: {any_of: [change]}
start: ask
nodes:
  ask: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: confirm}
  confirm: {type: confirm, prompt: "Change {acct}?", on_yes: call, on_no: done}
  call: {type: call, tool: change, args: {acct: "{acct}"}, on_ok: ok, on_error: refused}
  ok: {type: say, text: "Done.", next: done}
  refused: {type: say, text: "That change was refused.", next: done}
  done: {type: end}
"""
WORDING = {"call.failed": "Can't do that now.", "call.unconfirmed": "Not sure it went through.",
           "call.exceed": "Still failing, connecting you."}


def write(tmp, flows, tools=TOOLS):
    os.makedirs(os.path.join(tmp, "flows"), exist_ok=True)
    with open(os.path.join(tmp, "tools.yaml"), "w") as f:
        f.write(textwrap.dedent(tools))
    for name, body in flows.items():
        with open(os.path.join(tmp, "flows", f"{name}.yaml"), "w") as f:
            f.write(textwrap.dedent(body))
    return os.path.join(tmp, "flows"), os.path.join(tmp, "tools.yaml")


def build(tmp, flows=None, tools=TOOLS, executor=None, **fields):
    flows_dir, tools_path = write(tmp, flows or {"lookup": LOOKUP, "bare": BARE, "change_it": CHANGE}, tools)
    pack = DomainPack("bank", "en", {}, (), Fallback("sorry", "bye"), tools_path, "", None,
                      AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset(),
                      wording=WORDING, confirm_words=(("yes",), ("no",)), **fields)
    api = RecordingTools(executor or FakeApiExecutor.from_yaml(tools_path))
    return FlowManager(pack, api, load_flows(flows_dir, tools_path)), api


def talk(m, *inputs, setup=None):
    state, out = m.initial_state("s", setup), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


def calls(api):
    return [(c["name"], c["error"]) for c in api.records]


class FailsOnce(ToolExecutor):
    """The first call times out, the next ones answer."""

    def __init__(self, inner):
        self.inner, self.n = inner, 0

    def call(self, tool, args):
        self.n += 1
        return ToolResult(False, error="timeout") if self.n == 1 else self.inner.call(tool, args)


class RetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_timeout_is_tried_once_more(self):
        m, api = build(self.tmp.name)
        _, r = talk(m, Utterance("balance"), Dtmf("1111"))
        self.assertEqual(calls(api), [("look", "timeout"), ("look", "timeout")])
        self.assertEqual(r.reply, "I'm unable to look that up.")
        self.assertEqual(r.trace["call_policy"], ["retried"])
        self.assertEqual(r.state.meta[TOOL_FAILURES], 1)

    def test_not_found_is_not_retried_or_counted(self):
        m, api = build(self.tmp.name)
        _, r = talk(m, Utterance("balance"), Dtmf("9999"))
        self.assertEqual(calls(api), [("look", "not_found")])
        self.assertNotIn(TOOL_FAILURES, r.state.meta)

    def test_a_retry_that_answers(self):
        flows_dir, tools_path = write(self.tmp.name, {"lookup": LOOKUP})
        m, api = build(self.tmp.name, {"lookup": LOOKUP},
                       executor=FailsOnce(FakeApiExecutor.from_yaml(tools_path)))
        _, r = talk(m, Utterance("balance"), Dtmf("1234"))
        self.assertEqual((r.reply, calls(api)), ("It is 7.", [("look", "timeout"), ("look", None)]))
        self.assertNotIn(TOOL_FAILURES, r.state.meta)

    def test_a_tool_without_retry_is_called_once(self):
        m, api = build(self.tmp.name)
        _, r = talk(m, Utterance("usage"), Dtmf("1111"))
        self.assertEqual(calls(api), [("plain", "timeout")])


class DelayTest(unittest.TestCase):
    def test_slower_than_the_limit_is_a_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp)
            _, r = talk(m, Utterance("balance"), Dtmf("2222"))
        self.assertEqual(r.reply, "I'm unable to look that up.")   # the data is not used
        self.assertEqual([c["error"] for c in r.trace["calls"]], ["timeout", "timeout"])
        self.assertEqual(r.trace["calls"][0]["delay_ms"], 8000)

    def test_within_the_limit_is_an_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("balance"), Dtmf("3333"))
            self.assertEqual(r.reply, "It is 3.")
            m, _ = build(tmp, tool_policy=ToolPolicy(timeout_ms=50))
            _, r = talk(m, Utterance("balance"), Dtmf("3333"))
            self.assertEqual(r.reply, "I'm unable to look that up.")


class RiskyTimeoutTest(unittest.TestCase):
    def test_outcome_unknown_hands_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp)
            *_, r = talk(m, Utterance("change"), Dtmf("1111"), Utterance("yes"))
        self.assertEqual(calls(api), [("change", "timeout")])   # never repeated
        self.assertEqual((r.reply, r.actions), ("Not sure it went through.", (HandOff("outcome_unknown"),)))

    def test_a_clear_refusal_goes_to_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp)
            *_, r = talk(m, Utterance("change"), Dtmf("5555"), Utterance("yes"))
        self.assertEqual((r.reply, r.actions), ("That change was refused.", ()))


class LimitTest(unittest.TestCase):
    def test_the_second_failure_hands_off_across_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp)
            _, a, _, b = talk(m, Utterance("balance"), Dtmf("1111"), Utterance("usage"), Dtmf("1111"))
        self.assertEqual((a.reply, a.actions), ("I'm unable to look that up.", ()))
        self.assertEqual((b.reply, b.actions), ("Still failing, connecting you.", (HandOff("tool_failed"),)))

    def test_end_call_and_a_higher_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp, tool_policy=ToolPolicy(max_failures=1, on_exceed="end_call"))
            _, r = talk(m, Utterance("balance"), Dtmf("1111"))
            self.assertEqual(r.actions, (EndCall(),))
            m, _ = build(tmp, tool_policy=ToolPolicy(max_failures=3))
            *_, r = talk(m, Utterance("balance"), Dtmf("1111"), Utterance("balance"), Dtmf("1111"))
            self.assertEqual(r.actions, ())


class DefaultWordingTest(unittest.TestCase):
    def test_a_call_without_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("usage"), Dtmf("4444"))   # not_found, no on_error
        self.assertEqual((r.reply, r.actions), ("Can't do that now.", ()))
        self.assertEqual(r.trace["call_policy"], ["default wording"])


GATE_TOOLS = TOOLS + """
  secret: {requires: verified, params: [acct], default: {return: {value: 1}}}
  check:
    verifies: true
    params: [acct, pin]
    rules: [{when: {pin: "0000"}, error: timeout}]
    default: {error: invalid_credentials}
"""
SECRET = """
id: secret_flow
triggers: {any_of: [secret]}
start: ask
nodes:
  ask: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: secret, args: {acct: "{acct}"}, on_ok: done, on_error: done}
  done: {type: end}
"""
CHECK = """
id: check_id
role: verification
carry: [acct]
start: ask_acct
nodes:
  ask_acct: {type: ask, slot: acct, prompt: "Account?", extractor: digits, length: 4, next: ask_pin}
  ask_pin: {type: ask, slot: pin, prompt: "PIN?", extractor: digits, length: 4, next: call}
  call: {type: call, tool: check, args: {acct: "{acct}", pin: "{pin}"}, on_ok: done, on_error: wrong}
  wrong: {type: say, text: "That doesn't match.", next: ask_pin}
  done: {type: end}
"""


class VerifierTimeoutTest(unittest.TestCase):
    def test_a_timeout_is_not_a_failed_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, api = build(tmp, {"secret_flow": SECRET, "check_id": CHECK}, GATE_TOOLS)
            *_, r = talk(m, Utterance("secret"), Dtmf("1234"), Dtmf("0000"))
        self.assertEqual(calls(api), [("check", "timeout")])
        self.assertEqual(r.reply, "Can't do that now.")
        self.assertNotIn("verify_failures", r.state.meta)
        self.assertNotIn(GATED, r.state.meta)
        self.assertNotIn(VERIFIED, r.state.meta)


class LoadTest(unittest.TestCase):
    def test_on_error_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            flows = load_flows(*write(tmp, {"bare": BARE}))
        self.assertIsNone(flows["bare"].nodes["call"].data["on_error"])

    def test_retry_on_a_risky_tool_fails_to_load(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            build(tmp, tools=TOOLS.replace("    risky: true\n", "    risky: true\n    retry: 1\n"))


if __name__ == "__main__":
    unittest.main()
