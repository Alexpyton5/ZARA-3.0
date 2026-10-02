import asyncio
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage, _run_windows_ipc
from memory.project_memory import ProjectMemory


def exchange(**changes):
    return dict(event_id="turn-83e495c7", provider="muse", channel="voice",
                user_id="user-one", assistant_id="reply-one", user_text="Planeje a entrega azul",
                assistant_text="Vou preparar uma proposta.", **changes)


def memory(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=vault), vault


def test_confirmed_exchange_is_recoverable_after_restart_and_retry(tmp_path):
    pm, vault = memory(tmp_path)
    name = pm.record_pilot_turn(exchange())
    restarted = ProjectMemory(base_dir=tmp_path / "other-profile", obsidian_vault_dir=vault)
    assert restarted.record_pilot_turn(exchange()) == name
    files = list((vault / "conversas").glob("*.md"))
    assert len(files) == 1
    note = files[0].read_text(encoding="utf-8")
    assert "Planeje a entrega azul" in note and "Vou preparar uma proposta." in note
    assert "referencia" in note and "nao" in note and "autorizacao" in note
    assert note.endswith("[[INDICE]]\n")


def test_conflicting_retry_cannot_replace_previous_note(tmp_path):
    pm, vault = memory(tmp_path)
    name = pm.record_pilot_turn(exchange())
    note = vault / "conversas" / name
    original = note.read_bytes()
    altered = exchange()
    altered["assistant_text"] = "Outra resposta."
    assert pm.record_pilot_turn(altered) is None
    assert note.read_bytes() == original


def test_simultaneous_profiles_publish_only_one_complete_note(tmp_path):
    pm, vault = memory(tmp_path)
    other = ProjectMemory(base_dir=tmp_path / "other-profile", obsidian_vault_dir=vault)
    with ThreadPoolExecutor(max_workers=2) as pool:
        names = list(pool.map(lambda owner: owner.record_pilot_turn(exchange()), [pm, other]))
    assert names[0] and names[0] == names[1]
    assert len(list((vault / "conversas").glob("*.md"))) == 1
    assert not list((vault / "conversas").glob("*.tmp"))


def test_archive_is_queryable_as_reference_and_distinct_submissions_are_not_deduped_by_text(tmp_path):
    from memory.shared_second_brain import SharedSecondBrain
    pm, vault = memory(tmp_path)
    one = pm.record_pilot_turn(exchange())
    other = exchange()
    other["event_id"] = "turn-distinct"
    two = pm.record_pilot_turn(other)
    assert one and two and one != two
    brain = SharedSecondBrain(user_memory=None, lab_store=None, project_workspace=None,
                              obsidian_vault=vault, obsidian_index_db=tmp_path / "index.db")
    result = brain.query("entrega azul")
    assert any("conversas/" in str(item.get("provenance", "")) for item in result["items"])


def test_multiline_windows_text_remains_quoted_and_idempotent(tmp_path):
    pm, vault = memory(tmp_path)
    event = exchange()
    event["assistant_text"] = "Primeira linha.\r\n# Dado citado\r\nOutra linha."
    name = pm.record_pilot_turn(event)
    assert name and pm.record_pilot_turn(event) == name
    assert "> # Dado citado" in (vault / "conversas" / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("private_text", ["Minha senha é Exemplo123", "Meu PIN é 1234", "Dados bancários do teste fictício"])
def test_automatic_capture_rejects_natural_language_credentials(tmp_path, private_text):
    pm, vault = memory(tmp_path)
    event = exchange()
    event["user_text"] = private_text
    assert pm.record_pilot_turn(event) is None
    assert not list(vault.rglob("*.md"))


@pytest.mark.asyncio
async def test_slow_memory_write_cannot_hold_voice_stop_in_windows_queue(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    handled = []

    class SlowMemoryHandler:
        async def handle_message(self, message):
            if message.type == "shared-brain-learn":
                started.set()
                await release.wait()
            else:
                await started.wait()
                handled.append(message.type)
                release.set()

    frames = [json.dumps({"type": kind, "request_id": kind}) for kind in ("shared-brain-learn", "voice-stop")]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(frames) + "\n"))
    await asyncio.wait_for(_run_windows_ipc(SlowMemoryHandler()), timeout=0.3)
    assert handled == ["voice-stop"]


@pytest.mark.parametrize("field,value", [
    ("event_id", "../outside"), ("event_id", "Bearer private-example"),
    ("provider", "unverified"), ("channel", "whatsapp"), ("user_id", ""),
    ("assistant_id", ""), ("user_text", "senha: private-example"),
    ("assistant_text", "Resposta segura. " * 100 + "sk-1234567890abcdef"),
    ("assistant_text", "x" * 16001),
], ids=["path", "private-id", "provider", "channel", "empty-user", "empty-reply", "private-user", "private-reply", "oversize"])
def test_invalid_or_private_exchange_writes_nothing(tmp_path, field, value):
    pm, vault = memory(tmp_path)
    event = exchange()
    event[field] = value
    assert pm.record_pilot_turn(event) is None
    assert not list(vault.rglob("*.md"))


def test_offline_vault_is_not_created_or_reported_saved(tmp_path):
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=tmp_path / "offline")
    assert pm.record_pilot_turn(exchange()) is None
    assert not (tmp_path / "offline").exists()


def test_ipc_structured_exchange_uses_real_writer_and_reports_receipt(tmp_path):
    pm, vault = memory(tmp_path)
    handler = object.__new__(IPCHandler)
    handler.project_memory = pm
    sent = []

    async def send(message):
        sent.append(message)

    handler.send = send
    asyncio.run(handler.handle_shared_brain_learn(IPCMessage(
        type="shared-brain-learn", request_id="memory-one", payload={"turn": exchange()})))
    assert sent[0].response["success"] is True
    assert (vault / "conversas" / sent[0].response["path"]).exists()


def test_ipc_rejects_structured_private_data(tmp_path):
    pm, vault = memory(tmp_path)
    handler = object.__new__(IPCHandler)
    handler.project_memory = pm
    sent = []

    async def send(message):
        sent.append(message)

    handler.send = send
    event = exchange()
    event["assistant_text"] = "hidden reasoning: private example"
    asyncio.run(handler.handle_shared_brain_learn(IPCMessage(
        type="shared-brain-learn", request_id="memory-private", payload={"turn": event})))
    assert sent[0].error and (not sent[0].response or sent[0].response.get("success") is not True)
    assert not list(vault.rglob("*.md"))
