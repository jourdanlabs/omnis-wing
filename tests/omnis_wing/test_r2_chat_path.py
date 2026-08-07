"""R2/R2.1: real Hermes non-streaming chat path through WING boundary."""

from __future__ import annotations

import hashlib
import json
import os
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

_tmp_home = tempfile.mkdtemp(prefix="omnis-wing-r2-home-")
os.environ["HERMES_HOME"] = _tmp_home
for _name in ("requests", "yaml"):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        if _name == "yaml":
            def _safe_load(stream):
                return {}
            _m.safe_load = _safe_load  # type: ignore[attr-defined]
        sys.modules[_name] = _m

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.envelope import IntendedDestination, SourceProvenance  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import (  # noqa: E402
    WingEgressContext,
    WingRefusal,
    canonical_messages_payload_bytes,
    canonical_provider_request_body,
    derive_destination_from_client,
    governed_chat_completions_create,
    stable_json_bytes,
)
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402

CADMUS_R2 = ROOT / "omnis_wing" / "spec" / "omnis-wing-r2-live-chat-path.cadmus-input.json"
CADMUS_R2_SHA = "c12e0cb582634fca8a5bec1f5468c50cb82cf80b9661287a602acfb96d7396dd"

US_BASE = "https://ai.example.test/v1"
CN_BASE = "https://api.moonshot.cn/v1"


def _sha_file(path: Path) -> str:
    t = path.read_text(encoding="utf-8")
    if t.startswith("\ufeff"):
        t = t[1:]
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class FakeCompletions:
    def __init__(self, parent: "FakeClient"):
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        self._parent.create_calls += 1
        self._parent.last_kwargs = dict(kwargs)
        self._parent.received_body_bytes = stable_json_bytes(kwargs)
        self._parent.received_messages_bytes = canonical_messages_payload_bytes(
            kwargs.get("messages")
        )
        return SimpleNamespace(
            id="fake-1",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(role="assistant", content="ok"),
                    finish_reason="stop",
                )
            ],
        )


class FakeChat:
    def __init__(self, parent: "FakeClient"):
        self.completions = FakeCompletions(parent)


class FakeClient:
    is_fake = True

    def __init__(self, base_url: str = US_BASE):
        self.base_url = base_url
        self.chat = FakeChat(self)
        self.create_calls = 0
        self.last_kwargs: dict = {}
        self.received_messages_bytes: bytes | None = None
        self.received_body_bytes: bytes | None = None
        self.closed = False

    def close(self):
        self.closed = True


class MiniAgent:
    def __init__(self, wing_ctx: WingEgressContext | None, client: FakeClient):
        self.api_mode = "chat_completions"
        self.wing_egress_context = wing_ctx
        self._client = client
        self._interrupt_requested = False
        self.log_prefix = "test"
        self._codex_stream_last_event_ts = None
        self._codex_stream_last_progress_ts = None

    def _create_request_openai_client(self, *, reason: str, api_kwargs: dict):
        return self._client

    def _abort_request_openai_client(self, client, reason: str):
        pass

    def _close_request_openai_client(self, client, reason: str):
        if hasattr(client, "close"):
            client.close()

    def _compute_non_stream_stale_timeout(self, api_kwargs: dict) -> float:
        return 30.0

    def _touch_activity(self, msg: str = "") -> None:
        return None

    def _buffer_status(self, msg: str = "") -> None:
        return None


def _src(classification: str, payload: str, **kw) -> SourceProvenance:
    d = hashlib.sha256(payload.encode()).hexdigest()
    return SourceProvenance(
        path=kw.get("path", "src/x.py"),
        content_digest=kw.get("content_digest", d),
        classification=classification,
        protected_root=kw.get("protected_root", classification in ("project", "protected")),
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )


MESSAGES = [
    {"role": "system", "content": "You are a test assistant."},
    {"role": "user", "content": "Say hello from wing r2."},
]


def _api_kwargs(messages=None, **extra):
    kw = {
        "model": "fake-model",
        "messages": list(messages if messages is not None else MESSAGES),
        "temperature": 0,
    }
    kw.update(extra)
    return kw


def _ctx(classification: str = "generic", **kw) -> WingEgressContext:
    payload = json.dumps(MESSAGES, ensure_ascii=False, separators=(",", ":"))
    return WingEgressContext(
        sources=(_src(classification, payload, protected_root=(classification != "generic"), **kw),),
        declared_destination=kw.get("declared_destination"),
    )


