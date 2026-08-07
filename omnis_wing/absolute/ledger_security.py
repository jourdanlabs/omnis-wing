"""Production ledger path security — fail closed, never chmod-repair.

Controlled surfaces: configured ledger_dir and the ledger file under it.
System ancestors may be root-owned and may include OS symlinks (e.g. macOS
/var -> /private/var). Those are not refused.

Refuse when:
- ledger_dir or ledger file is a symlink
- ledger_dir is group/other-accessible or wrong owner
- ledger file is group/other-readable/writable or wrong owner
Never chmod-repairs an unsafe pre-existing path.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


class LedgerSecurityError(RuntimeError):
    """Unsafe ledger path — refuse before provider call."""


def _uid() -> int:
    return os.getuid()


def _is_group_or_other_rwx(mode: int) -> bool:
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


def _is_group_or_other_rw(mode: int) -> bool:
    return bool(mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH))


def abspath_nofollow(path: Path) -> Path:
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.normpath(str(path)))


def inspect_controlled_dir(path: Path) -> None:
    path = Path(path)
    if path.is_symlink():
        raise LedgerSecurityError(f"symlink_refused:{path}")
    if not path.exists():
        return
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode):
        raise LedgerSecurityError(f"symlink_refused:{path}")
    if not stat.S_ISDIR(st.st_mode):
        raise LedgerSecurityError(f"not_a_directory:{path}")
    if st.st_uid != _uid():
        raise LedgerSecurityError(f"wrong_owner:{path}:uid={st.st_uid}")
    mode = stat.S_IMODE(st.st_mode)
    if _is_group_or_other_rwx(mode):
        raise LedgerSecurityError(f"dir_not_private:{path}:mode={oct(mode)}")


def inspect_controlled_file(path: Path) -> None:
    path = Path(path)
    if path.is_symlink():
        raise LedgerSecurityError(f"symlink_refused:{path}")
    if not path.exists():
        return
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode):
        raise LedgerSecurityError(f"symlink_refused:{path}")
    if not stat.S_ISREG(st.st_mode):
        raise LedgerSecurityError(f"not_a_regular_file:{path}")
    if st.st_uid != _uid():
        raise LedgerSecurityError(f"wrong_owner:{path}:uid={st.st_uid}")
    mode = stat.S_IMODE(st.st_mode)
    if _is_group_or_other_rw(mode):
        raise LedgerSecurityError(f"file_not_private:{path}:mode={oct(mode)}")


def mkdir_private_tree(ledger_dir: Path) -> None:
    """Ensure ledger_dir exists at 0700. Refuse unsafe pre-existing. No chmod repair."""
    ledger_dir = abspath_nofollow(ledger_dir)

    if ledger_dir.is_symlink():
        raise LedgerSecurityError(f"symlink_refused:{ledger_dir}")

    if ledger_dir.exists():
        inspect_controlled_dir(ledger_dir)
        return

    # Create missing trailing components; parent must already exist (system or prior).
    missing = []
    cur = ledger_dir
    while not cur.exists() and cur != cur.parent:
        if cur.is_symlink():
            raise LedgerSecurityError(f"symlink_refused:{cur}")
        missing.append(cur.name)
        cur = cur.parent
    if not cur.exists():
        raise LedgerSecurityError(f"no_existing_ancestor:{ledger_dir}")

    for name in reversed(missing):
        cur = cur / name
        if cur.is_symlink():
            raise LedgerSecurityError(f"symlink_refused:{cur}")
        if cur.exists():
            inspect_controlled_dir(cur)
            continue
        try:
            os.mkdir(cur, 0o700)
        except OSError as exc:
            raise LedgerSecurityError(f"mkdir_failed:{cur}:{exc}") from exc
        st = cur.lstat()
        mode = stat.S_IMODE(st.st_mode)
        if st.st_uid != _uid() or _is_group_or_other_rwx(mode):
            raise LedgerSecurityError(
                f"dir_create_not_private:{cur}:mode={oct(mode)}:uid={st.st_uid}"
            )


def create_private_ledger_file(path: Path) -> None:
    path = abspath_nofollow(path)
    if path.is_symlink():
        raise LedgerSecurityError(f"symlink_refused:{path}")
    if path.exists():
        inspect_controlled_file(path)
        return
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    st = path.lstat()
    mode = stat.S_IMODE(st.st_mode)
    if st.st_uid != _uid() or _is_group_or_other_rw(mode):
        raise LedgerSecurityError(
            f"file_create_not_private:{path}:mode={oct(mode)}:uid={st.st_uid}"
        )


def prepare_private_ledger_file(path: Path) -> Path:
    path = abspath_nofollow(path)
    ledger_dir = path.parent
    mkdir_private_tree(ledger_dir)
    create_private_ledger_file(path)
    inspect_controlled_dir(ledger_dir)
    inspect_controlled_file(path)
    return path


def assert_lineage_safe(path: Path) -> None:
    path = abspath_nofollow(path)
    inspect_controlled_dir(path.parent)
    if path.exists() or path.is_symlink():
        inspect_controlled_file(path)


def inspect_path_component(path: Path) -> None:
    path = Path(path)
    if path.is_dir() and not path.is_symlink():
        inspect_controlled_dir(path)
    else:
        inspect_controlled_file(path)
