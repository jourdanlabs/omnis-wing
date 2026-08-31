"""R3 evidence spine cold controls on the selected R2.1 chat path."""

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

_tmp_home = tempfile.mkdtemp(prefix="omnis-wing-r3-home-")
os.environ["WING_HOME"] = _tmp_home
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
for _name in ("requests", "yaml"):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        if _name == "yaml":
            _m.safe_load = lambda stream: {}  # type: ignore
        sys.modules[_name] = _m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()
os.environ.setdefault("OMNIS_WING_SIGNER_MODE", "test")

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.envelope import SourceProvenance  # noqa: E402
from omnis_wing.absolute.wing_chat_join import (  # noqa: E402
    EvidenceSession,
    OutcomeUnknownError,
    WingEgressContext,
    WingRefusal,
)
from omnis_wing.absolute.transport_broker import get_broker  # noqa: E402
from omnis_wing.absolute.receipt_spine import (  # noqa: E402
    EvidenceLedger,
    UnavailableSigner,
    ledger_outcome_report,
    make_test_signer,
    verify_anchor,
    verify_signed_receipt,
    write_anchor,
)
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402

CADMUS_R3 = ROOT / "omnis_wing" / "spec" / "omnis-wing-r3-evidence-spine.cadmus-input.json"
CADMUS_R3_SHA = "6f7563d2bfe9f3dc752c5d395ed153a6fb944332ad5f56ae84bc64a4af202f23"
US_BASE = "https://ai.example.test/v1"
CN_BASE = "https://api.moonshot.cn/v1"


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
        self.last_kwargs: dict = {}
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs: Any) -> Any:
        self.create_calls += 1
        self.last_kwargs = dict(kwargs)
        return SimpleNamespace(id="fake", choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

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


MESSAGES = [{"role": "user", "content": "hello r3"}]


def _api_kwargs(**extra):
    kw = {"model": "m", "messages": list(MESSAGES), "temperature": 0}
    kw.update(extra)
    return kw


def _src(classification="generic"):
    d = hashlib.sha256(b"x").hexdigest()
    return SourceProvenance(
        path="n.txt",
        content_digest=d,
        classification=classification,
        protected_root=classification != "generic",
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )


def _session(dirpath: Path, signer=None) -> EvidenceSession:
    return EvidenceSession(
        signer=signer if signer is not None else make_test_signer(),
        ledger=EvidenceLedger(dirpath / "ledger.jsonl"),
    )


class R3EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="r3-ev-"))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_00_cadmus_r3(self):
        self.assertEqual(_sha_file(CADMUS_R3), CADMUS_R3_SHA)

    def test_01_generic_permit_signed_evidence_on_path(self):
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        resp = interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        self.assertIsNotNone(ev.last_signed)
        pk = ev.signer.public_key_bytes()
        self.assertTrue(verify_signed_receipt(ev.last_signed, pk))
        ok, reason = ev.ledger.verify_chain(pk)
        self.assertTrue(ok, reason)
        entries = ev.ledger.load_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["phase"], "TRANSMISSION_STARTED")
        self.assertEqual(entries[1]["phase"], "TRANSMISSION_COMPLETED")
        self.assertEqual(ev.last_signed.decision, "PERMIT")
        self.assertEqual(ev.last_signed.phase, "TRANSMISSION_COMPLETED")
        self.assertEqual(ev.last_signed.residency, "US")
        self.assertEqual(ledger_outcome_report(ev.ledger)["status"], "terminal_complete")

    def test_02_protected_cn_signed_refusal_client_0(self):
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("project"),), evidence=ev)
        client = FakeClient(CN_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_RESIDENCY")
        self.assertEqual(client.create_calls, 0)
        self.assertIsNotNone(cm.exception.signed)
        self.assertEqual(cm.exception.signed.decision, "REFUSE_RESIDENCY")
        self.assertTrue(verify_signed_receipt(cm.exception.signed, ev.signer.public_key_bytes()))

    def test_03_one_byte_receipt_mutation_fails_verify(self):
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        get_broker().transmit_chat_completions(FakeClient(US_BASE), _api_kwargs(), ctx)
        signed = ev.last_signed.to_dict()
        # mutate one byte in signature
        hx = signed["signature_hex"]
        flipped = ("0" if hx[0] != "0" else "1") + hx[1:]
        signed["signature_hex"] = flipped
        self.assertFalse(verify_signed_receipt(signed, ev.signer.public_key_bytes()))
        # mutate receipt_digest body field
        signed2 = ev.last_signed.to_dict()
        signed2["decision"] = "PERMIT" if signed2["decision"] != "PERMIT" else "REFUSE_SECRET"
        self.assertFalse(verify_signed_receipt(signed2, ev.signer.public_key_bytes()))

    def test_04_ledger_rewrite_fails_anchor(self):
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        get_broker().transmit_chat_completions(FakeClient(US_BASE), _api_kwargs(), ctx)
        anchor_path = self.td / "anchor.json"
        write_anchor(
            anchor_path,
            chain_head_digest=ev.ledger.head_digest(),
            key_id=ev.signer.key_id,
            public_key_hex=ev.signer.public_key_bytes().hex(),
        )
        ok, _ = verify_anchor(anchor_path, ev.ledger)
        self.assertTrue(ok)
        # Replace ledger with a fresh alternate chain
        alt = EvidenceLedger(self.td / "ledger.jsonl")
        # overwrite file with a different valid chain from another signer/session
        other_dir = self.td / "other"
        other_dir.mkdir()
        ev2 = _session(other_dir)
        ctx2 = WingEgressContext(sources=(_src("generic"),), evidence=ev2)
        get_broker().transmit_chat_completions(FakeClient(US_BASE), _api_kwargs(), ctx2)
        # copy other ledger over original
        shutil.copy(ev2.ledger.path, ev.ledger.path)
        ok2, reason = verify_anchor(anchor_path, ev.ledger)
        self.assertFalse(ok2)
        self.assertEqual(reason, "anchor_head_mismatch")

    def test_05_signer_unavailable_refuse_client_0(self):
        ev = EvidenceSession(
            signer=UnavailableSigner(),
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_06_secret_absent_from_receipt_ledger_anchor_exception(self):
        secret = PLANTED_SECRET_MARKERS[0]
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                MiniAgent(ctx, client),
                _api_kwargs(extra_body={"note": secret}),
            )
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SECRET")
        self.assertEqual(client.create_calls, 0)
        blobs = [
            str(cm.exception),
            cm.exception.receipt.serialize_for_hygiene(),
            cm.exception.signed.serialize() if cm.exception.signed else "",
            ev.ledger.path.read_text(encoding="utf-8"),
        ]
        anchor_path = self.td / "anchor.json"
        if cm.exception.signed:
            write_anchor(
                anchor_path,
                chain_head_digest=ev.ledger.head_digest(),
                key_id=ev.signer.key_id,
                public_key_hex=ev.signer.public_key_bytes().hex(),
            )
            blobs.append(anchor_path.read_text(encoding="utf-8"))
        bare = hashlib.sha256(secret.encode()).hexdigest()
        for b in blobs:
            self.assertNotIn(secret, b)
            self.assertNotIn(bare, b)



    # ── R3.1 P0-A ────────────────────────────────────────────────────────

    def test_07_noncanonical_S_plus_L_fails_verify(self):
        """Valid sig with S replaced by S+L must not verify (RFC 8032)."""
        signer = make_test_signer()
        msg = b"omnis-wing-r3-canonical-scalar"
        sig = signer.sign(msg)
        self.assertTrue(signer.verify(msg, sig))
        from omnis_wing.absolute.ed25519_pure import l as L

        S = int.from_bytes(sig[32:], "little")
        mutated = sig[:32] + (S + L).to_bytes(32, "little")
        self.assertNotEqual(sig, mutated)
        self.assertTrue(signer.verify(msg, sig))
        self.assertFalse(signer.verify(msg, mutated))
        # Also via receipt path
        ev = _session(self.td)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        get_broker().transmit_chat_completions(FakeClient(US_BASE), _api_kwargs(), ctx)
        d = ev.last_signed.to_dict()
        hx = d["signature_hex"]
        raw = bytes.fromhex(hx)
        S2 = int.from_bytes(raw[32:], "little")
        mut2 = raw[:32] + (S2 + L).to_bytes(32, "little")
        d["signature_hex"] = mut2.hex()
        self.assertFalse(verify_signed_receipt(d, signer.public_key_bytes()))

    # ── R3.1 P0-B ────────────────────────────────────────────────────────

    def test_08_sign_raises_before_send_client_0(self):
        class BoomSigner:
            key_id = "boom"

            def available(self):
                return True

            def public_key_bytes(self):
                return make_test_signer().public_key_bytes()

            def sign(self, message: bytes) -> bytes:
                raise RuntimeError("signer backend exploded")

        ev = EvidenceSession(
            signer=BoomSigner(),
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertIn("pre_send_evidence_failed", cm.exception.receipt.reason)
        self.assertEqual(client.create_calls, 0)
        self.assertEqual(ev.ledger.path.read_bytes(), b"")

    def test_09_ledger_not_appendable_before_send_client_0(self):
        ledger = EvidenceLedger(self.td / "ledger.jsonl")
        ledger._force_unappendable = True  # type: ignore[attr-defined]
        ev = EvidenceSession(signer=make_test_signer(), ledger=ledger)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_10_terminal_sign_fail_after_provider_outcome_unknown(self):
        class FailTerminalSigner:
            def __init__(self):
                self.inner = make_test_signer()
                self.key_id = self.inner.key_id
                self.n = 0

            def available(self):
                return True

            def public_key_bytes(self):
                return self.inner.public_key_bytes()

            def sign(self, message: bytes) -> bytes:
                self.n += 1
                if self.n >= 2:
                    raise RuntimeError("terminal sign fail")
                return self.inner.sign(message)

        signer = FailTerminalSigner()
        ev = EvidenceSession(
            signer=signer,
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(OutcomeUnknownError) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.client_calls, 1)
        self.assertEqual(client.create_calls, 1)
        self.assertIsNotNone(cm.exception.pre_send_signed)
        self.assertEqual(cm.exception.pre_send_signed.phase, "TRANSMISSION_STARTED")
        self.assertTrue(
            verify_signed_receipt(
                cm.exception.pre_send_signed, signer.public_key_bytes()
            )
        )
        # Durable start only — no COMPLETED terminal success
        entries = ev.ledger.load_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["phase"], "TRANSMISSION_STARTED")
        report = ledger_outcome_report(ev.ledger)
        self.assertEqual(report["status"], "OUTCOME_UNKNOWN")
        self.assertTrue(report["terminal_missing"])
        # Caller must not treat as normal success (exception raised)

    def test_11_p0b_evidence_hygiene_no_secret(self):
        secret = PLANTED_SECRET_MARKERS[0]
        class BoomSigner:
            key_id = "boom"
            def available(self):
                return True
            def public_key_bytes(self):
                return make_test_signer().public_key_bytes()
            def sign(self, message: bytes) -> bytes:
                raise RuntimeError("signer backend exploded")
        ev = EvidenceSession(
            signer=BoomSigner(),
            ledger=EvidenceLedger(self.td / "ledger.jsonl"),
        )
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        # even with secret in body, refuse path must not leak
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                MiniAgent(ctx, client),
                _api_kwargs(extra_body={"note": secret}),
            )
        # may be REFUSE_SECRET if eval happens before pre-send... 
        # Order: ensure ledger, build envelope, evaluate (secret → REFUSE_SECRET), try sign refuse
        # BoomSigner will fail signing refuse → signed=None, still WingRefusal REFUSE_SECRET
        self.assertEqual(client.create_calls, 0)
        blob = str(cm.exception) + cm.exception.receipt.serialize_for_hygiene()
        bare = hashlib.sha256(secret.encode()).hexdigest()
        self.assertNotIn(secret, blob)
        self.assertNotIn(bare, blob)



    def test_12_pre_send_fsync_fail_client_0_no_flattering(self):
        """fsync fail on first (pre-send) append → refuse, client 0, no durable start."""
        ledger = EvidenceLedger(self.td / "ledger.jsonl")
        ledger._force_fsync_fail_on = 1  # type: ignore[attr-defined]
        ledger._skip_ensure_fsync_probe = True  # type: ignore[attr-defined]
        ev = EvidenceSession(signer=make_test_signer(), ledger=ledger)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertIn("pre_send_evidence_failed", cm.exception.receipt.reason)
        self.assertEqual(client.create_calls, 0)
        self.assertEqual(ev.ledger.load_entries(), [])
        secret = PLANTED_SECRET_MARKERS[0]
        blob = str(cm.exception) + cm.exception.receipt.serialize_for_hygiene()
        self.assertNotIn(secret, blob)

    def test_13_terminal_fsync_fail_outcome_unknown_preserves_presend(self):
        """fsync fail on second (terminal) append after provider → OutcomeUnknown."""
        ledger = EvidenceLedger(self.td / "ledger.jsonl")
        ledger._force_fsync_fail_on = 2  # type: ignore[attr-defined]
        ledger._skip_ensure_fsync_probe = True  # type: ignore[attr-defined]
        ev = EvidenceSession(signer=make_test_signer(), ledger=ledger)
        ctx = WingEgressContext(sources=(_src("generic"),), evidence=ev)
        client = FakeClient(US_BASE)
        with self.assertRaises(OutcomeUnknownError) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.client_calls, 1)
        self.assertEqual(client.create_calls, 1)
        entries = ev.ledger.load_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["phase"], "TRANSMISSION_STARTED")
        self.assertTrue(
            verify_signed_receipt(entries[0], make_test_signer().public_key_bytes())
        )
        report = ledger_outcome_report(ev.ledger)
        self.assertEqual(report["status"], "OUTCOME_UNKNOWN")
        self.assertTrue(report["terminal_missing"])
        # not a normal success path
        self.assertIsNotNone(cm.exception.pre_send_signed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
