"""OMNIS WING v0 admission harness — cold local tests (no network, no credentials)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omnis_wing.boundary import (  # noqa: E402
    CONTRACT_PROTOCOL_VERSION,
    Action,
    ActionEnvelope,
    CountingStubProvider,
    Route,
    SourceRef,
    decide_and_maybe_call,
)
from omnis_wing.host_dispatch import dispatch_action  # noqa: E402
from omnis_wing.transport_guard import (  # noqa: E402
    TransportGuardError,
    assert_clean_package,
    scan_source,
)

CADMUS_SPEC = ROOT / "omnis_wing" / "spec" / "omnis-wing-v0.cadmus-input.json"
CADMUS_SHA = "8a9acc595722680f0f8c108539252e26e295bc9479d8f77b82425b12582767d5"
BASE_COMMIT = "2213ea9fa73ab06cf667c1bfb1e99c8de3541589"
PKG = ROOT / "omnis_wing"


def _sha256_file(path: Path) -> str:
    import hashlib

    data = path.read_bytes()
    # normalize LF like other chamber tools
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _generic_allowed() -> ActionEnvelope:
    return ActionEnvelope(
        project_id="wing-demo",
        spec_digest=CADMUS_SHA,
        privacy_profile="generic",
        source_refs=(SourceRef(kind="generic", digest="a" * 64),),
        route=Route(residency="US", provider="stub-local", modality="chat"),
        action=Action(kind="complete", digest="b" * 64),
    )


def _protected_cn_project() -> ActionEnvelope:
    return ActionEnvelope(
        project_id="wing-protected",
        spec_digest=CADMUS_SHA,
        privacy_profile="protected",
        source_refs=(
            SourceRef(kind="project", digest="c" * 64, path="src/secret_module.py"),
        ),
        route=Route(residency="CN", provider="cn-vendor", modality="chat"),
        action=Action(kind="complete", digest="d" * 64),
    )


def _protected_missing_provenance() -> ActionEnvelope:
    return ActionEnvelope(
        project_id="wing-protected",
        spec_digest=CADMUS_SHA,
        privacy_profile="protected",
        source_refs=(SourceRef(kind="project", digest=None, path="src/orphan.py"),),
        route=Route(residency="US", provider="stub-local", modality="chat"),
        action=Action(kind="complete", digest="e" * 64),
    )


class OmnisWingV0Tests(unittest.TestCase):
    def test_00_cadmus_spec_digest(self):
        self.assertTrue(CADMUS_SPEC.is_file())
        self.assertEqual(_sha256_file(CADMUS_SPEC), CADMUS_SHA)

    def test_01_ordinary_allowed_generic_control(self):
        stub = CountingStubProvider()
        receipt = dispatch_action(_generic_allowed(), stub)
        self.assertEqual(receipt.decision, "SENT")
        self.assertEqual(receipt.provider_calls, 1)
        self.assertEqual(stub.calls, 1)
        self.assertIsNotNone(receipt.provider_response_digest)
        self.assertEqual(receipt.reason_code, "GENERIC_ALLOWED")

    def test_02_protected_cn_refusal_zero_provider_calls(self):
        stub = CountingStubProvider()
        receipt = decide_and_maybe_call(_protected_cn_project(), stub)
        self.assertEqual(receipt.decision, "REFUSED_BEFORE_SEND")
        self.assertEqual(receipt.reason_code, "PROTECTED_PROJECT_CN_ROUTE")
        self.assertEqual(receipt.provider_calls, 0)
        self.assertEqual(stub.calls, 0)
        self.assertIsNone(receipt.provider_response_digest)

    def test_03_protected_missing_provenance_zero_calls(self):
        stub = CountingStubProvider()
        receipt = decide_and_maybe_call(_protected_missing_provenance(), stub)
        self.assertEqual(receipt.decision, "REFUSED_BEFORE_SEND")
        self.assertEqual(receipt.reason_code, "PROTECTED_MISSING_PROVENANCE")
        self.assertEqual(receipt.provider_calls, 0)
        self.assertEqual(stub.calls, 0)

    def test_04_transport_guard_clean_on_package(self):
        # Must not raise
        assert_clean_package(PKG)

    def test_05_planted_direct_https_import_breaks_guard(self):
        planted = "import httpx\n\ndef bad():\n    return httpx.get('https://example.invalid')\n"
        hits = scan_source(planted, filename="planted_bypass.py")
        self.assertTrue(any("httpx" in h for h in hits), hits)

        # Write canary under package and prove assert_clean fails, then remove
        canary_dir = PKG / "canary_plant"
        canary_dir.mkdir(exist_ok=True)
        canary = canary_dir / "direct_https_bypass.py"
        try:
            canary.write_text(planted, encoding="utf-8")
            # scan_source on canary content
            self.assertTrue(scan_source(canary.read_text(encoding="utf-8"), str(canary)))
            # Force guard over canary path explicitly (package assert excludes canary_plant)
            from omnis_wing.transport_guard import scan_paths

            violations = scan_paths([canary])
            self.assertTrue(violations)
            with self.assertRaises(TransportGuardError):
                # temporarily include canary by scanning parent with override
                bad = scan_paths(list(PKG.rglob("*.py")))
                if bad:
                    raise TransportGuardError("transport/import guard failed:\n" + "\n".join(bad))
                self.fail("expected planted bypass to be visible to scanner")
        finally:
            if canary.exists():
                canary.unlink()
            if canary_dir.exists():
                canary_dir.rmdir()

    def test_06_fork_admission_manifest_identity(self):
        manifest_path = ROOT / "OMNIS_WING_ADMISSION.json"
        self.assertTrue(manifest_path.is_file(), "OMNIS_WING_ADMISSION.json missing")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["product_name"], "OMNIS WING")
        self.assertEqual(data["contract_protocol_version"], CONTRACT_PROTOCOL_VERSION)
        self.assertEqual(data["upstream_wing_commit"], BASE_COMMIT)
        self.assertIn("NousResearch/OMNIS-WING", data["upstream_wing_url"])
        self.assertEqual(data["cadmus_input_sha256"], CADMUS_SHA)
        self.assertEqual(len(data["fork_commit"]), 40)
        # fork_commit is the introduction commit (ancestor of HEAD), not a self-hashing HEAD pin
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        base = data["upstream_wing_commit"]
        fork = data["fork_commit"]
        # base is ancestor of fork and fork is ancestor of HEAD
        rc1 = subprocess.call(
            ["git", "merge-base", "--is-ancestor", base, fork], cwd=str(ROOT)
        )
        rc2 = subprocess.call(
            ["git", "merge-base", "--is-ancestor", fork, head], cwd=str(ROOT)
        )
        self.assertEqual(rc1, 0, "upstream base must be ancestor of fork_commit")
        self.assertEqual(rc2, 0, "fork_commit must be ancestor of HEAD")
        # object exists
        typ = subprocess.check_output(
            ["git", "cat-file", "-t", fork], cwd=str(ROOT), text=True
        ).strip()
        self.assertEqual(typ, "commit")

    def test_07_no_flattering_decision_language(self):
        stub = CountingStubProvider()
        for env in (_generic_allowed(), _protected_cn_project(), _protected_missing_provenance()):
            r = decide_and_maybe_call(env, stub)
            self.assertIn(r.decision, ("REFUSED_BEFORE_SEND", "SENT"))
            blob = json.dumps(r.to_dict())
            for banned in ("SUCCESS", "APPROVED", "SAFE", "HARMLESS", "PASSED"):
                self.assertNotIn(banned, blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
