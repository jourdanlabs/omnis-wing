"""Sole R1 host entry — ABSOLUTE-shaped decide_and_execute."""

from __future__ import annotations

from .envelope import OutboundEnvelope
from .evaluator import RecordingBroker, TransmissionReceipt, decide_and_execute


def dispatch_outbound(
    envelope: OutboundEnvelope,
    broker: RecordingBroker,
    **kwargs,
) -> TransmissionReceipt:
    return decide_and_execute(envelope, broker, **kwargs)
