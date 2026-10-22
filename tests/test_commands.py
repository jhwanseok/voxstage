"""R8: global commands cancel, back and agent. Run: python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.domain_pack import COMMANDS, WORDING_KEYS, DomainPack, RuleError, load_commands
from voxstage.rules.flows import FlowError, load_flows

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")
BANK_TOOLS = os.path.join(ROOT, "bank", "tools.yaml")


def write(tmp, text) -> str:
    path = os.path.join(tmp, "commands.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text))
    return path


class CommandsFileTest(unittest.TestCase):
    def test_exactly_three_commands_as_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, "cancel: {any_of: [cancel]}\nback: {any_of: [back]}\nagent: {any_of: [agent], priority: 2}\n")
            cancel, back, agent = load_commands(ok)
            self.assertEqual((cancel.id, back.id, agent.id, agent.priority), ("cancel", "back", "agent", 2))
            for bad in ("cancel: {any_of: [x]}\nback: {any_of: [y]}\n",
                        "cancel: {any_of: [x]}\nback: {any_of: [y]}\nagent: {any_of: [z]}\nhelp: {any_of: [h]}\n",
                        "cancel: [x]\nback: {any_of: [y]}\nagent: {any_of: [z]}\n",
                        "cancel: {priority: 1}\nback: {any_of: [y]}\nagent: {any_of: [z]}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_commands(write(tmp, bad))

    def test_every_pack_has_commands_and_their_wording(self):
        self.assertTrue({"command.cancelled", "command.agent"} <= set(WORDING_KEYS))
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                pack = DomainPack.load(ROOT, d, lang)
                self.assertEqual(tuple(p.id for p in pack.commands), COMMANDS)
                self.assertTrue(pack.wording["command.cancelled"] and pack.wording["command.agent"])

    def test_a_pack_without_commands_does_not_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(ROOT, "bank"), os.path.join(tmp, "bank"))
            os.remove(os.path.join(tmp, "bank", "en", "rules", "commands.yaml"))
            with self.assertRaises(RuleError):
                DomainPack.load(tmp, "bank", "en")

    def test_main_menu_is_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "main_menu.yaml"), "w", encoding="utf-8") as f:
                f.write("id: main_menu\ntriggers: {any_of: [menu]}\nstart: done\nnodes:\n  done: {type: end}\n")
            with self.assertRaises(FlowError) as cm:
                load_flows(tmp, BANK_TOOLS)
        self.assertIn("reserved", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
