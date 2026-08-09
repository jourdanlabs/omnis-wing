"""M7 startup preflight — deny model egress if not ready."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from omnis_wing.absolute.signed_policy import PolicyError, load_policy
from omnis_wing.absolute.external_anchor import resolve_anchor_status
from omnis_wing.absolute.ledger_security import LedgerSecurityError, prepare_private_ledger_file
from omnis_wing.completion.product_disable import load_manifest
from omnis_wing.absolute.production_config import load_production_config, signer_mode
from omnis_wing.absolute.runtime_attach import attach_wing_runtime, build_signer_from_config
from omnis_wing.absolute.receipt_spine import GENESIS_PREV


@dataclass
class PreflightResult:
    ok: bool
    errors: List[str]
    glass: dict

    def raise_if_blocking(self) -> None:
        if not self.ok:
            raise RuntimeError("preflight_failed:" + ",".join(self.errors))


def run_preflight(agent=None) -> PreflightResult:
    errors: List[str] = []
    policy_valid = True
    policy_mode = "enforce"
    require_anchor = False
    policy_digest_display: Optional[str] = None
    # P0-1: ambient force-classification must never affect production classification.
    # Presence is ignored for classify paths (removed) and refused at preflight in
    # enforce/local_only so operators cannot rely on it as a silent bypass switch.
    if (os.environ.get("OMNIS_WING_FORCE_CLASSIFICATION") or "").strip():
        errors.append("force_classification_env_forbidden")

    try:
        pol = load_policy()
        policy_mode = pol.mode
        require_anchor = pol.require_remote_anchor
        if not pol.signature_valid:
            policy_valid = False
            errors.append("policy:signature_invalid")
        else:
            policy_digest_display = pol.policy_digest
        if pol.mode == "deny_all":
            errors.append("policy_deny_all")
    except PolicyError as exc:
        policy_valid = False
        errors.append(f"policy:{exc}")

    # manifest complete
    try:
        man = load_manifest()
        allowed_states = ("GOVERNED", "DISABLED")
        for r in man["routes"]:
            st = r.get("state")
            if st not in allowed_states:
                errors.append(f"route_bad_state:{r.get('route_id')}:{st}")
        if man.get("forbidden_states"):
            for r in man["routes"]:
                if r.get("state") in man["forbidden_states"]:
                    errors.append(f"forbidden_state:{r['route_id']}")
    except Exception as exc:
        errors.append(f"manifest:{type(exc).__name__}")

    signer_ready = False
    mode = signer_mode()
    if mode == "test":
        signer_ready = True  # explicit dogfood
    else:
        try:
            cfg = load_production_config(require=False)
            if cfg is None:
                errors.append("no_production_config")
            else:
                if agent is not None:
                    st = attach_wing_runtime(agent, force=True)
                    signer_ready = bool(st.get("ready"))
                    if not signer_ready:
                        errors.append("signer_not_ready")
                else:
                    from omnis_wing.absolute.runtime_attach import build_signer_from_config
                    sig = build_signer_from_config(cfg)
                    signer_ready = getattr(sig, "available", lambda: False)()
                    if not signer_ready:
                        errors.append("signer_not_ready")
        except Exception as exc:
            errors.append(f"signer:{type(exc).__name__}")

    # private ledger path when production
    if mode == "production":
        try:
            cfg = load_production_config(require=False)
            if cfg:
                lp = Path(cfg.ledger_dir) / "wing-production-ledger.jsonl"
                prepare_private_ledger_file(lp)
        except LedgerSecurityError as exc:
            errors.append(f"ledger:{exc}")
        except Exception as exc:
            errors.append(f"ledger:{type(exc).__name__}")

        try:
            from omnis_wing.absolute.real_work.config import (
                assert_pinned_caduceus_tree,
                load_real_work_config,
                service_capability,
            )

            rw = load_real_work_config(require=True)
            assert rw is not None
            assert_pinned_caduceus_tree(rw)
            service_capability(rw)
        except Exception as exc:
            errors.append(f"real_work:{type(exc).__name__}:{exc}")

    anchor = resolve_anchor_status(GENESIS_PREV)
    if require_anchor and anchor.state != "VERIFIED":
        errors.append(f"anchor:{anchor.state}")

    from omnis_wing.absolute.glass import glass_state

    g = glass_state(
        signer_ready=signer_ready and not any(e.startswith("signer") for e in errors),
        chain_valid=True,  # empty/ok at startup
        policy_valid=policy_valid,
        policy_mode=policy_mode,
        anchor_state=anchor.state,
        require_anchor=require_anchor,
        ungoverned_route=any(e.startswith("route_") for e in errors),
    )
    ok = len(errors) == 0 and g["color"] == "GREEN"
    if mode == "test":
        # dogfood: allow green path with test signer if policy ok —
        # still hard-fail force-classification env (must never be a silent switch).
        ok = policy_valid and not any(
            x.startswith("route_")
            or x.startswith("policy")
            or x.startswith("force_classification")
            for x in errors
        )
    return PreflightResult(ok=ok, errors=errors, glass=g)
