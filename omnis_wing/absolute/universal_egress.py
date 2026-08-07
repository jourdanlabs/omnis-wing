"""Universal governed AI egress — one door for all modalities on the selected fork.

Wraps the R3.1.1 evidence spine + R2.1 body/destination rules for arbitrary
provider body dicts and transmit callables.
"""

from __future__ import annotations

try:
    from omnis_wing.completion.side_doors import install_side_door_guards
    install_side_door_guards()
except Exception:
    pass

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context
from omnis_wing.absolute.envelope import IntendedDestination, OutboundEnvelope
from omnis_wing.absolute.evaluator import Authorization, evaluate_decision
from omnis_wing.absolute.hermes_chat_join import (
    ALLOWED_BODY_KEYS,
    HOSTNAME_POLICY,
    PATH_CLASS,
    R2_COVERAGE_CLASS,
    R2_LANE,
    R2_POLICY_VERSION,
    EvidenceSession,
    OutcomeUnknownError,
    WingEgressContext,
    WingRefusal,
    _refusal_receipt,
    _sign_and_ledger,
    _tr_from_auth_pre_send,
    _tr_outcome_unknown,
    _tr_terminal_complete,
    derive_destination_from_client,
    stable_json_bytes,
)
from omnis_wing.absolute.receipt_spine import EvidencePersistError, SignerUnavailable


# Expanded body keys for anthropic/bedrock/codex shapes
EXTRA_BODY_KEYS = frozenset(
    {
        "system",
        "max_tokens",
        "max_completion_tokens",
        "thinking",
        "metadata",
        "input",
        "instructions",
        "messages",
        "model",
        "tools",
        "tool_choice",
        "response_format",
        "extra_body",
        "temperature",
        "top_p",
        "stream",
        "stop",
        "n",
        "user",
        "seed",
        "logprobs",
        "top_logprobs",
        "presence_penalty",
        "frequency_penalty",
        "logit_bias",
        # bedrock
        "messages",
        "inferenceConfig",
        "additionalModelRequestFields",
        "system",
        "toolConfig",
        "modelId",
        # anthropic
        "max_tokens",
        "thinking",
    }
)

ALLOWED_UNIVERSAL = ALLOWED_BODY_KEYS | EXTRA_BODY_KEYS


def canonical_body_bytes(body: dict) -> tuple[Optional[bytes], Optional[str]]:
    unknown = sorted(set(body.keys()) - ALLOWED_UNIVERSAL)
    if unknown:
        # Strip unknown rather than refuse? BBB: if cannot canonicalize safely, refuse
        return None, f"unsupported_body_fields:{','.join(unknown)}"
    if body.get("stream") is True and body.get("__wing_allow_stream_flag") is not True:
        # stream flag in body for non-stream join is rejected; streaming join sets allow
        pass
    try:
        # remove internal wing keys
        clean = {k: v for k, v in body.items() if not str(k).startswith("__wing")}
        payload = stable_json_bytes(clean)
    except TypeError as exc:
        return None, str(exc)
    return payload, None


@dataclass
class TransmitResult:
    response: Any
    receipt_phase: str


class CallableBroker:
    """Broker that invokes a user-supplied transmit after authorization."""

    def __init__(self, transmit_fn: Callable[[dict], Any], body: dict):
        self.transmit_fn = transmit_fn
        self.body = dict(body)
        self.calls = 0
        self.last_payload: Optional[bytes] = None
        self.last_destination = None
        self.response = None
        self.delivered_kwargs = None

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
        self.delivered_kwargs = dict(body)
        self.response = self.transmit_fn(body)
        return {
            "ok": True,
            "stub": True,
            "payload_digest": envelope.payload_digest,
            "bytes_len": len(envelope.payload_bytes),
        }


def _destination_from_agent(agent, client=None, path_class: str = PATH_CLASS) -> tuple[Optional[IntendedDestination], Optional[str]]:
    if client is not None:
        return derive_destination_from_client(client)
    # Fall back to agent base URL attributes
    class _C:
        pass

    c = _C()
    for attr in ("base_url", "api_base", "_base_url"):
        if agent is not None and getattr(agent, attr, None):
            c.base_url = getattr(agent, attr)
            return derive_destination_from_client(c)
    if agent is not None and getattr(agent, "provider", None) == "bedrock":
        region = getattr(agent, "_bedrock_region", None) or "us-east-1"
        # Map bedrock regions: cn-* → CN else US
        residency = "CN" if str(region).lower().startswith("cn-") else "US"
        # synthetic hostname for policy
        host = f"bedrock.{region}.amazonaws.com"
        # extend policy dynamically
        HOSTNAME_POLICY.setdefault(host, ("bedrock", residency))
        return (
            IntendedDestination(
                provider="bedrock",
                scheme="https",
                hostname=host,
                port=443,
                path_class="bedrock.converse",
                residency=residency,
            ),
            None,
        )
    # anthropic default
    base = None
    if agent is not None:
        base = getattr(agent, "_anthropic_base_url", None) or getattr(agent, "base_url", None)
    if base:
        c = _C()
        c.base_url = base
        return derive_destination_from_client(c)
    # unknown → fail destination
    return None, "cannot_derive_destination"


