"""R7b: confirmation before risky actions. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.rules.flows import FlowError, load_flows, risky_tools
from voxstage.tools import FakeApiExecutor

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


if __name__ == "__main__":
    unittest.main()
