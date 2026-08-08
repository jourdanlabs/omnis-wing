"""M1 complete source-taint graph.

Canonical SourceProvenance at content boundaries. Taint survives
concat/summary/tool-result/system/message construction. Filename is never
required for secret/credential protection.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from omnis_wing.absolute.envelope import SourceProvenance
from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS, PRIVATE_KEY_RE, TOKEN_RE

# Content-based protected signals (filename-independent)
_ENV_ASSIGN_RE = re.compile(
    rb"(?i)(?:^|[\n\r;])\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}=[^\s\n\r]{8,}"
)
_CONN_RE = re.compile(
    rb"(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s\"']+"
)
_AWS_KEY_RE = re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}")
_PEM_RE = PRIVATE_KEY_RE
_CROWN_RE = re.compile(rb"(?i)OMNIS_WING_CROWN_JEWEL|CROWN_JEWEL_SOURCE")
_PROTECTED_FRAG_RE = re.compile(rb"(?i)OMNIS_WING_PROTECTED_FRAGMENT")
_PROJECT_RE = re.compile(
    rb"(?i)(?:/Users/[\w.-]+/(?:chamber|projects|pan-cc)|jourdanlabs|"
    rb"omnis-wing|SOUL\.md|MEMORY\.md|def |class |import |from \w+ import )"
)

# Default policy ceilings (bound into signed policy later)
DEFAULT_FILE_COUNT_CEILING = 50
DEFAULT_BYTE_CEILING = 512_000


@dataclass
class TaintRecord:
    digest: str
    classification: str  # generic|project|protected|credential|unknown
    protected_root: bool
    crown_jewel: bool
    path: str = "memory:anonymous"
    byte_range: Optional[Tuple[int, int]] = None
    parents: Tuple[str, ...] = ()

    def to_provenance(self) -> SourceProvenance:
        return SourceProvenance(
            path=self.path,
            content_digest=self.digest,
            classification=self.classification,
            protected_root=self.protected_root,
            crown_jewel=self.crown_jewel,
            byte_range=self.byte_range,
            whole_content=self.byte_range is None,
        )


def _d(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_content_bytes(data: bytes, *, path_hint: str = "") -> TaintRecord:
    """Classify bytes by content. Filename is advisory only, never sole authority.

    No ambient environment override. Classification is automatic and fail-closed.
    """
    dig = _d(data)

    # Credentials / secrets first — never washable
    if _PEM_RE.search(data) or _AWS_KEY_RE.search(data) or _CONN_RE.search(data):
        return TaintRecord(dig, "credential", True, False, path_hint or "content:credential")
    for m in PLANTED_SECRET_MARKERS:
        if m.encode() in data:
            return TaintRecord(dig, "credential", True, False, path_hint or "content:planted")
    if TOKEN_RE.search(data) or _ENV_ASSIGN_RE.search(data):
        return TaintRecord(dig, "credential", True, False, path_hint or "content:token")

    if _CROWN_RE.search(data):
        return TaintRecord(dig, "protected", True, True, path_hint or "content:crown")
    if _PROTECTED_FRAG_RE.search(data):
        return TaintRecord(dig, "protected", True, False, path_hint or "content:protected")

    # path_hint may reinforce project but never clear a credential
    path_l = (path_hint or "").lower()
    path_project = any(
        x in path_l for x in (".env", "id_rsa", "credentials", "secret", "chamber", "omnis")
    )

    if _PROJECT_RE.search(data) or path_project:
        return TaintRecord(dig, "project", True, False, path_hint or "content:project")

    if not data or not data.strip():
        return TaintRecord(dig, "generic", False, False, path_hint or "content:empty")

    # high binary ratio → unknown
    sample = data[:4000]
    printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
    if len(sample) > 200 and printable / len(sample) < 0.65:
        return TaintRecord(dig, "unknown", True, False, path_hint or "content:unknown")

    return TaintRecord(dig, "generic", False, False, path_hint or "content:generic")


def read_file_with_provenance(path: Path, *, root: Optional[Path] = None) -> Tuple[bytes, TaintRecord]:
    """WING file read boundary — always returns taint."""
    path = Path(path)
    data = path.read_bytes()
    try:
        rel = str(path.relative_to(root)) if root else str(path)
    except Exception:
        rel = str(path)
    rec = classify_content_bytes(data, path_hint=rel)
    # .env etc. reinforce protected even if content looks mild
    name = path.name.lower()
    if name in (".env", ".env.local", "credentials.json", "secrets.yaml") or name.endswith(".pem"):
        if rec.classification == "generic":
            rec = TaintRecord(_d(data), "protected", True, False, rel)
    return data, rec


_RANK = {"credential": 5, "protected": 4, "project": 3, "unknown": 2, "generic": 1, "": 0}


def merge_taint(*records: TaintRecord) -> TaintRecord:
    """Taint lattice join — protected never washes out."""
    if not records:
        return TaintRecord(_d(b""), "unknown", True, False, "merge:empty")
    worst = records[0]
    digests = []
    parents = []
    crown = False
    for r in records:
        digests.append(r.digest)
        parents.append(r.digest)
        crown = crown or r.crown_jewel
        if _RANK.get(r.classification, 0) > _RANK.get(worst.classification, 0):
            worst = r
    combo = _d(",".join(digests).encode())
    return TaintRecord(
        combo,
        worst.classification,
        worst.protected_root or worst.classification != "generic",
        crown,
        path=f"merge:{worst.path}",
        parents=tuple(parents),
    )


def taint_concat(parts: Sequence[Tuple[bytes, TaintRecord]]) -> Tuple[bytes, TaintRecord]:
    blob = b"".join(p for p, _ in parts)
    rec = merge_taint(*(r for _, r in parts))
    rec = replace(rec, digest=_d(blob), path="concat")
    # re-scan combined bytes — split secrets / re-formed markers
    rescanned = classify_content_bytes(blob, path_hint="concat")
    return blob, merge_taint(rec, rescanned)


def taint_summarize(original: bytes, summary_text: str, parent: TaintRecord) -> Tuple[bytes, TaintRecord]:
    """Summary inherits parent taint; also scan summary text."""
    sb = summary_text.encode("utf-8", errors="replace")
    child = classify_content_bytes(sb, path_hint="summary")
    # protected parent stays protected even if summary looks generic
    merged = merge_taint(parent, child)
    if parent.classification in ("protected", "project", "credential") and merged.classification == "generic":
        merged = replace(
            merged,
            classification=parent.classification,
            protected_root=True,
            crown_jewel=parent.crown_jewel,
            path="summary:inherited",
        )
    return sb, replace(merged, digest=_d(sb))


def taint_from_tool_result(text: str, *, tool_name: str = "tool") -> TaintRecord:
    return classify_content_bytes(
        text.encode("utf-8", errors="replace"), path_hint=f"tool:{tool_name}"
    )


def propagate_into_messages(
    messages: Sequence[dict],
    extra_taints: Sequence[TaintRecord] = (),
) -> Tuple[Tuple[SourceProvenance, ...], TaintRecord]:
    """Build provenance list from message tree + inherited taints."""
    records: List[TaintRecord] = list(extra_taints)
    for i, m in enumerate(messages or ()):
        if not isinstance(m, dict):
            continue
        for key in ("content", "name", "tool_call_id"):
            v = m.get(key)
            if isinstance(v, str) and v:
                records.append(
                    classify_content_bytes(
                        v.encode("utf-8", errors="replace"),
                        path_hint=f"messages[{i}].{key}",
                    )
                )
        # tool calls / function args
        for tc in m.get("tool_calls") or []:
            if isinstance(tc, dict):
                fn = (tc.get("function") or {})
                args = fn.get("arguments") or ""
                if isinstance(args, str) and args:
                    records.append(
                        classify_content_bytes(
                            args.encode(), path_hint=f"messages[{i}].tool_calls.args"
                        )
                    )
    if not records:
        records = [TaintRecord(_d(b""), "unknown", True, False, "messages:empty")]
    merged = merge_taint(*records)
    return tuple(r.to_provenance() for r in records), merged


def check_repo_breadth(
    file_count: int,
    total_bytes: int,
    *,
    file_ceiling: int = DEFAULT_FILE_COUNT_CEILING,
    byte_ceiling: int = DEFAULT_BYTE_CEILING,
) -> Optional[str]:
    if file_count > file_ceiling:
        return f"repo_breadth_file_count:{file_count}>{file_ceiling}"
    if total_bytes > byte_ceiling:
        return f"repo_breadth_bytes:{total_bytes}>{byte_ceiling}"
    return None
