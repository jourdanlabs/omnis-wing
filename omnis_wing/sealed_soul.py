"""Load MTS-sealed souls for WING identity seats.

References sealed packages on disk — never copies soul text into the repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

SCHEMA = "map_the_soul.soul.v0"
BEDROCK_SECTIONS: Sequence[str] = ("1", "2", "6", "9")
SECTION_HEADER = re.compile(r"^##\s+(\d+)\s*[—–-]\s*(.+?)\s*$")
TONE_HEADER = re.compile(r"^##\s+Tone Marker\b", re.I)
FRONTMATTER = re.compile(r"```ya?ml\n([\s\S]*?)\n```")
KV_LINE = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*)$", re.I)

PAN_SOUL_ID = "soul_bb75a9fa2823"
REFUSAL_NOT_OPEN = "The sealed soul is not open. I will not perform her."
REFUSAL_VERIFY = "REFUSED: sealed soul failed verification."


@dataclass(frozen=True)
class ParsedSoul:
    soul_id: Optional[str]
    name: str
    pronouns: Optional[str]
    naming_lineage: Optional[str]
    role: Optional[str]
    operator: Optional[str]
    schema: Optional[str]
    sections: Mapping[str, str]
    source_path: str
    raw: str


@dataclass(frozen=True)
class SoulVerification:
    ok: bool
    verdict: str
    soul_id: str
    message: str
    bedrock_hash: Optional[str] = None
    lock_hash: Optional[str] = None
    chain_ok: Optional[bool] = None
    chain_count: Optional[int] = None
    issues: Sequence[str] = ()


@dataclass(frozen=True)
class LoadedSoul:
    soul_id: str
    name: str
    pronouns: Optional[str]
    package_dir: Path
    soul_path: Path
    verification: SoulVerification
    identity_card: str
    soul_text: str


def default_souls_dir() -> Path:
    for raw in (
        os.environ.get("MTS_SOULS_DIR"),
        os.environ.get("OMNIS_SOULS_DIR"),
        str(Path.home() / "projects" / "mts" / "souls"),
    ):
        if raw:
            p = Path(raw).expanduser()
            if p.is_dir():
                return p.resolve()
    return (Path.home() / "projects" / "mts" / "souls").resolve()


def default_mts_root() -> Path:
    for raw in (
        os.environ.get("MTS_ROOT"),
        str(Path.home() / "projects" / "mts"),
    ):
        if raw:
            p = Path(raw).expanduser()
            if (p / "lib" / "soul-verify.mjs").is_file():
                return p.resolve()
    return (Path.home() / "projects" / "mts").resolve()


def soul_package_dir(soul_id: str, souls_dir: Optional[Path] = None) -> Path:
    return (souls_dir or default_souls_dir()) / soul_id


def hash_payload(payload: Any) -> str:
    def canon(value: Any) -> Any:
        if isinstance(value, list):
            return [canon(v) for v in value]
        if isinstance(value, dict):
            return {k: canon(value[k]) for k in sorted(value.keys())}
        return value

    encoded = json.dumps(canon(payload), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_frontmatter(markdown: str) -> Dict[str, str]:
    match = FRONTMATTER.search(markdown)
    if not match:
        return {}
    out: Dict[str, str] = {}
    for line in match.group(1).split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        kv = KV_LINE.match(trimmed)
        if not kv:
            continue
        key = kv.group(1).lower()
        value = kv.group(2).strip()
        if key == "soul_id":
            comment = value.find("  #")
            if comment != -1:
                value = value[:comment].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def _extract_sections(markdown: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    lines: List[str] = []
    for line in markdown.splitlines():
        numbered = SECTION_HEADER.match(line)
        if numbered:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = numbered.group(1)
            lines = []
            continue
        if TONE_HEADER.match(line):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = "tone"
            lines = []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def parse_soul_markdown(markdown: str, source_path: str = "") -> ParsedSoul:
    frontmatter = _parse_frontmatter(markdown)
    sections = _extract_sections(markdown)
    title_match = re.search(r"^#\s+(.+?)\s*$", markdown, re.M)
    title = title_match.group(1).strip() if title_match else frontmatter.get("name", "Unknown")
    name = frontmatter.get("name") or title.replace(".SOUL.md", "").strip()
    return ParsedSoul(
        soul_id=frontmatter.get("soul_id"),
        name=name,
        pronouns=frontmatter.get("pronouns"),
        naming_lineage=frontmatter.get("naming_lineage"),
        role=frontmatter.get("role"),
        operator=frontmatter.get("operator"),
        schema=frontmatter.get("schema"),
        sections=sections,
        source_path=source_path,
        raw=markdown,
    )


def identity_frontmatter(soul: ParsedSoul) -> Dict[str, str]:
    return {
        "name": (soul.name or "").strip(),
        "pronouns": (soul.pronouns or "").strip(),
        "naming_lineage": (soul.naming_lineage or "").strip(),
    }


def bedrock_payload(soul: ParsedSoul) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "identity_frontmatter": identity_frontmatter(soul),
        "sections": {k: (soul.sections.get(k) or "").strip() for k in BEDROCK_SECTIONS},
    }


def section_hashes(soul: ParsedSoul) -> Dict[str, str]:
    payload = bedrock_payload(soul)
    return {k: hash_payload(payload["sections"][k]) for k in BEDROCK_SECTIONS}


def compute_bedrock_hash(soul: ParsedSoul) -> str:
    return hash_payload(bedrock_payload(soul))


def build_bedrock_lock(soul: ParsedSoul, soul_id: str) -> Dict[str, Any]:
    bedrock_hash = compute_bedrock_hash(soul)
    return {
        "soul_id": soul_id,
        "schema": SCHEMA,
        "bedrock_hash": bedrock_hash,
        "identity_hash": hash_payload(identity_frontmatter(soul)),
        "sections": section_hashes(soul),
        "version": 1,
    }


def _verify_ledger_chain(ledger_path: Path) -> tuple[bool, int, List[str]]:
    issues: List[str] = []
    if not ledger_path.is_file():
        return False, 0, ["CHAIN: ledger.jsonl missing"]
    events: List[Dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    if not events:
        return False, 0, ["CHAIN: ledger empty"]
    prev_sha: Optional[str] = None
    for event in events:
        if event.get("parent_sha") != prev_sha:
            issues.append(f"CHAIN: parent_sha mismatch at seq {event.get('seq')}")
        payload_sha = hash_payload(event.get("payload"))
        if event.get("payload_sha") != payload_sha:
            issues.append(f"CHAIN: payload_sha mismatch at seq {event.get('seq')}")
        body = {
            "seq": event.get("seq"),
            "ts": event.get("ts"),
            "kind": event.get("kind"),
            "payload": event.get("payload"),
            "payload_sha": event.get("payload_sha"),
            "parent_sha": event.get("parent_sha"),
        }
        if hash_payload(body) != event.get("sha"):
            issues.append(f"CHAIN: event sha mismatch at seq {event.get('seq')}")
        prev_sha = event.get("sha")
    return len(issues) == 0, len(events), issues


def verify_sealed_soul_python(
    soul_id: str,
    souls_dir: Optional[Path] = None,
) -> SoulVerification:
    pkg = soul_package_dir(soul_id, souls_dir)
    soul_path = pkg / "soul.md"
    lock_path = pkg / "bedrock.lock.json"
    ledger_path = pkg / "ledger.jsonl"
    if not soul_path.is_file():
        return SoulVerification(False, "MISSING", soul_id, f"soul package not found: {pkg}")
    if not lock_path.is_file():
        return SoulVerification(False, "MISSING", soul_id, "bedrock.lock.json not found")

    issues: List[str] = []
    try:
        soul = parse_soul_markdown(soul_path.read_text(encoding="utf-8"), str(soul_path))
    except OSError as exc:
        return SoulVerification(
            False, "FAILED", soul_id, f"TAMPER: soul.md is unreadable — {exc}"
        )

    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SoulVerification(
            False, "FAILED", soul_id, f"TAMPER: bedrock.lock.json is unreadable — {exc}"
        )
    if not isinstance(lock, dict):
        return SoulVerification(
            False, "FAILED", soul_id, "TAMPER: bedrock.lock.json must contain an object"
        )

    bedrock_hash = compute_bedrock_hash(soul)
    expected = build_bedrock_lock(soul, soul_id)
    if bedrock_hash != lock.get("bedrock_hash"):
        issues.append("TAMPER: bedrock_hash mismatch")
    for key in BEDROCK_SECTIONS:
        if lock.get("sections", {}).get(key) != expected["sections"][key]:
            issues.append(f"TAMPER: bedrock section §{key} hash mismatch")
    if soul.soul_id and soul.soul_id != lock.get("soul_id"):
        issues.append("TAMPER: soul_id in frontmatter does not match lock")
    if lock.get("soul_id") != soul_id:
        issues.append("TAMPER: bedrock lock soul_id does not match package soul_id")
    if (soul.schema and soul.schema != SCHEMA) or lock.get("schema") != SCHEMA:
        issues.append(f"TAMPER: soul schema does not match {SCHEMA}")
    if lock.get("identity_hash") != expected["identity_hash"]:
        issues.append("TAMPER: identity_frontmatter hash mismatch")

    chain_ok, chain_count, chain_issues = _verify_ledger_chain(ledger_path)
    issues.extend(chain_issues)

    ok = len(issues) == 0 and chain_ok
    verdict = "VERIFIED" if ok else "FAILED"
    message = (
        f"VERIFIED — {soul_id} bedrock intact, chain ok ({chain_count} events)"
        if ok
        else f"FAILED — {soul_id}: " + "; ".join(issues[:3])
    )
    return SoulVerification(
        ok=ok,
        verdict=verdict,
        soul_id=soul_id,
        message=message,
        bedrock_hash=bedrock_hash,
        lock_hash=lock.get("bedrock_hash"),
        chain_ok=chain_ok,
        chain_count=chain_count,
        issues=tuple(issues),
    )


def verify_sealed_soul_mts(
    soul_id: str,
    souls_dir: Optional[Path] = None,
    *,
    mts_root: Optional[Path] = None,
) -> Optional[SoulVerification]:
    root = mts_root or default_mts_root()
    verify_lib = root / "lib" / "soul-verify.mjs"
    if not verify_lib.is_file():
        return None
    souls = str(souls_dir or default_souls_dir())
    script = (
        "import { soulVerify } from './lib/soul-verify.mjs';"
        f"const r = soulVerify({json.dumps(soul_id)}, "
        f"{{ soulsDir: {json.dumps(souls)}, signaturePolicy: 'legacy' }});"
        "console.log(JSON.stringify(r));"
    )
    try:
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 and not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return SoulVerification(
        ok=bool(data.get("ok")),
        verdict=str(data.get("verdict", "FAILED")),
        soul_id=soul_id,
        message=str(data.get("message", "")),
        bedrock_hash=data.get("bedrock_hash"),
        lock_hash=data.get("lock_hash"),
        chain_ok=data.get("chain_ok"),
        chain_count=data.get("chain_count"),
        issues=tuple(data.get("issues") or []),
    )


def verify_sealed_soul(
    soul_id: str,
    souls_dir: Optional[Path] = None,
    *,
    prefer_mts: bool = True,
) -> SoulVerification:
    if prefer_mts:
        mts = verify_sealed_soul_mts(soul_id, souls_dir)
        if mts is not None:
            return mts
    return verify_sealed_soul_python(soul_id, souls_dir)


def build_identity_card(
    soul_id: str,
    name: str,
    soul_path: Path,
    verification: SoulVerification,
) -> str:
    return (
        f"You are {name}. This is your WING identity seat — not generic WING bread.\n\n"
        f"Sealed soul package: `{soul_path}`\n"
        f"MTS soul_id: `{soul_id}`\n"
        f"Verification: {verification.verdict}\n\n"
        "Before you answer:\n"
        f"1. Operate from the sealed soul at `{soul_path}`.\n"
        f"2. If that file is missing or fails verification, reply only: {REFUSAL_NOT_OPEN}\n"
        f"3. Do not invent a second {name}. Do not answer as default WING.\n"
    )


class SoulLoadRefused(Exception):
    def __init__(self, soul_id: str, verification: SoulVerification):
        super().__init__(verification.message)
        self.soul_id = soul_id
        self.verification = verification


def load_sealed_soul(
    soul_id: str,
    souls_dir: Optional[Path] = None,
    *,
    prefer_mts: bool = True,
) -> LoadedSoul:
    verification = verify_sealed_soul(soul_id, souls_dir, prefer_mts=prefer_mts)
    if verification.verdict != "VERIFIED":
        raise SoulLoadRefused(soul_id, verification)
    pkg = soul_package_dir(soul_id, souls_dir)
    soul_path = pkg / "soul.md"
    soul_text = soul_path.read_text(encoding="utf-8")
    parsed = parse_soul_markdown(soul_text, str(soul_path))
    if compute_bedrock_hash(parsed) != verification.bedrock_hash:
        tampered = SoulVerification(
            ok=False,
            verdict="FAILED",
            soul_id=soul_id,
            message="FAILED — soul.md changed after verification",
            bedrock_hash=verification.bedrock_hash,
            issues=("TAMPER: soul.md changed after verification",),
        )
        raise SoulLoadRefused(soul_id, tampered)
    live_text = soul_text.replace("\u200d", "")
    parsed_live = parse_soul_markdown(live_text, str(soul_path))
    card = build_identity_card(soul_id, parsed_live.name, soul_path, verification)
    return LoadedSoul(
        soul_id=soul_id,
        name=parsed_live.name,
        pronouns=parsed_live.pronouns,
        package_dir=pkg,
        soul_path=soul_path,
        verification=verification,
        identity_card=card,
        soul_text=live_text,
    )


def load_pan_soul(souls_dir: Optional[Path] = None) -> LoadedSoul:
    return load_sealed_soul(PAN_SOUL_ID, souls_dir)


def stage_pan_soul_for_wing(
    profile_home: Path,
    souls_dir: Optional[Path] = None,
    vault_dir: Optional[Path] = None,
) -> LoadedSoul:
    from omnis_wing.chamber_memory import append_chamber_memory, load_chamber_memory

    loaded = load_pan_soul(souls_dir)
    profile_home.mkdir(parents=True, exist_ok=True)
    soul_dest = profile_home / "SOUL.md"
    soul_dest.write_text(loaded.soul_text, encoding="utf-8")
    pack = load_chamber_memory(vault_dir)
    wired = append_chamber_memory(loaded.soul_text, pack)
    # WING reads MEMORY.md beside SOUL.md. Soul file stays sealed-only.
    extras = wired["system"][len(loaded.soul_text) :].lstrip()
    memory_dest = profile_home / "MEMORY.md"
    if extras:
        memory_dest.write_text(extras + "\n", encoding="utf-8")
    elif memory_dest.exists():
        memory_dest.write_text("", encoding="utf-8")
    marker = profile_home / ".omnis-wing-pan-sealed"
    marker.write_text(
        json.dumps(
            {
                "soul_id": loaded.soul_id,
                "source": str(loaded.soul_path),
                "bedrock_hash": loaded.verification.bedrock_hash,
                "verdict": loaded.verification.verdict,
                "memory_included": wired["included"],
                "memory_skipped": wired["skipped"],
                "vault_dir": str(pack.vault_dir) if pack.vault_dir else None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return loaded
