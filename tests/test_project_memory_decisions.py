from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import core.autonomy_policy as autonomy_policy
import memory.project_memory as project_memory
from core.autonomy_policy import ActionRiskProfile, ApprovalSignal, AutonomyRequest, EnvironmentSignal
from memory.project_memory import ProjectMemory


def test_project_memory_decisions_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        # tmpdir represents the project-memory directory (e.g., %LOCALAPPDATA%\ZARA3\data\project-memory)
        base_dir = Path(tmpdir)
        pm = ProjectMemory(base_dir=base_dir)
        # Save a decision
        pm.save_doc(
            key="decisions",
            title="Test Decision",
            content="This is a test decision for the project."
        )
        # Retrieve it
        doc = pm.get_doc("decisions")
        assert doc is not None
        assert doc["title"] == "Test Decision"
        assert doc["content"] == "This is a test decision for the project."
        # Check that the vault file was created
        vault_file = base_dir / "vault" / "decisions.md"
        assert vault_file.exists()
        assert vault_file.read_text(encoding="utf-8") == "This is a test decision for the project."


# --------------------------------------------------------------------------
# AUDITORIA_2026-08-27 item 2.1 — importar este modulo troca globalmente
# core.autonomy_policy.decide por uma versao que grava em ProjectMemory. Se
# a inicializacao ou a gravacao falhar (disco cheio, permissao), a decisao
# real de autonomia nao pode quebrar junto — so o rastreamento e best-effort.
# --------------------------------------------------------------------------

def _request(action_name: str) -> AutonomyRequest:
    return AutonomyRequest(
        action_name=action_name,
        confidence=0.95,
        irreversible=False,
        configured_level=None,
        risk_profile=ActionRiskProfile(risk="LOW", capability="READ_ONLY", known=True),
        environment=EnvironmentSignal(),
        approval=ApprovalSignal(),
    )


def test_decide_survives_project_memory_init_failure(monkeypatch):
    monkeypatch.setattr(project_memory, "_DEFAULT_PM", None)
    monkeypatch.setattr(
        project_memory,
        "ProjectMemory",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disco cheio")),
    )

    decision = autonomy_policy.decide(_request(f"test_action_{uuid4()}"))

    assert decision is not None
    assert decision.verdict is not None


def test_decide_survives_append_decision_failure(monkeypatch):
    class _BrokenPM:
        def append_decision(self, *_a, **_k):
            raise OSError("falha ao gravar decisions.md")

    monkeypatch.setattr(project_memory, "_get_default_project_memory", lambda: _BrokenPM())

    decision = autonomy_policy.decide(_request(f"test_action_{uuid4()}"))

    assert decision is not None
    assert decision.verdict is not None


if __name__ == "__main__":
    test_project_memory_decisions_log()
    print("Test passed")
