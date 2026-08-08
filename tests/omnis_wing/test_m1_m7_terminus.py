"""M1–M7 TERMINUS ABSOLUTE WING cold can-fails. No live provider. No Keychain."""

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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="wing-m17-")
os.environ["HERMES_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = str(Path(_tmp) / "led")
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
os.environ.pop("OMNIS_WING_POLICY_PATH", None)
os.environ.pop("OMNIS_WING_ANCHOR_PATH", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.source_taint import (  # noqa: E402
    classify_content_bytes,
    merge_taint,
    taint_concat,
    taint_summarize,
    check_repo_breadth,
    read_file_with_provenance,
)
from omnis_wing.absolute.redact import redact_local, confirm_redacted_send_body  # noqa: E402
from omnis_wing.absolute.external_anchor import LocalFileAnchor, resolve_anchor_status  # noqa: E402
from omnis_wing.absolute.signed_policy import load_policy, PolicyError  # noqa: E402
from omnis_wing.absolute.glass import glass_state  # noqa: E402
from omnis_wing.absolute.preflight import run_preflight  # noqa: E402
from omnis_wing.absolute.transport_broker import get_broker  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402
from omnis_wing.absolute.receipt_spine import make_test_signer, EvidenceLedger  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import EvidenceSession, WingEgressContext  # noqa: E402
from omnis_wing.completion.product_disable import load_manifest  # noqa: E402

CADMUS = ROOT / "omnis_wing/spec/omnis-wing-m1-m7-terminus-absolute.cadmus-input.json"
CADMUS_SHA = "0f578b80374aeb1d78c1604071dfc814e2e26037e6501ce28d61b4abe589b2ad"
US = "https://ai.example.test/v1"


def _sha(p: Path) -> str:
    t = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    if t.startswith("\ufeff"):
        t = t[1:]
    return hashlib.sha256(t.encode()).hexdigest()


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

    def create(self, **k):
        self.create_calls += 1
        self.last = k
        return SimpleNamespace(id="ok", choices=[])

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

    def _create_request_openai_client(self, **k):
        return self._client

    def _abort_request_openai_client(self, *a, **k):
        pass

    def _close_request_openai_client(self, *a, **k):
        pass

    def _compute_non_stream_stale_timeout(self, k):
        return 30.0

    def _touch_activity(self, m=""):
        pass

    def _buffer_status(self, m=""):
        pass


def _kw(content="hello", **extra):
    b = {"model": "m", "messages": [{"role": "user", "content": content}], "temperature": 0}
    b.update(extra)
    return b


class M1TaintTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"

    def test_00_cadmus(self):
        self.assertTrue(CADMUS.is_file())
        self.assertEqual(_sha(CADMUS), CADMUS_SHA)

    def test_m1_secret_no_filename(self):
        rec = classify_content_bytes(PLANTED_SECRET_MARKERS[0].encode(), path_hint="")
        self.assertEqual(rec.classification, "credential")

    def test_m1_taint_survives_concat(self):
        a = classify_content_bytes(b"part-A-")
        b = classify_content_bytes(PLANTED_SECRET_MARKERS[0].encode())
        _, merged = taint_concat([(b"part-A-", a), (PLANTED_SECRET_MARKERS[0].encode(), b)])
        self.assertEqual(merged.classification, "credential")

    def test_m1_taint_survives_summary(self):
        parent = classify_content_bytes(b"OMNIS_WING_PROTECTED_FRAGMENT secret sauce")
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        try:
            parent = classify_content_bytes(b"OMNIS_WING_PROTECTED_FRAGMENT secret sauce")
            _, summ = taint_summarize(b"orig", "innocent paraphrase of the thing", parent)
            self.assertIn(summ.classification, ("protected", "project", "credential"))
        finally:
            os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"

    def test_m1_split_secret_reformed_in_concat(self):
        marker = PLANTED_SECRET_MARKERS[0]
        mid = len(marker) // 2
        left, right = marker[:mid], marker[mid:]
        _, merged = taint_concat(
            [
                (left.encode(), classify_content_bytes(left.encode())),
                (right.encode(), classify_content_bytes(right.encode())),
            ]
        )
        self.assertEqual(merged.classification, "credential")

    def test_m1_repo_breadth(self):
        self.assertIsNotNone(check_repo_breadth(999, 10))
        self.assertIsNotNone(check_repo_breadth(1, 9_999_999))
        self.assertIsNone(check_repo_breadth(1, 10))

    def test_m1_file_read_env(self):
        td = Path(tempfile.mkdtemp())
        env = td / ".env"
        env.write_text("export OPENAI_API_KEY=sk-test-not-real-1234567890abcd\n")
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        try:
            _, rec = read_file_with_provenance(env, root=td)
            self.assertIn(rec.classification, ("credential", "protected"))
        finally:
            os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
            shutil.rmtree(td, ignore_errors=True)

    def test_m1_protected_omitted_filename_refuses_provider(self):
        client = FakeClient()
        agent = MiniAgent(client)
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        try:
            with self.assertRaises(WingRefusal) as cm:
                interruptible_api_call(
                    agent, _kw("OMNIS_WING_PROTECTED_FRAGMENT in body without path")
                )
            self.assertIn(
                cm.exception.receipt.decision,
                ("REFUSE_SOURCE_POLICY", "REFUSE_CROWN_JEWEL", "REFUSE_SECRET"),
            )
            self.assertEqual(client.create_calls, 0)
        finally:
            os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"


class M2BrokerTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"

    def test_m2_manifest_states(self):
        man = load_manifest()
        for r in man["routes"]:
            self.assertIn(r["state"], ("GOVERNED", "DISABLED", "OUTSIDE_BOUNDARY"))

    def test_m2_broker_chat(self):
        client = FakeClient()
        agent = MiniAgent(client)
        from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context

        ctx = ensure_agent_wing_context(agent, _kw())
        get_broker().transmit_chat_completions(client, _kw(), ctx)
        self.assertEqual(client.create_calls, 1)


class M4RedactTests(unittest.TestCase):
    def test_m4_redact_sends_nothing_and_strips(self):
        prev = redact_local(f"leak {PLANTED_SECRET_MARKERS[0]} end")
        self.assertTrue(prev.sends_nothing)
        self.assertNotIn(PLANTED_SECRET_MARKERS[0], prev.redacted_text)
        self.assertNotEqual(prev.original_digest, prev.redacted_digest)
        body = confirm_redacted_send_body(prev, prev.redacted_text)
        self.assertTrue(body.get("__wing_new_envelope_required"))

    def test_m4_original_request_not_forwarded(self):
        client = FakeClient()
        agent = MiniAgent(client)
        # original hostile
        with self.assertRaises(WingRefusal):
            interruptible_api_call(agent, _kw(PLANTED_SECRET_MARKERS[0]))
        self.assertEqual(client.create_calls, 0)
        # redacted fresh body under generic force
        prev = redact_local(PLANTED_SECRET_MARKERS[0])
        interruptible_api_call(agent, _kw(prev.redacted_text))
        self.assertEqual(client.create_calls, 1)
        self.assertNotIn(PLANTED_SECRET_MARKERS[0], json.dumps(client.last))


class M5AnchorTests(unittest.TestCase):
    def test_m5_anchor_not_configured(self):
        os.environ.pop("OMNIS_WING_ANCHOR_PATH", None)
        st = resolve_anchor_status("abc")
        self.assertEqual(st.state, "REMOTE_ANCHOR_NOT_CONFIGURED")

    def test_m5_anchor_detects_ledger_replacement(self):
        td = Path(tempfile.mkdtemp())
        ap = td / "anchor.json"
        anc = LocalFileAnchor(ap)
        anc.publish("head-one")
        st = anc.status("head-two")
        self.assertEqual(st.state, "FAILED")
        shutil.rmtree(td, ignore_errors=True)


class M6PolicyGlassTests(unittest.TestCase):
    def test_m6_default_policy_enforce(self):
        p = load_policy()
        self.assertEqual(p.mode, "enforce")
        self.assertTrue(p.policy_digest)

    def test_m6_off_forbidden(self):
        td = Path(tempfile.mkdtemp())
        pf = td / "p.json"
        pf.write_text(json.dumps({"mode": "off", "policy_version": "x"}))
        os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
        try:
            with self.assertRaises(PolicyError):
                load_policy()
        finally:
            os.environ.pop("OMNIS_WING_POLICY_PATH", None)
            shutil.rmtree(td, ignore_errors=True)

    def test_m6_glass_red_without_signer(self):
        g = glass_state(
            signer_ready=False,
            chain_valid=True,
            policy_valid=True,
            policy_mode="enforce",
            anchor_state="REMOTE_ANCHOR_NOT_CONFIGURED",
            require_anchor=False,
            ungoverned_route=False,
        )
        self.assertEqual(g["color"], "RED")
        self.assertIn("IDE", g["outside_boundary"])


class M7PreflightTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_POLICY_PATH", None)

    def test_m7_preflight_test_mode_ok(self):
        r = run_preflight()
        self.assertTrue(r.ok, r.errors)
        self.assertIn("glass", r.glass)

    def test_m7_deny_all_blocks(self):
        td = Path(tempfile.mkdtemp())
        pf = td / "p.json"
        body = {
            "mode": "deny_all",
            "policy_version": "t",
            "file_count_ceiling": 50,
            "byte_ceiling": 1000,
            "require_remote_anchor": False,
        }
        # digest
        import copy
        dig = hashlib.sha256(
            json.dumps(
                {k: v for k, v in body.items()}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        # load_policy computes digest of body without policy_digest key
        pf.write_text(json.dumps(body))
        os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
        try:
            r = run_preflight()
            self.assertFalse(r.ok)
            self.assertTrue(any("deny_all" in e for e in r.errors))
        finally:
            os.environ.pop("OMNIS_WING_POLICY_PATH", None)
            shutil.rmtree(td, ignore_errors=True)


class ZeroToleranceSmoke(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"

    def test_zt_chat_secret_refuse_signed_absent(self):
        client = FakeClient()
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw(PLANTED_SECRET_MARKERS[0]))
        self.assertEqual(client.create_calls, 0)
        blob = json.dumps(cm.exception.receipt.to_dict())
        self.assertNotIn(PLANTED_SECRET_MARKERS[0], blob)

    def test_zt_cn_project_zero_bytes(self):
        client = FakeClient()
        client.base_url = "https://api.moonshot.cn/v1"
        agent = MiniAgent(client)
        agent.base_url = client.base_url
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        try:
            with self.assertRaises(WingRefusal):
                interruptible_api_call(
                    agent, _kw("def foo():\n  # chamber project\n  pass")
                )
            self.assertEqual(client.create_calls, 0)
        finally:
            os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"


if __name__ == "__main__":
    unittest.main(verbosity=2)
