"""Completion BBB: product-disabled side doors refuse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from omnis_wing.completion.product_disable import (  # noqa: E402
    WingRouteDisabled,
    assert_route_enabled,
    disabled_routes,
    load_manifest,
)
import omnis_wing.completion.side_doors  # noqa: E402,F401  # install guards


class CompletionDisabledTests(unittest.TestCase):
    def test_disabled_routes_nonempty(self):
        d = disabled_routes()
        self.assertIn("tools.vision_tools", d)
        self.assertIn("agent.auxiliary_client.chat_completions", d)

    def test_assert_route_enabled_raises(self):
        with self.assertRaises(WingRouteDisabled):
            assert_route_enabled("tools.vision_tools")

    def test_manifest_disabled_have_reason(self):
        man = load_manifest()
        for r in man["routes"]:
            if r["state"] == "DISABLED" and r.get("broker_join") == "DISABLED":
                self.assertTrue(r.get("disable_reason"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
