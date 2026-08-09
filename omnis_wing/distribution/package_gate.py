"""Build wheel/sdist and install into a disposable venv; report identities."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any, Mapping, Optional


class PackageGateError(RuntimeError):
    pass


def _repo_root() -> Path:
    # omnis_wing/distribution/package_gate.py → parents[2] = repo root when
    # running from a source tree; when installed from a wheel, callers must
    # pass explicit source_root.
    here = Path(__file__).resolve()
    candidate = here.parents[2]
    if (candidate / "pyproject.toml").is_file() and (candidate / "omnis_wing").is_dir():
        return candidate
    raise PackageGateError("source_root_unavailable_pass_explicitly")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_python_artifacts(
    *,
    source_root: Optional[str | Path] = None,
    dist_dir: Optional[str | Path] = None,
    python: Optional[str] = None,
) -> dict[str, Any]:
    """Build wheel + sdist via ``python -m build`` (fallback: pip wheel)."""
    root = Path(source_root) if source_root else _repo_root()
    if not (root / "pyproject.toml").is_file():
        raise PackageGateError("pyproject_missing")
    out = Path(dist_dir) if dist_dir else root / ".omnis-wing-build" / "dist"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    py = python or sys.executable

    # Prefer stdlib-adjacent `build` if present; otherwise use pip wheel + sdist
    # via setuptools (always available as build backend).
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = env.get("SOURCE_DATE_EPOCH", "1700000000")
    try:
        subprocess.run(
            [py, "-m", "build", "--outdir", str(out)],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback path: ensure build is installed into a temporary tool venv is
        # heavy; use pip wheel + setuptools sdist instead.
        subprocess.run(
            [py, "-m", "pip", "install", "--quiet", "build>=1.0,<2"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        subprocess.run(
            [py, "-m", "build", "--outdir", str(out)],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )

    wheels = sorted(out.glob("*.whl"))
    sdists = sorted(out.glob("*.tar.gz"))
    if not wheels:
        raise PackageGateError("wheel_missing")
    if not sdists:
        raise PackageGateError("sdist_missing")
    artifacts = []
    for path in [*wheels, *sdists]:
        artifacts.append(
            {
                "path": str(path),
                "name": path.name,
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
                "kind": "wheel" if path.suffix == ".whl" else "sdist",
            }
        )
    return {
        "schema": "omnis-wing.python-artifacts.v1",
        "source_root": str(root),
        "dist_dir": str(out),
        "artifacts": artifacts,
        "wheel": next(a for a in artifacts if a["kind"] == "wheel"),
        "sdist": next(a for a in artifacts if a["kind"] == "sdist"),
    }


def install_into_venv(
    *,
    wheel_path: str | Path,
    venv_dir: str | Path,
    clear: bool = True,
) -> dict[str, Any]:
    """Create a fresh venv and install the given wheel with no deps isolation opt.

    Uses ``pip install --no-deps`` only when ``OMNIS_WING_DIST_NO_DEPS=1`` so
    default installs remain runnable. Distribution identity checks only need
    the package files; matrix may need deps.
    """
    wheel = Path(wheel_path)
    if not wheel.is_file() or wheel.is_symlink():
        raise PackageGateError("wheel_not_regular_file")
    venv_path = Path(venv_dir)
    if clear and venv_path.exists():
        shutil.rmtree(venv_path)
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    builder = venv.EnvBuilder(with_pip=True, clear=False, symlinks=True)
    builder.create(str(venv_path))
    if sys.platform == "win32":
        py = venv_path / "Scripts" / "python.exe"
        pip = venv_path / "Scripts" / "pip.exe"
    else:
        py = venv_path / "bin" / "python"
        pip = venv_path / "bin" / "pip"
    if not py.is_file():
        raise PackageGateError("venv_python_missing")
    cmd = [str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    install_cmd = [str(py), "-m", "pip", "install", str(wheel)]
    if os.environ.get("OMNIS_WING_DIST_NO_DEPS") == "1":
        install_cmd.insert(-1, "--no-deps")
    subprocess.run(install_cmd, check=True, capture_output=True, text=True, timeout=600)
    return {
        "schema": "omnis-wing.venv-install.v1",
        "venv": str(venv_path),
        "python": str(py),
        "pip": str(pip),
        "wheel": str(wheel),
        "wheel_sha256": _sha256_file(wheel),
    }


def installed_identity(*, python: str | Path) -> dict[str, Any]:
    """Import omnis_wing from the installed interpreter and report identity."""
    py = str(python)
    script = r"""
import hashlib, json, importlib.util, omnis_wing, omnis_wing.completion, omnis_wing.absolute.real_work
from pathlib import Path
from omnis_wing.absolute.real_work.config import (
    PINNED_CADUCEUS_COMMIT,
    PINNED_CADUCEUS_LOCKFILE_SHA256,
    PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256,
    PINNED_OMNIS_GATE_COMMIT,
)
from omnis_wing.absolute.real_work.admission import assert_contract_not_drifted, admission_manifest
from omnis_wing.distribution.routes import closed_route_inventory, route_manifest_digest
from omnis_wing.completion.product_disable import load_manifest

assert_contract_not_drifted()
inv = closed_route_inventory()
man = load_manifest()
root = Path(omnis_wing.__file__).resolve().parent
files = {}
for rel in (
    "completion/route_manifest.json",
    "absolute/real_work/admission.json",
    "config/real-work.production.example.json",
    "config/production.example.yaml",
):
    p = root / rel
    files[rel] = {
        "exists": p.is_file(),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
    }
print(json.dumps({
    "schema": "omnis-wing.installed-identity.v1",
    "omnis_wing_path": str(root),
    "caduceus_commit": PINNED_CADUCEUS_COMMIT,
    "omnis_gate_commit": PINNED_OMNIS_GATE_COMMIT,
    "lockfile_sha256": PINNED_CADUCEUS_LOCKFILE_SHA256,
    "dependency_tree_sha256": PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256,
    "route_inventory": inv,
    "route_manifest_digest": route_manifest_digest(),
    "admission": admission_manifest(),
    "files": files,
    "summary": man.get("summary"),
}, sort_keys=True))
"""
    proc = subprocess.run(
        [py, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(proc.stdout)
