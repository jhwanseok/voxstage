"""R2: expression language, flow validation and the interpreter. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import dataset
from voxstage.dialogue import EndCall, HandOff, step
from voxstage.domain_pack import DomainPack
from voxstage.evaluate import RecordingTools
from voxstage.rules import flows as flowmod
from voxstage.rules import interpreter
from voxstage.rules.expr import ExprError, compile_expr
from voxstage.rules.flows import FlowError, compile_template, load_flow, load_flows, tool_params
from voxstage.rules.interpreter import FlowManager, build_manager
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import ButtonPress, Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")
needs_kiwi = unittest.skipUnless(kiwi_available(), "kiwipiepy missing: pip install 'voxstage[ko]'")


class ExprTest(unittest.TestCase):
    def ev(self, src, env=None, names=frozenset()):
        return compile_expr(src, "t", names).evaluate(env or {})

    def test_allowed_forms(self):
        env = {"customer": {"tier": "gold"}, "result": {"fee": 5, "items": [1, 2, 3]}, "policy": {}, "amount": "500"}
        names = frozenset({"amount"})
        self.assertTrue(self.ev("customer.tier == 'gold' and result.fee < 10", env, names))
        self.assertEqual(self.ev("int(amount) * 2 + 1", env, names), 1001)
        self.assertEqual(self.ev("result.items[1]", env), 2)
        self.assertEqual(self.ev("'a' if result.fee > 9 else 'b'", env), "b")
        self.assertTrue(self.ev("customer.tier in ['gold', 'silver']", env))
        self.assertTrue(self.ev("not (1 > 2) or None", env))
        self.assertEqual(self.ev("len(lower(customer.tier))", env), 4)
        self.assertEqual(self.ev("7 // 2 + 7 % 4 - 1 / 2", env), 5.5)
        self.assertTrue(self.ev("1 < 2 < 3", env))

    def test_every_disallowed_form_is_rejected_at_load(self):
        for bad in ("lambda: 1", "[x for x in result.items]", "{x: 1}", "{1, 2}", "result.items()", "customer.__class__",
                    "open('f')", "__import__('os')", "x := 1", "f'{amount}'", "result.fee ** 2", "a & b",
                    "result.items[0:2]", "result[amount]", "len(*result)", "unknown_name", "len", "b'bytes'", "..."):
            with self.assertRaises(ExprError, msg=bad):
                compile_expr(bad, "t", frozenset({"amount", "a", "b"}))
        for bad_statement in ("import os", "x = 1", "del x"):  # not expressions at all
            with self.assertRaises(ExprError, msg=bad_statement):
                compile_expr(bad_statement, "t")

    def test_runtime_problems_name_the_expression(self):
        with self.assertRaises(ExprError) as cm:
            self.ev("result.fee", {"result": {}})
        self.assertIn("no field `fee`", str(cm.exception))
        with self.assertRaises(ExprError):
            self.ev("1 // 0")
        with self.assertRaises(ExprError):
            self.ev("amount", {}, frozenset({"amount"}))  # a slot not filled yet

    def test_error_message_gives_location(self):
        with self.assertRaises(ExprError) as cm:
            compile_expr("1 + lambda: 2", "flow.yaml: node n.cases[0]")
        self.assertIn("flow.yaml: node n.cases[0]", str(cm.exception))
        self.assertIn("column", str(cm.exception))


class TemplateTest(unittest.TestCase):
    def test_fields_and_literal_braces(self):
        t = compile_template("Hi {name}, {{literal}} {n + 1}!", "t", frozenset({"name", "n"}))
        self.assertEqual(t.render({"name": "Ann", "n": 1}), "Hi Ann, {literal} 2!")

    def test_bad_templates(self):
        for bad in ("{open", "close}", "{bad name}", "{lambda: 1}"):
            with self.assertRaises(FlowError, msg=bad):
                compile_template(bad, "t", frozenset())


def write_flow(tmp, name, body):
    path = os.path.join(tmp, f"{name}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return path


GOOD = """
    id: {id}
    triggers: {{any_of: [balance]}}
    start: ask
    nodes:
      ask: {{type: ask, slot: acct, prompt: "Which?", extractor: digits, length: 4, next: look}}
      look: {{type: call, tool: get_balance, args: {{account_last4: "{{acct}}"}}, on_ok: say, on_error: say}}
      say: {{type: say, text: "{{result.balance}}", next: done}}
      done: {{type: end}}
