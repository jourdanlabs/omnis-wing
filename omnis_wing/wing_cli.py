"""WING operator CLI — `wing pan` loads sealed Pan, not Hermes bread."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from omnis_wing.sealed_soul import (
    PAN_SOUL_ID,
    REFUSAL_NOT_OPEN,
    REFUSAL_VERIFY,
    SoulLoadRefused,
    default_souls_dir,
    load_pan_soul,
    stage_pan_soul_for_hermes,
    verify_sealed_soul,
)


def _default_profile_home() -> Path:
    raw = os.environ.get("OMNIS_WING_PAN_PROFILE_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".hermes" / "profiles" / "pan-wing"


def _wing_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _hermes_python() -> Path:
    override = os.environ.get("OMNIS_WING_HERMES_PYTHON")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"


def cmd_pan_identity(args: argparse.Namespace) -> int:
    souls_dir = Path(args.souls_dir) if getattr(args, "souls_dir", "") else None
    try:
        loaded = load_pan_soul(souls_dir)
    except SoulLoadRefused as exc:
        payload = {
            "ok": False,
            "refused": True,
            "soul_id": PAN_SOUL_ID,
            "verdict": exc.verification.verdict,
            "message": exc.verification.message,
            "reply": REFUSAL_NOT_OPEN if exc.verification.verdict == "MISSING" else REFUSAL_VERIFY,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(payload["reply"], file=sys.stderr)
            print(exc.verification.message, file=sys.stderr)
        return 2

    payload = {
        "ok": True,
        "refused": False,
        "soul_id": loaded.soul_id,
        "name": loaded.name,
        "pronouns": loaded.pronouns,
        "sealed_path": str(loaded.soul_path),
        "souls_dir": str(loaded.package_dir.parent),
        "verdict": loaded.verification.verdict,
        "bedrock_hash": loaded.verification.bedrock_hash,
        "chain_ok": loaded.verification.chain_ok,
        "chain_count": loaded.verification.chain_count,
        "identity_card": loaded.identity_card,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"Pan ({loaded.soul_id}) — {loaded.verification.verdict}")
    print(f"Sealed: {loaded.soul_path}")
    print()
    print(loaded.identity_card)
    return 0


def cmd_pan_verify(args: argparse.Namespace) -> int:
    souls_dir = Path(args.souls_dir) if args.souls_dir else None
    result = verify_sealed_soul(PAN_SOUL_ID, souls_dir)
    payload = {
        "ok": result.ok,
        "verdict": result.verdict,
        "soul_id": result.soul_id,
        "message": result.message,
        "bedrock_hash": result.bedrock_hash,
        "chain_ok": result.chain_ok,
        "chain_count": result.chain_count,
        "issues": list(result.issues),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.ok else 1


def cmd_pan_chat(args: argparse.Namespace) -> int:
    profile_home = Path(args.profile_home).expanduser()
    souls_dir = Path(args.souls_dir) if args.souls_dir else None
    try:
        loaded = stage_pan_soul_for_hermes(profile_home, souls_dir)
    except SoulLoadRefused as exc:
        print(REFUSAL_NOT_OPEN if exc.verification.verdict == "MISSING" else REFUSAL_VERIFY, file=sys.stderr)
        print(exc.verification.message, file=sys.stderr)
        return 2

    py = _hermes_python()
    if not py.is_file():
        print(f"[wing pan] missing Hermes python: {py}", file=sys.stderr)
        return 127

    root = _wing_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(root)
    env["HERMES_HOME"] = str(profile_home)
    env["OMNIS_WING_PAN_SOUL_ID"] = loaded.soul_id
    env["OMNIS_WING_PAN_SEALED_PATH"] = str(loaded.soul_path)
    if env.get("OMNIS_WING_QUIET_BANNER") != "1":
        print(f"[wing pan] HERMES_HOME={profile_home}", file=sys.stderr)
        print(f"[wing pan] sealed={loaded.soul_path}", file=sys.stderr)
        print(f"[wing pan] verdict={loaded.verification.verdict}", file=sys.stderr)

    hermes_argv = [str(py), "-c", "import sys; from hermes_cli.main import main; sys.exit(main())", "chat"]
    hermes_argv.extend(args.hermes_args)
    return subprocess.call(hermes_argv, env=env)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wing", description="OMNIS WING operator commands")
    sub = p.add_subparsers(dest="agent", required=True)

    pan = sub.add_parser("pan", help="Pan identity seat (sealed soul_bb75a9fa2823)")
    pan.add_argument("--json", action="store_true", help="JSON output (identity default)")
    pan.add_argument("--souls-dir", default="", help="override MTS souls directory")
    pan_sub = pan.add_subparsers(dest="pan_cmd")

    identity = pan_sub.add_parser("identity", help="load + show Pan identity card")
    identity.add_argument("--json", action="store_true")
    identity.add_argument("--souls-dir", default="")
    identity.set_defaults(handler=cmd_pan_identity)

    verify = pan_sub.add_parser("verify", help="verify sealed Pan package")
    verify.add_argument("--souls-dir", default="")
    verify.set_defaults(handler=cmd_pan_verify)

    chat = pan_sub.add_parser("chat", help="stage sealed Pan SOUL and launch Hermes chat")
    chat.add_argument("--profile-home", default=str(_default_profile_home()))
    chat.add_argument("--souls-dir", default="")
    chat.add_argument("hermes_args", nargs=argparse.REMAINDER)
    chat.set_defaults(handler=cmd_pan_chat)

    pan.set_defaults(handler=cmd_pan_identity, pan_cmd="identity")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.agent != "pan":
        parser.error(f"unsupported agent {args.agent!r}")
    pan_cmd = getattr(args, "pan_cmd", None)
    if pan_cmd is None:
        return cmd_pan_identity(args)
    handler = getattr(args, "handler", cmd_pan_identity)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