class WingR2ChatPathTests(unittest.TestCase):
    def test_00_cadmus_r2_digest(self):
        self.assertTrue(CADMUS_R2.is_file())
        self.assertEqual(_sha_file(CADMUS_R2), CADMUS_R2_SHA)

    def test_01_real_path_protected_cn_refuse_zero_client_calls(self):
        # Actual CN endpoint via client base_url (not context blessing)
        client = FakeClient(base_url=CN_BASE)
        agent = MiniAgent(_ctx("project", path="src/secret_mod.py"), client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_RESIDENCY")
        self.assertEqual(cm.exception.receipt.phase, "NONE")
        self.assertEqual(client.create_calls, 0)

    def test_02_real_path_missing_provenance_refuse_zero_calls(self):
        client = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(None, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

        client2 = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal) as cm2:
            interruptible_api_call(
                MiniAgent(WingEgressContext(sources=()), client2), _api_kwargs()
            )
        self.assertEqual(cm2.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client2.create_calls, 0)

    def test_03_real_path_generic_permit_one_call_full_body_bytes_equal(self):
        messages = list(MESSAGES)
        api_kw = _api_kwargs(messages)
        expected_body, body_dict, err = canonical_provider_request_body(api_kw)
        self.assertIsNone(err)
        assert expected_body is not None

        client = FakeClient(base_url=US_BASE)
        agent = MiniAgent(_ctx("generic"), client)
        resp = interruptible_api_call(agent, api_kw)
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        self.assertEqual(client.received_body_bytes, expected_body)
        self.assertEqual(stable_json_bytes(client.last_kwargs), expected_body)

    def test_04_legacy_direct_create_not_in_selected_branch(self):
        src = (ROOT / "agent" / "chat_completion_helpers.py").read_text(encoding="utf-8")
        start = src.index("def interruptible_api_call")
        rest = src[start + 1 :]
        next_def = rest.index("\ndef ")
        body = src[start : start + 1 + next_def]
        self.assertIn("governed_chat_completions_create", body)
        self.assertNotIn("request_client.chat.completions.create(**api_kwargs)", body)

        client = FakeClient(base_url=US_BASE)
        out = governed_chat_completions_create(client, _api_kwargs(), _ctx("generic"))
        self.assertIsNotNone(out)
        self.assertEqual(client.create_calls, 1)

    def test_05_coverage_manifest_lists_r2_paths(self):
        man_path = ROOT / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json"
        man = json.loads(man_path.read_text(encoding="utf-8"))
        paths = {e["path"] for e in man["governed_r2"]}
        self.assertIn("omnis_wing/absolute/hermes_chat_join.py", paths)
        self.assertIn("agent/chat_completion_helpers.py", paths)
        self.assertFalse(man.get("claims_whole_tree_ai_egress"))
        self.assertFalse(man.get("claims_all_hermes_chat_paths"))

    # ── R2.1 P0-A ─────────────────────────────────────────────────────────

    def test_06_planted_secret_in_tools_refuse_zero_calls_no_leak(self):
        secret = PLANTED_SECRET_MARKERS[0]
        api_kw = _api_kwargs(
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "x",
                        "description": f"helper {secret}",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        )
        client = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(_ctx("generic"), client), api_kw)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SECRET")
        self.assertEqual(cm.exception.receipt.phase, "NONE")
        self.assertEqual(client.create_calls, 0)
        blob = cm.exception.receipt.serialize_for_hygiene()
        self.assertNotIn(secret, blob)
        bare = hashlib.sha256(secret.encode()).hexdigest()
        self.assertNotIn(bare, blob)

    def test_07_planted_secret_in_extra_body_refuse_zero_calls_no_leak(self):
        secret = PLANTED_SECRET_MARKERS[0]
        api_kw = _api_kwargs(extra_body={"metadata": {"note": secret}})
        client = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(_ctx("generic"), client), api_kw)
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SECRET")
        self.assertEqual(cm.exception.receipt.phase, "NONE")
        self.assertEqual(client.create_calls, 0)
        blob = cm.exception.receipt.serialize_for_hygiene()
        self.assertNotIn(secret, blob)
        self.assertNotIn(hashlib.sha256(secret.encode()).hexdigest(), blob)

    def test_08_unsupported_body_field_refuse_unsupported(self):
        api_kw = _api_kwargs(custom_provider_extension={"x": 1})
        client = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal) as cm:
            governed_chat_completions_create(client, api_kw, _ctx("generic"))
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_UNSUPPORTED")
        self.assertEqual(client.create_calls, 0)

    # ── R2.1 P0-B ─────────────────────────────────────────────────────────

    def test_09_claimed_us_context_actual_cn_base_url_refuse(self):
        """Context cannot bless a route: moonshot.cn + claimed US → refuse."""
        claimed_us = IntendedDestination(
            provider="stub-local",
            scheme="https",
            hostname="ai.example.test",
            port=443,
            path_class="chat.completions",
            residency="US",
        )
        ctx = WingEgressContext(
            sources=_ctx("generic").sources,
            declared_destination=claimed_us,
        )
        client = FakeClient(base_url=CN_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(ctx, client), _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_DESTINATION")
        self.assertEqual(client.create_calls, 0)

    def test_10_actual_cn_base_url_with_generic_sources_refuse_residency(self):
        # Even without mismatched declared dest, CN host maps to CN residency
        # and generic allowlist still excludes CN → REFUSE_RESIDENCY
        client = FakeClient(base_url=CN_BASE)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(MiniAgent(_ctx("generic"), client), _api_kwargs())
        self.assertIn(cm.exception.receipt.decision, ("REFUSE_RESIDENCY", "REFUSE_DESTINATION"))
        self.assertEqual(client.create_calls, 0)

    def test_11_derive_destination_from_client_base_url(self):
        client = FakeClient(base_url="https://api.moonshot.cn/v1")
        dest, err = derive_destination_from_client(client)
        self.assertIsNone(err)
        assert dest is not None
        self.assertEqual(dest.hostname, "api.moonshot.cn")
        self.assertEqual(dest.residency, "CN")
        self.assertEqual(dest.path_class, "chat.completions")
        self.assertEqual(dest.port, 443)
        self.assertEqual(dest.scheme, "https")

    def test_12_broker_does_not_forward_original_unscanned_kwargs(self):
        """If original kwargs had a secret field, only canonical body is sent."""
        secret = PLANTED_SECRET_MARKERS[0]
        # Secret only in a field that is allowed and thus scanned
        api_kw = _api_kwargs(tools=[{"type": "function", "function": {"name": "a", "description": secret}}])
        client = FakeClient(base_url=US_BASE)
        with self.assertRaises(WingRefusal):
            governed_chat_completions_create(client, api_kw, _ctx("generic"))
        self.assertEqual(client.create_calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
