"""M6 signed operator policy — real detached authenticity, not digest theater.

Production enforce | local_only | deny_all require a path to a policy document
whose canonical body is signed (Ed25519) under a pinned operator public key.
No unsigned generated default in production. Test fixtures use a disposable
signer/public key that is never a production default.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from omnis_wing.absolute import ed25519_pure as ed25519

VALID_MODES = frozenset({"enforce", "local_only", "deny_all"})
SIGNATURE_ALGORITHM = "ed25519"
# Authenticity envelope keys — excluded from canonical body bytes.
_ENVELOPE_KEYS = frozenset(
    {
        "signature",
        "policy_digest",
        "signature_digest",
        "signature_hex",
        "signature_algorithm",
        "key_id",
        "public_key_hex",
    }
)

# Disposable test-only key material. Never a production trust default.
TEST_POLICY_KEY_ID = "test-policy-ed25519-v1"
TEST_POLICY_SEED = bytes.fromhex(
    "a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00"
)
TEST_POLICY_PUBLIC_KEY = ed25519.publickey_from_seed(TEST_POLICY_SEED)

# Process-local trust store (tests install disposable keys here).
_PROCESS_TRUST: Dict[str, bytes] = {}


class PolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SignedPolicy:
    mode: str
    policy_version: str
    policy_digest: str
    file_count_ceiling: int
    byte_ceiling: int
    require_remote_anchor: bool
    signature_valid: bool
    key_id: str
    signature_algorithm: str
    raw: dict

    def public_dict(self) -> dict:
        return {
            "mode": self.mode,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest if self.signature_valid else None,
            "file_count_ceiling": self.file_count_ceiling,
            "byte_ceiling": self.byte_ceiling,
            "require_remote_anchor": self.require_remote_anchor,
            "signature_valid": self.signature_valid,
            "key_id": self.key_id,
            "signature_algorithm": self.signature_algorithm,
        }


def canonical_policy_body(data: Mapping[str, Any]) -> dict:
    """Policy fields that enter the signed digest — never the signature envelope."""
    return {k: v for k, v in data.items() if k not in _ENVELOPE_KEYS}


def canonical_policy_bytes(data: Mapping[str, Any]) -> bytes:
    body = canonical_policy_body(data)
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def policy_digest_hex(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_policy_bytes(data)).hexdigest()


def set_process_trust_store(mapping: Mapping[str, bytes] | None) -> None:
    """Replace process-local trust store. Production code never calls this."""
    global _PROCESS_TRUST
    _PROCESS_TRUST = {str(k): bytes(v) for k, v in (mapping or {}).items()}


def clear_process_trust_store() -> None:
    set_process_trust_store({})


def install_test_policy_trust() -> Dict[str, bytes]:
    """Install disposable test-only policy key into process trust. Tests only."""
    trust = {TEST_POLICY_KEY_ID: TEST_POLICY_PUBLIC_KEY}
    set_process_trust_store(trust)
    return trust


def _load_file_trust(path: str) -> Dict[str, bytes]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: Dict[str, bytes] = {}
    if not isinstance(raw, dict):
        raise PolicyError("trust_store_malformed")
    for kid, val in raw.items():
        if isinstance(val, dict):
            hx = val.get("public_key_hex") or val.get("pubkey_hex") or ""
        else:
            hx = str(val)
        hx = hx.strip().lower().replace("0x", "")
        try:
            pk = bytes.fromhex(hx)
        except ValueError as exc:
            raise PolicyError(f"trust_key_bad_hex:{kid}") from exc
        if len(pk) != 32:
            raise PolicyError(f"trust_key_bad_len:{kid}")
        out[str(kid)] = pk
    return out


def load_trust_store() -> Dict[str, bytes]:
    """Pinned operator public keys. Process store + optional file path. No test default in prod."""
    trust = dict(_PROCESS_TRUST)
    path = (os.environ.get("OMNIS_WING_POLICY_TRUST_PATH") or "").strip()
    if path:
        trust.update(_load_file_trust(path))
    # Single-key env pin (production-shaped)
    kid = (os.environ.get("OMNIS_WING_POLICY_KEY_ID") or "").strip()
    hx = (os.environ.get("OMNIS_WING_POLICY_PUBKEY_HEX") or "").strip().lower().replace("0x", "")
    if kid and hx:
        try:
            pk = bytes.fromhex(hx)
        except ValueError as exc:
            raise PolicyError("env_trust_key_bad_hex") from exc
        if len(pk) != 32:
            raise PolicyError("env_trust_key_bad_len")
        trust[kid] = pk
    return trust


def sign_policy_document(
    body: Mapping[str, Any],
    *,
    seed: bytes,
    key_id: str,
    algorithm: str = SIGNATURE_ALGORITHM,
) -> dict:
    """Return full policy document with detached authenticity envelope."""
    if algorithm != SIGNATURE_ALGORITHM:
        raise PolicyError(f"unsupported_sign_algorithm:{algorithm}")
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    doc_body = canonical_policy_body(dict(body))
    msg = canonical_policy_bytes(doc_body)
    sig = ed25519.sign(msg, seed)
    pk = ed25519.publickey_from_seed(seed)
    dig = hashlib.sha256(msg).hexdigest()
    out = dict(doc_body)
    out["policy_digest"] = dig  # informational only; authenticity is the signature
    out["signature"] = {
        "algorithm": algorithm,
        "key_id": key_id,
        "signature_hex": sig.hex(),
        "public_key_hex": pk.hex(),  # display aid; verification uses trust store only
    }
    return out


def make_test_signed_policy(
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    seed: bytes = TEST_POLICY_SEED,
    key_id: str = TEST_POLICY_KEY_ID,
) -> dict:
    """Disposable signed policy document for cold tests. Marked test-only via key id."""
    body = {
        "mode": "enforce",
        "policy_version": "omnis-wing.terminus-policy.v1",
        "file_count_ceiling": 50,
        "byte_ceiling": 512000,
        "require_remote_anchor": False,
        "allowed_residencies_generic": ["US", "EU", "LOCAL"],
        "issued_at": int(time.time()),
    }
    if overrides:
        body.update(dict(overrides))
    return sign_policy_document(body, seed=seed, key_id=key_id)


def write_test_policy_file(
    path: Path | str,
    overrides: Optional[Mapping[str, Any]] = None,
    *,
    install_trust: bool = True,
) -> Path:
    """Write a disposable signed policy and optionally install test trust."""
    if install_trust:
        install_test_policy_trust()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = make_test_signed_policy(overrides)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _extract_signature(data: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return (algorithm, key_id, signature_hex)."""
    sig_obj = data.get("signature")
    if isinstance(sig_obj, dict):
        algo = str(sig_obj.get("algorithm") or "").strip().lower()
        kid = str(sig_obj.get("key_id") or "").strip()
        hx = str(sig_obj.get("signature_hex") or sig_obj.get("sig_hex") or "").strip().lower()
        return algo, kid, hx
    # Flat envelope (legacy shape attempt)
    algo = str(data.get("signature_algorithm") or "").strip().lower()
    kid = str(data.get("key_id") or "").strip()
    hx = str(data.get("signature_hex") or "").strip().lower()
    return algo, kid, hx


