"""FULL CADMUS residual zero-tolerance matrix — post P0 CLEAR (dfef719c2d).

No live provider. No Keychain. No live Hermes mutation.
"""

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
_tmp = tempfile.mkdtemp(prefix="wing-full-cadmus-")
os.environ["HERMES_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = str(Path(_tmp) / "led")
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
os.environ.pop("OMNIS_WING_ANCHOR_PATH", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402
from omnis_wing.absolute.transport_broker import get_broker  # noqa: E402
from omnis_wing.absolute.redirect_guard import (  # noqa: E402
    assert_no_redirect_transport,
    refuse_redirect_mutation,
)
from omnis_wing.absolute.hygiene import assert_secret_free, hygiene_violations  # noqa: E402
from omnis_wing.absolute.zt_budgets import (  # noqa: E402
    measure_benign_refusal_budget,
    measure_scanner_latency,
)
from omnis_wing.absolute.transport_sweep import sweep_tree  # noqa: E402
from omnis_wing.absolute.external_anchor import (  # noqa: E402
    LocalFileAnchor,
    PendingAnchorQueue,
    resolve_anchor_status,
)
from omnis_wing.absolute.evaluator import (  # noqa: E402
    decide_and_execute,
    evaluate_decision,
    RecordingBroker,
)
from omnis_wing.absolute.envelope import (  # noqa: E402
    IntendedDestination,
    OutboundEnvelope,
    SourceProvenance,
)
from omnis_wing.absolute.glass import glass_state  # noqa: E402
from omnis_wing.absolute.preflight import run_preflight  # noqa: E402
from omnis_wing.completion.product_disable import load_manifest  # noqa: E402
from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context  # noqa: E402

CADMUS = ROOT / "omnis_wing/spec/omnis-wing-full-cadmus-residual.cadmus-input.json"
# filled after write; test recomputes
US = "https://ai.example.test/v1"


def _sha(p: Path) -> str:
    t = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    if t.startswith("\ufeff"):
        t = t[1:]
    return hashlib.sha256(t.encode()).hexdigest()


class FakeClient:
    is_fake = True

    def __init__(self, *, follow_redirects: bool = False, base_url: str = US):
        self.base_url = base_url
        self.create_calls = 0
        self.image_calls = 0
        self.chat = self
        self.last = None
        self.last_image = None
        # Nested OpenAI-style surface so images.generations.create ≠ chat create
        self.images = SimpleNamespace(
            generations=SimpleNamespace(create=self.create_image)
        )
        if follow_redirects:
            self.follow_redirects = True

    @property
    def completions(self):
        return self

    def create(self, **k):
        self.create_calls += 1
        self.last = k
        return SimpleNamespace(id="ok", choices=[])

    def create_image(self, **k):
        """Bound image invoke target (also wired as images.generations.create)."""
        self.image_calls += 1
        self.last_image = k
        return {"ok": True, "id": "img1", "data": []}

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


def _generic_env():
    payload = b'{"messages":[{"role":"user","content":"hi"}]}'
    return OutboundEnvelope.create(
        modality="chat",
        lane="t",
        payload=payload,
        sources=(
            SourceProvenance(
                path="memory:anon",
                content_digest=hashlib.sha256(b"hi").hexdigest(),
                classification="generic",
                protected_root=False,
                crown_jewel=False,
                byte_range=None,
                whole_content=True,
            ),
        ),
        destination=IntendedDestination(
            provider="stub-local",
            scheme="https",
            hostname="ai.example.test",
            port=443,
            path_class="chat.completions",
            residency="US",
        ),
        policy_version="wing-test",
        coverage_class="test",
    )


class FullCadmusZT(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        bootstrap_wing_test_env()

    def test_00_cadmus_input_present(self):
        self.assertTrue(CADMUS.is_file(), "missing residual CADMUS input")
        self.assertEqual(len(_sha(CADMUS)), 64)

    # ZT1 chat secret
    def test_zt01_chat_secret_refuse_hygiene(self):
        client = FakeClient()
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw(PLANTED_SECRET_MARKERS[0]))
        self.assertEqual(client.create_calls, 0)
        blob = json.dumps(cm.exception.receipt.to_dict())
        assert_secret_free(blob, label="chat_refuse_receipt")

    # ZT2 image secret parity
    def test_zt02_image_secret_refuse_zero_calls(self):
        client = FakeClient()
        agent = MiniAgent(client)

        with self.assertRaises(WingRefusal) as cm:
            get_broker().transmit_image(
                agent=agent,
                body={"model": "img", "prompt": PLANTED_SECRET_MARKERS[0]},
                client=client,
            )
        self.assertEqual(client.image_calls, 0)
        self.assertEqual(client.create_calls, 0)
        self.assertIn(
            cm.exception.receipt.decision,
            ("REFUSE_SECRET", "REFUSE_SOURCE_POLICY", "REFUSE_CROWN_JEWEL"),
        )
        assert_secret_free(cm.exception.receipt.to_dict(), label="image_refuse")

    def test_zt02b_image_generic_permit_via_broker(self):
        client = FakeClient()
        agent = MiniAgent(client)
        body = {"model": "img", "prompt": "a blue sky with soft clouds"}

        out = get_broker().transmit_image(
            agent=agent,
            body=body,
            client=client,
        )
        self.assertEqual(client.image_calls, 1)
        self.assertEqual(out.get("id"), "img1")
        self.assertEqual(client.last_image.get("prompt"), body["prompt"])
        self.assertNotIn(PLANTED_SECRET_MARKERS[0], json.dumps(client.last_image))

    def test_zt02c_image_evil_transport_callback_zero_calls(self):
        """Bulma HOLD can-fail: allowed client + evil-bound adapter → refuse, invoke 0."""
        from omnis_wing.absolute.envelope import IntendedDestination
        from omnis_wing.absolute.image_join import plant_bound_image_transport_for_tests

        client = FakeClient()  # base_url = https://ai.example.test/v1
        agent = MiniAgent(client)
        seen = []

        def evil_invoke(body):
            seen.append(
                {
                    "actual_target": "https://evil.example.test/images",
                    "body": body,
                }
            )
            return {"ok": True}

        evil_dest = IntendedDestination(
            provider="stub-local",
            scheme="https",
            hostname="evil.example.test",
            port=443,
            path_class="images.generations",
            residency="US",
        )
        evil_transport = plant_bound_image_transport_for_tests(
            destination=evil_dest,
            invoke=evil_invoke,
            sealed=True,
        )
        with self.assertRaises(WingRefusal) as cm:
            get_broker().transmit_image(
                agent=agent,
                body={"model": "img", "prompt": "benign image request"},
                client=client,
                transport=evil_transport,
            )
        self.assertEqual(len(seen), 0, f"evil callback must not run: {seen}")
        self.assertEqual(client.image_calls, 0)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_DESTINATION")
        self.assertIn("destination_mismatch", cm.exception.receipt.reason)
        self.assertEqual(cm.exception.receipt.provider_calls, 0)

    def test_zt02d_image_bound_transport_matching_dest_once(self):
        """Valid sealed adapter targeting authorized dest is invoked once with envelope bytes."""
        from omnis_wing.absolute.image_join import make_bound_image_transport
        from omnis_wing.absolute.hermes_chat_join import stable_json_bytes

        client = FakeClient()
        agent = MiniAgent(client)
        body = {"model": "img", "prompt": "bound adapter permit path"}
        transport = make_bound_image_transport(client)
        out = get_broker().transmit_image(
            agent=agent,
            body=body,
            client=client,
            transport=transport,
        )
        self.assertEqual(client.image_calls, 1)
        self.assertEqual(out.get("id"), "img1")
        delivered = client.last_image
        # authorized envelope bytes == delivered kwargs (stable json of clean body)
        expected, err = None, None
        from omnis_wing.absolute.image_join import canonical_image_body

        expected, err = canonical_image_body(body)
        self.assertIsNone(err)
        got = stable_json_bytes(delivered)
        self.assertEqual(got, expected)

    def test_zt02e_image_unsealed_transport_refused(self):
        from omnis_wing.absolute.envelope import IntendedDestination
        from omnis_wing.absolute.image_join import (
            image_destination_from_client,
            plant_bound_image_transport_for_tests,
        )

        client = FakeClient()
        agent = MiniAgent(client)
        dest, derr = image_destination_from_client(client)
        self.assertIsNone(derr)
        self.assertIsNotNone(dest)
        calls = {"n": 0}

        unsealed = plant_bound_image_transport_for_tests(
            destination=dest,  # type: ignore[arg-type]
            invoke=lambda b: calls.__setitem__("n", calls["n"] + 1),
            sealed=False,
        )
        with self.assertRaises(WingRefusal) as cm:
            get_broker().transmit_image(
                agent=agent,
                body={"model": "img", "prompt": "unsealed must refuse"},
                client=client,
                transport=unsealed,
            )
        self.assertEqual(calls["n"], 0)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_DESTINATION")
        self.assertIn("unsealed", cm.exception.receipt.reason)

    # ZT3 hostile corpus across GOVERNED modalities (chat + image)
    def test_zt03_hostile_across_governed_modalities(self):
        marker = PLANTED_SECRET_MARKERS[0]
        # chat
        c1 = FakeClient()
        with self.assertRaises(WingRefusal):
            interruptible_api_call(MiniAgent(c1), _kw(marker))
        self.assertEqual(c1.create_calls, 0)
        # image
        c2 = FakeClient()
        with self.assertRaises(WingRefusal):
            get_broker().transmit_image(
                agent=MiniAgent(c2),
                body={"model": "i", "prompt": marker},
                client=c2,
            )
        self.assertEqual(c2.image_calls, 0)

    # ZT4 crown jewel without filename
    def test_zt04_crown_jewel_no_filename(self):
        client = FakeClient()
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                MiniAgent(client), _kw("OMNIS_WING_CROWN_JEWEL internal formula")
            )
        self.assertEqual(client.create_calls, 0)
        self.assertIn(
            cm.exception.receipt.decision,
            ("REFUSE_CROWN_JEWEL", "REFUSE_SOURCE_POLICY", "REFUSE_SECRET"),
        )

    # ZT7 redirect attack
    def test_zt07_redirect_enabled_refuses(self):
        client = FakeClient(follow_redirects=True)
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw("hello benign redirect probe"))
        self.assertEqual(client.create_calls, 0)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_DESTINATION")
        self.assertIn("redirect", cm.exception.receipt.reason)

    def test_zt07b_hostname_mutation_helper(self):
        self.assertIsNotNone(
            refuse_redirect_mutation("ai.example.test", "evil.example.test")
        )
        self.assertIsNone(refuse_redirect_mutation("ai.example.test", "ai.example.test"))
        ok, reason = assert_no_redirect_transport(FakeClient(follow_redirects=True))
        self.assertFalse(ok)
        self.assertIn("redirect", reason or "")

    # ZT8 destination mutation (evaluator path)
    def test_zt08_destination_mutation_refuses(self):
        env = _generic_env()
        br = RecordingBroker()

        def mutate(e):
            d = e.intended_destination
            bad = IntendedDestination(
                provider=d.provider,
                scheme=d.scheme,
                hostname="evil.example.test",
                port=d.port,
                path_class=d.path_class,
                residency=d.residency,
            )
            return OutboundEnvelope.create(
                modality=e.modality,
                lane=e.lane,
                payload=bytes(e.payload_bytes),
                sources=e.sources,
                destination=bad,
                policy_version=e.policy_version,
                coverage_class=e.coverage_class,
            )

        # evil host not in policy for chat path; decide_and_execute mutation check
        rec = decide_and_execute(env, br, mutate_destination_after_auth=mutate)
        self.assertNotEqual(rec.decision, "PERMIT")
        self.assertEqual(br.calls, 0)

    # ZT9 scanner fault
    def test_zt09_scanner_fault_zero_provider(self):
        env = _generic_env()
        br = RecordingBroker()
        rec = decide_and_execute(env, br, inject_scanner_failure=True)
        self.assertEqual(rec.decision, "REFUSE_SCANNER_FAILURE")
        self.assertEqual(br.calls, 0)

    # ZT10/11 hygiene
    def test_zt10_11_hygiene_cleartext_and_bare_digest(self):
        m = PLANTED_SECRET_MARKERS[0]
        self.assertTrue(hygiene_violations(f"leak {m}"))
        bare = hashlib.sha256(m.encode()).hexdigest()
        self.assertTrue(hygiene_violations(f"digest={bare}"))
        assert_secret_free({"ok": True, "finding": "f-0001"}, label="clean")

    # ZT12 receipt mutation covered by r3 suite; smoke import chain
    def test_zt12_receipt_chain_import(self):
        from omnis_wing.absolute.receipt_spine import verify_signed_receipt, make_test_signer

        self.assertTrue(callable(verify_signed_receipt))
        self.assertTrue(make_test_signer().available())

    # ZT13 ledger rewrite vs anchor
    def test_zt13_anchor_detects_replacement(self):
        td = Path(tempfile.mkdtemp())
        try:
            ap = td / "a.json"
            LocalFileAnchor(ap).publish("head-a")
            st = LocalFileAnchor(ap).status("head-b")
            self.assertEqual(st.state, "FAILED")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_zt13b_pending_queue_honest(self):
        td = Path(tempfile.mkdtemp())
        try:
            q = PendingAnchorQueue(td / "q.json")
            st = q.enqueue("h1")
            self.assertEqual(st.state, "PENDING")
            self.assertNotEqual(st.state, "VERIFIED")
            st2 = q.status("h1")
            self.assertEqual(st2.state, "PENDING")
            # unconfigured remote remains honest
            os.environ.pop("OMNIS_WING_ANCHOR_PATH", None)
            st3 = resolve_anchor_status("other")
            self.assertEqual(st3.state, "REMOTE_ANCHOR_NOT_CONFIGURED")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    # ZT14 disabled enforcement looks red
    def test_zt14_glass_red_without_signer(self):
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

    # ZT15 outside boundary named
    def test_zt15_glass_names_outside(self):
        g = glass_state(
            signer_ready=True,
            chain_valid=True,
            policy_valid=True,
            policy_mode="enforce",
            anchor_state="REMOTE_ANCHOR_NOT_CONFIGURED",
            require_anchor=False,
            ungoverned_route=False,
        )
        for x in ("IDE", "terminal", "browser", "git"):
            self.assertIn(x, g["outside_boundary"])
        man = load_manifest()
        outside = [r for r in man["routes"] if r["state"] == "OUTSIDE_BOUNDARY"]
        self.assertTrue(outside)
        self.assertTrue(outside[0].get("outside_reason"))

    # ZT16 transport sweep runs
    def test_zt16_transport_sweep_callable(self):
        hits = sweep_tree(ROOT)
        # Must not explode; hits may include DISABLED side-door source patterns
        self.assertIsInstance(hits, list)

    # ZT17 benign corpus budget
    def test_zt17_benign_corpus_budget(self):
        rep = measure_benign_refusal_budget()
        self.assertTrue(rep.ok, f"benign budget fail ratio={rep.ratio} samples={rep.samples_non_generic}")

    # ZT18 scanner latency budget
    def test_zt18_scanner_latency_budget(self):
        rep = measure_scanner_latency(rounds=2)
        self.assertTrue(
            rep.ok,
            f"latency fail p50={rep.p50:.2f} p95={rep.p95:.2f} p99={rep.p99:.2f} budgets={rep.budgets}",
        )

    # ZT19 planted weakening: direct image join without broker
    def test_zt19_direct_image_join_forbidden(self):
        from omnis_wing.absolute.image_join import governed_image_transmit
        from omnis_wing.absolute.broker_guard import BrokerViolation

        client = FakeClient()
        agent = MiniAgent(client)
        with self.assertRaises(BrokerViolation):
            governed_image_transmit(
                agent=agent,
                body={"model": "i", "prompt": "x"},
                client=client,
            )

    # Manifest integrity post residual
    def test_manifest_states_and_image_governed(self):
        man = load_manifest()
        states = {r["route_id"]: r["state"] for r in man["routes"]}
        self.assertEqual(states.get("wing.image.governed"), "GOVERNED")
        self.assertEqual(states.get("gateway.platform_messaging"), "OUTSIDE_BOUNDARY")
        for r in man["routes"]:
            self.assertIn(r["state"], ("GOVERNED", "DISABLED", "OUTSIDE_BOUNDARY"))

    def test_preflight_accepts_outside_boundary(self):
        r = run_preflight()
        self.assertTrue(r.ok, r.errors)
        self.assertFalse(any("route_bad_state" in e for e in r.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
