"""Fail-closed AI side-door arming for OMNIS WING.

Deny is bound at the real registration/dispatch boundary (tools.registry)
and reinforced by post-import handler replacement. Installation never
reports complete while a declared DISABLED route is unresolved.
Primary WING joins call ensure_side_doors_armed() without swallowing.
"""

from __future__ import annotations

import builtins
import importlib
import json
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from omnis_wing.completion.product_disable import WingRouteDisabled, load_manifest

_REASON = (
    "AI side-door disabled in OMNIS WING completion candidate; "
    "use primary governed agent path only"
)

# Tool names blocked at ToolRegistry.register / .dispatch
# (covers late import of tool modules without prior patch success)
DISABLED_TOOL_NAMES: Dict[str, str] = {
    "vision_analyze": "tools.vision_tools",
    "video_analyze": "tools.vision_tools",
    "image_generate": "tools.image_generation_tool",
    "text_to_speech": "tools.tts_tool",
    "mixture_of_agents": "tools.mixture_of_agents_tool",
}

# Modules whose callables must refuse if the module ever loads
MODULE_HANDLER_TARGETS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "tools.vision_tools": ("tools.vision_tools", ("_handle_vision_analyze", "vision_analyze_tool", "_vision_analyze_native")),
    "tools.image_generation_tool": ("tools.image_generation_tool", ("_handle_image_generate",)),
    "tools.tts_tool": ("tools.tts_tool", ("text_to_speech_tool",)),
    "tools.transcription_tools": (
        "tools.transcription_tools",
        ("transcribe_audio", "_transcribe_local", "_transcribe_command_stt"),
    ),
    "tools.mixture_of_agents_tool": ("tools.mixture_of_agents_tool", ("mixture_of_agents_tool",)),
    "mini_swe_runner": ("mini_swe_runner", ("main",)),
    "trajectory_compressor": ("trajectory_compressor", ("main",)),
}

# Manifest route_id → arming strategy
# "registry" = covered by DISABLED_TOOL_NAMES + registry wrap
# "module" = covered by MODULE_HANDLER_TARGETS + import hook
# "aux" = auxiliary_client callable wrap + import hook
ROUTE_ARMING: Dict[str, str] = {
    "tools.vision_tools": "registry+module",
    "tools.image_generation_tool": "registry+module",
    "tools.tts_tool": "registry+module",
    "tools.mixture_of_agents_tool": "registry+module",
    "tools.transcription_tools": "module",
    "agent.auxiliary_client.chat_completions": "aux",
    "mini_swe_runner": "module",
    "trajectory_compressor": "module",
    "hermes_cli.goals_kanban_profile": "module_optional",
    "plugins.image_gen.openai": "module_optional",
    "plugins.image_gen.openai-codex": "module_optional",
    "plugins.video_gen": "module_optional",
    # Messaging is not model AI egress — named disabled, no AI handler arming required
    "gateway.platform_messaging": "named_non_ai",
}


class SideDoorArmingError(RuntimeError):
    """Declared DISABLED route could not be armed — fail closed."""

    def __init__(self, unresolved: List[str], detail: str = ""):
        self.unresolved = list(unresolved)
        msg = f"OMNIS_WING_SIDE_DOOR_ARMING_FAILED:unresolved={unresolved}"
        if detail:
            msg = f"{msg}:{detail}"
        super().__init__(msg)


@dataclass
class ArmingState:
    complete: bool = False
    registry_wrapped: bool = False
    import_hook_installed: bool = False
    routes: Dict[str, str] = field(default_factory=dict)  # route_id -> ARMED|UNRESOLVED|NAMED_OK
    errors: List[str] = field(default_factory=list)
    patched_modules: Set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "complete": self.complete,
            "registry_wrapped": self.registry_wrapped,
            "import_hook_installed": self.import_hook_installed,
            "routes": dict(self.routes),
            "errors": list(self.errors),
            "patched_modules": sorted(self.patched_modules),
        }


_STATE = ArmingState()
_ORIG_IMPORT = None
_TEST_FORCE_UNRESOLVED: Optional[str] = None  # can-fail injection


def _refuse(route_id: str) -> Callable[..., Any]:
    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise WingRouteDisabled(route_id, _REASON)

    _fn.__omnis_wing_disabled__ = True  # type: ignore[attr-defined]
    _fn.__omnis_wing_route_id__ = route_id  # type: ignore[attr-defined]
    return _fn


def _declared_disabled_routes() -> List[str]:
    man = load_manifest()
    out = []
    for r in man["routes"]:
        if r.get("state") == "DISABLED" and r.get("broker_join") == "DISABLED":
            out.append(r["route_id"])
    return out


