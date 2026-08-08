"""P0 HOLD repairs can-fails — Bulma SPEC WING-P0-M1-M7-THIS-ONE-FIRST.

Cold only. No live provider. No Keychain. No cutover.
"""

from __future__ import annotations

import ast
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

_tmp = tempfile.mkdtemp(prefix="wing-p0hold-")
os.environ["HERMES_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = str(Path(_tmp) / "led")
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
os.environ.pop("OMNIS_WING_POLICY_PATH", None)
os.environ.pop("OMNIS_WING_POLICY_TRUST_PATH", None)
os.environ.pop("OMNIS_WING_POLICY_KEY_ID", None)
os.environ.pop("OMNIS_WING_POLICY_PUBKEY_HEX", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env, refresh_signed_policy  # noqa: E402

bootstrap_wing_test_env()

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.broker_guard import (  # noqa: E402
    BrokerViolation,
    assert_no_agent_governed_bypass,
    require_broker_dispatch,
)
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.preflight import run_preflight  # noqa: E402
from omnis_wing.absolute.signed_policy import (  # noqa: E402
    PolicyError,
    TEST_POLICY_KEY_ID,
    TEST_POLICY_PUBLIC_KEY,
    TEST_POLICY_SEED,
    clear_process_trust_store,
    install_test_policy_trust,
    load_policy,
    make_test_signed_policy,
    policy_digest_hex,
    sign_policy_document,
    write_test_policy_file,
)
from omnis_wing.absolute.source_taint import classify_content_bytes  # noqa: E402
from omnis_wing.absolute.transport_broker import get_broker, reset_broker_for_tests  # noqa: E402
from omnis_wing.completion.product_disable import load_manifest  # noqa: E402

US = "https://ai.example.test/v1"
PROJECT_BODY = 'def proprietary_engine():\n    return "jourdanlabs internal"\n'


class FakeClient:
    is_fake = True

    def __init__(self, base_url=US):
        self.base_url = base_url
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


def _kw(content="hello operator", **extra):
    b = {"model": "m", "messages": [{"role": "user", "content": content}], "temperature": 0}
    b.update(extra)
    return b


class P0_1_ForceClassificationTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        bootstrap_wing_test_env()

    def test_spec_repro_force_no_longer_downgrades(self):
        p = PROJECT_BODY.encode()
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        self.assertEqual(classify_content_bytes(p).classification, "project")
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
        try:
            # Must still be project — env must not change classification
            self.assertEqual(classify_content_bytes(p).classification, "project")
        finally:
            os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)

    def test_static_product_modules_no_force_read(self):
        product_roots = [
            ROOT / "omnis_wing" / "absolute",
            ROOT / "omnis_wing" / "completion",
        ]
        banned = "OMNIS_WING_FORCE_CLASSIFICATION"
        offenders = []
        for base in product_roots:
            for path in base.rglob("*.py"):
                if path.name == "preflight.py":
                    # preflight may *detect* the env to refuse it; must not use it to classify
                    text = path.read_text(encoding="utf-8")
                    self.assertIn(banned, text)
                    # ensure not used in classify path — only error append
                    self.assertIn("force_classification_env_forbidden", text)
                    continue
                text = path.read_text(encoding="utf-8")
                if banned in text:
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], msg=f"product force reads: {offenders}")

    def test_real_join_force_env_project_refuses_zero_provider(self):
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
        try:
            client = FakeClient(US)
            agent = MiniAgent(client)
            with self.assertRaises(WingRefusal) as cm:
                interruptible_api_call(agent, _kw(PROJECT_BODY))
            self.assertIn(
                cm.exception.receipt.decision,
                ("REFUSE_SOURCE_POLICY", "REFUSE_RESIDENCY", "REFUSE_CROWN_JEWEL", "REFUSE_SECRET"),
            )
            self.assertEqual(client.create_calls, 0)
        finally:
            os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)

    def test_real_join_unknown_source_zero_provider(self):
        # high binary ratio → unknown
        blob = bytes([0, 1, 2, 3, 255, 254] * 80)
        text = blob.decode("latin-1")
        client = FakeClient(US)
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw(text))
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

    def test_preflight_refuses_force_env(self):
        os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
        try:
            r = run_preflight()
            self.assertFalse(r.ok)
            self.assertTrue(any("force_classification" in e for e in r.errors))
        finally:
            os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)


