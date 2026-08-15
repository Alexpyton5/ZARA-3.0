"""133 regression: LAB message order must be deterministic even when several
messages land inside the same created_at tick (ties broken by rowid)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.lab_coordinator import LabCoordinator


def _fresh_lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    lab = LabCoordinator()
    return lab


@pytest.mark.asyncio
async def test_message_order_is_stable_under_created_at_ties(tmp_path, monkeypatch):
    lab = _fresh_lab(tmp_path, monkeypatch)
    await lab.initialize()

    # Force an exact tie on created_at for every row.
    frozen = 1_700_000_000.0
    with sqlite3.connect(lab.db_path) as conn:
        for i in range(1, 11):
            conn.execute(
                "INSERT INTO messages(id,author,target,content,kind,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (f"M{i:03d}", "ZARA", "mentor", f"seq-{i:02d}", "agent", frozen),
            )
        conn.commit()

    state = await lab.get_state()
    seq = [m["content"] for m in state["messages"] if str(m["content"]).startswith("seq-")]

    assert seq == [f"seq-{i:02d}" for i in range(1, 11)]
    assert len(set(seq)) == len(seq)


@pytest.mark.asyncio
async def test_reload_does_not_duplicate_history(tmp_path, monkeypatch):
    lab = _fresh_lab(tmp_path, monkeypatch)
    await lab.initialize()
    with sqlite3.connect(lab.db_path) as conn:
        conn.execute(
            "INSERT INTO messages(id,author,target,content,kind,created_at)"
            " VALUES(?,?,?,?,?,?)",
            ("M1", "ZARA", "mentor", "unico", "agent", 1_700_000_000.0),
        )
        conn.commit()

    lab2 = LabCoordinator()
    await lab2.initialize()
    state = await lab2.get_state()
    hits = [m for m in state["messages"] if m["content"] == "unico"]

    assert len(hits) == 1