def _wrap_registry() -> None:
    """Bind deny at ToolRegistry.register + dispatch — no tool module import required."""
    from tools.registry import registry

    if getattr(registry.register, "__omnis_wing_wrapped__", False):
        _STATE.registry_wrapped = True
        return

    orig_register = registry.register
    orig_dispatch = registry.dispatch

    def register_wrapped(*args: Any, **kwargs: Any):
        # Support positional and keyword forms used by tool modules.
        name = kwargs.get("name")
        handler = kwargs.get("handler")
        if name is None and len(args) >= 1:
            name = args[0]
        if handler is None:
            # positional: name, toolset, schema, handler, ...
            if len(args) >= 4:
                handler = args[3]
        if name in DISABLED_TOOL_NAMES:
            route = DISABLED_TOOL_NAMES[name]
            handler = _refuse(route)
            kwargs = dict(kwargs)
            kwargs["handler"] = handler
            if len(args) >= 4:
                args = list(args)
                args[3] = handler
                args = tuple(args)
            elif "handler" not in kwargs:
                kwargs["handler"] = handler
        return orig_register(*args, **kwargs)

    def dispatch_wrapped(name: str, args: dict, **kwargs: Any):
        if name in DISABLED_TOOL_NAMES:
            raise WingRouteDisabled(DISABLED_TOOL_NAMES[name], _REASON)
        return orig_dispatch(name, args, **kwargs)

    register_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    dispatch_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    registry.register = register_wrapped  # type: ignore[assignment]
    registry.dispatch = dispatch_wrapped  # type: ignore[assignment]

    # If tools already registered before wrap, replace handlers in place
    tools_map = getattr(registry, "_tools", {}) or {}
    for tname, entry in list(tools_map.items()):
        if tname in DISABLED_TOOL_NAMES:
            entry.handler = _refuse(DISABLED_TOOL_NAMES[tname])

    _STATE.registry_wrapped = True


def _patch_module_handlers(mod_name: str) -> bool:
    if mod_name not in MODULE_HANDLER_TARGETS:
        return False
    route_id, names = MODULE_HANDLER_TARGETS[mod_name]
    if mod_name not in sys.modules:
        return False
    mod = sys.modules[mod_name]
    hit = False
    for n in names:
        if not hasattr(mod, n):
            continue
        obj = getattr(mod, n)
        if getattr(obj, "__omnis_wing_disabled__", False):
            hit = True
            continue
        if callable(obj):
            setattr(mod, n, _refuse(route_id))
            hit = True
    if hit:
        _STATE.patched_modules.add(mod_name)
    return hit


def _patch_auxiliary(mod: Any) -> bool:
    hit = False
    for attr in list(dir(mod)):
        if attr.startswith("_"):
            continue
        obj = getattr(mod, attr, None)
        if not callable(obj):
            continue
        if getattr(obj, "__omnis_wing_disabled__", False):
            hit = True
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
            setattr(mod, attr, _refuse("agent.auxiliary_client.chat_completions"))
            hit = True
    if hit:
        _STATE.patched_modules.add("agent.auxiliary_client")
    return hit


def _install_import_hook() -> None:
    global _ORIG_IMPORT
    if _STATE.import_hook_installed and _ORIG_IMPORT is not None:
        return

    if _ORIG_IMPORT is None:
        _ORIG_IMPORT = builtins.__import__

    watch = set(MODULE_HANDLER_TARGETS.keys()) | {
        "agent.auxiliary_client",
        "hermes_cli.goals",
        "hermes_cli.kanban_decompose",
        "hermes_cli.kanban_specify",
        "hermes_cli.profile_describer",
    }

    def _wing_import(name, globals=None, locals=None, fromlist=(), level=0):
        mod = _ORIG_IMPORT(name, globals, locals, fromlist, level)
        # Only act on top-level watched modules
        root = name.split(".")[0]
        candidates = set()
        if name in watch:
            candidates.add(name)
        # fromlist imports may load submodules already in sys.modules
        for w in watch:
            if w in sys.modules:
                candidates.add(w)
        for w in candidates:
            if w == "agent.auxiliary_client" and w in sys.modules:
                _patch_auxiliary(sys.modules[w])
            elif w in MODULE_HANDLER_TARGETS:
                _patch_module_handlers(w)
            elif w.startswith("hermes_cli.") and w in sys.modules:
                _patch_hermes_cli_mod(sys.modules[w], "hermes_cli.goals_kanban_profile")
        return mod

    builtins.__import__ = _wing_import
    _STATE.import_hook_installed = True


def _patch_hermes_cli_mod(mod: Any, route: str) -> None:
    for attr in list(dir(mod)):
        obj = getattr(mod, attr, None)
        if not callable(obj):
            continue
        if getattr(obj, "__omnis_wing_disabled__", False):
            continue
        if any(k in attr.lower() for k in ("llm", "complete", "chat", "describe", "generate", "call_model")):
            setattr(mod, attr, _refuse(route))


