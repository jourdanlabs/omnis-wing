"""M4 REDACT — local deterministic preview only.

A redaction action sends nothing. Confirmed send requires a fresh user request
with a new envelope ID and full re-scan. No path mutates-and-forwards original.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS, PRIVATE_KEY_RE, TOKEN_RE
from omnis_wing.absolute.source_taint import classify_content_bytes, TaintRecord

_REDACTIONS = [
    (PRIVATE_KEY_RE, "[REDACTED_PRIVATE_KEY]"),
    (re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"), b"[REDACTED_AWS_KEY]"),
    (TOKEN_RE, b"[REDACTED_SECRET_ASSIGNMENT]"),
    (re.compile(rb"(?i)(?:postgres(?:ql)?|mysql|mongodb)://[^\s\"']+"), b"[REDACTED_CONN]"),
]


@dataclass(frozen=True)
class RedactionPreview:
    preview_id: str
    original_digest: str
    redacted_text: str
    redacted_digest: str
    reasons: Tuple[str, ...]
    parent_taint: str
    # never ships
    sends_nothing: bool = True

    def to_public_dict(self) -> dict:
        return {
            "preview_id": self.preview_id,
            "original_digest": self.original_digest,
            "redacted_digest": self.redacted_digest,
            "reasons": list(self.reasons),
            "parent_taint": self.parent_taint,
            "sends_nothing": True,
            "note": "REDACT is local-only; confirm creates a NEW envelope and re-scan",
        }


def redact_local(text: str, *, parent: Optional[TaintRecord] = None) -> RedactionPreview:
    raw = text.encode("utf-8", errors="replace")
    orig_d = hashlib.sha256(raw).hexdigest()
    parent = parent or classify_content_bytes(raw)
    out = raw
    reasons: List[str] = []
    for m in PLANTED_SECRET_MARKERS:
        b = m.encode()
        if b in out:
            out = out.replace(b, b"[REDACTED_PLANTED_MARKER]")
            reasons.append("planted_secret_marker")
    for cre, repl in _REDACTIONS:
        if isinstance(repl, str):
            repl_b = repl.encode()
        else:
            repl_b = repl
        if cre.search(out):
            out = cre.sub(repl_b, out)
            reasons.append(cre.pattern.decode("utf-8", errors="replace")[:40])
    if parent.classification in ("protected", "project", "credential") and not reasons:
        # refuse-quality: whole-body redaction when we can't faithfully strip
        reasons.append(f"whole_body_redact:{parent.classification}")
        out = f"[REDACTED_UNSAFE_CONTENT classification={parent.classification}]".encode()
    red_text = out.decode("utf-8", errors="replace")
    return RedactionPreview(
        preview_id=str(uuid.uuid4()),
        original_digest=orig_d,
        redacted_text=red_text,
        redacted_digest=hashlib.sha256(out).hexdigest(),
        reasons=tuple(reasons) or ("noop_clean",),
        parent_taint=parent.classification,
    )


def confirm_redacted_send_body(preview: RedactionPreview, redacted_user_text: str) -> dict:
    """Build a NEW request body for a fresh envelope — caller must re-run full gate.

    Does not transmit. Does not reuse original envelope id.
    """
    if hashlib.sha256(redacted_user_text.encode()).hexdigest() != preview.redacted_digest:
        # allow user edits but mark as new content
        pass
    return {
        "model": "pending",
        "messages": [{"role": "user", "content": redacted_user_text}],
        "__wing_redact_preview_id": preview.preview_id,
        "__wing_new_envelope_required": True,
    }
