"""FASE 2 PECA 6 (28/09/2026): o loop do "cerebro pesado" sobrevive ao restart.

A PECA 4 fechou o loop em memoria: pergunta sai, resposta volta no
proximo turno da mesma (sessao, tarefa). Mas o _pending do leitor e em
memoria — um restart do backend entre a pergunta e a resposta (ou entre
a resposta e o consumo) deixava a escalacao orfa: a RESPOSTA-ZOE ficava
na caixinha e ninguem a lia. Esta peca prova:

- ask_zoe grava cabecalho legivel por maquina (sessao:/tarefa:);
- restore_from_inbox() re-registra as pendentes na subida;
- a entrega arquiva o par em entregues/ (nunca entrega duas vezes);
- o runtime realimenta _zoe_escalated no restore (sem pergunta duplicada
  para a mesma tarefa depois do restart).
"""
from __future__ import annotations

import pytest

from core.lab_v1.zoe_answer_reader import ARCHIVE_DIRNAME, ZoeAnswerReader
from core.lab_v1.zoe_brain import ask_zoe


def write_answer(inbox, qid: str, text: str):
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"RESPOSTA-ZOE-{qid}.md").write_text(text, encoding="utf-8")


def question_files(inbox):
    return sorted(inbox.glob("PERGUNTA-ZOE-*.md")) if inbox.exists() else []


# --- ask_zoe: cabecalho de roteamento -----------------------------------

