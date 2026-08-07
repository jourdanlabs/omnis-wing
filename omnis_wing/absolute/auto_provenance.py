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
    try:
        from omnis_wing.completion.side_doors import install_side_door_guards

        install_side_door_guards()
    except Exception:
        pass

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

    ledger = EvidenceLedger(_default_ledger_path())
    mode = (os.environ.get("OMNIS_WING_SIGNER_MODE") or "production").strip().lower()

    if mode == "test":
        # Explicit harness opt-in only
        return EvidenceSession(signer=make_test_signer(), ledger=ledger)

    # Product default — fail closed without production signer
    return EvidenceSession(signer=UnavailableSigner(), ledger=ledger)


def auto_wing_context(agent=None, payload_hint: str = "") -> WingEgressContext:
    sources = build_auto_sources(payload_hint)
    evidence = resolve_evidence_session(agent)
    return WingEgressContext(sources=sources, evidence=evidence)


def ensure_agent_wing_context(agent, api_kwargs: dict | None = None) -> WingEgressContext:
    """Attach auto context if missing — no Captain-sensitive mode switch.

    Explicit context (including empty sources) is preserved.
    """
    try:
        from omnis_wing.completion.side_doors import install_side_door_guards

        install_side_door_guards()
    except Exception:
        pass

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
    ctx = auto_wing_context(agent, payload_hint=hint)
    try:
        agent.wing_egress_context = ctx
    except Exception:
        pass
    return ctx
