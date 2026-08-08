"""Shared cold-test bootstrap for OMNIS WING — signed policy + no force-classification."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from omnis_wing.absolute.signed_policy import install_test_policy_trust, write_test_policy_file

_BOOTSTRAPPED = False
_POLICY_PATH: str | None = None


def bootstrap_wing_test_env(*, force: bool = False) -> Path:
    """Install disposable signed policy + trust. Never enables FORCE_CLASSIFICATION."""
    global _BOOTSTRAPPED, _POLICY_PATH
    os.environ.pop("OMNIS_WING_FORCE_CLASSIFICATION", None)
    if not os.environ.get("OMNIS_WING_SIGNER_MODE"):
        os.environ["OMNIS_WING_SIGNER_MODE"] = "test"
    if _BOOTSTRAPPED and not force and _POLICY_PATH and Path(_POLICY_PATH).is_file():
        os.environ["OMNIS_WING_POLICY_PATH"] = _POLICY_PATH
        install_test_policy_trust()
        return Path(_POLICY_PATH)
    td = Path(tempfile.mkdtemp(prefix="wing-test-policy-"))
    pf = write_test_policy_file(td / "policy.json", install_trust=True)
    _POLICY_PATH = str(pf)
    os.environ["OMNIS_WING_POLICY_PATH"] = _POLICY_PATH
    _BOOTSTRAPPED = True
    return pf


def refresh_signed_policy(overrides: dict | None = None) -> Path:
    """Rewrite the active test policy file with optional body overrides."""
    bootstrap_wing_test_env()
    path = Path(os.environ["OMNIS_WING_POLICY_PATH"])
    return write_test_policy_file(path, overrides=overrides, install_trust=True)
