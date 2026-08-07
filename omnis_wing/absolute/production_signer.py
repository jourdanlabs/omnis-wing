"""R4 production signer boundary — macOS Keychain adapter + disposable test backend.

Hard rules:
- Startup never enrolls/rotates/deletes/exports keys.
- Automated tests use DisposableTestBackend only — never the Captain Keychain tag.
- Health never claims hardware_backed from a missing token attribute.
- Private material never appears in outputs.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional, Protocol

from omnis_wing.absolute.receipt_spine import SignerUnavailable

# Captain's real tag from Bulma probe — tests must not touch this.
CAPTAIN_R4_TAG = "ai.jourdanlabs.omnis-wing.terminus.r4"
TAG_PREFIX = "ai.jourdanlabs.omnis-wing."


class SignerBackend(Protocol):
    def status(self) -> dict: ...
    def enroll(self) -> dict: ...  # explicit operator only
    def public_key_bytes(self) -> bytes: ...
    def sign(self, message: bytes) -> bytes: ...
    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool: ...


@dataclass
class DisposableTestBackend:
    """In-process disposable ECDSA-like test backend (HMAC stand-in for cold tests).

    Not Keychain. Not production. Signs with Ed25519 under the hood for verify
    compatibility with the existing receipt spine algorithm field 'ed25519-test'.
    """

    tag: str
    enrolled: bool = False
    fail_sign: bool = False
    seed: bytes = field(default_factory=lambda: bytes.fromhex(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ))
    _pk: bytes = field(init=False, repr=False)
    _sk: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.tag.startswith(TAG_PREFIX):
            raise ValueError("invalid_application_tag")
        if self.tag == CAPTAIN_R4_TAG:
            raise ValueError("refusing_captain_production_tag_in_test_backend")
        from omnis_wing.absolute import ed25519_pure as ed25519

        self._sk = self.seed
        self._pk = ed25519.publickey_from_seed(self.seed)

    def status(self) -> dict:
        if not self.enrolled:
            return {"ready": False, "state": "NOT_ENROLLED", "tag": self.tag}
        return {
            "ready": True,
            "state": "ENROLLED",
            "tag": self.tag,
            "key_type": "Ed25519-test-disposable",
            "storage_state": "TEST_DISPOSABLE",
            "public_key_sha256": sha256(self._pk).hexdigest(),
            "backend": "disposable_test",
        }

    def enroll(self) -> dict:
        """Explicit operator-invoked only — never called from WING startup."""
        self.enrolled = True
        return self.status()

    def public_key_bytes(self) -> bytes:
        if not self.enrolled:
            raise SignerUnavailable("not_enrolled")
        return self._pk

    def sign(self, message: bytes) -> bytes:
        if not self.enrolled:
            raise SignerUnavailable("not_enrolled")
        if self.fail_sign:
            raise RuntimeError("disposable_backend_sign_failed")
        from omnis_wing.absolute import ed25519_pure as ed25519

        return ed25519.sign(message, self._sk)

    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        from omnis_wing.absolute import ed25519_pure as ed25519

        return ed25519.verify(message, signature, public_key)


@dataclass
class MacOSKeychainBackend:
    """Production adapter: subprocess to compiled Swift Security bridge.

    Does not enroll on init. sign/status only. Operator must call enroll explicitly.
    """

    tag: str
    bridge_path: Path
    # Honesty: never auto-claim SE from missing attribute

    def __post_init__(self) -> None:
        if not self.tag.startswith(TAG_PREFIX):
            raise ValueError("invalid_application_tag")
        if not self.bridge_path.is_file():
            raise FileNotFoundError(f"bridge_not_found:{self.bridge_path}")

    def _run(self, args: list[str]) -> dict:
        cmd = [str(self.bridge_path), *args]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "bridge_failed").strip()
            raise RuntimeError(err)
        line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""
        return json.loads(line)

    def status(self) -> dict:
        st = self._run(["status", self.tag])
        # Preserve honesty: do not invent hardware_backed
        if "hardware_backed" in st:
            del st["hardware_backed"]
        st.setdefault("backend", "macos_keychain_bridge")
        return st

    def enroll(self) -> dict:
        """Explicit operator command only."""
        st = self._run(["enroll", self.tag])
        if "hardware_backed" in st:
            del st["hardware_backed"]
        st.setdefault("backend", "macos_keychain_bridge")
        return st

    def public_key_bytes(self) -> bytes:
        out = self._run(["public-key", self.tag])
        return base64.b64decode(out["public_key_b64"])

    def sign(self, message: bytes) -> bytes:
        out = self._run(["sign", self.tag, base64.b64encode(message).decode("ascii")])
        return base64.b64decode(out["signature_b64"])

    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        out = self._run(
            [
                "verify",
                self.tag,
                base64.b64encode(message).decode("ascii"),
                base64.b64encode(signature).decode("ascii"),
                base64.b64encode(public_key).decode("ascii"),
            ]
        )
        return bool(out.get("valid"))


@dataclass
class ProductionSignerAdapter:
    """Signer protocol adapter over a backend. Startup-safe: no enroll in __init__."""

    backend: Any
    key_id: str = ""
    signature_algorithm: str = "backend-default"

    def __post_init__(self) -> None:
        if not self.key_id:
            tag = getattr(self.backend, "tag", "unknown")
            self.key_id = f"wing-r4:{tag}"
        if isinstance(self.backend, DisposableTestBackend):
            self.signature_algorithm = "ed25519-test"
        elif isinstance(self.backend, MacOSKeychainBackend):
            self.signature_algorithm = "ecdsa-p256-x962-sha256"

    def available(self) -> bool:
        try:
            st = self.backend.status()
            return bool(st.get("ready"))
        except Exception:
            return False

    def enrollment_status(self) -> dict:
        try:
            return self.backend.status()
        except Exception as exc:
            return {
                "ready": False,
                "state": "UNAVAILABLE",
                "error": type(exc).__name__,
            }

    def public_key_bytes(self) -> bytes:
        return self.backend.public_key_bytes()

    def public_fingerprint(self) -> str:
        return sha256(self.public_key_bytes()).hexdigest()

    def sign(self, message: bytes) -> bytes:
        if not self.available():
            raise SignerUnavailable("production_signer_not_enrolled_or_unavailable")
        return self.backend.sign(message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        try:
            pk = self.public_key_bytes()
            return self.backend.verify(message, signature, pk)
        except Exception:
            return False

    def enroll_explicit(self) -> dict:
        """Operator-only enrollment entry. Never called from chat path / startup."""
        return self.backend.enroll()


def default_bridge_source() -> Path:
    return Path(__file__).resolve().parent / "omnis_wing_keychain.swift"


def default_bridge_binary(build_dir: Optional[Path] = None) -> Path:
    root = Path(__file__).resolve().parents[2]
    d = build_dir or (root / ".omnis-wing-build")
    return d / "omnis_wing_keychain"


def compile_keychain_bridge(build_dir: Optional[Path] = None) -> Path:
    """Compile Swift bridge with swiftc. Operator-side; not part of cold unittest."""
    src = default_bridge_source()
    out = default_bridge_binary(build_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "swiftc",
        "-O",
        "-o",
        str(out),
        str(src),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"swiftc_failed:{proc.stderr or proc.stdout}")
    out.chmod(0o755)
    return out
