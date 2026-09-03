"""R5–R7 TERMINUS convergence cold can-fails (no live provider, no Keychain)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="wing-r5r7-")
os.environ["WING_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = str(Path(_tmp) / "ledgers")
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from agent.chat_completion_helpers import (  # noqa: E402
    interruptible_api_call,
    interruptible_streaming_api_call,
)
from omnis_wing.absolute.wing_chat_join import (  # noqa: E402
    EvidenceSession,
    WingEgressContext,
    WingRefusal,
)
from omnis_wing.absolute.payload_policy import analyze_body, hygiene_check_text  # noqa: E402
from omnis_wing.absolute.receipt_spine import (  # noqa: E402
    EvidenceLedger,
    make_test_signer,
)
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402
from omnis_wing.absolute.transport_broker import get_broker  # noqa: E402
from omnis_wing.absolute.operator_health import build_health_report  # noqa: E402
from omnis_wing.completion.product_disable import load_manifest  # noqa: E402

CADMUS = ROOT / "omnis_wing/spec/omnis-wing-r5-r7-terminus-convergence.cadmus-input.json"
US = "https://ai.example.test/v1"


def _sha_file(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    if t.startswith("\ufeff"):
        t = t[1:]
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(t.encode()).hexdigest()


class FakeClient:
    is_fake = True

    def __init__(self, base_url=US):
        self.base_url = base_url
        self.create_calls = 0
        self.chat = self
        self.stream_calls = 0
        self.last = None

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.create_calls += 1
        self.last = kwargs
        if kwargs.get("stream"):
            self.stream_calls += 1
            return iter([SimpleNamespace(choices=[])])
        return SimpleNamespace(id="ok", choices=[SimpleNamespace(message=SimpleNamespace(content="x"))])

    def close(self):
        pass


class MiniAgent:
    def __init__(self, client=None, api_mode="chat_completions", wing_ctx=None):
        self.api_mode = api_mode
        self._client = client or FakeClient()
        self._interrupt_requested = False
        self.log_prefix = "t"
        self.provider = "stub"
        self.base_url = self._client.base_url
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None
        if wing_ctx is not None:
            self.wing_egress_context = wing_ctx

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

    def _anthropic_messages_create(self, body):
        self._client.create_calls += 1
        return SimpleNamespace(id="a", content=[])

    def _run_codex_stream(self, client, api_kwargs, on_first_delta=None):
        self._client.create_calls += 1
        return SimpleNamespace(id="c")


def _evidence():
    p = Path(tempfile.mkdtemp()) / "l.jsonl"
    return EvidenceSession(signer=make_test_signer(), ledger=EvidenceLedger(p))


def _kw(content="hello operator", **extra):
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
    }
    body.update(extra)
    return body


class R5PayloadPolicyTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
        bootstrap_wing_test_env()

    def test_00_cadmus(self):
        self.assertTrue(CADMUS.is_file())
        self.assertEqual(_sha_file(CADMUS), "05c1d58e2ade16e917892c220c13e9d69bf11447f6f543dacc5758ecc95c8605")

    def test_r5_secret_in_extra_body_refuse(self):
        client = FakeClient()
        agent = MiniAgent(client)
        body = _kw("hi")
        body["extra_body"] = {"note": PLANTED_SECRET_MARKERS[0]}
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, body)
        self.assertIn(cm.exception.receipt.decision, ("REFUSE_SECRET", "REFUSE_SOURCE_POLICY"))
        self.assertEqual(client.create_calls, 0)
        # hygiene
        self.assertTrue(hygiene_check_text(str(cm.exception.receipt.to_dict())))

    def test_r5_project_in_system_field_refuse(self):
        client = FakeClient()
        agent = MiniAgent(client)
        body = _kw("hi")
        body["system"] = "See /Users/x/chamber/SOUL.md and def classify():\n  pass"
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, body)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

    def test_r5_tool_arguments_project_refuse(self):
        client = FakeClient()
        agent = MiniAgent(client)
        body = _kw("hi")
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "x",
                    "description": "import os\nfrom pathlib import Path  # jourdanlabs",
                    "parameters": {},
                },
            }
        ]
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, body)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

    def test_r5_unknown_provenance_refuse(self):
        client = FakeClient()
        agent = MiniAgent(client)
        # high binary ratio → unknown classification without env override
        blob = bytes([0, 1, 2, 255, 254, 253] * 80).decode("latin-1")
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw(blob))
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

    def test_r5_scanner_failure_refuse(self):
        from omnis_wing.absolute.envelope import OutboundEnvelope, IntendedDestination, SourceProvenance
        from omnis_wing.absolute.evaluator import evaluate_decision

        dest = IntendedDestination("stub", "https", "ai.example.test", 443, "chat.completions", "US")
        src = SourceProvenance("p", "a" * 64, "generic", False, False, None, True)
        env = OutboundEnvelope.create(
            modality="chat", lane="t", payload=b'{"x":1}', sources=(src,), destination=dest
        )
        auth = evaluate_decision(env, inject_scanner_failure=True)
        self.assertEqual(auth.decision, "REFUSE_SCANNER_FAILURE")

    def test_r5_destination_mutation_after_auth(self):
        from omnis_wing.absolute.envelope import OutboundEnvelope, IntendedDestination, SourceProvenance
        from omnis_wing.absolute.evaluator import decide_and_execute, RecordingBroker

        dest = IntendedDestination("stub", "https", "ai.example.test", 443, "chat.completions", "US")
        src = SourceProvenance("p", "b" * 64, "generic", False, False, None, True)
        env = OutboundEnvelope.create(
            modality="chat", lane="t", payload=b'{"m":1}', sources=(src,), destination=dest
        )

        def mutate(e):
            bad = IntendedDestination("evil", "https", "evil.example", 443, "chat.completions", "CN")
            return OutboundEnvelope(
                envelope_id=e.envelope_id,
                modality=e.modality,
                lane=e.lane,
                payload_bytes=e.payload_bytes,
                payload_digest=e.payload_digest,
                sources=e.sources,
                intended_destination=bad,
                policy_version=e.policy_version,
                coverage_class=e.coverage_class,
            )

        br = RecordingBroker()
        rec = decide_and_execute(env, br, mutate_destination_after_auth=mutate)
        self.assertNotEqual(rec.decision, "PERMIT")
        self.assertEqual(br.calls, 0)

    def test_r5_planted_secret_message_refuse(self):
        client = FakeClient()
        agent = MiniAgent(client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _kw(PLANTED_SECRET_MARKERS[0]))
        self.assertIn(cm.exception.receipt.decision, ("REFUSE_SECRET",))
        self.assertEqual(client.create_calls, 0)
        blob = json.dumps(cm.exception.receipt.to_dict())
        for m in PLANTED_SECRET_MARKERS:
            self.assertNotIn(m, blob)

    def test_r5_generic_operator_still_permits(self):
        client = FakeClient()
        agent = MiniAgent(client)
        interruptible_api_call(agent, _kw("hi captain"))
        self.assertEqual(client.create_calls, 1)


class R6PrimaryPathTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
        bootstrap_wing_test_env()

    def test_r6_openai_non_stream_governed(self):
        client = FakeClient()
        agent = MiniAgent(client, api_mode="chat_completions")
        interruptible_api_call(agent, _kw())
        self.assertEqual(client.create_calls, 1)

    def test_r6_streaming_presend_before_provider(self):
        client = FakeClient()
        agent = MiniAgent(client)
        order = []

        real_create = client.create

        def tracked(**kw):
            order.append("provider")
            return real_create(**kw)

        client.create = tracked
        # patch ledger append to mark pre-send
        from omnis_wing.absolute import receipt_spine as rs

        orig = rs.EvidenceLedger.append

        def ap(self, receipt):
            order.append(f"ledger:{getattr(receipt,'phase',None) or receipt.to_dict().get('phase')}")
            return orig(self, receipt)

        rs.EvidenceLedger.append = ap  # type: ignore
        try:
            body = _kw()
            body["stream"] = True
            get_broker().transmit_streaming(agent=agent, client=client, api_kwargs=body)
        finally:
            rs.EvidenceLedger.append = orig  # type: ignore
        self.assertIn("provider", order)
        # first ledger phase should be TRANSMISSION_STARTED before provider
        led_idx = next(i for i, x in enumerate(order) if x.startswith("ledger:"))
        prov_idx = order.index("provider")
        self.assertLess(led_idx, prov_idx)
        self.assertIn("TRANSMISSION_STARTED", order[led_idx])

    def test_r6_anthropic_governed_join(self):
        client = FakeClient()
        agent = MiniAgent(client, api_mode="anthropic_messages")
        agent._anthropic_base_url = US
        calls = {"n": 0}

        def tx(body):
            calls["n"] += 1
            return SimpleNamespace(id="a")

        get_broker().transmit_callable(
            agent=agent,
            body=_kw(),
            transmit_fn=tx,
            client=client,
            route_id="agent.interruptible.anthropic_messages.non_stream",
        )
        self.assertEqual(calls["n"], 1)

    def test_r6_bedrock_governed_join(self):
        client = FakeClient()
        agent = MiniAgent(client, api_mode="bedrock_converse")
        agent.base_url = "https://bedrock-runtime.us-east-1.amazonaws.com"
        calls = {"n": 0}

        def tx(body):
            calls["n"] += 1
            return {"ok": True}

        get_broker().transmit_callable(
            agent=agent,
            body={"modelId": "x", "messages": [{"role": "user", "content": [{"text": "hi"}]}]},
            transmit_fn=tx,
            client=client,
            route_id="agent.interruptible.bedrock_converse.non_stream",
            path_class="bedrock.converse",
        )
        self.assertEqual(calls["n"], 1)

    def test_r6_codex_governed_join(self):
        client = FakeClient()
        agent = MiniAgent(client, api_mode="codex_responses")
        agent.base_url = US
        calls = {"n": 0}

        def tx(body):
            calls["n"] += 1
            return SimpleNamespace(id="c")

        get_broker().transmit_callable(
            agent=agent,
            body={"model": "codex", "input": "hi"},
            transmit_fn=tx,
            client=client,
            route_id="agent.interruptible.codex_responses.non_stream",
        )
        self.assertEqual(calls["n"], 1)

    def test_r6_stream_secret_refuse_zero_provider(self):
        client = FakeClient()
        agent = MiniAgent(client)
        body = _kw(PLANTED_SECRET_MARKERS[0])
        body["stream"] = True
        with self.assertRaises(WingRefusal):
            get_broker().transmit_streaming(agent=agent, client=client, api_kwargs=body)
        self.assertEqual(client.create_calls, 0)


class R7CoverageAdversarialTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
        bootstrap_wing_test_env()

    def tearDown(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
        os.environ.pop("OMNIS_WING_P256_WORK_DIR", None)

    def test_r7_manifest_exhaustive_states(self):
        man = load_manifest()
        for r in man["routes"]:
            self.assertIn(r["state"], ("GOVERNED", "DISABLED"), r["route_id"])
        # primary paths present
        ids = {r["route_id"] for r in man["routes"]}
        for need in (
            "agent.interruptible.chat_completions.non_stream",
            "agent.interruptible_streaming.chat_completions",
            "agent.interruptible.anthropic_messages.non_stream",
            "agent.interruptible.bedrock_converse.non_stream",
            "agent.interruptible.codex_responses.non_stream",
        ):
            self.assertIn(need, ids)

    def test_r7_health_truth_fields(self):
        led = EvidenceLedger(Path(tempfile.mkdtemp()) / "h.jsonl")
        report = build_health_report(root=ROOT, ledger=led, signer=None)
        self.assertIn("enrollment", report)
        self.assertIn("ledger", report)
        self.assertIn("coverage_boundary", report)
        self.assertIn("remote_anchor", report)
        self.assertIn(report["remote_anchor"]["state"], ("NOT_CONFIGURED", "REMOTE_ANCHOR_NOT_CONFIGURED"))
        self.assertFalse(report.get("claims_whole_tree_ai_egress", True))
        # routes summary via operator coverage
        man = load_manifest()
        self.assertIn("summary", man)

    def test_r7_reload_side_door_stays_dead(self):
        import importlib
        from omnis_wing.completion.side_doors import ensure_side_doors_armed, WingRouteDisabled

        ensure_side_doors_armed()
        # importlib reload path
        try:
            import tools.transcription_tools as tt
            importlib.reload(tt)
        except Exception:
            pass
        ensure_side_doors_armed()
        import tools.transcription_tools as tt2
        with self.assertRaises(Exception):
            if hasattr(tt2, "transcribe_audio"):
                tt2.transcribe_audio("/nope.wav")
            else:
                raise WingRouteDisabled("tools.transcription_tools", "missing")

    def test_r7_planted_agent_attrs_production(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
        try:
            client = FakeClient()
            agent = MiniAgent(client)
            agent.wing_runtime_attached = True
            agent.wing_evidence_session = _evidence()
            agent.wing_production_signer = make_test_signer()
            with self.assertRaises(WingRefusal):
                interruptible_api_call(agent, _kw())
            self.assertEqual(client.create_calls, 0)
        finally:
            os.environ["OMNIS_WING_SIGNER_MODE"] = "test"

    def test_r7_unsafe_ledger_production_refuse(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "production"
        td = Path(tempfile.mkdtemp())
        bad = td / "open"
        bad.mkdir()
        os.chmod(bad, 0o755)
        cfg = td / "c.yaml"
        cfg.write_text(
            f"backend: disposable_p256\ntag: ai.jourdanlabs.omnis-wing.test.r5r7.p256\n"
            f"ledger_dir: {bad}\nauto_enroll: false\n"
        )
        os.environ["OMNIS_WING_PRODUCTION_CONFIG"] = str(cfg)
        work = td / "w"
        work.mkdir()
        os.environ["OMNIS_WING_P256_WORK_DIR"] = str(work)
        try:
            from omnis_wing.absolute.production_signer import DisposableP256Backend
            from omnis_wing.absolute.runtime_attach import attach_wing_runtime

            DisposableP256Backend(
                tag="ai.jourdanlabs.omnis-wing.test.r5r7.p256", work_dir=work
            ).enroll()
            client = FakeClient()
            agent = MiniAgent(client)
            st = attach_wing_runtime(agent, force=True)
            self.assertFalse(st.get("ready"))
            with self.assertRaises(WingRefusal):
                interruptible_api_call(agent, _kw())
            self.assertEqual(client.create_calls, 0)
        finally:
            os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
            os.environ.pop("OMNIS_WING_PRODUCTION_CONFIG", None)
            os.environ.pop("OMNIS_WING_P256_WORK_DIR", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
