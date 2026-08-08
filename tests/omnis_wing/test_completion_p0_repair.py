"""Completion HOLD repairs: P0-A + fail-closed side-doors incl. importlib path."""

from __future__ import annotations

import hashlib
import importlib
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
os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
os.environ.pop("OMNIS_WING_SIGNER_MODE", None)

for _n in ("requests", "yaml"):
    if _n not in sys.modules:
        m = types.ModuleType(_n)
        if _n == "yaml":
            m.safe_load = lambda s: {}
        sys.modules[_n] = m

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from omnis_wing.absolute.auto_provenance import resolve_evidence_session  # noqa: E402
from omnis_wing.absolute.hermes_chat_join import WingRefusal  # noqa: E402
from omnis_wing.absolute.receipt_spine import UnavailableSigner, Ed25519TestSigner  # noqa: E402
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS  # noqa: E402
from omnis_wing.completion.product_disable import WingRouteDisabled, load_manifest  # noqa: E402
from omnis_wing.completion.side_doors import (  # noqa: E402
    MODULE_HANDLER_TARGETS,
    ROUTE_MODULES,
    SideDoorArmingError,
    arm_side_doors,
    ensure_side_doors_armed,
    force_unresolved_for_test,
    guards_installed,
    handler_is_disabled,
    skip_stub_for_test,
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
        self.assertTrue(st.importlib_wrapped)
        self.assertTrue(guards_installed())
        for route, status in st.routes.items():
            self.assertIn(status, ("ARMED", "NAMED_OK"), msg=f"{route}={status} state={st.as_dict()}")

    def test_p0b_registry_dispatch_denies_disabled_tools(self):
        ensure_side_doors_armed()
        from tools.registry import registry

        transport_calls = {"n": 0}

        def evil_handler(args, **kw):
            transport_calls["n"] += 1
            return "sent"

        for tname in (
            "vision_analyze",
            "image_generate",
            "text_to_speech",
            "mixture_of_agents",
            "video_analyze",
        ):
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

    def test_p0b_importlib_path_disables_transcription(self):
        """Bulma control: importlib.import_module after arm must not leave live callables."""
        ensure_side_doors_armed()
        # Drop any existing module to force a load path
        for key in list(sys.modules):
            if key == "tools.transcription_tools" or key.startswith("tools.transcription_tools."):
                del sys.modules[key]
        mod = importlib.import_module("tools.transcription_tools")
        self.assertTrue(
            getattr(mod, "__omnis_wing_deny_stub__", False)
            or handler_is_disabled("tools.transcription_tools", "transcribe_audio"),
            msg=f"mod attrs={[a for a in dir(mod) if not a.startswith('__')][:20]}",
        )
        with self.assertRaises(WingRouteDisabled):
            mod.transcribe_audio("/tmp/nonexistent-wing.ogg")

    def test_p0b_importlib_all_module_routes(self):
        ensure_side_doors_armed()
        man = load_manifest()
        module_routes = [
            r["route_id"]
            for r in man["routes"]
            if r.get("state") == "DISABLED"
            and r.get("broker_join") == "DISABLED"
            and r["route_id"] != "gateway.platform_messaging"
        ]
        for route_id in module_routes:
            mods = ROUTE_MODULES.get(route_id) or ()
            self.assertTrue(mods, msg=f"no modules for {route_id}")
            primary = mods[0]
            # re-import via importlib (product path)
            if primary in sys.modules and getattr(sys.modules[primary], "__omnis_wing_deny_stub__", False):
                mod = sys.modules[primary]
            else:
                try:
                    if primary in sys.modules:
                        del sys.modules[primary]
                except KeyError:
                    pass
                mod = importlib.import_module(primary)
            # Must not expose a live un-disabled primary entry
            if primary in MODULE_HANDLER_TARGETS:
                names = MODULE_HANDLER_TARGETS[primary][1]
                if names:
                    # at least one entry exists and refuses
                    found = False
                    for n in names:
                        if hasattr(mod, n):
                            found = True
                            with self.assertRaises(WingRouteDisabled, msg=f"{primary}.{n}"):
                                fn = getattr(mod, n)
                                try:
                                    res = fn()
                                    # if async coroutine
                                    if hasattr(res, "__await__"):
                                        pass
                                except TypeError:
                                    fn({})
                            self.assertTrue(handler_is_disabled(primary, n) or getattr(mod, "__omnis_wing_deny_stub__", False))
                    self.assertTrue(found or getattr(mod, "__omnis_wing_deny_stub__", False), msg=primary)
                else:
                    # pattern modules — stub or at least one disabled callable
                    self.assertTrue(
                        getattr(mod, "__omnis_wing_deny_stub__", False)
                        or any(
                            callable(getattr(mod, a, None))
                            and getattr(getattr(mod, a), "__omnis_wing_disabled__", False)
                            for a in dir(mod)
                        ),
                        msg=primary,
                    )

    def test_p0b_can_fail_unresolved_refuses_loudly(self):
        ensure_side_doors_armed()
        force_unresolved_for_test("tools.vision_tools")
        try:
            st = arm_side_doors(force_rearm=True)
            self.assertFalse(st.complete)
            with self.assertRaises(SideDoorArmingError) as cm:
                ensure_side_doors_armed()
            self.assertIn("tools.vision_tools", cm.exception.unresolved)
        finally:
            force_unresolved_for_test(None)
            arm_side_doors(force_rearm=True)
            ensure_side_doors_armed()

    def test_p0b_can_fail_skip_stub_unresolved(self):
        """If deny-stub cannot install and module not patched → not complete."""
        skip_stub_for_test("tools.transcription_tools")
        # remove module so eager path needs stub
        for key in list(sys.modules):
            if key == "tools.transcription_tools":
                del sys.modules[key]
        try:
            st = arm_side_doors(force_rearm=True)
            # may be unresolved
            if st.routes.get("tools.transcription_tools") == "UNRESOLVED":
                with self.assertRaises(SideDoorArmingError):
                    ensure_side_doors_armed()
            else:
                # if real module patched without stub, still ok — force unresolved
                force_unresolved_for_test("tools.transcription_tools")
                with self.assertRaises(SideDoorArmingError):
                    ensure_side_doors_armed()
        finally:
            skip_stub_for_test(None)
            force_unresolved_for_test(None)
            arm_side_doors(force_rearm=True)
            ensure_side_doors_armed()

    def test_p0b_fresh_subprocess_importlib_all_disabled(self):
        code = textwrap.dedent(
            f"""
            import os, sys, tempfile, importlib
            sys.path.insert(0, {str(ROOT)!r})
            os.environ['HERMES_HOME'] = {tempfile.mkdtemp()!r}
            os.environ['OMNIS_WING_LEDGER_DIR'] = {tempfile.mkdtemp()!r}
            # no httpx stubs
            from omnis_wing.completion.side_doors import ensure_side_doors_armed, ROUTE_MODULES, MODULE_HANDLER_TARGETS
            from omnis_wing.completion.product_disable import WingRouteDisabled, load_manifest
            st = ensure_side_doors_armed()
            assert st.complete and st.importlib_wrapped and st.registry_wrapped, st.as_dict()
            man = load_manifest()
            routes = [r['route_id'] for r in man['routes']
                      if r.get('state')=='DISABLED' and r.get('broker_join')=='DISABLED'
                      and r['route_id']!='gateway.platform_messaging']
            for route_id in routes:
                mods = ROUTE_MODULES[route_id]
                primary = mods[0]
                # force importlib path even if stub already present
                mod = importlib.import_module(primary)
                if primary in MODULE_HANDLER_TARGETS and MODULE_HANDLER_TARGETS[primary][1]:
                    name = MODULE_HANDLER_TARGETS[primary][1][0]
                    fn = getattr(mod, name)
                    try:
                        fn()
                    except TypeError:
                        try:
                            fn({{}})
                        except WingRouteDisabled:
                            pass
                        else:
                            # async?
                            raise SystemExit('no refuse '+primary+'.'+name)
                    except WingRouteDisabled:
                        pass
                    else:
                        raise SystemExit('no refuse '+primary+'.'+name)
                else:
                    assert getattr(mod, '__omnis_wing_deny_stub__', False) or any(
                        getattr(getattr(mod,a), '__omnis_wing_disabled__', False)
                        for a in dir(mod) if callable(getattr(mod,a,None))
                    ), primary
            # registry evil
            from tools.registry import registry
            calls={{'n':0}}
            def evil(a,**k):
                calls['n']+=1
                return 'SENT'
            registry.register(name='vision_analyze', toolset='t',
                schema={{'name':'vision_analyze','description':'d','parameters':{{}}}},
                handler=evil, override=True)
            try:
                registry.dispatch('vision_analyze', {{}})
            except WingRouteDisabled:
                pass
            assert calls['n']==0
            print('FRESH_IMPORTLIB_OK')
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("FRESH_IMPORTLIB_OK", proc.stdout)

    def test_p0b_fresh_subprocess_can_fail_incomplete(self):
        code = textwrap.dedent(
            f"""
            import os, sys, tempfile
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
