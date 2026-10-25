"""R13: identity gate. Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voxstage.rules.flows import gate_tools
from voxstage.tools import FakeApiExecutor

ROOT = os.path.join(os.path.dirname(__file__), "..", "domains")


def tool(**body):
    return {"params": [], **body}


class ToolKeysTest(unittest.TestCase):
    def test_protected_and_verifying_tools(self):
        api = FakeApiExecutor({"tools": {"look": tool(requires="verified"), "check": tool(verifies=True)}})
        self.assertEqual(api.tools["look"]["requires"], "verified")
        self.assertTrue(api.tools["check"]["verifies"])

    def test_bad_keys(self):
        for tools in ({"look": tool(requires="admin"), "check": tool(verifies=True)},
                      {"look": tool(requires="verified"), "check": tool(verifies="yes")},
                      {"both": tool(requires="verified", verifies=True)},
                      {"look": tool(requires="verified")},
                      {"look": tool(requires="verified"), "a": tool(verifies=True), "b": tool(verifies=True)}):
            with self.subTest(tools=sorted(tools)), self.assertRaises(ValueError):
                FakeApiExecutor({"tools": tools})

    def test_a_verifier_without_protected_tools_is_allowed(self):
        FakeApiExecutor({"tools": {"check": tool(verifies=True)}})

    def test_the_domains(self):
        found = {d: gate_tools(os.path.join(ROOT, d, "tools.yaml")) for d in ("bank", "shop", "telecom")}
        self.assertEqual(found, {"bank": (frozenset({"get_balance"}), "verify_identity"),
                                 "shop": (frozenset({"get_order_status"}), "verify_identity"),
                                 "telecom": (frozenset({"get_bill"}), "verify_identity")})


if __name__ == "__main__":
    unittest.main()
