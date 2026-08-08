"""Secret-free evidence hygiene — ZT matrix #10 / #11.

Receipts, ledgers, logs, exceptions, and operator outputs must contain:
  - zero cleartext planted test-secret markers
  - zero bare reversible SHA-256 digests of low-entropy markers
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Union

from omnis_wing.absolute.scanner import PLANTED_SECRET_MARKERS

# Low-entropy markers whose bare sha256 must not appear (reversible lookup).
_LOW_ENTROPY_FOR_DIGEST = list(PLANTED_SECRET_MARKERS) + [
    "password",
    "secret",
    "sk-test",
    "AKIATESTKEYEXAMPLE0000",
]


def _bare_marker_digests() -> frozenset[str]:
    out = set()
    for m in _LOW_ENTROPY_FOR_DIGEST:
        out.add(hashlib.sha256(m.encode("utf-8")).hexdigest())
        out.add(hashlib.sha256(m.encode("utf-8")).hexdigest().upper())
    return frozenset(out)


BARE_MARKER_DIGESTS = _bare_marker_digests()
_HEX64_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


def serialize_for_scan(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, (bytes, bytearray)):
        try:
            return bytes(obj).decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=str, sort_keys=True)
    except Exception:
        return str(obj)


def hygiene_violations(blob: str) -> List[str]:
    """Return list of violation codes found in *blob*."""
    hits: List[str] = []
    if not blob:
        return hits
    for m in PLANTED_SECRET_MARKERS:
        if m in blob:
            hits.append(f"cleartext_marker:{m[:24]}")
    for dig in _HEX64_RE.findall(blob):
        if dig.lower() in {d.lower() for d in BARE_MARKER_DIGESTS}:
            hits.append("bare_low_entropy_marker_digest")
            break
    return hits


def assert_secret_free(
    *parts: Any,
    label: str = "artifact",
) -> None:
    """Raise ValueError if any part leaks cleartext marker or bare marker digest."""
    blob = "\n".join(serialize_for_scan(p) for p in parts)
    viol = hygiene_violations(blob)
    if viol:
        raise ValueError(f"hygiene_fail:{label}:{','.join(viol)}")


def scan_path_tree(root: Union[str, Path], *, globs: Sequence[str] = ("**/*",)) -> List[str]:
    """Scan text-ish files under root; return violation codes with paths."""
    root = Path(root)
    out: List[str] = []
    if not root.exists():
        return out
    for pattern in globs:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if p.suffix in {".pyc", ".so", ".dylib", ".png", ".jpg", ".zip"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for v in hygiene_violations(text):
                out.append(f"{p}:{v}")
    return out


def finding_correlation_digest(finding_ids: Iterable[str], *, key: bytes = b"wing-corr-v1") -> str:
    """Keyed correlation over finding IDs only — never secret material."""
    ids = sorted(str(x) for x in finding_ids)
    payload = key + b"\0" + "\0".join(ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
