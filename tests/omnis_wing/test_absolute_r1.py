"""OMNIS WING R1 ABSOLUTE-shaped cold controls."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omnis_wing.absolute.coverage import assert_manifest_honest, governed_module_paths, load_manifest
from omnis_wing.absolute.envelope import (
    IntendedDestination,
    OutboundEnvelope,
    SourceProvenance,
)
from omnis_wing.absolute.evaluator import RecordingBroker, decide_and_execute
from omnis_wing.absolute.host import dispatch_outbound
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS
from omnis_wing.transport_guard import (
    TransportGuardError,
    assert_clean_package,
    r1_governed_paths,
    scan_paths,
    scan_source,
)

CADMUS_R1 = ROOT / "omnis_wing" / "spec" / "omnis-wing-r1-absolute.cadmus-input.json"
CADMUS_R1_SHA = "b4dcb959ddda7a0ac488817e65fed255a31da6e077c20596d90d62fe0e121805"


def _sha_file(path: Path) -> str:
    t = path.read_text(encoding="utf-8")
    if t.startswith("\ufeff"):
        t = t[1:]
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _generic_source(payload: str) -> SourceProvenance:
    d = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return SourceProvenance(
        path="notes/generic.txt",
        content_digest=d,
        classification="generic",
        protected_root=False,
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )


def _project_source(payload: str, **kwargs) -> SourceProvenance:
    d = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return SourceProvenance(
        path=kwargs.get("path", "src/project_module.py"),
        content_digest=kwargs.get("content_digest", d),
        classification=kwargs.get("classification", "project"),
        protected_root=kwargs.get("protected_root", True),
        crown_jewel=kwargs.get("crown_jewel", False),
        byte_range=kwargs.get("byte_range"),
        whole_content=kwargs.get("whole_content", True),
    )


def _dest(**kwargs) -> IntendedDestination:
    return IntendedDestination(
        provider=kwargs.get("provider", "stub-local"),
        scheme=kwargs.get("scheme", "https"),
        hostname=kwargs.get("hostname", "ai.example.test"),
        port=kwargs.get("port", 443),
        path_class=kwargs.get("path_class", "chat.completions"),
        residency=kwargs.get("residency", "US"),
    )


class AbsoluteR1Tests(unittest.TestCase):
    def test_00_cadmus_r1_digest(self):
        self.assertTrue(CADMUS_R1.is_file())
        self.assertEqual(_sha_file(CADMUS_R1), CADMUS_R1_SHA)

    def test_01_protected_project_cn_refuse_residency_zero_calls(self):
        payload = "summarize protected project module"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(_project_source(payload),),
            destination=_dest(residency="CN"),
        )
        broker = RecordingBroker()
        receipt = dispatch_outbound(env, broker)
        self.assertEqual(receipt.decision, "REFUSE_RESIDENCY")
        self.assertEqual(receipt.phase, "NONE")
        self.assertEqual(receipt.provider_calls, 0)
        self.assertEqual(broker.calls, 0)

    def test_02_missing_provenance_refuse_source_policy(self):
        payload = "no sources attached"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(),
            destination=_dest(residency="US"),
        )
        broker = RecordingBroker()
        receipt = decide_and_execute(env, broker)
        self.assertEqual(receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(broker.calls, 0)

        # invalid digest
        bad = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(
                SourceProvenance(
                    path="x.py",
                    content_digest="short",
                    classification="project",
                    protected_root=True,
                    crown_jewel=False,
                    byte_range=None,
                    whole_content=True,
                ),
            ),
            destination=_dest(),
        )
        r2 = decide_and_execute(bad, RecordingBroker())
        self.assertEqual(r2.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(r2.provider_calls, 0)

    def test_03_planted_secret_refuse_no_leak(self):
        secret = PLANTED_SECRET_MARKERS[0]
        payload = f"please store {secret} in vault"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(_generic_source(payload),),
            destination=_dest(),
        )
        broker = RecordingBroker()
        receipt = decide_and_execute(env, broker)
        self.assertEqual(receipt.decision, "REFUSE_SECRET")
        self.assertEqual(broker.calls, 0)
        blob = receipt.serialize_for_hygiene()
        self.assertNotIn(secret, blob)
        # bare sha256 of low-entropy marker must not appear
        bare = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        self.assertNotIn(bare, blob)
        # finding ids only
        self.assertTrue(receipt.finding_ids)

    def test_04_scanner_exception_refuse_scanner_failure(self):
        payload = "benign generic text for scanner failure path"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(_generic_source(payload),),
            destination=_dest(),
        )
        broker = RecordingBroker()
        receipt = decide_and_execute(env, broker, inject_scanner_failure=True)
        self.assertEqual(receipt.decision, "REFUSE_SCANNER_FAILURE")
        self.assertEqual(broker.calls, 0)

    def test_05_allowed_generic_bytes_equal_phase_completed(self):
        payload = "hello wing r1 generic allow path"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(_generic_source(payload),),
            destination=_dest(residency="US"),
        )
        broker = RecordingBroker()
        receipt = decide_and_execute(env, broker)
        self.assertEqual(receipt.decision, "PERMIT")
        self.assertEqual(receipt.phase, "TRANSMISSION_COMPLETED")
        self.assertEqual(broker.calls, 1)
        self.assertEqual(broker.last_payload, env.payload_bytes)
        self.assertEqual(receipt.delivered_payload_digest, env.payload_digest)
        self.assertEqual(
            list(receipt.phases_observed),
            ["AUTHORIZED", "TRANSMISSION_STARTED", "TRANSMISSION_COMPLETED"],
        )

    def test_06_destination_mutation_refuse_zero_calls(self):
        payload = "mutate destination after auth"
        env = OutboundEnvelope.create(
            modality="chat",
            lane="wing-r1",
            payload=payload,
            sources=(_generic_source(payload),),
            destination=_dest(hostname="ai.example.test", residency="US"),
        )

        def mutate(e: OutboundEnvelope) -> OutboundEnvelope:
            return OutboundEnvelope.create(
                modality=e.modality,
                lane=e.lane,
                payload=e.payload_bytes,
                sources=e.sources,
                destination=_dest(hostname="evil.example.test", residency="US"),
                envelope_id=e.envelope_id,
            )

        broker = RecordingBroker()
        receipt = decide_and_execute(
            env, broker, mutate_destination_after_auth=mutate
        )
        self.assertEqual(receipt.decision, "REFUSE_DESTINATION")
        self.assertEqual(broker.calls, 0)

    def test_06b_empty_path_class_refuse_destination_zero_calls(self):
        """H6: ABSOLUTE binds path_class; empty/blank endpoint class must refuse."""
        payload = "generic allow would succeed except empty path_class"
        for blank in ("", "   ", "\t"):
            env = OutboundEnvelope.create(
                modality="chat",
                lane="wing-r1",
                payload=payload,
                sources=(_generic_source(payload),),
                destination=_dest(path_class=blank, residency="US"),
            )
            broker = RecordingBroker()
            receipt = decide_and_execute(env, broker)
            self.assertEqual(
                receipt.decision,
                "REFUSE_DESTINATION",
                f"path_class={blank!r} must refuse",
            )
            self.assertEqual(receipt.phase, "NONE")
            self.assertEqual(receipt.provider_calls, 0)
            self.assertEqual(broker.calls, 0)

    def test_07_planted_direct_transport_import_fails_guard(self):
        assert_clean_package(ROOT / "omnis_wing")
        planted = "import httpx\n\ndef p():\n    return httpx.get('https://x')\n"
        self.assertTrue(scan_source(planted, "plant.py"))
        # plant into a governed module path temporarily
        target = ROOT / "omnis_wing" / "absolute" / "_canary_httpx_plant.py"
        try:
            target.write_text(planted, encoding="utf-8")
            # governed list is from manifest — canary not listed; scan all governed + plant explicitly
            violations = scan_paths(list(r1_governed_paths(ROOT)) + [target])
            self.assertTrue(any("httpx" in v for v in violations))
            with self.assertRaises(TransportGuardError):
                bad = scan_paths([target])
                if bad:
                    raise TransportGuardError("\n".join(bad))
        finally:
            if target.exists():
                target.unlink()
        assert_clean_package(ROOT / "omnis_wing")

    def test_08_coverage_manifest_honest(self):
        assert_manifest_honest(ROOT)
        man = load_manifest()
        self.assertFalse(man["claims_whole_tree_ai_egress"])
        self.assertFalse(man["claims_absolute_complete"])
        governed = governed_module_paths(ROOT)
        self.assertGreaterEqual(len(governed), 5)
        for p in governed:
            self.assertTrue(p.is_file(), p)
        for entry in man["inherited_hermes_transport"]:
            self.assertIn(
                entry["status"],
                ("ungoverned", "inbound", "outside_r1", "outside_r2"),
            )

    def test_09_r1_guard_covers_all_governed_modules(self):
        paths = r1_governed_paths(ROOT)
        self.assertTrue(paths)
        violations = scan_paths(paths)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
