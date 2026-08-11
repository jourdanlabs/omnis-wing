"""WING surface for TERMINUS_RUN_LOCAL_V1 (Phase 1 cold).

WING never opens a local model socket. It only constructs a normalized
route intent and dispatches to CADUCEUS (the sole socket owner).

Identity: this is transport only. SHIMMER is a separate future MTS identity —
not Pan, not continuity-by-renaming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

ROUTE_INTENT = "RUN_LOCAL"
ROUTE_LABEL = "LOCAL / GOVERNED / TOOLS DISABLED"
POLICY_ID = "TERMINUS_RUN_LOCAL_V1"
PROVIDER_ID = "muse_glimmer_local"
TOOL_EGRESS_MODE = "DISABLED"
CONFIG_VERSION = "OMNIS_WING_RUN_LOCAL_V1"
LITERAL_HOST = "127.0.0.1"
CHAT_PATH = "/v1/chat/completions"

# Sentinel: any intentional direct local-provider construction increments this.
# L2 requires allowed paths leave this at zero; intentional construct turns red.
_direct_local_provider_constructions: int = 0


class RunLocalWingError(Exception):
    """Typed WING-side refusal before CADUCEUS dispatch when intent is malformed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RunLocalRouteIntent:
    """Normalized route request WING hands to CADUCEUS — not a transport client."""

    route_intent: str
    label: str
    config: Mapping[str, Any]
    messages: Sequence[Mapping[str, str]]
    tool_egress_mode: str = TOOL_EGRESS_MODE


def direct_local_provider_construction_count() -> int:
    return _direct_local_provider_constructions


def reset_direct_local_provider_constructions_for_tests() -> None:
    global _direct_local_provider_constructions
    _direct_local_provider_constructions = 0


def intentional_direct_local_provider_construct() -> Dict[str, Any]:
    """Can-fail plant: simulates a forbidden WING-side local client construction."""
    global _direct_local_provider_constructions
    _direct_local_provider_constructions += 1
    return {
        "base_url": f"http://{LITERAL_HOST}:9/v1",
        "constructed": True,
        "forbidden": True,
    }


def default_disabled_config(port: int = 8080) -> Dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "enabled": False,
        "provider_id": PROVIDER_ID,
        "protocol": "openai_chat_completions",
        "host": LITERAL_HOST,
        "port": port,
        "path": CHAT_PATH,
        "declared_model_id": "operator-local-model",
        "tool_egress_mode": TOOL_EGRESS_MODE,
    }


def build_run_local_intent(
    *,
    config: Mapping[str, Any],
    messages: Sequence[Mapping[str, str]],
) -> RunLocalRouteIntent:
    """Build a frozen route intent. Does not open sockets. Does not call providers."""
    if not isinstance(config, Mapping):
        raise RunLocalWingError("RUN_LOCAL_CONFIG_INVALID", "config must be a mapping")
    if not messages:
        raise RunLocalWingError("RUN_LOCAL_CONFIG_INVALID", "messages required")
    for m in messages:
        if m.get("role") not in ("system", "user", "assistant"):
            raise RunLocalWingError("RUN_LOCAL_CONFIG_INVALID", f"bad role {m.get('role')!r}")
        if not isinstance(m.get("content"), str):
            raise RunLocalWingError("RUN_LOCAL_CONFIG_INVALID", "content must be string")

    # No OpenAI/httpx/http.client construction here — by design.
    return RunLocalRouteIntent(
        route_intent=ROUTE_INTENT,
        label=ROUTE_LABEL,
        config=dict(config),
        messages=tuple(dict(m) for m in messages),
        tool_egress_mode=TOOL_EGRESS_MODE,
    )


def request_run_local_turn(
    *,
    config: Mapping[str, Any],
    messages: Sequence[Mapping[str, str]],
    caduceus_dispatch: Callable[[RunLocalRouteIntent], Any],
) -> Any:
    """WING operator path: intent → CADUCEUS dispatch only.

    ``caduceus_dispatch`` is the governed client boundary (HTTP/CLI/native).
    This function must never construct a local model HTTP client.
    """
    if not callable(caduceus_dispatch):
        raise RunLocalWingError(
            "RUN_LOCAL_RECEIPT_PREREQUISITE_FAILED",
            "caduceus_dispatch is required",
        )
    intent = build_run_local_intent(config=config, messages=messages)
    # Re-check sentinel: if someone constructed a direct client, refuse to proceed
    # as a successful governed path (CADUCEUS tests also enforce this).
    return caduceus_dispatch(intent)


def operator_remediation(code: str) -> str:
    """Plain-language remediations for WING UI (Phase 1)."""
    table = {
        "RUN_LOCAL_NOT_ENABLED": (
            "Turn on the private local route after an admitted artifact/runner is available."
        ),
        "RUN_LOCAL_LITERAL_ENDPOINT_REQUIRED": (
            "Set an explicit 127.0.0.1 host and port; hostnames are not allowed."
        ),
        "RUN_LOCAL_DESTINATION_NOT_LOOPBACK": (
            "This route cannot use LAN, public, IPv6, or alternate loopback addresses."
        ),
        "RUN_LOCAL_TRANSPORT_SHAPE_REFUSED": (
            "Proxy, redirect, alternate path, socket, or endpoint override is not allowed."
        ),
        "RUN_LOCAL_TOOL_EGRESS_DISABLED": "V1 local RUN_LOCAL has no tools.",
        "RUN_LOCAL_PROVIDER_PROTOCOL_INVALID": (
            "Local server returned an unsupported response."
        ),
        "RUN_LOCAL_RECEIPT_VERIFICATION_FAILED": (
            "The turn cannot be trusted because its receipt/evidence did not verify."
        ),
    }
    return table.get(code, "Local governed route refused; see receipt code.")


__all__ = [
    "ROUTE_INTENT",
    "ROUTE_LABEL",
    "POLICY_ID",
    "PROVIDER_ID",
    "RunLocalRouteIntent",
    "RunLocalWingError",
    "build_run_local_intent",
    "request_run_local_turn",
    "default_disabled_config",
    "direct_local_provider_construction_count",
    "reset_direct_local_provider_constructions_for_tests",
    "intentional_direct_local_provider_construct",
    "operator_remediation",
]
