"""Track B: `wing pan` loads sealed Pan — refuse missing/tampered."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from omnis_wing.sealed_soul import (
    PAN_SOUL_ID,
    REFUSAL_NOT_OPEN,
    REFUSAL_VERIFY,
    SoulLoadRefused,
    build_bedrock_lock,
    compute_bedrock_hash,
    default_souls_dir,
    hash_payload,
    load_pan_soul,
    load_sealed_soul,
    parse_soul_markdown,
    stage_pan_soul_for_hermes,
    verify_sealed_soul,
    verify_sealed_soul_python,
)
from omnis_wing.wing_cli import main as wing_main

ROOT = Path(__file__).resolve().parents[2]
MTS_ROOT = Path.home() / "projects" / "mts"
MTS_SOULS = MTS_ROOT / "souls"
TAMPERED_FIXTURE = MTS_ROOT / "core-spec" / "fixtures" / "tampered-bedrock"
GATE_SOUL_ID = "soul_739f266524c8"
WING_SCRIPT = ROOT / "scripts" / "wing"


class TestSealedSoulHash(unittest.TestCase):
    def test_hash_payload_matches_mts_vectors(self):
        self.assertEqual(
            hash_payload({}),
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        )
        self.assertEqual(
            hash_payload({"b": 2, "a": 1}),
            "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
        )


class TestPanSealedSoul(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pan_pkg = MTS_SOULS / PAN_SOUL_ID
        cls.pan_available = cls.pan_pkg.is_dir() and (cls.pan_pkg / "soul.md").is_file()

    def test_real_pan_verifies_when_package_present(self):
        if not self.pan_available:
            self.skipTest(f"sealed Pan package missing at {self.pan_pkg}")
        result = verify_sealed_soul(PAN_SOUL_ID, MTS_SOULS)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.verdict, "VERIFIED")
        self.assertEqual(result.soul_id, PAN_SOUL_ID)

    def test_real_pan_loads_name_and_card(self):
        if not self.pan_available:
            self.skipTest(f"sealed Pan package missing at {self.pan_pkg}")
        loaded = load_pan_soul(MTS_SOULS)
        self.assertEqual(loaded.name, "Pan")
        self.assertEqual(loaded.soul_id, PAN_SOUL_ID)
        self.assertIn("not generic Hermes bread", loaded.identity_card)
        self.assertIn(str(loaded.soul_path), loaded.identity_card)
        self.assertIn("PannyWanny", loaded.soul_text)

    def test_refuse_missing_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            souls = Path(tmp)
            with self.assertRaises(SoulLoadRefused) as ctx:
                load_sealed_soul(PAN_SOUL_ID, souls)
            self.assertEqual(ctx.exception.verification.verdict, "MISSING")

    def test_refuse_tampered_bedrock_fixture(self):
        if not TAMPERED_FIXTURE.is_dir():
            self.skipTest(f"tampered fixture missing at {TAMPERED_FIXTURE}")
        with tempfile.TemporaryDirectory() as tmp:
            souls = Path(tmp)
            shutil.copytree(TAMPERED_FIXTURE, souls / GATE_SOUL_ID)
            result = verify_sealed_soul_python(GATE_SOUL_ID, souls)
            self.assertFalse(result.ok)
            self.assertEqual(result.verdict, "FAILED")
            self.assertTrue(any("bedrock_hash mismatch" in i for i in result.issues))
            with self.assertRaises(SoulLoadRefused):
                load_sealed_soul(GATE_SOUL_ID, souls, prefer_mts=False)

    def test_stage_writes_verified_soul_to_profile(self):
        if not self.pan_available:
            self.skipTest(f"sealed Pan package missing at {self.pan_pkg}")
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "pan-wing"
            loaded = stage_pan_soul_for_hermes(profile, MTS_SOULS)
            soul_dest = profile / "SOUL.md"
            self.assertTrue(soul_dest.is_file())
            staged = parse_soul_markdown(soul_dest.read_text(encoding="utf-8"))
            self.assertEqual(staged.name, "Pan")
            self.assertIn("soul_bb75a9fa2823", staged.soul_id or "")
            marker = json.loads((profile / ".omnis-wing-pan-sealed").read_text(encoding="utf-8"))
            self.assertEqual(marker["soul_id"], PAN_SOUL_ID)
            self.assertEqual(marker["verdict"], "VERIFIED")
            self.assertEqual(marker["bedrock_hash"], loaded.verification.bedrock_hash)


class TestWingPanCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pan_available = (MTS_SOULS / PAN_SOUL_ID / "soul.md").is_file()

    def test_wing_pan_identity_json_ok(self):
        if not self.pan_available:
            self.skipTest("sealed Pan package missing")
        rc = wing_main(["pan", "identity", "--json", "--souls-dir", str(MTS_SOULS)])
        self.assertEqual(rc, 0)

    def test_wing_pan_refuses_missing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = wing_main(["pan", "identity", "--json", "--souls-dir", tmp])
            self.assertEqual(rc, 2)

    def test_wing_script_pan_verify(self):
        if not WING_SCRIPT.is_file():
            self.skipTest("scripts/wing missing")
        if not self.pan_available:
            self.skipTest("sealed Pan package missing")
        proc = subprocess.run(
            [str(WING_SCRIPT), "pan", "verify", "--souls-dir", str(MTS_SOULS)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["verdict"], "VERIFIED")

    def test_wing_pan_default_is_identity(self):
        if not self.pan_available:
            self.skipTest("sealed Pan package missing")
        rc = wing_main(["pan", "--json", "--souls-dir", str(MTS_SOULS)])
        self.assertEqual(rc, 0)


class TestRefusalCopy(unittest.TestCase):
    def test_refusal_strings_are_stable(self):
        self.assertIn("sealed soul is not open", REFUSAL_NOT_OPEN.lower())
        self.assertIn("failed verification", REFUSAL_VERIFY.lower())


if __name__ == "__main__":
    unittest.main()
