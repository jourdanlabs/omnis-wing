"""Tests for the Nous-Wing-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"wing"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``wing-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "wing" tag namespace.

``is_nous_wing_non_agentic`` should only match the actual Nous Research
Wing-3 / Wing-4 chat family.
"""

from __future__ import annotations

import pytest

from wing_cli.model_switch import (
    _WING_MODEL_WARNING,
    _check_wing_model_warning,
    is_nous_wing_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Wing-3-Llama-3.1-70B",
        "NousResearch/Wing-3-Llama-3.1-405B",
        "wing-3",
        "Wing-3",
        "wing-4",
        "wing-4-405b",
        "wing_4_70b",
        "openrouter/hermes3:70b",
        "openrouter/nousresearch/wing-4-405b",
        "NousResearch/Wing3",
        "wing-3.1",
    ],
)
def test_matches_real_nous_wing_chat_models(model_name: str) -> None:
    assert is_nous_wing_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous WING 3/4"
    )
    assert _check_wing_model_warning(model_name) == _WING_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "wing-brain:qwen3-14b-ctx16k",
        "wing-brain:qwen3-14b-ctx32k",
        "wing-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat WING models we don't warn about
        "wing-llm-2",
        "hermes2-pro",
        "nous-wing-2-mistral",
        # Edge cases
        "",
        "wing",  # bare "wing" isn't the 3/4 family
        "wing-brain",
        "brain-wing-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_wing_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous WING 3/4"
    )
    assert _check_wing_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_wing_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_wing_model_warning("") == ""
