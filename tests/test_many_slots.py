"""R10: captures on every turn, cue words, duration, the form node. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import step
from voxstage.domain_pack import AskPolicy, DomainPack, Fallback, parse_pattern
from voxstage.evaluate import RecordingTools
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import ASK_MISSES, FlowManager, cue_windows
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")

TOOLS = """
tools:
  change:
    params: [qty, order_id, size]
    risky: true
    default: {return: {ok: true}}
"""

FLOW = """
    id: change
    triggers: {any_of: [change]}
    captures: {size: {extractor: choice, choices: [small, medium, large]},
               order_id: {extractor: digits, length: 4, cue: [order, 주문]}}
    start: ask_qty
    nodes:
      ask_qty: {type: ask, slot: qty, prompt: "How many?", extractor: number, next: ask_order}
      ask_order: {type: ask, slot: order_id, prompt: "Order number?", extractor: digits, length: 4, next: confirm}
      confirm: {type: confirm, prompt: "Change order {order_id} to {qty} in {size | default('any size')}?", on_yes: call, on_no: done}
      call: {type: call, tool: change, args: {qty: "{qty}", order_id: "{order_id}", size: "{size | default('')}"}, on_ok: done, on_error: done}
      done: {type: end}
"""


def build(tmp, flow=FLOW):
    with open(os.path.join(tmp, "tools.yaml"), "w", encoding="utf-8") as f:
        f.write(TOOLS)
    flows = os.path.join(tmp, "flows")
    os.makedirs(flows, exist_ok=True)
    with open(os.path.join(flows, "change.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(flow))
    pack = DomainPack("shop", "en", {}, (), Fallback("sorry", "bye"), "", "", None,
                      AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset(),
                      confirm_words=(("yes",), ("no",)))
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(tmp, "tools.yaml")))
    return FlowManager(pack, tools, load_flows(flows, os.path.join(tmp, "tools.yaml"))), tools


def talk(m, *inputs):
    state, out = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        out.append(r)
    return out


class CueTest(unittest.TestCase):
    def test_windows_around_a_cue(self):
        self.assertEqual(cue_windows("return it from order 1001 please", ("order",)), ["it from order 1001 please"])
        self.assertEqual(cue_windows("5580으로 끝나는 번호에 해외 로밍", ("끝나는",)), ["5580으로 끝나는 번호에 해외"])
        self.assertEqual(cue_windows("천일 주문에서 산 재킷", ("주문",)), ["천일 주문에서 산 재킷"])   # a particle after the cue
        self.assertEqual(cue_windows("no cue here 1001", ("order",)), [])

    def test_a_cued_capture_on_the_first_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            r, = talk(m, Utterance("change order 1001 to large"))
        self.assertEqual((r.state.slots, r.state.node_id), ({"order_id": "1001", "size": "large"}, "ask_qty"))

    def test_without_its_cue_a_number_is_not_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            r, = talk(m, Utterance("change 1001"))
        self.assertEqual(r.state.slots, {})

    def test_bad_cue_is_a_load_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FlowError):
                build(tmp, FLOW.replace("choices: [small, medium, large]}", "choices: [small, medium, large], cue: [size]}"))


class LaterTurnTest(unittest.TestCase):
    def test_a_bare_number_never_fills_another_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            *_, r = talk(m, Utterance("change it"), Utterance("2"), Utterance("1001"))
        self.assertEqual((r.state.slots, r.state.node_id), ({"qty": "2", "order_id": "1001"}, "confirm"))

    def test_another_slot_at_an_ask_is_taken_and_the_question_asked_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("change it"), Utterance("make it medium"))
        self.assertEqual((r.state.slots, r.state.node_id, r.reply), ({"size": "medium"}, "ask_qty", "How many?"))
        self.assertEqual((r.trace["captured"], r.state.meta.get(ASK_MISSES, 0)), ({"size": "medium"}, 0))

    def test_an_answer_and_a_choice_word_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("change it"), Utterance("3 in large"))
        self.assertEqual((r.state.slots, r.state.node_id), ({"qty": "3", "size": "large"}, "ask_order"))

    def test_the_asked_slot_takes_a_number_first_even_with_a_cue(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, _ = build(tmp)
            _, r = talk(m, Utterance("change it"), Utterance("it is order 1001"))
        self.assertEqual(r.state.slots, {"qty": "1001"})   # asked first (R10-1): a finding, not a feature

    def test_a_cued_number_at_a_confirm_changes_its_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, r = talk(m, Utterance("change it"), Utterance("2"), Dtmf("1001"), Utterance("sorry it is order 1002"))
        self.assertEqual((r.state.slots["order_id"], r.state.node_id, tools.records), ("1002", "confirm", []))

    def test_a_change_at_the_confirm_asks_the_confirm_again_without_a_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            m, tools = build(tmp)
            *_, c, r = talk(m, Utterance("change it in medium"), Utterance("2"), Dtmf("1001"), Utterance("actually make it large"))
        self.assertEqual(c.reply, "Change order 1001 to 2 in medium?")
        self.assertEqual((r.reply, r.state.node_id, tools.records), ("Change order 1001 to 2 in large?", "confirm", []))
        *_, r = talk(m, Utterance("change it in medium"), Utterance("2"), Dtmf("1001"), Utterance("make it large"), Utterance("yes"))
        self.assertEqual([x["args"]["size"] for x in tools.records], ["large"])


FORM = """
    id: ret
    triggers: {any_of: [return]}
    captures: {item: {extractor: choice, choices: [laptop, shirt]},
               kind: {extractor: choice, choices: {laptop: electronics, shirt: clothing}}}
    start: collect
    nodes:
      collect:
        type: form
        slots:
          - {slot: order_id, prompt: "Order number?", extractor: digits, length: 4}
          - {slot: item, prompt: "Which item?", extractor: choice, choices: [laptop, shirt]}
        say_when_ready:
          - {needs: [kind], say: "Category {kind}."}
          - {needs: [item, order_id], say: "Got {item} from {order_id}."}
        next: done
      done: {type: end}
