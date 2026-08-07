"""OMNIS WING v0 host adapter package."""

from .boundary import (
    CONTRACT_PROTOCOL_VERSION,
    PRODUCT_NAME,
    Action,
    ActionEnvelope,
    CountingStubProvider,
    Receipt,
    Route,
    SourceRef,
    decide_and_maybe_call,
    envelope_digest,
    evaluate_boundary,
    run_through_boundary,
)
from .transport_guard import TransportGuardError, assert_clean_package, scan_source

__all__ = [
    "CONTRACT_PROTOCOL_VERSION",
    "PRODUCT_NAME",
    "Action",
    "ActionEnvelope",
    "CountingStubProvider",
    "Receipt",
    "Route",
    "SourceRef",
    "decide_and_maybe_call",
    "envelope_digest",
    "evaluate_boundary",
    "run_through_boundary",
    "TransportGuardError",
    "assert_clean_package",
    "scan_source",
]
