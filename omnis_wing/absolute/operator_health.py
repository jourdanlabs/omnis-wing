"""R4 offline operator verifier / health surface — secret-free, observational."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

from omnis_wing.absolute.production_signer import ProductionSignerAdapter
from omnis_wing.absolute.receipt_spine import (
    EvidenceLedger,
    GENESIS_PREV,
    ledger_outcome_report,
    verify_signed_receipt,
)


def _load_coverage(root: Path) -> dict:
    p = root / "omnis_wing" / "coverage" / "ai_egress_coverage_r1.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_health_report(
    *,
    root: Path,
    ledger: EvidenceLedger,
    signer: Optional[ProductionSignerAdapter] = None,
    public_key: Optional[bytes] = None,
    anchor_path: Optional[Path] = None,
    remote_anchor_configured: bool = False,
) -> dict:
    """Observational health. Never clears a failed verifier. Never secrets."""
    enrollment = (
        signer.enrollment_status()
        if signer is not None
        else {"ready": False, "state": "NOT_CONFIGURED"}
    )
    # Strip any accidental secret-looking fields
    for k in list(enrollment.keys()):
        if "private" in k.lower() or "secret" in k.lower() or "password" in k.lower():
            enrollment.pop(k, None)

    pk = public_key
    fp = None
    key_id = None
    if signer is not None and signer.available():
        try:
            pk = signer.public_key_bytes()
            fp = sha256(pk).hexdigest()
            key_id = signer.key_id
        except Exception:
            fp = None

    entries = ledger.load_entries()
    signed_count = len(entries)
    # We do not invent unsigned historical rows; report 0 unknown unless tracked
    unsigned_count = 0

    chain_valid = False
    chain_reason = "no_public_key"
    if pk is not None and entries:
        chain_valid, chain_reason = ledger.verify_chain(pk)
    elif not entries:
        chain_valid, chain_reason = True, "empty_ledger"

    outcome = ledger_outcome_report(ledger)
    cov = _load_coverage(root)
    boundary = (cov.get("glass") or {}).get("active_boundary") or "selected_path_only"

    if remote_anchor_configured and anchor_path and anchor_path.is_file():
        remote_anchor = {
            "state": "LOCAL_FIXTURE_ONLY",
            "note": "local fixture file present; not remote replication",
            "path": str(anchor_path.name),  # basename only
        }
    else:
        remote_anchor = {
            "state": "NOT_CONFIGURED",
            "note": "no remote witness configured; local fsync is not remote durability",
        }

    # Verifier overall: green only if chain ok AND enrollment ready when required
    if not chain_valid:
        verifier = "INVALID"
    elif enrollment.get("state") in ("NOT_ENROLLED", "NOT_CONFIGURED", "UNAVAILABLE"):
        verifier = "NOT_READY"
    elif outcome.get("status") == "OUTCOME_UNKNOWN":
        verifier = "DEGRADED_OUTCOME_UNKNOWN"
    else:
        verifier = "OK"

    try:
        from omnis_wing.completion.product_disable import load_manifest
        _man = load_manifest()
        _routes = {
            "summary": _man.get("summary"),
            "governed": [r["route_id"] for r in _man["routes"] if r["state"] == "GOVERNED"],
            "disabled": [r["route_id"] for r in _man["routes"] if r["state"] == "DISABLED"],
        }
    except Exception:
        _routes = {"summary": {}, "governed": [], "disabled": []}

    report = {
        "schema": "omnis-wing.operator-health.v1",
        "route_manifest": _routes,
        "enrollment": {
            "state": enrollment.get("state"),
            "ready": bool(enrollment.get("ready")),
            "tag": enrollment.get("tag"),
            "storage_state": enrollment.get("storage_state"),
            "key_type": enrollment.get("key_type"),
            "backend": enrollment.get("backend"),
        },
        "signer": {
            "key_id": key_id,
            "public_key_sha256": fp,
            "signature_algorithm": getattr(signer, "signature_algorithm", None) if signer else None,
        },
        "ledger": {
            "signed_receipt_count": signed_count,
            "unsigned_receipt_count": unsigned_count,
            "chain_valid": chain_valid,
            "chain_reason": chain_reason,
            "outcome": outcome,
            "head_digest": ledger.head_digest() if entries else GENESIS_PREV,
        },
        "coverage_boundary": boundary,
        "claims_whole_tree_ai_egress": bool(cov.get("claims_whole_tree_ai_egress")),
        "remote_anchor": remote_anchor,
        "verifier": verifier,
        "notes": [
            "Health is observational and cannot clear a failed chain.",
            "storage_state UNVERIFIED_AT_READ must not be read as hardware_backed=true.",
            "Selected ordinary non-stream chat.completions path only.",
        ],
    }
    return report


def health_to_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
