"""Completion HOLD repairs: P0-A signer default + fail-closed side-door arming."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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

from omnis_wing.absolute.auto_provenance import resolve_evidence_session  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.receipt_spine import UnavailableSigner, Ed25519TestSigner  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402
from omnis_wing.completion.product_disable import WingRouteDisabled  # noqa: E402
from omnis_wing.completion.side_doors import (  # noqa: E402
    SideDoorArmingError,
    arm_side_doors,
    ensure_side_doors_armed,
    force_unresolved_for_test,
    get_arming_state,
    guards_installed,
    handler_is_disabled,
    DISABLED_TOOL_NAMES,
)


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

        class A:
            pass

        sess = resolve_evidence_session(A())
        self.assertIsInstance(sess.signer, UnavailableSigner)
        self.assertFalse(sess.signer.available())
        self.assertNotIsInstance(sess.signer, Ed25519TestSigner)

    def test_p0a_clean_env_refuse_before_provider(self):
        os.environ.pop("OMNIS_WING_SIGNER_MODE", None)
        from agent.chat_completion_helpers import interruptible_api_call

        client = FakeClient()
        agent = MiniAgent(client)
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

    def test_p0b_ensure_armed_on_primary_join(self):
        st = ensure_side_doors_armed()
        self.assertTrue(st.complete)
        self.assertTrue(st.registry_wrapped)
        self.assertTrue(st.import_hook_installed)
        self.assertTrue(guards_installed())
        for route, status in st.routes.items():
            self.assertIn(status, ("ARMED", "NAMED_OK"), msg=f"{route}={status}")

    def test_p0b_registry_dispatch_denies_disabled_tools(self):
        ensure_side_doors_armed()
        from tools.registry import registry

        # Register a fake disabled-name tool with a transport that must never run
        transport_calls = {"n": 0}

        def evil_handler(args, **kw):
            transport_calls["n"] += 1
            return "sent"

        registry.register(
            name="vision_analyze",
            toolset="wing_test",
            schema={"name": "vision_analyze", "description": "t", "parameters": {}},
            handler=evil_handler,
            override=True,
        )
        # Handler on entry must already be refuse wrapper
        entry = registry.get_entry("vision_analyze")
        self.assertTrue(getattr(entry.handler, "__omnis_wing_disabled__", False))
        with self.assertRaises(WingRouteDisabled):
            registry.dispatch("vision_analyze", {"image_url": "x"})
        self.assertEqual(transport_calls["n"], 0)

        # Other disabled names
        for tname in ("image_generate", "text_to_speech", "mixture_of_agents", "video_analyze"):
            registry.register(
                name=tname,
                toolset="wing_test",
                schema={"name": tname, "description": "t", "parameters": {}},
                handler=evil_handler,
                override=True,
            )
            with self.assertRaises(WingRouteDisabled):
                registry.dispatch(tname, {})
        self.assertEqual(transport_calls["n"], 0)

    def test_p0b_import_hook_patches_late_module(self):
        ensure_side_doors_armed()
        # Simulate a late-loaded side-door module
        mod = types.ModuleType("tools.vision_tools")

        def _handle_vision_analyze(args, **kw):
            return "would_call_provider"

        mod._handle_vision_analyze = _handle_vision_analyze
        sys.modules["tools.vision_tools"] = mod
        # Trigger import hook path via __import__ of watched name
        __import__("tools.vision_tools")
        # Re-run patch explicitly through arm (hook also runs on import)
        from omnis_wing.completion.side_doors import _patch_module_handlers

        _patch_module_handlers("tools.vision_tools")
        self.assertTrue(handler_is_disabled("tools.vision_tools", "_handle_vision_analyze"))
        with self.assertRaises(WingRouteDisabled):
            sys.modules["tools.vision_tools"]._handle_vision_analyze({})

    def test_p0b_can_fail_unresolved_refuses_loudly(self):
        ensure_side_doors_armed()
        force_unresolved_for_test("tools.vision_tools")
        try:
            st = arm_side_doors(force_rearm=True)
            self.assertFalse(st.complete)
            self.assertEqual(st.routes.get("tools.vision_tools"), "UNRESOLVED")
            with self.assertRaises(SideDoorArmingError) as cm:
                ensure_side_doors_armed()
            self.assertIn("tools.vision_tools", cm.exception.unresolved)
            # Primary join import path would raise — simulate ensure call site
            with self.assertRaises(SideDoorArmingError):
                from omnis_wing.completion.side_doors import ensure_side_doors_armed as ens

                ens()
        finally:
            force_unresolved_for_test(None)
            arm_side_doors(force_rearm=True)
            ensure_side_doors_armed()

    def test_p0b_fresh_subprocess_no_dep_stubs_arms_and_denies(self):
        """Fresh process: no test-only httpx/requests stubs; registry deny must arm."""
        code = textwrap.dedent(
            f"""
            import os, sys
            sys.path.insert(0, {str(ROOT)!r})
            os.environ['HERMES_HOME'] = {tempfile.mkdtemp()!r}
            os.environ['OMNIS_WING_LEDGER_DIR'] = {tempfile.mkdtemp()!r}
            # Explicitly do NOT install httpx/openai stubs
            from omnis_wing.completion.side_doors import ensure_side_doors_armed, WingRouteDisabled
            from omnis_wing.completion.product_disable import WingRouteDisabled as WRD
            st = ensure_side_doors_armed()
            assert st.complete, st.as_dict()
            assert st.registry_wrapped
            from tools.registry import registry
            calls = {{'n': 0}}
            def evil(args, **kw):
                calls['n'] += 1
                return 'nope'
            for name in ('vision_analyze', 'image_generate', 'text_to_speech', 'mixture_of_agents'):
                registry.register(
                    name=name, toolset='t', schema={{'name': name, 'description': 'd', 'parameters': {{}}}},
                    handler=evil, override=True,
                )
                try:
                    registry.dispatch(name, {{}})
                    raise SystemExit('dispatch did not refuse ' + name)
                except WRD:
                    pass
            assert calls['n'] == 0
            print('FRESH_OK')
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("FRESH_OK", proc.stdout)

    def test_p0b_fresh_subprocess_can_fail_incomplete(self):
        code = textwrap.dedent(
            f"""
            import os, sys
            sys.path.insert(0, {str(ROOT)!r})
            os.environ['HERMES_HOME'] = {tempfile.mkdtemp()!r}
            from omnis_wing.completion import side_doors as sd
            sd.ensure_side_doors_armed()
            sd.force_unresolved_for_test('tools.tts_tool')
            try:
                sd.ensure_side_doors_armed()
            except sd.SideDoorArmingError as e:
                assert 'tools.tts_tool' in e.unresolved
                print('CANFAIL_OK')
            else:
                raise SystemExit('expected SideDoorArmingError')
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("CANFAIL_OK", proc.stdout)

    def test_p1_handoff_hygiene_no_planted_marker(self):
        secret = PLANTED_SECRET_MARKERS[0]
        bare = hashlib.sha256(secret.encode()).hexdigest()
        handoff = (ROOT / "OMNIS-WING-COMPLETION-HANDOFF.md").read_text(encoding="utf-8")
        self.assertNotIn(secret, handoff)
        self.assertNotIn(bare, handoff)
        self.assertIn(
            "test_r4_production_signer_health.R4ProductionSignerHealthTests.test_12_opt_in_real_keychain_if_enrolled",
            handoff,
        )
        self.assertNotIn("WING_R1_PLANTED", handoff)


if __name__ == "__main__":
    unittest.main(verbosity=2)
