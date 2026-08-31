"""Cold tests for OMNIS WING product distribution packaging."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from omnis_wing.absolute.real_work.config import PINNED_CADUCEUS_COMMIT  # noqa: E402
from omnis_wing.distribution.operator_bundle import build_operator_bundle  # noqa: E402
from omnis_wing.distribution.routes import (  # noqa: E402
    RouteInventoryError,
    closed_route_inventory,
)


class RouteInventoryTests(unittest.TestCase):
    def test_shipping_manifest_is_closed(self) -> None:
        inv = closed_route_inventory()
        self.assertEqual(inv["summary"]["GOVERNED"] + inv["summary"]["DISABLED"], inv["total"])
        self.assertGreaterEqual(inv["summary"]["GOVERNED"], 2)
        self.assertEqual(inv["forbidden_states_observed"], [])
        self.assertTrue(inv["digest"])

    def test_unenforced_refuses(self) -> None:
        planted = {
            "routes": [
                {"route_id": "a", "state": "GOVERNED"},
                {"route_id": "b", "state": "UNENFORCED"},
            ]
        }
        with self.assertRaises(RouteInventoryError):
            closed_route_inventory(planted)


class OperatorBundleTests(unittest.TestCase):
    def test_bundle_is_content_addressed_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wing-bundle-") as tmp:
            bundle = build_operator_bundle(tmp)
            self.assertTrue(bundle.path.is_dir())
            self.assertTrue((bundle.path / "MANIFEST.json").is_file())
            self.assertTrue((bundle.path / "pins.json").is_file())
            self.assertTrue(
                (bundle.path / "templates" / "real-work.production.example.json").is_file()
            )
            pins = json.loads((bundle.path / "pins.json").read_text(encoding="utf-8"))
            self.assertEqual(pins["caduceus_commit"], PINNED_CADUCEUS_COMMIT)
            text = bundle.path.joinpath("templates", "real-work.production.example.json").read_text()
            self.assertNotIn("sk-", text)
            self.assertIn(PINNED_CADUCEUS_COMMIT, text)
            # Digest is hex
            self.assertRegex(bundle.digest, r"^[0-9a-f]{64}$")


class CaduceusPinTests(unittest.TestCase):
    def test_product_pin_is_code_wave4(self) -> None:
        self.assertEqual(
            PINNED_CADUCEUS_COMMIT,
            "6fe2d1f014bf6da7b3fb99a3c0145a3d9f4576b9",
        )


if __name__ == "__main__":
    unittest.main()
