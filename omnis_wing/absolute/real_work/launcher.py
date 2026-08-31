"""Fail-closed operator launcher support for the isolated WING fork."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .caduceus_client import CaduceusRealWorkClient, loopback_origin_is_listening
from .config import (
    RealWorkConfigError,
    assert_pinned_runtime_dependencies,
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
    assert_pinned_runtime_dependencies(cfg)
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
    assert_pinned_runtime_dependencies(cfg)
    token = service_capability(cfg)
    client = CaduceusRealWorkClient(cfg, token=token)
    try:
        return {"started": False, **status()}
    except Exception:
        pass

    if loopback_origin_is_listening(cfg.caduceus_base):
        raise RealWorkConfigError("caduceus_port_collision_untrusted_service")

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
    try:
        identity = _process_identity(proc.pid)
    except Exception:
        proc.terminate()
        raise RealWorkConfigError("caduceus_process_identity_unavailable")
    owner = {
        "schema": "omnis-wing.caduceus-process-owner.v1",
        "pid": proc.pid,
        "process_start": identity["process_start"],
        "command": identity["command"],
        "caduceus_commit": cfg.caduceus_commit,
        "caduceus_base": cfg.caduceus_base,
    }
    pidfile.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="ascii")
    os.chmod(pidfile, 0o600)
    deadline = time.monotonic() + 20.0
    last_error = "not_ready"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pidfile.unlink(missing_ok=True)
            raise RealWorkConfigError(f"caduceus_start_failed_exit_{proc.returncode}")
        try:
            health = client.health()
            return {"started": True, **status(), "pid": proc.pid, "chain": health.get("chain")}
        except Exception as exc:
            last_error = type(exc).__name__
            time.sleep(0.2)
    proc.terminate()
    pidfile.unlink(missing_ok=True)
    raise RealWorkConfigError(f"caduceus_start_timeout:{last_error}")


def _process_identity(pid: int) -> dict[str, str]:
    proc = subprocess.run(
        ["ps", "-o", "lstart=", "-o", "command=", "-p", str(pid)],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    line = proc.stdout.strip()
    if not line:
        raise RealWorkConfigError("caduceus_process_not_running")
    # lstart is five whitespace-delimited fields; the remainder is argv.
    parts = line.split(None, 5)
    if len(parts) != 6:
        raise RealWorkConfigError("caduceus_process_identity_malformed")
    return {"process_start": " ".join(parts[:5]), "command": parts[5]}


def owned_service_status() -> dict:
    cfg = load_real_work_config(require=True)
    assert cfg is not None
    pidfile = _runtime_dir() / "caduceus.pid"
    if not pidfile.is_file() or pidfile.is_symlink():
        raise RealWorkConfigError("caduceus_process_not_owned_by_run")
    try:
        owner = json.loads(pidfile.read_text(encoding="ascii"))
        pid = int(owner["pid"])
    except Exception as exc:
        raise RealWorkConfigError("caduceus_process_owner_record_invalid") from exc
    identity = _process_identity(pid)
    entry = str(cfg.caduceus_root / "src" / "caduceus.mjs")
    if (
        owner.get("schema") != "omnis-wing.caduceus-process-owner.v1"
        or owner.get("process_start") != identity["process_start"]
        or owner.get("command") != identity["command"]
        or owner.get("caduceus_commit") != cfg.caduceus_commit
        or owner.get("caduceus_base") != cfg.caduceus_base
        or entry not in identity["command"]
    ):
        raise RealWorkConfigError("caduceus_process_ownership_mismatch")
    return {"owned": True, "pid": pid, **owner}


def stop_owned_service() -> dict:
    owner = owned_service_status()
    pid = int(owner["pid"])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            (_runtime_dir() / "caduceus.pid").unlink(missing_ok=True)
            return {"state": "STOPPED", "pid": pid, "owned": True}
        time.sleep(0.1)
    raise RealWorkConfigError("caduceus_owned_process_stop_timeout")


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
    p.add_argument("command", choices=("status", "ensure", "preflight", "owned", "stop"))
    args = p.parse_args(argv)
    try:
        value = (
            status()
            if args.command == "status"
            else ensure_service()
            if args.command == "ensure"
            else cold_preflight()
            if args.command == "preflight"
            else owned_service_status()
            if args.command == "owned"
            else stop_owned_service()
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
