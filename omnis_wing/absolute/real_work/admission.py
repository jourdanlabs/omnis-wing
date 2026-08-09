"""W0 admission pins for WING × TERMINUS_REAL_WORK_V1 cutover.

Immutable digests — drift guard fails if corpus/contract files change without
intentional pin bump.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Build base (parent of this cutover branch tip at admission)
WING_BUILD_BASE = "b5bba23a5746aab9a217c4638d67260ccecaa6f4"
WING_BRANCH = "toph/wing-terminus-real-work-cutover-v1"

# Proven external pins (do not invent)
CADUCEUS_PROVEN_PIN = "05c7af0d3e49c73552cd446f3d1884ad40ae40b1"
IDE_CONTRACT_PIN = "b72876528abafb7b0dd54bac4f7b1a7bce75accd"

# Live proof digests from Bulma CLEAR package
LIVE_EVIDENCE_MANIFEST_DIGEST = (
    "183d1651caba906ea270066e69ffca501a2a74f56a29cfda77815cf0d6b938bb"
)
LIVE_RAW_FILE_DIGEST = (
    "5a6cb43dc844101923ee912382dccd1da9299c9f1947e3416bb3abbea29a0021"
)
LIVE_RECEIPT_CHAIN_DIGEST = (
    "ad50c81cd4d54b12fc991cbbb938fdec14de3f4a20275bda6792eb8770f3dae5"
)

POLICY_ID = "TERMINUS_REAL_WORK_V1"

_CORPUS = Path(__file__).with_name("terminus-transform-v1.corpus.json")
_CONTRACT = Path(__file__).with_name("contract.py")
_ADMISSION = Path(__file__).with_name("admission.json")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def admission_manifest() -> dict:
    live = {
        "wing_build_base": WING_BUILD_BASE,
        "wing_branch": WING_BRANCH,
        "caduceus_proven_pin": CADUCEUS_PROVEN_PIN,
        "ide_contract_pin": IDE_CONTRACT_PIN,
        "policy_id": POLICY_ID,
        "live_evidence_manifest_digest": LIVE_EVIDENCE_MANIFEST_DIGEST,
        "live_raw_file_digest": LIVE_RAW_FILE_DIGEST,
        "live_receipt_chain_digest": LIVE_RECEIPT_CHAIN_DIGEST,
        "corpus_sha256": file_sha256(_CORPUS) if _CORPUS.is_file() else None,
        "contract_sha256": file_sha256(_CONTRACT) if _CONTRACT.is_file() else None,
    }
    if _ADMISSION.is_file():
        live["frozen"] = json.loads(_ADMISSION.read_text(encoding="utf-8"))
    return live


def assert_contract_not_drifted(*, expected_corpus: str | None = None) -> None:
    """Fail closed against the committed W0 admission, not caller attention."""
    for path in (_CORPUS, _CONTRACT, _ADMISSION):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"missing or unsafe admission file: {path}")
    try:
        frozen = json.loads(_ADMISSION.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError("admission manifest invalid") from exc
    expected = {
        "wing_corpus_sha256": file_sha256(_CORPUS),
        "wing_contract_sha256": file_sha256(_CONTRACT),
    }
    if expected_corpus is not None:
        expected["wing_corpus_sha256"] = expected_corpus
    for field, got in expected.items():
        if frozen.get(field) != got:
            raise AssertionError(
                f"{field} drift: got {got} expected {frozen.get(field)}"
            )
    if frozen.get("wing_base") != WING_BUILD_BASE:
        raise AssertionError("wing base admission mismatch")
    if (frozen.get("caduceus") or {}).get("commit") != CADUCEUS_PROVEN_PIN:
        raise AssertionError("CADUCEUS pin admission mismatch")
    if (frozen.get("ide_contract") or {}).get("commit") != IDE_CONTRACT_PIN:
        raise AssertionError("IDE contract pin admission mismatch")
    if frozen.get("policy_id") != POLICY_ID:
        raise AssertionError("policy admission mismatch")
