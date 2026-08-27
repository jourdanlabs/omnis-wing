"""Chamber memory bridge — fail open, soul first, vault stays outside the repo."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnis_wing.chamber_memory import (
    append_chamber_memory,
    load_chamber_memory,
    resolve_chamber_vault,
)
from omnis_wing.sealed_soul import PAN_SOUL_ID, stage_pan_soul_for_hermes

MTS_SOULS = Path.home() / "projects" / "mts" / "souls"


class TestChamberMemory(unittest.TestCase):
    def test_missing_vault_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = load_chamber_memory(Path(tmp) / "no-such-vault")
            self.assertIsNone(pack.vault_dir)
            self.assertEqual(pack.memory, "")
            wired = append_chamber_memory("SOUL ONLY", pack)
            self.assertEqual(wired["system"], "SOUL ONLY")
            self.assertEqual(wired["included"], ["soul"])

    def test_explicit_missing_dir_does_not_fall_back_to_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent"
            self.assertIsNone(resolve_chamber_vault(missing))

    def test_soul_never_truncated_to_make_room(self):
        soul = "S" * 200
        pack = load_chamber_memory(Path("/no/such-chamber-vault"))
        # inject a fat extra via a real tmp vault
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "BOOT.md").write_text("BOOT", encoding="utf-8")
            (vault / "memory").mkdir()
            (vault / "memory" / "MEMORY.md").write_text("M" * 1000, encoding="utf-8")
            pack = load_chamber_memory(vault)
            wired = append_chamber_memory(soul, pack, max_bytes=len(soul.encode()) + 20)
            self.assertTrue(wired["system"].startswith(soul))
            self.assertEqual(wired["system"][: len(soul)], soul)
            self.assertIn("soul", wired["included"])
            self.assertTrue(len(wired["skipped"]) >= 1)

    def test_stage_writes_memory_beside_soul_not_into_soul(self):
        if not (MTS_SOULS / PAN_SOUL_ID / "soul.md").is_file():
            self.skipTest("sealed Pan missing")
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            (vault / "BOOT.md").write_text("# Chamber boot", encoding="utf-8")
            (vault / "memory").mkdir()
            (vault / "memory" / "MEMORY.md").write_text("fact: wing memory bridge\n", encoding="utf-8")
            (vault / "sessions").mkdir()
            profile = Path(tmp) / "pan-wing"
            loaded = stage_pan_soul_for_hermes(profile, MTS_SOULS, vault_dir=vault)
            soul = (profile / "SOUL.md").read_text(encoding="utf-8")
            mem = (profile / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("PannyWanny", soul)
            self.assertNotIn("wing memory bridge", soul)
            self.assertIn("wing memory bridge", mem)
            self.assertIn("BOOT.md", mem)
            marker = json.loads((profile / ".omnis-wing-pan-sealed").read_text(encoding="utf-8"))
            self.assertIn("soul", marker["memory_included"])
            self.assertIn("memory/MEMORY.md", marker["memory_included"])
            self.assertEqual(marker["soul_id"], loaded.soul_id)

    def test_missing_vault_stage_leaves_soul_intact(self):
        if not (MTS_SOULS / PAN_SOUL_ID / "soul.md").is_file():
            self.skipTest("sealed Pan missing")
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "pan-wing"
            stage_pan_soul_for_hermes(profile, MTS_SOULS, vault_dir=Path(tmp) / "nope")
            soul = (profile / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn("PannyWanny", soul)
            marker = json.loads((profile / ".omnis-wing-pan-sealed").read_text(encoding="utf-8"))
            self.assertEqual(marker["memory_included"], ["soul"])
            self.assertIsNone(marker["vault_dir"])

    def test_live_vault_stages_memory_without_copying_vault_into_soul(self):
        if not (MTS_SOULS / PAN_SOUL_ID / "soul.md").is_file():
            self.skipTest("sealed Pan missing")
        live = Path.home() / "chamber-soul-vault"
        mem_path = live / "memory" / "MEMORY.md"
        if not mem_path.is_file():
            self.skipTest("live chamber vault missing")
        mem = mem_path.read_text(encoding="utf-8")
        marker_line = next((ln.strip() for ln in mem.splitlines() if ln.strip()), "")
        if not marker_line:
            self.skipTest("MEMORY.md empty")
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "pan-wing"
            stage_pan_soul_for_hermes(profile, MTS_SOULS, vault_dir=live)
            soul = (profile / "SOUL.md").read_text(encoding="utf-8")
            staged = (profile / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("PannyWanny", soul)
            self.assertNotIn(marker_line[:40], soul)
            self.assertIn(marker_line[:40], staged)
            self.assertNotIn(str(live), soul)


if __name__ == "__main__":
    unittest.main()
