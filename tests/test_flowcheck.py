"""R16b (ADR 0014): typed API params, response schema and the load-time check of the calls.
Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.evaluate import DEFAULT_DOMAINS_DIR
from voxstage.rules.flows import FlowCheckError, load_flows
from voxstage.rules.types import load_types
from voxstage.tools import FakeApiExecutor

TYPES = os.path.join(DEFAULT_DOMAINS_DIR, "bank", "types.yaml")

TOOLS = """tools:
  verify_identity:
    verifies: true
    params: {account_last4: {type: digits, length: 4}, pin: {type: digits, length: 4}}
    returns: {verified: boolean}
    rules: []
    default: {return: {verified: true}}
  lookup:
    params:
      phone: {type: digits, length: 4}
      kind: {type: choice, choices: [gold, basic]}
      note: {type: text, required: false}
    returns: {fee: number, tier: {type: choice, choices: [gold, basic]}, code: text}
    rules: []
    default: {return: {fee: 1, tier: gold, code: abc}}
  use_fee:
    params: {amount: number, tier: {type: choice, choices: [gold, basic]}}
    rules: []
    default: {return: {ok: true}}
  get_visit:
    requires: verified
    params: {account_last4: {type: digits, length: 4}}
    rules: []
    default: {return: {ok: true}}
"""
HEADER = """id: t
triggers: {any_of: [hello]}
roles:
  booker: {type: Person}
  visitor: {type: Person}
start: ask_first
"""
HEADER_DEFAULT = HEADER.replace("visitor: {type: Person}", "visitor: {type: Person, default: {from: booker}}")
FLOW = HEADER + """nodes:
  ask_first: {type: ask, role: booker, field: phone_last4, prompt: "Phone?", next: look}
  look:
    type: call
    tool: lookup
    bind:
      phone: {role: booker, field: phone_last4}
      kind: {const: gold}
    on_ok: use
    on_error: done
  use:
    type: call
    tool: use_fee
    bind:
      amount: {call: look, field: fee}
      tier: {call: look, field: tier}
    on_ok: done
  done: {type: end}
"""


VERIFY = """id: verify
role: verification
start: v
nodes:
  v: {type: call, tool: verify_identity, args: {account_last4: "1234", pin: "1234"}, on_ok: done}
  done: {type: end}
"""


def load(flow, tools=TOOLS, name="t", verify=False):
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "tools.yaml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(tools)
        os.mkdir(os.path.join(tmp, "flows"))
        with open(os.path.join(tmp, "flows", f"{name}.yaml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(flow)
        if verify:
            with open(os.path.join(tmp, "flows", "verify.yaml"), "w", encoding="utf-8", newline="\n") as f:
                f.write(VERIFY)
        return load_flows(os.path.join(tmp, "flows"), os.path.join(tmp, "tools.yaml"), types=load_types(TYPES))


def items(flow, tools=TOOLS, verify=False):
    try:
        load(flow, tools, verify=verify)
    except FlowCheckError as exc:
        return exc.items
    return []


def codes(found):
    return sorted((i["code"], i["node"], i["parameter"]) for i in found)


class ToolSpecTest(unittest.TestCase):
    def test_the_good_flow_loads(self):
        self.assertIn("t", load(FLOW))

    def test_old_list_params_still_work(self):
        api = FakeApiExecutor({"tools": {"a": {"params": ["x"], "rules": [{"when": {"y": 1}, "return": {"z": 1}}]}}})
        self.assertEqual(api.call("a", {}).error, "missing_param:x")
        self.assertTrue(api.call("a", {"x": 1, "y": 1}).ok)

    def test_an_optional_param_may_be_left_out(self):
        api = FakeApiExecutor.__new__(FakeApiExecutor)
        api.__init__({"tools": {"a": {"params": {"x": "text", "n": {"type": "text", "required": False}},
                                      "rules": [], "default": {"return": {}}}}})
        self.assertTrue(api.call("a", {"x": "1"}).ok)
        self.assertEqual(api.call("a", {"n": "1"}).error, "missing_param:x")

    def test_rules_must_follow_the_spec(self):
        base = {"params": {"x": {"type": "digits", "length": 2}}, "returns": {"r": "number"}}
        with self.assertRaisesRegex(ValueError, "not a param"):
            FakeApiExecutor({"tools": {"a": {**base, "rules": [{"when": {"nope": "12"}, "return": {"r": 1}}]}}})
        with self.assertRaisesRegex(ValueError, "does not fit"):
            FakeApiExecutor({"tools": {"a": {**base, "rules": [{"when": {"x": "123"}, "return": {"r": 1}}]}}})
        with self.assertRaisesRegex(ValueError, "does not declare"):
            FakeApiExecutor({"tools": {"a": {**base, "rules": [{"when": {"x": "12"}, "return": {"q": 1}}]}}})
        with self.assertRaisesRegex(ValueError, "does not fit"):
            FakeApiExecutor({"tools": {"a": {**base, "default": {"return": {"r": "abc"}}}}})

    def test_bad_specs(self):
        with self.assertRaisesRegex(ValueError, "must be one of"):
            FakeApiExecutor({"tools": {"a": {"params": {"x": "nope"}}}})
        with self.assertRaisesRegex(ValueError, "choices"):
            FakeApiExecutor({"tools": {"a": {"params": {"x": {"type": "choice"}}}}})
        with self.assertRaisesRegex(ValueError, "required"):
            FakeApiExecutor({"tools": {"a": {"params": {"x": {"type": "text", "required": "no"}}}}})


class CheckTest(unittest.TestCase):
    def test_unbound(self):
        found = items(FLOW.replace("      kind: {const: gold}\n", ""))
        self.assertEqual(codes(found), [("unbound", "look", "kind")])
        self.assertEqual(set(found[0]), {"code", "node", "parameter", "role", "field", "path"})
        self.assertEqual(found[0]["path"], [])

    def test_an_optional_param_may_stay_unbound(self):
        self.assertEqual(items(FLOW), [])   # `note` is not bound anywhere

    def test_unbound_names_a_field_the_tool_does_not_return(self):
        found = items(FLOW.replace("field: fee", "field: price"))
        self.assertEqual(codes(found), [("unbound", "use", "amount")])
        self.assertEqual(found[0]["field"], "look.price")

    def test_type_mismatch_of_a_role_field_a_const_and_a_returned_field(self):
        self.assertEqual(codes(items(FLOW.replace("kind: {const: gold}", "kind: {const: silver}"))),
                         [("type_mismatch", "look", "kind")])
        self.assertEqual(codes(items(FLOW.replace("amount: {call: look, field: fee}", "amount: {call: look, field: code}"))),
                         [("type_mismatch", "use", "amount")])
        # a 4-digit phone number does not fit a 3-digit parameter
        tools = TOOLS.replace("phone: {type: digits, length: 4}", "phone: {type: digits, length: 3}")
        found = items(FLOW, tools)
        self.assertEqual(codes(found), [("type_mismatch", "look", "phone")])
        self.assertEqual((found[0]["role"], found[0]["field"]), ("booker", "phone_last4"))

    def test_not_collected_has_a_witness_path(self):
        skip = FLOW.replace("triggers: {any_of: [hello]}", "triggers: {any_of: [hello]}").replace(
            "start: ask_first", "start: pick").replace("nodes:\n", """nodes:
  pick: {type: branch, cases: [{when: "1 == 2", next: ask_first}], else: look}
