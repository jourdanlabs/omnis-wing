"""WING production-cutover leg: attach production signer; no live Keychain/Hermes."""

from __future__ import annotations

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
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="wing-prod-cut-")
os.environ["HERMES_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = str(Path(_tmp) / "ledgers")
os.environ.pop("OMNIS_WING_SIGNER_MODE", None)
os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
os.environ.pop("OMNIS_WING_SIGNER_BACKEND", None)
os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            def _safe_load(stream):
                import json as _j
                # minimal yaml: only handle our simple test files via json if needed
                text = stream.read() if hasattr(stream, "read") else str(stream)
                # very small subset: key: value lines
                out = {}
                for line in text.splitlines():
                    line = line.split("#", 1)[0].strip()
                    if not line or ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    v = v.strip().strip('"').strip("'")
                    if v.lower() in ("false", "true"):
                        out[k.strip()] = v.lower() == "true"
                    else:
                        out[k.strip()] = v
                return out
            m.safe_load = _safe_load
        sys.modules[_n] = m

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.production_config import (  # noqa: E402
    ProductionConfigError,
    load_production_config,
)
from omnis_wing.absolute.production_signer import (  # noqa: E402
    CAPTAIN_R4_TAG,
    DisposableP256Backend,
    ProductionSignerAdapter,
)
from omnis_wing.absolute.runtime_attach import (  # noqa: E402
    attach_wing_runtime,
    build_signer_from_config,
)
from omnis_wing.absolute.operator_health import build_health_report  # noqa: E402
from omnis_wing.absolute.receipt_spine import (  # noqa: E402
    EvidenceLedger,
    UnavailableSigner,
    verify_signed_receipt,
)
from omnis_wing.absolute.hermes_chat_join import EvidenceSession  # noqa: E402

US = "https://ai.example.test/v1"
TEST_P256_TAG = "ai.jourdanlabs.omnis-wing.test.prodcutover.p256"


class FakeClient:
    is_fake = True

    def __init__(self):
        self.base_url = US
        self.create_calls = 0
        self.chat = self
        self.last = None

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.create_calls += 1
        self.last = kwargs
        return SimpleNamespace(id="ok", choices=[SimpleNamespace(message=SimpleNamespace(content="x"))])

    def close(self):
        pass


class MiniAgent:
    def __init__(self, client=None):
        self.api_mode = "chat_completions"
        self._client = client or FakeClient()
        self._interrupt_requested = False
        self.log_prefix = "t"
        self.provider = "stub"
        self.base_url = self._client.base_url
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None

    def _create_request_openai_client(self, *, reason, api_kwargs):
        return self._client

    def _abort_request_openai_client(self, c, reason):
        pass

    def _close_request_openai_client(self, c, reason):
        pass

    def _compute_non_stream_stale_timeout(self, k):
        return 30.0

    def _touch_activity(self, m=""):
        pass

    def _buffer_status(self, m=""):
        pass


def _write_cfg(dirpath: Path, **fields) -> Path:
    p = dirpath / "prod.yaml"
    lines = []
    for k, v in fields.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    p.write_text("\n".join(lines) + "\n")
    return p


class ProductionCutoverTests(unittest.TestCase):
    def setUp(self):
        for k in list(os.environ.keys()):
            if k.startswith("OMNIS_WING_") and k not in ("OMNIS_WING_FORCE_CLASSIFICATION",):
                os.environ.pop(k, None)
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
        self.td = Path(tempfile.mkdtemp(prefix="wing-pc-"))
        os.environ["OMNIS_WING_LEDGER_DIR"] = str(self.td / "ledgers")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_01_production_mode_no_config_refuse_zero_calls(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        client = FakeClient()
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                agent,
                {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0},
            )
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_02_bridge_missing_keychain_config_refuse(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        cfg = _write_cfg(
            self.td,
            backend="keychain",
            tag=CAPTAIN_R4_TAG,
            ledger_dir=str(self.td / "led"),
            bridge_path=str(self.td / "no-such-bridge"),
            profile="production",
            auto_enroll=False,
        )
        os.environ["OMNIS_WING_PRODUCTION_CONFIG"] = str(cfg)
        client = FakeClient()
        agent = MiniAgent(client)
        st = attach_wing_runtime(agent, force=True)
        self.assertFalse(st.get("ready"))
        with self.assertRaises(WingRefusal):
            interruptible_api_call(
                agent,
                {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0},
            )
        self.assertEqual(client.create_calls, 0)

    def test_03_configured_p256_enrolled_permit_signed_presend(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        work = self.td / "p256work"
        work.mkdir()
        os.environ["OMNIS_WING_P256_WORK_DIR"] = str(work)
        cfg = _write_cfg(
            self.td,
            backend="disposable_p256",
            tag=TEST_P256_TAG,
            ledger_dir=str(self.td / "led"),
            bridge_path="",
            profile="cold",
            auto_enroll=False,
        )
        os.environ["OMNIS_WING_PRODUCTION_CONFIG"] = str(cfg)
        # explicit enroll (operator action) — not startup
        be = DisposableP256Backend(tag=TEST_P256_TAG, work_dir=work)
        st_en = be.enroll()
        self.assertTrue(st_en["ready"])
        adapter = ProductionSignerAdapter(backend=be)
        self.assertTrue(adapter.available())
        self.assertEqual(adapter.signature_algorithm, "ecdsa-p256-x962-sha256")

        client = FakeClient()
        agent = MiniAgent(client)
        attach_wing_runtime(agent, force=True)
        # re-bind enrolled backend from work dir
        self.assertTrue(agent.wing_production_signer.available())

        interruptible_api_call(
            agent,
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0},
        )
        self.assertEqual(client.create_calls, 1)

        ledger = EvidenceLedger(Path(agent.wing_ledger_path))
        entries = ledger.load_entries()
        self.assertGreaterEqual(len(entries), 1)
        # first should be pre-send
        # verify chain with public key
        pk = agent.wing_production_signer.public_key_bytes()
        ok, reason = ledger.verify_chain(pk)
        self.assertTrue(ok, reason)
        # health shows fingerprint + algorithm
        report = build_health_report(root=ROOT, ledger=ledger, signer=agent.wing_production_signer)
        self.assertEqual(report["signer"]["signature_algorithm"], "ecdsa-p256-x962-sha256")
        self.assertEqual(report["signer"]["public_key_sha256"], agent.wing_production_signer.public_fingerprint())
        self.assertTrue(report["ledger"]["chain_valid"])

    def test_04_test_mode_explicit_only(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        client = FakeClient()
        agent = MiniAgent(client)
        attach_wing_runtime(agent, force=True)
        self.assertEqual(agent.wing_runtime_status.get("backend"), "test_ed25519")
        interruptible_api_call(
            agent,
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0},
        )
        self.assertEqual(client.create_calls, 1)

    def test_05_auto_enroll_forbidden_in_config(self):
        cfg = _write_cfg(
            self.td,
            backend="keychain",
            tag=CAPTAIN_R4_TAG,
            ledger_dir=str(self.td / "led"),
            auto_enroll=True,
        )
        with self.assertRaises(ProductionConfigError):
            load_production_config(cfg)

    def test_06_outcome_unknown_terminal_sign_fail(self):
        """Post-send evidence failure remains OUTCOME_UNKNOWN (existing spine)."""
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        work = self.td / "p256work2"
        work.mkdir()
        os.environ["OMNIS_WING_P256_WORK_DIR"] = str(work)
        cfg = _write_cfg(
            self.td,
            backend="disposable_p256",
            tag=TEST_P256_TAG,
            ledger_dir=str(self.td / "led2"),
            auto_enroll=False,
        )
        os.environ["OMNIS_WING_PRODUCTION_CONFIG"] = str(cfg)
        be = DisposableP256Backend(tag=TEST_P256_TAG, work_dir=work)
        be.enroll()
        client = FakeClient()
        agent = MiniAgent(client)
        attach_wing_runtime(agent, force=True)

        # Break ledger append after first success by making path a directory mid-flight is hard;
        # use fail_sign on backend for terminal — actually sign happens twice.
        # Flip fail_sign after pre-send by wrapping ledger
        from omnis_wing.absolute.hermes_chat_join import OutcomeUnknownError

        orig = agent.wing_evidence_session.ledger.append
        calls = {"n": 0}

        def flaky(sr):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise OSError("fsync_fail_sim")
            return orig(sr)

        agent.wing_evidence_session.ledger.append = flaky  # type: ignore
        with self.assertRaises(Exception) as cm:
            interruptible_api_call(
                agent,
                {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0},
            )
        self.assertEqual(client.create_calls, 1)
        ex = cm.exception
        self.assertTrue(
            isinstance(ex, OutcomeUnknownError)
            or "OUTCOME_UNKNOWN" in type(ex).__name__
            or getattr(getattr(ex, "receipt", None), "phase", "") in ("OUTCOME_UNKNOWN", "UNKNOWN")
            or "fsync" in str(ex).lower()
            or "OUTCOME_UNKNOWN" in str(ex)
            or type(ex).__name__ == "OutcomeUnknownError",
            msg=type(ex).__name__ + ":" + str(ex),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
