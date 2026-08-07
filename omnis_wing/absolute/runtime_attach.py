"""Attach production signer + evidence session to a live agent.

Called from agent init and ensure_agent_wing_context. Never enrolls.
Never falls back to test signer unless OMNIS_WING_SIGNER_MODE=test.

Production mode: config owns signer + ledger. Mutable agent flags/paths are
NOT trusted (wing_runtime_attached / wing_evidence_session / wing_ledger_path
cannot override).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from omnis_wing.absolute.hermes_chat_join import EvidenceSession
from omnis_wing.absolute.ledger_security import LedgerSecurityError
from omnis_wing.absolute.production_config import (
    ProductionConfigError,
    WingProductionConfig,
    load_production_config,
    signer_mode,
)
from omnis_wing.absolute.production_signer import (
    DisposableP256Backend,
    MacOSKeychainBackend,
    ProductionSignerAdapter,
    default_bridge_binary,
)
from omnis_wing.absolute.receipt_spine import EvidenceLedger, UnavailableSigner, make_test_signer


class RuntimeAttachError(RuntimeError):
    pass


def _test_ledger_path(agent: Any = None) -> Path:
    """Test/dogfood only — may honor agent path override."""
    if agent is not None and getattr(agent, "wing_ledger_path", None):
        return Path(agent.wing_ledger_path)
    base = Path(
        os.environ.get("OMNIS_WING_LEDGER_DIR")
        or (Path.home() / ".omnis-wing" / "ledgers")
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "wing-completion-ledger.jsonl"


def _production_ledger_path(cfg: WingProductionConfig) -> Path:
    """Config-owned path only — never agent.wing_ledger_path."""
    return Path(cfg.ledger_dir) / "wing-production-ledger.jsonl"


def build_signer_from_config(cfg: WingProductionConfig) -> ProductionSignerAdapter | UnavailableSigner:
    """Construct signer adapter. Does not enroll. May be unavailable if not enrolled."""
    if cfg.backend == "none":
        return UnavailableSigner()
    if cfg.backend == "disposable_p256":
        work = Path(tempfile.mkdtemp(prefix="wing-p256-rt-"))
        work_env = os.environ.get("OMNIS_WING_P256_WORK_DIR")
        if work_env:
            work = Path(work_env)
            work.mkdir(parents=True, exist_ok=True)
        be = DisposableP256Backend(tag=cfg.tag, work_dir=work)
        priv = work / "p256-priv.pem"
        pub = work / "p256-pub.raw"
        if priv.is_file() and pub.is_file():
            be._priv = priv
            be._raw_pub = pub.read_bytes()
            be.enrolled = True
        return ProductionSignerAdapter(backend=be)
    if cfg.backend == "keychain":
        bridge = cfg.bridge_path or default_bridge_binary()
        if not Path(bridge).is_file():
            return UnavailableSigner()
        try:
            be = MacOSKeychainBackend(tag=cfg.tag, bridge_path=Path(bridge))
            return ProductionSignerAdapter(backend=be)
        except Exception:
            return UnavailableSigner()
    raise ProductionConfigError(f"unsupported_backend:{cfg.backend}")


def _open_private_ledger(path: Path) -> EvidenceLedger:
    return EvidenceLedger(path, require_private=True)


def attach_wing_runtime(agent: Any, *, force: bool = False) -> dict:
    """Attach wing_production_signer + wing_evidence_session on agent.

    Production mode always rebuilds from explicit config (force implied).
    Test mode may short-circuit on wing_runtime_attached unless force=True.
    """
    if agent is None:
        raise RuntimeAttachError("agent_required")

    mode = signer_mode()
    status: dict[str, Any] = {"signer_mode": mode, "attached": False}

    # Production: never trust agent flags — always rebuild from config.
    if mode == "production":
        force = True

    if mode != "production" and not force and getattr(agent, "wing_runtime_attached", False):
        return getattr(agent, "wing_runtime_status", {}) or {"state": "already_attached"}

    if force:
        for attr in (
            "wing_runtime_attached",
            "wing_runtime_status",
            "wing_production_signer",
            "wing_evidence_session",
            "wing_ledger_path",
            "wing_egress_context",
        ):
            if hasattr(agent, attr):
                try:
                    delattr(agent, attr)
                except Exception:
                    setattr(agent, attr, None)

    if mode == "test":
        ledger_path = _test_ledger_path(agent)
        signer = make_test_signer()
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(ledger_path)  # type: ignore[attr-defined]
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(ledger_path, require_private=False)
        )
        status.update(
            {
                "attached": True,
                "backend": "test_ed25519",
                "ready": True,
                "note": "explicit OMNIS_WING_SIGNER_MODE=test",
            }
        )
        agent.wing_runtime_attached = True  # type: ignore[attr-defined]
        agent.wing_runtime_status = status  # type: ignore[attr-defined]
        return status

    # ---- production mode ----
    try:
        cfg = load_production_config(require=False)
    except ProductionConfigError as exc:
        status.update(
            {"attached": True, "ready": False, "error": str(exc), "backend": "unavailable"}
        )
        signer: Any = UnavailableSigner()
        # scratch non-private refuse ledger under temp (test harness only path)
        scratch = Path(tempfile.mkdtemp(prefix="wing-refuse-")) / "refuse.jsonl"
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(scratch)  # type: ignore[attr-defined]
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(scratch, require_private=False)
        )
        agent.wing_runtime_attached = True  # type: ignore[attr-defined]
        agent.wing_runtime_status = status  # type: ignore[attr-defined]
        return status

    if cfg is None:
        status.update(
            {
                "attached": True,
                "ready": False,
                "backend": "unavailable",
                "note": "no_production_config_REFUSE_on_send",
            }
        )
        signer = UnavailableSigner()
        scratch = Path(tempfile.mkdtemp(prefix="wing-refuse-")) / "refuse.jsonl"
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(scratch)  # type: ignore[attr-defined]
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(scratch, require_private=False)
        )
        agent.wing_runtime_attached = True  # type: ignore[attr-defined]
        agent.wing_runtime_status = status  # type: ignore[attr-defined]
        return status

    status["config"] = cfg.as_public_dict()
    signer = build_signer_from_config(cfg)
    ledger_path = _production_ledger_path(cfg)

    ledger: EvidenceLedger | None = None
    ledger_error = None
    try:
        ledger = _open_private_ledger(ledger_path)
    except LedgerSecurityError as exc:
        ledger_error = str(exc)
        # Fail closed: no send — UnavailableSigner
        signer = UnavailableSigner()
        status.update(
            {
                "attached": True,
                "ready": False,
                "backend": "unavailable",
                "ledger_security": ledger_error,
                "note": "unsafe_ledger_REFUSE_on_send",
            }
        )
        scratch = Path(tempfile.mkdtemp(prefix="wing-refuse-")) / "refuse.jsonl"
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(ledger_path)  # report intended path
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(scratch, require_private=False)
        )
        agent.wing_runtime_attached = True  # type: ignore[attr-defined]
        agent.wing_runtime_status = status  # type: ignore[attr-defined]
        return status

    ready = False
    backend_name = cfg.backend
    enroll_state = "NOT_CONFIGURED"
    fp = None
    algo = None
    if isinstance(signer, ProductionSignerAdapter):
        st = signer.enrollment_status()
        enroll_state = st.get("state") or "UNKNOWN"
        ready = bool(st.get("ready")) and signer.available()
        backend_name = st.get("backend") or cfg.backend
        algo = signer.signature_algorithm
        if ready:
            try:
                fp = signer.public_fingerprint()
            except Exception:
                fp = None
    else:
        enroll_state = "UNAVAILABLE"
        ready = False
        backend_name = "unavailable"

    status.update(
        {
            "attached": True,
            "ready": ready,
            "backend": backend_name,
            "enrollment_state": enroll_state,
            "public_key_sha256": fp,
            "signature_algorithm": algo,
            "tag": cfg.tag,
            "ledger": str(ledger_path),
            "ledger_private": True,
        }
    )

    agent.wing_production_signer = signer  # type: ignore[attr-defined]
    agent.wing_ledger_path = str(ledger_path)  # type: ignore[attr-defined]
    agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
        signer=signer, ledger=ledger
    )
    agent.wing_runtime_attached = True  # type: ignore[attr-defined]
    agent.wing_runtime_status = status  # type: ignore[attr-defined]
    return status


def ensure_agent_production_runtime(agent: Any) -> dict:
    """Attach for dispatch. Production always rebuilds from config (no agent flag trust)."""
    if signer_mode() == "production":
        return attach_wing_runtime(agent, force=True)
    return attach_wing_runtime(agent, force=False)
