"""R3 evidence spine: fail-closed signed receipts + chained ledger + anchor.

Test-only Ed25519 via pure-python backend. No Keychain / SE / network.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from omnis_wing.absolute import ed25519_pure as ed25519
from omnis_wing.absolute.evaluator import TransmissionReceipt

R3_COVERAGE = "AI_EGRESS_GOVERNED_R3_EVIDENCE_SPINE"
GENESIS_PREV = "0" * 64


class SignerUnavailable(Exception):
    """Signing key not available — fail closed."""


class EvidencePersistError(Exception):
    """Sign or ledger append failed — fail closed / outcome unknown."""



class Signer(Protocol):
    key_id: str

    def sign(self, message: bytes) -> bytes: ...

    def public_key_bytes(self) -> bytes: ...

    def available(self) -> bool: ...


@dataclass
class Ed25519TestSigner:
    """Isolated test-only Ed25519 signer. Seed from env/file/bytes — never Keychain."""

    seed: bytes
    key_id: str = "test-ed25519-r3-v1"
    _pk: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.seed) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes")
        self._pk = ed25519.publickey_from_seed(self.seed)

    def available(self) -> bool:
        return len(self.seed) == 32

    def public_key_bytes(self) -> bytes:
        return self._pk

    def sign(self, message: bytes) -> bytes:
        if not self.available():
            raise SignerUnavailable("signer seed missing")
        return ed25519.sign(message, self.seed)

    def verify(self, message: bytes, signature: bytes) -> bool:
        return ed25519.verify(message, signature, self._pk)


class UnavailableSigner:
    key_id = "unavailable"

    def available(self) -> bool:
        return False

    def public_key_bytes(self) -> bytes:
        raise SignerUnavailable("no public key")

    def sign(self, message: bytes) -> bytes:
        raise SignerUnavailable("signer unavailable")


def _stable(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def findings_correlation_digest(finding_ids: Sequence[str]) -> str:
    """Keyed correlation over finding IDs only — never payload secrets."""
    blob = _stable(list(finding_ids))
    return sha256(b"finding-ids|" + blob).hexdigest()


@dataclass(frozen=True)
class SignedEvidenceReceipt:
    """Secret-free canonical signed receipt."""

    schema: str
    envelope_digest: str
    decision: str
    phase: str
    policy_version: str
    coverage_class: str
    destination: dict
    provider: str
    residency: str
    findings_correlation_digest: str
    previous_digest: str
    sequence: int
    key_id: str
    receipt_digest: str
    signature_hex: str

    def canonical_unsigned_dict(self) -> dict:
        return {
            "schema": self.schema,
            "envelope_digest": self.envelope_digest,
            "decision": self.decision,
            "phase": self.phase,
            "policy_version": self.policy_version,
            "coverage_class": self.coverage_class,
            "destination": self.destination,
            "provider": self.provider,
            "residency": self.residency,
            "findings_correlation_digest": self.findings_correlation_digest,
            "previous_digest": self.previous_digest,
            "sequence": self.sequence,
            "key_id": self.key_id,
        }

    def to_dict(self) -> dict:
        d = self.canonical_unsigned_dict()
        d["receipt_digest"] = self.receipt_digest
        d["signature_hex"] = self.signature_hex
        return d

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_signed_receipt(
    tr: TransmissionReceipt,
    *,
    signer: Signer,
    previous_digest: str,
    sequence: int,
) -> SignedEvidenceReceipt:
    if not signer.available():
        raise SignerUnavailable("signer not available")

    dest = dict(tr.destination or {})
    provider = str(dest.get("provider") or "")
    residency = str(dest.get("residency") or "")
    body = {
        "schema": "omnis-wing.evidence-receipt.v1",
        "envelope_digest": tr.envelope_digest,
        "decision": tr.decision,
        "phase": tr.phase,
        "policy_version": tr.policy_version,
        "coverage_class": tr.coverage_class,
        "destination": dest,
        "provider": provider,
        "residency": residency,
        "findings_correlation_digest": findings_correlation_digest(tr.finding_ids),
        "previous_digest": previous_digest,
        "sequence": sequence,
        "key_id": signer.key_id,
    }
    unsigned = _stable(body)
    receipt_digest = sha256(unsigned).hexdigest()
    # Sign the receipt digest bytes (hex utf-8) for stable length
    try:
        sig = signer.sign(receipt_digest.encode("ascii"))
    except SignerUnavailable:
        raise
    except Exception as exc:
        raise EvidencePersistError(f"sign_failed:{type(exc).__name__}") from exc
    return SignedEvidenceReceipt(
        schema=body["schema"],
        envelope_digest=body["envelope_digest"],
        decision=body["decision"],
        phase=body["phase"],
        policy_version=body["policy_version"],
        coverage_class=body["coverage_class"],
        destination=dest,
        provider=provider,
        residency=residency,
        findings_correlation_digest=body["findings_correlation_digest"],
        previous_digest=previous_digest,
        sequence=sequence,
        key_id=body["key_id"],
        receipt_digest=receipt_digest,
        signature_hex=sig.hex(),
    )


def verify_signed_receipt(receipt: SignedEvidenceReceipt | dict, public_key: bytes) -> bool:
    if isinstance(receipt, SignedEvidenceReceipt):
        d = receipt.to_dict()
    else:
        d = dict(receipt)
    sig_hex = d.get("signature_hex") or ""
    digest = d.get("receipt_digest") or ""
    body = {
        "schema": d.get("schema"),
        "envelope_digest": d.get("envelope_digest"),
        "decision": d.get("decision"),
        "phase": d.get("phase"),
        "policy_version": d.get("policy_version"),
        "coverage_class": d.get("coverage_class"),
        "destination": d.get("destination") or {},
        "provider": d.get("provider"),
        "residency": d.get("residency"),
        "findings_correlation_digest": d.get("findings_correlation_digest"),
        "previous_digest": d.get("previous_digest"),
        "sequence": d.get("sequence"),
        "key_id": d.get("key_id"),
    }
    unsigned = _stable(body)
    if sha256(unsigned).hexdigest() != digest:
        return False
    try:
        sig = bytes.fromhex(sig_hex)
    except ValueError:
        return False
    return ed25519.verify(digest.encode("ascii"), sig, public_key)


@dataclass
class LedgerEntry:
    receipt: dict


class EvidenceLedger:
    """Append-only JSONL ledger with sequence/previous-digest chain checks."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def load_entries(self) -> list[dict]:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            out.append(json.loads(ln))
        return out

    def head_digest(self) -> str:
        entries = self.load_entries()
        if not entries:
            return GENESIS_PREV
        return entries[-1]["receipt_digest"]

    def next_sequence(self) -> int:
        return len(self.load_entries()) + 1

    def _fsync_count(self) -> int:
        return int(getattr(self, "_fsync_calls", 0))

    def _durable_fsync(self, f) -> None:
        """os.fsync before append returns — required for durable pre-send contract."""
        n = int(getattr(self, "_fsync_calls", 0)) + 1
        self._fsync_calls = n
        fail_on = getattr(self, "_force_fsync_fail_on", None)
        if fail_on is not None and n == int(fail_on):
            raise OSError("fsync_injected_fail")
        if getattr(self, "_force_fsync_fail", False):
            raise OSError("fsync_injected_fail")
        os.fsync(f.fileno())

    def ensure_appendable(self) -> None:
        """Prove write + fsync capability on the ledger path (advisory gate).

        Authority remains append()+fsync success before transmit; this only
        fails closed early when the filesystem cannot support that path.
        """
        if getattr(self, "_force_unappendable", False):
            raise EvidencePersistError("ledger_not_appendable:forced")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Do not bump the real append fsync counter here — probe only.
            with self.path.open("a", encoding="utf-8") as f:
                f.flush()
                if getattr(self, "_force_fsync_fail_on", None) == 0:
                    raise OSError("fsync_injected_fail")
                # Probe fsync without consuming append-phase inject counters
                if getattr(self, "_skip_ensure_fsync_probe", False):
                    return
                os.fsync(f.fileno())
        except OSError as exc:
            raise EvidencePersistError(f"ledger_not_appendable:{exc}") from exc

    def append(self, receipt: SignedEvidenceReceipt) -> None:
        if getattr(self, "_force_unappendable", False):
            raise EvidencePersistError("ledger_not_appendable:forced")
        entries = self.load_entries()
        prev = GENESIS_PREV if not entries else entries[-1]["receipt_digest"]
        seq = len(entries) + 1
        if receipt.previous_digest != prev:
            raise ValueError("previous_digest chain break on append")
        if receipt.sequence != seq:
            raise ValueError("sequence break on append")
        prev_size = self.path.stat().st_size if self.path.exists() else 0
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(receipt.serialize() + "\n")
                f.flush()
                self._durable_fsync(f)
        except OSError as exc:
            # Roll back this process-visible write so a failed fsync cannot
            # leave flattering pre-send evidence without durability.
            try:
                with self.path.open("rb+") as rf:
                    rf.truncate(prev_size)
                    rf.flush()
                    try:
                        os.fsync(rf.fileno())
                    except OSError:
                        pass
            except OSError:
                pass
            raise EvidencePersistError(f"ledger_fsync_or_append_failed:{exc}") from exc

    def verify_chain(self, public_key: bytes) -> tuple[bool, str]:
        entries = self.load_entries()
        prev = GENESIS_PREV
        for i, e in enumerate(entries, start=1):
            if e.get("sequence") != i:
                return False, f"sequence_mismatch_at_{i}"
            if e.get("previous_digest") != prev:
                return False, f"prev_digest_mismatch_at_{i}"
            if not verify_signed_receipt(e, public_key):
                return False, f"signature_fail_at_{i}"
            prev = e["receipt_digest"]
        return True, "ok"


