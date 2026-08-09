"""Provider-neutral real-work contract facts for WING parity.

MiniMax is first adapter in CADUCEUS proofs — not a special safety category.
Routes without transform/response coverage stay DISABLED, not "governed by vibes."
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REAL_WORK_POLICY_ID = "TERMINUS_REAL_WORK_V1"

DELIVERY_MODE = frozenset({"RAW", "TRANSFORMED", "LOCAL_ONLY"})
RESPONSE_HANDLING = frozenset(
    {"CLEAN", "REDACTED", "SUPPRESSED", "REINTEGRATION_REFUSED", "NOT_APPLICABLE"}
)

# Honest route table for this vertical. Update only when a path is actually joined.
# Primary ordinary chat becomes GOVERNED via CADUCEUS join (not direct MiniMax).
ROUTE_TABLE: Mapping[str, str] = {
    "caduceus.chat_completions": "GOVERNED",  # when terminus_real_work_v1 present
    "caduceus.omnis_broker_chat": "GOVERNED",  # P2 path; compose when section present
    "caduceus.image_generations": "DISABLED",  # real-work transform not wired
    "wing.chat_join": "GOVERNED",  # TransportBroker → CADUCEUS when configured
    "wing.chat_join_direct_provider": "DISABLED",  # no direct MiniMax on dogfood path
    "wing.image_join": "DISABLED",  # residual/history; not real-work vertical
    "wing.embeddings": "DISABLED",
    "wing.audio": "DISABLED",
    "wing.mcp": "DISABLED",
    "wing.stream": "DISABLED",
    "wing.anthropic": "DISABLED",
    "wing.bedrock": "DISABLED",
    "wing.codex": "DISABLED",
    "wing.vision": "DISABLED",
    "wing.transcription": "DISABLED",
    "wing.moa": "DISABLED",
    "wing.auxiliary": "DISABLED",
}

_CORPUS_PATH = Path(__file__).with_name("terminus-transform-v1.corpus.json")


def load_shared_corpus(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or _CORPUS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("policy_id") != REAL_WORK_POLICY_ID:
        raise ValueError("corpus policy_id mismatch")
    if data.get("provider_neutral") is not True:
        raise ValueError("corpus must be provider_neutral")
    return data


def corpus_digest(path: Optional[Path] = None) -> str:
    p = path or _CORPUS_PATH
    return hashlib.sha256(p.read_bytes()).hexdigest()


def assert_route_honest(route_id: str, claimed: str) -> None:
    """Refuse silent upgrade of a DISABLED route to GOVERNED without table update."""
    expected = ROUTE_TABLE.get(route_id)
    if expected is None:
        raise KeyError(f"unknown route_id {route_id}")
    if claimed != expected:
        raise AssertionError(
            f"route {route_id}: claimed {claimed!r} but table says {expected!r}"
        )


def delivery_mode_valid(mode: str) -> bool:
    return mode in DELIVERY_MODE


def transformed_receipt_complete(fields: Mapping[str, Any]) -> List[str]:
    """Same bar as CADUCEUS validateRealWorkReceiptFields for TRANSFORMED."""
    errors: List[str] = []
    if fields.get("delivery_mode") != "TRANSFORMED":
        return errors
    for k in (
        "transform_policy_digest",
        "transform_input_digest",
        "transform_output_digest",
    ):
        v = fields.get(k)
        if not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            errors.append(f"{k}: mandatory hex sha256 when TRANSFORMED")
    if not fields.get("origin_classification"):
        errors.append("origin_classification required")
    if fields.get("emitted_classification") not in ("safe_derived", "generic"):
        errors.append("emitted_classification invalid for TRANSFORMED")
    return errors
