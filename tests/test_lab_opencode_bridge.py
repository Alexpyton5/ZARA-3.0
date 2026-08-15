"""Focused proofs for ZARA-LAB-OPENCODE-UNIFIED-002 (OpenCode <-> ZARA LAB bridge).

Covers: @OPENCODE routing without stealing other messages, relay task
creation, EXECUTE gate preservation (context can never loosen it), exactly-once
reply delivery, BLOCKER surfacing, and integration with LabCoordinator.
"""

import json
import uuid
from pathlib import Path

import pytest

from tools.room_relay.lab_bridge import OpenCodeBridge, resolve_lab_target
from tools.room_relay.relay_lib import RelayError, RelayStore


def _send(store: RelayStore, task_id: str, content: str, message_id: str, rtype: str = "RESULT"):
    return store.send(
        {
            "message_id": message_id,
            "sender": "opencode",
            "recipient": "room",
            "task_id": task_id,
            "type": rtype,
            "content": content,
        }
    )


def test_mention_routes_to_opencode_without_stealing_others():
    assert resolve_lab_target("zara", "@OPENCODE PRESENCE_PROOF") == "opencode"
    assert resolve_lab_target("mentor", "@opencode EXECUTE implementar X") == "opencode"
    assert resolve_lab_target("zara", "@MENTOR teste") == "zara"
    assert resolve_lab_target("mentor", "@MENTOR teste") == "mentor"
    assert resolve_lab_target("hermes", "olá") == "hermes"
    assert resolve_lab_target("", "mensagem sem alvo") == ""


