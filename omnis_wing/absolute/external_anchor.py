"""M5 external anchor — honest NOT_CONFIGURED until wired; test double for can-fail."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class AnchorStatus:
    state: str  # REMOTE_ANCHOR_NOT_CONFIGURED | PENDING | VERIFIED | FAILED
    note: str
    head_digest: Optional[str] = None
    anchor_digest: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "note": self.note,
            "head_digest": self.head_digest,
            "anchor_digest": self.anchor_digest,
        }


@dataclass
class LocalFileAnchor:
    """Test double / optional local witness file — NOT remote durability."""

    path: Path
    queue: List[str] = field(default_factory=list)

    def status(self, ledger_head: str) -> AnchorStatus:
        if not self.path.parent.exists():
            return AnchorStatus(
                "REMOTE_ANCHOR_NOT_CONFIGURED",
                "anchor path parent missing; local fsync is not remote durability",
            )
        if not self.path.is_file():
            return AnchorStatus(
                "REMOTE_ANCHOR_NOT_CONFIGURED",
                "no anchor file; configure external witness to claim anchored",
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            return AnchorStatus("FAILED", f"anchor_read_failed:{type(exc).__name__}")
        ad = data.get("head_digest")
        if ad != ledger_head:
            return AnchorStatus(
                "FAILED",
                "anchor_head_mismatch_possible_ledger_replacement",
                head_digest=ledger_head,
                anchor_digest=ad,
            )
        return AnchorStatus(
            "VERIFIED",
            "local_fixture_only_not_remote",
            head_digest=ledger_head,
            anchor_digest=ad,
        )

    def publish(self, ledger_head: str) -> AnchorStatus:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "head_digest": ledger_head,
            "anchor_digest": hashlib.sha256(ledger_head.encode()).hexdigest(),
            "kind": "local_file_anchor_test_double",
        }
        self.path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return self.status(ledger_head)

    def enqueue(self, ledger_head: str) -> None:
        self.queue.append(ledger_head)


def resolve_anchor_status(ledger_head: str) -> AnchorStatus:
    cfg = (os.environ.get("OMNIS_WING_ANCHOR_PATH") or "").strip()
    if not cfg:
        return AnchorStatus(
            "REMOTE_ANCHOR_NOT_CONFIGURED",
            "no remote witness configured; local fsync is not remote durability",
            head_digest=ledger_head,
        )
    return LocalFileAnchor(Path(cfg)).status(ledger_head)
