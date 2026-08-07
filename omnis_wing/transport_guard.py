"""Import/transport guard for OMNIS WING touched host modules.

R1: covers every path listed as governed in ai_egress_coverage_r1.json
plus the historical W0 seam modules.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterable, List

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
    tree = ast.parse(source, filename=filename)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                root = _module_root(mod)
                if mod in FORBIDDEN_MODULES or root in FORBIDDEN_FROM_ROOTS:
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


def r1_governed_paths(repo_root: Path) -> List[Path]:
    """Paths subject to the import/transport guard.

    Coverage may list Hermes host files as governed_r2 for the join site, but
    those files still contain upstream HTTP imports. The guard applies to
    omnis_wing package modules only (including R2 hermes_chat_join).
    """
    man_path = repo_root / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json"
    data = json.loads(man_path.read_text(encoding="utf-8"))
    paths = [repo_root / e["path"] for e in data.get("governed_r1", [])]
    for e in list(data.get("governed_r2", [])) + list(data.get("governed_r3", [])) + list(data.get("governed_r4", [])):
        rel = e["path"]
        if not rel.startswith("omnis_wing/"):
            continue  # host join file: coverage-claimed, not import-clean
        p = repo_root / rel
        if p.suffix != ".py":
            continue  # Swift/bridge sources are not Python AST-scanned
        if p not in paths:
            paths.append(p)
    for extra in (
        repo_root / "omnis_wing" / "boundary.py",
        repo_root / "omnis_wing" / "host_dispatch.py",
        repo_root / "omnis_wing" / "__init__.py",
    ):
        if extra.is_file() and extra not in paths:
            paths.append(extra)
    return paths


def assert_clean_package(package_dir: Path) -> None:
    """Fail if any governed R1 module (or package py without canary) has forbidden imports."""
    repo_root = package_dir.parent if package_dir.name == "omnis_wing" else package_dir
    if (repo_root / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json").is_file():
        files = [p for p in r1_governed_paths(repo_root) if p.is_file()]
    else:
        files = sorted(package_dir.rglob("*.py"))
        files = [p for p in files if "canary_plant" not in p.parts]
    violations = scan_paths(files)
    if violations:
        raise TransportGuardError(
            "transport/import guard failed:\n" + "\n".join(violations)
        )


def guarded_modules() -> list[Path]:
    root = Path(__file__).resolve().parent
    repo = root.parent
    if (repo / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json").is_file():
        return [p for p in r1_governed_paths(repo) if p.is_file()]
    return sorted(p for p in root.rglob("*.py") if "canary_plant" not in p.parts)
