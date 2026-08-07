"""R2 join: ordinary Hermes non-streaming chat.completions → WING R1.1 boundary.

Selected production path (documented in BUILD_HANDOFF):
  AIAgent._interruptible_api_call
    → agent.chat_completion_helpers.interruptible_api_call
      → _call() [api_mode default / chat_completions]
        → omnis_wing.absolute.hermes_chat_join.governed_chat_completions_create
          → OutboundEnvelope(payload_bytes = canonical messages JSON)
          → decide_and_execute / dispatch_outbound
          → injected client.chat.completions.create ONLY via broker.transmit

Outside R2 (not claimed equal to envelope bytes):
  - provider SDK HTTP framing, auth headers, base_url path
  - model / temperature / tools / extra_body fields on api_kwargs
    (messages alone are the envelope payload; other kwargs ride along
     after PERMIT and are labelled outside payload equality)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from omnis_wing.absolute.envelope import (
    COVERAGE_CLASS,
    POLICY_VERSION,
    IntendedDestination,
    OutboundEnvelope,
    SourceProvenance,
)
from omnis_wing.absolute.evaluator import (
    Authorization,
    RecordingBroker,
    TransmissionReceipt,
    decide_and_execute,
)
from omnis_wing.absolute.host import dispatch_outbound

# R2 coverage class — seam is the chat join only
R2_COVERAGE_CLASS = "AI_EGRESS_GOVERNED_R2_CHAT_COMPLETIONS_JOIN"
R2_LANE = "hermes.chat_completions.non_stream"
R2_POLICY_VERSION = POLICY_VERSION


class WingRefusal(Exception):
    """Raised when WING refuses before or without completed transmission."""

    def __init__(self, receipt: TransmissionReceipt):
        self.receipt = receipt
        super().__init__(
            f"WING {receipt.decision} phase={receipt.phase}: {receipt.reason}"
        )


@dataclass
class WingEgressContext:
    """Explicit provenance + destination for the selected chat path."""

    sources: tuple[SourceProvenance, ...]
    destination: IntendedDestination
    lane: str = R2_LANE
    policy_version: str = R2_POLICY_VERSION
    coverage_class: str = R2_COVERAGE_CLASS


def canonical_messages_payload_bytes(messages: Any) -> bytes:
    """Exact chat message bytes placed on the envelope and re-delivered to the client.

    Message order preserved. Separators compact. UTF-8.
    This is the R2 equality boundary — not the full HTTP request.
    """
    return json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class ChatCompletionsClientBroker(RecordingBroker):
    """Broker that invokes the OpenAI-compatible client's create once with
    messages decoded from the authorized envelope payload bytes.
    """

    def __init__(self, client: Any, api_kwargs: dict):
        super().__init__()
        self.client = client
        self.api_kwargs = dict(api_kwargs)
        self.response: Any = None
        self.delivered_messages: Any = None
        # Fields sent alongside messages but outside envelope equality claim
        self.outside_r2_kwargs_keys: tuple[str, ...] = tuple(
            sorted(k for k in api_kwargs.keys() if k != "messages")
        )

    def transmit(self, envelope: OutboundEnvelope, authorization: Authorization) -> dict:
        if authorization.destination_binding != envelope.intended_destination.binding_tuple():
            raise RuntimeError("broker_destination_mismatch")
        if authorization.payload_digest != envelope.payload_digest:
            raise RuntimeError("broker_payload_digest_mismatch")
        if authorization.decision != "PERMIT":
            raise RuntimeError("broker_called_without_permit")

        self.calls += 1
        self.last_payload = bytes(envelope.payload_bytes)
        self.last_destination = envelope.intended_destination.binding_tuple()

        messages = json.loads(envelope.payload_bytes.decode("utf-8"))
        self.delivered_messages = messages
        kwargs = dict(self.api_kwargs)
        kwargs["messages"] = messages
        # Sole client invocation on this path
        self.response = self.client.chat.completions.create(**kwargs)
        return {
            "ok": True,
            "stub": getattr(self.client, "is_fake", False),
            "payload_digest": envelope.payload_digest,
            "bytes_len": len(envelope.payload_bytes),
        }


def build_envelope_for_chat(
    api_kwargs: dict,
    wing_ctx: Optional[WingEgressContext],
) -> OutboundEnvelope:
    messages = api_kwargs.get("messages")
    if messages is None:
        messages = []
    payload = canonical_messages_payload_bytes(messages)

    if wing_ctx is None:
        # Missing context ⇒ missing provenance (must refuse)
        sources: tuple[SourceProvenance, ...] = ()
        destination = IntendedDestination(
            provider="unspecified",
            scheme="https",
            hostname="unspecified.invalid",
            port=443,
            path_class="chat.completions",
            residency="US",
        )
        lane = R2_LANE
        policy_version = R2_POLICY_VERSION
        coverage_class = R2_COVERAGE_CLASS
    else:
        sources = tuple(wing_ctx.sources)
        destination = wing_ctx.destination
        lane = wing_ctx.lane
        policy_version = wing_ctx.policy_version
        coverage_class = wing_ctx.coverage_class

    return OutboundEnvelope.create(
        modality="chat",
        lane=lane,
        payload=payload,
        sources=sources,
        destination=destination,
        policy_version=policy_version,
        coverage_class=coverage_class,
    )


def governed_chat_completions_create(
    client: Any,
    api_kwargs: dict,
    wing_ctx: Optional[WingEgressContext],
    *,
    broker: Optional[ChatCompletionsClientBroker] = None,
) -> Any:
    """
    Sole outbound join for the selected non-streaming chat_completions path.
    Always runs dispatch_outbound before any client.chat.completions.create.
    """
    envelope = build_envelope_for_chat(api_kwargs, wing_ctx)
    br = broker or ChatCompletionsClientBroker(client, api_kwargs)
    receipt = dispatch_outbound(envelope, br)
    if receipt.decision != "PERMIT" or receipt.phase != "TRANSMISSION_COMPLETED":
        raise WingRefusal(receipt)
    # Byte equality proof surface for tests
    if br.last_payload != envelope.payload_bytes:
        raise RuntimeError("delivered_payload_bytes_mismatch")
    return br.response


def resolve_wing_context(agent: Any) -> Optional[WingEgressContext]:
    """Pull explicit context from the agent; None means missing provenance."""
    return getattr(agent, "wing_egress_context", None)