def write_anchor(path: Path, *, chain_head_digest: str, key_id: str, public_key_hex: str) -> dict:
    anchor = {
        "schema": "omnis-wing.evidence-anchor.v1",
        "chain_head_digest": chain_head_digest,
        "key_id": key_id,
        "public_key_hex": public_key_hex,
        "anchor_note": "test-fixture-external-anchor-not-production",
    }
    anchor["anchor_digest"] = sha256(_stable(anchor)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(anchor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return anchor


def verify_anchor(path: Path, ledger: EvidenceLedger) -> tuple[bool, str]:
    if not path.is_file():
        return False, "anchor_missing"
    anchor = json.loads(path.read_text(encoding="utf-8"))
    head = ledger.head_digest()
    if head == GENESIS_PREV and not ledger.load_entries():
        # empty ledger special
        pass
    if anchor.get("chain_head_digest") != head:
        return False, "anchor_head_mismatch"
    body = {
        "schema": anchor.get("schema"),
        "chain_head_digest": anchor.get("chain_head_digest"),
        "key_id": anchor.get("key_id"),
        "public_key_hex": anchor.get("public_key_hex"),
        "anchor_note": anchor.get("anchor_note"),
    }
    if sha256(_stable(body)).hexdigest() != anchor.get("anchor_digest"):
        return False, "anchor_digest_mismatch"
    return True, "ok"


def make_test_signer(seed: Optional[bytes] = None) -> Ed25519TestSigner:
    if seed is None:
        seed = bytes.fromhex(
            "35e8f67854259b85950d9f88e71b8f912892339eac961dd8dd9c584365513e1d"
        )
    return Ed25519TestSigner(seed=seed)


def ledger_outcome_report(ledger: EvidenceLedger) -> dict:
    """Truthful report of chain terminal completeness (no flattering SENT)."""
    entries = ledger.load_entries()
    if not entries:
        return {"status": "empty", "terminal_missing": True}
    last = entries[-1]
    phase = last.get("phase")
    if phase == "TRANSMISSION_STARTED":
        return {
            "status": "OUTCOME_UNKNOWN",
            "terminal_missing": True,
            "last_phase": phase,
            "last_receipt_digest": last.get("receipt_digest"),
            "sequence": last.get("sequence"),
        }
    if phase == "TRANSMISSION_COMPLETED":
        return {
            "status": "terminal_complete",
            "terminal_missing": False,
            "last_phase": phase,
            "last_receipt_digest": last.get("receipt_digest"),
            "sequence": last.get("sequence"),
        }
    if phase in ("NONE",) or str(last.get("decision", "")).startswith("REFUSE"):
        return {
            "status": "refusal_recorded",
            "terminal_missing": False,
            "last_phase": phase,
            "decision": last.get("decision"),
            "last_receipt_digest": last.get("receipt_digest"),
        }
    return {
        "status": "OUTCOME_UNKNOWN",
        "terminal_missing": True,
        "last_phase": phase,
        "last_receipt_digest": last.get("receipt_digest"),
    }
