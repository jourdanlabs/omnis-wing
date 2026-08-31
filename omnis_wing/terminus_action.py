"""WING client for the canonical CADUCEUS TERMINUS action gate.

WING does not grow a fourth refusal grammar. Shell / write / patch call
``authorize_action``; CADUCEUS decides ALLOW | REFUSE | HOLD.
Fail-closed: missing node, missing CLI, timeout, or garbage JSON is REFUSE.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path.home() / "projects" / "caduceus"
_TIMEOUT_SEC = 8


def cli_path() -> Path | None:
    explicit = os.environ.get("TERMINUS_AUTHORIZE")
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    root = Path(os.environ.get("CADUCEUS_ROOT") or _DEFAULT_ROOT)
    candidate = root / "scripts" / "terminus-authorize.mjs"
    return candidate if candidate.is_file() else None


def authorize_action(
    *,
    agent_id: str,
    kind: str,
    payload: str,
    session_id: str = "",
    human_override: bool = False,
    target_path: str | None = None,
    workspace_root: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call CADUCEUS authorizeAction via the language-agnostic CLI.

    Always returns a dict with ``verdict`` in {ALLOW, REFUSE, HOLD}.
    Never raises on a gate miss — a miss is REFUSE.
    """
    unavailable = {
        "verdict": "REFUSE",
        "decision": "REFUSE_SCANNER_FAILURE",
        "reason": "terminus_unavailable",
        "receipt": None,
    }
    cli = cli_path()
    node = shutil.which("node")
    if cli is None or node is None:
        return unavailable

    action: dict[str, Any] = {
        "agent_id": agent_id,
        "kind": kind,
        "payload": payload,
        "session_id": session_id,
    }
    if target_path:
        action["target_path"] = target_path
    if workspace_root:
        action["workspace_root"] = workspace_root
    if metadata:
        action["metadata"] = metadata
    if human_override:
        action["human_override"] = True

    try:
        proc = subprocess.run(
            [node, str(cli)],
            input=json.dumps(action),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return unavailable

    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return unavailable

    verdict = out.get("verdict")
    if verdict not in ("ALLOW", "REFUSE", "HOLD"):
        return unavailable
    return {
        "verdict": verdict,
        "decision": out.get("decision"),
        "reason": out.get("reason"),
        "receipt": out.get("receipt"),
    }


def block_message(result: dict[str, Any]) -> str:
    reason = result.get("reason") or "terminus"
    if result.get("verdict") == "HOLD":
        return (
            f"TERMINUS HOLD ({reason}): this action is paused for human approval. "
            "No side effect ran."
        )
    return f"TERMINUS REFUSED ({reason}): this action did not run."
