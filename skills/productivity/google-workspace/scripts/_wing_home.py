"""Resolve WING_HOME for standalone skill scripts.

Skill scripts may run outside the WING process (e.g. system Python,
nix env, CI) where ``wing_constants`` is not importable.  This module
provides the same ``get_wing_home()`` and ``display_wing_home()``
contracts as ``wing_constants`` without requiring it on ``sys.path``.

When ``wing_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``wing_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``WING_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from wing_constants import display_wing_home as display_wing_home
    from wing_constants import get_wing_home as get_wing_home
except (ModuleNotFoundError, ImportError):

    def get_wing_home() -> Path:
        """Return the WING home directory (default: ~/.omnis-wing).

        Mirrors ``wing_constants.get_wing_home()``."""
        val = os.environ.get("WING_HOME", "").strip()
        return Path(val) if val else Path.home() / ".omnis-wing"

    def display_wing_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``wing_constants.display_wing_home()``."""
        home = get_wing_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
