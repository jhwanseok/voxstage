"""R5: the notices registry, the `notices` node, situation wording. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.dialogue import HandOff, step
from voxstage.domain_pack import WORDING_KEYS, DomainPack, Fallback, RuleError, load_registry
from voxstage.evaluate import RecordingTools
from voxstage.rules.faq import FaqRuleManager
from voxstage.rules.flows import FlowError, load_flows
from voxstage.rules.interpreter import FlowManager, build_manager
from voxstage.rules.tokenize import kiwi_available
from voxstage.tools import FakeApiExecutor
from voxstage.turn import Dtmf, Utterance

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")
needs_kiwi = unittest.skipUnless(kiwi_available(), "kiwipiepy missing: pip install 'voxstage[ko]'")

WORDING = "\n".join(f"  {k}: \"w:{k}\"" for k in WORDING_KEYS)


def registry(tmp, notices_yaml, wording=WORDING):
    path = os.path.join(tmp, "notices.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("notices:\n" + textwrap.indent(textwrap.dedent(notices_yaml), "  ") + "\nwording:\n" + wording + "\n")
    return path


TWO = """
    late: {fixed: true, priority: 20, text: "Second.", applies_when: "kind == 'x'"}
    early: {fixed: true, priority: 10, text: "First."}
"""
FLOW = """
    id: n
    triggers: {any_of: [go]}
    captures: {kind: {extractor: choice, choices: [x, y]}}
    start: ask
    nodes:
      ask: {type: ask, slot: kind, prompt: "Which?", extractor: choice, choices: [x, y], next: say}
      say: {type: notices, next: done}
      done: {type: end}
