"""M6 operator glass — visible enforcement state."""

from __future__ import annotations

from typing import Any, Optional


def glass_state(
    *,
    signer_ready: bool,
    chain_valid: bool,
    policy_valid: bool,
    policy_mode: str,
    anchor_state: str,
    require_anchor: bool,
    ungoverned_route: bool,
    last_phase: Optional[str] = None,
    last_decision: Optional[str] = None,
) -> dict:
    red_reasons = []
    if not signer_ready:
        red_reasons.append("signer_unavailable")
    if not chain_valid:
        red_reasons.append("invalid_chain")
    if not policy_valid:
        red_reasons.append("stale_or_invalid_policy")
    if require_anchor and anchor_state not in ("VERIFIED",):
        red_reasons.append("anchor_required_not_verified")
    if ungoverned_route:
        red_reasons.append("ungoverned_registered_route")
    if policy_mode not in ("enforce", "local_only", "deny_all"):
        red_reasons.append("bad_policy_mode")

    color = "RED" if red_reasons else "GREEN"
    label = "AI EGRESS GOVERNED" if color == "GREEN" else "AI EGRESS NOT HEALTHY"
    # never claim SENT/COMPLETED from AUTHORIZED alone
    display_phase = last_phase or "NONE"
    if display_phase in ("AUTHORIZED",) and last_decision == "PERMIT":
        display_phase = "AUTHORIZED_NOT_SENT"

    return {
        "glass": label,
        "color": color,
        "red_reasons": red_reasons,
        "coverage_boundary": "WING-owned supported AI transmissions only",
        "outside_boundary": [
            "IDE",
            "terminal",
            "browser",
            "git",
            "third_party_extensions",
            "live_hermes_install_until_cutover",
        ],
        "last_phase": display_phase,
        "last_decision": last_decision,
        "policy_mode": policy_mode,
        "anchor_state": anchor_state,
    }