""")
        found = items(skip)
        self.assertEqual(codes(found), [("not_collected", "look", "phone")])
        self.assertEqual(found[0]["path"], ["pick", "look"])
        self.assertEqual((found[0]["role"], found[0]["field"]), ("booker", "phone_last4"))

    def test_a_loop_does_not_hide_a_missing_value(self):
        loop = FLOW.replace("  done: {type: end}", """  again: {type: say, text: "again", next: look}
  done: {type: end}""").replace("on_error: done", "on_error: again").replace(
            "start: ask_first", "start: ask_first")
        self.assertEqual(items(loop), [])   # the ask comes before the loop on every path

    def test_a_confirm_default_collects_the_role_on_yes_only(self):
        flow = HEADER_DEFAULT + """nodes:
  ask_first: {type: ask, role: booker, field: phone_last4, prompt: "Phone?", next: same}
  same: {type: confirm, role_default: visitor, prompt: "You?", on_yes: look, on_no: look}
  look:
    type: call
    tool: lookup
    bind:
      phone: {role: visitor, field: phone_last4}
      kind: {const: gold}
    on_ok: done
  done: {type: end}
"""
        found = items(flow)
        self.assertEqual(codes(found), [("not_collected", "look", "phone")])
        self.assertEqual(found[0]["path"], ["ask_first", "same", "look"])
        self.assertEqual(items(flow.replace("on_yes: look, on_no: look", "on_yes: look, on_no: ask_v").replace(
            "  look:", '  ask_v: {type: ask, role: visitor, field: phone_last4, prompt: "Who?", next: look}\n  look:')), [])

    def test_a_result_is_there_only_after_the_ok_edge(self):
        found = items(FLOW.replace("on_ok: use\n    on_error: done", "on_ok: use\n    on_error: use"))
        self.assertEqual(codes(found), [("not_collected", "use", "amount"), ("not_collected", "use", "tier")])
        self.assertEqual(found[0]["path"], ["ask_first", "look", "use"])

    def test_the_caller_needs_a_protected_tool(self):
        flow = """id: t
triggers: {any_of: [hello]}
start: go
nodes:
  go:
    type: call
    tool: get_visit
    bind: {account_last4: {role: caller, field: account_last4}}
    on_ok: done
  done: {type: end}
"""
        self.assertEqual(items(flow, verify=True), [])
        bad = flow.replace("tool: get_visit", "tool: lookup").replace("account_last4: {role", "phone: {role")
        found = items(bad, verify=True)
        self.assertIn(("not_collected", "go", "phone"), codes(found))
        self.assertEqual(next(i for i in found if i["parameter"] == "phone")["role"], "caller")

    def test_several_problems_come_together_and_the_text_is_built_from_them(self):
        broken = FLOW.replace("      kind: {const: gold}\n", "").replace("field: fee", "field: price")
        with self.assertRaises(FlowCheckError) as ctx:
            load(broken)
        self.assertEqual(codes(ctx.exception.items), [("unbound", "look", "kind"), ("unbound", "use", "amount")])
        self.assertIn("2 problem(s)", str(ctx.exception))
        self.assertIn("node look, parameter `kind`", str(ctx.exception))

    def test_a_single_placeholder_in_args_is_checked_like_a_bind(self):
        flow = FLOW.replace("""    bind:
      phone: {role: booker, field: phone_last4}
      kind: {const: gold}""", """    args:
      phone: "{booker.phone_last4}"
      kind: "gold" """)
        self.assertEqual(items(flow), [])
        skip = flow.replace("start: ask_first", "start: pick").replace("nodes:\n", """nodes:
  pick: {type: branch, cases: [{when: "1 == 2", next: ask_first}], else: look}
""")
        self.assertEqual(codes(items(skip)), [("not_collected", "look", "phone")])


if __name__ == "__main__":
    unittest.main()