"""


def build_form(tmp, flow=FORM):
    flows = os.path.join(tmp, "flows")
    os.makedirs(flows, exist_ok=True)
    with open(os.path.join(flows, "ret.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(flow))
    tools = os.path.join(ROOT, "shop", "tools.yaml")
    commands = tuple(parse_pattern("t", {"id": n, "any_of": w}) for n, w in
                     (("cancel", ["cancel"]), ("back", ["go back"]), ("agent", ["agent"])))
    pack = DomainPack("shop", "en", {"ship": "Shipping takes 3 days."},
                      (parse_pattern("t", {"id": "ship", "any_of": ["shipping"]}),), Fallback("sorry", "bye"), "", "",
                      None, AskPolicy("not valid.", "keypad.", "giving up.", 2, "handoff"), frozenset(),
                      commands=commands, wording={"flow.no_flow": "Nothing."})
    return FlowManager(pack, FakeApiExecutor.from_yaml(tools), load_flows(flows, tools))


class FormTest(unittest.TestCase):
    def test_item_known_first_says_its_part_at_once_then_asks_what_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build_form(tmp)
            a, b = talk(m, Utterance("return a laptop"), Dtmf("1001"))
        self.assertEqual(a.reply, "Category electronics. Order number?")
        self.assertEqual((b.reply, b.state.node_id), ("Got laptop from 1001.", "done"))

    def test_nothing_known_asks_in_order_and_says_each_part_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build_form(tmp)
            a, b, c = talk(m, Utterance("return something"), Dtmf("1001"), Utterance("the shirt"))
        self.assertEqual((a.reply, b.reply), ("Order number?", "Which item?"))
        self.assertEqual(c.reply, "Category clothing. Got shirt from 1001.")

    def test_back_inside_a_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build_form(tmp)
            *_, r = talk(m, Utterance("return something"), Dtmf("1001"), Utterance("go back"))
        self.assertEqual((r.reply, r.state.slots), ("Order number?", {"order_id": "1001"}))
        *_, r = talk(m, Utterance("return something"), Dtmf("1001"), Utterance("go back"), Dtmf("2002"))
        self.assertEqual((r.reply, r.state.slots["order_id"]), ("Which item?", "2002"))

    def test_a_side_question_inside_a_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build_form(tmp)
            _, r = talk(m, Utterance("return something"), Utterance("how long does shipping take"))
        self.assertEqual((r.reply, r.state.node_id), ("Shipping takes 3 days. Order number?", "collect"))

    def test_an_invalid_answer_inside_a_form_is_reprompted(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = build_form(tmp)
            _, r = talk(m, Utterance("return something"), Utterance("hmm"))
        self.assertEqual((r.reply, r.state.meta[ASK_MISSES]), ("not valid. Order number?", 1))

    def test_load_errors(self):
        bad = [FORM.replace("""        slots:
          - {slot: order_id, prompt: "Order number?", extractor: digits, length: 4}
          - {slot: item, prompt: "Which item?", extractor: choice, choices: [laptop, shirt]}""", "        slots: []"),
               FORM.replace('extractor: digits, length: 4}', 'extractor: digits, length: 4, next: done}'),
               FORM.replace("needs: [kind]", "needs: [colour]"),
               FORM.replace('say: "Category {kind}."', 'shout: "Category."'),
               FORM.replace("{slot: item, prompt", "{slot: order_id, prompt")]
        for text in bad:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(FlowError, msg=text[:60]):
                    build_form(tmp, text)


if __name__ == "__main__":
    unittest.main()
