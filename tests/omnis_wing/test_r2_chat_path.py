"""R2: real Hermes non-streaming chat path through WING boundary."""

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

# Isolate from live Hermes home / profile before any hermes import.
_tmp_home = tempfile.mkdtemp(prefix="omnis-wing-r2-home-")
os.environ["HERMES_HOME"] = _tmp_home
# Offline stubs for optional host deps pulled by chat_completion_helpers import chain.
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
    governed_chat_completions_create,
)

CADMUS_R2 = ROOT / "omnis_wing" / "spec" / "omnis-wing-r2-live-chat-path.cadmus-input.json"
CADMUS_R2_SHA = "c12e0cb582634fca8a5bec1f5468c50cb82cf80b9661287a602acfb96d7396dd"


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
        self._parent.last_kwargs = kwargs
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

    def __init__(self):
        self.chat = FakeChat(self)
        self.create_calls = 0
        self.last_kwargs: dict = {}
        self.received_messages_bytes: bytes | None = None
        self.closed = False

    def close(self):
        self.closed = True


class MiniAgent:
    """Minimal stand-in for AIAgent for interruptible_api_call chat_completions path."""

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


def _dest(residency: str = "US", **kw) -> IntendedDestination:
    return IntendedDestination(
        provider=kw.get("provider", "stub-local"),
        scheme="https",
        hostname=kw.get("hostname", "ai.example.test"),
        port=443,
        path_class=kw.get("path_class", "chat.completions"),
        residency=residency,
    )


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


def _api_kwargs(messages=None):
    return {
        "model": "fake-model",
        "messages": list(messages if messages is not None else MESSAGES),
        "temperature": 0,
    }


class WingR2ChatPathTests(unittest.TestCase):
    def test_00_cadmus_r2_digest(self):
        self.assertTrue(CADMUS_R2.is_file())
        self.assertEqual(_sha_file(CADMUS_R2), CADMUS_R2_SHA)

    def test_01_real_path_protected_cn_refuse_zero_client_calls(self):
        payload_preview = json.dumps(MESSAGES, ensure_ascii=False, separators=(",", ":"))
        ctx = WingEgressContext(
            sources=(_src("project", payload_preview, path="src/secret_mod.py"),),
            destination=_dest(residency="CN"),
        )
        client = FakeClient()
        agent = MiniAgent(ctx, client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_RESIDENCY")
        self.assertEqual(cm.exception.receipt.phase, "NONE")
        self.assertEqual(client.create_calls, 0)

    def test_02_real_path_missing_provenance_refuse_zero_calls(self):
        client = FakeClient()
        agent = MiniAgent(None, client)
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(agent, _api_kwargs())
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client.create_calls, 0)

        ctx = WingEgressContext(sources=(), destination=_dest())
        client2 = FakeClient()
        with self.assertRaises(WingRefusal) as cm2:
            interruptible_api_call(MiniAgent(ctx, client2), _api_kwargs())
        self.assertEqual(cm2.exception.receipt.decision, "REFUSE_SOURCE_POLICY")
        self.assertEqual(client2.create_calls, 0)

    def test_03_real_path_generic_permit_one_call_bytes_equal(self):
        messages = list(MESSAGES)
        raw = canonical_messages_payload_bytes(messages)
        ctx = WingEgressContext(
            sources=(_src("generic", raw.decode("utf-8"), path="notes/t.txt", protected_root=False),),
            destination=_dest(residency="US"),
        )
        client = FakeClient()
        agent = MiniAgent(ctx, client)
        resp = interruptible_api_call(agent, _api_kwargs(messages))
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        self.assertEqual(client.received_messages_bytes, raw)
        self.assertEqual(
            canonical_messages_payload_bytes(client.last_kwargs["messages"]),
            raw,
        )

    def test_04_legacy_direct_create_not_in_selected_branch(self):
        src = (ROOT / "agent" / "chat_completion_helpers.py").read_text(encoding="utf-8")
        start = src.index("def interruptible_api_call")
        rest = src[start + 1 :]
        next_def = rest.index("\ndef ")
        body = src[start : start + 1 + next_def]
        self.assertIn("governed_chat_completions_create", body)
        self.assertNotIn(
            "request_client.chat.completions.create(**api_kwargs)",
            body,
        )
        client = FakeClient()
        client.chat.completions.create(**_api_kwargs())
        self.assertEqual(client.create_calls, 1)
        client2 = FakeClient()
        messages = list(MESSAGES)
        raw = canonical_messages_payload_bytes(messages)
        ctx = WingEgressContext(
            sources=(_src("generic", "g", protected_root=False),),
            destination=_dest(),
        )
        out = governed_chat_completions_create(client2, _api_kwargs(messages), ctx)
        self.assertIsNotNone(out)
        self.assertEqual(client2.create_calls, 1)
        self.assertEqual(client2.received_messages_bytes, raw)

    def test_05_coverage_manifest_lists_r2_paths(self):
        man_path = ROOT / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json"
        man = json.loads(man_path.read_text(encoding="utf-8"))
        self.assertIn("governed_r2", man)
        paths = {e["path"] for e in man["governed_r2"]}
        self.assertIn("omnis_wing/absolute/hermes_chat_join.py", paths)
        self.assertIn("agent/chat_completion_helpers.py", paths)
        for e in man["governed_r2"]:
            self.assertEqual(e["status"], "governed_r2")
            self.assertTrue((ROOT / e["path"]).is_file(), e["path"])
        self.assertFalse(man.get("claims_whole_tree_ai_egress"))
        self.assertFalse(man.get("claims_all_hermes_chat_paths"))
        for e in man["inherited_hermes_transport"]:
            self.assertIn(e["status"], ("ungoverned", "inbound", "outside_r1", "outside_r2"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
