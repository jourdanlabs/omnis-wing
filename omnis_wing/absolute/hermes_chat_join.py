"""R2.1 join: ordinary Hermes non-streaming chat.completions → WING boundary.

Selected production path:
  AIAgent._interruptible_api_call
    → agent.chat_completion_helpers.interruptible_api_call
      → _call() [chat_completions]
        → governed_chat_completions_create
          → canonical provider-request BODY (all forwarded fields)
          → OutboundEnvelope.payload_bytes
          → dispatch_outbound
          → broker reconstructs create(**body) from evaluated bytes only
          → destination derived from actual client.base_url + policy map

P0-A closed: no unscanned api_kwargs ride-along.
P0-B closed: context cannot bless a route; actual endpoint binds authorization.

Outside claim (still):
  HTTP/TLS framing, auth headers, SDK transport internals — not body fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from omnis_wing.absolute.envelope import (
    POLICY_VERSION,
    IntendedDestination,
    OutboundEnvelope,
    SourceProvenance,
)
from omnis_wing.absolute.evaluator import (
    Authorization,
    RecordingBroker,
    TransmissionReceipt,
)
from omnis_wing.absolute.host import dispatch_outbound
from omnis_wing.absolute.receipt_spine import (
    EvidenceLedger,
    Signer,
    SignerUnavailable,
    UnavailableSigner,
    build_signed_receipt,
    make_test_signer,
)

R2_COVERAGE_CLASS = "AI_EGRESS_GOVERNED_R2_CHAT_COMPLETIONS_JOIN"
R2_LANE = "hermes.chat_completions.non_stream"
R2_POLICY_VERSION = POLICY_VERSION
PATH_CLASS = "chat.completions"

# Body fields this join may forward. Anything else → REFUSE_UNSUPPORTED.
ALLOWED_BODY_KEYS = frozenset(
    {
        "messages",
        "model",
        "tools",
        "tool_choice",
        "response_format",
        "extra_body",
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "n",
        "stop",
        "stream",
        "presence_penalty",
        "frequency_penalty",
        "logit_bias",
        "user",
        "seed",
        "logprobs",
        "top_logprobs",
    }
)

# Controlled R2 policy map: hostname → (provider, residency). Not caller assertion.
HOSTNAME_POLICY: dict[str, tuple[str, str]] = {
    "ai.example.test": ("stub-local", "US"),
    "api.openai.com": ("openai", "US"),
    "api.x.ai": ("xai", "US"),
    "api.fireworks.ai": ("fireworks", "US"),
    "api.moonshot.cn": ("moonshot", "CN"),
    "api.moonshot.ai": ("moonshot", "US"),
    "localhost": ("local", "LOCAL"),
    "127.0.0.1": ("local", "LOCAL"),
}


class WingRefusal(Exception):
    def __init__(self, receipt: TransmissionReceipt, signed=None):
        self.receipt = receipt
        self.signed = signed
        super().__init__(
            f"WING {receipt.decision} phase={receipt.phase}: {receipt.reason}"
        )


@dataclass
class EvidenceSession:
    """R3 evidence spine handles for the selected path (test-only signer OK)."""

    signer: object  # Signer protocol
    ledger: EvidenceLedger
    last_signed: object | None = None


@dataclass
class WingEgressContext:
    """Source provenance for the selected chat path.

    Destination is NOT authoritative. Optional declared_destination, if present,
    must exactly match the destination derived from the actual client endpoint.

    evidence: R3 spine session; missing/unavailable signer → REFUSE_POLICY_INVALID
    before broker call.
    """

    sources: tuple[SourceProvenance, ...]
    declared_destination: Optional[IntendedDestination] = None
    lane: str = R2_LANE
    policy_version: str = R2_POLICY_VERSION
    coverage_class: str = R2_COVERAGE_CLASS
    evidence: Optional[EvidenceSession] = None

    @property
    def destination(self) -> Optional[IntendedDestination]:
        return self.declared_destination


def _json_default(obj: Any) -> Any:
    raise TypeError(f"non_json_serializable:{type(obj).__name__}")


def stable_json_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    ).encode("utf-8")


def canonical_provider_request_body(
    api_kwargs: dict,
) -> tuple[Optional[bytes], Optional[dict], Optional[str]]:
    """
    Deterministic canonical representation of every outbound request-body field.
    Returns (payload_bytes, body_dict, error_reason).
    """
    unknown = sorted(set(api_kwargs.keys()) - ALLOWED_BODY_KEYS)
    if unknown:
        return None, None, f"unsupported_body_fields:{','.join(unknown)}"

    if api_kwargs.get("stream") is True:
        return None, None, "stream_true_not_on_non_stream_join"

    body: dict[str, Any] = {}
    for key in sorted(api_kwargs.keys()):
        body[key] = api_kwargs[key]

    # Ensure messages key exists (may be empty list)
    if "messages" not in body:
        body["messages"] = []

    try:
        payload = stable_json_bytes(body)
    except TypeError as exc:
        return None, None, str(exc)

    return payload, body, None


# Back-compat helper name used in older tests
def canonical_messages_payload_bytes(messages: Any) -> bytes:
    return stable_json_bytes(messages)


def _extract_base_url(client: Any) -> str:
    for attr in ("base_url", "api_base", "base_api"):
        val = getattr(client, attr, None)
        if val is not None and str(val).strip():
            return str(val).strip().rstrip("/")
    inner = getattr(client, "_client", None)
    if inner is not None:
        val = getattr(inner, "base_url", None)
        if val is not None and str(val).strip():
            return str(val).strip().rstrip("/")
    return ""


def _parse_endpoint(raw: str) -> tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    """Minimal URL parse without urllib (import-guard safe). Returns scheme, host, port, err."""
    s = raw.strip()
    if "://" not in s:
        s = "https://" + s
    try:
        scheme, rest = s.split("://", 1)
    except ValueError:
        return None, None, None, "unparseable_client_base_url"
    scheme = scheme.lower()
    # drop path/query
    hostport = rest.split("/", 1)[0]
    hostport = hostport.split("?", 1)[0]
    if not hostport:
        return None, None, None, "unparseable_client_base_url"
    if hostport.startswith("["):
        # ipv6 not needed in R2.1 policy map
        return None, None, None, "ipv6_not_supported_r21"
    if ":" in hostport:
        host, port_s = hostport.rsplit(":", 1)
        try:
            port = int(port_s)
        except ValueError:
            return None, None, None, "unparseable_port"
    else:
        host = hostport
        port = 443 if scheme == "https" else 80
    host = host.lower()
    if not host or not scheme:
        return None, None, None, "unparseable_client_base_url"
    return scheme, host, port, None


def derive_destination_from_client(client: Any) -> tuple[Optional[IntendedDestination], Optional[str]]:
    """Derive scheme/host/port/path_class/provider/residency from actual client config."""
    raw = _extract_base_url(client)
    if not raw:
        return None, "missing_client_base_url"

    scheme, hostname, port, perr = _parse_endpoint(raw)
    if perr or not scheme or not hostname or port is None:
        return None, perr or "unparseable_client_base_url"

    policy = HOSTNAME_POLICY.get(hostname)
    if policy is None:
        return None, f"hostname_not_in_r2_policy_map:{hostname}"

    provider, residency = policy
    dest = IntendedDestination(
        provider=provider,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path_class=PATH_CLASS,
        residency=residency,
    )
    return dest, None


def _refusal_receipt(
    *,
    decision: str,
    reason: str,
    envelope_id: str = "ungoverned",
    envelope_digest: str = "",
    payload_digest: str = "",
    destination: Optional[dict] = None,
    policy_version: str = R2_POLICY_VERSION,
    coverage_class: str = R2_COVERAGE_CLASS,
) -> TransmissionReceipt:
    return TransmissionReceipt(
        envelope_id=envelope_id,
        envelope_digest=envelope_digest or ("0" * 64),
        payload_digest=payload_digest or ("0" * 64),
        decision=decision,  # type: ignore[arg-type]
        phase="NONE",
        reason=reason,
        finding_ids=(),
        provider_calls=0,
        delivered_payload_digest=None,
        destination=destination or {},
        policy_version=policy_version,
        coverage_class=coverage_class,
        phases_observed=(),
    )


class ChatCompletionsClientBroker(RecordingBroker):
    """Reconstructs create() solely from evaluated canonical body bytes."""

    def __init__(self, client: Any):
        super().__init__()
        self.client = client
        self.response: Any = None
        self.delivered_body: Any = None
        self.delivered_kwargs: dict = {}

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

        body = json.loads(envelope.payload_bytes.decode("utf-8"))
        if not isinstance(body, dict):
            raise RuntimeError("canonical_body_not_object")
        self.delivered_body = body
        self.delivered_kwargs = dict(body)
        # Sole client invocation — kwargs only from evaluated body
        self.response = self.client.chat.completions.create(**self.delivered_kwargs)
        return {
            "ok": True,
            "stub": getattr(self.client, "is_fake", False),
            "payload_digest": envelope.payload_digest,
            "bytes_len": len(envelope.payload_bytes),
        }


def build_envelope_for_chat(
    api_kwargs: dict,
    wing_ctx: Optional[WingEgressContext],
    client: Any,
) -> tuple[Optional[OutboundEnvelope], Optional[TransmissionReceipt]]:
    """Build envelope or return a pre-broker refusal receipt."""
    payload, _body, err = canonical_provider_request_body(api_kwargs)
    if err is not None:
        return None, _refusal_receipt(decision="REFUSE_UNSUPPORTED", reason=err)

    dest, derr = derive_destination_from_client(client)
    if derr is not None or dest is None:
        return None, _refusal_receipt(
            decision="REFUSE_DESTINATION",
            reason=derr or "destination_derive_failed",
        )

    if wing_ctx is None:
        sources: tuple[SourceProvenance, ...] = ()
        lane = R2_LANE
        policy_version = R2_POLICY_VERSION
        coverage_class = R2_COVERAGE_CLASS
        declared = None
    else:
        sources = tuple(wing_ctx.sources)
        lane = wing_ctx.lane
        policy_version = wing_ctx.policy_version
        coverage_class = wing_ctx.coverage_class
        declared = wing_ctx.declared_destination or wing_ctx.destination

    if declared is not None and declared.binding_tuple() != dest.binding_tuple():
        return None, _refusal_receipt(
            decision="REFUSE_DESTINATION",
            reason="declared_destination_mismatch_actual_client_endpoint",
            destination=dest.to_dict(),
            policy_version=policy_version,
            coverage_class=coverage_class,
        )

    assert payload is not None
    env = OutboundEnvelope.create(
        modality="chat",
        lane=lane,
        payload=payload,
        sources=sources,
        destination=dest,
        policy_version=policy_version,
        coverage_class=coverage_class,
    )
    return env, None


def _resolve_evidence(wing_ctx: Optional[WingEgressContext]) -> Optional[EvidenceSession]:
    if wing_ctx is None:
        return None
    return wing_ctx.evidence


def _sign_and_ledger(
    tr: TransmissionReceipt,
    evidence: Optional[EvidenceSession],
) -> object | None:
    """Create signed receipt and append ledger when evidence session present."""
    if evidence is None:
        return None
    signer = evidence.signer
    ledger = evidence.ledger
    signed = build_signed_receipt(
        tr,
        signer=signer,
        previous_digest=ledger.head_digest(),
        sequence=ledger.next_sequence(),
    )
    ledger.append(signed)
    evidence.last_signed = signed
    return signed


def governed_chat_completions_create(
    client: Any,
    api_kwargs: dict,
    wing_ctx: Optional[WingEgressContext],
    *,
    broker: Optional[ChatCompletionsClientBroker] = None,
) -> Any:
    """Sole outbound join for selected non-streaming chat_completions path.

    R3: evidence.signer must be available before any broker/client call.
    """
    evidence = _resolve_evidence(wing_ctx)
    # Fail-closed signer gate (before envelope broker / client)
    if evidence is None or evidence.signer is None or not evidence.signer.available():
        early = _refusal_receipt(
            decision="REFUSE_POLICY_INVALID",
            reason="signer_unavailable",
        )
        raise WingRefusal(early)

    envelope, early = build_envelope_for_chat(api_kwargs, wing_ctx, client)
    if early is not None:
        signed = _sign_and_ledger(early, evidence)
        raise WingRefusal(early, signed=signed)
    assert envelope is not None

    br = broker or ChatCompletionsClientBroker(client)
    receipt = dispatch_outbound(envelope, br)
    signed = _sign_and_ledger(receipt, evidence)
    if receipt.decision != "PERMIT" or receipt.phase != "TRANSMISSION_COMPLETED":
        raise WingRefusal(receipt, signed=signed)
    if br.last_payload != envelope.payload_bytes:
        raise RuntimeError("delivered_payload_bytes_mismatch")
    if br.delivered_kwargs is not None:
        rebuilt = stable_json_bytes(br.delivered_kwargs)
        if rebuilt != envelope.payload_bytes:
            raise RuntimeError("delivered_body_canonical_mismatch")
    return br.response


def resolve_wing_context(agent: Any) -> Optional[WingEgressContext]:
    return getattr(agent, "wing_egress_context", None)
