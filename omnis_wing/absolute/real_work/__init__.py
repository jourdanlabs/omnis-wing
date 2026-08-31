"""TERMINUS_REAL_WORK_V1 — WING uses CADUCEUS as sole provider-facing authority."""

from .contract import (
    DELIVERY_MODE,
    REAL_WORK_POLICY_ID,
    RESPONSE_HANDLING,
    ROUTE_TABLE,
    load_shared_corpus,
    corpus_digest,
)
from .admission import admission_manifest, assert_contract_not_drifted
from .config import (
    RealWorkConfig,
    RealWorkConfigError,
    load_real_work_config,
    PINNED_CADUCEUS_COMMIT,
)
from .caduceus_client import (
    CaduceusBoundaryError,
    CaduceusOutcomeUnknown,
    CaduceusRealWorkClient,
    CaduceusResult,
)
from .runtime import real_work_required, transmit_primary_chat, refuse_non_primary_route

__all__ = [
    "DELIVERY_MODE",
    "REAL_WORK_POLICY_ID",
    "RESPONSE_HANDLING",
    "ROUTE_TABLE",
    "load_shared_corpus",
    "corpus_digest",
    "admission_manifest",
    "assert_contract_not_drifted",
    "RealWorkConfig",
    "RealWorkConfigError",
    "load_real_work_config",
    "PINNED_CADUCEUS_COMMIT",
    "CaduceusBoundaryError",
    "CaduceusOutcomeUnknown",
    "CaduceusRealWorkClient",
    "CaduceusResult",
    "real_work_required",
    "transmit_primary_chat",
    "refuse_non_primary_route",
]
