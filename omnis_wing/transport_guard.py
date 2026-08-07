"""Import/transport guard for OMNIS WING touched host modules.

Forbidden: direct provider/https clients in the admission seam.
Allowed: stdlib hashing/json and the injected Provider protocol only.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

# Names that must not appear as imports inside the guarded package.
FORBIDDEN_MODULES = frozenset(
    {
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "urllib3",
        "openai",
        "anthropic",
        "httplib",
        "http.client",
        "socket",
    }
)

FORBIDDEN_FROM_ROOTS = frozenset(
    {
        "urllib",
        "http",
        "httpx",
        "aiohttp",
        "requests",
        "openai",
        "anthropic",
        "socket",
    }
)


class TransportGuardError(Exception):
    """Raised when a forbidden transport/provider import is found."""


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def scan_source(source: str, filename: str = "<memory>") -> list[str]:
    """Return list of violation messages for a Python source string."""
    tree = ast.parse(source, filename=filename)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod in FORBIDDEN_MODULES or _module_root(mod) in FORBIDDEN_FROM_ROOTS:
                    if mod == "http.client" or mod.startswith("http.") or mod in FORBIDDEN_MODULES or _module_root(mod) in {
                        "httpx", "aiohttp", "requests", "openai", "anthropic", "socket", "urllib",
                    }:
                        # allow nothing from forbidden roots
                        if _module_root(mod) in FORBIDDEN_FROM_ROOTS or mod in FORBIDDEN_MODULES:
                            hits.append(f"{filename}:{node.lineno}: forbidden import '{mod}'")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = _module_root(mod) if mod else ""
            if mod in FORBIDDEN_MODULES or root in FORBIDDEN_FROM_ROOTS:
                hits.append(f"{filename}:{node.lineno}: forbidden from-import '{mod}'")
    return hits


def scan_paths(paths: Iterable[Path]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        violations.extend(scan_source(text, filename=str(path)))
    return violations


def assert_clean_package(package_dir: Path) -> None:
    """Fail if any .py under package_dir contains forbidden transport imports."""
    files = sorted(package_dir.rglob("*.py"))
    # Exclude intentional canary directory if present
    files = [p for p in files if "canary_plant" not in p.parts]
    violations = scan_paths(files)
    if violations:
        raise TransportGuardError(
            "transport/import guard failed:\n" + "\n".join(violations)
        )


def guarded_modules() -> list[Path]:
    root = Path(__file__).resolve().parent
    return sorted(p for p in root.rglob("*.py") if "canary_plant" not in p.parts)