def _check_staleness(body: Mapping[str, Any]) -> None:
    now = int(time.time())
    not_after = body.get("not_after")
    if not_after is not None:
        try:
            exp = int(not_after)
        except (TypeError, ValueError) as exc:
            raise PolicyError("policy_not_after_malformed") from exc
        if now > exp:
            raise PolicyError("policy_stale")
    max_age = body.get("max_age_seconds")
    issued = body.get("issued_at")
    if max_age is not None and issued is not None:
        try:
            if now - int(issued) > int(max_age):
                raise PolicyError("policy_stale")
        except (TypeError, ValueError) as exc:
            raise PolicyError("policy_age_malformed") from exc


def verify_policy_document(data: Mapping[str, Any], trust: Mapping[str, bytes]) -> SignedPolicy:
    """Verify detached signature against pinned trust. Raises PolicyError on any failure."""
    if not isinstance(data, Mapping):
        raise PolicyError("policy_malformed")

    algo, key_id, sig_hex = _extract_signature(data)
    if not algo and not sig_hex:
        raise PolicyError("policy_unsigned")
    if algo != SIGNATURE_ALGORITHM:
        raise PolicyError(f"policy_unknown_algorithm:{algo or 'missing'}")
    if not key_id:
        raise PolicyError("policy_missing_key_id")
    if key_id not in trust:
        raise PolicyError(f"policy_unknown_key_id:{key_id}")
    if not sig_hex:
        raise PolicyError("policy_missing_signature")
    try:
        sig = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise PolicyError("policy_signature_bad_hex") from exc
    if len(sig) != 64:
        raise PolicyError("policy_signature_bad_len")

    body = canonical_policy_body(data)
    msg = canonical_policy_bytes(body)
    dig = hashlib.sha256(msg).hexdigest()
    # Optional embedded digest must match canonical body if present (informational)
    embedded = data.get("policy_digest") or data.get("signature_digest")
    if embedded and str(embedded) != dig:
        # Digest theater without signature would have passed old code; we still
        # require signature, but a lying digest is also a refuse.
        raise PolicyError("policy_digest_mismatch")

    pk = trust[key_id]
    if not ed25519.verify(msg, sig, pk):
        raise PolicyError("policy_signature_invalid")

    _check_staleness(body)

    mode = str(body.get("mode") or "enforce").strip().lower()
    if mode == "off":
        raise PolicyError("policy_mode_off_forbidden")
    if mode not in VALID_MODES:
        raise PolicyError(f"invalid_policy_mode:{mode}")

    return SignedPolicy(
        mode=mode,
        policy_version=str(body.get("policy_version") or "unknown"),
        policy_digest=dig,
        file_count_ceiling=int(body.get("file_count_ceiling") or 50),
        byte_ceiling=int(body.get("byte_ceiling") or 512000),
        require_remote_anchor=bool(body.get("require_remote_anchor")),
        signature_valid=True,
        key_id=key_id,
        signature_algorithm=algo,
        raw=dict(data),
    )


def load_policy(path: Optional[str] = None) -> SignedPolicy:
    """Load and cryptographically verify operator policy. No unsigned production default."""
    p = (path if path is not None else os.environ.get("OMNIS_WING_POLICY_PATH") or "").strip()
    if not p:
        raise PolicyError("policy_missing")
    try:
        text = Path(p).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyError("policy_missing") from exc
    except OSError as exc:
        raise PolicyError(f"policy_unreadable:{type(exc).__name__}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolicyError("policy_malformed") from exc
    if not isinstance(data, dict):
        raise PolicyError("policy_malformed")

    trust = load_trust_store()
    if not trust:
        raise PolicyError("policy_trust_empty")
    return verify_policy_document(data, trust)


def unenforced_banner() -> str:
    return "UNENFORCED — PAYLOAD NOT INSPECTED"
