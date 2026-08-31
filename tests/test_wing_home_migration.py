"""Copy-on-first-run from the pre-rename state dir."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class TestLegacyHomeMigration(unittest.TestCase):
    def setUp(self) -> None:
        self._home_env = os.environ.pop("WING_HOME", None)

    def tearDown(self) -> None:
        if self._home_env is not None:
            os.environ["WING_HOME"] = self._home_env
        else:
            os.environ.pop("WING_HOME", None)

    def test_copy_on_first_run_skips_source_checkout(self) -> None:
        import wing_constants

        with TemporaryDirectory() as td:
            home = Path(td)
            legacy = home / ".hermes"
            dest = home / ".omnis-wing"
            legacy.mkdir()
            (legacy / "config.yaml").write_text("model: x\n", encoding="utf-8")
            (legacy / "sessions").mkdir()
            checkout = legacy / "hermes-agent"
            checkout.mkdir()
            (checkout / "README").write_text("src\n", encoding="utf-8")

            with (
                patch.object(wing_constants, "_get_platform_default_wing_home", return_value=dest),
                patch.object(wing_constants, "_legacy_state_home", return_value=legacy),
            ):
                got = wing_constants.get_wing_home()

            self.assertEqual(got, dest)
            self.assertEqual((dest / "config.yaml").read_text(encoding="utf-8"), "model: x\n")
            self.assertTrue((dest / "sessions").is_dir())
            self.assertFalse((dest / "hermes-agent").exists())
            self.assertTrue((legacy / "MOVED-TO-OMNIS-WING.txt").is_file())
            self.assertTrue((dest / ".migrated-from-legacy-home").is_file())

    def test_existing_state_is_not_clobbered(self) -> None:
        import wing_constants

        with TemporaryDirectory() as td:
            dest = Path(td) / "omnis-wing"
            dest.mkdir()
            (dest / "config.yaml").write_text("keep: me\n", encoding="utf-8")
            legacy = Path(td) / ".hermes"
            legacy.mkdir()
            (legacy / "config.yaml").write_text("old: yes\n", encoding="utf-8")
            (legacy / "sessions").mkdir()

            with (
                patch.object(wing_constants, "_get_platform_default_wing_home", return_value=dest),
                patch.object(wing_constants, "_legacy_state_home", return_value=legacy),
            ):
                got = wing_constants.get_wing_home()

            self.assertEqual(got, dest)
            self.assertEqual((dest / "config.yaml").read_text(encoding="utf-8"), "keep: me\n")
            self.assertFalse((dest / ".migrated-from-legacy-home").exists())


if __name__ == "__main__":
    unittest.main()
