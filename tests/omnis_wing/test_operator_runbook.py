"""Wave 0 clean-profile operator workflow — cold, no Keychain mutation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.omnis_wing._fixtures import bootstrap_wing_test_env  # noqa: E402

bootstrap_wing_test_env()

from omnis_wing.absolute.production_signer import ProductionSignerAdapter  # noqa: E402
from omnis_wing.absolute.real_work import config as rw_config  # noqa: E402
from omnis_wing.absolute.real_work import launcher  # noqa: E402
from omnis_wing.absolute.real_work import operator_runbook as runbook  # noqa: E402


class _ReadyBackend:
    tag = "ai.jourdanlabs.omnis-wing.terminus.r4"

    def __init__(self) -> None:
        self.enroll_calls = 0

    def status(self):
        return {
            "ready": True,
            "state": "ENROLLED",
            "storage_state": "UNVERIFIED_AT_READ",
            "backend": "macos_keychain_bridge",
        }

    def enroll(self):
        self.enroll_calls += 1
        raise AssertionError("operator verification must never enroll")

    def public_key_bytes(self):
        return b"public-key"

    def sign(self, _message):
        raise AssertionError("operator verification must never sign")

    def verify(self, *_args):
        return True


class _LockedBackend(_ReadyBackend):
    def status(self):
        return {
            "ready": False,
            "state": "LOCKED",
            "storage_state": "UNAVAILABLE",
            "backend": "macos_keychain_bridge",
        }


class OperatorRunbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="wing-runbook-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "profile"
        self.home.mkdir(mode=0o700)
        self.old_env = dict(os.environ)
        os.environ["WING_HOME"] = str(self.home)
        os.environ["OMNIS_WING_PROFILE_HOME"] = str(self.home)
        os.environ["CADUCEUS_STATE_DIR"] = str(self.home / "caduceus-state")
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmp.cleanup()

    def _pinned_cfg(self, caduceus: Path) -> SimpleNamespace:
        return SimpleNamespace(
            caduceus_root=caduceus,
            caduceus_commit=rw_config.PINNED_CADUCEUS_COMMIT,
        )

    def _assembly(self, *, gate_commit: str | None = None, with_deps: bool = True) -> Path:
        caduceus = self.root / "assembly" / "caduceus"
        gate = caduceus.parent / "omnis-gate"
        for repo in (caduceus, gate):
            (repo / ".git").mkdir(parents=True, exist_ok=True)
        (caduceus / "src").mkdir(parents=True, exist_ok=True)
        (caduceus / "src" / "caduceus.mjs").write_text("// entry\n", encoding="utf-8")
        lock = {
            "name": "caduceus-test",
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"js-yaml": "4.3.0"}},
                "node_modules/argparse": {"version": "2.0.1"},
                "node_modules/js-yaml": {"version": "4.3.0"},
            },
        }
        (caduceus / "package-lock.json").write_text(
            json.dumps(lock, sort_keys=True) + "\n", encoding="utf-8"
        )
        if with_deps:
            (caduceus / "node_modules" / "argparse").mkdir(parents=True, exist_ok=True)
            (caduceus / "node_modules" / "argparse" / "package.json").write_text(
                '{"name":"argparse"}\n', encoding="utf-8"
            )
            (caduceus / "node_modules" / "js-yaml").mkdir(parents=True, exist_ok=True)
            (caduceus / "node_modules" / "js-yaml" / "package.json").write_text(
                "{}", encoding="utf-8"
            )
        (gate / "src").mkdir(parents=True, exist_ok=True)
        (gate / "src" / "gate.mjs").write_text("// gate\n", encoding="utf-8")
        self._gate_commit = gate_commit or rw_config.PINNED_OMNIS_GATE_COMMIT
        self._caduceus_commit = rw_config.PINNED_CADUCEUS_COMMIT
        return caduceus

    def _dependency_pins(self, caduceus: Path) -> tuple[str, str]:
        lock_bytes = (caduceus / "package-lock.json").read_bytes()
        lock = json.loads(lock_bytes)
        return (
            hashlib.sha256(lock_bytes).hexdigest(),
            rw_config._dependency_tree_sha256(caduceus, lock),
        )

    def _fake_git_run(self, args, **_kwargs):
        path = " ".join(str(a) for a in args)
        is_gate = "omnis-gate" in path
        if "status" in args:
            return SimpleNamespace(stdout="")
        commit = self._gate_commit if is_gate else self._caduceus_commit
        return SimpleNamespace(stdout=commit + "\n")

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, tuple[str, int, bytes]]:
        snapshot: dict[str, tuple[str, int, bytes]] = {}
        for path in sorted(root.rglob("*")):
            mode = path.lstat().st_mode
            relative = str(path.relative_to(root))
            if stat.S_ISDIR(mode):
                snapshot[relative] = ("directory", stat.S_IMODE(mode), b"")
            elif stat.S_ISREG(mode):
                snapshot[relative] = ("file", stat.S_IMODE(mode), path.read_bytes())
            elif stat.S_ISLNK(mode):
                snapshot[relative] = (
                    "symlink",
                    stat.S_IMODE(mode),
                    os.readlink(path).encode("utf-8"),
                )
            else:
                snapshot[relative] = ("other", stat.S_IMODE(mode), b"")
        return snapshot

    def test_exact_caduceus_and_sibling_gate_pins_are_required(self) -> None:
        caduceus = self._assembly()
        cfg = self._pinned_cfg(caduceus)
        lock_pin, tree_pin = self._dependency_pins(caduceus)
        with (
            patch.object(rw_config, "PINNED_CADUCEUS_LOCKFILE_SHA256", lock_pin),
            patch.object(rw_config, "PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256", tree_pin),
            patch.object(rw_config.subprocess, "run", side_effect=self._fake_git_run),
        ):
            self.assertEqual(
                rw_config.assert_pinned_runtime_dependencies(cfg),
                caduceus.parent / "omnis-gate",
            )

        self._gate_commit = "0" * 40
        with (
            patch.object(rw_config, "PINNED_CADUCEUS_LOCKFILE_SHA256", lock_pin),
            patch.object(rw_config, "PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256", tree_pin),
            patch.object(rw_config.subprocess, "run", side_effect=self._fake_git_run),
        ):
            with self.assertRaisesRegex(RuntimeError, "omnis_gate_tree_commit_mismatch"):
                rw_config.assert_pinned_runtime_dependencies(cfg)

    def test_missing_dependencies_and_sibling_authority_refuse(self) -> None:
        caduceus = self._assembly(with_deps=False)
        cfg = self._pinned_cfg(caduceus)
        lock_pin = hashlib.sha256((caduceus / "package-lock.json").read_bytes()).hexdigest()
        with (
            patch.object(rw_config, "PINNED_CADUCEUS_LOCKFILE_SHA256", lock_pin),
            patch.object(rw_config.subprocess, "run", side_effect=self._fake_git_run),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "caduceus_dependencies_missing_run_npm_ci"
            ):
                rw_config.assert_pinned_runtime_dependencies(cfg)

        # Sibling missing entirely.
        shutil.rmtree(caduceus.parent / "omnis-gate")
        caduceus2 = self.root / "assembly2" / "caduceus"
        (caduceus2 / ".git").mkdir(parents=True)
        (caduceus2 / "src").mkdir(parents=True)
        (caduceus2 / "src" / "caduceus.mjs").write_text("x", encoding="utf-8")
        (caduceus2 / "node_modules" / "js-yaml").mkdir(parents=True)
        (caduceus2 / "node_modules" / "js-yaml" / "package.json").write_text(
            "{}", encoding="utf-8"
        )
        cfg2 = self._pinned_cfg(caduceus2)
        with patch.object(rw_config.subprocess, "run", side_effect=self._fake_git_run):
            with self.assertRaisesRegex(RuntimeError, "omnis_gate_sibling_not_git_worktree"):
                rw_config.assert_pinned_runtime_dependencies(cfg2)

    def test_mutated_js_yaml_dependency_refuses(self) -> None:
        caduceus = self._assembly()
        cfg = self._pinned_cfg(caduceus)
        lock_pin, tree_pin = self._dependency_pins(caduceus)
        package = caduceus / "node_modules" / "js-yaml" / "package.json"
        package.write_text('{"name":"js-yaml","mutation":true}\n', encoding="utf-8")
        with (
            patch.object(rw_config, "PINNED_CADUCEUS_LOCKFILE_SHA256", lock_pin),
            patch.object(rw_config, "PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256", tree_pin),
            patch.object(rw_config.subprocess, "run", side_effect=self._fake_git_run),
        ):
            with self.assertRaisesRegex(RuntimeError, "caduceus_dependency_tree_mismatch"):
                rw_config.assert_pinned_runtime_dependencies(cfg)

    def test_private_state_and_empty_ledgers_are_initialized_honestly(self) -> None:
        cfg = SimpleNamespace(ledger_dir=self.home / "ledgers")
        state = runbook._prepare_state(self.home, cfg)
        for directory in (self.home, state["runtime"], state["wing_ledger"].parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for path in (state["wing_ledger"], state["caduceus_chain"]):
            self.assertEqual(path.read_bytes(), b"")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_ledger_intermediate_symlink_refuses_without_outside_write(self) -> None:
        outside = self.root / "outside-ledger"
        outside.mkdir(mode=0o700)
        (outside / "sentinel").write_bytes(b"ledger-sentinel")
        before = self._tree_bytes(outside)
        redirect = self.home / "redirect-ledger"
        redirect.symlink_to(outside, target_is_directory=True)
        cfg = SimpleNamespace(ledger_dir=redirect / "ledgers")
        with self.assertRaisesRegex(RuntimeError, "controlled_path_symlink_refused"):
            runbook._prepare_state(self.home, cfg)
        self.assertEqual(self._tree_bytes(outside), before)

    def test_state_intermediate_symlink_refuses_without_outside_write(self) -> None:
        outside = self.root / "outside-state"
        outside.mkdir(mode=0o700)
        (outside / "sentinel").write_bytes(b"state-sentinel")
        before = self._tree_bytes(outside)
        redirect = self.home / "redirect-state"
        redirect.symlink_to(outside, target_is_directory=True)
        os.environ["CADUCEUS_STATE_DIR"] = str(redirect / "caduceus")
        cfg = SimpleNamespace(ledger_dir=self.home / "ledgers")
        with self.assertRaisesRegex(RuntimeError, "controlled_path_symlink_refused"):
            runbook._prepare_state(self.home, cfg)
        self.assertEqual(self._tree_bytes(outside), before)

    def test_manifest_directory_symlink_refuses_without_outside_write(self) -> None:
        outside = self.root / "outside-manifests"
        outside.mkdir(mode=0o700)
        (outside / "sentinel").write_bytes(b"manifest-sentinel")
        before = self._tree_bytes(outside)
        runtime = self.home / "omnis-wing-runtime"
        runtime.mkdir(mode=0o700)
        (runtime / "manifests").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "controlled_path_symlink_refused"):
            runbook._manifest_path(runtime, "a" * 64)
        self.assertEqual(self._tree_bytes(outside), before)

    def test_bridge_status_is_read_without_enrollment_or_signing(self) -> None:
        runtime = self.home / "omnis-wing-runtime"
        bridge = runtime / "bin" / "omnis_wing_keychain"
        bridge.parent.mkdir(parents=True)
        bridge.write_text("bridge", encoding="utf-8")
        bridge.chmod(0o700)
        cfg = SimpleNamespace(backend="keychain", bridge_path=bridge)
        backend = _ReadyBackend()
        adapter = ProductionSignerAdapter(backend=backend)
        with patch.object(runbook, "build_signer_from_config", return_value=adapter):
            got_bridge, status_value = runbook._prepare_bridge(
                cfg, runtime, compile_bridge=False
            )
        self.assertEqual(got_bridge, bridge.resolve())
        self.assertEqual(status_value["state"], "ENROLLED")
        self.assertEqual(backend.enroll_calls, 0)

    def test_bridge_directory_symlink_refuses_without_outside_write(self) -> None:
        runtime = self.home / "omnis-wing-runtime"
        runtime.mkdir(mode=0o700)
        outside = self.root / "outside-bridge"
        outside.mkdir(mode=0o700)
        bridge = outside / "omnis_wing_keychain"
        bridge.write_bytes(b"bridge-sentinel")
        bridge.chmod(0o700)
        before = self._tree_bytes(outside)
        (runtime / "bin").symlink_to(outside, target_is_directory=True)
        cfg = SimpleNamespace(
            backend="keychain",
            bridge_path=runtime / "bin" / "omnis_wing_keychain",
        )
        adapter = ProductionSignerAdapter(backend=_ReadyBackend())
        with patch.object(runbook, "build_signer_from_config", return_value=adapter):
            with self.assertRaisesRegex(RuntimeError, "controlled_path_symlink_refused"):
                runbook._prepare_bridge(cfg, runtime, compile_bridge=False)
        self.assertEqual(self._tree_bytes(outside), before)

    def test_signer_lock_refuses_without_enrollment(self) -> None:
        runtime = self.home / "omnis-wing-runtime"
        bridge = runtime / "bin" / "omnis_wing_keychain"
        bridge.parent.mkdir(parents=True)
        bridge.write_text("bridge", encoding="utf-8")
        bridge.chmod(0o700)
        cfg = SimpleNamespace(backend="keychain", bridge_path=bridge)
        adapter = ProductionSignerAdapter(backend=_LockedBackend())
        with patch.object(runbook, "build_signer_from_config", return_value=adapter):
            with self.assertRaisesRegex(RuntimeError, "signer_not_enrolled_or_locked:LOCKED"):
                runbook._prepare_bridge(cfg, runtime, compile_bridge=False)

    def test_content_addressed_manifest_is_secret_free_and_exact(self) -> None:
        operator = self.home / "operator"
        operator.mkdir(mode=0o700)
        production = operator / "production.yaml"
        real_work = operator / "real-work.json"
        lanes = operator / "lanes.yaml"
        bridge = self.home / "omnis-wing-runtime" / "bin" / "omnis_wing_keychain"
        production.write_text("production-config", encoding="utf-8")
        real_work.write_text("real-work-config", encoding="utf-8")
        lanes.write_text("lanes: {}", encoding="utf-8")
        runtime = self.home / "omnis-wing-runtime"
        runtime.mkdir(mode=0o700)
        (runtime / "bin").mkdir(mode=0o700)
        bridge.write_text("bridge", encoding="utf-8")
        bridge.chmod(0o700)
        os.environ["CADUCEUS_LANES"] = str(lanes)
        os.environ["MINIMAX_API_KEY"] = "provider-secret-value-sk-not-for-stdout"
        os.environ["CADUCEUS_SERVICE_TOKEN"] = "A" * 43

        prod = SimpleNamespace(
            backend="keychain",
            bridge_path=bridge,
            ledger_dir=self.home / "ledgers",
            source=str(production),
        )
        rw = SimpleNamespace(
            caduceus_root=self.root / "assembly" / "caduceus",
            caduceus_base="http://127.0.0.1:28791",
            caduceus_instance_id="runbook-test",
            source=str(real_work),
            public_dict=lambda: {"target": {"provider": "minimax", "model": "MiniMax-M3"}},
        )
        policy = SimpleNamespace(
            mode="enforce",
            policy_version="v1",
            policy_digest="a" * 64,
            key_id="operator-key",
            require_remote_anchor=False,
        )
        signer = {
            "state": "ENROLLED",
            "storage_state": "UNVERIFIED_AT_READ",
            "backend": "macos_keychain_bridge",
            "key_id": "wing-r4:test",
            "signature_algorithm": "ecdsa-p256-x962-sha256",
            "public_key_sha256": "b" * 64,
        }
        gate = self.root / "assembly" / "omnis-gate"
        with (
            patch.object(runbook, "assert_contract_not_drifted"),
            patch.object(runbook, "load_production_config", return_value=prod),
            patch.object(runbook, "load_real_work_config", return_value=rw),
            patch.object(runbook, "assert_pinned_runtime_dependencies", return_value=gate),
            patch.object(
                runbook,
                "caduceus_dependency_identity",
                return_value={
                    "lockfile_sha256": "e" * 64,
                    "dependency_tree_sha256": "f" * 64,
                    "assembly_command": "npm ci --ignore-scripts",
                },
            ),
            patch.object(runbook, "service_capability", return_value="local-service-secret-token"),
            patch.object(runbook, "load_policy", return_value=policy),
            patch.object(runbook, "_prepare_bridge", return_value=(bridge, signer)),
            patch.object(
                runbook,
                "_git_identity",
                return_value={"commit": "c" * 40, "tree": "d" * 40, "dirty": False},
            ),
            patch.object(
                runbook,
                "_route_summary",
                return_value={"governed": ["chat"], "disabled": ["image"], "summary": {}},
            ),
        ):
            result = runbook.prepare()
        manifest = Path(result["manifest"])
        raw = manifest.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["manifest_sha256"])
        self.assertNotIn(b"local-service-secret-token", raw)
        self.assertNotIn(b"provider-secret-value", raw)
        self.assertNotIn(b"sk-", raw)
        body = json.loads(raw)
        self.assertEqual(body["schema"], runbook.SCHEMA)
        self.assertEqual(body["pins"]["caduceus"], rw_config.PINNED_CADUCEUS_COMMIT)
        self.assertEqual(body["pins"]["omnis_gate"], rw_config.PINNED_OMNIS_GATE_COMMIT)
        self.assertTrue(runbook.SCHEMA_PATH.is_file())
        self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["keychain_mutations"], 0)

    def test_policy_id_mismatch_refuses(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "policy_id_mismatch"):
            rw_config.parse_real_work_config(
                {
                    "policy_id": "wrong",
                    "caduceus_base": "http://127.0.0.1:28791",
                    "caduceus_instance_id": "x",
                    "caduceus_root": "/tmp/caduceus",
                    "caduceus_commit": rw_config.PINNED_CADUCEUS_COMMIT,
                    "service_token_env": "CADUCEUS_SERVICE_TOKEN",
                    "target": {
                        "provider": "minimax",
                        "scheme": "https",
                        "hostname": "api.minimax.io",
                        "port": 443,
                        "path": "/v1/chat/completions",
                        "model": "MiniMax-M3",
                        "residency": "CN",
                        "api_shape": "openai_chat_completions",
                        "lane": "plan",
                    },
                },
                source="test",
            )

    def test_dirty_wing_tree_refuses_manifest(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "wing_tree_tracked_or_untracked_drift"):
            runbook._require_clean_wing_identity({"dirty": True})

    def test_env_only_configs_refuse_before_manifest(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "production_config_must_be_explicit_regular_file"
        ):
            runbook._config_digest("env", "production")

    def test_default_live_wing_home_is_refused(self) -> None:
        live = Path.home() / ".omnis-wing"
        os.environ["WING_HOME"] = str(live)
        os.environ["OMNIS_WING_PROFILE_HOME"] = str(live)
        with self.assertRaisesRegex(RuntimeError, "live_default_wing_home_refused"):
            runbook._require_isolated_profile()

    def test_equivalent_live_wing_dotdot_alias_is_refused_before_preparation(self) -> None:
        live_alias = Path.home() / ".omnis-wing" / ".." / ".omnis-wing"
        os.environ["WING_HOME"] = str(live_alias)
        os.environ["OMNIS_WING_PROFILE_HOME"] = str(live_alias)
        with (
            patch.object(runbook, "mkdir_private_tree") as mkdir,
            patch.object(runbook, "inspect_controlled_dir") as inspect,
        ):
            with self.assertRaisesRegex(RuntimeError, "live_default_wing_home_refused"):
                runbook._require_isolated_profile()
        mkdir.assert_not_called()
        inspect.assert_not_called()

    def test_stop_command_refuses_equivalent_live_alias_before_launcher(self) -> None:
        live_alias = Path.home() / ".omnis-wing" / ".." / ".omnis-wing"
        os.environ["WING_HOME"] = str(live_alias)
        os.environ["OMNIS_WING_PROFILE_HOME"] = str(live_alias)
        with patch.object(launcher, "stop_owned_service") as stop:
            self.assertEqual(runbook.main(["stop"]), 2)
        stop.assert_not_called()

    def test_port_collision_refuses_before_start(self) -> None:
        cfg = SimpleNamespace(caduceus_base="http://127.0.0.1:28791")
        with (
            patch.object(launcher, "load_real_work_config", return_value=cfg),
            patch.object(launcher, "assert_pinned_runtime_dependencies"),
            patch.object(launcher, "service_capability", return_value="x" * 43),
            patch.object(launcher, "status", side_effect=OSError("not ours")),
            patch.object(launcher, "loopback_origin_is_listening", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "caduceus_port_collision_untrusted_service"):
                launcher.ensure_service()

    def test_stop_targets_only_exact_owned_process(self) -> None:
        runtime = self.home / "omnis-wing-runtime"
        runtime.mkdir(mode=0o700)
        entry = self.root / "assembly" / "caduceus" / "src" / "caduceus.mjs"
        entry.parent.mkdir(parents=True)
        entry.write_text("x", encoding="utf-8")
        cfg = SimpleNamespace(
            caduceus_root=entry.parents[1],
            caduceus_commit=rw_config.PINNED_CADUCEUS_COMMIT,
            caduceus_base="http://127.0.0.1:28791",
        )
        command = f"/usr/bin/node {entry}"
        owner = {
            "schema": "omnis-wing.caduceus-process-owner.v1",
            "pid": 4242,
            "process_start": "Sat Aug 9 09:00:00 2026",
            "command": command,
            "caduceus_commit": cfg.caduceus_commit,
            "caduceus_base": cfg.caduceus_base,
        }
        (runtime / "caduceus.pid").write_text(json.dumps(owner), encoding="ascii")

        calls = []

        def fake_kill(pid, sig):
            calls.append((pid, sig))
            if sig == 0:
                raise ProcessLookupError

        with (
            patch.object(launcher, "load_real_work_config", return_value=cfg),
            patch.object(launcher, "_runtime_dir", return_value=runtime),
            patch.object(
                launcher,
                "_process_identity",
                return_value={"process_start": owner["process_start"], "command": command},
            ),
            patch.object(launcher.os, "kill", side_effect=fake_kill),
        ):
            result = launcher.stop_owned_service()
        self.assertEqual(result["state"], "STOPPED")
        self.assertEqual([pid for pid, _sig in calls], [4242, 4242])
        self.assertFalse((runtime / "caduceus.pid").exists())

    def test_stop_refuses_reused_pid_without_signaling(self) -> None:
        runtime = self.home / "omnis-wing-runtime"
        runtime.mkdir(mode=0o700)
        entry = self.root / "assembly" / "caduceus" / "src" / "caduceus.mjs"
        entry.parent.mkdir(parents=True)
        entry.write_text("x", encoding="utf-8")
        cfg = SimpleNamespace(
            caduceus_root=entry.parents[1],
            caduceus_commit=rw_config.PINNED_CADUCEUS_COMMIT,
            caduceus_base="http://127.0.0.1:28791",
        )
        owner = {
            "schema": "omnis-wing.caduceus-process-owner.v1",
            "pid": 4242,
            "process_start": "Sat Aug 9 09:00:00 2026",
            "command": f"/usr/bin/node {entry}",
            "caduceus_commit": cfg.caduceus_commit,
            "caduceus_base": cfg.caduceus_base,
        }
        (runtime / "caduceus.pid").write_text(json.dumps(owner), encoding="ascii")
        with (
            patch.object(launcher, "load_real_work_config", return_value=cfg),
            patch.object(launcher, "_runtime_dir", return_value=runtime),
            patch.object(
                launcher,
                "_process_identity",
                return_value={
                    "process_start": "Sat Aug 9 09:01:00 2026",
                    "command": owner["command"],
                },
            ),
            patch.object(launcher.os, "kill") as kill,
        ):
            with self.assertRaisesRegex(RuntimeError, "caduceus_process_ownership_mismatch"):
                launcher.stop_owned_service()
        kill.assert_not_called()

    def test_cli_verify_setup_alias_and_secret_scrub(self) -> None:
        os.environ["MINIMAX_API_KEY"] = "sk-live-super-secret-value-xyz"
        with patch.object(
            runbook,
            "prepare",
            return_value={
                "state": "READY",
                "manifest": "/tmp/run.json",
                "manifest_sha256": "e" * 64,
                "signer_state": "ENROLLED",
                "provider_calls": 0,
                "keychain_mutations": 0,
            },
        ):
            code = runbook.main(["verify-setup"])
        self.assertEqual(code, 0)

        with patch.object(
            runbook,
            "prepare",
            side_effect=rw_config.RealWorkConfigError(
                "caduceus_dependencies_missing_run_npm_ci"
            ),
        ):
            from io import StringIO

            err = StringIO()
            with patch.object(sys, "stderr", err):
                code = runbook.main(["verify"])
            self.assertEqual(code, 2)
            body = err.getvalue()
            self.assertIn("caduceus_dependencies_missing_run_npm_ci", body)
            self.assertNotIn("sk-live-super-secret-value-xyz", body)

    def test_scrub_public_text_redacts_credential_patterns(self) -> None:
        text = runbook._scrub_public_text(
            'token Bearer abcdefghijklmnop and sk-abcdefghijklmnop'
        )
        self.assertNotIn("Bearer abc", text)
        self.assertNotIn("sk-abc", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
