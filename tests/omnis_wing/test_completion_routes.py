"""Completion BBB: multi-route governed path + auto provenance."""

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
sys.path.insert(0, str(ROOT))
os.environ["WING_HOME"] = tempfile.mkdtemp(prefix="wing-comp-home-")
os.environ["OMNIS_WING_LEDGER_DIR"] = tempfile.mkdtemp(prefix="wing-comp-led-")
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from agent.chat_completion_helpers import interruptible_api_call  # noqa: E402
from omnis_wing.absolute.wing_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.auto_provenance import auto_wing_context, ensure_agent_wing_context  # noqa: E402
from omnis_wing.absolute.transport_broker import get_broker  # noqa: E402
from omnis_wing.completion.product_disable import load_manifest, WingRouteDisabled  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402

BBB = ROOT / "omnis_wing" / "spec" / "OMNIS-WING-COMPLETION-BBB.md"
BBB_SHA = "64e7a48b72cf83a5fad574e485f8b96983a353c45cf70fd6334a6518c011fc6c"
US = "https://ai.example.test/v1"
CN = "https://api.moonshot.cn/v1"


def _sha(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    if t.startswith("\ufeff"):
        t = t[1:]
    return hashlib.sha256(t.replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()


class FakeClient:
    is_fake = True

    def __init__(self, base_url=US):
        self.base_url = base_url
        self.create_calls = 0
        self.chat = self

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
    def __init__(self, client, api_mode="chat_completions"):
        self.api_mode = api_mode
        self._client = client
        self._interrupt_requested = False
        self.log_prefix = "t"
        self.provider = "stub"
        self.base_url = client.base_url
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

    def _run_codex_stream(self, api_kwargs, client=None, on_first_delta=None):
        self._client.create_calls += 1
        return SimpleNamespace(id="codex", output=[])

    def _anthropic_messages_create(self, api_kwargs):
        self._client.create_calls += 1
        return SimpleNamespace(id="ant", content=[])


class CompletionRouteTests(unittest.TestCase):
    def test_00_bbb_digest(self):
        self.assertEqual(_sha(BBB), BBB_SHA)

    def test_01_manifest_no_forbidden_states(self):
        man = load_manifest()
        for r in man["routes"]:
            self.assertIn(r["state"], ("GOVERNED", "DISABLED"))
            self.assertNotIn(r["state"].lower(), ("outside", "later"))
        self.assertGreaterEqual(man["summary"]["GOVERNED"], 1)
        self.assertGreaterEqual(man["summary"]["DISABLED"], 1)

    def test_02_auto_provenance_chat_completions(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        client = FakeClient(US)
        agent = MiniAgent(client)
        # no manual wing_ctx — auto
        resp = interruptible_api_call(
            agent, {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0}
        )
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)
        self.assertIsNotNone(getattr(agent, "wing_egress_context", None))

    def test_03_protected_cn_auto_refuse(self):
        client = FakeClient(CN)
        agent = MiniAgent(client)
        with self.assertRaises(Exception):
            # project-classified body to CN residency must refuse before provider
            interruptible_api_call(
                agent,
                {
                    "model": "m",
                    "messages": [
                        {
                            "role": "user",
                            "content": 'def proprietary_engine():\n    return "jourdanlabs internal"\n',
                        }
                    ],
                    "temperature": 0,
                },
            )
        self.assertEqual(client.create_calls, 0)

    def test_04_secret_in_body_refuse(self):
        client = FakeClient(US)
        agent = MiniAgent(client)
        secret = PLANTED_SECRET_MARKERS[0]
        with self.assertRaises(Exception):
            interruptible_api_call(
                agent,
                {
                    "model": "m",
                    "messages": [{"role": "user", "content": "hi"}],
                    "extra_body": {"x": secret},
                    "temperature": 0,
                },
            )
        self.assertEqual(client.create_calls, 0)

    def test_05_codex_mode_governed(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        client = FakeClient(US)
        agent = MiniAgent(client, api_mode="codex_responses")
        resp = interruptible_api_call(
            agent, {"model": "m", "input": [{"role": "user", "content": "hi"}]}
        )
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)

    def test_06_anthropic_mode_governed(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        client = FakeClient("https://api.anthropic.com")
        agent = MiniAgent(client, api_mode="anthropic_messages")
        agent._anthropic_base_url = "https://api.anthropic.com"
        resp = interruptible_api_call(
            agent,
            {"model": "claude", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 16},
        )
        self.assertIsNotNone(resp)
        self.assertEqual(client.create_calls, 1)

    def test_07_universal_bytes_equal(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        client = FakeClient(US)
        agent = MiniAgent(client)
        body = {"model": "m", "messages": [{"role": "user", "content": "z"}], "temperature": 0}
        calls = {"n": 0, "body": None}

        def tx(b):
            calls["n"] += 1
            calls["body"] = b
            return SimpleNamespace(ok=True)

        ensure_agent_wing_context(agent, body)
        get_broker().transmit_callable(
            agent=agent, body=body, transmit_fn=tx, client=client, route_id="test"
        )
        self.assertEqual(calls["n"], 1)
        self.assertEqual(calls["body"]["messages"][0]["content"], "z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
