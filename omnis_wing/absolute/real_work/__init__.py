"""TERMINUS_REAL_WORK_V1 — shared contract with CADUCEUS (provider-neutral).

WING does not define a second safety model. Delivery modes, receipt fields, and
corpus outcomes must match CADUCEUS before any route may claim TRANSFORMED.
"""

from .contract import (
    DELIVERY_MODE,
    REAL_WORK_POLICY_ID,
    RESPONSE_HANDLING,
    ROUTE_TABLE,
    load_shared_corpus,
    corpus_digest,
)

__all__ = [
    "DELIVERY_MODE",
    "REAL_WORK_POLICY_ID",
    "RESPONSE_HANDLING",
    "ROUTE_TABLE",
    "load_shared_corpus",
    "corpus_digest",
]
