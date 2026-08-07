"""ABSOLUTE-shaped immutable OutboundEnvelope for OMNIS WING R1."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal, Optional, Sequence, Tuple
import json
import uuid

Modality = Literal[
    "chat", "image", "embedding", "audio", "file", "batch", "tool", "mcp", "health"
]
Scheme = Literal["https", "http"]
Classification = Literal[
    "generic",
    "project",
    "protected",
    "credential",
    "unknown",
]

POLICY_VERSION = "omnis-wing.absolute-r1.v1"
COVERAGE_CLASS = "AI_EGRESS_GOVERNED_R1_SEAM_ONLY"


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class SourceProvenance:
    path: str
    content_digest: str
    classification: str
    protected_root: bool
    crown_jewel: bool
    byte_range: Optional[Tuple[int, int]]  # None means whole content
    whole_content: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_digest": self.content_digest,
            "classification": self.classification,
            "protected_root": self.protected_root,
            "crown_jewel": self.crown_jewel,
            "byte_range": list(self.byte_range) if self.byte_range is not None else None,
            "whole_content": self.whole_content,
        }


@dataclass(frozen=True)
class IntendedDestination:
    provider: str
    scheme: str
    hostname: str
    port: int
    path_class: str
    residency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "scheme": self.scheme,
            "hostname": self.hostname,
            "port": self.port,
            "path_class": self.path_class,
            "residency": self.residency,
        }

    def binding_tuple(self) -> tuple:
        return (
            self.provider,
            self.scheme,
            self.hostname,
            int(self.port),
            self.path_class,
            self.residency,
        )


@dataclass(frozen=True)
class OutboundEnvelope:
    envelope_id: str
    modality: str
    lane: str
    payload_bytes: bytes
    payload_digest: str
    sources: Tuple[SourceProvenance, ...]
    intended_destination: IntendedDestination
    policy_version: str
    coverage_class: str

    @staticmethod
    def create(
        *,
        modality: str,
        lane: str,
        payload: str | bytes,
        sources: Sequence[SourceProvenance],
        destination: IntendedDestination,
        envelope_id: Optional[str] = None,
        policy_version: str = POLICY_VERSION,
        coverage_class: str = COVERAGE_CLASS,
    ) -> "OutboundEnvelope":
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = bytes(payload)
        digest = _sha256_bytes(payload_bytes)
        return OutboundEnvelope(
            envelope_id=envelope_id or str(uuid.uuid4()),
            modality=modality,
            lane=lane,
            payload_bytes=payload_bytes,
            payload_digest=digest,
            sources=tuple(sources),
            intended_destination=destination,
            policy_version=policy_version,
            coverage_class=coverage_class,
        )

    def canonical_eval_view(self) -> dict[str, Any]:
        """Stable structure the evaluator/scanner bind to (payload by digest + bytes)."""
        return {
            "envelope_id": self.envelope_id,
            "modality": self.modality,
            "lane": self.lane,
            "payload_digest": self.payload_digest,
            "payload_utf8": self.payload_bytes.decode("utf-8", errors="surrogateescape"),
            "sources": [s.to_dict() for s in self.sources],
            "intended_destination": self.intended_destination.to_dict(),
            "policy_version": self.policy_version,
            "coverage_class": self.coverage_class,
        }

    def envelope_digest(self) -> str:
        view = self.canonical_eval_view()
        # digest over structure excluding raw embedding of payload twice: use payload_digest only
        wire = {
            **view,
            "payload_utf8": None,
            "payload_digest": self.payload_digest,
            "payload_len": len(self.payload_bytes),
        }
        blob = json.dumps(wire, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return _sha256_bytes(blob)
