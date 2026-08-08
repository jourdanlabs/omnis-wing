"""M2/M3 GOVERNED image modality join — hostile corpus parity with chat.

Product vision side-doors remain DISABLED until they call this path via
TransportBroker.transmit_image. This module is the sole image provider
dispatch implementation, reachable only under a broker transmit frame.

Destination binding is real: the final sender is always the broker-owned
method on the same ``client`` from which the authorized destination is
derived (``client.images.generations.create`` / ``client.create_image``).
No caller-supplied transport, callback, adapter, or invoke is accepted on
the product path — there is no ``transport=`` parameter.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from omnis_wing.absolute.auto_provenance import ensure_agent_wing_context
from omnis_wing.absolute.envelope import IntendedDestination, OutboundEnvelope
from omnis_wing.absolute.evaluator import Authorization, evaluate_decision
from omnis_wing.absolute.hermes_chat_join import (
    R2_COVERAGE_CLASS,
    R2_POLICY_VERSION,
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


def image_destination_from_client(
    client: Any,
) -> tuple[Optional[IntendedDestination], Optional[str]]:
    """Derive authorized image destination from the live client endpoint."""
    dest, derr = derive_destination_from_client(client)
    if derr or dest is None:
        return None, derr or "destination_derive_failed"
    return (
        IntendedDestination(
            provider=dest.provider,
            scheme=dest.scheme,
            hostname=dest.hostname,
            port=dest.port,
            path_class=IMAGE_PATH_CLASS,
            residency=dest.residency,
        ),
        None,
    )


def _client_images_generations_create(client: Any, body: dict) -> Any:
    """Broker-owned final image invoke on the bound client object only."""
    images = getattr(client, "images", None)
    if images is not None:
        gens = getattr(images, "generations", None)
        if gens is not None and callable(getattr(gens, "create", None)):
            return gens.create(**body)
    # Explicit image create hook used by fakes
    create_image = getattr(client, "create_image", None)
    if callable(create_image):
        return create_image(**body)
    raise RuntimeError("client_lacks_images_generations_create")


class _ImageBroker:
    """Owns final image provider dispatch; invoke only on authorized client."""

    def __init__(self, client: Any, authorized_dest: IntendedDestination):
        self.client = client
        self.authorized_dest = authorized_dest
        self.calls = 0
        self.last_payload: Optional[bytes] = None
        self.last_destination: Optional[tuple] = None
        self.response = None
        self.delivered_body: Any = None

    def transmit(self, envelope: OutboundEnvelope, authorization: Authorization) -> dict:
        if authorization.decision != "PERMIT":
            raise RuntimeError("broker_called_without_permit")
        if authorization.payload_digest != envelope.payload_digest:
            raise RuntimeError("broker_payload_digest_mismatch")
        env_binding = envelope.intended_destination.binding_tuple()
        if authorization.destination_binding != env_binding:
            raise RuntimeError("broker_destination_mismatch")
        # Authorized dest must match the client-derived destination used at join.
        if self.authorized_dest.binding_tuple() != authorization.destination_binding:
            raise RuntimeError("image_client_destination_mismatch")
        if self.authorized_dest.binding_tuple() != env_binding:
            raise RuntimeError("image_envelope_destination_mismatch")

        self.calls += 1
        self.last_payload = bytes(envelope.payload_bytes)
        self.last_destination = env_binding
        body = json.loads(envelope.payload_bytes.decode("utf-8"))
        if not isinstance(body, dict):
            raise RuntimeError("canonical_body_not_object")
        self.delivered_body = body
        # Sole final sender: method on the same client that bound the dest.
        self.response = _client_images_generations_create(self.client, body)
        return {
            "ok": True,
            "payload_digest": envelope.payload_digest,
            "bytes_len": len(envelope.payload_bytes),
        }


def _refuse_dest(
    *,
    reason: str,
    evidence: Any,
    destination: Optional[dict] = None,
) -> WingRefusal:
    early = _refusal_receipt(
        decision="REFUSE_DESTINATION",
        reason=reason,
        destination=destination or {},
    )
    try:
        signed = _sign_and_ledger(early, evidence)
    except Exception:
        signed = None
    return WingRefusal(early, signed=signed)


def governed_image_transmit(
    *,
    agent: Any,
    body: dict,
    client: Any,
    wing_ctx: Optional[WingEgressContext] = None,
    route_id: str = "image.governed",
) -> Any:
    """Internal image join — only under TransportBroker.transmit_image frame.

    ``client`` is required. Final send is always broker-owned
    ``client.images.generations.create`` (or ``client.create_image``). There is
    no transport / callback / adapter parameter.
    """
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

    if client is None:
        raise _refuse_dest(reason="missing_client", evidence=evidence)

    ok_redir, redir_reason = assert_no_redirect_transport(client)
    if not ok_redir:
        raise _refuse_dest(
            reason=redir_reason or "redirect_enabled", evidence=evidence
        )

    dest, derr = image_destination_from_client(client)
    if derr or dest is None:
        raise _refuse_dest(
            reason=derr or "destination_derive_failed", evidence=evidence
        )

    payload, err = canonical_image_body(body)
    if err:
        early = _refusal_receipt(decision="REFUSE_UNSUPPORTED", reason=err)
        try:
            signed = _sign_and_ledger(early, evidence)
        except Exception:
            signed = None
        raise WingRefusal(early, signed=signed)

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

    # Post-auth: authorized destination must still match client-derived dest.
    if dest.binding_tuple() != authorization.destination_binding:
        raise _refuse_dest(
            reason="image_client_destination_mismatch_post_auth",
            evidence=evidence,
            destination=dest.to_dict(),
        )

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

    br = _ImageBroker(client, dest)
    try:
        br.transmit(envelope, authorization)
    except RuntimeError as exc:
        # Binding failures after PERMIT must not count as a successful send.
        if br.calls == 0:
            raise _refuse_dest(
                reason=str(exc),
                evidence=evidence,
                destination=dest.to_dict(),
            ) from exc
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
