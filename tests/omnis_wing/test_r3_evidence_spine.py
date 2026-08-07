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
from omnis_wing.absolute.receipt_spine import (  # noqa: E402
    EvidenceLedger,
    UnavailableSigner,
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
        self.assertEqual(ev.last_signed.decision, "PERMIT")
        self.assertEqual(ev.last_signed.phase, "TRANSMISSION_COMPLETED")
        self.assertEqual(ev.last_signed.residency, "US")

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
        governed_chat_completions_create(FakeClient(US_BASE), _api_kwargs(), ctx)
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
        governed_chat_completions_create(FakeClient(US_BASE), _api_kwargs(), ctx)
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
        governed_chat_completions_create(FakeClient(US_BASE), _api_kwargs(), ctx2)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
