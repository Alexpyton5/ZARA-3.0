"""Regression tests for reminders crossing the Python/Electron boundary."""

import asyncio
import json
import time

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage, serialize_ipc_message
from core.reminder_engine import ReminderEngine


def _handler() -> tuple[IPCHandler, list[IPCMessage]]:
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    return IPCHandler(send), sent


@pytest.mark.asyncio
async def test_text_reminder_is_created_once_and_confirmation_is_not_duplicated(tmp_path):
    handler, sent = _handler()
    handler.reminder_engine = ReminderEngine(db_path=tmp_path / "reminders.db")

    await handler.handle_send_message(
        IPCMessage(
            type="send-message",
            request_id="req-1",
            payload={"message": "Zara, me lembre de comprar pão daqui a 2 minutos"},
        )
    )

    reminders = handler.reminder_engine.list()
    assert len(reminders) == 1
    assert reminders[0].message == "comprar pão"
    assert [message.type for message in sent] == ["reminder-created", "response"]
    assert sent[0].data == {
        "id": reminders[0].id,
        "text": "comprar pão",
        "due_at": reminders[0].due_at_utc,
        "state": "SCHEDULED",
    }
    assert sent[1].response["response"].startswith("Certo. Vou te lembrar de comprar pão")


@pytest.mark.asyncio
async def test_manual_reminder_uses_public_ipc_field_names(tmp_path):
    handler, sent = _handler()
    handler.reminder_engine = ReminderEngine(db_path=tmp_path / "reminders.db")
    due_at = time.time() + 60

    await handler.handle_reminder_create(
        IPCMessage(
            type="reminder-create",
            request_id="req-2",
            payload={"text": "revisar validação", "due_at": due_at, "timezone": "local"},
        )
    )

    assert [message.type for message in sent] == ["response", "reminder-created"]
    assert sent[0].response["text"] == "revisar validação"
    assert sent[0].response["due_at"] == due_at
    assert sent[1].data["text"] == "revisar validação"


@pytest.mark.asyncio
async def test_scheduler_thread_delivers_fired_event_once(tmp_path):
    delivered = asyncio.Event()
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)
        if message.type == "reminder-fired":
            delivered.set()

    handler = IPCHandler(send)
    handler._event_loop = asyncio.get_running_loop()
    engine = ReminderEngine(
        db_path=tmp_path / "reminders.db",
        on_fire=handler._schedule_reminder_fire,
    )
    reminder = engine.create("beber água", time.time() - 1)

    fired_count = await asyncio.to_thread(engine.fire_due_now)
    await asyncio.wait_for(delivered.wait(), timeout=1)

    fired_events = [message for message in sent if message.type == "reminder-fired"]
    assert fired_count == 1
    assert len(fired_events) == 1
    assert fired_events[0].data["id"] == reminder.id
    assert fired_events[0].data["text"] == "beber água"
    assert engine.get(reminder.id).state == "FIRED"


def test_ipc_serialization_round_trips_portuguese_without_mojibake():
    original = "Olá ZARA, validação, informação, você está funcionando?"
    frame = serialize_ipc_message(
        IPCMessage(type="reminder-fired", data={"text": original})
    )

    assert json.loads(frame.encode("utf-8").decode("utf-8"))["data"]["text"] == original
    assert "Ã" not in frame
