"""Host entry used by OMNIS WING wiring — all provider traffic must enter here."""

from __future__ import annotations

from omnis_wing.boundary import ActionEnvelope, Provider, Receipt, decide_and_maybe_call


def dispatch_action(envelope: ActionEnvelope, provider: Provider) -> Receipt:
    """Sole outbound path for v0 host actions."""
    return decide_and_maybe_call(envelope, provider)
