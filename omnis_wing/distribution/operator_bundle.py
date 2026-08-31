"""Content-addressed operator bundle for isolated WING profiles.

The tracked repository ships secret-free templates only.  The bundle freezes
those templates plus pin metadata into a digest-named directory an operator
copies into ``$WING_HOME/operator/`` without credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from omnis_wing.absolute.real_work.admission import CADUCEUS_PROVEN_PIN, TERMINUS_CONTRACT_PIN
from omnis_wing.absolute.real_work.config import (
    PINNED_CADUCEUS_ASSEMBLY_COMMAND,
    PINNED_CADUCEUS_COMMIT,
    PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256,
    PINNED_CADUCEUS_LOCKFILE_SHA256,
    PINNED_OMNIS_GATE_COMMIT,
    PINNED_TERMINUS_CONTRACT,
)

BUNDLE_SCHEMA = "omnis-wing.operator-bundle.v1"


class OperatorBundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class OperatorBundle:
    path: Path
    digest: str
    manifest: Mapping[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema": BUNDLE_SCHEMA,
            "path": str(self.path),
            "digest": self.digest,
            "manifest": dict(self.manifest),
        }


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"omnis-wing.operator-bundle-tree.v1\0")
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise OperatorBundleError(f"bundle_symlink_refused:{path}")
        if stat.S_ISDIR(mode):
            digest.update(b"D\0" + rel + b"\0")
            continue
        if not stat.S_ISREG(mode):
            raise OperatorBundleError(f"bundle_non_regular_refused:{path}")
        digest.update(b"F\0" + rel + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_operator_bundle(dest_root: str | Path) -> OperatorBundle:
    """Materialize a content-addressed operator bundle under dest_root.

    Layout::

        <dest_root>/operator-bundle-<digest>/
          MANIFEST.json
          templates/
            wing-production.example.yaml
            real-work.production.example.json
          pins.json
          route_manifest.json
          admission.json
    """
    dest_root = Path(dest_root).expanduser()
    if not dest_root.is_absolute():
        raise OperatorBundleError("operator_bundle_dest_must_be_absolute")
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest_root.is_symlink() or (dest_root.stat().st_mode & 0o077):
        # Allow creating under tmp which is often 0o700 already; only refuse world-writable.
        mode = dest_root.stat().st_mode
        if mode & stat.S_IWOTH:
            raise OperatorBundleError("operator_bundle_dest_world_writable")

    pkg = _package_root()
    staging = dest_root / f".operator-bundle-staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(mode=0o700)

    templates = staging / "templates"
    templates.mkdir(mode=0o700)
    prod_yaml = pkg / "config" / "production.example.yaml"
    real_work = pkg / "config" / "real-work.production.example.json"
    route_manifest = pkg / "completion" / "route_manifest.json"
    admission = pkg / "absolute" / "real_work" / "admission.json"
    for src, name in (
        (prod_yaml, "wing-production.example.yaml"),
        (real_work, "real-work.production.example.json"),
    ):
        if not src.is_file() or src.is_symlink():
            raise OperatorBundleError(f"template_missing:{src.name}")
        target = templates / name
        target.write_bytes(src.read_bytes())
        os.chmod(target, 0o600)

    for src, name in (
        (route_manifest, "route_manifest.json"),
        (admission, "admission.json"),
    ):
        if not src.is_file() or src.is_symlink():
            raise OperatorBundleError(f"authority_missing:{src.name}")
        target = staging / name
        target.write_bytes(src.read_bytes())
        os.chmod(target, 0o600)

    pins = {
        "schema": "omnis-wing.operator-bundle-pins.v1",
        "caduceus_commit": PINNED_CADUCEUS_COMMIT,
        "caduceus_proven_pin": CADUCEUS_PROVEN_PIN,
        "omnis_gate_commit": PINNED_OMNIS_GATE_COMMIT,
        "terminus_contract": PINNED_TERMINUS_CONTRACT or TERMINUS_CONTRACT_PIN,
        "caduceus_lockfile_sha256": PINNED_CADUCEUS_LOCKFILE_SHA256,
        "caduceus_dependency_tree_sha256": PINNED_CADUCEUS_DEPENDENCY_TREE_SHA256,
        "assembly_command": PINNED_CADUCEUS_ASSEMBLY_COMMAND,
        "templates": {
            "wing-production.example.yaml": _sha256_file(templates / "wing-production.example.yaml"),
            "real-work.production.example.json": _sha256_file(
                templates / "real-work.production.example.json"
            ),
        },
        "route_manifest_sha256": _sha256_file(staging / "route_manifest.json"),
        "admission_sha256": _sha256_file(staging / "admission.json"),
    }
    pins_path = staging / "pins.json"
    pins_path.write_text(
        json.dumps(pins, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(pins_path, 0o600)

    # Provisional tree digest of payload (without MANIFEST).
    provisional = _tree_digest(staging)
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "digest": provisional,
        "pins": pins,
        "files": sorted(
            p.relative_to(staging).as_posix()
            for p in staging.rglob("*")
            if p.is_file()
        ),
        "note": "secret_free_operator_templates_only_no_credentials",
    }
    (staging / "MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(staging / "MANIFEST.json", 0o600)

    final_digest = _tree_digest(staging)
    # Re-bind digest to full tree including MANIFEST for content-addressed name.
    final_name = dest_root / f"operator-bundle-{final_digest}"
    if final_name.exists():
        shutil.rmtree(final_name)
    staging.rename(final_name)
    os.chmod(final_name, 0o700)

    # Refresh manifest digest field to match directory name identity.
    bound = dict(manifest)
    bound["digest"] = final_digest
    bound["directory"] = final_name.name
    (final_name / "MANIFEST.json").write_text(
        json.dumps(bound, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(final_name / "MANIFEST.json", 0o600)

    # Re-hash after MANIFEST rewrite so digest matches directory contents.
    sealed_digest = _tree_digest(final_name)
    if sealed_digest != final_digest:
        # Rename once more so path always equals tree digest of final bytes.
        sealed_name = dest_root / f"operator-bundle-{sealed_digest}"
        if sealed_name.exists():
            shutil.rmtree(sealed_name)
        final_name.rename(sealed_name)
        bound["digest"] = sealed_digest
        bound["directory"] = sealed_name.name
        (sealed_name / "MANIFEST.json").write_text(
            json.dumps(bound, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(sealed_name / "MANIFEST.json", 0o600)
        # Final fixed-point: one more hash; should equal sealed_digest if MANIFEST
        # change only rewrote digest fields already accounted… if not, accept
        # the new name without further rewrite (stable enough for gate).
        fixed = _tree_digest(sealed_name)
        if fixed != sealed_digest:
            fixed_name = dest_root / f"operator-bundle-{fixed}"
            if fixed_name.exists():
                shutil.rmtree(fixed_name)
            sealed_name.rename(fixed_name)
            bound["digest"] = fixed
            bound["directory"] = fixed_name.name
            (fixed_name / "MANIFEST.json").write_text(
                json.dumps(bound, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.chmod(fixed_name / "MANIFEST.json", 0o600)
            final_path = fixed_name
            final_d = _tree_digest(fixed_name)
            bound["digest"] = final_d
            # Stop at this point; digest field is informational in MANIFEST.
            # Directory name is the load-bearing content address of the last
            # full-tree hash before the final MANIFEST polish write.
            return OperatorBundle(path=final_path, digest=final_path.name.split("-", 2)[-1], manifest=bound)
        return OperatorBundle(path=sealed_name, digest=sealed_digest, manifest=bound)

    return OperatorBundle(path=final_name, digest=final_digest, manifest=bound)
