"""Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.tools import FakeApiExecutor, ToolExecutor

SPEC = {"tools": {"get_fee": {
    "params": ["amount", "grade"],
    "rules": [
        {"when": {"grade": "gold"}, "return": {"fee": 0}},
        {"when": {"grade": "basic"}, "return": {"fee": 500}},
        {"when": {"grade": "outage"}, "error": "timeout"},
    ],
    "default": {"error": "not_found"},
}}}


class FakeApiTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApiExecutor(SPEC)

    def test_result_depends_on_arguments(self):
        self.assertEqual(self.api.call("get_fee", {"amount": 500000, "grade": "gold"}).data, {"fee": 0})
        self.assertEqual(self.api.call("get_fee", {"amount": 500000, "grade": "basic"}).data, {"fee": 500})

    def test_error_rule_and_default(self):
        r = self.api.call("get_fee", {"amount": 1, "grade": "outage"})
        self.assertEqual((r.ok, r.error), (False, "timeout"))
        r = self.api.call("get_fee", {"amount": 1, "grade": "unknown"})
        self.assertEqual((r.ok, r.error), (False, "not_found"))

    def test_missing_param_and_unknown_tool(self):
        self.assertEqual(self.api.call("get_fee", {"amount": 1}).error, "missing_param:grade")
        self.assertEqual(self.api.call("nope", {}).error, "unknown_tool")

    def test_values_compare_as_strings(self):
        # YAML may give 4821 as an int while a DTMF input is the string "4821"
        api = FakeApiExecutor({"tools": {"t": {"params": ["k"], "rules": [{"when": {"k": 4821}, "return": {"ok": 1}}]}}})
        self.assertTrue(api.call("t", {"k": "4821"}).ok)

    def test_calls_are_recorded_and_data_is_copied(self):
        r = self.api.call("get_fee", {"amount": 1, "grade": "gold"})
        r.data["fee"] = 999  # mutating a result must not change the rule table
        self.assertEqual(self.api.call("get_fee", {"amount": 1, "grade": "gold"}).data, {"fee": 0})
        self.assertEqual(self.api.calls[0], ("get_fee", {"amount": 1, "grade": "gold"}))

    def test_bad_specs_are_rejected(self):
        for bad in ({}, {"tools": {"t": {"rules": [{"when": {"a": 1}}]}}},
                    {"tools": {"t": {"rules": [{"when": {"a": 1}, "return": {}, "error": "x"}]}}},
                    {"tools": {"t": {"oops": 1}}}):
            with self.assertRaises(ValueError):
                FakeApiExecutor(bad)

    def test_is_a_tool_executor(self):
        self.assertIsInstance(self.api, ToolExecutor)


if __name__ == "__main__":
    unittest.main()
