"""Automatic workspace provenance — Captain does not tag modes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.hermes_chat_join import EvidenceSession, WingEgressContext
from omnis_wing.absolute.production_signer import (
    DisposableTestBackend,
    ProductionSignerAdapter,
)
from omnis_wing.absolute.receipt_spine import EvidenceLedger, make_test_signer

# Roots treated as protected/project when payload originates under them
_DEFAULT_PROTECTED_NAME_MARKERS = (
    "chamber",
    "jourdanlabs",
    "omnis",
    "pan-cc",
    "projects",
)


def _digest_path(p: Path) -> str:
    try:
        data = p.read_bytes() if p.is_file() else str(p.resolve()).encode()
    except Exception:
        data = str(p).encode()
    return hashlib.sha256(data).hexdigest()


def workspace_root() -> Path:
    env = os.environ.get("OMNIS_WING_WORKSPACE") or os.environ.get("HERMES_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def classify_workspace(root: Path) -> str:
    """Derive classification without Captain choosing a mode."""
    force = os.environ.get("OMNIS_WING_FORCE_CLASSIFICATION")
    if force in ("generic", "project", "protected"):
        return force
    name = root.name.lower()
    parts = {p.lower() for p in root.parts}
    if any(m in name or m in parts for m in _DEFAULT_PROTECTED_NAME_MARKERS):
        # Working inside JL/project trees defaults to project classification
        return "project"
    return "generic"


def build_auto_sources(payload_hint: str = "") -> tuple[SourceProvenance, ...]:
    root = workspace_root()
    classification = classify_workspace(root)
    content = payload_hint or f"workspace:{root}"
    d = hashlib.sha256(content.encode()).hexdigest()
    src = SourceProvenance(
        path=str(root / ".omnis-wing-workspace"),
        content_digest=d,
        classification=classification,
        protected_root=classification in ("project", "protected"),
        crown_jewel=False,
        byte_range=None,
        whole_content=True,
    )
    return (src,)


def _default_ledger_path() -> Path:
    base = Path(os.environ.get("OMNIS_WING_LEDGER_DIR") or (Path.home() / ".omnis-wing" / "ledgers"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "wing-completion-ledger.jsonl"


def resolve_evidence_session(agent=None) -> EvidenceSession:
    """Explicit production signer if agent provides one; else cold-safe test signer.

    Production enrollment remains operator-only. Missing production key in
    production mode refuses at sign time (available=False).
    """
    if agent is not None:
        existing = getattr(agent, "wing_evidence_session", None)
        if existing is not None:
            return existing
        signer = getattr(agent, "wing_production_signer", None)
        if signer is not None:
            ledger = EvidenceLedger(
                Path(getattr(agent, "wing_ledger_path", None) or _default_ledger_path())
            )
            sess = EvidenceSession(signer=signer, ledger=ledger)
            try:
                agent.wing_evidence_session = sess
            except Exception:
                pass
            return sess

    # Disposable cold / default fork path: test signer (not Keychain)
    mode = os.environ.get("OMNIS_WING_SIGNER_MODE", "test")
    ledger = EvidenceLedger(_default_ledger_path())
    if mode == "production":
        # Caller must set agent.wing_production_signer; bare production mode without
        # signer → unavailable session via empty sources path handled upstream
        from omnis_wing.absolute.receipt_spine import UnavailableSigner

        return EvidenceSession(signer=UnavailableSigner(), ledger=ledger)

    return EvidenceSession(signer=make_test_signer(), ledger=ledger)


def auto_wing_context(agent=None, payload_hint: str = "") -> WingEgressContext:
    sources = build_auto_sources(payload_hint)
    evidence = resolve_evidence_session(agent)
    return WingEgressContext(sources=sources, evidence=evidence)


def ensure_agent_wing_context(agent, api_kwargs: dict | None = None) -> WingEgressContext:
    """Attach auto context if missing — no Captain-sensitive mode switch.

    Explicit context (including empty sources) is preserved so SOURCE_POLICY
    refusals remain testable and intentional empty provenance is not overwritten.
    """
    ctx = getattr(agent, "wing_egress_context", None)
    if ctx is not None:
        if getattr(ctx, "evidence", None) is None:
            ctx.evidence = resolve_evidence_session(agent)
        return ctx
    hint = ""
    if api_kwargs:
        import json as _json

        try:
            hint = _json.dumps(api_kwargs.get("messages") or api_kwargs, default=str)[:2000]
        except Exception:
            hint = str(type(api_kwargs))
    ctx = auto_wing_context(agent, payload_hint=hint)
    try:
        agent.wing_egress_context = ctx
    except Exception:
        pass
    return ctx
