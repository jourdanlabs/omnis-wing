"""AI-egress coverage manifest loader for OMNIS WING R1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "coverage" / "ai_egress_coverage_r1.json"


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema") == "omnis-wing.ai-egress-coverage.r1"
    return data


def governed_module_paths(root: Path) -> List[Path]:
    """Return absolute paths of modules this R1 claims to govern."""
    man = load_manifest()
    out: List[Path] = []
    for entry in man["governed_r1"]:
        p = root / entry["path"]
        out.append(p)
    return out


def assert_manifest_honest(root: Path) -> None:
    man = load_manifest()
    for entry in man["governed_r1"]:
        p = root / entry["path"]
        if not p.is_file():
            raise AssertionError(f"governed path missing: {entry['path']}")
        if entry.get("status") != "governed":
            raise AssertionError(f"governed entry bad status: {entry}")
    for entry in man["inherited_hermes_transport"]:
        if entry.get("status") not in ("ungoverned", "inbound", "outside_r1"):
            raise AssertionError(f"inherited entry must not claim governed: {entry}")
    if man.get("claims_whole_tree_ai_egress"):
        raise AssertionError("manifest must not claim whole-tree AI egress")
