"""Cold tests: WING primary chat → fake CADUCEUS via real_work.runtime."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from omnis_wing.absolute.envelope import SourceProvenance  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import (  # noqa: E402
    EvidenceSession,
    WingEgressContext,
    WingRefusal,
)
from omnis_wing.absolute.real_work.admission import (  # noqa: E402
    admission_manifest,
    assert_contract_not_drifted,
)
from omnis_wing.absolute.real_work.caduceus_client import (  # noqa: E402
    CaduceusBoundaryError,
    CaduceusOutcomeUnknown,
    CaduceusRealWorkClient,
    HttpResult,
    SERVICE_AUTH_CONTEXT,
)
from omnis_wing.absolute.real_work.config import (  # noqa: E402
    PINNED_CADUCEUS_COMMIT,
    parse_real_work_config,
)
from omnis_wing.absolute.real_work.contract import ROUTE_TABLE, assert_route_honest  # noqa: E402
from omnis_wing.absolute.real_work.runtime import (  # noqa: E402
    real_work_required,
    transmit_primary_chat,
)
from omnis_wing.absolute.receipt_spine import EvidenceLedger, make_test_signer  # noqa: E402
from omnis_wing.absolute.transport_broker import TransportBroker, reset_broker_for_tests  # noqa: E402
from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


TOKEN = _b64url(os.urandom(32))


def _cfg():
    return parse_real_work_config(
        {
            "policy_id": "TERMINUS_REAL_WORK_V1",
            "caduceus_base": "http://127.0.0.1:18787",
            "caduceus_instance_id": "test-instance",
            "caduceus_root": str(Path("/Users/sokpyeon/projects/caduceus")),
            "caduceus_commit": PINNED_CADUCEUS_COMMIT,
            "service_token_env": "TEST_CADUCEUS_TOKEN",
            "timeout_seconds": 30,
            "target": {
                "provider": "minimax",
                "scheme": "https",
                "hostname": "api.minimax.io",
                "port": 443,
                "path": "/v1/chat/completions",
                "model": "MiniMax-M2",
                "residency": "CN",
                "api_shape": "openai_chat_completions",
                "lane": "codegen",
            },
        },
        source="test",
    )


class FakeCaduceusHttp:
    def __init__(self):
        self.challenges: set[str] = set()
        self.contexts: dict[str, dict] = {}
        self.chat_bodies: list[bytes] = []
        self.provider_bodies: list[bytes] = []
        self.mode = "TRANSFORMED"
        self.chain_count = 0
        self.planted_seen: list[str] = []
        self.transform_enabled = True
        self.scanner_failure = False
        self.response_marker = False
        self.extra_chain_rows = 0
        self.redirect_chat = False

    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> HttpResult:
        if method == "GET" and url.endswith("/health"):
            return HttpResult(
                200,
                {"content-type": "application/json"},
                json.dumps(
                    {
                        "ok": True,
                        "terminus": True,
                        "service_auth": "required",
                        "instance_id": "test-instance",
                        "chain": {"ok": True, "count": self.chain_count, "head": "a" * 64},
                    }
                ).encode(),
            )
        if method == "GET" and "/auth/challenge" in url:
            nonce = url.split("nonce=", 1)[1]
            if nonce in self.challenges:
                return HttpResult(409, {}, b'{"error":"replay"}')
            self.challenges.add(nonce)
            msg = f"{SERVICE_AUTH_CONTEXT}\ntest-instance\n{nonce}".encode()
            proof = _b64url(hmac.new(TOKEN.encode(), msg, hashlib.sha256).digest())
            return HttpResult(
                200,
                {},
                json.dumps(
                    {
                        "instance_id": "test-instance",
                        "nonce": nonce,
                        "algorithm": "hmac-sha256",
                        "proof": proof,
                    }
                ).encode(),
            )
        if method == "POST" and url.endswith("/v1/omnis/context"):
            assert body is not None
            reg = json.loads(body.decode())
            for f in reg.get("fragments") or []:
                if "text" in f or "content" in f:
                    return HttpResult(400, {}, b'{"error":"raw"}')
            h = "lctx_" + hashlib.sha256(body).hexdigest()[:20]
            dig = hashlib.sha256(body).hexdigest()
            self.contexts[h] = {"digest": dig, "used": False, "registration": reg}
            return HttpResult(
                200,
                {},
                json.dumps({"handle": h, "manifest_digest": dig}).encode(),
            )
        if method == "POST" and url.endswith("/v1/omnis/chat"):
            assert body is not None
            if self.redirect_chat:
                return HttpResult(307, {"location": "https://evil.example/v1/chat"}, b'{"error":{}}')
            self.chat_bodies.append(body)
            if headers.get("x-caduceus-body-sha256") != hashlib.sha256(body).hexdigest():
                return HttpResult(403, {}, b'{"error":{"type":"body_digest_mismatch"}}')
            text = body.decode("utf-8", errors="replace")
            for plant in ("PROJECT-BLUEBIRD-CODENAME", "sk-abcdefghijklmnopqrstuvwxyz012345"):
                if plant in text:
                    self.planted_seen.append(plant)
            obj = json.loads(body)
            h = obj.get("context_handle")
            if not h or h not in self.contexts:
                return HttpResult(
                    403,
                    {},
                    json.dumps(
                        {
                            "error": {
                                "type": "caduceus_refusal",
                                "message": "context unresolved",
                                "delivery_mode": "LOCAL_ONLY",
                            }
                        }
                    ).encode(),
                )
            ctx = self.contexts[h]
            if ctx["used"]:
                return HttpResult(403, {}, b'{"error":{"message":"replay","delivery_mode":"LOCAL_ONLY"}}')
            if obj.get("context_manifest_digest") != ctx["digest"]:
                return HttpResult(403, {}, b'{"error":{"message":"digest","delivery_mode":"LOCAL_ONLY"}}')
            ctx["used"] = True
            if self.scanner_failure:
                return HttpResult(
                    403,
                    {"x-caduceus-delivery-mode": "LOCAL_ONLY"},
                    b'{"error":{"type":"pre_write_scanner_failure"}}',
                )

            if self.mode == "LOCAL_ONLY":
                return HttpResult(
                    403,
                    {"x-caduceus-delivery-mode": "LOCAL_ONLY"},
                    b'{"error":{"type":"caduceus_refusal"}}',
                )

            fragments = ctx["registration"].get("fragments") or []
            protected = any(
                f.get("classification") in ("project", "confidential", "crown_jewel", "credential", "unknown")
                for f in fragments
                if isinstance(f, dict)
            )
            provider_obj = {"messages": obj.get("messages") or []}
            if protected and self.transform_enabled:
                provider_obj = {
                    "messages": [
                        {
                            "role": "user",
                            "content": "[TERM_SOURCE_ABSTRACT] assist_with_structure_only_no_raw_source",
                        }
                    ]
                }
                self.mode = "TRANSFORMED"
            elif not protected:
                self.mode = "RAW"
            provider_wire = json.dumps(provider_obj, separators=(",", ":")).encode()
            self.provider_bodies.append(provider_wire)
            self.chain_count += 2 + self.extra_chain_rows
            headers = {
                "x-caduceus-delivery-mode": self.mode,
                "x-caduceus-terminal": f"{self.mode}_COMPLETED",
                "x-caduceus-receipt": "r" * 64,
            }
            return HttpResult(
                200,
                headers,
                json.dumps(
                    {
                        "id": "x",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": (
                                        "PROJECT-BLUEBIRD-CODENAME"
                                        if self.response_marker
                                        else "useful minimax-like answer"
                                    ),
                                }
                            }
                        ],
                    }
                ).encode(),
            ) if not self.response_marker else HttpResult(
                403,
                {
                    "x-caduceus-delivery-mode": self.mode,
                    "x-caduceus-terminal": f"{self.mode}_COMPLETED",
                    "x-caduceus-receipt": "r" * 64,
                },
                b'{"error":{"type":"caduceus_response_gate"}}',
            )
        return HttpResult(404, {}, b"{}")


class RealPathAgent:
    """Small host fixture that executes Hermes's actual interruptible seam."""

    api_mode = "chat_completions"
    provider = "minimax"
    base_url = "https://api.minimax.io"
    profile_name = "wing-real-work-test"

    def __init__(self, client, ctx):
        self._wing_caduceus_client = client
        self.wing_egress_context = ctx
        self._interrupt_requested = False
        self.direct_client_constructions = 0

    def _create_request_openai_client(self, **kwargs):
        self.direct_client_constructions += 1
        raise AssertionError("direct provider client must be unreachable")

    def _abort_request_openai_client(self, client, reason):
        return None

    def _close_request_openai_client(self, client, reason):
        return None

    def _compute_non_stream_stale_timeout(self, api_kwargs):
        return 30.0

    def _touch_activity(self, message=""):
        return None

    def _buffer_status(self, message=""):
        return None


class WingCaduceusRealWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        bootstrap_wing_test_env()
        os.environ["TEST_CADUCEUS_TOKEN"] = TOKEN
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        os.environ["OMNIS_WING_REAL_WORK_CONFIG"] = "/dev/null"  # trigger real_work_required
        # real_work_required uses config path or production mode; set config path to a temp file
        reset_broker_for_tests()
        self.fake = FakeCaduceusHttp()
        self.cfg = _cfg()
        self.client = CaduceusRealWorkClient(self.cfg, token=TOKEN, http_request=self.fake)
        ledger_path = Path(os.environ.get("TMPDIR", "/tmp")) / f"wing-rw-ledger-{os.getpid()}.jsonl"
        if ledger_path.exists():
            ledger_path.unlink()
        self.evidence = EvidenceSession(
            signer=make_test_signer(),
            ledger=EvidenceLedger(ledger_path),
        )
        self.sources = (
            SourceProvenance(
                path="payload:msg",
                content_digest="b" * 64,
                classification="project",
                protected_root=True,
                crown_jewel=False,
                byte_range=None,
                whole_content=True,
            ),
        )
        self.ctx = WingEgressContext(sources=self.sources, evidence=self.evidence)
        self.agent = type(
            "Agent",
            (),
            {"_wing_caduceus_client": self.client, "profile_name": "test"},
        )()

    def tearDown(self) -> None:
        os.environ.pop("OMNIS_WING_REAL_WORK_CONFIG", None)

    def test_admission_and_routes(self) -> None:
        assert_contract_not_drifted()
        m = admission_manifest()
        self.assertEqual(m["policy_id"], "TERMINUS_REAL_WORK_V1")
        assert_route_honest("wing.chat_join", "GOVERNED")
        self.assertEqual(ROUTE_TABLE["wing.image_join"], "DISABLED")
        self.assertEqual(ROUTE_TABLE["wing.chat_join_direct_provider"], "DISABLED")

    def test_client_transformed_happy_path(self) -> None:
        self.fake.mode = "TRANSFORMED"
        marker = "PROJECT-BLUEBIRD-CODENAME"
        result = self.client.call(
            messages=[{"role": "user", "content": f"abstract this protected project work {marker}"}],
            sources=self.sources,
            workspace_identity="/tmp/chamber-test-workspace",
        )
        self.assertEqual(result.delivery_mode, "TRANSFORMED")
        self.assertEqual(result.provider_calls, 1)
        # Raw WING→local-CADUCEUS contains the source; the simulated external
        # provider receives only CADUCEUS's structural abstraction.
        self.assertIn(marker, self.fake.chat_bodies[0].decode())
        self.assertNotIn(marker, self.fake.provider_bodies[0].decode())
        self.assertIn("TERM_SOURCE_ABSTRACT", self.fake.provider_bodies[0].decode())
        self.assertEqual(len(self.fake.provider_bodies), 1)
        self.assertEqual(len(self.fake.chat_bodies), 1)

    def test_transform_control_is_load_bearing(self) -> None:
        marker = "PROJECT-BLUEBIRD-CODENAME"
        self.fake.transform_enabled = False
        result = self.client.call(
            messages=[{"role": "user", "content": marker}],
            sources=self.sources,
            workspace_identity="ws",
        )
        self.assertEqual(result.provider_calls, 1)
        self.assertIn(marker, self.fake.provider_bodies[0].decode())

    def test_generic_raw_control_is_byte_equal(self) -> None:
        generic = (
            SourceProvenance(
                path="payload:generic",
                content_digest=hashlib.sha256(b"hello").hexdigest(),
                classification="generic",
                protected_root=False,
                crown_jewel=False,
                byte_range=None,
                whole_content=True,
            ),
        )
        result = self.client.call(
            messages=[{"role": "user", "content": "hello"}],
            sources=generic,
            workspace_identity="ws",
        )
        self.assertEqual(result.delivery_mode, "RAW")
        self.assertEqual(
            json.loads(self.fake.provider_bodies[0]),
            {"messages": [{"role": "user", "content": "hello"}]},
        )

    def test_scanner_failure_and_redirect_are_zero_provider(self) -> None:
        self.fake.scanner_failure = True
        with self.assertRaises(CaduceusBoundaryError) as cm:
            self.client.call(
                messages=[{"role": "user", "content": "protected"}],
                sources=self.sources,
                workspace_identity="ws",
            )
        self.assertEqual(cm.exception.provider_calls, 0)
        self.assertEqual(self.fake.provider_bodies, [])

        other = FakeCaduceusHttp()
        other.redirect_chat = True
        client = CaduceusRealWorkClient(self.cfg, token=TOKEN, http_request=other)
        with self.assertRaises(CaduceusBoundaryError) as cm2:
            client.call(
                messages=[{"role": "user", "content": "protected"}],
                sources=self.sources,
                workspace_identity="ws",
            )
        self.assertEqual(cm2.exception.provider_calls, 0)
        self.assertEqual(other.provider_bodies, [])

    def test_response_gate_and_duplicate_chain_never_deliver_success(self) -> None:
        self.fake.response_marker = True
        with self.assertRaises(CaduceusBoundaryError) as cm:
            self.client.call(
                messages=[{"role": "user", "content": "protected"}],
                sources=self.sources,
                workspace_identity="ws",
            )
        self.assertEqual(cm.exception.provider_calls, 1)

        other = FakeCaduceusHttp()
        other.extra_chain_rows = 1
        client = CaduceusRealWorkClient(self.cfg, token=TOKEN, http_request=other)
        with self.assertRaises(CaduceusOutcomeUnknown):
            client.call(
                messages=[{"role": "user", "content": "protected"}],
                sources=self.sources,
                workspace_identity="ws",
            )

    def test_runtime_transmit_primary_chat(self) -> None:
        # Planted client is only accepted in test signer mode (runtime._client_for)
        self.fake.mode = "TRANSFORMED"
        out = transmit_primary_chat(
            agent=self.agent,
            api_kwargs={
                "messages": [
                    {
                        "role": "user",
                        "content": "Help with project code structure abstractly",
                    }
                ]
            },
            wing_ctx=self.ctx,
        )
        self.assertEqual(out.choices[0].message.content, "useful minimax-like answer")
        st = getattr(self.agent, "wing_real_work_status", {})
        self.assertEqual(st.get("state"), "TRANSFORMED · DELIVERED")

    def test_actual_hermes_host_seam_uses_caduceus_and_no_direct_client(self) -> None:
        agent = RealPathAgent(self.client, self.ctx)
        out = interruptible_api_call(
            agent,
            {
                "model": "ignored-by-local-caduceus-binding",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "OMNIS_WING_PROTECTED_FRAGMENT "
                            "PROJECT-BLUEBIRD-CODENAME help with structure"
                        ),
                    }
                ],
            },
        )
        self.assertEqual(out.choices[0].message.content, "useful minimax-like answer")
        self.assertEqual(agent.direct_client_constructions, 0)
        self.assertEqual(len(self.fake.provider_bodies), 1)
        self.assertNotIn("PROJECT-BLUEBIRD-CODENAME", self.fake.provider_bodies[0].decode())
        self.assertEqual(agent.wing_real_work_status["state"], "TRANSFORMED · DELIVERED")

    def test_broker_uses_runtime_when_real_work_required(self) -> None:
        # Write a minimal config file so real_work_required is true without invalid path
        cfg_path = Path(os.environ.get("TMPDIR", "/tmp")) / f"wing-rw-cfg-{os.getpid()}.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "policy_id": "TERMINUS_REAL_WORK_V1",
                    "caduceus_base": "http://127.0.0.1:18787",
                    "caduceus_instance_id": "test-instance",
                    "caduceus_root": str(Path("/Users/sokpyeon/projects/caduceus")),
                    "caduceus_commit": PINNED_CADUCEUS_COMMIT,
                    "service_token_env": "TEST_CADUCEUS_TOKEN",
                    "timeout_seconds": 30,
                    "target": {
                        "provider": "minimax",
                        "scheme": "https",
                        "hostname": "api.minimax.io",
                        "port": 443,
                        "path": "/v1/chat/completions",
                        "model": "MiniMax-M2",
                        "residency": "CN",
                        "api_shape": "openai_chat_completions",
                        "lane": "codegen",
                    },
                }
            ),
            encoding="utf-8",
        )
        os.environ["OMNIS_WING_REAL_WORK_CONFIG"] = str(cfg_path)
        self.assertTrue(real_work_required())
        self.fake.mode = "TRANSFORMED"
        # Ensure CADUCEUS pin check is skipped via planted client in test mode
        broker = TransportBroker()
        from omnis_wing.absolute.runtime_context import set_wing_agent

        try:
            set_wing_agent(self.agent)
        except Exception:
            # may not exist — pass agent kw if supported
            pass
        try:
            out = broker.transmit_chat_completions(
                client=None,
                api_kwargs={
                    "messages": [{"role": "user", "content": "project abstract help"}]
                },
                wing_ctx=self.ctx,
                agent=self.agent,
            )
            self.assertEqual(out.choices[0].message.content, "useful minimax-like answer")
        finally:
            cfg_path.unlink(missing_ok=True)
            os.environ.pop("OMNIS_WING_REAL_WORK_CONFIG", None)

    def test_local_only_zero_provider(self) -> None:
        self.fake.mode = "LOCAL_ONLY"
        with self.assertRaises(CaduceusBoundaryError) as cm:
            self.client.call(
                messages=[{"role": "user", "content": "x"}],
                sources=self.sources,
                workspace_identity="ws",
            )
        self.assertEqual(cm.exception.provider_calls, 0)

    def test_messages_only_provenance_ok(self) -> None:
        # empty sources: messages themselves are provenance
        self.fake.mode = "TRANSFORMED"
        result = self.client.call(
            messages=[{"role": "user", "content": "generic hello"}],
            sources=(),
            workspace_identity="ws",
        )
        self.assertEqual(result.delivery_mode, "TRANSFORMED")


if __name__ == "__main__":
    unittest.main()
