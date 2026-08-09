"""CLI for OMNIS WING product distribution gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omnis-wing-distribution",
        description="Package, install, and cold-gate OMNIS WING distribution",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bundle = sub.add_parser("operator-bundle", help="build content-addressed operator bundle")
    p_bundle.add_argument(
        "--dest",
        default="",
        help="absolute destination root (default: temp under /tmp)",
    )

    p_build = sub.add_parser("build", help="build wheel + sdist")
    p_build.add_argument("--source-root", default="")
    p_build.add_argument("--dist-dir", default="")

    p_install = sub.add_parser("install-identity", help="install wheel into fresh venv and report identity")
    p_install.add_argument("--wheel", required=True)
    p_install.add_argument("--venv", required=True)

    p_routes = sub.add_parser("routes", help="emit closed route inventory")

    p_matrix = sub.add_parser(
        "external-matrix",
        help="run shared matrix via real CADUCEUS + external loopback fake",
    )
    p_matrix.add_argument(
        "--caduceus-root",
        required=True,
        help="absolute path to pinned CADUCEUS worktree",
    )
    p_matrix.add_argument("--work-dir", default="")

    p_gate = sub.add_parser(
        "gate",
        help="full distribution gate: build, install, routes, optional matrix",
    )
    p_gate.add_argument("--source-root", default="")
    p_gate.add_argument("--out", default="")
    p_gate.add_argument("--caduceus-root", default="")
    p_gate.add_argument("--skip-matrix", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "operator-bundle":
        from omnis_wing.distribution.operator_bundle import build_operator_bundle

        dest = args.dest or tempfile.mkdtemp(prefix="wing-operator-bundle-")
        bundle = build_operator_bundle(dest)
        print(json.dumps(bundle.public_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "build":
        from omnis_wing.distribution.package_gate import build_python_artifacts

        result = build_python_artifacts(
            source_root=args.source_root or None,
            dist_dir=args.dist_dir or None,
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0

    if args.command == "install-identity":
        from omnis_wing.distribution.package_gate import install_into_venv, installed_identity

        inst = install_into_venv(wheel_path=args.wheel, venv_dir=args.venv)
        identity = installed_identity(python=inst["python"])
        print(json.dumps({"install": inst, "identity": identity}, sort_keys=True, indent=2))
        return 0

    if args.command == "routes":
        from omnis_wing.distribution.routes import closed_route_inventory

        print(json.dumps(closed_route_inventory(), sort_keys=True, indent=2))
        return 0

    if args.command == "external-matrix":
        from omnis_wing.distribution.external_matrix import run_external_matrix

        result = run_external_matrix(
            caduceus_root=args.caduceus_root,
            work_dir=args.work_dir or None,
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result.get("all_pass") else 2

    if args.command == "gate":
        from omnis_wing.distribution.operator_bundle import build_operator_bundle
        from omnis_wing.distribution.package_gate import (
            build_python_artifacts,
            install_into_venv,
            installed_identity,
        )
        from omnis_wing.distribution.routes import closed_route_inventory

        out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="wing-dist-gate-"))
        out.mkdir(parents=True, exist_ok=True)
        report: dict = {"schema": "omnis-wing.distribution-gate.v1", "out": str(out)}

        report["routes"] = closed_route_inventory()
        report["operator_bundle"] = build_operator_bundle(out / "bundles").public_dict()
        artifacts = build_python_artifacts(
            source_root=args.source_root or None,
            dist_dir=out / "dist",
        )
        report["artifacts"] = artifacts
        venv_dir = out / "venv"
        install = install_into_venv(wheel_path=artifacts["wheel"]["path"], venv_dir=venv_dir)
        report["install"] = install
        report["installed_identity"] = installed_identity(python=install["python"])

        if not args.skip_matrix and args.caduceus_root:
            from omnis_wing.distribution.external_matrix import run_external_matrix

            report["matrix"] = run_external_matrix(
                caduceus_root=args.caduceus_root,
                work_dir=out / "matrix",
            )
        elif not args.skip_matrix:
            report["matrix"] = {
                "skipped": True,
                "reason": "caduceus_root_not_provided",
            }

        report_path = out / "DISTRIBUTION_GATE_REPORT.json"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True, indent=2))
        matrix = report.get("matrix") or {}
        if matrix.get("skipped"):
            return 0
        if matrix and not matrix.get("all_pass"):
            return 2
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
