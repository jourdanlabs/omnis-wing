"""Chamber memory on a WING Pan seat — same files CODE hands a spawn.

Reads ~/chamber-soul-vault. Never copies the vault into this repo.
Soul stays first and is never truncated. Missing vault fails open.
Does not walk memory/*.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

LIVE_CHAMBER_VAULT = Path.home() / "chamber-soul-vault"
CADUCEUS_MAX_INPUT_BYTES = 262144


@dataclass(frozen=True)
class ChamberMemoryPack:
    vault_dir: Optional[Path]
    boot: str
    memory: str
    sessions: str
    sessions_label: str


EMPTY = ChamberMemoryPack(
    vault_dir=None,
    boot="",
    memory="",
    sessions="",
    sessions_label="",
)


def iso_week_file(d: Optional[datetime] = None) -> str:
    now = d or datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}.jsonl"


def _prev_week_file(name: str) -> Optional[str]:
    if len(name) < 10 or not name.startswith("20") or "-W" not in name:
        return None
    try:
        y = int(name[0:4])
        w = int(name[6:8])
    except ValueError:
        return None
    w -= 1
    if w < 1:
        y -= 1
        w = 52
    return f"{y}-W{w:02d}.jsonl"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return ""


def resolve_chamber_vault(vault_dir: Optional[Path] = None) -> Optional[Path]:
    if vault_dir is not None:
        p = Path(vault_dir).expanduser()
        return p if p.is_dir() else None
    env = os.environ.get("OMNIS_CHAMBER_VAULT")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
    if LIVE_CHAMBER_VAULT.is_dir():
        return LIVE_CHAMBER_VAULT.resolve()
    return None


def _session_slice(vault: Path, now: Optional[datetime] = None) -> tuple[str, str]:
    week = iso_week_file(now)
    week_path = vault / "sessions" / week
    week_text = _read_text(week_path).strip()
    parts: List[str] = []
    labels: List[str] = []
    if week_text:
        parts.append(week_text)
        labels.append(f"sessions/{week}")
    lines = week_text.splitlines() if week_text else []
    if len(lines) < 10:
        prev = _prev_week_file(week)
        if prev:
            prior = _read_text(vault / "sessions" / prev).strip()
            if prior:
                parts.append(prior)
                labels.append(f"sessions/{prev}")
    return "\n".join(parts), " + ".join(labels)


def load_chamber_memory(
    vault_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> ChamberMemoryPack:
    try:
        vault = resolve_chamber_vault(vault_dir)
        if vault is None:
            return EMPTY
        sessions, label = _session_slice(vault, now)
        return ChamberMemoryPack(
            vault_dir=vault,
            boot=_read_text(vault / "BOOT.md"),
            memory=_read_text(vault / "memory" / "MEMORY.md"),
            sessions=sessions,
            sessions_label=label,
        )
    except Exception:
        return EMPTY


def append_chamber_memory(
    soul_system: str,
    pack: ChamberMemoryPack,
    max_bytes: int = CADUCEUS_MAX_INPUT_BYTES,
) -> dict:
    included: List[str] = ["soul"]
    skipped: List[str] = []
    system = soul_system
    extras: Sequence[tuple[str, str]] = (
        ("BOOT.md", pack.boot),
        ("memory/MEMORY.md", pack.memory),
        (pack.sessions_label or "sessions", pack.sessions),
    )
    refuse_rest = False
    for name, body in extras:
        body = (body or "").strip()
        if not body:
            continue
        if refuse_rest:
            skipped.append(name)
            continue
        block = f"\n\n--- {name} ---\n{body}"
        if len(system.encode("utf-8")) + len(block.encode("utf-8")) > max_bytes:
            skipped.append(name)
            refuse_rest = True
            continue
        system += block
        included.append(name)
    return {
        "system": system,
        "included": included,
        "skipped": skipped,
        "bytes": len(system.encode("utf-8")),
    }