class P0_2_BrokerSoleJoinTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        bootstrap_wing_test_env()
        reset_broker_for_tests()

    def test_source_guard_agent_trees_clean(self):
        assert_no_agent_governed_bypass(ROOT)

    def test_direct_governed_call_raises(self):
        from omnis_wing.absolute.hermes_chat_join import governed_chat_completions_create
        from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context

        client = FakeClient()
        agent = MiniAgent(client)
        ctx = ensure_agent_wing_context(agent, _kw())
        with self.assertRaises(BrokerViolation):
            governed_chat_completions_create(client, _kw(), ctx)
        self.assertEqual(client.create_calls, 0)

    def test_broker_path_permits_generic(self):
        client = FakeClient()
        agent = MiniAgent(client)
        from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context

        ctx = ensure_agent_wing_context(agent, _kw("hi there"))
        get_broker().transmit_chat_completions(client, _kw("hi there"), ctx)
        self.assertEqual(client.create_calls, 1)

    def test_real_agent_path_traverses_broker(self):
        """Instrument broker; interruptible path must hit it once before provider."""
        client = FakeClient()
        agent = MiniAgent(client)
        hits = {"n": 0}
        br = get_broker()
        orig = br.transmit_chat_completions

        def wrapped(c, kw, ctx):
            hits["n"] += 1
            return orig(c, kw, ctx)

        br.transmit_chat_completions = wrapped  # type: ignore[method-assign]
        try:
            interruptible_api_call(agent, _kw("hello operator chat"))
            self.assertEqual(hits["n"], 1)
            self.assertEqual(client.create_calls, 1)
        finally:
            br.transmit_chat_completions = orig  # type: ignore[method-assign]

    def test_manifest_governed_routes_name_broker(self):
        man = load_manifest()
        for r in man["routes"]:
            if r["state"] != "GOVERNED":
                continue
            if r.get("broker_join") in ("N/A_NAMED_PROBE", "DISABLED"):
                continue
            bj = r.get("broker_join") or ""
            self.assertIn(
                "transport_broker.TransportBroker",
                bj,
                msg=f"{r['route_id']} broker_join={bj}",
            )


