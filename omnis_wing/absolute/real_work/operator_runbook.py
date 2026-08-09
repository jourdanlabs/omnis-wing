"""Repeatable, fail-closed operator workflow for an isolated WING profile.

This module prepares run-owned state, observes the production signer without
enrolling or rotating it, freezes a secret-free manifest, and delegates local
CADUCEUS lifecycle to the ownership-aware launcher.  It never submits a model
request and never changes Keychain state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from omnis_wing.absolute.ledger_security import (
    LedgerSecurityError,
    inspect_controlled_dir,
    inspect_controlled_file,
    mkdir_private_tree,
    prepare_private_ledger_file,
)
from omnis_wing.absolute.production_config import load_production_config
from omnis_wing.absolute.production_signer import (
    ProductionSignerAdapter,
    compile_keychain_bridge,
)
from omnis_wing.absolute.runtime_attach import build_signer_from_config
from omnis_wing.absolute.signed_policy import load_policy
from omnis_wing.completion.product_disable import load_manifest

from .admission import assert_contract_not_drifted
from .config import (
    PINNED_CADUCEUS_COMMIT,
    PINNED_IDE_CONTRACT,
    PINNED_OMNIS_GATE_COMMIT,
    RealWorkConfigError,
    assert_pinned_runtime_dependencies,
    load_real_work_config,
    service_capability,
)

SCHEMA = "omnis-wing.operator-run-manifest.v1"
SCHEMA_PATH = Path(__file__).resolve().parent / "operator_run_manifest.schema.json"

# Patterns never allowed to appear in operator CLI stdout/stderr.
_CREDENTIAL_LEAK_RE = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9_\-]{8,}"
    r"|Bearer\s+[A-Za-z0-9_\-\.=]+"
    r"|MINIMAX_API_KEY\s*=\s*\S+"
    r"|CADUCEUS_SERVICE_TOKEN\s*=\s*\S+"
    r")"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _scrub_public_text(text: str) -> str:
    """Remove credential substrings and known env secret values from operator output."""
    redacted = _CREDENTIAL_LEAK_RE.sub("[REDACTED]", text)
    for key in (
        "MINIMAX_API_KEY",
        "CADUCEUS_SERVICE_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        secret = (os.environ.get(key) or "").strip()
        if secret and len(secret) >= 8 and secret in redacted:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _require_isolated_profile() -> Path:
    raw_home = (os.environ.get("HERMES_HOME") or "").strip()
    raw_profile = (os.environ.get("OMNIS_WING_PROFILE_HOME") or "").strip()
    if not raw_home or not raw_profile:
        raise RealWorkConfigError("isolated_profile_home_required")
    home = Path(raw_home).expanduser()
    profile = Path(raw_profile).expanduser()
    if not home.is_absolute() or not profile.is_absolute() or home != profile:
        raise RealWorkConfigError("hermes_home_must_equal_omnis_wing_profile_home")
    if home == Path.home() / ".hermes":
        raise RealWorkConfigError("live_default_hermes_home_refused")
    if home.is_symlink():
        raise RealWorkConfigError("profile_home_symlink_refused")
    mkdir_private_tree(home)
    inspect_controlled_dir(home)
    return home


def _must_be_within(child: Path, parent: Path, reason: str) -> Path:
    child = Path(os.path.normpath(str(child.expanduser())))
    try:
        child.relative_to(parent)
    except ValueError as exc:
        raise RealWorkConfigError(reason) from exc
    return child


def _regular_file_from_env(name: str) -> Path:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        raise RealWorkConfigError(f"{name.lower()}_required")
    path = Path(raw).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RealWorkConfigError(f"{name.lower()}_must_be_absolute_regular_file")
    return path


def _git_identity(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
    except Exception as exc:
        raise RealWorkConfigError("wing_tree_identity_unavailable") from exc
    return {"commit": head, "tree": tree, "dirty": dirty}


def _require_clean_wing_identity(identity: Mapping[str, Any]) -> None:
    if identity.get("dirty"):
        raise RealWorkConfigError("wing_tree_tracked_or_untracked_drift")


def _prepare_bridge(cfg, runtime: Path, *, compile_bridge: bool) -> tuple[Path, dict[str, Any]]:
    if cfg.backend != "keychain":
        raise RealWorkConfigError("wave0_requires_keychain_backend")
    expected = runtime / "bin" / "omnis_wing_keychain"
    bridge = cfg.bridge_path or expected
    if compile_bridge:
        if bridge != expected:
            raise RealWorkConfigError("compiled_bridge_must_use_run_owned_path")
        mkdir_private_tree(expected.parent)
        compile_keychain_bridge(expected.parent)
    if bridge.is_symlink() or not bridge.is_file():
        raise RealWorkConfigError("keychain_bridge_missing_run_compile_bridge")
    mode = stat.S_IMODE(bridge.stat().st_mode)
    if not mode & stat.S_IXUSR:
        raise RealWorkConfigError("keychain_bridge_not_executable")
    signer = build_signer_from_config(cfg)
    if not isinstance(signer, ProductionSignerAdapter):
        raise RealWorkConfigError("signer_backend_unavailable")
    status = signer.enrollment_status()
    if not status.get("ready") or not signer.available():
        state = str(status.get("state") or "UNAVAILABLE")
        raise RealWorkConfigError(f"signer_not_enrolled_or_locked:{state}")
    return bridge, {
        "state": status.get("state"),
        "storage_state": status.get("storage_state"),
        "backend": status.get("backend"),
        "key_id": signer.key_id,
        "signature_algorithm": signer.signature_algorithm,
        "public_key_sha256": signer.public_fingerprint(),
    }


def _prepare_state(home: Path, cfg) -> dict[str, Path]:
    runtime = home / "omnis-wing-runtime"
    mkdir_private_tree(runtime)
    inspect_controlled_dir(runtime)
    ledger_dir = _must_be_within(
        cfg.ledger_dir, home, "production_ledger_must_be_inside_isolated_profile"
    )
    wing_ledger = prepare_private_ledger_file(ledger_dir / "wing-production-ledger.jsonl")

    raw_state = (os.environ.get("CADUCEUS_STATE_DIR") or "").strip()
    if not raw_state:
        raise RealWorkConfigError("caduceus_state_dir_required")
    caduceus_state = _must_be_within(
        Path(raw_state).expanduser(), home, "caduceus_state_must_be_inside_isolated_profile"
    )
    mkdir_private_tree(caduceus_state)
    chain = prepare_private_ledger_file(caduceus_state / "chain.jsonl")
    return {"runtime": runtime, "wing_ledger": wing_ledger, "caduceus_chain": chain}


def _route_summary() -> dict[str, Any]:
    manifest = load_manifest()
    bad = [r["route_id"] for r in manifest["routes"] if r.get("state") not in ("GOVERNED", "DISABLED")]
    if bad:
        raise RealWorkConfigError("coverage_contains_non_dogfood_states")
    return {
        "governed": sorted(r["route_id"] for r in manifest["routes"] if r["state"] == "GOVERNED"),
        "disabled": sorted(r["route_id"] for r in manifest["routes"] if r["state"] == "DISABLED"),
        "summary": manifest.get("summary"),
    }


def prepare(*, compile_bridge: bool = False, write_manifest: bool = True) -> dict[str, Any]:
    """Verify and prepare a clean profile.  No Keychain mutation; no model call."""
    home = _require_isolated_profile()
    assert_contract_not_drifted()
    prod = load_production_config(require=True)
    assert prod is not None
    rw = load_real_work_config(require=True)
    assert rw is not None
    gate_root = assert_pinned_runtime_dependencies(rw)
    token = service_capability(rw)  # availability/shape only; never serialized
    policy = load_policy()
    lanes = _regular_file_from_env("CADUCEUS_LANES")
    state = _prepare_state(home, prod)
    bridge, signer = _prepare_bridge(prod, state["runtime"], compile_bridge=compile_bridge)
    wing_root = Path(__file__).resolve().parents[3]
    identity = _git_identity(wing_root)
    _require_clean_wing_identity(identity)

    manifest = {
        "schema": SCHEMA,
        "boundary": "selected ordinary WING chat + buffered stream through local CADUCEUS",
        "pins": {
            "wing": identity,
            "caduceus": PINNED_CADUCEUS_COMMIT,
            "omnis_gate": PINNED_OMNIS_GATE_COMMIT,
            "ide_contract": PINNED_IDE_CONTRACT,
        },
        "profile": {
            "home": str(home),
            "runtime_mode": "0700",
            "state_files_mode": "0600",
        },
        "signer": signer,
        "policy": {
            "mode": policy.mode,
            "version": policy.policy_version,
            "digest": policy.policy_digest,
            "key_id": policy.key_id,
            "require_remote_anchor": policy.require_remote_anchor,
        },
        "configuration": {
            "production_config_sha256": _sha256(Path(prod.source)),
            "real_work_config_sha256": _sha256(Path(rw.source)),
            "caduceus_lanes_sha256": _sha256(lanes),
            "keychain_bridge_sha256": _sha256(bridge),
            "caduceus_root": str(rw.caduceus_root),
            "omnis_gate_root": str(gate_root),
            "caduceus_base": rw.caduceus_base,
            "caduceus_instance_id": rw.caduceus_instance_id,
            "target": rw.public_dict()["target"],
        },
        "initial_state": {
            "wing_ledger_sha256": _sha256(state["wing_ledger"]),
            "caduceus_chain_sha256": _sha256(state["caduceus_chain"]),
        },
        "routes": _route_summary(),
        "non_claims": [
            "No provider request was made by this workflow.",
            "No Keychain enrollment, rotation, deletion, or export occurred.",
            "This does not claim workstation-wide DLP or every WING route governed.",
        ],
    }
    raw = _canonical_bytes(manifest)
    for secret in (token, os.environ.get("MINIMAX_API_KEY") or ""):
        if secret and secret.encode("utf-8") in raw:
            raise RealWorkConfigError("credential_material_in_run_manifest")
    digest = hashlib.sha256(raw).hexdigest()
    path = state["runtime"] / "manifests" / f"run-{digest}.json"
    if write_manifest:
        mkdir_private_tree(path.parent)
        if path.exists() or path.is_symlink():
            inspect_controlled_file(path)
            if path.read_bytes() != raw:
                raise RealWorkConfigError("content_addressed_manifest_collision")
        else:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(raw)
        inspect_controlled_file(path)
    return {
        "state": "READY",
        "manifest": str(path),
        "manifest_sha256": digest,
        "signer_state": signer["state"],
        "provider_calls": 0,
        "keychain_mutations": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnis-wing-operator")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser(
        "verify",
        aliases=("verify-setup",),
        help="prepare/verify isolated state; no provider call",
    )
    verify.add_argument("--compile-bridge", action="store_true")
    sub.add_parser("start", help="verify setup, start local CADUCEUS, run cold preflight")
    sub.add_parser("status", help="verify setup and read local CADUCEUS health")
    sub.add_parser("stop", help="stop only the process owned by this profile")
    args = parser.parse_args(argv)
    try:
        if args.command in ("verify", "verify-setup"):
            result = prepare(compile_bridge=bool(getattr(args, "compile_bridge", False)))
        elif args.command == "start":
            result = {"setup": prepare(), "service": _start_and_preflight()}
        elif args.command == "status":
            from .launcher import status

            result = {"setup": prepare(), "service": status()}
        else:
            from .launcher import stop_owned_service

            result = stop_owned_service()
    except Exception as exc:
        payload = _scrub_public_text(
            json.dumps(
                {"state": "REFUSED", "reason": str(exc), "type": type(exc).__name__},
                sort_keys=True,
            )
        )
        print(payload, file=sys.stderr)
        return 2
    text = _scrub_public_text(json.dumps(result, sort_keys=True, indent=2))
    if _CREDENTIAL_LEAK_RE.search(text):
        print(
            json.dumps(
                {
                    "state": "REFUSED",
                    "reason": "credential_pattern_in_operator_output",
                    "type": "RealWorkConfigError",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(text)
    return 0


def _start_and_preflight() -> dict[str, Any]:
    from .launcher import cold_preflight, ensure_service, owned_service_status

    service = ensure_service()
    return {
        "service": service,
        "preflight": cold_preflight(),
        "ownership": owned_service_status() if service.get("started") else {"owned": False},
    }


if __name__ == "__main__":
    raise SystemExit(main())
