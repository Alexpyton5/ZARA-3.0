"""Single-writer advisory guard for the ZARA data directory.

Detects (never kills) another live ZARA process already owning the same data
dir. Uses an advisory lock file holding the owner PID. The guard is fail-open:
any unexpected error degrades to "no guard" so the runtime never breaks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOCK_NAME = "zara.writer.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


@dataclass
class WriterLock:
    path: Path
    owner_pid: int
    acquired: bool
    conflict_pid: int | None = None

    @property
    def blocked(self) -> bool:
        return not self.acquired

    def release(self) -> None:
        """Release only if we own the lock. Never removes another PID's lock."""
        if not self.acquired:
            return
        try:
            if self.path.exists() and self.path.read_text(encoding="utf-8").strip() == str(self.owner_pid):
                self.path.unlink()
        except Exception:
            pass


def acquire_writer_lock(data_dir: Path | str) -> WriterLock:
    """Try to claim the data dir as the single writer.

    Returns a WriterLock. `acquired=False` + `conflict_pid` means another live
    process already holds it: the caller should warn and refuse to open the DB
    for writing. A stale lock (dead PID) is reclaimed.
    """
    base = Path(data_dir)
    pid = os.getpid()
    try:
        base.mkdir(parents=True, exist_ok=True)
        lock = base / LOCK_NAME
        if lock.exists():
            try:
                raw = lock.read_text(encoding="utf-8").strip()
                other = int(raw) if raw.isdigit() else -1
            except Exception:
                other = -1
            if other == pid:
                return WriterLock(lock, pid, True)
            if other > 0 and _pid_alive(other):
                return WriterLock(lock, pid, False, conflict_pid=other)
            # stale lock: owner is gone, reclaim it
        lock.write_text(str(pid), encoding="utf-8")
        # re-read to confirm we won a race
        try:
            if lock.read_text(encoding="utf-8").strip() != str(pid):
                return WriterLock(lock, pid, False, conflict_pid=-1)
        except Exception:
            pass
        return WriterLock(lock, pid, True)
    except Exception:
        # fail-open: never break the runtime because of the guard
        return WriterLock(base / LOCK_NAME, pid, True)
