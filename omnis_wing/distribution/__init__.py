"""OMNIS WING product distribution: package, install, operator bundle, matrix.

This package owns the reproducible install path for the WING dogfood product.
It never calls a live provider and never mutates live Hermes profiles.
"""

from __future__ import annotations

from .operator_bundle import build_operator_bundle, OperatorBundle
from .package_gate import build_python_artifacts, install_into_venv, installed_identity
from .routes import closed_route_inventory

__all__ = [
    "OperatorBundle",
    "build_operator_bundle",
    "build_python_artifacts",
    "install_into_venv",
    "installed_identity",
    "closed_route_inventory",
]
