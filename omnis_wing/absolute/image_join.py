"""M2/M3 GOVERNED image modality join — hostile corpus parity with chat.

Product vision side-doors remain DISABLED until they call this path via
TransportBroker.transmit_image. This module is the sole image provider
dispatch implementation, reachable only under a broker transmit frame.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context
from omnis_wing.absolute.envelope import OutboundEnvelope
from omnis_wing.absolute.evaluator import Authorization, evaluate_decision
from omnis_wing.absolute.hermes_chat_join import (
    R2_COVERAGE_CLASS,
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
from omnis_wing.absolute.receipt_spine import EvidencePersistError
from omnis_wing.absolute.redirect_guard import assert_no_redirect_transport

IMAGE_PATH_CLASS = "images.generations"
IMAGE_LANE = "wing.image.governed"
ALLOWED_IMAGE_KEYS = frozenset(
    {
        "model",
        "prompt",
        "n",
        "size",
        "quality",
        "style",
        "response_format",
        "user",
        "messages",  # vision chat-shaped
        "image",
        "images",
        "extra_body",
    }
)


def canonical_image_body(body: dict) -> tuple[Optional[bytes], Optional[str]]:
    clean = {k: v for k, v in body.items() if not str(k).startswith("__wing")}
    unknown = sorted(set(clean.keys()) - ALLOWED_IMAGE_KEYS)
    if unknown:
        return None, f"unsupported_body_fields:{','.join(unknown)}"
    try:
        return stable_json_bytes(clean), None
    except TypeError as exc:
        return None, str(exc)


class _ImageBroker:
    def __init__(self, transmit_fn: Callable[[dict], Any]):
        self.transmit_fn = transmit_fn
        self.calls = 0
        self.last_payload: Optional[bytes] = None
        self.response = None

    def transmit(self, envelope: OutboundEnvelope, authorization: Authorization) -> dict:
        if authorization.decision != "PERMIT":
            raise RuntimeError("broker_called_without_permit")
        if authorization.payload_digest != envelope.payload_digest:
            raise RuntimeError("broker_payload_digest_mismatch")
        self.calls += 1
        self.last_payload = bytes(envelope.payload_bytes)
        body = json.loads(envelope.payload_bytes.decode("utf-8"))
        self.response = self.transmit_fn(body)
        return {"ok": True, "payload_digest": envelope.payload_digest}


def governed_image_transmit(
    *,
    agent: Any,
    body: dict,
    transmit_fn: Callable[[dict], Any],
    client: Any = None,
    wing_ctx: Optional[WingEgressContext] = None,
    route_id: str = "image.governed",
) -> Any:
    """Internal image join — only under TransportBroker.transmit_image frame."""
    from omnis_wing.absolute.broker_guard import require_broker_dispatch

    require_broker_dispatch("governed_image_transmit")

    if wing_ctx is None and agent is not None:
        wing_ctx = ensure_agent_wing_context(agent, body)
    evidence = wing_ctx.evidence if wing_ctx else None
    signer = getattr(evidence, "signer", None) if evidence is not None else None
    avail = getattr(signer, "available", None)
    if evidence is None or signer is None or not (avail() if callable(avail) else False):
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

    ok_redir, redir_reason = assert_no_redirect_transport(client)
    if not ok_redir:
        early = _refusal_receipt(
            decision="REFUSE_DESTINATION",
            reason=redir_reason or "redirect_enabled",
        )
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    payload, err = canonical_image_body(body)
    if err:
        early = _refusal_receipt(decision="REFUSE_UNSUPPORTED", reason=err)
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    if client is not None:
        dest, derr = derive_destination_from_client(client)
    else:
        dest, derr = None, "missing_client_base_url"
    if derr or dest is None:
        # re-bind path_class for image
        early = _refusal_receipt(
            decision="REFUSE_DESTINATION", reason=derr or "destination_derive_failed"
        )
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

    # Force image path_class on destination binding
    from omnis_wing.absolute.envelope import IntendedDestination

    dest = IntendedDestination(
        provider=dest.provider,
        scheme=dest.scheme,
        hostname=dest.hostname,
        port=dest.port,
        path_class=IMAGE_PATH_CLASS,
        residency=dest.residency,
    )

    from omnis_wing.absolute.payload_policy import analyze_body, analyze_payload_bytes

    clean_body = {k: v for k, v in body.items() if not str(k).startswith("__wing")}
    body_sources, _ = analyze_body(clean_body)
    if not body_sources:
        body_sources, _ = analyze_payload_bytes(payload)  # type: ignore[arg-type]
    envelope = OutboundEnvelope.create(
        modality="image",
        lane=f"{IMAGE_LANE}:{route_id}",
        payload=payload,  # type: ignore[arg-type]
        sources=body_sources,
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

    br = _ImageBroker(transmit_fn)
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

    term = _tr_terminal_complete(envelope, authorization, br)
    try:
        _sign_and_ledger(term, evidence)
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
