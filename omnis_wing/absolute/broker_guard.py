"""Static + runtime guards: TransportBroker is the sole real AI egress join."""

from __future__ import annotations

import ast
import re
import threading
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# Names agent/product modules must not import or call directly.
BANNED_GOVERNED_NAMES = frozenset(
    {
        "governed_chat_completions_create",
        "governed_callable_transmit",
        "governed_streaming_create",
    }
)

# Modules allowed to reference the governed implementations (broker + impl bodies).
ALLOWED_GOVERNED_MODULES = frozenset(
    {
        "omnis_wing.absolute.transport_broker",
        "omnis_wing.absolute.hermes_chat_join",
        "omnis_wing.absolute.universal_egress",
        "omnis_wing.absolute.broker_guard",
    }
)

# Paths (relative to repo root) that may contain governed names.
ALLOWED_PATH_PREFIXES = (
    "omnis_wing/absolute/transport_broker.py",
    "omnis_wing/absolute/hermes_chat_join.py",
    "omnis_wing/absolute/universal_egress.py",
    "omnis_wing/absolute/broker_guard.py",
    "tests/",  # tests may instrument / assert
    "omnis_wing/spec/",
    "omnis_wing/completion/route_manifest.json",
)

# Agent-side trees that must not import governed helpers.
AGENT_SCAN_GLOBS = (
    "agent/**/*.py",
    "tools/**/*.py",
    "hermes_cli/**/*.py",
    "gateway/**/*.py",
    "plugins/**/*.py",
    "cron/**/*.py",
)

_tls = threading.local()


class BrokerViolation(RuntimeError):
    """Raised when a non-broker path attempts provider ownership or direct governed call."""


def broker_context_depth() -> int:
    return int(getattr(_tls, "depth", 0) or 0)


class broker_dispatch_scope:
    """Context manager entered only by TransportBroker around real dispatch."""

    def __enter__(self) -> "broker_dispatch_scope":
        _tls.depth = broker_context_depth() + 1
        return self

    def __exit__(self, *exc: object) -> None:
        d = broker_context_depth()
        _tls.depth = max(0, d - 1)


def require_broker_dispatch(entry: str) -> None:
    """Runtime gate: governed transmit implementations are broker-only."""
    if broker_context_depth() < 1:
        raise BrokerViolation(f"direct_governed_call_forbidden:{entry}")


_IMPORT_FROM_RE = re.compile(
    r"from\s+omnis_wing\.absolute\.(hermes_chat_join|universal_egress)\s+import\s+\(?([^)\n]+)\)?",
    re.MULTILINE,
)
_NAME_RE = re.compile(r"\b(governed_chat_completions_create|governed_callable_transmit|governed_streaming_create)\b")


def _path_allowed(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    for pref in ALLOWED_PATH_PREFIXES:
        if rel == pref or rel.startswith(pref):
            return True
    return False


def scan_source_for_governed_bypass(
    root: Path,
    *,
    extra_globs: Sequence[str] = (),
) -> List[Tuple[str, int, str]]:
    """Return list of (relpath, lineno, line) violations outside the broker waist."""
    hits: List[Tuple[str, int, str]] = []
    globs = list(AGENT_SCAN_GLOBS) + list(extra_globs)
    seen: set[Path] = set()
    for pattern in globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rp = path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(path)
            if _path_allowed(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Skip pure comments-only mentions in docs-like strings carefully via AST when possible
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if not _NAME_RE.search(line):
                    continue
                # allow string mentions in comments already skipped; allow "broker_join" JSON-like docs in py strings only if no import
                if "import" in line or "governed_" in line:
                    # flag import or call
                    hits.append((rel, i, stripped[:200]))
    return hits


def scan_ast_agent_imports(root: Path) -> List[Tuple[str, int, str]]:
    """AST pass: agent trees must not import banned governed names."""
    hits: List[Tuple[str, int, str]] = []
    for pattern in AGENT_SCAN_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if _path_allowed(rel):
                continue
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=rel)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod in (
                        "omnis_wing.absolute.hermes_chat_join",
                        "omnis_wing.absolute.universal_egress",
                    ) or mod.endswith(".hermes_chat_join") or mod.endswith(".universal_egress"):
                        for alias in node.names:
                            if alias.name in BANNED_GOVERNED_NAMES or alias.name == "*":
                                hits.append(
                                    (
                                        rel,
                                        getattr(node, "lineno", 0),
                                        f"from {mod} import {alias.name}",
                                    )
                                )
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.attr in BANNED_GOVERNED_NAMES:
                        hits.append((rel, getattr(node, "lineno", 0), f"attr {node.attr}"))
    return hits


def assert_no_agent_governed_bypass(root: Path) -> None:
    hits = scan_ast_agent_imports(root) + scan_source_for_governed_bypass(root)
    # de-dupe
    uniq = sorted(set(hits))
    if uniq:
        detail = "; ".join(f"{p}:{n}:{s}" for p, n, s in uniq[:20])
        raise BrokerViolation(f"agent_governed_bypass:{len(uniq)}:{detail}")
