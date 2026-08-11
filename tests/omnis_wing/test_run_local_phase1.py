"""Phase 1 WING RUN_LOCAL surface — direct-socket sentinel + intent only."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from omnis_wing.absolute import run_local as rl
from omnis_wing.absolute.real_work import contract as rw_contract

ROOT = Path(__file__).resolve().parents[2]
RUN_LOCAL_PY = ROOT / "omnis_wing" / "absolute" / "run_local.py"


def test_default_config_disabled():
    cfg = rl.default_disabled_config(8080)
    assert cfg["enabled"] is False
    assert cfg["host"] == "127.0.0.1"
    assert cfg["tool_egress_mode"] == "DISABLED"
    assert cfg["provider_id"] == "muse_glimmer_local"


def test_build_intent_no_socket_fields_as_client():
    rl.reset_direct_local_provider_constructions_for_tests()
    intent = rl.build_run_local_intent(
        config=rl.default_disabled_config(),
        messages=[{"role": "user", "content": "hello"}],
    )
    assert intent.route_intent == "RUN_LOCAL"
    assert intent.label == "LOCAL / GOVERNED / TOOLS DISABLED"
    assert intent.tool_egress_mode == "DISABLED"
    assert rl.direct_local_provider_construction_count() == 0


def test_request_dispatches_only_to_caduceus():
    rl.reset_direct_local_provider_constructions_for_tests()
    seen = {}

    def fake_caduceus(intent: rl.RunLocalRouteIntent):
        seen["intent"] = intent
        return {"ok": True, "via": "caduceus"}

    out = rl.request_run_local_turn(
        config={**rl.default_disabled_config(), "enabled": True, "port": 9},
        messages=[{"role": "user", "content": "x"}],
        caduceus_dispatch=fake_caduceus,
    )
    assert out["via"] == "caduceus"
    assert seen["intent"].route_intent == "RUN_LOCAL"
    assert rl.direct_local_provider_construction_count() == 0


def test_sentinel_zero_on_allowed_path_red_on_intentional_construct():
    rl.reset_direct_local_provider_constructions_for_tests()
    assert rl.direct_local_provider_construction_count() == 0
    rl.intentional_direct_local_provider_construct()
    assert rl.direct_local_provider_construction_count() == 1
    rl.reset_direct_local_provider_constructions_for_tests()
    assert rl.direct_local_provider_construction_count() == 0


def test_run_local_module_does_not_import_http_clients():
    """Static: run_local.py must not import openai/httpx/requests/urllib for sockets."""
    src = RUN_LOCAL_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {
        "openai",
        "httpx",
        "requests",
        "urllib",
        "urllib.request",
        "aiohttp",
        "http.client",
        "socket",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
    for b in banned:
        assert b not in imported and b.split(".")[0] not in {
            x for x in imported if x in banned
        }, f"forbidden import {b} in run_local.py: {imported}"


def test_remediation_copy_for_literal_host():
    text = rl.operator_remediation("RUN_LOCAL_LITERAL_ENDPOINT_REQUIRED")
    assert "127.0.0.1" in text
    assert "hostname" in text.lower() or "hostnames" in text.lower()


def test_route_table_honest_for_run_local_addition():
    """RUN_LOCAL is CADUCEUS-owned; wing local client path stays absent/disabled."""
    # Existing honest table must not silently claim wing local socket.
    rw_contract.assert_route_honest("wing.chat_join", "DISABLED")
    # New route id, if present, must be GOVERNED only as caduceus.run_local
    table = dict(rw_contract.ROUTE_TABLE)
    assert table.get("wing.embeddings") == "DISABLED"
    # Do not claim a wing-direct local model route exists.
    assert "wing.local_model_socket" not in table
