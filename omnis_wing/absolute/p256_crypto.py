"""P-256 ECDSA (SHA-256, DER/X9.62) via system openssl — no network deps.

Used for:
- verifying production Keychain bridge signatures (public verify only)
- disposable cold-test backend (generate/sign in temp dir — NOT Keychain)

Not a production HSM. Not Secure Enclave.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


class P256Error(Exception):
    pass


def _run(args: list[str], *, input_bytes: Optional[bytes] = None) -> bytes:
    proc = subprocess.run(
        args,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        raise P256Error(err.strip() or "openssl_failed")
    return proc.stdout


def _spki_from_uncompressed_point(point65: bytes) -> bytes:
    """Build SubjectPublicKeyInfo DER for P-256 uncompressed point (0x04||X||Y)."""
    if len(point65) != 65 or point65[0] != 0x04:
        raise P256Error("public_key_must_be_uncompressed_p256_65")
    # AlgorithmIdentifier for ecPublicKey + prime256v1
    algo = bytes.fromhex("301306072a8648ce3d020106082a8648ce3d030107")
    # subjectPublicKey BIT STRING: 0 unused bits + point
    bitstring = b"\x03" + bytes([len(point65) + 1]) + b"\x00" + point65
    spki_inner = algo + bitstring
    return b"\x30" + bytes([len(spki_inner)]) + spki_inner


def public_key_raw_from_pem(pem: bytes) -> bytes:
    der = _run(["openssl", "ec", "-pubin", "-pubout", "-conv_form", "uncompressed", "-outform", "DER"], input_bytes=pem)
    # SPKI DER ends with bitstring containing 0x00 + 0x04||X||Y
    # Find uncompressed point marker
    idx = der.find(b"\x04")
    # Prefer last 65-byte 04-prefixed chunk
    for i in range(len(der) - 65, -1, -1):
        if der[i] == 0x04 and i + 65 <= len(der):
            # heuristic: X,Y look like bigints
            cand = der[i : i + 65]
            if len(cand) == 65:
                return cand
    raise P256Error("could_not_extract_uncompressed_point")


def generate_keypair_pem(dirpath: Path) -> Tuple[Path, Path, bytes]:
    """Create disposable P-256 keypair under dirpath. Returns priv_pem, pub_pem, raw_pub65."""
    dirpath.mkdir(parents=True, exist_ok=True)
    priv = dirpath / "p256-priv.pem"
    pub = dirpath / "p256-pub.pem"
    _run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(priv)])
    _run(["openssl", "ec", "-in", str(priv), "-pubout", "-out", str(pub)])
    raw = public_key_raw_from_pem(pub.read_bytes())
    return priv, pub, raw


def sign_message(priv_pem_path: Path, message: bytes) -> bytes:
    """ECDSA-SHA256 over message bytes; returns DER signature (SecKey X9.62 style)."""
    # openssl dgst -sha256 -sign signs the message (hashes internally)
    return _run(
        ["openssl", "dgst", "-sha256", "-sign", str(priv_pem_path)],
        input_bytes=message,
    )


def verify_message(public_key_raw65: bytes, message: bytes, signature_der: bytes) -> bool:
    """Verify ECDSA-SHA256 DER sig with uncompressed P-256 public point."""
    try:
        spki = _spki_from_uncompressed_point(public_key_raw65)
        with tempfile.TemporaryDirectory(prefix="wing-p256-v-") as td:
            pub_der = Path(td) / "pub.der"
            pub_pem = Path(td) / "pub.pem"
            sig_path = Path(td) / "sig.der"
            msg_path = Path(td) / "msg.bin"
            pub_der.write_bytes(spki)
            sig_path.write_bytes(signature_der)
            msg_path.write_bytes(message)
            # DER → PEM
            pem = _run(["openssl", "pkey", "-pubin", "-inform", "DER", "-in", str(pub_der), "-outform", "PEM"])
            pub_pem.write_bytes(pem)
            proc = subprocess.run(
                [
                    "openssl",
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(pub_pem),
                    "-signature",
                    str(sig_path),
                    str(msg_path),
                ],
                capture_output=True,
                check=False,
            )
            out = (proc.stdout or b"").decode() + (proc.stderr or b"").decode()
            return proc.returncode == 0 and "Verified OK" in out
    except Exception:
        return False
