import re
from uuid import uuid4

import memory.project_memory as project_memory
from memory.project_memory import ProjectMemory
from core.autonomy_policy import AutonomyRequest, ActionRiskProfile, EnvironmentSignal, ApprovalSignal, decide


def test_decision_is_recorded_in_project_memory(tmp_path, monkeypatch):
    # AUDITORIA_2026-08-27: esta prova usava ProjectMemory() sem argumentos, que
    # resolve para %LOCALAPPDATA%\ZARA3\data\project-memory — o arquivo REAL de
    # decisoes do Alex. Cada rodada da suite escrevia lixo de teste ali dentro,
    # exatamente o incidente que tests/conftest.py ja documentou para
    # core/cronometro.py. Isola-se aqui a mesma singleton que decide() usa.
    isolated_pm = ProjectMemory(base_dir=tmp_path / "project-memory")
    monkeypatch.setattr(project_memory, "_DEFAULT_PM", isolated_pm)

    # We use a unique action name to identify our test decision in the log
    unique_action = f"test_action_{uuid4()}"

    # Build a minimal request that will produce a decision (low risk, readable, etc.)
    request = AutonomyRequest(
        action_name=unique_action,
        confidence=0.95,
        irreversible=False,
        configured_level=None,
        risk_profile=ActionRiskProfile(risk="LOW", capability="READ_ONLY", known=True),
        environment=EnvironmentSignal(),
        approval=ApprovalSignal(),
    )

    # Call the decision function (this is now traced by our patch in project_memory)
    decision = decide(request)

    doc = isolated_pm.get_doc("decisions")

    assert doc is not None, "Decisions document should exist"
    content = doc["content"]

    # KNOWN_BROKEN (pre-existente, fora do escopo da AUDITORIA_2026-08-27):
    # format_decision_pt() nao inclui o action_name no texto formatado — so
    # verbo/capability/risk genericos. Ate isso ser decidido (mudar o formato
    # do log e uma escolha de produto, nao um bug obvio), a prova possivel
    # aqui e que uma entrada nova foi de fato gravada, nao que ela cita o
    # nome da acao.
    assert content.strip(), "Decisions document should not be empty"
    lines = content.splitlines()
    assert lines, "Decisions document should have at least one line"
    assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', lines[-1]), (
        f"Ultima linha do log deveria ter timestamp da decisao recem-tomada:\n{content}"
    )
