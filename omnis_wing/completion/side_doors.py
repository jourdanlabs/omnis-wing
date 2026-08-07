"""Fail-closed AI side-door arming for OMNIS WING.

Coverage is a property of concrete entrypoint/handler boundaries — never of
"a builtins import hook exists."

Arming strategy:
  1. Wrap tools.registry.register / .dispatch for named registry tools.
  2. Wrap importlib.import_module AND builtins.__import__ AND importlib.reload
     so late dynamic loads (the product's real path) still get handler deny.
  3. Eagerly resolve every declared module-backed DISABLED route: patch real
     handlers if the module loads, otherwise install a deny-stub module with
     the real entrypoint names. Route is ARMED only when callables refuse.
  4. complete=False / SideDoorArmingError if any declared DISABLED route
     lacks a refuse boundary.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from omnis_wing.completion.product_disable import WingRouteDisabled, load_manifest

_REASON = (
    "AI side-door disabled in OMNIS WING completion candidate; "
    "use primary governed agent path only"
)

DISABLED_TOOL_NAMES: Dict[str, str] = {
    "vision_analyze": "tools.vision_tools",
    "video_analyze": "tools.vision_tools",
    "image_generate": "tools.image_generation_tool",
    "text_to_speech": "tools.tts_tool",
    "mixture_of_agents": "tools.mixture_of_agents_tool",
}

# module_name -> (route_id, entrypoint names that must refuse)
MODULE_HANDLER_TARGETS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "tools.vision_tools": (
        "tools.vision_tools",
        ("_handle_vision_analyze", "vision_analyze_tool", "_vision_analyze_native"),
    ),
    "tools.image_generation_tool": (
        "tools.image_generation_tool",
        ("_handle_image_generate",),
    ),
    "tools.tts_tool": ("tools.tts_tool", ("text_to_speech_tool",)),
    "tools.transcription_tools": (
        "tools.transcription_tools",
        ("transcribe_audio", "_transcribe_local", "_transcribe_command_stt"),
    ),
    "tools.mixture_of_agents_tool": (
        "tools.mixture_of_agents_tool",
        ("mixture_of_agents_tool",),
    ),
    "mini_swe_runner": ("mini_swe_runner", ("main",)),
    "trajectory_compressor": ("trajectory_compressor", ("main",)),
    "agent.auxiliary_client": (
        "agent.auxiliary_client.chat_completions",
        (),  # special: name-pattern patch
    ),
    "hermes_cli.goals": ("hermes_cli.goals_kanban_profile", ()),
    "hermes_cli.kanban_decompose": ("hermes_cli.goals_kanban_profile", ()),
    "hermes_cli.kanban_specify": ("hermes_cli.goals_kanban_profile", ()),
    "hermes_cli.profile_describer": ("hermes_cli.goals_kanban_profile", ()),
}

# route_id -> modules that implement it
ROUTE_MODULES: Dict[str, Tuple[str, ...]] = {
    "tools.vision_tools": ("tools.vision_tools",),
    "tools.image_generation_tool": ("tools.image_generation_tool",),
    "tools.tts_tool": ("tools.tts_tool",),
    "tools.transcription_tools": ("tools.transcription_tools",),
    "tools.mixture_of_agents_tool": ("tools.mixture_of_agents_tool",),
    "mini_swe_runner": ("mini_swe_runner",),
    "trajectory_compressor": ("trajectory_compressor",),
    "agent.auxiliary_client.chat_completions": ("agent.auxiliary_client",),
    "hermes_cli.goals_kanban_profile": (
        "hermes_cli.goals",
        "hermes_cli.kanban_decompose",
        "hermes_cli.kanban_specify",
        "hermes_cli.profile_describer",
    ),
    "plugins.image_gen.openai": ("plugins.image_gen.openai",),
    "plugins.image_gen.openai-codex": ("plugins.image_gen.openai_codex", "plugins.image_gen.openai-codex"),
    "plugins.video_gen": (
        "plugins.video_gen",
        "plugins.video_gen.fal",
        "plugins.video_gen.xai",
    ),
    "gateway.platform_messaging": (),  # named non-AI
}

# Plugin-ish modules get deny stubs with generic entry names if absent
PLUGIN_ENTRY_NAMES = ("generate", "create", "run", "handle", "main", "generate_image", "generate_video")


class SideDoorArmingError(RuntimeError):
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
    importlib_wrapped: bool = False
    routes: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    patched_modules: Set[str] = field(default_factory=set)
    stubbed_modules: Set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "complete": self.complete,
            "registry_wrapped": self.registry_wrapped,
            "importlib_wrapped": self.importlib_wrapped,
            "routes": dict(self.routes),
            "errors": list(self.errors),
            "patched_modules": sorted(self.patched_modules),
            "stubbed_modules": sorted(self.stubbed_modules),
        }


_STATE = ArmingState()
_ORIG_IMPORT = None
_ORIG_IMPORT_MODULE = None
_ORIG_RELOAD = None
_TEST_FORCE_UNRESOLVED: Optional[str] = None
_TEST_SKIP_STUB_FOR: Optional[str] = None
_WRAPPING = False  # re-entrancy guard


def _refuse(route_id: str) -> Callable[..., Any]:
    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise WingRouteDisabled(route_id, _REASON)

    _fn.__omnis_wing_disabled__ = True  # type: ignore[attr-defined]
    _fn.__omnis_wing_route_id__ = route_id  # type: ignore[attr-defined]
    return _fn


def _declared_disabled_routes() -> List[str]:
    man = load_manifest()
    return [
        r["route_id"]
        for r in man["routes"]
        if r.get("state") == "DISABLED" and r.get("broker_join") == "DISABLED"
    ]


def _is_disabled_callable(obj: Any) -> bool:
    return bool(getattr(obj, "__omnis_wing_disabled__", False))


def _wrap_registry() -> None:
    from tools.registry import registry

    if getattr(registry.register, "__omnis_wing_wrapped__", False):
        _STATE.registry_wrapped = True
        return

    orig_register = registry.register
    orig_dispatch = registry.dispatch

    def register_wrapped(*args: Any, **kwargs: Any):
        name = kwargs.get("name")
        handler = kwargs.get("handler")
        if name is None and len(args) >= 1:
            name = args[0]
        if handler is None and len(args) >= 4:
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
        return orig_register(*args, **kwargs)

    def dispatch_wrapped(name: str, args: dict, **kwargs: Any):
        if name in DISABLED_TOOL_NAMES:
            raise WingRouteDisabled(DISABLED_TOOL_NAMES[name], _REASON)
        return orig_dispatch(name, args, **kwargs)

    register_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    dispatch_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    registry.register = register_wrapped  # type: ignore[assignment]
    registry.dispatch = dispatch_wrapped  # type: ignore[assignment]

    for tname, entry in list((getattr(registry, "_tools", {}) or {}).items()):
        if tname in DISABLED_TOOL_NAMES:
            entry.handler = _refuse(DISABLED_TOOL_NAMES[tname])

    _STATE.registry_wrapped = True


def _patch_pattern_callables(mod: Any, route_id: str, keys: Tuple[str, ...]) -> int:
    n = 0
    for attr in list(dir(mod)):
        if attr.startswith("_") and attr not in keys:
            # still allow explicit underscore entry names from keys
            if attr not in keys:
                continue
        obj = getattr(mod, attr, None)
        if not callable(obj):
            continue
        if _is_disabled_callable(obj):
            n += 1
            continue
        low = attr.lower()
        if attr in keys or any(k in low for k in keys):
            setattr(mod, attr, _refuse(route_id))
            n += 1
    return n


def _patch_module_handlers(mod_name: str) -> bool:
    if mod_name not in sys.modules:
        return False
    mod = sys.modules[mod_name]
    if mod_name not in MODULE_HANDLER_TARGETS and not mod_name.startswith("plugins."):
        # plugin / hermes handled below via ROUTE_MODULES
        pass

    if mod_name in MODULE_HANDLER_TARGETS:
        route_id, names = MODULE_HANDLER_TARGETS[mod_name]
        if mod_name == "agent.auxiliary_client":
            hit = _patch_pattern_callables(
                mod,
                route_id,
                (
                    "complete",
                    "chat",
                    "call_llm",
                    "run_aux",
                    "auxiliary",
                    "get_client",
                    "resolve_client",
                ),
            )
            if hit:
                _STATE.patched_modules.add(mod_name)
            return hit > 0
        if mod_name.startswith("hermes_cli."):
            hit = _patch_pattern_callables(
                mod, route_id, ("llm", "complete", "chat", "describe", "generate", "call_model")
            )
            if hit:
                _STATE.patched_modules.add(mod_name)
            return hit > 0
        hit = False
        for n in names:
            if not hasattr(mod, n):
                continue
            obj = getattr(mod, n)
            if _is_disabled_callable(obj):
                hit = True
                continue
            if callable(obj):
                setattr(mod, n, _refuse(route_id))
                hit = True
        if hit:
            _STATE.patched_modules.add(mod_name)
        return hit

    # plugins
    if mod_name.startswith("plugins."):
        # map to route
        route_id = "plugins.video_gen"
        if "image_gen" in mod_name and "codex" in mod_name:
            route_id = "plugins.image_gen.openai-codex"
        elif "image_gen" in mod_name:
            route_id = "plugins.image_gen.openai"
        hit = _patch_pattern_callables(mod, route_id, PLUGIN_ENTRY_NAMES)
        if hit:
            _STATE.patched_modules.add(mod_name)
        return hit > 0

    return False


def _install_deny_stub(mod_name: str, route_id: str, entry_names: Tuple[str, ...]) -> None:
    """Install refuse-only module so importlib returns a disabled surface."""
    if _TEST_SKIP_STUB_FOR and (
        _TEST_SKIP_STUB_FOR == mod_name or _TEST_SKIP_STUB_FOR == route_id
    ):
        return
    mod = types.ModuleType(mod_name)
    mod.__omnis_wing_deny_stub__ = True  # type: ignore[attr-defined]
    mod.__omnis_wing_route_id__ = route_id  # type: ignore[attr-defined]
    names = entry_names or PLUGIN_ENTRY_NAMES
    for n in names:
        setattr(mod, n, _refuse(route_id))
    # minimal package path support
    if "." in mod_name:
        parts = mod_name.split(".")
        for i in range(1, len(parts)):
            pkg = ".".join(parts[:i])
            if pkg not in sys.modules:
                pkg_mod = types.ModuleType(pkg)
                pkg_mod.__path__ = []  # type: ignore[attr-defined]
                pkg_mod.__package__ = pkg
                sys.modules[pkg] = pkg_mod
            else:
                pkg_mod = sys.modules[pkg]
            # link child
            child_name = parts[i]
            full_child = ".".join(parts[: i + 1])
            if i == len(parts) - 1:
                setattr(pkg_mod, child_name, mod)
            elif not hasattr(pkg_mod, child_name):
                setattr(pkg_mod, child_name, sys.modules.get(full_child))
    sys.modules[mod_name] = mod
    _STATE.stubbed_modules.add(mod_name)


def _module_entrypoints_disabled(mod_name: str) -> bool:
    if mod_name not in sys.modules:
        return False
    mod = sys.modules[mod_name]
    if getattr(mod, "__omnis_wing_deny_stub__", False):
        return True
    if mod_name in MODULE_HANDLER_TARGETS:
        route_id, names = MODULE_HANDLER_TARGETS[mod_name]
        if not names:
            # pattern-based: at least one disabled callable or stub
            for attr in dir(mod):
                obj = getattr(mod, attr, None)
                if callable(obj) and _is_disabled_callable(obj):
                    return True
            return False
        ok = True
        found = 0
        for n in names:
            if not hasattr(mod, n):
                continue
            found += 1
            if not _is_disabled_callable(getattr(mod, n)):
                ok = False
        return ok and found > 0
    # plugins
    if mod_name.startswith("plugins."):
        for attr in dir(mod):
            obj = getattr(mod, attr, None)
            if callable(obj) and _is_disabled_callable(obj):
                return True
        return getattr(mod, "__omnis_wing_deny_stub__", False)
    return False


def _after_module_present(mod_name: str) -> None:
    """Called whenever a watched module is in sys.modules after a load."""
    if mod_name in MODULE_HANDLER_TARGETS or mod_name.startswith("plugins."):
        if getattr(sys.modules.get(mod_name), "__omnis_wing_deny_stub__", False):
            return
        _patch_module_handlers(mod_name)


def _wrap_importlib() -> None:
    """Wrap importlib.import_module + builtins.__import__ + reload (product uses importlib)."""
    global _ORIG_IMPORT, _ORIG_IMPORT_MODULE, _ORIG_RELOAD, _WRAPPING

    if _STATE.importlib_wrapped and _ORIG_IMPORT_MODULE is not None:
        return

    if _ORIG_IMPORT is None:
        _ORIG_IMPORT = builtins.__import__
    if _ORIG_IMPORT_MODULE is None:
        _ORIG_IMPORT_MODULE = importlib.import_module
    if _ORIG_RELOAD is None:
        _ORIG_RELOAD = importlib.reload

    watch_exact = set(MODULE_HANDLER_TARGETS.keys())
    for mods in ROUTE_MODULES.values():
        watch_exact.update(mods)

    def _maybe_patch_from_sys():
        for w in list(watch_exact):
            if w and w in sys.modules:
                _after_module_present(w)

    def import_module_wrapped(name: str, package: Any = None):
        global _WRAPPING
        target = name
        # If already a deny stub, return it (do not re-exec real file after del+import
        # unless stub missing).
        if name in sys.modules and getattr(sys.modules[name], "__omnis_wing_deny_stub__", False):
            return sys.modules[name]
        try:
            mod = _ORIG_IMPORT_MODULE(name, package)
        except Exception as exc:
            # Watched disabled modules: fail closed to deny stub, never leave load hole
            if name in watch_exact or any(name == w or name.startswith(w + ".") for w in watch_exact):
                route_id = name
                entry: Tuple[str, ...] = PLUGIN_ENTRY_NAMES
                if name in MODULE_HANDLER_TARGETS:
                    route_id, entry = MODULE_HANDLER_TARGETS[name]
                elif name.startswith("plugins.image_gen") and "codex" in name:
                    route_id = "plugins.image_gen.openai-codex"
                elif name.startswith("plugins.image_gen"):
                    route_id = "plugins.image_gen.openai"
                elif name.startswith("plugins.video_gen"):
                    route_id = "plugins.video_gen"
                _STATE.errors.append(f"importlib_fail_stub:{name}:{type(exc).__name__}")
                _install_deny_stub(name, route_id, entry or PLUGIN_ENTRY_NAMES)
                return sys.modules[name]
            raise
        if _WRAPPING:
            return mod
        _WRAPPING = True
        try:
            abs_name = getattr(mod, "__name__", name)
            if abs_name in watch_exact or name in watch_exact:
                _after_module_present(abs_name if abs_name in watch_exact else name)
                # If patch could not disable entrypoints, replace with deny stub
                check = abs_name if abs_name in watch_exact else name
                if check in MODULE_HANDLER_TARGETS or check.startswith("plugins."):
                    if not _module_entrypoints_disabled(check):
                        route_id = MODULE_HANDLER_TARGETS.get(check, (check, ()))[0]
                        entry = MODULE_HANDLER_TARGETS.get(check, (check, PLUGIN_ENTRY_NAMES))[1]
                        _install_deny_stub(check, route_id, entry or PLUGIN_ENTRY_NAMES)
                        return sys.modules[check]
            _maybe_patch_from_sys()
        finally:
            _WRAPPING = False
        return mod

    def builtin_import_wrapped(name, globals=None, locals=None, fromlist=(), level=0):
        global _WRAPPING
        mod = _ORIG_IMPORT(name, globals, locals, fromlist, level)
        if _WRAPPING:
            return mod
        _WRAPPING = True
        try:
            abs_name = name
            if abs_name in watch_exact:
                if abs_name in sys.modules:
                    _after_module_present(abs_name)
            _maybe_patch_from_sys()
        finally:
            _WRAPPING = False
        return mod

    def reload_wrapped(module):
        global _WRAPPING
        mod = _ORIG_RELOAD(module)
        _WRAPPING = True
        try:
            abs_name = getattr(mod, "__name__", "")
            if abs_name in watch_exact:
                _after_module_present(abs_name)
        finally:
            _WRAPPING = False
        return mod

    import_module_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    builtin_import_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]
    reload_wrapped.__omnis_wing_wrapped__ = True  # type: ignore[attr-defined]

    importlib.import_module = import_module_wrapped  # type: ignore[assignment]
    builtins.__import__ = builtin_import_wrapped
    importlib.reload = reload_wrapped  # type: ignore[assignment]
    _STATE.importlib_wrapped = True


def _eager_resolve_module(mod_name: str, route_id: str) -> bool:
    """Load-or-stub a module and ensure entrypoints refuse. Returns True if armed."""
    if _TEST_SKIP_STUB_FOR in (mod_name, route_id):
        # leave unarmed for can-fail
        if mod_name in sys.modules:
            # strip deny if we must leave unresolved - don't patch
            return _module_entrypoints_disabled(mod_name)
        return False

    entry_names: Tuple[str, ...] = ()
    if mod_name in MODULE_HANDLER_TARGETS:
        entry_names = MODULE_HANDLER_TARGETS[mod_name][1]

    # Already present
    if mod_name in sys.modules:
        if getattr(sys.modules[mod_name], "__omnis_wing_deny_stub__", False):
            return True
        _patch_module_handlers(mod_name)
        if _module_entrypoints_disabled(mod_name):
            return True
        # present but couldn't patch entrypoints — force stub overwrite only if no real attrs needed
        # Overwrite with deny stub to fail closed rather than leave live callables
        _install_deny_stub(mod_name, route_id, entry_names or PLUGIN_ENTRY_NAMES)
        return mod_name in sys.modules and _module_entrypoints_disabled(mod_name)

    # Try real import through wrapped importlib (may fail on missing deps)
    try:
        importlib.import_module(mod_name)
        _patch_module_handlers(mod_name)
        if _module_entrypoints_disabled(mod_name):
            return True
        # Imported but handlers not found/patchable → stub over
        _install_deny_stub(mod_name, route_id, entry_names or PLUGIN_ENTRY_NAMES)
        return _module_entrypoints_disabled(mod_name)
    except Exception as exc:
        _STATE.errors.append(f"import:{mod_name}:{type(exc).__name__}")
        _install_deny_stub(mod_name, route_id, entry_names or PLUGIN_ENTRY_NAMES)
        return _module_entrypoints_disabled(mod_name)


def _evaluate_and_eager_arm() -> None:
    declared = _declared_disabled_routes()
    routes: Dict[str, str] = {}
    errors = list(_STATE.errors)

    for route_id in declared:
        if _TEST_FORCE_UNRESOLVED and route_id == _TEST_FORCE_UNRESOLVED:
            routes[route_id] = "UNRESOLVED"
            errors.append(f"forced_unresolved:{route_id}")
            continue

        mods = ROUTE_MODULES.get(route_id)
        if mods is None:
            routes[route_id] = "UNRESOLVED"
            errors.append(f"no_route_mapping:{route_id}")
            continue
        if route_id == "gateway.platform_messaging":
            routes[route_id] = "NAMED_OK"
            continue

        # Registry-backed AI tools still require registry wrap + module surface
        registry_needed = route_id in {
            "tools.vision_tools",
            "tools.image_generation_tool",
            "tools.tts_tool",
            "tools.mixture_of_agents_tool",
        }
        if registry_needed and not _STATE.registry_wrapped:
            routes[route_id] = "UNRESOLVED"
            errors.append(f"registry_unwrapped:{route_id}")
            continue

        if not mods:
            routes[route_id] = "UNRESOLVED"
            errors.append(f"empty_modules:{route_id}")
            continue

        armed_any = False
        for mod_name in mods:
            if not mod_name:
                continue
            if _eager_resolve_module(mod_name, route_id):
                armed_any = True
        # hermes multi-module: ARMED if at least one module surface disabled OR all missing stubbed
        if route_id == "hermes_cli.goals_kanban_profile":
            # all listed modules must be resolved (stub or patch)
            ok = all(
                (m in sys.modules and _module_entrypoints_disabled(m))
                or _eager_resolve_module(m, route_id)
                for m in mods
            )
            # re-check
            ok = all(m in sys.modules and _module_entrypoints_disabled(m) for m in mods)
            routes[route_id] = "ARMED" if ok else "UNRESOLVED"
            if not ok:
                errors.append(f"hermes_unarmed:{route_id}")
            continue

        if route_id.startswith("plugins."):
            # any one of the plugin module names armed is enough if others stubbed
            ok = False
            for m in mods:
                if _eager_resolve_module(m, route_id):
                    ok = True
            routes[route_id] = "ARMED" if ok else "UNRESOLVED"
            if not ok:
                errors.append(f"plugin_unarmed:{route_id}")
            continue

        if armed_any and all(
            (m not in sys.modules) or _module_entrypoints_disabled(m) for m in mods if m
        ):
            # primary module must be disabled
            primary = mods[0]
            if primary in sys.modules and _module_entrypoints_disabled(primary):
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"primary_live:{route_id}:{primary}")
        else:
            # try force primary
            primary = mods[0]
            if _eager_resolve_module(primary, route_id):
                routes[route_id] = "ARMED"
            else:
                routes[route_id] = "UNRESOLVED"
                errors.append(f"module_unarmed:{route_id}")

    _STATE.routes = routes
    _STATE.errors = errors
    unresolved = [r for r, s in routes.items() if s == "UNRESOLVED"]
    # NOTE: import hook presence alone is NOT enough for complete
    _STATE.complete = (
        len(unresolved) == 0
        and _STATE.registry_wrapped
        and _STATE.importlib_wrapped
    )


def arm_side_doors(*, force_rearm: bool = False) -> ArmingState:
    global _STATE
    if _STATE.complete and not force_rearm and _TEST_FORCE_UNRESOLVED is None and _TEST_SKIP_STUB_FOR is None:
        return _STATE

    try:
        _wrap_registry()
    except Exception as exc:
        _STATE.errors.append(f"registry_wrap:{type(exc).__name__}:{exc}")
        _STATE.registry_wrapped = False

    try:
        _wrap_importlib()
    except Exception as exc:
        _STATE.errors.append(f"importlib_wrap:{type(exc).__name__}:{exc}")
        _STATE.importlib_wrapped = False

    _evaluate_and_eager_arm()
    return _STATE


def install_side_door_guards() -> None:
    arm_side_doors()


def ensure_side_doors_armed() -> ArmingState:
    st = arm_side_doors()
    if not st.complete:
        unresolved = [r for r, s in st.routes.items() if s == "UNRESOLVED"]
        raise SideDoorArmingError(unresolved, detail=";".join(st.errors[:12]))
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
        return _is_disabled_callable(obj)
    except Exception:
        return False


def force_unresolved_for_test(route_id: Optional[str]) -> None:
    global _TEST_FORCE_UNRESOLVED, _STATE
    _TEST_FORCE_UNRESOLVED = route_id
    _STATE.complete = False
    _evaluate_and_eager_arm()


def skip_stub_for_test(mod_or_route: Optional[str]) -> None:
    """Test-only: prevent deny-stub install so route stays unarmed if unloadable."""
    global _TEST_SKIP_STUB_FOR, _STATE
    _TEST_SKIP_STUB_FOR = mod_or_route
    _STATE.complete = False


def reset_arming_state_for_test() -> None:
    global _STATE, _TEST_FORCE_UNRESOLVED, _TEST_SKIP_STUB_FOR
    _TEST_FORCE_UNRESOLVED = None
    _TEST_SKIP_STUB_FOR = None
    reg = _STATE.registry_wrapped
    imp = _STATE.importlib_wrapped
    _STATE = ArmingState(registry_wrapped=reg, importlib_wrapped=imp)
    if reg or imp:
        _evaluate_and_eager_arm()
