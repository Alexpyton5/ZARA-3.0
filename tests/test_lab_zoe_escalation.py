"""FASE 2 PECA 2 (28/09/2026): rota "cerebro pesado" plugada no turno.

Quando a escada esgota (nenhum motor conseguiu rodar a missao), o turno
deixa uma PERGUNTA-ZOE-<id>.md na caixinha em vez de so falhar em
silencio — a zoe responde no turno vanguarda com RESPOSTA-ZOE-<id>.md
(zoe_brain.read_zoe_answer le de volta). Regras:

- a Run continua FAILED com o erro ORIGINAL (nada mascarado);
- uma pergunta por tarefa (a mesma missao falhando de novo nao enche
  a caixinha de perguntas repetidas);
- mismatch (hard-stop de integridade) NAO escala;
- sucesso NAO escala;
- caixinha inacessivel NAO muda o resultado do turno.
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


class BrainFixture(ProviderAdapter):
    label = "Brain fixture"

    def __init__(self, provider_id: str, models: tuple[str, ...], *, succeed: bool = True,
                 lie_about_model: bool = False):
        self.id = provider_id
        self.declared_models = tuple(ModelDescriptor(provider_id, m, m) for m in models)
        self.succeed = succeed
        self.lie_about_model = lie_about_model
        self.calls: list[str] = []

    def probe(self):
        return ProviderInfo(self.id, self.label, self.id, Availability.AVAILABLE)

    def complete(self, *, prompt, model, **kwargs):
        self.calls.append(model)
        if not self.succeed:
            return ProviderResult(False, availability=Availability.ERROR, error="fixture failure")
        reported = "someone-else/model" if self.lie_about_model else model
        return ProviderResult(True, text="OK", availability=Availability.AVAILABLE,
                              model_reported=reported)


def setup_runtime(tmp_path, agent: AgentProfile, adapters: list[BrainFixture]):
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


def test_exhausted_ladder_leaves_question_for_zoe(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    broken = BrainFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])
    task = make_task(session)

    run, result = runtime._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)

    # A falha continua exatamente a do motor do agente: nada mascarado.
    assert not result.ok and run.state is RunState.FAILED
    assert result.error == "fixture failure"
    assert run.error == "fixture failure"
    # ...mas a missao virou pergunta para a zoe na caixinha.
    files = question_files(inbox)
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "Migrar o relatorio" in body
    assert "fixture failure" in body
    assert run.id in body
    assert "agent" in body


def test_escalation_happens_once_per_task(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    broken = BrainFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])
    task = make_task(session)

    runtime._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)
    runtime._run_agent(session, agent, "prompt", "sys", task, timeout_s=3)

    assert len(question_files(inbox)) == 1


def test_different_tasks_get_different_questions(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    broken = BrainFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])

    runtime._run_agent(session, agent, "prompt", "sys", make_task(session, "task1"), timeout_s=3)
    runtime._run_agent(session, agent, "prompt", "sys", make_task(session, "task2"), timeout_s=3)

    assert len(question_files(inbox)) == 2


def test_mismatch_hard_stop_does_not_escalate(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    liar = BrainFixture("liar", ("liar/m1",), succeed=True, lie_about_model=True)
    agent = AgentProfile("agent", "Worker", "liar", "liar/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [liar])

    run, result = runtime._run_agent(session, agent, "prompt", "sys", make_task(session), timeout_s=3)

    assert not result.ok and run.state is RunState.FAILED
    assert result.error == "CODEX_MODEL_MISMATCH"
    assert question_files(inbox) == []


def test_success_never_escalates(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(inbox))
    nvidia = BrainFixture("nvidia", ("nvidia/m1",), succeed=True)
    agent = AgentProfile("agent", "Worker", "nvidia", "nvidia/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [nvidia])

    run, result = runtime._run_agent(session, agent, "prompt", "sys", make_task(session), timeout_s=3)

    assert result.ok and run.state is RunState.COMPLETED
    assert question_files(inbox) == []


def test_unwritable_inbox_keeps_original_failure(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("sou um arquivo, nao uma pasta", encoding="utf-8")
    monkeypatch.setenv("ZARA_ZOE_INBOX", str(blocker))
    broken = BrainFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])

    # Nao pode explodir: a escalacao e melhor esforco, a falha original vale.
    run, result = runtime._run_agent(session, agent, "prompt", "sys", make_task(session), timeout_s=3)

    assert not result.ok and run.state is RunState.FAILED
    assert result.error == "fixture failure"