class P0_3_SignedPolicyTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        clear_process_trust_store()
        install_test_policy_trust()
        bootstrap_wing_test_env(force=True)

    def tearDown(self):
        install_test_policy_trust()
        bootstrap_wing_test_env(force=True)

    def test_unsigned_default_refused(self):
        clear_process_trust_store()
        os.environ.pop("OMNIS_WING_POLICY_PATH", None)
        with self.assertRaises(PolicyError) as cm:
            load_policy()
        self.assertIn(str(cm.exception), ("policy_missing", "policy_trust_empty"))

    def test_digest_recompute_without_signature_refuses(self):
        """Attack: modify mode, recompute digest, leave/old-break signature."""
        td = Path(tempfile.mkdtemp())
        try:
            doc = make_test_signed_policy({"mode": "enforce"})
            # attacker flips mode and rewrites digest only
            body = {k: v for k, v in doc.items() if k not in ("signature", "policy_digest")}
            body["mode"] = "local_only"
            body["policy_digest"] = policy_digest_hex(body)
            # keep original signature (now invalid) OR drop signature and only keep digest
            body["signature"] = doc["signature"]  # stale sig over old body
            pf = td / "evil.json"
            pf.write_text(json.dumps(body))
            os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
            install_test_policy_trust()
            with self.assertRaises(PolicyError) as cm:
                load_policy()
            self.assertIn(
                str(cm.exception),
                ("policy_signature_invalid", "policy_digest_mismatch"),
            )
            # preflight red
            r = run_preflight()
            self.assertFalse(r.ok)
            # real path refuse, provider 0
            client = FakeClient()
            agent = MiniAgent(client)
            with self.assertRaises(WingRefusal):
                interruptible_api_call(agent, _kw("hello"))
            self.assertEqual(client.create_calls, 0)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_unknown_key_id_refuses(self):
        td = Path(tempfile.mkdtemp())
        try:
            doc = sign_policy_document(
                {
                    "mode": "enforce",
                    "policy_version": "t",
                    "file_count_ceiling": 50,
                    "byte_ceiling": 1000,
                    "require_remote_anchor": False,
                },
                seed=TEST_POLICY_SEED,
                key_id="not-a-trusted-key",
            )
            pf = td / "p.json"
            pf.write_text(json.dumps(doc))
            os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
            install_test_policy_trust()  # only TEST_POLICY_KEY_ID
            with self.assertRaises(PolicyError) as cm:
                load_policy()
            self.assertTrue(str(cm.exception).startswith("policy_unknown_key_id"))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_absent_signature_refuses(self):
        td = Path(tempfile.mkdtemp())
        try:
            body = {
                "mode": "enforce",
                "policy_version": "t",
                "file_count_ceiling": 50,
                "byte_ceiling": 1000,
                "require_remote_anchor": False,
                "policy_digest": "abc",
            }
            pf = td / "p.json"
            pf.write_text(json.dumps(body))
            os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
            install_test_policy_trust()
            with self.assertRaises(PolicyError) as cm:
                load_policy()
            self.assertEqual(str(cm.exception), "policy_unsigned")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_stale_policy_refuses(self):
        td = Path(tempfile.mkdtemp())
        try:
            write_test_policy_file(
                td / "p.json",
                overrides={"not_after": 1, "issued_at": 1},
                install_trust=True,
            )
            os.environ["OMNIS_WING_POLICY_PATH"] = str(td / "p.json")
            with self.assertRaises(PolicyError) as cm:
                load_policy()
            self.assertEqual(str(cm.exception), "policy_stale")
            r = run_preflight()
            self.assertFalse(r.ok)
            client = FakeClient()
            agent = MiniAgent(client)
            with self.assertRaises(WingRefusal):
                interruptible_api_call(agent, _kw("hello"))
            self.assertEqual(client.create_calls, 0)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_valid_signed_policy_loads_and_health_digest(self):
        p = load_policy()
        self.assertTrue(p.signature_valid)
        self.assertEqual(p.mode, "enforce")
        self.assertEqual(p.key_id, TEST_POLICY_KEY_ID)
        self.assertTrue(p.policy_digest)
        # glass/health may show digest only after verification
        from omnis_wing.absolute.glass import glass_state

        g = glass_state(
            signer_ready=True,
            chain_valid=True,
            policy_valid=True,
            policy_mode=p.mode,
            anchor_state="REMOTE_ANCHOR_NOT_CONFIGURED",
            require_anchor=False,
            ungoverned_route=False,
        )
        self.assertEqual(g["color"], "GREEN")

    def test_modified_ceiling_invalid_sig_zero_provider(self):
        td = Path(tempfile.mkdtemp())
        try:
            doc = make_test_signed_policy()
            doc["file_count_ceiling"] = 999999  # tamper body; keep old signature
            pf = td / "p.json"
            pf.write_text(json.dumps(doc))
            os.environ["OMNIS_WING_POLICY_PATH"] = str(pf)
            install_test_policy_trust()
            with self.assertRaises(PolicyError):
                load_policy()
            client = FakeClient()
            agent = MiniAgent(client)
            with self.assertRaises(WingRefusal):
                interruptible_api_call(agent, _kw("hello"))
            self.assertEqual(client.create_calls, 0)
        finally:
            shutil.rmtree(td, ignore_errors=True)


class HonestColdSuiteSmoke(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        bootstrap_wing_test_env(force=True)

    def test_generic_permit_without_force_env(self):
        self.assertNotIn("OMNIS_WING_FORCE_CLASSIFICATION", os.environ)
        client = FakeClient()
        agent = MiniAgent(client)
        interruptible_api_call(agent, _kw("hello operator"))
        self.assertEqual(client.create_calls, 1)

    def test_product_classifier_no_os_environ_force(self):
        # AST: source_taint + payload_policy must not reference the env name
        for rel in (
            "omnis_wing/absolute/source_taint.py",
            "omnis_wing/absolute/payload_policy.py",
            "omnis_wing/absolute/auto_provenance.py",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("OMNIS_WING_FORCE_CLASSIFICATION", src, msg=rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
