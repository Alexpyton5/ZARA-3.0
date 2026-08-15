from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from core import operational_recall
from core.ipc_handlers import IPCHandler


class _UserMemory:
    def list(self):
        return [
            {"fact": "Alex prefere respostas diretas", "status": "confirmed"},
            {"fact": "fato esquecido", "status": "forgotten"},
        ]


class _ProjectMemory:
    def list_docs(self):
        return ["architecture", "state", "roadmap"]


def test_current_work_and_pending_use_live_catalog_rows(monkeypatch):
    monkeypatch.setattr(
        operational_recall,
        "_catalog_rows",
        lambda: [
            ("Volume", "RUNTIME_AUTOMATED_PASS"),
            ("Nova guia", "READY_NOT_PROVEN"),
        ],
    )

    current = operational_recall.recall_operational_memory("O que estávamos fazendo?")
    pending = operational_recall.recall_operational_memory("O que ficou pendente?")

    assert "Volume" in current
    assert "Nova guia: READY_NOT_PROVEN" in pending


def test_user_and_project_memory_have_bounded_natural_answers():
    user = operational_recall.recall_operational_memory(
        "O que você lembra sobre mim?", user_memory=_UserMemory()
    )
    project = operational_recall.recall_operational_memory(
        "Liste a Project Memory", project_memory=_ProjectMemory()
    )

    assert user == "Na User Memory local: Alex prefere respostas diretas."
    assert project == "Documentos da Project Memory: architecture, state, roadmap."


def test_caderninho_returns_only_numbered_idea_headings(monkeypatch):
    monkeypatch.setattr(
        operational_recall,
        "_read_text",
        lambda path, max_chars=80_000: "# Caderno\n### 1. Ideia A\ntexto\n### 2. Ideia B\n",
    )

    reply = operational_recall.recall_operational_memory("O que tem no caderninho?")

    assert reply == "Ideias registradas no Caderninho: Ideia A; Ideia B."


@pytest.mark.asyncio
async def test_handler_reads_operational_memory_without_model():
    handler = IPCHandler(AsyncMock())
    handler.user_memory = _UserMemory()

    reply = await handler._try_operational_memory_intent("O que você lembra sobre mim?")

    assert reply == "Na User Memory local: Alex prefere respostas diretas."


def test_text_and_voice_share_operational_memory_path():
    assert "_try_operational_memory_intent" in inspect.getsource(IPCHandler.handle_send_message)
    assert "_try_operational_memory_intent" in inspect.getsource(IPCHandler._process_voice_message)