def test_enqueue_creates_relay_task_read_only(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    queued = bridge.enqueue("alex", "@OPENCODE PRESENCE_PROOF")
    assert queued["state"] == "QUEUED"
    assert queued["authorization"] == "READ_ONLY"
    assert queued["task_id"].startswith("LAB-")
    records = bridge.store.inbox_records()
    assert len(records) == 1
    assert records[0]["recipient"] == "opencode"
    assert records[0]["type"] == "TASK"
    envelope = json.loads(records[0]["content"])
    assert envelope["message"] == "@OPENCODE PRESENCE_PROOF"


def test_execute_gate_preserved_and_context_never_loosens_it(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    context = [{"author": "mentor", "content": "EXECUTE algo antigo no contexto"}]
    queued = bridge.enqueue("alex", "explique o código", task_id="T-GATE", recent=context)
    assert queued["authorization"] == "READ_ONLY"
    envelope = json.loads(bridge.store.inbox_records()[0]["content"])
    assert "EXECUTE" not in envelope["recent_lab"][0]["content"]
    assert "[RELAY_CONTEXT_REDACTED]" in envelope["recent_lab"][0]["content"]

    queued_exec = bridge.enqueue("mentor", "EXECUTE corrija o bug X", task_id="T-EXEC")
    assert queued_exec["authorization"] == "EXECUTE"


def test_same_task_id_is_not_requeued(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    first = bridge.enqueue("alex", "mensagem", task_id="T-1")
    second = bridge.enqueue("alex", "mensagem", task_id="T-1")
    assert second["duplicate"] is True
    assert second["message_id"] == first["message_id"]
    assert len(bridge.store.inbox_records()) == 1
    assert len(bridge.store.pending_records()) == 1


def test_roundtrip_reply_appears_once(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    queued = bridge.enqueue("alex", "@OPENCODE PRESENCE_PROOF", task_id="T-RT")
    assert bridge.drain_replies() == []
    _send(
        bridge.store,
        queued["task_id"],
        "[OPENCODE -> ROOM]\nPRESENCE_PROOF\nSTATUS: PASS",
        "rep-1",
    )
    replies = bridge.drain_replies()
    assert len(replies) == 1
    assert replies[0]["message_id"] == "rep-1"
    bridge.mark_imported("rep-1")
    assert bridge.drain_replies() == []


def test_duplicate_reply_send_is_rejected_by_relay(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    bridge.enqueue("alex", "msg", task_id="T-D")
    _send(bridge.store, "T-D", "resposta", "dup-1")
    with pytest.raises(RelayError, match="Duplicate message_id"):
        _send(bridge.store, "T-D", "resposta", "dup-1")
    assert len(bridge.store.outbox_records()) == 1


def test_blocker_surfaces_as_explicit_error_type(tmp_path):
    bridge = OpenCodeBridge(tmp_path)
    bridge.enqueue("alex", "execute algo", task_id="T-B")
    _send(bridge.store, "T-B", "BLOCKER: gateway offline", "blk-1", rtype="BLOCKER")
    replies = bridge.drain_replies()
    assert len(replies) == 1
    assert replies[0]["type"] == "BLOCKER"
    assert "gateway offline" in replies[0]["content"]


def test_bridge_never_writes_outside_store_dir(tmp_path):
    store_dir = tmp_path / "store"
    bridge = OpenCodeBridge(store_dir)
    before = {p.name for p in tmp_path.iterdir()}
    bridge.enqueue("alex", "msg")
    _send(bridge.store, "LAB-1", "ok", "m-1")
    bridge.drain_replies()
    bridge.mark_imported("m-1")
    assert {p.name for p in tmp_path.iterdir()} == before | {"store"}
    for path in store_dir.rglob("*"):
        assert path.relative_to(store_dir)  # every artifact lives under store_dir


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr("core.lab_worker_runtime.data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr("core.lab_coordinator.data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr("tools.room_relay.lab_bridge.DEFAULT_STORE", tmp_path / "relay")
    return tmp_path


@pytest.mark.asyncio
async def test_lab_send_opencode_queues_and_reply_returns_to_lab(lab_env):
    from core.lab_coordinator import LabCoordinator

    coordinator = LabCoordinator()
    result = await coordinator.send_message("alex", "zara", "@OPENCODE PRESENCE_PROOF")
    assert result["state"] == "QUEUED"
    assert result["authorization"] == "READ_ONLY"

    _send(
        coordinator.opencode_bridge.store,
        result["task_id"],
        "[OPENCODE -> ROOM]\nPRESENCE_PROOF\nSTATUS: PASS",
        "r-" + uuid.uuid4().hex,
    )

    state = await coordinator.get_state()
    replies = [m for m in state["messages"] if m["author"] == "opencode"]
    assert len(replies) == 1
    assert "PRESENCE_PROOF" in replies[0]["content"]
    assert replies[0]["kind"] == "agent"

    state2 = await coordinator.get_state()
    replies2 = [m for m in state2["messages"] if m["author"] == "opencode"]
    assert len(replies2) == 1


@pytest.mark.asyncio
async def test_lab_other_targets_are_not_routed_to_opencode(lab_env):
    from core.lab_coordinator import LabCoordinator

    coordinator = LabCoordinator()
    result = await coordinator.send_message("alex", "mentor", "@MENTOR teste")
    assert result["state"] == "QUEUED"
    assert coordinator.opencode_bridge.store.inbox_records() == []
    assert len(list(coordinator.mentor_relay.outbox.glob("MR-*.json"))) == 1


@pytest.mark.asyncio
async def test_lab_opencode_failure_surfaces_as_explicit_error(lab_env, monkeypatch):
    from core.lab_coordinator import LabCoordinator

    coordinator = LabCoordinator()

    def broken_enqueue(*args, **kwargs):
        raise RelayError("relay store corrupt")

    monkeypatch.setattr(coordinator.opencode_bridge, "enqueue", broken_enqueue)
    result = await coordinator.send_message("alex", "opencode", "tarefa que falha")
    assert result["state"] == "ERROR"
    assert "relay store corrupt" in result["response"]
    state = await coordinator.get_state()
    errors = [m for m in state["messages"] if m["kind"] == "status" and "relay store corrupt" in m["content"]]
    assert len(errors) == 1


@pytest.mark.asyncio
async def test_lab_read_only_never_alters_functional_files(lab_env):
    from core.lab_coordinator import LabCoordinator

    root = Path(__file__).resolve().parents[1]
    functional = sorted(
        p for p in root.joinpath("core").rglob("*.py") if p.stat().st_mtime_ns > 0
    )
    before = {p: p.stat().st_mtime_ns for p in functional}

    coordinator = LabCoordinator()
    result = await coordinator.send_message("alex", "opencode", "@OPENCODE PRESENCE_PROOF")
    assert result["authorization"] == "READ_ONLY"
    await coordinator.get_state()

    after = {p: p.stat().st_mtime_ns for p in functional}
    assert before == after
