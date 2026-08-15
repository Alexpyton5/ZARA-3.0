import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.single_writer import acquire_writer_lock, LOCK_NAME  # noqa: E402


def test_acquire_creates_lock(tmp_path):
    lk = acquire_writer_lock(tmp_path)
    assert lk.acquired is True
    assert (tmp_path / LOCK_NAME).read_text().strip() == str(os.getpid())
    lk.release()
    assert not (tmp_path / LOCK_NAME).exists()


def test_same_process_reentrant(tmp_path):
    a = acquire_writer_lock(tmp_path)
    b = acquire_writer_lock(tmp_path)
    assert a.acquired and b.acquired
    a.release()


def test_live_foreign_pid_blocks(tmp_path, monkeypatch):
    (tmp_path / LOCK_NAME).write_text("424242")
    monkeypatch.setattr("core.single_writer._pid_alive", lambda pid: True)
    lk = acquire_writer_lock(tmp_path)
    assert lk.acquired is False
    assert lk.blocked is True
    assert lk.conflict_pid == 424242
    # foreign lock must be preserved
    assert (tmp_path / LOCK_NAME).read_text().strip() == "424242"
    lk.release()
    assert (tmp_path / LOCK_NAME).read_text().strip() == "424242"


def test_stale_lock_reclaimed(tmp_path, monkeypatch):
    (tmp_path / LOCK_NAME).write_text("999999")
    monkeypatch.setattr("core.single_writer._pid_alive", lambda pid: False)
    lk = acquire_writer_lock(tmp_path)
    assert lk.acquired is True
    assert (tmp_path / LOCK_NAME).read_text().strip() == str(os.getpid())
    lk.release()


def test_garbage_lock_reclaimed(tmp_path):
    (tmp_path / LOCK_NAME).write_text("not-a-pid")
    lk = acquire_writer_lock(tmp_path)
    assert lk.acquired is True
    lk.release()


def test_distinct_data_dirs_do_not_conflict(tmp_path, monkeypatch):
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    l1 = acquire_writer_lock(d1)
    l2 = acquire_writer_lock(d2)
    assert l1.acquired and l2.acquired
    l1.release()
    l2.release()