"""


class FlowValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tools = tool_params(BANK_TOOLS)

    def load(self, body, name="f"):
        return load_flow(write_flow(self.tmp.name, name, body), self.tools)

    def mutate(self, old, new):
        body = GOOD.format(id="f")
        assert old in body, old
        return body.replace(old, new)

    def test_a_good_flow_loads(self):
        flow = self.load(GOOD.format(id="f"))
        self.assertEqual((flow.id, flow.start, sorted(flow.nodes)), ("f", "ask", ["ask", "done", "look", "say"]))

    def test_one_failing_example_per_check(self):
        cases = {
            "unknown node type": self.mutate("type: say", "type: shout"),
            "missing next target": self.mutate("next: done}\n      done", "next: nowhere}\n      done"),
            "start missing": self.mutate("start: ask", "start: nowhere"),
            "unreachable node": GOOD.format(id="f") + "      orphan: {type: end}\n",
            "no end node": self.mutate("done: {type: end}", "done: {type: goto, next: ask}"),
            "unknown tool": self.mutate("tool: get_balance", "tool: get_nothing"),
            "wrong tool args": self.mutate("account_last4:", "wrong:"),
            "bad extractor": self.mutate("extractor: digits", "extractor: magic"),
            "length without digits": self.mutate("extractor: digits", "extractor: text"),
            "unknown name in template": self.mutate('"{result.balance}"', '"{nobody}"'),
            "bad expression": self.mutate('"{result.balance}"', '"{lambda: 1}"'),
            "unknown key": self.mutate("type: end}", "type: end, color: red}"),
            "say without text": self.mutate('text: "{result.balance}", ', ""),
            "bad end action": self.mutate("done: {type: end}", "done: {type: end, action: dance}"),
            "extra top-level key": GOOD.format(id="f") + "extra: 1\n",
            "triggers without words": self.mutate("{any_of: [balance]}", "{}"),
        }
        for label, body in cases.items():
            with self.assertRaises(FlowError, msg=label):
                self.load(body)

    def test_branch_needs_else_and_loops_must_wait(self):
        branch = """
            id: b
            triggers: {any_of: [x]}
            start: pick
            nodes:
              pick: {type: branch, cases: [{when: "1 == 1", next: done}]}
              done: {type: end}
        """
        with self.assertRaises(FlowError):
            self.load(branch, "b")
        loop = """
            id: l
            triggers: {any_of: [x]}
            start: a
            nodes:
              a: {type: branch, cases: [{when: "1 == 1", next: b}], else: done}
              b: {type: goto, next: a}
              done: {type: end}
        """
        with self.assertRaises(FlowError) as cm:
            self.load(loop, "l")
        self.assertIn("loop without waiting", str(cm.exception))
        ok_loop = """
            id: w
            triggers: {any_of: [x]}
            start: a
            nodes:
              a: {type: ask, slot: s, prompt: "again?", next: b}
              b: {type: goto, next: a}
              done: {type: end}
        """
        with self.assertRaises(FlowError) as cm:   # a loop that waits is fine, but `done` is unreachable here
            self.load(ok_loop, "w")
        self.assertIn("unreachable", str(cm.exception))

    def test_file_name_must_be_the_flow_id(self):
        with self.assertRaises(FlowError):
            self.load(GOOD.format(id="other"), "f")


class RegistryTest(unittest.TestCase):
    def test_a_new_node_type_needs_no_change_to_the_loop(self):
        @flowmod.register_node_type("shout", edges=lambda d: [d["next"]])
        def compile_shout(raw, ctx):
            return {"text": ctx.template(ctx.need(raw, "text"), "text"), "next": ctx.need(raw, "next")}

        @interpreter.handler("shout")
        def run_shout(run, node):
            run.out.append(node.data["text"].render(run.env()).upper())
            return node.data["next"]

        self.addCleanup(lambda: (flowmod.NODE_TYPES.pop("shout"), interpreter.HANDLERS.pop("shout")))
        with tempfile.TemporaryDirectory() as tmp:
            write_flow(tmp, "loud", """
                id: loud
                triggers: {any_of: [loud]}
                start: s
                nodes:
                  s: {type: shout, text: "hello", next: done}
                  done: {type: end}
            """)
            flows = load_flows(tmp, BANK_TOOLS)
            pack = DomainPack("bank", "en", {}, (), None)
            m = FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), flows)
            r = step(m, m.initial_state("s"), Utterance("be loud"))
            self.assertEqual(r.reply, "HELLO")

    def test_manager_refuses_a_node_type_without_a_handler(self):
        flowmod.register_node_type("mute", edges=lambda d: ["done"])(lambda raw, ctx: {})
        self.addCleanup(lambda: flowmod.NODE_TYPES.pop("mute"))
        with tempfile.TemporaryDirectory() as tmp:
            write_flow(tmp, "m", "id: m\ntriggers: {any_of: [m]}\nstart: a\nnodes:\n  a: {type: mute}\n  done: {type: end}\n")
            flows = load_flows(tmp, BANK_TOOLS)
            with self.assertRaises(FlowError):
                FlowManager(DomainPack("bank", "en", {}, (), None), FakeApiExecutor.from_yaml(BANK_TOOLS), flows)


def manager(domain, lang):
    tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, domain, "tools.yaml")))
    return build_manager(ROOT, domain, lang, tools), tools


def converse(m, *inputs):
    state, replies = m.initial_state("s"), []
    for i in inputs:
        r = step(m, state, i)
        state = r.state
        replies.append(r)
    return replies


class LookupFlowsTest(unittest.TestCase):
    LANGS = ("en", "ko") if kiwi_available() else ("en",)

    def test_bank_balance_en(self):
        m, tools = manager("bank", "en")
        a, b = converse(m, Utterance("what's my balance"), Utterance("4821"))
        self.assertIn("last four digits", a.reply)
        self.assertEqual((a.state.flow_id, a.state.node_id), ("balance_inquiry", "ask_account"))
        self.assertEqual(b.reply, "Your balance is 1250 USD.")
        self.assertEqual(tools.records, [{"name": "get_balance", "args": {"account_last4": "4821"}, "error": None}])
        self.assertEqual(b.state.slots, {"account_last4": "4821"})
        self.assertEqual(b.state.node_id, "done")

    def test_keypad_digits_fill_a_digits_slot(self):
        m, _ = manager("bank", "en")
        _, b = converse(m, Utterance("balance please"), Dtmf("7310"))
        self.assertIn("3000", b.reply)

    def test_wrong_input_asks_again_without_calling_the_api(self):
        m, tools = manager("bank", "en")
        a, b, c = converse(m, Utterance("my balance"), Utterance("I don't know"), Utterance("12"))
        self.assertTrue(b.reply.endswith(a.reply) and b.reply != a.reply)   # re-prompt wording + the question
        self.assertTrue(c.reply.endswith(a.reply))
        self.assertEqual(tools.records, [])
        self.assertEqual(c.state.node_id, "ask_account")

    def test_api_failure_says_so_and_invents_nothing(self):
        for domain, text, digits in (("bank", "my balance", "0000"), ("shop", "where is my order", "9999"),
                                     ("telecom", "how much data have I used", "0000")):
            m, tools = manager(domain, "en")
            _, b = converse(m, Utterance(text), Dtmf(digits))
            self.assertIn("unable", b.reply, domain)
            self.assertNotIn("$", b.reply)
            self.assertEqual(tools.records[0]["error"], "timeout")

    def test_shop_branches_on_the_status_the_api_returns(self):
        expected = {"1001": "shipped", "1002": "still being prepared", "1003": "delivered", }
        for order, word in expected.items():
            m, _ = manager("shop", "en")
            _, b = converse(m, Utterance("where is my order"), Utterance(order))
            self.assertIn(word, b.reply, order)
        m, _ = manager("shop", "en")
        _, b = converse(m, Utterance("where is my order"), Utterance("5555"))  # not_found -> honest failure
        self.assertIn("unable", b.reply)

    def test_telecom_usage_en(self):
        m, _ = manager("telecom", "en")
        a, b = converse(m, Utterance("how much data have I used"), Utterance("5580"))
        self.assertIn("last four digits", a.reply)
        self.assertEqual(b.reply, "You have used 12 GB of your 20 GB.")

    @needs_kiwi
    def test_korean_twins_answer_in_korean(self):
        cases = (("bank", "내 잔액 알려줘", "4821", ["네 자리"], "1250"),
                 ("shop", "제 주문 어디쯤 왔어요", "1001", ["주문번호"], "배송 중"),
                 ("telecom", "데이터 얼마나 남았어요", "5580", ["뒤 네 자리"], "12GB"))
        for domain, text, digits, ask_words, answer in cases:
            m, tools = manager(domain, "ko")
            a, b = converse(m, Utterance(text), Dtmf(digits))
            for w in ask_words:
                self.assertIn(w, a.reply, domain)
            self.assertIn(answer, b.reply, domain)
            self.assertEqual(len(tools.records), 1)

    @needs_kiwi
    def test_korean_failure_wording_matches_the_scenario_expectations(self):
        for domain, text, digits, must_not in (("bank", "잔액 확인", "0000", ["달러", "$"]),
                                               ("shop", "내 주문 어디까지 왔어요", "9999", ["배송 중", "배송 완료", "준비 중"]),
                                               ("telecom", "데이터 사용량 알려줘", "0000", ["기가", "GB"])):
            m, _ = manager(domain, "ko")
            _, b = converse(m, Utterance(text), Dtmf(digits))
            self.assertTrue(any(w in b.reply for w in ("다시 시도", "조회할 수 없", "확인할 수 없")), domain)
            for w in must_not:
                self.assertNotIn(w, b.reply, domain)

    def test_no_flow_falls_back_to_the_faq_rules(self):
        m, _ = manager("bank", "en")
        faq, _ = dataset.load_domain(os.path.join(ROOT, "bank"), "en")
        hours = next(e for e in faq if e.id == "bank.faq.hours")
        (r,) = converse(m, Utterance(hours.question))
        self.assertEqual(r.reply, hours.answer)
        (r,) = converse(m, Utterance("tell me a joke about penguins"))
        self.assertEqual(r.trace["rule"], "fallback")

    def test_canonical_faq_questions_never_start_a_flow(self):
        for domain in dataset.DOMAINS:
            for lang in self.LANGS:
                m, _ = manager(domain, lang)
                faq, _ = dataset.load_domain(os.path.join(ROOT, domain), lang)
                for e in faq:
                    self.assertIsNone(m.matcher.match(e.question)[0], (domain, lang, e.id))

    def test_a_finished_flow_can_start_again_and_state_is_not_mutated(self):
        m, _ = manager("bank", "en")
        s0 = m.initial_state("s")
        r1 = step(m, s0, Utterance("my balance"))
        r2 = step(m, r1.state, Dtmf("4821"))
        r3 = step(m, r2.state, Utterance("my balance"))
        self.assertEqual(r3.state.node_id, "ask_account")
        self.assertEqual((s0.flow_id, s0.slots), (None, {}))
        self.assertEqual(r1.state.slots, {})

    def test_other_inputs_outside_a_flow_do_not_crash(self):
        m, _ = manager("bank", "en")
        (r,) = converse(m, ButtonPress("menu_unknown"))
        self.assertEqual(r.trace["rule"], "fallback")  # a button no flow declares is a miss

    def test_end_node_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_flow(tmp, "bye", """
                id: bye
                triggers: {any_of: [bye]}
                start: s
                nodes:
                  s: {type: say, text: "Goodbye.", next: out}
                  out: {type: end, action: end_call}
            """)
            write_flow(tmp, "agent", """
                id: agent
                triggers: {any_of: [agent]}
                start: s
                nodes:
                  s: {type: say, text: "Connecting.", next: out}
                  out: {type: end, action: handoff, reason: asked_for_agent}
            """)
            flows = load_flows(tmp, BANK_TOOLS)
            m = FlowManager(DomainPack("bank", "en", {}, (), None), FakeApiExecutor.from_yaml(BANK_TOOLS), flows)
            (r,) = converse(m, Utterance("bye"))
            self.assertEqual(r.actions, (EndCall(),))
            (r,) = converse(m, Utterance("I want an agent"))
            self.assertEqual(r.actions, (HandOff("asked_for_agent"),))


class TwinFlowsTest(unittest.TestCase):
    @needs_kiwi
    def test_korean_and_english_flows_share_structure(self):
        for domain in dataset.DOMAINS:
            en = load_flows(os.path.join(ROOT, domain, "en", "flows"), os.path.join(ROOT, domain, "tools.yaml"))
            ko = load_flows(os.path.join(ROOT, domain, "ko", "flows"), os.path.join(ROOT, domain, "tools.yaml"))
            self.assertEqual(sorted(en), sorted(ko), domain)
            for fid, fe in en.items():
                fk = ko[fid]
                self.assertEqual(fe.start, fk.start)
                self.assertEqual(sorted(fe.nodes), sorted(fk.nodes), fid)
                for nid, ne in fe.nodes.items():
                    nk = fk.nodes[nid]
                    self.assertEqual(ne.type, nk.type, f"{fid}.{nid}")
                    edges = flowmod.NODE_TYPES[ne.type].edges
                    self.assertEqual(edges(ne.data), edges(nk.data), f"{fid}.{nid}")
                    if ne.type == "call":
                        self.assertEqual(ne.data["tool"], nk.data["tool"])
                        self.assertEqual(sorted(ne.data["args"]), sorted(nk.data["args"]))
                    if ne.type == "ask":
                        self.assertEqual((ne.data["slot"], ne.data["extractor"], ne.data["length"]),
                                         (nk.data["slot"], nk.data["extractor"], nk.data["length"]))
                    if ne.type == "branch":
                        self.assertEqual([c.source for c, _ in ne.data["cases"]], [c.source for c, _ in nk.data["cases"]])


if __name__ == "__main__":
    unittest.main()
