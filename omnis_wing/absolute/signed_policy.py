"""M6 signed operator policy — enforce | local_only | deny_all. No production off."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

VALID_MODES = frozenset({"enforce", "local_only", "deny_all"})


@dataclass(frozen=True)
class SignedPolicy:
    mode: str
    policy_version: str
    policy_digest: str
    file_count_ceiling: int
    byte_ceiling: int
    require_remote_anchor: bool
    raw: dict

    def public_dict(self) -> dict:
        return {
            "mode": self.mode,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "file_count_ceiling": self.file_count_ceiling,
            "byte_ceiling": self.byte_ceiling,
            "require_remote_anchor": self.require_remote_anchor,
        }


class PolicyError(RuntimeError):
    pass


def _digest_obj(obj: dict) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


DEFAULT_POLICY = {
    "mode": "enforce",
    "policy_version": "omnis-wing.terminus-policy.v1",
    "file_count_ceiling": 50,
    "byte_ceiling": 512000,
    "require_remote_anchor": False,
    "allowed_residencies_generic": ["US", "EU", "LOCAL"],
}


def load_policy(path: Optional[str] = None) -> SignedPolicy:
    p = path or os.environ.get("OMNIS_WING_POLICY_PATH") or ""
    if p:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
    else:
        data = dict(DEFAULT_POLICY)
    mode = (data.get("mode") or "enforce").strip().lower()
    if mode == "off":
        # production has no off — treat as invalid
        raise PolicyError("policy_mode_off_forbidden")
    if mode not in VALID_MODES:
        raise PolicyError(f"invalid_policy_mode:{mode}")
    # optional detached digest check
    expected = data.get("policy_digest") or data.get("signature_digest")
    body = {k: v for k, v in data.items() if k not in ("policy_digest", "signature_digest", "signature")}
    dig = _digest_obj(body)
    if expected and expected != dig:
        raise PolicyError("policy_digest_mismatch")
    return SignedPolicy(
        mode=mode,
        policy_version=str(data.get("policy_version") or "unknown"),
        policy_digest=dig,
        file_count_ceiling=int(data.get("file_count_ceiling") or 50),
        byte_ceiling=int(data.get("byte_ceiling") or 512000),
        require_remote_anchor=bool(data.get("require_remote_anchor")),
        raw=data,
    )


def unenforced_banner() -> str:
    return "UNENFORCED — PAYLOAD NOT INSPECTED"
