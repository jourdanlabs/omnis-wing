"""Attach production signer + evidence session to a live agent.

Called from agent init and ensure_agent_wing_context. Never enrolls.
Never falls back to test signer unless OMNIS_WING_SIGNER_MODE=test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from omnis_wing.absolute.hermes_chat_join import EvidenceSession
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


def _ledger_path(cfg: Optional[WingProductionConfig], agent: Any = None) -> Path:
    if agent is not None and getattr(agent, "wing_ledger_path", None):
        return Path(agent.wing_ledger_path)
    if cfg is not None:
        cfg.ledger_dir.mkdir(parents=True, exist_ok=True)
        return cfg.ledger_dir / "wing-production-ledger.jsonl"
    base = Path(os.environ.get("OMNIS_WING_LEDGER_DIR") or (Path.home() / ".omnis-wing" / "ledgers"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "wing-completion-ledger.jsonl"


def build_signer_from_config(cfg: WingProductionConfig) -> ProductionSignerAdapter | UnavailableSigner:
    """Construct signer adapter. Does not enroll. May be unavailable if not enrolled."""
    if cfg.backend == "none":
        return UnavailableSigner()
    if cfg.backend == "disposable_p256":
        # Cold / operator-local disposable only — never Captain tag
        work = Path(tempfile.mkdtemp(prefix="wing-p256-rt-"))
        # Reuse agent-stable work dir if set
        work_env = os.environ.get("OMNIS_WING_P256_WORK_DIR")
        if work_env:
            work = Path(work_env)
            work.mkdir(parents=True, exist_ok=True)
        be = DisposableP256Backend(tag=cfg.tag, work_dir=work)
        # Restore enrollment if key files already present from prior explicit enroll
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
            # Unavailable — do not crash process; agent will refuse sends
            return UnavailableSigner()
        try:
            be = MacOSKeychainBackend(tag=cfg.tag, bridge_path=Path(bridge))
            return ProductionSignerAdapter(backend=be)
        except Exception:
            return UnavailableSigner()
    raise ProductionConfigError(f"unsupported_backend:{cfg.backend}")


def attach_wing_runtime(agent: Any, *, force: bool = False) -> dict:
    """Attach wing_production_signer + wing_evidence_session on agent.

    Returns public status dict (no secrets).
    """
    if agent is None:
        raise RuntimeAttachError("agent_required")

    if not force and getattr(agent, "wing_runtime_attached", False):
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

    mode = signer_mode()
    status: dict[str, Any] = {"signer_mode": mode, "attached": False}

    if mode == "test":
        # Explicit dogfood/harness only
        ledger_path = _ledger_path(None, agent)
        signer = make_test_signer()
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(ledger_path)  # type: ignore[attr-defined]
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(ledger_path)
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

    # production mode — require explicit config to attach real signer;
    # missing config => UnavailableSigner (refuse on send), not test fallback
    try:
        cfg = load_production_config(require=False)
    except ProductionConfigError as exc:
        status.update({"attached": True, "ready": False, "error": str(exc), "backend": "unavailable"})
        signer: Any = UnavailableSigner()
        ledger_path = _ledger_path(None, agent)
        agent.wing_production_signer = signer  # type: ignore[attr-defined]
        agent.wing_ledger_path = str(ledger_path)  # type: ignore[attr-defined]
        agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
            signer=signer, ledger=EvidenceLedger(ledger_path)
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
        ledger_path = _ledger_path(None, agent)
    else:
        status["config"] = cfg.as_public_dict()
        signer = build_signer_from_config(cfg)
        ledger_path = _ledger_path(cfg, agent)
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
            }
        )

    agent.wing_production_signer = signer  # type: ignore[attr-defined]
    agent.wing_ledger_path = str(ledger_path)  # type: ignore[attr-defined]
    agent.wing_evidence_session = EvidenceSession(  # type: ignore[attr-defined]
        signer=signer, ledger=EvidenceLedger(ledger_path)
    )
    agent.wing_runtime_attached = True  # type: ignore[attr-defined]
    agent.wing_runtime_status = status  # type: ignore[attr-defined]
    return status


def ensure_agent_production_runtime(agent: Any) -> dict:
    """Idempotent attach for dispatch path."""
    return attach_wing_runtime(agent, force=False)
