"""R4: production signer boundary + operator health — disposable backend only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_tmp_home = tempfile.mkdtemp(prefix="omnis-wing-r4-home-")
os.environ["HERMES_HOME"] = _tmp_home
for _name in ("requests", "yaml"):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        if _name == "yaml":
            _m.safe_load = lambda stream: {}  # type: ignore
        sys.modules[_name] = _m

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.envelope import SourceProvenance  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import (  # noqa: E402
    EvidenceSession,
    WingEgressContext,
    WingRefusal,
    governed_chat_completions_create,
)
from omnis_wing.absolute.production_signer import (  # noqa: E402
    CAPTAIN_R4_TAG,
    DisposableP256Backend,
    DisposableTestBackend,
    ProductionSignerAdapter,
)
from omnis_wing.absolute.operator_health import build_health_report  # noqa: E402

from omnis_wing.absolute.receipt_spine import (  # noqa: E402
    EvidenceLedger,
    make_test_signer,
    verify_signed_receipt,
)
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402

CADMUS_R4 = ROOT / "omnis_wing" / "spec" / "omnis-wing-r4-production-signer-health.cadmus-input.json"
CADMUS_R4_SHA = "a54c70e866a137e9513db3f99f2859dc6bf37873205bc4e2326a3355b8b52c86"
US_BASE = "https://ai.example.test/v1"
TEST_TAG = "ai.jourdanlabs.omnis-wing.test.r4.disposable"


def _sha_file(path: Path) -> str:
    t = path.read_text(encoding="utf-8")
    if t.startswith("\ufeff"):
        t = t[1:]
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class FakeClient:
    is_fake = True

    def __init__(self, base_url: str = US_BASE):
        self.base_url = base_url
        self.create_calls = 0
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs: Any) -> Any:
        self.create_calls += 1
        return SimpleNamespace(id="f", choices=[])

    def close(self):
        pass


class MiniAgent:
    def __init__(self, wing_ctx, client):
        self.api_mode = "chat_completions"
        self.wing_egress_context = wing_ctx
        self._client = client
        self._interrupt_requested = False
        self.log_prefix = "t"
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None

    def _create_request_openai_client(self, *, reason: str, api_kwargs: dict):
        return self._client

    def _abort_request_openai_client(self, client, reason: str):
        pass

    def _close_request_openai_client(self, client, reason: str):
        pass

    def _compute_non_stream_stale_timeout(self, api_kwargs: dict) -> float:
        return 30.0

    def _touch_activity(self, msg: str = "") -> None:
        pass

    def _buffer_status(self, msg: str = "") -> None:
        pass


def _src(classification="generic"):
    return SourceProvenance(
        path="n.txt",
        content_digest=hashlib.sha256(b"x").hexdigest(),
        classification=classification,
        protected_root=classification != "generic",
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )


def _api_kwargs(**extra):
    kw = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0}
    kw.update(extra)
    return kw


class R4ProductionSignerHealthTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="r4-"))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_00_cadmus_r4(self):
        self.assertEqual(_sha_file(CADMUS_R4), CADMUS_R4_SHA)

    def test_01_no_enrollment_refuses_client_0(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=False)
        adapter = ProductionSignerAdapter(backend=be)
        self.assertFalse(adapter.available())
        ev = EvidenceSession(
            signer=adapter,
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient()
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_02_explicit_enroll_then_permit(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=False)
        adapter = ProductionSignerAdapter(backend=be)
        # startup did not enroll
        self.assertEqual(adapter.enrollment_status()["state"], "NOT_ENROLLED")
        # explicit operator action
        st = adapter.enroll_explicit()
        self.assertTrue(st["ready"])
        self.assertEqual(st["state"], "ENROLLED")
        self.assertEqual(st["storage_state"], "TEST_DISPOSABLE")
        self.assertNotIn("hardware_backed", st)

        ev = EvidenceSession(
            signer=adapter,
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient()
        resp = interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        self.assertEqual(len(ev.ledger.load_entries()), 2)

    def test_03_signer_error_refuses_client_0(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True, fail_sign=True)
        adapter = ProductionSignerAdapter(backend=be)
        ev = EvidenceSession(
            signer=adapter,
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient()
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_04_health_invalid_on_ledger_mutation(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True)
        adapter = ProductionSignerAdapter(backend=be)
        ledger = EvidenceLedger(self.td / "ledger.jsonl")
        ev = EvidenceSession(signer=adapter, ledger=ledger)
        governed_chat_completions_create(
            FakeClient(), _api_kwargs(), WingEgressContext(sources=(_src(),), evidence=ev)
        )
        # mutate ledger
        text = ledger.path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        d = json.loads(lines[-1])
        d["decision"] = "MUTATED"
        lines[-1] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertEqual(report["verifier"], "INVALID")
        self.assertFalse(report["ledger"]["chain_valid"])
        self.assertEqual(report["remote_anchor"]["state"], "NOT_CONFIGURED")

    def test_05_health_anchor_not_configured_never_green_remote(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True)
        adapter = ProductionSignerAdapter(backend=be)
        ledger = EvidenceLedger(self.td / "empty.jsonl")
        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertEqual(report["remote_anchor"]["state"], "NOT_CONFIGURED")
        self.assertNotEqual(report["remote_anchor"]["state"], "GREEN")
        blob = json.dumps(report)
        self.assertNotIn("remote durability achieved", blob.lower())

    def test_06_secret_absent_from_health_and_path(self):
        secret = PLANTED_SECRET_MARKERS[0]
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True)
        adapter = ProductionSignerAdapter(backend=be)
        ledger = EvidenceLedger(self.td / "ledger.jsonl")
        ev = EvidenceSession(signer=adapter, ledger=ledger)
        client = FakeClient()
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                MiniAgent(
                    WingEgressContext(sources=(_src(),), evidence=ev),
                    client,
                ),
                _api_kwargs(extra_body={"x": secret}),
            )
        self.assertEqual(client.create_calls, 0)
        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        blob = json.dumps(report) + str(cm.exception) + cm.exception.receipt.serialize_for_hygiene()
        bare = hashlib.sha256(secret.encode()).hexdigest()
        self.assertNotIn(secret, blob)
        self.assertNotIn(bare, blob)
        # filename hygiene
        for p in self.td.rglob("*"):
            self.assertNotIn(secret, p.name)

    def test_07_refuses_captain_tag_on_test_backend(self):
        with self.assertRaises(ValueError):
            DisposableTestBackend(tag=CAPTAIN_R4_TAG, enrolled=False)

    def test_08_storage_state_honesty_no_false_hardware(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True)
        st = be.status()
        self.assertEqual(st["storage_state"], "TEST_DISPOSABLE")
        self.assertNotIn("hardware_backed", st)

    def test_09_health_not_ready_when_not_enrolled(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=False)
        adapter = ProductionSignerAdapter(backend=be)
        ledger = EvidenceLedger(self.td / "e.jsonl")
        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertEqual(report["enrollment"]["state"], "NOT_ENROLLED")
        self.assertEqual(report["verifier"], "NOT_READY")


    def test_10_p256_disposable_end_to_end_chain_valid(self):
        """P-256 algorithm receipts verify; mutation fails — cold, no Keychain."""
        be = DisposableP256Backend(tag=TEST_TAG + ".p256", work_dir=self.td / "p256")
        adapter = ProductionSignerAdapter(backend=be)
        self.assertEqual(adapter.signature_algorithm, "ecdsa-p256-x962-sha256")
        adapter.enroll_explicit()
        ledger = EvidenceLedger(self.td / "p256-ledger.jsonl")
        ev = EvidenceSession(signer=adapter, ledger=ledger)
        client = FakeClient()
        resp = interruptible_api_call(
            MiniAgent(WingEgressContext(sources=(_src(),), evidence=ev), client),
            _api_kwargs(),
        )
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        entries = ledger.load_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["signature_algorithm"], "ecdsa-p256-x962-sha256")
        pk = adapter.public_key_bytes()
        ok, reason = ledger.verify_chain(pk)
        self.assertTrue(ok, reason)
        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertTrue(report["ledger"]["chain_valid"])
        self.assertIn(report["verifier"], ("OK", "DEGRADED_OUTCOME_UNKNOWN"))
        self.assertEqual(report["remote_anchor"]["state"], "NOT_CONFIGURED")
        # mutation → INVALID
        lines = ledger.path.read_text().splitlines()
        d = json.loads(lines[-1])
        d["phase"] = "MUTATED"
        lines[-1] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        ledger.path.write_text("\n".join(lines) + "\n")
        report2 = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertEqual(report2["verifier"], "INVALID")
        self.assertFalse(report2["ledger"]["chain_valid"])

    def test_11_unknown_algorithm_fail_closed(self):
        be = DisposableTestBackend(tag=TEST_TAG, enrolled=True)
        adapter = ProductionSignerAdapter(backend=be)
        ledger = EvidenceLedger(self.td / "u.jsonl")
        ev = EvidenceSession(signer=adapter, ledger=ledger)
        governed_chat_completions_create(
            FakeClient(), _api_kwargs(), WingEgressContext(sources=(_src(),), evidence=ev)
        )
        entries = ledger.load_entries()
        e = dict(entries[0])
        # Tamper algorithm without resigning → digest fail
        e["signature_algorithm"] = "unknown-algo-xyz"
        self.assertFalse(verify_signed_receipt(e, adapter.public_key_bytes()))

    @unittest.skipUnless(
        os.environ.get("OMNIS_WING_R4_KEYCHAIN_IT") == "1",
        "opt-in real Keychain IT only",
    )
    def test_12_opt_in_real_keychain_if_enrolled(self):
        """Does not enroll. Uses Captain tag only if already ENROLLED. Never deletes."""
        from omnis_wing.absolute.production_signer import (
            MacOSKeychainBackend,
            default_bridge_binary,
            compile_keychain_bridge,
        )
        bridge = default_bridge_binary(self.td / "bridge-build")
        if not bridge.is_file():
            compile_keychain_bridge(self.td / "bridge-build")
            bridge = default_bridge_binary(self.td / "bridge-build")
        be = MacOSKeychainBackend(tag=CAPTAIN_R4_TAG, bridge_path=bridge)
        adapter = ProductionSignerAdapter(backend=be)
        st = adapter.enrollment_status()
        if not st.get("ready"):
            self.skipTest("Captain tag not enrolled on this machine")
        self.assertEqual(st.get("storage_state"), "UNVERIFIED_AT_READ")
        ledger = EvidenceLedger(self.td / "kc-ledger.jsonl")
        ev = EvidenceSession(signer=adapter, ledger=ledger)
        client = FakeClient()
        interruptible_api_call(
            MiniAgent(WingEgressContext(sources=(_src(),), evidence=ev), client),
            _api_kwargs(),
        )
        self.assertEqual(client.create_calls, 1)
        ok, reason = ledger.verify_chain(adapter.public_key_bytes())
        self.assertTrue(ok, reason)
        report = build_health_report(root=ROOT, ledger=ledger, signer=adapter)
        self.assertTrue(report["ledger"]["chain_valid"])
        self.assertEqual(report["remote_anchor"]["state"], "NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
