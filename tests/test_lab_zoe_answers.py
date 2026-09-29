"""FASE 2 PECA 4 (28/09/2026): o outro lado do loop do "cerebro pesado".

A PECA 2 escreve a PERGUNTA-ZOE na caixinha quando a escada esgota; a zoe
responde com RESPOSTA-ZOE-<id>.md. Esta peca prova que a resposta volta
para o Lab: no proximo turno da mesma (sessao, tarefa), ela entra no
prompt do agente como contexto — uma vez so, sem mascara, sem explodir.
"""
from __future__ import annotations

from core.lab_v1.domain import (
    AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, RunState,
    Session, Task, Team,
)
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.zoe_answer_reader import ZoeAnswerReader


class AnswerFixture(ProviderAdapter):
    label = "Answer fixture"

    def __init__(self, provider_id: str, models: tuple[str, ...], *, succeed: bool = True):
        self.id = provider_id
        self.declared_models = tuple(ModelDescriptor(provider_id, m, m) for m in models)
        self.succeed = succeed
        self.prompts: list[str] = []

    def probe(self):
        return ProviderInfo(self.id, self.label, self.id, Availability.AVAILABLE)

    def complete(self, *, prompt, model, **kwargs):
        self.prompts.append(prompt)
        if not self.succeed:
            return ProviderResult(False, availability=Availability.ERROR, error="fixture failure")
        return ProviderResult(True, text="OK", availability=Availability.AVAILABLE,
                              model_reported=model)


def setup_runtime(tmp_path, agent: AgentProfile, adapters: list[AnswerFixture]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    team = Team("team", "Brain")
    store.save_team(team)
    session = Session("session", team.id, "Brain")
    store.save_session(session)
    store.save_agent(agent)
    registry = ProviderRegistry(tmp_path / "health.json")
    for adapter in adapters:
        registry.register(adapter)
    return LabRuntime(store, registry), session


def make_task(session: Session, task_id: str = "task1") -> Task:
    return Task(task_id, session.id, "Migrar o relatorio", "Migre o relatorio X para Y.", "agent")


def question_files(inbox) -> list:
    return sorted(inbox.glob("PERGUNTA-ZOE-*.md")) if inbox.exists() else []


def write_answer(inbox, qid: str, text: str):
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"RESPOSTA-ZOE-{qid}.md").write_text(text, encoding="utf-8")


# --- o leitor sozinho ---------------------------------------------------

