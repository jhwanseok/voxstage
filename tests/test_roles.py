"""R16a (ADR 0014): types, roles and call binding. Run: python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.evaluate import DEFAULT_DOMAINS_DIR
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import build_manager
from voxstage.rules.types import load_types
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

BANK = os.path.join(DEFAULT_DOMAINS_DIR, "bank")
TYPES = os.path.join(BANK, "types.yaml")
TOOLS = os.path.join(BANK, "tools.yaml")

HEADER = """id: t
triggers: {any_of: [hello]}
roles:
  booker: {type: Person}
  visitor: {type: Person, default: {from: booker}}
start: ask_first
"""
FLOW_OK = HEADER + """nodes:
  ask_first: {type: ask, role: booker, field: phone_last4, prompt: "Phone?", next: same}
  same: {type: confirm, role_default: visitor, prompt: "You?", on_yes: book, on_no: ask_v}
  ask_v: {type: ask, role: visitor, field: phone_last4, prompt: "Who?", next: book}
  book:
    type: call
    tool: book_visit
    bind:
      booker_phone: {role: booker, field: phone_last4}
      visitor_phone: {role: visitor, field: phone_last4}
    on_ok: done
  done: {type: end}
"""


def load(text, types=True):
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "t.yaml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return load_flows(tmp, TOOLS, types=load_types(TYPES) if types else None)


def turns(manager, state, *inputs):
    result = None
    for item in inputs:
        result = step(manager, state, item)
        state = result.state
    return result


class TypesTest(unittest.TestCase):
    def write(self, text):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "types.yaml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def test_the_bank_dictionary_loads(self):
        types = load_types(TYPES)
        self.assertEqual(sorted(types.types), ["Caller", "Person"])
        self.assertEqual(types.fields_of("Person")["phone_last4"].spec["length"], 4)
        self.assertEqual(types.session_roles, {"caller": "Caller"})

    def test_a_field_cannot_be_a_type(self):
        path = self.write("types:\n  A: {fields: {x: {type: text}}}\n  B: {fields: {a: {type: A}}}\n")
        with self.assertRaisesRegex(FlowError, "do not nest"):
            load_types(path)

    def test_unknown_field_type_and_session_role(self):
        with self.assertRaisesRegex(FlowError, "must be one of"):
            load_types(self.write("types:\n  A: {fields: {x: {type: nope}}}\n"))
        with self.assertRaisesRegex(FlowError, "only session role"):
            load_types(self.write("types:\n  A: {fields: {x: {type: text}}}\nsession_roles:\n  boss: {type: A}\n"))


class LoaderTest(unittest.TestCase):
    def test_a_good_flow_loads(self):
        flow = load(FLOW_OK)["t"]
        self.assertEqual(flow.roles, (("booker", "Person", None), ("visitor", "Person", "booker")))

    def test_roles_need_types(self):
        with self.assertRaisesRegex(FlowError, "types.yaml"):
            load(FLOW_OK, types=False)

    def test_unknown_role_and_field(self):
        with self.assertRaisesRegex(FlowError, "unknown role `guest`"):
            load(FLOW_OK.replace("role: booker, field: phone_last4, prompt", "role: guest, field: phone_last4, prompt"))
        with self.assertRaisesRegex(FlowError, "no field `age`"):
            load(FLOW_OK.replace("field: phone_last4, prompt: \"Phone?\"", "field: age, prompt: \"Phone?\""))

    def test_slot_and_role_are_exclusive(self):
        with self.assertRaisesRegex(FlowError, "not both"):
            load(FLOW_OK.replace("role: booker, field: phone_last4, prompt", "slot: x, role: booker, field: phone_last4, prompt"))

    def test_args_and_bind_are_exclusive_and_complete(self):
        with self.assertRaisesRegex(FlowError, "both `args` and `bind`"):
            load(FLOW_OK.replace("    bind:\n", "    args: {booker_phone: \"x\"}\n    bind:\n"))
        with self.assertRaisesRegex(FlowError, "takes"):
            load(FLOW_OK.replace("      booker_phone: {role: booker, field: phone_last4}\n", ""))

    def test_bad_bindings(self):
        with self.assertRaisesRegex(FlowError, "another call node"):
            load(FLOW_OK.replace("visitor_phone: {role: visitor, field: phone_last4}", "visitor_phone: {call: book, field: x}"))
        with self.assertRaisesRegex(FlowError, "no field"):
            load(FLOW_OK.replace("booker_phone: {role: booker, field: phone_last4}", "booker_phone: {role: caller, field: pin}"))
        with self.assertRaisesRegex(FlowError, "one of"):
            load(FLOW_OK.replace("booker_phone: {role: booker, field: phone_last4}", "booker_phone: {nothing: 1}"))

    def test_a_role_default_needs_its_question(self):
        no_node = FLOW_OK.replace("on_yes: book, on_no: ask_v}", "on_yes: book, on_no: ask_v}").replace(
            "role_default: visitor, ", "")
        with self.assertRaisesRegex(FlowError, "role_default"):
            load(no_node)
        with self.assertRaisesRegex(FlowError, "needs a role with a `default`"):
            load(FLOW_OK.replace("role_default: visitor", "role_default: booker"))

    def test_default_source_must_be_another_role_of_the_same_type(self):
        with self.assertRaisesRegex(FlowError, "another role of the same type"):
            load(FLOW_OK.replace("default: {from: booker}", "default: {from: visitor}"))

    def test_old_args_still_load(self):
        # the shipped flows use `args`; they load next to roles in the same pack
        self.assertIn("balance_inquiry", build_manager(DEFAULT_DOMAINS_DIR, "bank", "en",
                                                       FakeApiExecutor.from_yaml(TOOLS)).flows)


class RuntimeTest(unittest.TestCase):
    def manager(self, lang="en"):
        return build_manager(DEFAULT_DOMAINS_DIR, "bank", lang, FakeApiExecutor.from_yaml(TOOLS))

    def test_the_visitor_is_the_booker_after_a_yes(self):
        m = self.manager()
        r = turns(m, m.initial_state("t", {}), Utterance("book a visit", source="typed"), Dtmf("5580"),
                  Utterance("yes", source="typed"))
        self.assertEqual(r.state.slots["visitor.phone_last4"], "5580")
        self.assertEqual(r.state.slots["booker.phone_last4"], "5580")
        self.assertIn("5580", r.reply)

    def test_the_visitor_is_asked_after_a_no(self):
        m = self.manager("ko")
        r = turns(m, m.initial_state("t", {}), Utterance("지점 방문 예약할게요", source="typed"), Dtmf("5580"),
                  Utterance("아니요", source="typed"))
        self.assertIn("방문하실 분", r.reply)
        self.assertNotIn("visitor.phone_last4", r.state.slots)
        r = step(m, r.state, Dtmf("7310"))
        self.assertEqual(r.state.slots["visitor.phone_last4"], "7310")
        self.assertEqual(r.state.slots["booker.phone_last4"], "5580")
        self.assertEqual(r.trace["calls"][-1]["args"], {"booker_phone": "5580", "visitor_phone": "7310"})

    def test_caller_is_filled_by_the_identity_check(self):
        m = self.manager()
        r = turns(m, m.initial_state("t", {}), Utterance("when is my visit", source="typed"), Dtmf("4821"), Dtmf("2468"))
        self.assertEqual(r.state.meta["caller"], {"account_last4": "4821"})
        self.assertIn("BV0420", r.reply)

    def test_a_binding_to_an_earlier_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(DEFAULT_DOMAINS_DIR, tmp, dirs_exist_ok=True)
            flows = os.path.join(tmp, "bank", "en", "flows")
            with open(os.path.join(flows, "book_visit.yaml"), "w", encoding="utf-8", newline="\n") as f:
                f.write("""id: book_visit
triggers: {all_of: [[book], [visit]]}
start: fee
nodes:
  fee:
    type: call
    tool: get_transfer_fee
    bind:
      amount: {const: "100"}
      grade: {const: gold}
    on_ok: book
  book:
    type: call
    tool: book_visit
    bind:
      booker_phone: {call: fee, field: currency}
      visitor_phone: {call: fee, field: fee}
    on_ok: done
  done: {type: end}
""")
            m = build_manager(tmp, "bank", "en", FakeApiExecutor.from_yaml(os.path.join(tmp, "bank", "tools.yaml")))
            r = step(m, m.initial_state("t", {}), Utterance("book a visit", source="typed"))
            calls = r.trace["calls"]
            self.assertEqual(calls[-1]["args"], {"booker_phone": "USD", "visitor_phone": "0"})


if __name__ == "__main__":
    unittest.main()
