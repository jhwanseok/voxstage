"""R15: the complexity curve. Run: python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage import complexity, dataset

LEDGER = """# Effort ledger

| Step | Commit | Domain | Lang | Flow YAML lines | Flow nodes | Patterns | Regex patterns | Interpreter lines | Other rule-code lines | Rule-file entries | Normalize lines |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | aaa1111 | bank | en | 0 | 0 | 8 | 0 | 0 | 148 | - | - |
| R1 | aaa1111 | shop | en | 0 | 0 | 8 | 0 | 0 | 148 | - | - |
| R2 | bbb2222 | bank | en | 9 | 5 | 8 | 1 | 521 | 164 | 3 | 10 |
| R2 | bbb2222 | shop | en | 18 | 8 | 8 | 0 | 521 | 164 | 2 | 10 |
| R2 | bbb2222 | bank | ko | 9 | 5 | 8 | 0 | 521 | 164 | 3 | 10 |
"""


class LedgerTest(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "effort.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(LEDGER)
            self.rows = complexity.read_ledger(path)

    def test_steps_keep_file_order(self):
        self.assertEqual(complexity.steps(self.rows), ["R1", "R2"])

    def test_dash_cells_count_as_zero(self):
        r1 = complexity.totals(self.rows, "R1", "en")
        self.assertEqual((r1["nodes"], r1["rules"], r1["flow_lines"], r1["code_lines"]), (0, 16, 0, 148))

    def test_totals_sum_domains_and_share_the_code(self):
        r2 = complexity.totals(self.rows, "R2", "en")
        self.assertEqual(r2["nodes"], 13)
        self.assertEqual(r2["rules"], 13 + 8 + 8 + 1 + 3 + 2)
        self.assertEqual(r2["flow_lines"], 27)
        self.assertEqual(r2["code_lines"], 521 + 164 + 10)   # once, not per domain
        self.assertEqual(r2["commit"], "bbb2222")

    def test_markdown_has_a_row_per_step_and_language(self):
        md = complexity.to_markdown(self.rows, {"R2": {"en": [3, 4]}})
        self.assertIn("| R2 | en | 13 |", md)
        self.assertIn("| 3 | 4 | 75.0 |", md)
        self.assertNotIn("| R1 | ko |", md)   # no ledger row for it


class CapabilityTest(unittest.TestCase):
    def test_c13_is_a_capability(self):
        self.assertIn("C13", dataset.CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
