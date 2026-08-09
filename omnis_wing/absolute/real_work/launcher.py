"""Fail-closed operator launcher support for the isolated WING fork."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .caduceus_client import CaduceusRealWorkClient
from .config import (
    RealWorkConfigError,
    assert_pinned_caduceus_tree,
    load_real_work_config,
    service_capability,
)


def _runtime_dir() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    path = home / "omnis-wing-runtime"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or (path.stat().st_mode & 0o077):
        raise RealWorkConfigError("wing_runtime_dir_not_private")
    return path


def _client():
    cfg = load_real_work_config(require=True)
    assert cfg is not None
    assert_pinned_caduceus_tree(cfg)
    token = service_capability(cfg)
    return cfg, CaduceusRealWorkClient(cfg, token=token)


def status() -> dict:
    cfg, client = _client()
    health = client.health()
    return {
        "state": "READY",
        "policy_id": cfg.policy_id,
        "caduceus": {
            "base": cfg.caduceus_base,
            "instance_id": cfg.caduceus_instance_id,
            "commit": cfg.caduceus_commit,
            "terminus": health.get("terminus"),
            "service_auth": health.get("service_auth"),
            "chain": health.get("chain"),
        },
        "target": cfg.public_dict()["target"],
    }


def ensure_service() -> dict:
    cfg = load_real_work_config(require=True)
    assert cfg is not None
    assert_pinned_caduceus_tree(cfg)
    token = service_capability(cfg)
    client = CaduceusRealWorkClient(cfg, token=token)
    try:
        return {"started": False, **status()}
    except Exception:
        pass

    for name in ("CADUCEUS_LANES", "CADUCEUS_STATE_DIR"):
        if not (os.environ.get(name) or "").strip():
            raise RealWorkConfigError(f"{name.lower()}_required")
    node = shutil.which("node")
    if not node:
        raise RealWorkConfigError("node_runtime_missing")
    entry = cfg.caduceus_root / "src" / "caduceus.mjs"
    if not entry.is_file():
        raise RealWorkConfigError("caduceus_entry_missing")
    runtime = _runtime_dir()
    log = runtime / "caduceus.log"
    pidfile = runtime / "caduceus.pid"
    env = dict(os.environ)
    env["CADUCEUS_SERVICE_TOKEN"] = token
    env["CADUCEUS_INSTANCE_ID"] = cfg.caduceus_instance_id
    from urllib.parse import urlsplit

    u = urlsplit(cfg.caduceus_base)
    env["CADUCEUS_HOST"] = str(u.hostname)
    env["CADUCEUS_PORT"] = str(u.port)
    with log.open("ab", buffering=0) as out:
        proc = subprocess.Popen(
            [node, str(entry)],
            cwd=str(cfg.caduceus_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )
    pidfile.write_text(f"{proc.pid}\n", encoding="ascii")
    os.chmod(pidfile, 0o600)
    deadline = time.monotonic() + 20.0
    last_error = "not_ready"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RealWorkConfigError(f"caduceus_start_failed_exit_{proc.returncode}")
        try:
            health = client.health()
            return {"started": True, **status(), "pid": proc.pid, "chain": health.get("chain")}
        except Exception as exc:
            last_error = type(exc).__name__
            time.sleep(0.2)
    proc.terminate()
    raise RealWorkConfigError(f"caduceus_start_timeout:{last_error}")


def cold_preflight() -> dict:
    from omnis_wing.absolute.preflight import run_preflight
    from omnis_wing.completion.product_disable import load_manifest

    st = status()
    result = run_preflight()
    manifest = load_manifest()
    forbidden = [
        r["route_id"]
        for r in manifest["routes"]
        if r.get("state") not in ("GOVERNED", "DISABLED")
    ]
    if forbidden:
        raise RealWorkConfigError("coverage_contains_non_dogfood_states")
    if not result.ok:
        raise RealWorkConfigError("preflight_failed:" + ",".join(result.errors))
    return {"state": "READY", "preflight": result.glass, "real_work": st}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="omnis_wing.absolute.real_work.launcher")
    p.add_argument("command", choices=("status", "ensure", "preflight"))
    args = p.parse_args(argv)
    try:
        value = (
            status()
            if args.command == "status"
            else ensure_service()
            if args.command == "ensure"
            else cold_preflight()
        )
    except Exception as exc:
        print(
            json.dumps(
                {"state": "REFUSED", "reason": str(exc), "type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
