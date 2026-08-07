"""Operator-facing CLI for OMNIS WING R4 enrollment + health.

  python -m omnis_wing.operator_cli status --backend test --tag ai.jourdanlabs.omnis-wing.test.r4
  python -m omnis_wing.operator_cli enroll --backend test --tag ai.jourdanlabs.omnis-wing.test.r4
  python -m omnis_wing.operator_cli health --ledger /path/ledger.jsonl --backend test --tag ...

Never enrolls as a side effect of import or chat-path startup.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from omnis_wing.absolute.operator_health import build_health_report, health_to_json
from omnis_wing.absolute.production_signer import (
    CAPTAIN_R4_TAG,
    DisposableTestBackend,
    MacOSKeychainBackend,
    ProductionSignerAdapter,
    compile_keychain_bridge,
    default_bridge_binary,
)
from omnis_wing.absolute.receipt_spine import EvidenceLedger


def _backend(args) -> ProductionSignerAdapter:
    if args.backend == "test":
        if args.tag == CAPTAIN_R4_TAG:
            print("refusing: test backend cannot use Captain production tag", file=sys.stderr)
            sys.exit(2)
        # Persist enrollment in a small state file for CLI demo only
        state = Path(args.state_dir) / "test_enroll.json"
        enrolled = False
        if state.is_file():
            enrolled = json.loads(state.read_text()).get("enrolled", False)
        be = DisposableTestBackend(tag=args.tag, enrolled=enrolled)
        return ProductionSignerAdapter(backend=be)
    if args.backend == "keychain":
        bridge = Path(args.bridge) if args.bridge else default_bridge_binary()
        if not bridge.is_file():
            print(f"bridge missing: {bridge} (run: compile-bridge)", file=sys.stderr)
            sys.exit(2)
        be = MacOSKeychainBackend(tag=args.tag, bridge_path=bridge)
        return ProductionSignerAdapter(backend=be)
    print("unknown backend", file=sys.stderr)
    sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="omnis_wing.operator_cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--backend", choices=("test", "keychain"), default="test")
        sp.add_argument(
            "--tag",
            default="ai.jourdanlabs.omnis-wing.test.r4",
            help="application tag; Captain production tag only for keychain backend",
        )
        sp.add_argument("--bridge", default="", help="path to compiled keychain bridge")
        sp.add_argument(
            "--state-dir",
            default=".omnis-wing-build/operator-state",
            help="test-backend enrollment state dir (not Keychain)",
        )

    sp = sub.add_parser("status", help="report enrollment without changing keys")
    add_common(sp)

    sp = sub.add_parser("enroll", help="EXPLICIT enrollment only — never auto")
    add_common(sp)

    sp = sub.add_parser("health", help="offline verifier/health (secret-free)")
    add_common(sp)
    sp.add_argument("--ledger", required=True)
    sp.add_argument("--root", default=".")
    sp.add_argument("--anchor", default="")

    sp = sub.add_parser("compile-bridge", help="compile Swift keychain bridge (operator)")
    sp.add_argument("--out-dir", default=".omnis-wing-build")

    args = p.parse_args(argv)
    if args.cmd == "compile-bridge":
        out = compile_keychain_bridge(Path(args.out_dir))
        print(json.dumps({"bridge": str(out), "state": "COMPILED"}))
        return 0

    Path(getattr(args, "state_dir", ".omnis-wing-build/operator-state")).mkdir(
        parents=True, exist_ok=True
    )
    adapter = _backend(args)

    if args.cmd == "status":
        print(json.dumps(adapter.enrollment_status(), sort_keys=True, indent=2))
        return 0

    if args.cmd == "enroll":
        st = adapter.enroll_explicit()
        if args.backend == "test":
            state = Path(args.state_dir) / "test_enroll.json"
            state.write_text(json.dumps({"enrolled": True, "tag": args.tag}) + "\n")
        print(json.dumps(st, sort_keys=True, indent=2))
        return 0

    if args.cmd == "health":
        ledger = EvidenceLedger(Path(args.ledger))
        anchor = Path(args.anchor) if args.anchor else None
        report = build_health_report(
            root=Path(args.root).resolve(),
            ledger=ledger,
            signer=adapter,
            anchor_path=anchor,
            remote_anchor_configured=bool(args.anchor),
        )
        sys.stdout.write(health_to_json(report))
        return 0 if report.get("verifier") in ("OK", "NOT_READY", "DEGRADED_OUTCOME_UNKNOWN") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
