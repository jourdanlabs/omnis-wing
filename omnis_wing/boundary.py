"""OMNIS WING v0 — fork-admission host boundary.

Minimal invasive seam: decide whether an action envelope may reach an
injected provider. No network. No credentials. Not TERMINUS-complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Optional, Protocol, Sequence
import hashlib
import json

CONTRACT_PROTOCOL_VERSION = "omnis-wing.admission.v0"
PRODUCT_NAME = "OMNIS WING"

PrivacyProfile = Literal["protected", "generic"]
Residency = str  # e.g. "CN", "US", "EU", "LOCAL"
DecisionCode = Literal["REFUSED_BEFORE_SEND", "SENT"]


class SourceKind(str, Enum):
    PROJECT = "project"
    GENERIC = "generic"


@dataclass(frozen=True)
class SourceRef:
    kind: str  # "project" | "generic"
    digest: Optional[str] = None  # sha-256 hex when provenance is known
    path: Optional[str] = None  # optional label only; never used for allow


@dataclass(frozen=True)
class Route:
    residency: str
    provider: str
    modality: str  # e.g. "chat", "embed"


@dataclass(frozen=True)
class Action:
    kind: str
    digest: str


@dataclass(frozen=True)
class ActionEnvelope:
    project_id: str
    spec_digest: str
    privacy_profile: str
    source_refs: tuple[SourceRef, ...]
    route: Route
    action: Action

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ActionEnvelope":
        refs = tuple(
            SourceRef(
                kind=str(r.get("kind", "")),
                digest=r.get("digest"),
                path=r.get("path"),
            )
            for r in (data.get("sourceRefs") or data.get("source_refs") or [])
        )
        route_raw = data.get("route") or {}
        action_raw = data.get("action") or {}
        return ActionEnvelope(
            project_id=str(data.get("projectId") or data.get("project_id") or ""),
            spec_digest=str(data.get("specDigest") or data.get("spec_digest") or ""),
            privacy_profile=str(
                data.get("privacyProfile") or data.get("privacy_profile") or ""
            ),
            source_refs=refs,
            route=Route(
                residency=str(route_raw.get("residency") or ""),
                provider=str(route_raw.get("provider") or ""),
                modality=str(route_raw.get("modality") or ""),
            ),
            action=Action(
                kind=str(action_raw.get("kind") or ""),
                digest=str(action_raw.get("digest") or ""),
            ),
        )


@dataclass
class Receipt:
    """Projection only: REFUSED_BEFORE_SEND or SENT. No flattering outcomes."""

    decision: DecisionCode
    reason_code: str
    envelope_digest: str
    provider_calls: int
    provider_response_digest: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Provider(Protocol):
    """Injected provider surface. Tests supply a stub; production wiring is out of v0 scope."""

    def complete(self, envelope: ActionEnvelope) -> dict[str, Any]:
        ...


@dataclass
class CountingStubProvider:
    """Local fake provider. Records call count; never touches network."""

    calls: int = 0
    last_envelope: Optional[ActionEnvelope] = None
    response_body: dict[str, Any] = field(
        default_factory=lambda: {"ok": True, "stub": True, "tokens": 1}
    )

    def complete(self, envelope: ActionEnvelope) -> dict[str, Any]:
        self.calls += 1
        self.last_envelope = envelope
        return dict(self.response_body)


def envelope_digest(envelope: ActionEnvelope) -> str:
    payload = {
        "project_id": envelope.project_id,
        "spec_digest": envelope.spec_digest,
        "privacy_profile": envelope.privacy_profile,
        "source_refs": [
            {"kind": s.kind, "digest": s.digest, "path": s.path}
            for s in envelope.source_refs
        ],
        "route": {
            "residency": envelope.route.residency,
            "provider": envelope.route.provider,
            "modality": envelope.route.modality,
        },
        "action": {"kind": envelope.action.kind, "digest": envelope.action.digest},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).digest().hex()


def _has_project_source(refs: Sequence[SourceRef]) -> bool:
    return any(r.kind == SourceKind.PROJECT.value for r in refs)


def _missing_project_provenance(refs: Sequence[SourceRef]) -> bool:
    """Protected work requires every project source ref to carry a digest."""
    project_refs = [r for r in refs if r.kind == SourceKind.PROJECT.value]
    if not project_refs:
        # Protected with zero project refs still lacks provenance for project work.
        return True
    return any(not (r.digest and isinstance(r.digest, str) and len(r.digest) >= 32) for r in project_refs)


def _is_cn_route(route: Route) -> bool:
    return route.residency.strip().upper() == "CN"


def evaluate_boundary(envelope: ActionEnvelope) -> tuple[bool, str, str]:
    """
    Return (allowed, reason_code, detail).
    Does not call any provider.
    """
    profile = envelope.privacy_profile.strip().lower()
    if profile not in ("protected", "generic"):
        return False, "INVALID_PRIVACY_PROFILE", f"unknown privacy_profile={envelope.privacy_profile!r}"

    if not envelope.project_id or not envelope.spec_digest or not envelope.action.digest:
        return False, "INVALID_ENVELOPE", "project_id, spec_digest, and action.digest are required"

    if not envelope.route.residency or not envelope.route.provider or not envelope.route.modality:
        return False, "INVALID_ROUTE", "route.residency, provider, and modality are required"

    if profile == "protected":
        # Rule 2: missing source provenance → refuse before send
        if _missing_project_provenance(envelope.source_refs):
            return (
                False,
                "PROTECTED_MISSING_PROVENANCE",
                "protected profile requires project source refs with digests",
            )
        # Rule 1: protected + project source + CN → refuse before send
        if _has_project_source(envelope.source_refs) and _is_cn_route(envelope.route):
            return (
                False,
                "PROTECTED_PROJECT_CN_ROUTE",
                "protected project material cannot use CN residency route",
            )
        # Protected + non-CN with provenance: v0 still does not auto-allow project
        # traffic to external providers. Only the explicit generic path is allowed.
        return (
            False,
            "PROTECTED_NOT_GENERIC_ALLOWLIST",
            "v0 only allows explicitly generic actions with no project source refs",
        )

    # generic
    if _has_project_source(envelope.source_refs):
        return (
            False,
            "GENERIC_WITH_PROJECT_SOURCE",
            "generic profile cannot carry project source refs",
        )
    if _is_cn_route(envelope.route):
        return (
            False,
            "GENERIC_CN_NOT_IN_V0_ALLOWLIST",
            "v0 allowed generic path excludes CN residency",
        )
    # Rule 3: explicitly generic, no project source, declared allowed route
    return True, "GENERIC_ALLOWED", "generic action on allowed non-CN route"


def decide_and_maybe_call(envelope: ActionEnvelope, provider: Provider) -> Receipt:
    """
    Single host-boundary entrypoint.
    Provider is only invoked when evaluate_boundary allows.
    """
    env_d = envelope_digest(envelope)
    allowed, reason, detail = evaluate_boundary(envelope)
    if not allowed:
        return Receipt(
            decision="REFUSED_BEFORE_SEND",
            reason_code=reason,
            envelope_digest=env_d,
            provider_calls=0,
            provider_response_digest=None,
            detail=detail,
        )

    # Only path that may touch the provider.
    response = provider.complete(envelope)
    resp_blob = json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Receipt(
        decision="SENT",
        reason_code=reason,
        envelope_digest=env_d,
        provider_calls=1,
        provider_response_digest=hashlib.sha256(resp_blob).hexdigest(),
        detail=detail,
    )


# Alias used by host wiring docs
run_through_boundary = decide_and_maybe_call
