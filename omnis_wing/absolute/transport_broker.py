"""M2 TransportBroker — sole owner of outbound provider transmits on WING fork.

No other module may own an outbound provider socket/client call for AI payload
routes. All GOVERNED routes enter here. Governed implementation functions are
not public agent API — they are reachable only when a real
``TransportBroker.transmit_*`` frame is on the stack (runtime gate) and agent
trees must not import them (source guard).

There is no public enterable scope token. Final provider-dispatch ownership is
structurally confined to this class's transmit methods.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional, Set

from omnis_wing.absolute.broker_guard import BrokerViolation
from omnis_wing.absolute.universal_egress import (
    governed_callable_transmit,
    governed_streaming_create,
)
from omnis_wing.absolute.hermes_chat_join import governed_chat_completions_create

_lock = threading.RLock()
_REGISTERED_TRANSPORTS: Set[str] = set()

__all__ = [
    "BrokerViolation",
    "TransportBroker",
    "get_broker",
    "assert_broker_only_import",
    "broker_seen_routes",
    "reset_broker_for_tests",
]


@dataclass
class TransportBroker:
    """Process-wide singleton — owns final provider dispatch for AI egress."""

    _instance_id: str = "wing-transport-broker-v1"

    def transmit_chat_completions(self, client: Any, api_kwargs: dict, wing_ctx: Any) -> Any:
        with _lock:
            _REGISTERED_TRANSPORTS.add("chat_completions")
        # Stack frame of this method is the sole runtime authority for
        # require_broker_dispatch inside the governed implementation.
        return governed_chat_completions_create(client, api_kwargs, wing_ctx)

    def transmit_callable(
        self,
        *,
        agent: Any,
        body: dict,
        transmit_fn: Callable[[dict], Any],
        client: Any = None,
        route_id: str = "universal",
        path_class: str = "chat.completions",
        wing_ctx: Any = None,
    ) -> Any:
        with _lock:
            _REGISTERED_TRANSPORTS.add(route_id)
        return governed_callable_transmit(
            agent=agent,
            body=body,
            transmit_fn=transmit_fn,
            client=client,
            path_class=path_class,
            route_id=route_id,
            wing_ctx=wing_ctx,
        )

    def transmit_streaming(
        self,
        *,
        agent: Any,
        client: Any,
        api_kwargs: dict,
        route_id: str = "stream",
    ) -> Any:
        with _lock:
            _REGISTERED_TRANSPORTS.add(route_id)
        return governed_streaming_create(
            agent=agent, client=client, api_kwargs=api_kwargs, route_id=route_id
        )


_BROKER: Optional[TransportBroker] = None


def get_broker() -> TransportBroker:
    global _BROKER
    with _lock:
        if _BROKER is None:
            _BROKER = TransportBroker()
        return _BROKER


def reset_broker_for_tests() -> None:
    """Drop singleton + seen routes. Tests only."""
    global _BROKER
    with _lock:
        _BROKER = None
        _REGISTERED_TRANSPORTS.clear()


def assert_broker_only_import(module_name: str, attr: str) -> None:
    """Runtime guard helper for conformance tests."""
    banned = {
        "openai.OpenAI",
        "anthropic.Anthropic",
        "httpx.Client.send",
    }
    key = f"{module_name}.{attr}"
    if key in banned:
        raise BrokerViolation(f"direct_transport_forbidden:{key}")


def broker_seen_routes() -> Set[str]:
    with _lock:
        return set(_REGISTERED_TRANSPORTS)