def _evaluate_routes() -> None:
    declared = _declared_disabled_routes()
    routes: Dict[str, str] = {}
    errors: List[str] = list(_STATE.errors)

    for route_id in declared:
        if _TEST_FORCE_UNRESOLVED and route_id == _TEST_FORCE_UNRESOLVED:
            routes[route_id] = "UNRESOLVED"
            errors.append(f"forced_unresolved:{route_id}")
            continue

        strategy = ROUTE_ARMING.get(route_id, "unknown")
        if strategy == "named_non_ai":
            routes[route_id] = "NAMED_OK"
            continue
        if strategy == "module_optional":
            # Armed if import hook live (will refuse handlers when module loads)
            # or module already patched
            if _STATE.import_hook_installed:
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"no_import_hook:{route_id}")
            continue
        if strategy == "registry+module":
            if _STATE.registry_wrapped and _STATE.import_hook_installed:
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"registry_or_hook_missing:{route_id}")
            continue
        if strategy == "module":
            if _STATE.import_hook_installed or any(
                m in _STATE.patched_modules
                for m, (rid, _) in MODULE_HANDLER_TARGETS.items()
                if rid == route_id
            ):
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"module_unarmed:{route_id}")
            continue
        if strategy == "aux":
            if _STATE.import_hook_installed or "agent.auxiliary_client" in _STATE.patched_modules:
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"aux_unarmed:{route_id}")
            continue
        routes[route_id] = "UNRESOLVED"
        errors.append(f"unknown_strategy:{route_id}:{strategy}")

    _STATE.routes = routes
    _STATE.errors = errors
    unresolved = [r for r, s in routes.items() if s == "UNRESOLVED"]
    _STATE.complete = len(unresolved) == 0 and _STATE.registry_wrapped and _STATE.import_hook_installed


def arm_side_doors(*, force_rearm: bool = False) -> ArmingState:
    """Arm all declared DISABLED routes. Never marks complete if any unresolved."""
    global _STATE
    if _STATE.complete and not force_rearm and _TEST_FORCE_UNRESOLVED is None:
        return _STATE

    if force_rearm:
        # Keep import hook; re-evaluate registry wrap + routes
        pass

    try:
        _wrap_registry()
    except Exception as exc:
        _STATE.errors.append(f"registry_wrap:{type(exc).__name__}:{exc}")
        _STATE.registry_wrapped = False

    try:
        _install_import_hook()
    except Exception as exc:
        _STATE.errors.append(f"import_hook:{type(exc).__name__}:{exc}")
        _STATE.import_hook_installed = False

    # Best-effort immediate patch of already-loaded modules (no stubs required)
    for mod_name in list(MODULE_HANDLER_TARGETS.keys()):
        if mod_name in sys.modules:
            try:
                _patch_module_handlers(mod_name)
            except Exception as exc:
                _STATE.errors.append(f"patch:{mod_name}:{type(exc).__name__}")
    if "agent.auxiliary_client" in sys.modules:
        try:
            _patch_auxiliary(sys.modules["agent.auxiliary_client"])
        except Exception as exc:
            _STATE.errors.append(f"patch:aux:{type(exc).__name__}")

    _evaluate_routes()
    return _STATE


def install_side_door_guards() -> None:
    """Back-compat name. Prefer ensure_side_doors_armed() at product boundaries."""
    arm_side_doors()


def ensure_side_doors_armed() -> ArmingState:
    """Fail closed: raise if any declared DISABLED route is unresolved."""
    st = arm_side_doors()
    if not st.complete:
        unresolved = [r for r, s in st.routes.items() if s == "UNRESOLVED"]
        raise SideDoorArmingError(unresolved, detail=";".join(st.errors[:8]))
    return st


def guards_installed() -> bool:
    return _STATE.complete


def install_errors() -> list[str]:
    return list(_STATE.errors)


def get_arming_state() -> dict:
    return _STATE.as_dict()


def handler_is_disabled(mod_name: str, attr: str) -> bool:
    try:
        if mod_name not in sys.modules:
            return False
        obj = getattr(sys.modules[mod_name], attr, None)
        return bool(getattr(obj, "__omnis_wing_disabled__", False))
    except Exception:
        return False


def force_unresolved_for_test(route_id: Optional[str]) -> None:
    """Test-only: force a declared route UNRESOLVED and clear complete."""
    global _TEST_FORCE_UNRESOLVED, _STATE
    _TEST_FORCE_UNRESOLVED = route_id
    _STATE.complete = False
    _evaluate_routes()


def reset_arming_state_for_test() -> None:
    """Test-only hard reset (does not unhook import if already replaced)."""
    global _STATE, _TEST_FORCE_UNRESOLVED
    _TEST_FORCE_UNRESOLVED = None
    complete = _STATE.registry_wrapped
    hook = _STATE.import_hook_installed
    _STATE = ArmingState(
        registry_wrapped=complete,
        import_hook_installed=hook,
    )
    if complete or hook:
        _evaluate_routes()
