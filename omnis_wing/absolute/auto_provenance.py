"""Automatic workspace provenance — Captain does not tag modes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.hermes_chat_join import EvidenceSession, WingEgressContext
from omnis_wing.absolute.receipt_spine import EvidenceLedger, UnavailableSigner, make_test_signer

_DEFAULT_PROTECTED_NAME_MARKERS = (
    "chamber",
    "jourdanlabs",
    "omnis",
    "pan-cc",
    "projects",
)


def workspace_root() -> Path:
    env = os.environ.get("OMNIS_WING_WORKSPACE") or os.environ.get("HERMES_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def classify_workspace(root: Path) -> str:
    force = os.environ.get("OMNIS_WING_FORCE_CLASSIFICATION")
    if force in ("generic", "project", "protected"):
        return force
    name = root.name.lower()
    parts = {p.lower() for p in root.parts}
    if any(m in name or m in parts for m in _DEFAULT_PROTECTED_NAME_MARKERS):
        return "project"
    return "generic"


def build_auto_sources(payload_hint: str = "", body: dict | None = None) -> tuple[SourceProvenance, ...]:
    """R5: payload/body is the authority. Workspace path is never sole permit basis."""
    from omnis_wing.absolute.payload_policy import analyze_body, analyze_payload_bytes, classify_bytes

    if body is not None and isinstance(body, dict):
        sources, _ = analyze_body(body)
        return sources
    if payload_hint:
        # try parse as json body first
        import json as _json
        try:
            obj = _json.loads(payload_hint)
            if isinstance(obj, dict):
                sources, _ = analyze_body(obj)
                return sources
        except Exception:
            pass
        sources, _ = analyze_payload_bytes(payload_hint.encode("utf-8", errors="replace"))
        return sources
    # No body at all — unknown provenance (fail closed at evaluate)
    f = classify_bytes(b"", "missing_payload")
    return (
        SourceProvenance(
            path="payload:missing",
            content_digest=f.digest,
            classification="unknown",
            protected_root=True,
            crown_jewel=False,
            byte_range=None,
            whole_content=True,
        ),
    )


def _default_ledger_path() -> Path:
    base = Path(
        os.environ.get("OMNIS_WING_LEDGER_DIR")
        or (Path.home() / ".omnis-wing" / "ledgers")
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "wing-completion-ledger.jsonl"


def resolve_evidence_session(agent=None) -> EvidenceSession:
    """Resolve evidence session for the selected path.

    Product default: production signer required (agent.wing_production_signer or
    explicitly configured production backend). Disposable test signer is **opt-in
    only** via OMNIS_WING_SIGNER_MODE=test (harness). Missing production signer
    → UnavailableSigner → REFUSE_POLICY_INVALID before provider call.
    """
    # Install side-door product disables on every evidence resolution (startup path)
    from omnis_wing.completion.side_doors import ensure_side_doors_armed

    ensure_side_doors_armed()

    if agent is not None:
        from omnis_wing.absolute.runtime_attach import ensure_agent_production_runtime
        from omnis_wing.absolute.production_config import signer_mode

        ensure_agent_production_runtime(agent)
        # Production: session always comes from attach (config-owned). Never keep a
        # pre-planted agent session/path that bypassed attach.
        existing = getattr(agent, "wing_evidence_session", None)
        if existing is not None:
            return existing
        if signer_mode() == "production":
            # attach failed to set session — fail closed
            return EvidenceSession(signer=UnavailableSigner(), ledger=EvidenceLedger(_default_ledger_path()))
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

    ledger = EvidenceLedger(_default_ledger_path())
    mode = (os.environ.get("OMNIS_WING_SIGNER_MODE") or "production").strip().lower()

    if mode == "test":
        # Explicit harness opt-in only
        return EvidenceSession(signer=make_test_signer(), ledger=ledger)

    # Product default — fail closed without production signer
    return EvidenceSession(signer=UnavailableSigner(), ledger=ledger)


def auto_wing_context(agent=None, payload_hint: str = "", body: dict | None = None) -> WingEgressContext:
    sources = build_auto_sources(payload_hint, body=body)
    evidence = resolve_evidence_session(agent)
    return WingEgressContext(sources=sources, evidence=evidence)


def ensure_agent_wing_context(agent, api_kwargs: dict | None = None) -> WingEgressContext:
    """Attach auto context if missing — no Captain-sensitive mode switch.

    Explicit context (including empty sources) is preserved.
    """
    from omnis_wing.completion.side_doors import ensure_side_doors_armed

    ensure_side_doors_armed()

    ctx = getattr(agent, "wing_egress_context", None)
    if ctx is not None:
        if getattr(ctx, "evidence", None) is None:
            ctx.evidence = resolve_evidence_session(agent)
        return ctx
    hint = ""
    if api_kwargs:
        import json as _json

        try:
            hint = _json.dumps(
                api_kwargs.get("messages") or api_kwargs, default=str
            )[:2000]
        except Exception:
            hint = str(type(api_kwargs))
    body = api_kwargs if isinstance(api_kwargs, dict) else None
    ctx = auto_wing_context(agent, payload_hint=hint, body=body)
    try:
        agent.wing_egress_context = ctx
    except Exception:
        pass
    return ctx
