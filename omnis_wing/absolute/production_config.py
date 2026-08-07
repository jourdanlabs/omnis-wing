"""Operator-controlled production signer configuration.

Explicit config only. No startup enrollment. No silent test-signer fallback
when mode is production.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from omnis_wing.absolute.production_signer import CAPTAIN_R4_TAG, TAG_PREFIX

DEFAULT_PRODUCTION_TAG = CAPTAIN_R4_TAG


@dataclass(frozen=True)
class WingProductionConfig:
    backend: str  # keychain | disposable_p256 (cold only) | none
    tag: str
    ledger_dir: Path
    bridge_path: Optional[Path]
    profile: str
    auto_enroll: bool
    source: str  # path or env

    def as_public_dict(self) -> dict:
        return {
            "backend": self.backend,
            "tag": self.tag,
            "ledger_dir": str(self.ledger_dir),
            "bridge_path": str(self.bridge_path) if self.bridge_path else None,
            "profile": self.profile,
            "auto_enroll": self.auto_enroll,
            "source": self.source,
        }


class ProductionConfigError(RuntimeError):
    pass


def _expand(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _simple_yaml_map(text: str) -> dict:
    """Minimal key: value parser for operator config (no nested structures)."""
    out: dict = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif v.lower() in ("null", "~", ""):
            out[k] = ""
        else:
            out[k] = v
    return out


def _load_mapping(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        # Flat operator config only — do not depend on PyYAML or test stubs.
        data = _simple_yaml_map(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ProductionConfigError("config_not_object")
    return data


def load_production_config(
    path: Optional[str | Path] = None,
    *,
    require: bool = False,
) -> Optional[WingProductionConfig]:
    """Load explicit production config from path or OMNIS_WING_PRODUCTION_CONFIG.

    Returns None if no config and require=False.
    """
    raw_path = path or os.environ.get("OMNIS_WING_PRODUCTION_CONFIG") or ""
    # Env-only override without file: all required pieces must be present
    if not raw_path:
        backend = (os.environ.get("OMNIS_WING_SIGNER_BACKEND") or "").strip().lower()
        if not backend:
            if require:
                raise ProductionConfigError("missing_production_config")
            return None
        tag = (os.environ.get("OMNIS_WING_SIGNER_TAG") or DEFAULT_PRODUCTION_TAG).strip()
        ledger = os.environ.get("OMNIS_WING_LEDGER_DIR") or str(
            Path.home() / ".omnis-wing" / "ledgers" / "production"
        )
        bridge = (os.environ.get("OMNIS_WING_BRIDGE_PATH") or "").strip()
        profile = (os.environ.get("OMNIS_WING_PROFILE") or "production").strip()
        data = {
            "backend": backend,
            "tag": tag,
            "ledger_dir": ledger,
            "bridge_path": bridge,
            "profile": profile,
            "auto_enroll": False,
        }
        source = "env"
    else:
        p = _expand(str(raw_path))
        if not p.is_file():
            raise ProductionConfigError(f"config_not_found:{p}")
        data = _load_mapping(p)
        source = str(p)
        # Env overrides file for operator convenience (still explicit)
        if os.environ.get("OMNIS_WING_SIGNER_BACKEND"):
            data["backend"] = os.environ["OMNIS_WING_SIGNER_BACKEND"]
        if os.environ.get("OMNIS_WING_SIGNER_TAG"):
            data["tag"] = os.environ["OMNIS_WING_SIGNER_TAG"]
        if os.environ.get("OMNIS_WING_LEDGER_DIR"):
            data["ledger_dir"] = os.environ["OMNIS_WING_LEDGER_DIR"]
        if os.environ.get("OMNIS_WING_BRIDGE_PATH"):
            data["bridge_path"] = os.environ["OMNIS_WING_BRIDGE_PATH"]

    backend = str(data.get("backend") or "").strip().lower()
    if backend not in ("keychain", "disposable_p256", "none"):
        raise ProductionConfigError(f"invalid_backend:{backend}")

    tag = str(data.get("tag") or DEFAULT_PRODUCTION_TAG).strip()
    if not tag.startswith(TAG_PREFIX):
        raise ProductionConfigError("invalid_tag_prefix")
    if backend == "disposable_p256" and tag == CAPTAIN_R4_TAG:
        raise ProductionConfigError("refusing_captain_tag_on_disposable_backend")
    if backend == "keychain" and tag != CAPTAIN_R4_TAG:
        # Allow only Captain production tag for keychain in this leg
        # (operator must use the stated tag)
        if os.environ.get("OMNIS_WING_ALLOW_ALT_KEYCHAIN_TAG") != "1":
            if tag != CAPTAIN_R4_TAG:
                raise ProductionConfigError(
                    f"keychain_tag_must_be_captain_r4_got:{tag}"
                )

    raw_auto = data.get("auto_enroll", False)
    if isinstance(raw_auto, str):
        auto = raw_auto.strip().lower() in ("1", "true", "yes", "on")
    else:
        auto = bool(raw_auto)
    if auto:
        raise ProductionConfigError("auto_enroll_forbidden")

    ledger_dir = _expand(str(data.get("ledger_dir") or "~/.omnis-wing/ledgers/production"))
    bp = data.get("bridge_path") or ""
    bridge_path = _expand(str(bp)) if str(bp).strip() else None
    profile = str(data.get("profile") or "production")

    return WingProductionConfig(
        backend=backend,
        tag=tag,
        ledger_dir=ledger_dir,
        bridge_path=bridge_path,
        profile=profile,
        auto_enroll=False,
        source=source,
    )


def signer_mode() -> str:
    """production (default) | test (explicit harness/dogfood only)."""
    return (os.environ.get("OMNIS_WING_SIGNER_MODE") or "production").strip().lower()
