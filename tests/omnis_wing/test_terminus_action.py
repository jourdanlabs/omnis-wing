"""WING client for canonical CADUCEUS TERMINUS — live CLI + hook surface."""

from __future__ import annotations

import json

import pytest

import omnis_wing.terminus_action as terminus_action
from omnis_wing.terminus_action import block_message, cli_path


@pytest.mark.terminus_live
def test_cli_allow_echo():
    assert cli_path() is not None, "CADUCEUS terminus-authorize.mjs must exist"
    out = terminus_action.authorize_action(
        agent_id="wing", kind="shell", payload="echo ok", session_id="t"
    )
    assert out["verdict"] == "ALLOW"
    assert out["decision"] == "PERMIT"
    rec = out["receipt"] or {}
    blob = json.dumps(rec)
    assert "echo ok" not in blob


@pytest.mark.terminus_live
def test_cli_refuse_rm_rf_root():
    out = terminus_action.authorize_action(
        agent_id="wing", kind="shell", payload="rm -rf /", session_id="t"
    )
    assert out["verdict"] == "REFUSE"
    assert out["reason"] == "action_catastrophic"


@pytest.mark.terminus_live
def test_cli_hold_pkill():
    out = terminus_action.authorize_action(
        agent_id="wing", kind="shell", payload="pkill python", session_id="t"
    )
    assert out["verdict"] == "HOLD"
    assert "HOLD" in block_message(out)


@pytest.mark.terminus_live
def test_cli_refuse_sudo():
    out = terminus_action.authorize_action(
        agent_id="wing", kind="shell", payload="sudo id", session_id="t"
    )
    assert out["verdict"] == "REFUSE"


def test_stub_allow_is_the_test_default():
    # Autouse conftest stub — proves the hook import path, not CADUCEUS.
    out = terminus_action.authorize_action(
        agent_id="wing", kind="shell", payload="sudo id", session_id="t"
    )
    assert out["verdict"] == "ALLOW"
