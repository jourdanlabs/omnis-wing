"""Operator-owned OMNIS WING -> local CADUCEUS configuration.

The tracked repository contains a schema/example only.  Live egress authority
stays in the separately supplied CADUCEUS signed policy.  This file binds WING
to one loopback process identity and one frozen CADUCEUS implementation; it
never contains a provider credential or the CADUCEUS service capability.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from .contract import REAL_WORK_POLICY_ID

PINNED_CADUCEUS_COMMIT = "05c7af0d3e49c73552cd446f3d1884ad40ae40b1"
PINNED_IDE_CONTRACT = "b72876528abafb7b0dd54bac4f7b1a7bce75accd"
CAPABILITY_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class RealWorkConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealWorkConfig:
    policy_id: str
    caduceus_base: str
    caduceus_instance_id: str
    caduceus_root: Path
    caduceus_commit: str
    service_token_env: str
    provider: str
    scheme: str
    hostname: str
    port: int
    path: str
    model: str
    residency: str
    api_shape: str
    lane: str
    timeout_seconds: float
    source: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "caduceus_base": self.caduceus_base,
            "caduceus_instance_id": self.caduceus_instance_id,
            "caduceus_root": str(self.caduceus_root),
            "caduceus_commit": self.caduceus_commit,
            "service_token_env": self.service_token_env,
            "target": {
                "provider": self.provider,
                "scheme": self.scheme,
                "hostname": self.hostname,
                "port": self.port,
                "path": self.path,
                "model": self.model,
                "residency": self.residency,
                "api_shape": self.api_shape,
                "lane": self.lane,
            },
            "source": self.source,
        }


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RealWorkConfigError(f"config_invalid_json:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise RealWorkConfigError("config_not_object")
    return data


def _strict_loopback_origin(value: str) -> str:
    try:
        u = urlsplit(value)
        port = u.port
    except Exception as exc:
        raise RealWorkConfigError("caduceus_base_invalid") from exc
    if (
        u.scheme != "http"
        or u.hostname not in ("127.0.0.1", "localhost")
        or port is None
        or not 1 <= port <= 65535
        or u.username
        or u.password
        or u.path not in ("", "/")
        or u.query
        or u.fragment
    ):
        raise RealWorkConfigError("caduceus_base_must_be_exact_loopback_origin")
    canonical = f"http://{u.hostname}:{port}"
    if value.rstrip("/") != canonical:
        raise RealWorkConfigError("caduceus_base_not_canonical")
    return canonical


def _absolute_without_following(value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise RealWorkConfigError("caduceus_root_must_be_absolute")
    return Path(os.path.normpath(str(p)))


def _target(data: Mapping[str, Any]) -> dict[str, Any]:
    value = data.get("target")
    if not isinstance(value, dict):
        raise RealWorkConfigError("target_not_object")
    return value


def parse_real_work_config(data: Mapping[str, Any], *, source: str) -> RealWorkConfig:
    policy_id = str(data.get("policy_id") or "")
    if policy_id != REAL_WORK_POLICY_ID:
        raise RealWorkConfigError("policy_id_mismatch")
    base = _strict_loopback_origin(str(data.get("caduceus_base") or ""))
    instance = str(data.get("caduceus_instance_id") or "").strip()
    if not instance or len(instance) > 200:
        raise RealWorkConfigError("caduceus_instance_id_required")
    root = _absolute_without_following(str(data.get("caduceus_root") or ""))
    commit = str(data.get("caduceus_commit") or "").strip().lower()
    if commit != PINNED_CADUCEUS_COMMIT:
        raise RealWorkConfigError("caduceus_commit_not_frozen_authority")
    token_env = str(data.get("service_token_env") or "").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", token_env):
        raise RealWorkConfigError("service_token_env_invalid")

    target = _target(data)
    provider = str(target.get("provider") or "").strip().lower()
    scheme = str(target.get("scheme") or "").strip().lower()
    hostname = str(target.get("hostname") or "").strip().lower()
    path = str(target.get("path") or "").strip()
    model = str(target.get("model") or "").strip()
    residency = str(target.get("residency") or "").strip().upper()
    api_shape = str(target.get("api_shape") or "").strip()
    lane = str(target.get("lane") or "").strip()
    try:
        port = int(target.get("port"))
    except Exception as exc:
        raise RealWorkConfigError("target_port_invalid") from exc
    if (
        provider != "minimax"
        or scheme != "https"
        or hostname != "api.minimax.io"
        or port != 443
        or path != "/v1/chat/completions"
        or not model
        or residency != "CN"
        or api_shape != "openai_chat_completions"
        or lane not in ("plan", "codegen", "validation")
    ):
        raise RealWorkConfigError("target_not_exact_minimax_cn_binding")
    try:
        timeout = float(data.get("timeout_seconds", 180.0))
    except Exception as exc:
        raise RealWorkConfigError("timeout_invalid") from exc
    if not 1 <= timeout <= 1800:
        raise RealWorkConfigError("timeout_out_of_range")
    return RealWorkConfig(
        policy_id=policy_id,
        caduceus_base=base,
        caduceus_instance_id=instance,
        caduceus_root=root,
        caduceus_commit=commit,
        service_token_env=token_env,
        provider=provider,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path=path,
        model=model,
        residency=residency,
        api_shape=api_shape,
        lane=lane,
        timeout_seconds=timeout,
        source=source,
    )


def load_real_work_config(path: Optional[str | Path] = None, *, require: bool = True) -> Optional[RealWorkConfig]:
    raw = str(path or os.environ.get("OMNIS_WING_REAL_WORK_CONFIG") or "").strip()
    if not raw:
        if require:
            raise RealWorkConfigError("missing_real_work_config")
        return None
    p = _absolute_without_following(raw)
    if not p.is_file() or p.is_symlink():
        raise RealWorkConfigError("real_work_config_not_regular_file")
    return parse_real_work_config(_load_mapping(p), source=str(p))


def service_capability(cfg: RealWorkConfig, env: Optional[Mapping[str, str]] = None) -> str:
    source = os.environ if env is None else env
    token = str(source.get(cfg.service_token_env) or "")
    if not CAPABILITY_RE.fullmatch(token):
        raise RealWorkConfigError("caduceus_service_capability_unavailable")
    return token


def assert_pinned_caduceus_tree(cfg: RealWorkConfig) -> None:
    root = cfg.caduceus_root
    if root.is_symlink() or not (root / ".git").exists():
        raise RealWorkConfigError("caduceus_root_not_git_worktree")
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception as exc:
        raise RealWorkConfigError("caduceus_tree_identity_unavailable") from exc
    if head != cfg.caduceus_commit:
        raise RealWorkConfigError("caduceus_tree_commit_mismatch")
    if status:
        raise RealWorkConfigError("caduceus_tree_tracked_drift")
