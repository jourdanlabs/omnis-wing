"""Deterministic local content inspection for OMNIS WING R1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .envelope import OutboundEnvelope, SourceProvenance

# Low-entropy markers used in tests — receipts must not echo cleartext or bare sha256 of these.
PLANTED_SECRET_MARKERS = (
    "WING_R1_PLANTED_SECRET_MARKER_DO_NOT_LEAK",
    "AKIATESTKEYEXAMPLE0000",
)

PRIVATE_KEY_RE = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
TOKEN_RE = re.compile(
    rb"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*[\'\"]?[A-Za-z0-9_\-]{16,}"
)


@dataclass(frozen=True)
class ScanFinding:
    code: str
    message: str
    finding_id: str  # keyed correlation — never the secret itself


@dataclass(frozen=True)
class ScanResult:
    ok: bool
    findings: tuple
    error: Optional[str] = None


def _finding(code: str, message: str, index: int) -> ScanFinding:
    return ScanFinding(code=code, message=message, finding_id=f"f-{index:04d}")


def scan_payload_bytes(payload: bytes) -> ScanResult:
    findings: List[ScanFinding] = []
    i = 0
    if PRIVATE_KEY_RE.search(payload):
        findings.append(_finding("PRIVATE_KEY", "private key material present", i))
        i += 1
    for marker in PLANTED_SECRET_MARKERS:
        if marker.encode("utf-8") in payload:
            findings.append(_finding("PLANTED_SECRET", "operator secret marker present", i))
            i += 1
    if TOKEN_RE.search(payload):
        findings.append(_finding("SECRET_ASSIGNMENT", "secret-shaped assignment present", i))
        i += 1
    return ScanResult(ok=len(findings) == 0, findings=tuple(findings))


def scan_envelope(
    envelope: OutboundEnvelope,
    *,
    inject_failure: bool = False,
) -> ScanResult:
    if inject_failure:
        return ScanResult(ok=False, findings=(), error="scanner_exception_injected")
    try:
        return scan_payload_bytes(envelope.payload_bytes)
    except Exception as exc:  # noqa: BLE001
        return ScanResult(
            ok=False,
            findings=(),
            error=f"scanner_exception:{type(exc).__name__}",
        )


def source_policy_violations(
    sources: Sequence[SourceProvenance],
    require_provenance: bool,
) -> List[str]:
    codes: List[str] = []
    if require_provenance and not sources:
        codes.append("MISSING_SOURCE_PROVENANCE")
        return codes
    for s in sources:
        if require_provenance:
            if not s.content_digest or len(s.content_digest) < 32:
                codes.append("INVALID_SOURCE_DIGEST")
            if s.classification in ("unknown", ""):
                codes.append("UNKNOWN_SOURCE_CLASSIFICATION")
        if s.classification == "credential":
            codes.append("CREDENTIAL_SOURCE")
    return codes
