"""ABSOLUTE decision grammar + phase outcomes for OMNIS WING R1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Callable, List, Literal, Optional, Sequence

from .envelope import IntendedDestination, OutboundEnvelope, SourceProvenance
from .scanner import scan_envelope, source_policy_violations

Decision = Literal[
    "PERMIT",
    "REFUSE_RESIDENCY",
    "REFUSE_SOURCE_POLICY",
    "REFUSE_SECRET",
    "REFUSE_SCANNER_FAILURE",
    "REFUSE_DESTINATION",
    "REFUSE_POLICY_INVALID",
    "REFUSE_CROWN_JEWEL",
]

Phase = Literal[
    "AUTHORIZED",
    "TRANSMISSION_STARTED",
    "TRANSMISSION_COMPLETED",
    "FAILED_AFTER_TRANSMISSION_STARTED",
    "OUTCOME_UNKNOWN",
    "NONE",
]

ALLOWED_GENERIC_RESIDENCIES = frozenset({"US", "EU", "LOCAL"})
CN_RESIDENCIES = frozenset({"CN"})


@dataclass(frozen=True)
class Authorization:
    decision: Decision
    envelope_digest: str
    payload_digest: str
    destination_binding: tuple
    policy_version: str
    coverage_class: str
    reason: str
    finding_ids: tuple


@dataclass(frozen=True)
class TransmissionReceipt:
    envelope_id: str
    envelope_digest: str
    payload_digest: str
    decision: Decision
    phase: Phase
    reason: str
    finding_ids: tuple
    provider_calls: int
    delivered_payload_digest: Optional[str]
    destination: dict
    policy_version: str
    coverage_class: str
    phases_observed: tuple

    def to_dict(self) -> dict:
        return asdict(self)

    def serialize_for_hygiene(self) -> str:
        return str(self.to_dict())


def _refusal_receipt(
    envelope: OutboundEnvelope,
    decision: Decision,
    reason: str,
    finding_ids: tuple = (),
    phases_observed: tuple = (),
) -> TransmissionReceipt:
    return TransmissionReceipt(
        envelope_id=envelope.envelope_id,
        envelope_digest=envelope.envelope_digest(),
        payload_digest=envelope.payload_digest,
        decision=decision,
        phase="NONE",
        reason=reason,
        finding_ids=finding_ids,
        provider_calls=0,
        delivered_payload_digest=None,
        destination=envelope.intended_destination.to_dict(),
        policy_version=envelope.policy_version,
        coverage_class=envelope.coverage_class,
        phases_observed=phases_observed,
    )


def evaluate_decision(
    envelope: OutboundEnvelope,
    *,
    inject_scanner_failure: bool = False,
    authorized_destination: Optional[IntendedDestination] = None,
) -> Authorization:
    ed = envelope.envelope_digest()
    dest = envelope.intended_destination
    binding = dest.binding_tuple()

    def auth(decision: Decision, reason: str, finding_ids: Sequence[str] = ()) -> Authorization:
        return Authorization(
            decision=decision,
            envelope_digest=ed,
            payload_digest=envelope.payload_digest,
            destination_binding=binding,
            policy_version=envelope.policy_version,
            coverage_class=envelope.coverage_class,
            reason=reason,
            finding_ids=tuple(finding_ids),
        )

    if not envelope.policy_version or not envelope.coverage_class:
        return auth("REFUSE_POLICY_INVALID", "missing policy_version or coverage_class")
    if dest.scheme not in ("https", "http"):
        return auth("REFUSE_DESTINATION", "invalid scheme")
    if dest.scheme != "https" and dest.residency.upper() not in ("LOCAL",):
        return auth("REFUSE_DESTINATION", "external providers require https")
    if not dest.hostname or not dest.provider or int(dest.port) <= 0:
        return auth("REFUSE_DESTINATION", "incomplete destination")
    # ABSOLUTE destination binding requires non-empty endpoint/path class (H6).
    path_class = (dest.path_class or "").strip()
    if not path_class:
        return auth("REFUSE_DESTINATION", "empty or blank path_class")

    if authorized_destination is not None:
        if authorized_destination.binding_tuple() != binding:
            return auth("REFUSE_DESTINATION", "destination mutated after authorization")

    scan_result = scan_envelope(envelope, inject_failure=inject_scanner_failure)
    if scan_result.error:
        return auth("REFUSE_SCANNER_FAILURE", scan_result.error)
    if not scan_result.ok:
        ids = tuple(f.finding_id for f in scan_result.findings)
        return auth("REFUSE_SECRET", "deterministic scanner refused payload", ids)

    if not envelope.sources:
        return auth("REFUSE_SOURCE_POLICY", "missing source provenance")

    src_codes = source_policy_violations(envelope.sources, require_provenance=True)
    for code in src_codes:
        return auth("REFUSE_SOURCE_POLICY", code)

    for s in envelope.sources:
        if s.crown_jewel:
            return auth("REFUSE_CROWN_JEWEL", "crown-jewel source refused")

    residency = dest.residency.strip().upper()
    protectedish = any(
        s.classification in ("protected", "project") or s.protected_root or s.crown_jewel
        for s in envelope.sources
    )

    if protectedish and residency in CN_RESIDENCIES:
        return auth("REFUSE_RESIDENCY", "protected/project material cannot use CN residency")

    if protectedish:
        return auth(
            "REFUSE_SOURCE_POLICY",
            "R1 permits only generic-classified sources on allowlisted residencies",
        )

    if residency in CN_RESIDENCIES:
        return auth("REFUSE_RESIDENCY", "CN residency not in R1 generic allowlist")

    if residency not in ALLOWED_GENERIC_RESIDENCIES:
        return auth("REFUSE_RESIDENCY", f"residency {residency!r} not allowlisted")

    if not all(
        s.classification == "generic" and not s.protected_root and not s.crown_jewel
        for s in envelope.sources
    ):
        return auth("REFUSE_SOURCE_POLICY", "non-generic source on permit path")

    return auth("PERMIT", "generic payload on allowlisted destination")


@dataclass
class RecordingBroker:
    calls: int = 0
    last_payload: Optional[bytes] = None
    last_destination: Optional[tuple] = None
    fail_after_start: bool = False

    def transmit(self, envelope: OutboundEnvelope, authorization: Authorization) -> dict:
        if authorization.destination_binding != envelope.intended_destination.binding_tuple():
            raise RuntimeError("broker_destination_mismatch")
        if authorization.payload_digest != envelope.payload_digest:
            raise RuntimeError("broker_payload_digest_mismatch")
        self.calls += 1
        self.last_payload = bytes(envelope.payload_bytes)
        self.last_destination = envelope.intended_destination.binding_tuple()
        if self.fail_after_start:
            raise ConnectionError("stub_transport_failed_after_start")
        return {
            "ok": True,
            "stub": True,
            "payload_digest": envelope.payload_digest,
            "bytes_len": len(envelope.payload_bytes),
        }


def execute_authorized(
    envelope: OutboundEnvelope,
    authorization: Authorization,
    broker: RecordingBroker,
) -> TransmissionReceipt:
    phases: List[str] = []
    dest = envelope.intended_destination.to_dict()

    if authorization.decision != "PERMIT":
        return _refusal_receipt(
            envelope, authorization.decision, authorization.reason, authorization.finding_ids
        )

    phases.append("AUTHORIZED")
    recheck = evaluate_decision(envelope, authorized_destination=envelope.intended_destination)
    if recheck.decision != "PERMIT":
        return _refusal_receipt(
            envelope,
            recheck.decision,
            recheck.reason,
            recheck.finding_ids,
            phases_observed=tuple(phases),
        )

    phases.append("TRANSMISSION_STARTED")
    try:
        broker.transmit(envelope, authorization)
    except Exception:  # noqa: BLE001
        phases.append("FAILED_AFTER_TRANSMISSION_STARTED")
        return TransmissionReceipt(
            envelope_id=envelope.envelope_id,
            envelope_digest=authorization.envelope_digest,
            payload_digest=authorization.payload_digest,
            decision=authorization.decision,
            phase="FAILED_AFTER_TRANSMISSION_STARTED",
            reason=authorization.reason,
            finding_ids=authorization.finding_ids,
            provider_calls=broker.calls,
            delivered_payload_digest=None,
            destination=dest,
            policy_version=authorization.policy_version,
            coverage_class=authorization.coverage_class,
            phases_observed=tuple(phases),
        )

    if broker.last_payload != envelope.payload_bytes:
        phases.append("OUTCOME_UNKNOWN")
        return TransmissionReceipt(
            envelope_id=envelope.envelope_id,
            envelope_digest=authorization.envelope_digest,
            payload_digest=authorization.payload_digest,
            decision=authorization.decision,
            phase="OUTCOME_UNKNOWN",
            reason="delivered_bytes_mismatch",
            finding_ids=authorization.finding_ids,
            provider_calls=broker.calls,
            delivered_payload_digest=None,
            destination=dest,
            policy_version=authorization.policy_version,
            coverage_class=authorization.coverage_class,
            phases_observed=tuple(phases),
        )

    delivered_digest = sha256(broker.last_payload).hexdigest()
    phases.append("TRANSMISSION_COMPLETED")
    return TransmissionReceipt(
        envelope_id=envelope.envelope_id,
        envelope_digest=authorization.envelope_digest,
        payload_digest=authorization.payload_digest,
        decision=authorization.decision,
        phase="TRANSMISSION_COMPLETED",
        reason=authorization.reason,
        finding_ids=authorization.finding_ids,
        provider_calls=broker.calls,
        delivered_payload_digest=delivered_digest,
        destination=dest,
        policy_version=authorization.policy_version,
        coverage_class=authorization.coverage_class,
        phases_observed=tuple(phases),
    )


def decide_and_execute(
    envelope: OutboundEnvelope,
    broker: RecordingBroker,
    *,
    inject_scanner_failure: bool = False,
    mutate_destination_after_auth: Optional[Callable[[OutboundEnvelope], OutboundEnvelope]] = None,
) -> TransmissionReceipt:
    authorization = evaluate_decision(envelope, inject_scanner_failure=inject_scanner_failure)
    if authorization.decision != "PERMIT":
        return _refusal_receipt(
            envelope,
            authorization.decision,
            authorization.reason,
            authorization.finding_ids,
        )

    env = envelope
    if mutate_destination_after_auth is not None:
        env = mutate_destination_after_auth(envelope)
        again = evaluate_decision(env, authorized_destination=envelope.intended_destination)
        if again.decision != "PERMIT":
            return _refusal_receipt(
                env,
                again.decision,
                again.reason,
                again.finding_ids,
                phases_observed=("AUTHORIZED",),
            )

    return execute_authorized(env, authorization, broker)
