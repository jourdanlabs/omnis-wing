"""Install product-disable wrappers on AI side-doors. Idempotent."""

from __future__ import annotations

import importlib
from typing import Callable

from omnis_wing.completion.product_disable import WingRouteDisabled

_INSTALLED = False


def _refuse(route_id: str, reason: str) -> Callable:
    def _fn(*args, **kwargs):
        raise WingRouteDisabled(route_id, reason)

    return _fn


def install_side_door_guards() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    reason = "AI side-door disabled in OMNIS WING completion candidate; primary governed path only"
    targets = [
        ("tools.vision_tools", "tools.vision_tools", "agent.auxiliary not used"),
    ]
    # Patch by replacing module callables when present
    patches = [
        ("tools.vision_tools", ["analyze_image", "vision_analyze", "describe_image", "main"], "tools.vision_tools"),
        ("tools.tts_tool", ["text_to_speech", "tts", "run_tts"], "tools.tts_tool"),
        ("tools.transcription_tools", ["transcribe", "transcribe_audio"], "tools.transcription_tools"),
        ("tools.mixture_of_agents_tool", ["mixture_of_agents", "run_mixture"], "tools.mixture_of_agents_tool"),
        ("tools.image_generation_tool", ["generate_image", "image_generate"], "tools.image_generation_tool"),
        ("agent.auxiliary_client", ["call_llm", "chat_completion", "complete"], "agent.auxiliary_client.chat_completions"),
    ]
    for mod_name, names, route in patches:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for n in names:
            if hasattr(mod, n) and callable(getattr(mod, n)):
                setattr(mod, n, _refuse(route, reason))
        # Also wrap common Client factory patterns
        if hasattr(mod, "get_async_client"):
            setattr(mod, "get_async_client", _refuse(route, reason))
        if hasattr(mod, "get_client"):
            setattr(mod, "get_client", _refuse(route, reason))

    # auxiliary_client: wrap AuxClient create path if class exists
    try:
        aux = importlib.import_module("agent.auxiliary_client")
        for cls_name in ("AuxiliaryClient", "OpenAIAuxiliaryClient", "ChatCompletionsClient"):
            cls = getattr(aux, cls_name, None)
            if cls is None:
                continue
            if hasattr(cls, "chat"):
                pass
        # Wrap module-level call_llm-style functions more broadly
        for attr in dir(aux):
            if attr.startswith("_"):
                continue
            obj = getattr(aux, attr)
            if callable(obj) and any(
                k in attr.lower()
                for k in ("complete", "chat", "call_llm", "run_aux", "auxiliary_call")
            ):
                setattr(aux, attr, _refuse("agent.auxiliary_client.chat_completions", reason))
    except Exception:
        pass

    _INSTALLED = True


# Auto-install on import of completion package
install_side_door_guards()
