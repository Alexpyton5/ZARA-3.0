from __future__ import annotations

from core.lab_v1.domain import EventType, LabEvent, Session, Team
from core.lab_v1.domain import (
    AgentProfile, Availability, CostBasis, ProviderInfo, ProviderResult,
    RoleBinding, RoleName, TeamMembership,
)
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from memory.user_memory import UserMemoryCore


class _EmptyMemory:
    def search(self, *_args, **_kwargs):
        return []


def _promote_lesson(store: LabStore, session_id: str, marker_id: str, statement: str) -> None:
    evidence = store.append_event(
        LabEvent(
            id=f"evidence:{marker_id}",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id=session_id,
            entity_id="task",
            payload={"result": "observed"},
        )
    )
    marker = store.append_event(
        LabEvent(
            id=marker_id,
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id=session_id,
            entity_id=None,
            payload={"lesson": statement, "evidence_event_id": evidence.id},
        )
    )
    store.promote_lesson(marker.id)


def test_ceo_context_keeps_base_once_and_appends_same_team_verified_provenance(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team-a", name="A"))
    store.save_team(Team(id="team-b", name="B"))
    current = Session(id="current", team_id="team-a", objective="Recover CEO memory")
    store.save_session(current)
    store.save_session(Session(id="prior-a", team_id="team-a", objective="Prior A"))
    store.save_session(Session(id="prior-b", team_id="team-b", objective="Prior B"))
    _promote_lesson(store, "prior-a", "lesson-a", "Recover CEO memory from verified evidence.")
    _promote_lesson(store, "prior-b", "lesson-b", "Recover CEO memory from foreign evidence.")

    runtime = object.__new__(LabRuntime)
    runtime.memory_adapter = LabMemoryAdapter(store, _EmptyMemory())
    calls = []

    def base_context(session, text):
        calls.append((session.id, text))
        return "BASE OWNER HISTORY\nMensagem atual de Alex:\nRecover memory"

    runtime._session_context = base_context
    context = runtime._session_context_with_recovery(current, "Recover memory")

    assert calls == [("current", "Recover memory")]
    assert context.count("BASE OWNER HISTORY") == 1
    assert "Recover CEO memory from verified evidence." in context
    assert "sessao prior-a" in context
    assert "event:evidence:lesson-a" in context
    assert "foreign evidence" not in context


def test_ceo_context_returns_original_base_for_legacy_or_failing_adapter():
    class LegacyAdapter:
        def recover_session_context(self, session, text, *, base_context):
            return "replacement that lost history"

    runtime = object.__new__(LabRuntime)
    runtime.memory_adapter = LegacyAdapter()
    calls = []
    runtime._session_context = lambda session, text: calls.append(text) or "ORIGINAL BASE"

    assert runtime._session_context_with_recovery(object(), "hello") == "ORIGINAL BASE"
    assert calls == ["hello"]


def test_ceo_context_rejects_duplicate_base_and_broken_descriptor():
    class DuplicateAdapter:
        def recover_session_context(self, session, text):
            return "ORIGINAL BASEORIGINAL BASEMEMORY"

    class BrokenAdapter:
        @property
        def recover_session_context(self):
            raise RuntimeError("broken descriptor")

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "ORIGINAL BASE"
    runtime.memory_adapter = DuplicateAdapter()
    assert runtime._session_context_with_recovery(object(), "hello") == "ORIGINAL BASE"
    runtime.memory_adapter = BrokenAdapter()
    assert runtime._session_context_with_recovery(object(), "hello") == "ORIGINAL BASE"


def test_ceo_context_rejects_a_recovery_echo_of_the_current_alex_message():
    class EchoAdapter:
        def recover_session_context(self, session, text):
            return f"Licoes verificadas:\nMensagem atual de Alex:\n{text}"

    class RawEchoAdapter:
        def recover_session_context(self, session, text):
            return text

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: (
        f"BASE\nMensagem atual de Alex:\n{text}"
    )
    current = "Nao repita esta mensagem do Alex."
    runtime.memory_adapter = EchoAdapter()
    assert runtime._session_context_with_recovery(object(), current) == (
        f"BASE\nMensagem atual de Alex:\n{current}"
    )
    runtime.memory_adapter = RawEchoAdapter()
    assert runtime._session_context_with_recovery(object(), current) == (
        f"BASE\nMensagem atual de Alex:\n{current}"
    )


def test_ceo_context_rejects_recovery_with_a_preamble_before_the_full_current_message():
    class PrefixedEchoAdapter:
        def recover_session_context(self, session, text):
            return f"Licao recuperada: {text}"

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "BASE"
    runtime.memory_adapter = PrefixedEchoAdapter()
    current = "Organize os arquivos do projeto ZARA e confirme o resultado final."

    assert runtime._session_context_with_recovery(object(), current) == "BASE"


def test_ceo_context_rejects_material_partial_echo_but_keeps_an_independent_lesson():
    class Adapter:
        def __init__(self, recovered):
            self.recovered = recovered

        def recover_session_context(self, session, text):
            return self.recovered

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "BASE"
    current = "Organize os arquivos do projeto ZARA e confirme o resultado final."
    runtime.memory_adapter = Adapter(
        "Licao recuperada: organize os arquivos do projeto ZARA e confirme o resultado."
    )
    assert runtime._session_context_with_recovery(object(), current) == "BASE"

    lesson = "O projeto ZARA guarda evidencias de testes junto aos arquivos relevantes."
    runtime.memory_adapter = Adapter(lesson)
    assert runtime._session_context_with_recovery(object(), current) == f"BASE\n\n{lesson}"


def test_ceo_context_rejects_eight_of_ten_current_tokens_with_interleaved_words():
    class InterleavedAdapter:
        def recover_session_context(self, session, text):
            return (
                "alpha marker bravo marker charlie marker delta marker "
                "echo marker foxtrot marker golf marker hotel"
            )

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "BASE"
    runtime.memory_adapter = InterleavedAdapter()
    current = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"

    assert runtime._session_context_with_recovery(object(), current) == "BASE"


def test_ceo_context_rejects_four_of_five_current_tokens_with_interleaved_words():
    class InterleavedAdapter:
        def recover_session_context(self, session, text):
            return "alpha marker bravo marker charlie marker delta"

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "BASE"
    runtime.memory_adapter = InterleavedAdapter()
    current = "alpha bravo charlie delta echo"

    assert runtime._session_context_with_recovery(object(), current) == "BASE"


def test_ceo_context_rejects_sensitive_or_private_recovery_appendix():
    class UnsafeAdapter:
        def recover_session_context(self, session, text):
            return "Bearer eyJhbGciOiJIUzI1NiJ9\nRaciocinio privado: hidden steps"

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: "ORIGINAL BASE"
    runtime.memory_adapter = UnsafeAdapter()

    assert runtime._session_context_with_recovery(object(), "hello") == "ORIGINAL BASE"


def test_ceo_context_with_empty_base_uses_only_memory_appendix():
    class Adapter:
        def recover_session_context(self, session, text):
            return "MEMORY APPENDIX"

    runtime = object.__new__(LabRuntime)
    runtime._session_context = lambda session, text: ""
    runtime.memory_adapter = Adapter()

    assert runtime._session_context_with_recovery(object(), "hello") == "MEMORY APPENDIX"


class _PromptAdapter(ProviderAdapter):
    id = "fake"
    label = "Fake"
    declared_models = (
        ModelDescriptor("fake", "plain", "Plain"),
        ModelDescriptor("fake", "switched", "Switched"),
    )

    def __init__(self):
        self.prompts = []

    def probe(self):
        return ProviderInfo(self.id, self.label, self.id, Availability.AVAILABLE, "fake")

    def complete(self, *, prompt, model, system=None, **kwargs):
        self.prompts.append(prompt)
        return ProviderResult(
            True,
            '{"reply_to_alex":"ok","delegate":null,"decision":null}',
            model_reported=model,
            cost_usd=0,
            cost_basis=CostBasis.KNOWN,
        )


def test_submit_delivers_base_once_plus_recovered_lesson_to_provider(tmp_path):
    store = LabStore(tmp_path / "submit.db")
    store.initialize()
    team = Team(id="team", name="Team")
    store.save_team(team)
    ceo = AgentProfile(
        id="ceo", name="CEO", provider_id="fake", model="plain", role=RoleName.CEO
    )
    store.save_agent(ceo)
    store.save_membership(TeamMembership(id="membership", team_id=team.id, agent_id=ceo.id))
    store.save_role_binding(
        RoleBinding(id="binding", team_id=team.id, role=RoleName.CEO, agent_id=ceo.id)
    )
    store.save_session(Session(id="prior", team_id=team.id, objective="Prior"))
    current = Session(id="current", team_id=team.id, objective="Recover CEO memory")
    store.save_session(current)
    _promote_lesson(store, "prior", "submit-lesson", "Remember the marked recovery path.")
    _promote_lesson(
        store,
        "prior",
        "secret-lesson",
        "ZARA project token: must-not-enter-the-prompt",
    )
    _promote_lesson(
        store,
        "prior",
        "bearer-lesson",
        "Bearer eyJhbGciOiJIUzI1NiJ9.must-not-enter-the-prompt",
    )
    _promote_lesson(
        store,
        "prior",
        "private-reasoning-lesson",
        "Raciocinio privado: must-not-enter-the-prompt",
    )
    _promote_lesson(
        store,
        "prior",
        "echo-current-lesson",
        "Qual trabalho recente e projeto atual do Alex devemos recuperar agora?",
    )
    memory_path = tmp_path / "user-memory.db"
    memory = UserMemoryCore(db_path=memory_path)
    writer = LabMemoryAdapter(store, memory)
    for event_id, statement in (
        ("recent-work", "O trabalho recente do Alex foi organizar a memoria da ZARA."),
        ("current-project", "O projeto atual do Alex tem o objetivo de recuperar contexto apos reinicio."),
    ):
        event = store.append_event(
            LabEvent(
                id=event_id,
                seq=0,
                type=EventType.LESSON_MARKED_VERIFIED,
                session_id="prior",
                entity_id=None,
                payload={"lesson": statement},
            )
        )
        writer.promote(event, session=store.get_session("prior"), statement=statement)

    # A new runtime and memory instances represent process restart. Changing
    # the stored CEO model proves the recovered context is provider-independent.
    reopened_store = LabStore(tmp_path / "submit.db")
    reopened_store.initialize()
    switched_ceo = reopened_store.get_agent("ceo")
    switched_ceo.model = "switched"
    reopened_store.save_agent(switched_ceo)
    provider = _PromptAdapter()
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(provider)
    runtime = LabRuntime(
        reopened_store,
        registry,
        LabMemoryAdapter(reopened_store, UserMemoryCore(db_path=memory_path)),
    )

    result = runtime.submit(
        "current", "Qual trabalho recente e projeto atual do Alex devemos recuperar agora?"
    )

    assert result["session_state"] == "COMPLETED"
    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert prompt.count("Mensagem atual de Alex:") == 1
    assert prompt.count("Qual trabalho recente e projeto atual do Alex") == 1
    assert "O trabalho recente do Alex foi organizar a memoria da ZARA." in prompt
    assert "O projeto atual do Alex tem o objetivo de recuperar contexto" in prompt
    assert "origem: sessao prior" in prompt
    assert "must-not-enter-the-prompt" not in prompt
    assert "Raciocinio privado" not in prompt
    assert prompt.count("Mensagem atual de Alex:") == 1
    assert prompt.count("Qual trabalho recente e projeto atual do Alex") == 1
    assert provider.prompts and reopened_store.get_agent("ceo").model == "switched"
