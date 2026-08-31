"""WING parity: shared TERMINUS_REAL_WORK_V1 corpus + honest route table."""

from __future__ import annotations

import hashlib
from pathlib import Path

from omnis_wing.absolute.real_work.contract import (
    REAL_WORK_POLICY_ID,
    ROUTE_TABLE,
    assert_route_honest,
    corpus_digest,
    delivery_mode_valid,
    load_shared_corpus,
    transformed_receipt_complete,
)


def test_corpus_provider_neutral_and_named():
    c = load_shared_corpus()
    assert c["policy_id"] == REAL_WORK_POLICY_ID
    assert c["provider_neutral"] is True
    assert c["first_adapter"] == "minimax"
    assert any(x["id"] == "secret_in_message" for x in c["cases"])


def test_corpus_digest_stable_shape():
    d = corpus_digest()
    assert len(d) == 64
    assert all(c in "0123456789abcdef" for c in d)


def test_route_table_honest_primary_governed():
    assert ROUTE_TABLE["wing.chat_join"] == "GOVERNED"
    assert ROUTE_TABLE["wing.chat_join_direct_provider"] == "DISABLED"
    assert ROUTE_TABLE["caduceus.image_generations"] == "DISABLED"
    assert_route_honest("wing.chat_join", "GOVERNED")


def test_cannot_silently_upgrade_disabled_route():
    try:
        assert_route_honest("wing.embeddings", "GOVERNED")
        assert False, "expected AssertionError"
    except AssertionError:
        pass


def test_transformed_receipt_requires_digests():
    errs = transformed_receipt_complete(
        {
            "delivery_mode": "TRANSFORMED",
            "origin_classification": ["credential"],
            "emitted_classification": "safe_derived",
        }
    )
    assert any("transform_policy_digest" in e for e in errs)


def test_transformed_receipt_complete_ok():
    d = "a" * 64
    errs = transformed_receipt_complete(
        {
            "delivery_mode": "TRANSFORMED",
            "origin_classification": ["credential"],
            "emitted_classification": "safe_derived",
            "transform_policy_digest": d,
            "transform_input_digest": d,
            "transform_output_digest": d,
        }
    )
    assert errs == []


def test_delivery_modes():
    assert delivery_mode_valid("RAW")
    assert delivery_mode_valid("TRANSFORMED")
    assert delivery_mode_valid("LOCAL_ONLY")
    assert not delivery_mode_valid("PERMIT")
