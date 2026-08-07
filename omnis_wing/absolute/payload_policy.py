"""R5 automatic source/policy pipeline — payload authority, not path theater.

Classifies outbound content from the actual request body fields.
Never requires a sensitive-mode switch. Never puts raw secrets into receipts.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS, PRIVATE_KEY_RE, TOKEN_RE

# Content signals — NOT workspace directory names as sole authority
_PROJECT_PATH_RE = re.compile(
    rb"(?i)(?:/Users/|/home/|\\\\|chamber|jourdanlabs|omnis-wing|pan-cc|"
    rb"projects/omnis|SOUL\.md|MEMORY\.md|\.hermes/profiles)"
)
_SOURCE_CODE_RE = re.compile(
    rb"(?i)(?:def |class |import |from \w+ import |function |const |let |var |"
    rb"#!/usr/bin|package\.json|Cargo\.toml|pyproject\.toml)"
)
_PROTECTED_MARKER_RE = re.compile(
    rb"(?i)(?:CROWN_JEWEL|PROTECTED_SOURCE|REDACT_REQUIRED|"
    rb"OMNIS_WING_PROTECTED_FRAGMENT)"
)
_FIELD_PATH_SEP = "."

# Fields that are operator-generic by nature when short
_GENERIC_HINT_FIELDS = frozenset(
    {"model", "temperature", "top_p", "n", "stream", "max_tokens", "max_completion_tokens"}
)


@dataclass(frozen=True)
class FieldFragment:
    field_path: str
    digest: str
    classification: str  # generic|project|protected|credential|unknown
    protected_root: bool
    crown_jewel: bool


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iter_string_fields(obj: Any, prefix: str = "") -> Iterable[Tuple[str, str]]:
    """Yield (field_path, text) for every string-bearing leaf in body."""
    if obj is None:
        return
    if isinstance(obj, str):
        yield prefix or "root", obj
        return
    if isinstance(obj, (bytes, bytearray)):
        try:
            yield prefix or "root", bytes(obj).decode("utf-8", errors="replace")
        except Exception:
            yield prefix or "root", ""
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("__wing"):
                continue
            p = f"{prefix}.{k}" if prefix else str(k)
            yield from iter_string_fields(v, p)
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            yield from iter_string_fields(v, p)
        return
    # numbers/bools ignored for classification


def classify_bytes(data: bytes, field_path: str = "") -> FieldFragment:
    """Classify one fragment from content signals."""
    d = _digest(data)
    if not data or not data.strip():
        empty_force = (os.environ.get("OMNIS_WING_FORCE_CLASSIFICATION") or "").strip().lower()
        if empty_force in ("generic", "project", "protected", "unknown"):
            return FieldFragment(field_path or "payload", d, empty_force, empty_force!="generic", False)
        return FieldFragment(field_path or "payload", d, "generic", False, False)

    # Credentials first — never overridden by force hook
    if PRIVATE_KEY_RE.search(data):
        return FieldFragment(field_path or "payload", d, "credential", True, False)
    for m in PLANTED_SECRET_MARKERS:
        if m.encode() in data:
            return FieldFragment(field_path or "payload", d, "credential", True, False)
    if TOKEN_RE.search(data):
        return FieldFragment(field_path or "payload", d, "credential", True, False)

    # Force hook for cold tests only (non-secret content)
    force = (os.environ.get("OMNIS_WING_FORCE_CLASSIFICATION") or "").strip().lower()
    if force in ("generic", "project", "protected", "unknown", "credential"):
        return FieldFragment(
            field_path=field_path or "payload",
            digest=d,
            classification=force,
            protected_root=force in ("project", "protected", "unknown", "credential"),
            crown_jewel=force == "protected" and b"CROWN" in data.upper(),
        )

    if _PROTECTED_MARKER_RE.search(data):
        return FieldFragment(field_path or "payload", d, "protected", True, True)

    projectish = bool(_PROJECT_PATH_RE.search(data) or _SOURCE_CODE_RE.search(data))
    # Long base64-looking blobs with no language → unknown
    if len(data) > 4000 and not projectish:
        # high non-text ratio
        sample = data[:2000]
        printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
        if printable / max(len(sample), 1) < 0.7:
            return FieldFragment(field_path or "payload", d, "unknown", True, False)

    if projectish:
        return FieldFragment(
            field_path=field_path or "payload",
            digest=d,
            classification="project",
            protected_root=True,
            crown_jewel=False,
        )

    # Default: operator text / generic chat
    return FieldFragment(
        field_path=field_path or "payload",
        digest=d,
        classification="generic",
        protected_root=False,
        crown_jewel=False,
    )


def analyze_body(body: dict) -> Tuple[Tuple[SourceProvenance, ...], Tuple[FieldFragment, ...]]:
    """Full-body analysis. Every string field contributes provenance."""
    frags: List[FieldFragment] = []
    for path, text in iter_string_fields(body):
        raw = text.encode("utf-8", errors="surrogateescape")
        frags.append(classify_bytes(raw, path))

    if not frags:
        # empty body → unknown provenance (conservative)
        empty = classify_bytes(b"", "empty_body")
        # empty is generic; mark as unknown for missing content policy when require
        frags = [
            FieldFragment("empty_body", _digest(b""), "unknown", True, False)
        ]

    sources: List[SourceProvenance] = []
    for f in frags:
        sources.append(
            SourceProvenance(
                path=f"payload:{f.field_path}",
                content_digest=f.digest,
                classification=f.classification,
                protected_root=f.protected_root,
                crown_jewel=f.crown_jewel,
                byte_range=None,
                whole_content=True,
            )
        )
    return tuple(sources), tuple(frags)


def analyze_payload_bytes(payload: bytes) -> Tuple[Tuple[SourceProvenance, ...], Tuple[FieldFragment, ...]]:
    """When only canonical bytes exist, try JSON parse then whole-blob classify."""
    import json

    try:
        obj = json.loads(payload.decode("utf-8"))
        if isinstance(obj, dict):
            return analyze_body(obj)
    except Exception:
        pass
    f = classify_bytes(payload, "payload_bytes")
    src = SourceProvenance(
        path="payload:payload_bytes",
        content_digest=f.digest,
        classification=f.classification,
        protected_root=f.protected_root,
        crown_jewel=f.crown_jewel,
        byte_range=None,
        whole_content=True,
    )
    return (src,), (f,)


def worst_classification(sources: Sequence[SourceProvenance]) -> str:
    order = {"credential": 5, "protected": 4, "project": 3, "unknown": 2, "generic": 1, "": 0}
    worst = "generic"
    for s in sources:
        if order.get(s.classification, 0) > order.get(worst, 0):
            worst = s.classification
    return worst


def hygiene_check_text(text: str) -> bool:
    """Return True if text is clean of planted secret markers (for receipts/health)."""
    if not text:
        return True
    for m in PLANTED_SECRET_MARKERS:
        if m in text:
            return False
    return "BEGIN PRIVATE KEY" not in text and "BEGIN RSA PRIVATE KEY" not in text
