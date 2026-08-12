"""Persistence and privacy-boundary tests for the Home conversation log."""

from __future__ import annotations

from pathlib import Path
from time import time

import pytest

import core.ipc_handlers as ipc_handlers
from core.conversation_history import MAX_CONTENT_CHARS, ConversationHistory
from core.ipc_handlers import IPCHandler, IPCMessage


def test_history_survives_store_restart_and_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    first = ConversationHistory(path)
    now_ms = int(time() * 1000)
    first.append("user", "Olá, ZARA — amanhã às 8h", engine="auto_smart", timestamp=now_ms)
    first.append("assistant", "Combinado, Alex!", engine="gemini", timestamp=now_ms + 1)

    messages = ConversationHistory(path).list_recent()

    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "Olá, ZARA — amanhã às 8h"),
        ("assistant", "Combinado, Alex!"),
    ]
    assert messages[0]["timestamp"] == now_ms
    assert all(item["id"] for item in messages)


def test_history_is_bounded_and_normalizes_untrusted_fields(tmp_path: Path) -> None:
    store = ConversationHistory(tmp_path / "history.sqlite3", max_messages=3)
    now_ms = int(time() * 1000)
    for index in range(5):
        store.append(
            "user", f"message {index}\x00", engine="x" * 100, timestamp=now_ms + index
        )

    messages = store.list_recent(limit=50)

    assert [item["content"] for item in messages] == ["message 2", "message 3", "message 4"]
    assert all(len(item["engine"]) == 64 for item in messages)
    assert store.append("assistant", "y" * (MAX_CONTENT_CHARS + 20))["content"] == (
        "y" * MAX_CONTENT_CHARS
    )
    with pytest.raises(ValueError, match="role"):
        store.append("admin", "not allowed")
    with pytest.raises(ValueError, match="empty"):
        store.append("user", "\x00  ")


def test_clear_physically_removes_transcript_database(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    store = ConversationHistory(path)
    store.append("user", "private message")

    assert store.clear() == 1
    assert not path.exists()
    assert not Path(f"{path}-wal").exists()
    assert not Path(f"{path}-shm").exists()
    assert store.list_recent() == []


def test_ipc_constructor_initializes_home_history_that_survives_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "history.sqlite3"
    monkeypatch.setattr(ipc_handlers, "ConversationHistory", lambda: ConversationHistory(path))

    async def send(_: IPCMessage) -> None:
        pass

    first = IPCHandler(send)
    assert first.conversation_history is not None
    first.conversation_history.append("user", "available before initialize")

    restarted = IPCHandler(send)
    assert restarted.conversation_history is not None
    messages = restarted.conversation_history.list_recent()
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "available before initialize"),
    ]


@pytest.mark.asyncio
async def test_history_ipc_lists_and_clears_real_store(tmp_path: Path) -> None:
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    handler = IPCHandler(send)
    handler.conversation_history = ConversationHistory(tmp_path / "history.sqlite3")
    handler.conversation_history.append("user", "persisted")

    await handler.handle_message(
        IPCMessage(type="conversation-history-list", request_id="list", payload={"limit": 10})
    )
    assert sent[-1].request_id == "list"
    assert sent[-1].response["messages"][0]["content"] == "persisted"

    await handler.handle_message(
        IPCMessage(type="conversation-history-clear", request_id="clear")
    )
    assert sent[-1].response == {"success": True, "deleted": 1}
    assert handler.conversation_history.list_recent() == []


@pytest.mark.asyncio
async def test_text_chat_persists_user_and_assistant_as_separate_ui_history(
    tmp_path: Path,
) -> None:
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    class Orchestrator:
        last_engine_used = "fake_engine"

        async def process_message(self, text: str, engine: str, history=None) -> str:
            assert history == [
                {"role": "user", "content": "previous question"},
                {"role": "assistant", "content": "previous answer"},
            ]
            assert text == "Como está o projeto?"
            assert engine == "auto_smart"
            return "Tudo certo, Alex."

    path = tmp_path / "history.sqlite3"
    handler = IPCHandler(send)
    handler.conversation_history = ConversationHistory(path)
    handler.orchestrator = Orchestrator()  # type: ignore[assignment]

    await handler.handle_send_message(
        IPCMessage(
            type="send-message",
            request_id="chat",
            payload={
                "message": "Como está o projeto?",
                "engine": "auto_smart",
                "history": [
                    {"role": "user", "content": "previous question"},
                    {"role": "assistant", "content": "previous answer"},
                ],
            },
        )
    )

    assert sent[-1].response["response"] == "Tudo certo, Alex."
    restarted = ConversationHistory(path)
    assert [(item["role"], item["content"]) for item in restarted.list_recent()] == [
        ("user", "Como está o projeto?"),
        ("assistant", "Tudo certo, Alex."),
    ]
