"""Closed shipping-route inventory: GOVERNED | DISABLED only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from omnis_wing.completion.product_disable import load_manifest


ALLOWED_STATES = frozenset({"GOVERNED", "DISABLED"})


class RouteInventoryError(RuntimeError):
    pass


def closed_route_inventory(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a secret-free closed inventory or raise on UNENFORCED / unknown."""
    man = manifest if manifest is not None else load_manifest()
    routes = man.get("routes")
    if not isinstance(routes, list) or not routes:
        raise RouteInventoryError("route_manifest_empty")
    bad: list[str] = []
    governed: list[str] = []
    disabled: list[str] = []
    seen: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise RouteInventoryError("route_entry_not_object")
        rid = str(route.get("route_id") or "")
        state = str(route.get("state") or "")
        if not rid:
            raise RouteInventoryError("route_id_missing")
        if rid in seen:
            raise RouteInventoryError(f"duplicate_route:{rid}")
        seen.add(rid)
        if state not in ALLOWED_STATES:
            bad.append(f"{rid}:{state or 'MISSING'}")
            continue
        if state == "GOVERNED":
            governed.append(rid)
        else:
            disabled.append(rid)
    if bad:
        raise RouteInventoryError("unenforced_or_unknown_routes:" + ",".join(sorted(bad)))
    payload = {
        "schema": "omnis-wing.route-inventory.v1",
        "total": len(routes),
        "governed": sorted(governed),
        "disabled": sorted(disabled),
        "summary": {"GOVERNED": len(governed), "DISABLED": len(disabled)},
        "forbidden_states_observed": [],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    payload["digest"] = hashlib.sha256(canonical).hexdigest()
    return payload


def route_manifest_digest() -> str:
    path = Path(__file__).resolve().parents[1] / "completion" / "route_manifest.json"
    return hashlib.sha256(path.read_bytes()).hexdigest()
