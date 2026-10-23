"""R9: read-back, corrections and the confusion table. Run: python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.domain_pack import (PLACEHOLDER_KEYS, CorrectionPolicy, DomainPack, RuleError, load_confusions,
                                  load_correction, load_correction_policy, load_readback_slots, load_registry)

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


def write(tmp, name, text) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class FilesTest(unittest.TestCase):
    def test_readback_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, "r.yaml", "readback_slots:\n  amount: \"money('USD')\"\n  quantity: count\n")
            self.assertEqual(load_readback_slots(ok), {"amount": "money('USD')", "quantity": "count"})
            for bad in ("readback_slots:\n  amount: loud\n", "slots: {}\n", "readback_slots: [amount]\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_readback_slots(write(tmp, "r.yaml", bad))

    def test_corrections_and_confusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_correction(write(tmp, "c.yaml", "correction: {any_of: [wrong]}\n")).id, "correction")
            for bad in ("fix: {any_of: [wrong]}\n", "correction: [wrong]\n", "correction: {priority: 1}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_correction(write(tmp, "c.yaml", bad))
            table = load_confusions(write(tmp, "p.yaml", "pairs: [[13, 30], [15, 50]]\n"))
            self.assertEqual(table, {"13": "30", "30": "13", "15": "50", "50": "15"})
            for bad in ("pairs: [[13, 30], [30, 3]]\n", "pairs: [[13]]\n", "pairs: [[13, 13]]\n", "pairs: [[a, b]]\n",
                        "table: []\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_confusions(write(tmp, "p.yaml", bad))

    def test_correction_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_correction_policy(write(tmp, "c.yaml", "fallback: {}\n")), CorrectionPolicy(2, "handoff"))
            self.assertEqual(load_correction_policy(write(tmp, "c.yaml", "correction: {max_corrections: 1, on_exceed: end_call}\n")),
                             CorrectionPolicy(1, "end_call"))
            for bad in ("correction: {max: 1}\n", "correction: {max_corrections: -1}\n", "correction: {on_exceed: wait}\n"):
                with self.assertRaises(RuleError, msg=bad):
                    load_correction_policy(write(tmp, "c.yaml", bad))

    def test_every_pack_has_the_r9_files(self):
        expected = {"bank": {"amount"}, "shop": {"quantity"}, "telecom": {"plan_gb"}}
        for d in ("bank", "shop", "telecom"):
            for lang in ("en", "ko"):
                pack = DomainPack.load(ROOT, d, lang)
                self.assertEqual(set(pack.readback), expected[d])
                self.assertIsNotNone(pack.correction)
                self.assertEqual(pack.confusions["13"], "30")
                for key in PLACEHOLDER_KEYS:
                    self.assertIn("{value}", pack.wording[key])

    def test_placeholder_wording_must_have_value(self):
        with open(os.path.join(ROOT, "bank", "en", "notices.yaml"), encoding="utf-8") as f:
            text = f.read().replace('readback: "{value}."', 'readback: "Got it."')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuleError) as cm:
                load_registry(write(tmp, "n.yaml", text))
        self.assertIn("readback", str(cm.exception))

    def test_a_pack_without_corrections_does_not_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(ROOT, "bank"), os.path.join(tmp, "bank"))
            os.remove(os.path.join(tmp, "bank", "en", "rules", "corrections.yaml"))
            with self.assertRaises(RuleError):
                DomainPack.load(tmp, "bank", "en")


if __name__ == "__main__":
    unittest.main()