def test_ask_zoe_writes_routing_headers(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    qid = ask_zoe("como migro?", session_id="sess-1", task_id="task-9")
    texto = (inbox / f"PERGUNTA-ZOE-{qid}.md").read_text(encoding="utf-8")
    assert "sessao: sess-1" in texto
    assert "tarefa: task-9" in texto
    assert "como migro?" in texto  # a pergunta continua legivel


def test_ask_zoe_without_ids_has_no_routing_headers(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    qid = ask_zoe("pergunta antiga")
    texto = (inbox / f"PERGUNTA-ZOE-{qid}.md").read_text(encoding="utf-8")
    assert "sessao:" not in texto
    assert "tarefa:" not in texto


def test_ask_zoe_task_none_writes_dash(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    qid = ask_zoe("turno avulso", session_id="sess-1", task_id=None)
    texto = (inbox / f"PERGUNTA-ZOE-{qid}.md").read_text(encoding="utf-8")
    assert "sessao: sess-1" in texto
    assert "tarefa: -" in texto


# --- restore_from_inbox -------------------------------------------------

def test_restore_rehydrates_pending_question(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    qid = ask_zoe("ajuda aqui", session_id="s1", task_id="t1")

    # "Restart": leitor novo, memoria vazia.
    leitor2 = ZoeAnswerReader()
    restauradas = leitor2.restore_from_inbox()
    assert restauradas == [("s1", "t1")]
    assert leitor2.pending() == [qid]

    # A resposta chega depois do restart e e entregue normalmente.
    write_answer(inbox, qid, "faca em duas etapas")
    got = leitor2.take_for("s1", "t1")
    assert got is not None and got[0] == qid
    assert "duas etapas" in got[1]


def test_restore_rehydrates_answered_but_unconsumed(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    qid = ask_zoe("ajuda", session_id="s1", task_id="t1")
    write_answer(inbox, qid, "resposta que ninguem consumiu")

    leitor2 = ZoeAnswerReader()
    assert leitor2.restore_from_inbox() == [("s1", "t1")]
    got = leitor2.take_for("s1", "t1")
    assert got is not None and got[0] == qid


def test_restore_skips_old_format_without_headers(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    (inbox / "PERGUNTA-ZOE-123-45.md").write_text(
        "[ZOE-BRAIN] formato antigo\nid: 123-45\nde: lab\n", encoding="utf-8")
    leitor = ZoeAnswerReader()
    assert leitor.restore_from_inbox() == []
    assert leitor.pending() == []  # nunca adivinha


def test_restore_skips_inconsistent_file(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    # id do cabecalho diverge do nome do arquivo: arquivo estranho, ignora.
    (inbox / "PERGUNTA-ZOE-111.md").write_text(
        "id: 222\nsessao: s1\ntarefa: t1\n", encoding="utf-8")
    # sem sessao: ignora.
    (inbox / "PERGUNTA-ZOE-333.md").write_text(
        "id: 333\ntarefa: t1\n", encoding="utf-8")
    leitor = ZoeAnswerReader()
    assert leitor.restore_from_inbox() == []
    assert leitor.pending() == []


def test_restore_is_idempotent(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    ask_zoe("ajuda", session_id="s1", task_id="t1")
    leitor = ZoeAnswerReader()
    assert leitor.restore_from_inbox() == [("s1", "t1")]
    assert leitor.restore_from_inbox() == []  # segunda vez: nada novo
    assert len(leitor.pending()) == 1


def test_restore_empty_or_missing_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(tmp_path / "nao-existe"))
    assert ZoeAnswerReader().restore_from_inbox() == []
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert ZoeAnswerReader().restore_from_inbox(vazia) == []


# --- entrega arquiva o par (nunca duas vezes) ----------------------------

def test_take_for_archives_pair_on_delivery(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    leitor = ZoeAnswerReader()
    assert leitor.register("123-45", session_id="s1", task_id="t1")
    (inbox / "PERGUNTA-ZOE-123-45.md").write_text(
        "id: 123-45\nsessao: s1\ntarefa: t1\n", encoding="utf-8")
    write_answer(inbox, "123-45", "resposta final")

    got = leitor.take_for("s1", "t1")
    assert got is not None and got[0] == "123-45"

    # Par saiu da pasta principal: casa limpa.
    assert question_files(inbox) == []
    assert not (inbox / "RESPOSTA-ZOE-123-45.md").exists()
    arquivados = sorted((inbox / ARCHIVE_DIRNAME).glob("*.md"))
    assert [p.name for p in arquivados] == [
        "PERGUNTA-ZOE-123-45.md", "RESPOSTA-ZOE-123-45.md"]

    # Restore futuro nao re-registra: nunca entrega duas vezes.
    leitor2 = ZoeAnswerReader()
    assert leitor2.restore_from_inbox() == []
    assert leitor2.take_for("s1", "t1") is None
    eventos = [e["evento"] for e in leitor.journal()]
    assert eventos == ["registrar", "entregar", "arquivar"]


def test_archive_failure_still_delivers(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    # Sabota o arquivamento: um ARQUIVO no lugar da pasta "entregues".
    (inbox / ARCHIVE_DIRNAME).write_text("bloqueio", encoding="utf-8")
    leitor = ZoeAnswerReader()
    assert leitor.register("999", session_id="s1", task_id="t1")
    (inbox / "PERGUNTA-ZOE-999.md").write_text(
        "id: 999\nsessao: s1\ntarefa: t1\n", encoding="utf-8")
    write_answer(inbox, "999", "resposta")

    got = leitor.take_for("s1", "t1")  # entrega acontece mesmo assim
    assert got is not None and got[0] == "999"
    eventos = [e["evento"] for e in leitor.journal()]
    assert "arquivar_falhou" in eventos


# --- o runtime realimenta _zoe_escalated no restore ----------------------
# (precisa da arvore completa do app: pula no teste local, roda no PC)

def test_runtime_restore_feeds_zoe_escalated(tmp_path, monkeypatch):
    try:
        from core.lab_v1.domain import (
            AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName,
            Session, Task, Team,
        )
        from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
        from core.lab_v1.providers.registry import ProviderRegistry
        from core.lab_v1.runtime import LabRuntime
        from core.lab_v1.store import LabStore
        from core.lab_v1.zoe_brain import QUESTION_PREFIX
    except ImportError:
        pytest.skip("precisa da arvore completa do app (roda no PC)")

    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))

    class Broken(ProviderAdapter):
        id = "broken"
        label = "broken"
        declared_models = (ModelDescriptor("broken", "broken/m1", "broken/m1"),)

        def probe(self):
            return ProviderInfo(self.id, self.label, self.id,
                                Availability.AVAILABLE)

        def complete(self, *, prompt, model, **kwargs):
            return ProviderResult(False, availability=Availability.ERROR,
                                  error="quebrou")

    tmp_path.mkdir(parents=True, exist_ok=True)
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    team = Team("team", "Brain")
    store.save_team(team)
    session = Session("session", team.id, "Brain")
    store.save_session(session)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1",
                         role=RoleName.CEO)
    store.save_agent(agent)
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(Broken())

    rt1 = LabRuntime(store, registry)
    task = Task("task1", session.id, "Migrar", "Migre X.", "agent")
    run1, res1 = rt1._run_agent(session, agent, "prompt", "sys", task,
                               timeout_s=3)
    assert not res1.ok
    arquivos = sorted(inbox.glob(f"{QUESTION_PREFIX}*.md"))
    assert len(arquivos) == 1  # a pergunta saiu com cabecalho
    texto = arquivos[0].read_text(encoding="utf-8")
    assert "sessao: session" in texto and "tarefa: task1" in texto

    # "Restart": runtime novo re-registra e NAO pergunta de novo.
    rt2 = LabRuntime(store, registry)
    assert ("session", "task1") in rt2._zoe_escalated
    assert len(rt2._zoe_answers.pending()) == 1

    # A zoe responde; o proximo turno entrega a resposta no prompt.
    qid = arquivos[0].stem[len(QUESTION_PREFIX):]
    write_answer(inbox, qid, "Dica da zoe pos-restart.")
    prompts = []
    original_complete = Broken.complete

    def spy(self, *, prompt, model, **kwargs):
        prompts.append(prompt)
        return original_complete(self, prompt=prompt, model=model, **kwargs)

    monkeypatch.setattr(Broken, "complete", spy)
    rt2._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)
    assert prompts and "Dica da zoe pos-restart." in prompts[-1]
    # E a pergunta nao foi duplicada: continua existindo uma so (arquivada).
    total = list(inbox.glob(f"{QUESTION_PREFIX}*.md")) + list(
        (inbox / ARCHIVE_DIRNAME).glob(f"{QUESTION_PREFIX}*.md"))
    assert len(total) == 1
