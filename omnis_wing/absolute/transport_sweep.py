"""Static whole-tree transport sweep — ZT #16 residual.

Finds provider-bearing client construction / raw HTTP send ownership outside
the TransportBroker ownership boundary. Complements broker_guard (governed
helper import ban) with a broader transport pattern sweep.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# Patterns that indicate direct provider transport ownership in product trees.
_TRANSPORT_CALL_RES = (
    re.compile(r"\bopenai\.OpenAI\s*\("),
    re.compile(r"\banthropic\.Anthropic\s*\("),
    re.compile(r"\bhttpx\.(Client|AsyncClient)\s*\("),
    re.compile(r"\brequests\.(get|post|put|patch|delete|request)\s*\("),
    re.compile(r"\bClient\s*\(\s*api_key\s*="),
)

# Trees that must not own AI provider sockets (except broker-owned joins).
DEFAULT_SCAN_GLOBS = (
    "agent/**/*.py",
    "tools/**/*.py",
    "wing_cli/**/*.py",
    "plugins/**/*.py",
    "cron/**/*.py",
)

# Allowlist: known non-AI or already-DISABLED / non-join scaffolding.
# Sweep still reports; conformance tests decide GOVERNED vs DISABLED routing.
ALLOWLIST_PATH_SUBSTRINGS = (
    "/omnis_wing/absolute/",  # seam owns guards
    "/tests/",
    "doctor.py",  # health probes named in manifest
    "status.py",
)


def _allowed(path: Path, root: Path) -> bool:
    rel = str(path.relative_to(root)).replace("\\", "/")
    # Never allowlist agent chat join files — they must use broker only
    if rel.startswith("agent/chat_completion") or rel.startswith("agent/anthropic"):
        return False
    full = str(path)
    for a in ALLOWLIST_PATH_SUBSTRINGS:
        if a.strip("/") in rel or a in full:
            # doctor/status yes; absolute yes; tests yes
            if "agent/" in rel and "omnis_wing" not in rel:
                if "doctor" not in rel and "status" not in rel:
                    continue
            return True
    return False


def sweep_file(path: Path, root: Path) -> List[str]:
    hits: List[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return [f"{path}:read_error:{type(exc).__name__}"]
    rel = str(path.relative_to(root)).replace("\\", "/")
    if _allowed(path, root):
        return hits
    for cre in _TRANSPORT_CALL_RES:
        for m in cre.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{rel}:{line}:{cre.pattern}")
    # AST: attribute send on httpx-ish
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"send", "request"} and isinstance(node.func.value, ast.Name):
                # flag bare .send( / .request( on names that look like clients
                base = node.func.value.id.lower()
                if any(x in base for x in ("client", "http", "session", "transport")):
                    hits.append(f"{rel}:{getattr(node, 'lineno', 0)}:attr_{node.func.attr}")
    return hits


def sweep_tree(
    root: Path,
    globs: Sequence[str] = DEFAULT_SCAN_GLOBS,
) -> List[str]:
    root = Path(root)
    out: List[str] = []
    for g in globs:
        for p in root.glob(g):
            if p.is_file() and p.suffix == ".py":
                out.extend(sweep_file(p, root))
    return sorted(set(out))


def assert_no_unmanifested_transport(
    root: Path,
    *,
    allowed_hit_substrings: Iterable[str] = (),
) -> None:
    """Raise if sweep finds hits not covered by allowed substrings.

    DISABLED side-door modules may still construct clients in source; those
    paths must appear in allowed_hit_substrings or be product-disabled at
    runtime. This gate is for *untracked* new transport.
    """
    hits = sweep_tree(root)
    allowed = tuple(allowed_hit_substrings)
    bad = [h for h in hits if not any(a in h for a in allowed)]
    if bad:
        raise AssertionError("unmanifested_transport:\n" + "\n".join(bad[:40]))
