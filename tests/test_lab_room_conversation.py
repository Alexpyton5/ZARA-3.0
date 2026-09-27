import pytest

from core.ipc_handlers import IPCHandler
from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


class ConversationalCodex(ProviderAdapter):
    id = "codex_cli"
    label = "Codex Auth"

    def __init__(self):
        self.calls = []

    def probe(self):
        return ProviderInfo(
            id=self.id,
            label=self.label,
            adapter=self.id,
            availability=Availability.AVAILABLE,
            detail="test adapter",
        )

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs["model"]
        return ProviderResult(
            ok=True,
            availability=Availability.AVAILABLE,
            text=f"Resposta natural de {model}",
            model_reported=model,
        )


def service_with_real_store(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    adapter = ConversationalCodex()
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(adapter)
    runtime = LabRuntime(store, registry)
    service = LabV1Service()
    service._store = store
    service._runtime = runtime
    return service, store, adapter


@pytest.mark.asyncio
async def test_plain_room_chat_uses_real_leader_run_without_creating_a_mission(tmp_path):
    service, store, adapter = service_with_real_store(tmp_path)

    result = await service.room_message("room-one", "Oi, equipe")

    assert result["success"] is True
    assert result["agent_name"] == "Artemis"
    assert result["run_id"].startswith("run_")
    assert result["model_reported"] == result["model_requested"]
    assert result["response"].startswith("Resposta natural")
    assert len(store.list_runs("room-one")) == 1
    assert [message.kind.value for message in store.list_messages("room-one")] == ["USER", "AGENT"]
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_action_request_in_room_starts_real_autopilot_instead_of_fake_chat(tmp_path):
    service, _store, adapter = service_with_real_store(tmp_path)
    calls = []

    async def start(intent, session_id=None):
        calls.append((intent, session_id))
        return {"success": True, "code": "MISSION_STARTED", "session_id": session_id, "state": "PLANNING"}

    service.start_autopilot = start
    result = await service.room_message(
        "room-action",
        "@Artemis convoque o time e melhore a latência da voz da ZARA",
    )

    assert result["success"] is True
    assert result["code"] == "MISSION_STARTED"
    assert calls == [("@Artemis convoque o time e melhore a latência da voz da ZARA", "room-action")]
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_opencode_model_fix_request_starts_mission_not_chat(tmp_path):
    service, _store, adapter = service_with_real_store(tmp_path)
    request = "corrija os modelos não verificados do open code e traga eles para trabalhar conosco"
    calls = []

    async def start(intent, session_id=None):
        calls.append((intent, session_id))
        return {"success": True, "code": "MISSION_STARTED", "session_id": session_id, "state": "PLANNING"}

    service.start_autopilot = start
    result = await service.room_message("room-opencode", request)

    assert result["code"] == "MISSION_STARTED"
    assert calls == [(request, "room-opencode")]
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_room_message_during_active_mission_steers_same_mission(tmp_path):
    service, _store, adapter = service_with_real_store(tmp_path)
    calls = []
    service._autopilot = type("Autopilot", (), {
        "controller": type("Controller", (), {
            "snapshot": lambda self, sid: {"session_id": sid, "state": "RUNNING"},
            "submit_owner_input": lambda self, sid, text: calls.append((sid, text)) or {
                "accepted": True, "session_id": sid, "status": "PENDING"},
        })(),
    })()

    result = await service.room_message("room-live", "priorize a experiência de voz")

    assert result["success"] is True
    assert result["code"] == "OWNER_INPUT_ACCEPTED"
    assert calls == [("room-live", "priorize a experiência de voz")]
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_at_mention_routes_to_that_active_participant_with_provenance(tmp_path):
    service, store, adapter = service_with_real_store(tmp_path)

    result = await service.room_message("room-two", "@Vulcan explique o próximo passo")

    assert result["success"] is True
    assert result["agent_name"] == "Vulcan"
    assert result["provider"] == "codex_cli"
    assert result["model_reported"] == result["model_requested"]
    run = store.get_run(result["run_id"])
    assert run is not None and run.agent_id == result["agent_id"]
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_agent_soul_and_permissions_reach_the_next_real_turn(tmp_path):
    service, store, adapter = service_with_real_store(tmp_path)
    team = service._get_runtime().ensure_core_team()
    vulcan = next(agent for agent in store.list_agents() if agent.name == "Vulcan")
    service._agent_profiles = __import__(
        "core.lab_v1.agent_profiles", fromlist=["AgentProfileStore"]
    ).AgentProfileStore(tmp_path / "profiles")
    service._agent_profiles.update(
        vulcan.id,
        soul="Você é direto e sempre propõe um teste verificável.",
        permissions=["read_workspace", "run_tests"],
    )

    result = await service.room_message("room-profile", "@Vulcan avalie esta ideia")

    assert result["success"] is True
    system = adapter.calls[-1]["system"]
    assert "sempre propõe um teste verificável" in system
    assert "read_workspace" in system and "run_tests" in system


@pytest.mark.asyncio
async def test_updated_soul_is_also_used_by_mission_runtime_profiles(tmp_path):
    service, store, _adapter = service_with_real_store(tmp_path)
    service._get_runtime().ensure_core_team()
    artemis = next(agent for agent in store.list_agents() if agent.name == "Artemis")
    service._agent_profiles = __import__(
        "core.lab_v1.agent_profiles", fromlist=["AgentProfileStore"]
    ).AgentProfileStore(tmp_path / "profiles")

    result = await service.update_agent_profile(
        agent_id=artemis.id,
        soul="Priorize evidência e proponha melhorias mensuráveis.",
        permissions=["read_workspace", "run_tests"],
    )

    assert result["success"] is True
    saved = store.get_agent(artemis.id)
    assert saved.instructions == "Priorize evidência e proponha melhorias mensuráveis."
    assert "model.text" in saved.capabilities
    assert "profile.permissions.configured" in saved.capabilities
    assert "permission:run_tests" in saved.capabilities


@pytest.mark.asyncio
async def test_durable_room_operation_dispatches_the_same_conversation_path(tmp_path):
    service, store, _adapter = service_with_real_store(tmp_path)
    assert "lab.v1.room" in IPCHandler._LAB_V1_ADMISSIBLE_COMMANDS
    ack, created = await service.admit_operation_for_dispatch(
        "request-room-1",
        "lab.v1.room",
        {"session_id": "room-three", "content": "Oi"},
    )
    assert created is True and ack["accepted"] is True
    await service.authorize_operation_dispatch(ack["operation_id"])

    terminal = await service.dispatch_operation(ack["operation_id"])

    assert terminal["success"] is True
    assert terminal["result"]["code"] == "ROOM_REPLY"
    assert len(store.list_runs("room-three")) == 1