"""


def manager(tmp, notices_yaml=TWO, flow=FLOW):
    notices, wording = load_registry(registry(tmp, notices_yaml))
    os.makedirs(os.path.join(tmp, "flows"), exist_ok=True)
    with open(os.path.join(tmp, "flows", "n.yaml"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(flow))
    flows = load_flows(os.path.join(tmp, "flows"), BANK_TOOLS, frozenset(), notices)
    pack = DomainPack("bank", "en", {}, (), Fallback("s", "b"), notices=notices, wording=wording)
    return FlowManager(pack, FakeApiExecutor.from_yaml(BANK_TOOLS), flows)


class RegistryFileTest(unittest.TestCase):
    def test_notices_come_back_in_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            notices, wording = load_registry(registry(tmp, TWO))
            self.assertEqual([n.id for n in notices], ["early", "late"])
            self.assertEqual(wording["fallback.miss"], "w:fallback.miss")

    def test_one_failing_example_per_check(self):
        base = 'a: {fixed: true, priority: 1, text: "A."}\n'
        cases = {
            "not marked fixed": 'a: {fixed: false, priority: 1, text: "A."}\n',
            "fixed missing": 'a: {priority: 1, text: "A."}\n',
            "priority missing": 'a: {fixed: true, text: "A."}\n',
            "same priority": base + 'b: {fixed: true, priority: 1, text: "B."}\n',
            "empty text": 'a: {fixed: true, priority: 1, text: " "}\n',
            "unknown key": 'a: {fixed: true, priority: 1, text: "A.", color: red}\n',
            "bad priority": 'a: {fixed: true, priority: first, text: "A."}\n',
        }
        for label, body in cases.items():
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(RuleError, msg=label):
                load_registry(registry(tmp, body))

    def test_every_situation_key_is_required_and_nothing_else_is_allowed(self):
        base = 'a: {fixed: true, priority: 1, text: "A."}\n'
        missing = "\n".join(f"  {k}: x" for k in WORDING_KEYS[1:])
        extra = WORDING + "\n  made.up: x"
        for wording in (missing, extra):
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(RuleError):
                load_registry(registry(tmp, base, wording))


class NoticeNodeTest(unittest.TestCase):
    def test_all_applicable_notices_are_said_in_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manager(tmp)
            r = step(m, m.initial_state("s"), Utterance("go x"))
            self.assertEqual(r.reply, "First. Second.")
            self.assertEqual(r.trace["notices"], ["early", "late"])

    def test_a_notice_whose_condition_fails_is_not_said(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manager(tmp)
            r = step(m, m.initial_state("s"), Utterance("go y"))
            self.assertEqual(r.reply, "First.")

    def test_notice_text_is_literal_not_a_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manager(tmp, 'a: {fixed: true, priority: 1, text: "Pay {amount} now."}\n')
            r = step(m, m.initial_state("s"), Utterance("go x"))
            self.assertEqual(r.reply, "Pay {amount} now.")

    def test_unknown_id_or_unknown_name_in_a_condition_fails_at_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FlowError):
                manager(tmp, flow=FLOW.replace("type: notices,", "type: notices, ids: [nope],"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FlowError):
                manager(tmp, 'a: {fixed: true, priority: 1, text: "A.", applies_when: "nobody == 1"}\n')

    def test_ids_limit_the_notices_a_flow_can_say(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manager(tmp, flow=FLOW.replace("type: notices,", "type: notices, ids: [late],"))
            r = step(m, m.initial_state("s"), Utterance("go x"))
            self.assertEqual(r.reply, "Second.")


class WordingTest(unittest.TestCase):
    def test_fallback_and_ask_use_the_registry_wording(self):
        pack = DomainPack.load(ROOT, "bank", "en")
        self.assertEqual(pack.fallback.reply, pack.wording["fallback.miss"])
        self.assertEqual(pack.fallback.exceed_reply, pack.wording["fallback.exceed"])
        self.assertEqual((pack.ask.invalid_reply, pack.ask.keypad_reply, pack.ask.exceed_reply),
                         (pack.wording["ask.invalid"], pack.wording["ask.keypad_only"], pack.wording["ask.exceed"]))
        self.assertEqual(pack.missing_reply, pack.wording["flow.attribute_missing"])
        m = FaqRuleManager(pack)
        r = step(m, m.initial_state("s"), Utterance("zzz qqq"))
        self.assertEqual(r.reply, pack.wording["fallback.miss"])

    def test_changing_the_registry_changes_what_is_said_with_no_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "bank", "en", "rules")
            os.makedirs(base)
            os.makedirs(os.path.join(tmp, "bank", "en", "scenarios"))
            os.makedirs(os.path.join(tmp, "bank", "ko"))
            import shutil
            shutil.copy(os.path.join(ROOT, "bank", "en", "faq.yaml"), os.path.join(tmp, "bank", "en", "faq.yaml"))
            shutil.copy(os.path.join(ROOT, "bank", "en", "rules", "config.yaml"), base)
            shutil.copy(os.path.join(ROOT, "bank", "en", "rules", "faq_patterns.yaml"), base)
            shutil.copy(BANK_TOOLS, os.path.join(tmp, "bank", "tools.yaml"))
            registry(os.path.join(tmp, "bank", "en"), 'a: {fixed: true, priority: 1, text: "A."}\n',
                     WORDING.replace('"w:fallback.miss"', '"Pardon?"'))
            pack = DomainPack.load(tmp, "bank", "en")
            r = step(FaqRuleManager(pack), FaqRuleManager(pack).initial_state("s"), Utterance("zzz qqq"))
            self.assertEqual(r.reply, "Pardon?")

    def test_no_flow_wording_is_used_when_nothing_matches(self):
        m = build_manager(ROOT, "bank", "en", FakeApiExecutor.from_yaml(BANK_TOOLS))
        m.faq = None
        r = step(m, m.initial_state("s"), Utterance("zzz qqq"))
        self.assertEqual(r.reply, m.pack.wording["flow.no_flow"])

    def test_both_languages_have_the_same_notice_ids_and_situation_keys(self):
        for d in ("bank", "shop", "telecom"):
            en, ko = DomainPack.load(ROOT, d, "en"), DomainPack.load(ROOT, d, "ko")
            self.assertEqual([n.id for n in en.notices], [n.id for n in ko.notices], d)
            self.assertEqual([(n.priority, n.applies_when) for n in en.notices],
                             [(n.priority, n.applies_when) for n in ko.notices], d)
            self.assertEqual(sorted(en.wording), sorted(ko.wording), d)


class ShippedNoticesTest(unittest.TestCase):
    def talk(self, domain, lang, text, *more):
        tools = RecordingTools(FakeApiExecutor.from_yaml(os.path.join(ROOT, domain, "tools.yaml")))
        m = build_manager(ROOT, domain, lang, tools)
        r = step(m, m.initial_state("s"), Utterance(text))
        for t in more:
            r = step(m, r.state, Utterance(t))
        return m, r

    def test_the_notice_is_said_exactly_as_registered_when_it_applies(self):
        for domain, text in (("bank", "I want to open a time deposit"), ("shop", "I want to return a laptop"),
                             ("telecom", "I want to downgrade to the basic plan")):
            m, r = self.talk(domain, "en", text)
            self.assertEqual(len(m.pack.notices), 1)
            self.assertIn(m.pack.notices[0].text, r.reply, domain)

    def test_the_notice_is_absent_when_the_condition_does_not_hold(self):
        for domain, text in (("bank", "I want to open a checking account"), ("shop", "I want to return a t-shirt"),
                             ("telecom", "I want to upgrade to the plus plan")):
            m, r = self.talk(domain, "en", text)
            self.assertNotIn(m.pack.notices[0].text, r.reply, domain)

    def test_the_caller_is_asked_when_the_condition_depends_on_a_missing_word(self):
        m, a = self.talk("shop", "en", "I want to return something")
        self.assertEqual(a.reply, "What would you like to return?")
        r = step(m, a.state, Utterance("my laptop"))
        self.assertIn(m.pack.notices[0].text, r.reply)

    @needs_kiwi
    def test_korean_notices(self):
        for domain, text, applies in (("bank", "정기예금 가입하고 싶어요", True), ("bank", "입출금 통장 만들고 싶어요", False),
                                      ("shop", "노트북 반품하려고 하는데요", True), ("shop", "티셔츠 반품할게요", False),
                                      ("telecom", "기본 요금제로 낮추고 싶어요", True), ("telecom", "플러스 요금제로 올리고 싶어요", False)):
            m, r = self.talk(domain, "ko", text)
            self.assertEqual(m.pack.notices[0].text in r.reply, applies, (domain, text))


if __name__ == "__main__":
    unittest.main()
