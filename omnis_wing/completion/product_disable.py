"""Product-disable AI side-doors. Accurate refusal — never silent bypass."""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any, Callable


class WingRouteDisabled(RuntimeError):
    """Raised when a product-disabled AI egress route is invoked."""

    def __init__(self, route_id: str, reason: str):
        self.route_id = route_id
        self.reason = reason
        super().__init__(f"OMNIS_WING_ROUTE_DISABLED:{route_id}:{reason}")


def load_manifest() -> dict:
    p = Path(__file__).resolve().parent / "route_manifest.json"
    return json.loads(p.read_text(encoding="utf-8"))


def disabled_routes() -> dict[str, str]:
    man = load_manifest()
    out = {}
    for r in man["routes"]:
        if r["state"] == "DISABLED" and r.get("broker_join") == "DISABLED":
            out[r["route_id"]] = r.get("disable_reason") or "disabled"
    return out


def assert_route_enabled(route_id: str) -> None:
    d = disabled_routes()
    if route_id in d:
        raise WingRouteDisabled(route_id, d[route_id])


def disabled_guard(route_id: str) -> Callable:
    """Decorator: refuse before any nested transport."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            assert_route_enabled(route_id)
            return fn(*args, **kwargs)

        return wrapper

    return deco


def refuse_disabled_call(route_id: str, *args, **kwargs) -> Any:
    assert_route_enabled(route_id)
    raise RuntimeError("unreachable")