def test_reader_returns_none_before_answer(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader()
    assert reader.register("123-45", session_id="s1", task_id="t1", agent_id="a1") is True
    assert reader.take_for("s1", "t1") is None
    assert reader.pending() == ["123-45"]  # nao consumiu


def test_reader_delivers_answer_exactly_once(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader()
    reader.register("123-45", session_id="s1", task_id="t1", agent_id="a1")
    write_answer(inbox, "123-45", "Tente migrar em duas etapas: extrair, depois formatar.")

    got = reader.take_for("s1", "t1")
    assert got is not None
    qid, answer = got
    assert qid == "123-45"
    assert "duas etapas" in answer
    assert reader.take_for("s1", "t1") is None  # consumida: segunda vez = None
    assert reader.pending() == []
    assert reader.delivered() == ["123-45"]


def test_reader_scopes_to_same_session_and_task(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader()
    reader.register("111", session_id="s1", task_id="t1", agent_id="a1")
    reader.register("222", session_id="s1", task_id="t2", agent_id="a1")
    write_answer(inbox, "111", "resposta da tarefa 1")

    assert reader.take_for("s1", "t2") is None  # tarefa errada: nada
    assert reader.take_for("s2", "t1") is None  # sessao errada: nada
    got = reader.take_for("s1", "t1")
    assert got is not None and got[0] == "111"
    assert reader.pending() == ["222"]  # a outra continua pendente


def test_reader_rejects_bad_qid():
    reader = ZoeAnswerReader()
    assert reader.register("", session_id="s1") is False
    assert reader.register(None, session_id="s1") is False
    assert reader.register("abc", session_id="s1") is False  # sem digito: invalido
    assert reader.register("123", session_id="") is False  # sem sessao: invalido
    assert reader.pending() == []


def test_reader_duplicate_register_is_noop():
    reader = ZoeAnswerReader()
    assert reader.register("123", session_id="s1", task_id="t1") is True
    assert reader.register("123", session_id="s1", task_id="t1") is False
    assert reader.pending() == ["123"]


def test_reader_unreadable_answer_does_not_explode(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader()
    reader.register("999", session_id="s1", task_id="t1")
    # Resposta "ilegivel": uma pasta no lugar do arquivo (OSError na leitura).
    (inbox / "RESPOSTA-ZOE-999.md").mkdir()
    assert reader.take_for("s1", "t1") is None
    assert reader.pending() == ["999"]  # nao consumiu


def test_reader_caps_giant_answer(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader()
    reader.register("777", session_id="s1", task_id="t1")
    write_answer(inbox, "777", "x" * 9000)
    got = reader.take_for("s1", "t1")
    assert got is not None
    assert len(got[1]) < 9000
    assert "cortada" in got[1]


def test_reader_journal_is_auditable(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    reader = ZoeAnswerReader(clock=lambda: "AGORA")
    reader.register("123", session_id="s1", task_id="t1")
    write_answer(inbox, "123", "ok")
    reader.take_for("s1", "t1")
    eventos = [e["evento"] for e in reader.journal()]
    assert eventos == ["registrar", "entregar", "arquivar"]  # PECA 6: entrega arquiva o par
    assert all(e["ts"] == "AGORA" for e in reader.journal())


# --- o loop fechado no runtime ------------------------------------------

def test_run_agent_injects_zoe_answer_into_next_turn_prompt(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    broken = AnswerFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])
    task = make_task(session)

    # Turno 1: escada esgota -> pergunta para a zoe na caixinha.
    run1, result1 = runtime._run_agent(session, agent, "prompt original", "sys", task, timeout_s=3)
    assert not result1.ok and run1.state is RunState.FAILED
    files = question_files(inbox)
    assert len(files) == 1
    qid = files[0].stem[len("PERGUNTA-ZOE-"):]

    # A zoe responde no turno vanguarda.
    write_answer(inbox, qid, "Dica da zoe: migre em duas etapas.")

    # Turno 2: a resposta entra no prompt do agente (ainda falha no motor,
    # mas NAO cria segunda pergunta — uma por tarefa).
    broken.prompts.clear()
    run2, result2 = runtime._run_agent(session, agent, "prompt original", "sys", task, timeout_s=3)
    assert not result2.ok and run2.state is RunState.FAILED
    # FASE 2 PECA 6: o par pergunta+resposta entregue foi arquivado em
    # entregues/ (casa limpa) — nenhuma pergunta duplicada foi criada.
    assert question_files(inbox) == []
    arquivadas = sorted((inbox / "entregues").glob("PERGUNTA-ZOE-*.md"))
    assert len(arquivadas) == 1
    assert broken.prompts, "o motor deveria ter sido chamado"
    assert "Dica da zoe: migre em duas etapas." in broken.prompts[-1]
    assert "prompt original" in broken.prompts[-1]  # o prompt original continua la

    # Turno 3: resposta ja foi consumida — o prompt volta ao normal.
    broken.prompts.clear()
    runtime._run_agent(session, agent, "prompt original", "sys", task, timeout_s=3)
    assert "Dica da zoe" not in broken.prompts[-1]


def test_answer_never_masks_failure(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    broken = AnswerFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])
    task = make_task(session)

    runtime._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)
    qid = question_files(inbox)[0].stem[len("PERGUNTA-ZOE-"):]
    write_answer(inbox, qid, "resposta da zoe")

    run, result = runtime._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)
    # A resposta e contexto, nao mascara: a falha do motor continua valendo.
    assert not result.ok and run.state is RunState.FAILED
    assert result.error == "fixture failure"
