"""Hard product-disable of AI side-doors at real handler boundaries."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any, Callable

from omnis_wing.completion.product_disable import WingRouteDisabled

_INSTALLED = False
_INSTALL_ERRORS: list[str] = []
_REASON = (
    "AI side-door disabled in OMNIS WING completion candidate; "
    "use primary governed agent path only"
)


def _refuse(route_id: str) -> Callable[..., Any]:
    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise WingRouteDisabled(route_id, _REASON)

    _fn.__omnis_wing_disabled__ = True  # type: ignore[attr-defined]
    _fn.__omnis_wing_route_id__ = route_id  # type: ignore[attr-defined]
    return _fn


def _stub_missing_deps() -> None:
    """Allow importing tool modules in cold env without httpx/openai installed."""
    stubs = [
        "httpx",
        "openai",
        "anthropic",
        "PIL",
        "PIL.Image",
        "aiohttp",
        "elevenlabs",
        "faster_whisper",
    ]
    for name in stubs:
        if name in sys.modules:
            continue
        mod = types.ModuleType(name)
        # common attrs
        if name == "httpx":
            class _C:
                def __init__(self, *a, **k):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def get(self, *a, **k):
                    raise RuntimeError("stub")

                def post(self, *a, **k):
                    raise RuntimeError("stub")

            mod.Client = _C
            mod.AsyncClient = _C
            mod.HTTPError = Exception
            mod.TimeoutException = Exception
        if name == "openai":
            class _O:
                def __init__(self, *a, **k):
                    pass

            mod.OpenAI = _O
            mod.AsyncOpenAI = _O
        sys.modules[name] = mod
        if "." in name:
            parent = name.rsplit(".", 1)[0]
            if parent not in sys.modules:
                sys.modules[parent] = types.ModuleType(parent)


def _patch_attr(mod: Any, name: str, route_id: str) -> bool:
    if not hasattr(mod, name):
        return False
    obj = getattr(mod, name)
    if getattr(obj, "__omnis_wing_disabled__", False):
        return True
    if not callable(obj):
        return False
    setattr(mod, name, _refuse(route_id))
    return True


def install_side_door_guards() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _stub_missing_deps()

    patches = [
        (
            "tools.vision_tools",
            ["_handle_vision_analyze", "vision_analyze_tool", "_vision_analyze_native"],
            "tools.vision_tools",
        ),
        (
            "tools.image_generation_tool",
            ["_handle_image_generate"],
            "tools.image_generation_tool",
        ),
        ("tools.tts_tool", ["text_to_speech_tool"], "tools.tts_tool"),
        (
            "tools.transcription_tools",
            ["transcribe_audio", "_transcribe_local", "_transcribe_command_stt"],
            "tools.transcription_tools",
        ),
        (
            "tools.mixture_of_agents_tool",
            ["mixture_of_agents_tool"],
            "tools.mixture_of_agents_tool",
        ),
        ("mini_swe_runner", ["main"], "mini_swe_runner"),
        ("trajectory_compressor", ["main"], "trajectory_compressor"),
    ]

    for mod_name, names, route in patches:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            _INSTALL_ERRORS.append(f"{mod_name}:import:{type(exc).__name__}:{exc}")
            continue
        hit = False
        for n in names:
            if _patch_attr(mod, n, route):
                hit = True
        # Also patch registry handler if present
        reg = getattr(mod, "registry", None)
        if reg is not None and hasattr(reg, "_tools"):
            try:
                tools_map = getattr(reg, "_tools", {}) or {}
                for tname, tdef in list(tools_map.items()):
                    handler = getattr(tdef, "handler", None)
                    if handler is not None:
                        setattr(tdef, "handler", _refuse(route))
                        hit = True
            except Exception:
                pass
        if not hit:
            _INSTALL_ERRORS.append(f"{mod_name}:no_handler_matched:{names}")

    try:
        aux = importlib.import_module("agent.auxiliary_client")
        for attr in list(dir(aux)):
            if attr.startswith("_"):
                continue
            obj = getattr(aux, attr, None)
            if not callable(obj):
                continue
            low = attr.lower()
            if any(
                k in low
                for k in (
                    "complete",
                    "chat",
                    "call_llm",
                    "run_aux",
                    "auxiliary",
                    "get_client",
                    "resolve_client",
                )
            ):
                if not getattr(obj, "__omnis_wing_disabled__", False):
                    setattr(aux, attr, _refuse("agent.auxiliary_client.chat_completions"))
    except Exception as exc:
        _INSTALL_ERRORS.append(f"auxiliary:{type(exc).__name__}")

    _INSTALLED = True


def guards_installed() -> bool:
    return _INSTALLED


def install_errors() -> list[str]:
    return list(_INSTALL_ERRORS)


def handler_is_disabled(mod_name: str, attr: str) -> bool:
    try:
        _stub_missing_deps()
        mod = importlib.import_module(mod_name)
        obj = getattr(mod, attr, None)
        return bool(getattr(obj, "__omnis_wing_disabled__", False))
    except Exception:
        return False
