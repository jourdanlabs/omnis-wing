"""Completion HOLD repairs: product default no test signer; real side-door disables."""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Isolate env for product-default test — do NOT set SIGNER_MODE=test here globally.
_tmp = tempfile.mkdtemp(prefix="wing-p0-")
os.environ["HERMES_HOME"] = _tmp
os.environ["OMNIS_WING_LEDGER_DIR"] = tempfile.mkdtemp(prefix="wing-p0-led-")
os.environ["OMNIS_WING_FORCE_CLASSIFICATION"] = "generic"
os.environ.pop("OMNIS_WING_SIGNER_MODE", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from omnis_wing.absolute.auto_provenance import (  # noqa: E402
    resolve_evidence_session,
    ensure_agent_wing_context,
)
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.receipt_spine import UnavailableSigner, Ed25519TestSigner  # noqa: E402
from omnis_wing.completion.side_doors import (  # noqa: E402
    install_side_door_guards,
    handler_is_disabled,
    guards_installed,
)
from omnis_wing.completion.product_disable import WingRouteDisabled  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402


class FakeClient:
    is_fake = True

    def __init__(self, base_url="https://ai.example.test/v1"):
        self.base_url = base_url
        self.create_calls = 0
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.create_calls += 1
        return SimpleNamespace(id="x", choices=[])

    def close(self):
        pass


class MiniAgent:
    def __init__(self, client):
        self.api_mode = "chat_completions"
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


class CompletionP0RepairTests(unittest.TestCase):
    def test_p0a_product_default_no_test_signer(self):
        os.environ.pop("OMNIS_WING_SIGNER_MODE", None)
        # fresh agent, no production signer
        class A:
            pass

        agent = A()
        sess = resolve_evidence_session(agent)
        self.assertIsInstance(sess.signer, UnavailableSigner)
        self.assertFalse(sess.signer.available())
        self.assertNotIsInstance(sess.signer, Ed25519TestSigner)

    def test_p0a_clean_env_refuse_before_provider(self):
        os.environ.pop("OMNIS_WING_SIGNER_MODE", None)
        # Import call path after env clear
        from agent.chat_completion_helpers import interruptible_api_call

        client = FakeClient()
        agent = MiniAgent(client)
        # ensure no leftover context/signer
        if hasattr(agent, "wing_egress_context"):
            delattr(agent, "wing_egress_context")
        if hasattr(agent, "wing_production_signer"):
            delattr(agent, "wing_production_signer")
        if hasattr(agent, "wing_evidence_session"):
            delattr(agent, "wing_evidence_session")
        with self.assertRaises(WingRefusal) as cm:
            interruptible_api_call(
                agent,
                {
                    "model": "m",
                    "messages": [{"role": "user", "content": "hi"}],
                    "temperature": 0,
                },
            )
        self.assertEqual(cm.exception.receipt.decision, "REFUSE_POLICY_INVALID")
        self.assertEqual(client.create_calls, 0)

    def test_p0a_test_mode_opt_in_only(self):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
        try:
            sess = resolve_evidence_session(None)
            self.assertIsInstance(sess.signer, Ed25519TestSigner)
        finally:
            os.environ.pop("OMNIS_WING_SIGNER_MODE", None)

    def test_p0b_primary_import_installs_guards(self):
        import omnis_wing.absolute.hermes_chat_join  # noqa: F401
        from omnis_wing.completion.side_doors import install_errors

        install_side_door_guards()
        self.assertTrue(guards_installed())
        errs = install_errors()
        self.assertTrue(
            handler_is_disabled("tools.vision_tools", "_handle_vision_analyze"),
            msg=f"vision not disabled; errors={errs}",
        )
        self.assertTrue(handler_is_disabled("tools.image_generation_tool", "_handle_image_generate"))
        self.assertTrue(handler_is_disabled("tools.tts_tool", "text_to_speech_tool"))
        self.assertTrue(handler_is_disabled("tools.transcription_tools", "transcribe_audio"))
        self.assertTrue(handler_is_disabled("tools.mixture_of_agents_tool", "mixture_of_agents_tool"))

    def test_p0b_real_handlers_refuse_zero_transport(self):
        install_side_door_guards()
        import tools.vision_tools as vt
        import tools.tts_tool as tts
        import tools.image_generation_tool as igt
        import tools.transcription_tools as tr
        import tools.mixture_of_agents_tool as moa

        # Fake transport counters would not be reached — handlers raise first
        with self.assertRaises(WingRouteDisabled):
            vt._handle_vision_analyze({"image_url": "https://example.com/x.png", "question": "q"})
        with self.assertRaises(WingRouteDisabled):
            tts.text_to_speech_tool(text="hello")
        with self.assertRaises(WingRouteDisabled):
            igt._handle_image_generate({"prompt": "cat"})
        with self.assertRaises(WingRouteDisabled):
            tr.transcribe_audio("/tmp/nonexistent-wing-test.ogg")
        # async moa — call and expect raise
        import asyncio

        async def _run():
            return await moa.mixture_of_agents_tool(user_prompt="hi")

        with self.assertRaises(WingRouteDisabled):
            asyncio.run(_run())

    def test_p1_handoff_hygiene_no_planted_marker(self):
        secret = PLANTED_SECRET_MARKERS[0]
        bare = hashlib.sha256(secret.encode()).hexdigest()
        handoff = (ROOT / "OMNIS-WING-COMPLETION-HANDOFF.md").read_text(encoding="utf-8")
        self.assertNotIn(secret, handoff)
        self.assertNotIn(bare, handoff)
        # Command must reference real test path
        self.assertIn(
            "test_r4_production_signer_health.R4ProductionSignerHealthTests.test_12_opt_in_real_keychain_if_enrolled",
            handoff,
        )
        self.assertNotIn("WING_R1_PLANTED", handoff)


if __name__ == "__main__":
    unittest.main(verbosity=2)
