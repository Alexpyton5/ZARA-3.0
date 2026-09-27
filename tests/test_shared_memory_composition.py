"""Integrated proof for the shared second brain vertical slice.

Fakes are safe and local; no provider is called. The canonical owners are
real: `UserMemoryCore`, `LabStore`, `ProjectMemory` and
`ObsidianMemoryManager` with an injected temporary vault and index. Proven
here (SOURCE/TEST only): the same structured memory is queryable by the ZARA
conversation path and the Lab agent path, with provenance, degradation,
restart recovery and secret exclusion.
"""
from __future__ import annotations

import pytest

from core.lab_v1.domain import EventType, LabEvent, Session, Team
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.store import LabStore
from core.obsidian_memory import ObsidianMemoryManager
from memory.project_memory import ProjectMemory
from memory.second_brain_composition import (
    build_shared_second_brain,
    render_second_brain_context,
)
from memory.user_memory import UserMemoryCore


def _canon(tmp_path):
    """Real canonical owners on temporary paths; no real user data touched."""
    user_memory = UserMemoryCore(db_path=tmp_path / "user_memory.db")
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="Mentor"))
    store.save_session(
        Session(id="mission-a", team_id="team", objective="Recuperar contexto apos reinicio")
    )
    store.save_session(
        Session(id="mission-b", team_id="team", objective="Recuperar contexto apos reinicio")
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    return user_memory, store, vault, tmp_path / "obsidian_index.sqlite3"


def _brain(user_memory, store, vault, index_db, project_memory=None):
    return build_shared_second_brain(
        user_memory=user_memory,
        lab_store=store,
        project_memory=project_memory,
        obsidian=ObsidianMemoryManager(vault_path=vault),
        obsidian_index_db=index_db,
    )


def _promote_discovery(store, user_memory, event_id: str, statement: str) -> None:
    """Canonical verified shape: observed evidence + marked-verified marker.

    The recovery audit gate only accepts facts whose promoting event is a
    marked-verified lesson, so the test promotes exactly what production
    promotes.
    """
    evidence = store.append_event(
        LabEvent(
            id=f"evidence:{event_id}",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id="mission-a",
            entity_id="task-1",
            payload={"result": "observed"},
        )
    )
    marker = store.append_event(
        LabEvent(
            id=event_id,
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id="mission-a",
            entity_id=None,
            payload={"lesson": statement, "evidence_event_id": evidence.id},
        )
    )
    LabMemoryAdapter(store, user_memory).promote(
        marker,
        session=store.get_session("mission-a"),
        statement=statement,
    )


def test_verified_mission_fact_reaches_both_zara_and_agent_paths(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    statement = "A ZARA guarda fatos verificados com proveniencia apos reinicio."
    _promote_discovery(store, user_memory, "disc-1", statement)
    brain = _brain(user_memory, store, vault, index_db)

    # ZARA conversation path: relevant fact with lab provenance.
    zara_context = render_second_brain_context(
        brain, "como recuperar contexto apos reinicio?"
    )
    assert "fatos verificados com proveniencia" in zara_context
    assert "fonte: user_memory" in zara_context
    assert "lab:mission-a:disc-1" in zara_context

    # Agent path: a new mission instance recovers the same verified fact,
    # exactly once (the shared facade must not duplicate the lesson row).
    adapter = LabMemoryAdapter(store, user_memory, second_brain=brain)
    agent_context = adapter.recover_session_context(
        store.get_session("mission-b"), "como recuperar contexto apos reinicio?"
    )
    assert agent_context.count("fatos verificados com proveniencia") == 1
    assert "origem: sessao mission-a" in agent_context
    assert "evidencia: lab:mission-a:disc-1" in agent_context


def test_owner_goal_fact_has_origin_and_timestamp_in_both_paths(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    user_memory.add(
        "Objetivo do Alex: ZARA autonoma persistente",
        category="semantic_fact",
        source="owner",
        ref="owner-goal-1",
    )
    brain = _brain(user_memory, store, vault, index_db)
    query = "qual o objetivo do Alex com a ZARA?"

    # The shared facade carries origin and timestamp on the item itself;
    # both paths below consult this same query result.
    result = brain.query(query)
    item = next(i for i in result["items"] if "Objetivo do Alex" in i["text"])
    assert item["source"] == "user_memory"
    assert "owner:owner-goal-1" in item["provenance"]
    assert item["timestamp"] > 0

    zara_context = render_second_brain_context(brain, query)
    assert "Objetivo do Alex" in zara_context
    assert "origem: owner:owner-goal-1" in zara_context

    adapter = LabMemoryAdapter(store, user_memory, second_brain=brain)
    agent_context = adapter.recover_session_context(store.get_session("mission-b"), query)
    assert "Objetivo do Alex" in agent_context
    assert "fonte: user_memory; origem: owner:owner-goal-1" in agent_context


def test_project_memory_event_reaches_both_paths(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    project_memory = ProjectMemory(base_dir=tmp_path / "project-memory")
    project_memory.record_mentor_event(
        "task-lab-9", "OK", "Integrou a memoria compartilhada da ZARA"
    )
    brain = _brain(user_memory, store, vault, index_db, project_memory)
    query = "a memoria compartilhada da ZARA ficou pronta?"

    zara_context = render_second_brain_context(brain, query)
    assert "task=task-lab-9" in zara_context
    assert "status=OK" in zara_context
    assert "Integrou a memoria compartilhada" in zara_context
    assert "fonte: project_memory" in zara_context

    adapter = LabMemoryAdapter(store, user_memory, second_brain=brain)
    agent_context = adapter.recover_session_context(store.get_session("mission-b"), query)
    assert "task=task-lab-9" in agent_context
    assert "fonte: project_memory" in agent_context


def test_obsidian_note_appears_after_sync_and_degrades_to_safe_cache(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    (vault / "projeto-zara.md").write_text(
        "A ZARA usa voz Kore na saida e memoria compartilhada.", encoding="utf-8"
    )
    brain = _brain(user_memory, store, vault, index_db)
    query = "que voz a ZARA usa na saida?"

    zara_context = render_second_brain_context(brain, query)
    assert "voz Kore" in zara_context
    assert "fonte: obsidian" in zara_context
    assert "projeto-zara.md" in zara_context

    # The vault disappears: a new composition degrades and still serves the
    # derived, safe index cache — never an invented answer.
    vault.rename(tmp_path / "vault-gone")
    degraded_brain = _brain(user_memory, store, vault, index_db)
    result = degraded_brain.query(query)
    assert "obsidian_unavailable" in result["degraded"]
    cached_text = " ".join(i["text"] for i in result["items"])
    assert "voz Kore" in cached_text


def test_secrets_never_reach_any_path(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    (vault / "notas-creds.md").write_text(
        "api_key = sk-abcdef1234567890\nBearer eyJhbGciOiJIUzI1NiJ9.token-aqui",
        encoding="utf-8",
    )
    (vault / "raciocinio.md").write_text(
        "Raciocinio privado: passos internos ocultos do planejamento",
        encoding="utf-8",
    )
    (vault / "projeto-tokens.md").write_text(
        "Conteudo benigno que nunca deveria ser indexado por nome de caminho.",
        encoding="utf-8",
    )
    brain = _brain(user_memory, store, vault, index_db)
    sync_result = brain.sync_obsidian()
    assert sync_result["excluded"] >= 3

    probe = "credenciais api_key Bearer token raciocinio privado passos internos"
    for context in (
        render_second_brain_context(brain, probe),
        LabMemoryAdapter(store, user_memory, second_brain=brain)
        .recover_session_context(store.get_session("mission-b"), probe),
    ):
        assert "sk-abcdef" not in context
        assert "eyJ" not in context
        assert "Raciocinio privado" not in context
        assert "nunca deveria ser indexado" not in context

    # The canonical owner itself refuses to store secrets.
    with pytest.raises(ValueError):
        user_memory.add("Bearer eyJhbGciOiJIUzI1NiJ9.secret", source="manual")


def _promote_lesson(store, event_id: str, statement: str) -> None:
    """Central-lab lesson shape: observed evidence + marked-verified marker."""
    evidence = store.append_event(
        LabEvent(
            id=f"evidence:{event_id}",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id="mission-a",
            entity_id="task-1",
            payload={"result": "observed"},
        )
    )
    marker = store.append_event(
        LabEvent(
            id=event_id,
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id="mission-a",
            entity_id=None,
            payload={"lesson": statement, "evidence_event_id": evidence.id},
        )
    )
    store.promote_lesson(marker.id)


def test_fact_promoted_to_both_stores_appears_once_in_agent_context(tmp_path):
    """Terra finding 1: a verified outcome is promoted into BOTH stores with
    different evidence refs; the agent prompt must render it exactly once."""
    user_memory, store, vault, index_db = _canon(tmp_path)
    statement = "O comando de recuperao usa checkpoint assinado com evidencia."
    _promote_lesson(store, "disc-dup", statement)
    _promote_discovery(store, user_memory, "disc-dup-mem", statement)
    brain = _brain(user_memory, store, vault, index_db)
    adapter = LabMemoryAdapter(store, user_memory, second_brain=brain)
    agent_context = adapter.recover_session_context(
        store.get_session("mission-b"), "como recuperar com checkpoint?"
    )
    assert agent_context.count("checkpoint assinado") == 1
    zara_context = render_second_brain_context(brain, "como recuperar com checkpoint?")
    assert zara_context.count("checkpoint assinado") == 1


def test_secret_shaped_note_never_reaches_zara_context(tmp_path):
    """Terra finding 2: the ZARA render path must apply the same secret gate
    as the agent path, including the label-in-the-middle form."""
    user_memory, store, vault, index_db = _canon(tmp_path)
    (vault / "notas.md").write_text(
        "senha do roteador: abc123\nConfiguracao de rede benigna sem segredos.",
        encoding="utf-8",
    )
    brain = _brain(user_memory, store, vault, index_db)
    zara_context = render_second_brain_context(brain, "configuracao de rede?")
    assert "abc123" not in zara_context
    # The agent path keeps enforcing the same shared gate.
    assert (
        LabMemoryAdapter(store, user_memory, second_brain=brain)
        .recover_session_context(store.get_session("mission-b"), "configuracao de rede?")
        .count("abc123")
        == 0
    )


def test_current_message_is_not_duplicated_in_any_path(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    current = "Qual trabalho recente e projeto atual do Alex devemos recuperar agora?"
    user_memory.add(current, category="semantic_fact", source="owner", ref="dup-1")
    brain = _brain(user_memory, store, vault, index_db)

    assert render_second_brain_context(brain, current) == ""
    adapter = LabMemoryAdapter(store, user_memory, second_brain=brain)
    assert adapter.recover_session_context(store.get_session("mission-b"), current) == ""


def test_restart_recovers_same_facts_and_preserves_human_edits(tmp_path):
    user_memory, store, vault, index_db = _canon(tmp_path)
    statement = "Procedimento verificado: recompilar o sidecar apos mudanca de IPC."
    _promote_discovery(store, user_memory, "disc-restart", statement)
    writer = LabMemoryAdapter(store, user_memory, ObsidianMemoryManager(vault_path=vault))
    assert writer.sync_to_obsidian("mission-a") == 1

    # Restart: new objects over the same canonical stores and derived cache.
    user_memory2 = UserMemoryCore(db_path=user_memory.db_path)
    store2 = LabStore(store.db_path)
    store2.initialize()
    brain2 = _brain(user_memory2, store2, vault, index_db)
    adapter2 = LabMemoryAdapter(
        store2, user_memory2, ObsidianMemoryManager(vault_path=vault), second_brain=brain2
    )

    # The verified fact survives restart in both paths, exactly once, and the
    # projection stays idempotent (one note, zero duplicated writes).
    assert adapter2.sync_to_obsidian("mission-a") == 0
    notes = list(vault.rglob("*.md"))
    assert len(notes) == 1
    agent_context = adapter2.recover_session_context(
        store2.get_session("mission-b"), "recompilar sidecar apos mudanca"
    )
    assert agent_context.count("recompilar o sidecar") == 1
    assert "origem: sessao mission-a" in agent_context
    zara_context = render_second_brain_context(brain2, "recompilar sidecar apos mudanca")
    assert zara_context.count("recompilar o sidecar") == 1
    assert "recompilar o sidecar" in zara_context

    # A human edit to the projected note is preserved and produces a
    # conflict artifact instead of being overwritten by the next sync.
    note = notes[0]
    note.write_text(
        note.read_text(encoding="utf-8")
        + "\n\nCorrecao humana: usar o caminho aprovado de recovery.",
        encoding="utf-8",
    )
    assert adapter2.sync_to_obsidian("mission-a") == 0
    assert "Correcao humana" in note.read_text(encoding="utf-8")
    assert note.with_name(note.stem + ".conflict.md").exists()