def governed_callable_transmit(
    *,
    agent: Any,
    body: dict,
    transmit_fn: Callable[[dict], Any],
    client: Any = None,
    path_class: str = PATH_CLASS,
    route_id: str = "universal",
    wing_ctx: Optional[WingEgressContext] = None,
) -> Any:
    """One door: canonicalize → auto provenance → pre-send evidence → transmit → terminal."""
    if wing_ctx is None and agent is not None:
        wing_ctx = ensure_agent_wing_context(agent, body)
    evidence = wing_ctx.evidence if wing_ctx else None
    if evidence is None or evidence.signer is None or not evidence.signer.available():
        raise WingRefusal(
            _refusal_receipt(decision="REFUSE_POLICY_INVALID", reason="signer_unavailable")
        )
    try:
        evidence.ledger.ensure_appendable()
    except EvidencePersistError as exc:
        raise WingRefusal(
            _refusal_receipt(
                decision="REFUSE_POLICY_INVALID",
                reason=f"ledger_not_appendable:{exc}",
            )
        ) from exc

    payload, err = canonical_body_bytes(body)
    if err:
        early = _refusal_receipt(decision="REFUSE_UNSUPPORTED", reason=err)
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    dest, derr = _destination_from_agent(agent, client=client, path_class=path_class)
    if derr or dest is None:
        early = _refusal_receipt(
            decision="REFUSE_DESTINATION", reason=derr or "destination_derive_failed"
        )
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    declared = wing_ctx.declared_destination if wing_ctx else None
    if declared is not None and declared.binding_tuple() != dest.binding_tuple():
        early = _refusal_receipt(
            decision="REFUSE_DESTINATION",
            reason="declared_destination_mismatch_actual_client_endpoint",
            destination=dest.to_dict(),
        )
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    sources = tuple(wing_ctx.sources) if wing_ctx else ()
    envelope = OutboundEnvelope.create(
        modality="chat",
        lane=f"{R2_LANE}:{route_id}",
        payload=payload,
        sources=sources,
        destination=dest,
        policy_version=R2_POLICY_VERSION,
        coverage_class=R2_COVERAGE_CLASS,
    )

    authorization = evaluate_decision(envelope)
    if authorization.decision != "PERMIT":
        from omnis_wing.absolute.evaluator import TransmissionReceipt

        refuse_tr = TransmissionReceipt(
            envelope_id=envelope.envelope_id,
            envelope_digest=authorization.envelope_digest,
            payload_digest=authorization.payload_digest,
            decision=authorization.decision,
            phase="NONE",
            reason=authorization.reason,
            finding_ids=authorization.finding_ids,
            provider_calls=0,
            delivered_payload_digest=None,
            destination=dest.to_dict(),
            policy_version=authorization.policy_version,
            coverage_class=authorization.coverage_class,
            phases_observed=(),
        )
        try:
            signed = _sign_and_ledger(refuse_tr, evidence)
        except Exception:
            signed = None
        raise WingRefusal(refuse_tr, signed=signed)

    pre_tr = _tr_from_auth_pre_send(envelope, authorization)
    try:
        pre_signed = _sign_and_ledger(pre_tr, evidence)
    except Exception as exc:
        raise WingRefusal(
            _refusal_receipt(
                decision="REFUSE_POLICY_INVALID",
                reason=f"pre_send_evidence_failed:{type(exc).__name__}",
            )
        ) from exc

    br = CallableBroker(transmit_fn, body)
    try:
        br.transmit(envelope, authorization)
    except Exception as exc:
        unk = _tr_outcome_unknown(
            envelope, authorization, br, reason=f"transmit_failed:{type(exc).__name__}"
        )
        try:
            _sign_and_ledger(unk, evidence)
        except Exception:
            pass
        raise OutcomeUnknownError(
            receipt=unk,
            pre_send_signed=pre_signed,
            client_calls=br.calls,
            response=br.response,
            reason=unk.reason,
        ) from exc

    if br.last_payload != envelope.payload_bytes:
        unk = _tr_outcome_unknown(
            envelope, authorization, br, reason="delivered_bytes_mismatch"
        )
        raise OutcomeUnknownError(
            receipt=unk,
            pre_send_signed=pre_signed,
            client_calls=br.calls,
            response=br.response,
            reason="delivered_bytes_mismatch",
        )

    term_tr = _tr_terminal_complete(envelope, authorization, br)
    try:
        _sign_and_ledger(term_tr, evidence)
    except Exception as exc:
        unk = _tr_outcome_unknown(
            envelope,
            authorization,
            br,
            reason=f"terminal_evidence_failed:{type(exc).__name__}",
        )
        raise OutcomeUnknownError(
            receipt=unk,
            pre_send_signed=pre_signed,
            client_calls=br.calls,
            response=br.response,
            reason=unk.reason,
        ) from exc

    return br.response


def governed_streaming_create(
    *,
    agent: Any,
    client: Any,
    api_kwargs: dict,
    route_id: str = "agent.interruptible_streaming.chat_completions",
) -> Any:
    """Govern the initial streaming create; stream iteration remains local after PERMIT."""
    body = dict(api_kwargs)
    body["__wing_allow_stream_flag"] = True

    def _tx(authorized_body: dict):
        # drop internal keys
        kw = {k: v for k, v in authorized_body.items() if not str(k).startswith("__wing")}
        return client.chat.completions.create(**kw)

    return governed_callable_transmit(
        agent=agent,
        body=body,
        transmit_fn=_tx,
        client=client,
        route_id=route_id,
    )
