"""Static + runtime guards: TransportBroker is the sole real AI egress join.

Authority for governed provider dispatch is **stack ownership by
``TransportBroker.transmit_*`` methods** — not a public enterable scope, not a
caller-mintable thread-local depth token. Non-broker modules cannot forge that
frame; forging a deprecated scope no longer authorizes anything.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# Names agent/product modules must not import, call, getattr, or dynamically load.
BANNED_GOVERNED_NAMES = frozenset(
    {
        "governed_chat_completions_create",
        "governed_callable_transmit",
        "governed_streaming_create",
        "governed_image_transmit",
    }
)

# Capability tokens that must not appear as agent-owned authority (even if inert).
BANNED_SCOPE_NAMES = frozenset(
    {
        "broker_dispatch_scope",
        "require_broker_dispatch",
    }
)

BANNED_ALL_NAMES = BANNED_GOVERNED_NAMES | BANNED_SCOPE_NAMES

# Modules that may reference governed implementations (broker + impl bodies + guard).
ALLOWED_GOVERNED_MODULES = frozenset(
    {
        "omnis_wing.absolute.transport_broker",
        "omnis_wing.absolute.hermes_chat_join",
        "omnis_wing.absolute.universal_egress",
        "omnis_wing.absolute.image_join",
        "omnis_wing.absolute.broker_guard",
    }
)

# Paths (relative to repo root) that may contain governed names.
ALLOWED_PATH_PREFIXES = (
    "omnis_wing/absolute/transport_broker.py",
    "omnis_wing/absolute/hermes_chat_join.py",
    "omnis_wing/absolute/universal_egress.py",
    "omnis_wing/absolute/image_join.py",
    "omnis_wing/absolute/broker_guard.py",
    "tests/",  # tests may instrument / assert
    "omnis_wing/spec/",
    "omnis_wing/completion/route_manifest.json",
)

# Agent-side trees that must not import governed helpers or forge dispatch.
AGENT_SCAN_GLOBS = (
    "agent/**/*.py",
    "tools/**/*.py",
    "hermes_cli/**/*.py",
    "gateway/**/*.py",
    "plugins/**/*.py",
    "cron/**/*.py",
)

_BROKER_MODULE = "omnis_wing.absolute.transport_broker"
_BROKER_CLASS = "TransportBroker"
_TRANSMIT_METHODS = frozenset(
    {
        "transmit_chat_completions",
        "transmit_callable",
        "transmit_streaming",
        "transmit_image",
    }
)

_BANNED_MODULE_FRAGMENTS = (
    "hermes_chat_join",
    "universal_egress",
    "broker_guard",
    "image_join",
)

_NAME_RE = re.compile(
    r"\b(governed_chat_completions_create|governed_callable_transmit|"
    r"governed_streaming_create|governed_image_transmit|"
    r"broker_dispatch_scope|require_broker_dispatch)\b"
)

_DYNAMIC_IMPORT_FUNCS = frozenset(
    {
        "import_module",
        "__import__",
        "reload",
    }
)


class BrokerViolation(RuntimeError):
    """Raised when a non-broker path attempts provider ownership or direct governed call."""


def broker_context_depth() -> int:
    """Deprecated no-op residual. Depth is not authorization; always 0."""
    return 0


class broker_dispatch_scope:
    """Deprecated: public enterable scope is **not** a dispatch capability.

    Kept only so residual imports fail closed if misused as an authority token.
    Entering this scope does not authorize governed provider dispatch.
    Prefer stack-owned ``TransportBroker.transmit_*`` paths exclusively.
    """

    def __enter__(self) -> "broker_dispatch_scope":
        # Explicitly non-authorizing. Callers that only wrap this and expect
        # require_broker_dispatch to pass will get BrokerViolation.
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _frame_is_broker_transmit(frame) -> bool:
    """True iff *frame* is a real TransportBroker.transmit_* method body."""
    code = frame.f_code
    if code.co_name not in _TRANSMIT_METHODS:
        return False
    mod = frame.f_globals.get("__name__", "")
    if mod != _BROKER_MODULE:
        return False
    # Prefer live instance check — rejects fakes with matching function names.
    self_obj = frame.f_locals.get("self")
    if self_obj is not None:
        cls = type(self_obj)
        if (
            getattr(cls, "__name__", None) == _BROKER_CLASS
            and getattr(cls, "__module__", None) == _BROKER_MODULE
        ):
            return True
        return False
    # No self (unexpected for methods) — accept only qualified name on class.
    qual = getattr(code, "co_qualname", code.co_name)
    return qual.startswith(f"{_BROKER_CLASS}.")


def require_broker_dispatch(entry: str) -> None:
    """Runtime gate: governed transmit implementations are broker-only.

    Authorization is structural stack ownership by
    ``omnis_wing.absolute.transport_broker.TransportBroker.transmit_*``.
    A public scope or thread-local depth is **not** sufficient and is ignored.
    """
    frame = sys._getframe(1)
    while frame is not None:
        if _frame_is_broker_transmit(frame):
            return
        frame = frame.f_back
    raise BrokerViolation(f"direct_governed_call_forbidden:{entry}")


def _path_allowed(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    for pref in ALLOWED_PATH_PREFIXES:
        if rel == pref or rel.startswith(pref):
            return True
    return False


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _collect_string_constants(tree: ast.AST) -> List[str]:
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append(v.value)
    return out


def _can_assemble_banned(constants: Sequence[str], target: str) -> bool:
    """Whether any constant equals *target* or a short concat of constants forms it."""
    if not target:
        return False
    for c in constants:
        if c == target or target in c:
            return True
    # Pairwise / triple concat of short fragments (planted dynamic name assembly).
    frags = [c for c in constants if c and len(c) <= len(target) and c in target]
    if not frags:
        return False
    # DFS limited depth — enough for "governed_" + "chat_completions_create" style plants.
    limit = 6

    def dfs(built: str, depth: int) -> bool:
        if built == target:
            return True
        if depth >= limit or len(built) >= len(target):
            return False
        for f in frags:
            if target.startswith(built + f) and dfs(built + f, depth + 1):
                return True
        return False

    return dfs("", 0)


def _call_func_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def scan_source_for_governed_bypass(
    root: Path,
    *,
    extra_globs: Sequence[str] = (),
) -> List[Tuple[str, int, str]]:
    """Return list of (relpath, lineno, line) violations outside the broker waist."""
    hits: List[Tuple[str, int, str]] = []
    globs = list(AGENT_SCAN_GLOBS) + list(extra_globs)
    seen: set[Path] = set()
    for pattern in globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rp = path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(path)
            if _path_allowed(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if not _NAME_RE.search(line):
                    continue
                if "import" in line or "governed_" in line or "broker_dispatch" in line:
                    hits.append((rel, i, stripped[:200]))
    return hits


def scan_ast_agent_imports(root: Path) -> List[Tuple[str, int, str]]:
    """AST pass: agent trees must not import banned governed names (static)."""
    hits: List[Tuple[str, int, str]] = []
    for pattern in AGENT_SCAN_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if _path_allowed(rel):
                continue
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=rel)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if (
                        mod
                        in (
                            "omnis_wing.absolute.hermes_chat_join",
                            "omnis_wing.absolute.universal_egress",
                            "omnis_wing.absolute.broker_guard",
                        )
                        or mod.endswith(".hermes_chat_join")
                        or mod.endswith(".universal_egress")
                        or mod.endswith(".broker_guard")
                    ):
                        for alias in node.names:
                            if (
                                alias.name in BANNED_ALL_NAMES
                                or alias.name == "*"
                                or alias.name in BANNED_GOVERNED_NAMES
                            ):
                                hits.append(
                                    (
                                        rel,
                                        getattr(node, "lineno", 0),
                                        f"from {mod} import {alias.name}",
                                    )
                                )
                            # Any import from hermes_chat_join / universal_egress is suspect
                            # if the name is a governed helper or star.
                            if mod.endswith("hermes_chat_join") or mod.endswith(
                                "universal_egress"
                            ):
                                if alias.name in BANNED_GOVERNED_NAMES or alias.name == "*":
                                    hits.append(
                                        (
                                            rel,
                                            getattr(node, "lineno", 0),
                                            f"from {mod} import {alias.name}",
                                        )
                                    )
                if isinstance(node, ast.Attribute):
                    if node.attr in BANNED_ALL_NAMES:
                        hits.append(
                            (
                                rel,
                                getattr(node, "lineno", 0),
                                f"attr {node.attr}",
                            )
                        )
                if isinstance(node, ast.Name) and node.id in BANNED_ALL_NAMES:
                    hits.append(
                        (
                            rel,
                            getattr(node, "lineno", 0),
                            f"name {node.id}",
                        )
                    )
    return hits


def scan_ast_dynamic_bypass(root: Path) -> List[Tuple[str, int, str]]:
    """AST pass: reject dynamic/late import, getattr, re-export, and name assembly.

    Covers SPEC P0-2 repair item 3: aliases, re-exports, wrappers,
    dynamic import/reload, and late import of governed helpers / broker scope.
    """
    hits: List[Tuple[str, int, str]] = []
    for pattern in AGENT_SCAN_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if _path_allowed(rel):
                continue
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=rel)
            except (OSError, SyntaxError):
                continue

            constants = _collect_string_constants(tree)
            const_set = list(dict.fromkeys(constants))  # preserve order, uniq

            # 1) String constants that name or assemble banned symbols/modules.
            for target in list(BANNED_ALL_NAMES) + [
                "omnis_wing.absolute.hermes_chat_join",
                "omnis_wing.absolute.universal_egress",
                "omnis_wing.absolute.broker_guard",
            ]:
                if _can_assemble_banned(const_set, target):
                    # Find a representative line
                    lineno = 0
                    for node in ast.walk(tree):
                        s = _const_str(node)
                        if s and (s == target or target in s or s in target):
                            lineno = getattr(node, "lineno", 0)
                            break
                    hits.append(
                        (
                            rel,
                            lineno,
                            f"dynamic_name_assembly:{target}",
                        )
                    )

            # 2) importlib.import_module / __import__ / reload with banned module fragments
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fname = _call_func_name(node)
                if fname not in _DYNAMIC_IMPORT_FUNCS and fname not in (
                    "getattr",
                    "hasattr",
                ):
                    # also catch importlib.import_module via attr already covered
                    continue

                if fname in _DYNAMIC_IMPORT_FUNCS or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in _DYNAMIC_IMPORT_FUNCS
                ):
                    for arg in list(node.args) + [
                        k.value for k in node.keywords if k.arg in (None, "name", "module")
                    ]:
                        s = _const_str(arg)
                        if s and any(frag in s for frag in _BANNED_MODULE_FRAGMENTS):
                            hits.append(
                                (
                                    rel,
                                    getattr(node, "lineno", 0),
                                    f"dynamic_import:{s[:80]}",
                                )
                            )
                        # f-string / binop module assembly: if any const in call subtree is banned
                        for sub in ast.walk(arg):
                            ss = _const_str(sub)
                            if ss and any(frag in ss for frag in _BANNED_MODULE_FRAGMENTS):
                                hits.append(
                                    (
                                        rel,
                                        getattr(node, "lineno", 0),
                                        f"dynamic_import_fragment:{ss[:80]}",
                                    )
                                )

                if fname in ("getattr", "hasattr") or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("getattr", "hasattr")
                ):
                    if len(node.args) >= 2:
                        s = _const_str(node.args[1])
                        if s and s in BANNED_ALL_NAMES:
                            hits.append(
                                (
                                    rel,
                                    getattr(node, "lineno", 0),
                                    f"dynamic_getattr:{s}",
                                )
                            )

            # 3) importlib present + any banned fragment constant in same file
            uses_importlib = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "importlib" or alias.name.startswith("importlib."):
                            uses_importlib = True
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "importlib"
                ):
                    uses_importlib = True
                if isinstance(node, ast.Name) and node.id == "__import__":
                    uses_importlib = True
            if uses_importlib:
                for c in const_set:
                    if any(frag in c for frag in _BANNED_MODULE_FRAGMENTS) or any(
                        b in c for b in BANNED_GOVERNED_NAMES
                    ):
                        hits.append(
                            (
                                rel,
                                0,
                                f"importlib_with_banned_fragment:{c[:80]}",
                            )
                        )
                        break

            # 4) Re-export wrappers: assign Name = Call/Name of banned, or __all__ listing
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id in BANNED_ALL_NAMES:
                            hits.append(
                                (
                                    rel,
                                    getattr(node, "lineno", 0),
                                    f"reexport_assign:{t.id}",
                                )
                            )
                if isinstance(node, ast.Assign):
                    # __all__ = [..., "governed_..."]
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == "__all__":
                            for sub in ast.walk(node.value):
                                s = _const_str(sub)
                                if s and s in BANNED_ALL_NAMES:
                                    hits.append(
                                        (
                                            rel,
                                            getattr(node, "lineno", 0),
                                            f"reexport_all:{s}",
                                        )
                                    )
    return hits


def assert_no_agent_governed_bypass(root: Path) -> None:
    hits = (
        scan_ast_agent_imports(root)
        + scan_source_for_governed_bypass(root)
        + scan_ast_dynamic_bypass(root)
    )
    # de-dupe
    uniq = sorted(set(hits))
    if uniq:
        detail = "; ".join(f"{p}:{n}:{s}" for p, n, s in uniq[:20])
        raise BrokerViolation(f"agent_governed_bypass:{len(uniq)}:{detail}")
