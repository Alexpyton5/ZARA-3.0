from __future__ import annotations

import pytest

from core.lab_v1.domain import AgentProfile, RoleBinding, RoleName, Session, Team, TeamMembership, Task
from core.lab_v1.mentions import MentionResolutionError
from core.lab_v1.runtime import LabRuntime, MissionRoom
from core.lab_v1.store import LabStore


def _world(tmp_path):
    store = LabStore(tmp_path / "communication.db")
    store.initialize()
    store.save_team(Team("team", "Communication team"))
    sender = AgentProfile("sender", "Artemis", "fake", "fake", role=RoleName.CEO)
    receiver = AgentProfile("receiver", "Vulcan", "fake", "fake", role=RoleName.BUILDER)
    outsider = AgentProfile("outsider", "Ghost", "fake", "fake")
    for agent in (sender, receiver, outsider):
        store.save_agent(agent)
    store.save_membership(TeamMembership("membership_sender", "team", "sender"))
    store.save_membership(TeamMembership("membership_receiver", "team", "receiver"))
    store.save_role_binding(RoleBinding("binding_builder", "team", RoleName.BUILDER, "receiver"))
    store.save_session(Session("session", "team", "Ship communication"))
    store.save_task(Task(
        "task", "session", "Build piece", "Build the piece", "sender",
        assigned_agent_id="receiver",
    ))
    return store, LabRuntime(store, registry=None)


def test_missionroom_persists_canonical_message_and_pending_across_restart(tmp_path):
    store, runtime = _world(tmp_path)
    room = MissionRoom(object(), runtime=runtime)

    sent = room.send(
        "session", from_agent_id="sender", content="  @Vulcan\nprepare   the evidence  ",
        task_id="task", natural_language=True,
    )
    assert sent["status"] == "PENDING_REPLY"
    assert sent["to_agent_id"] == "receiver"
    assert sent["content"] == "@Vulcan prepare the evidence"
    assert sent["correlation_id"].startswith("v1comm_")
    assert sent["provenance"]["author_agent_id"] == "sender"
    assert sent["provenance"]["to_agent_id"] == "receiver"
    assert sent["provenance"]["assigned_agent_id"] == "receiver"
    assert sent["assignment"] == {"task_id": "task", "assigned_agent_id": "receiver"}

    restarted = LabRuntime(LabStore(store.db_path), registry=None)
    restarted_room = MissionRoom(object(), runtime=restarted)
    pending = restarted_room.pending_replies("session", for_agent_id="receiver")
    assert [item["id"] for item in pending] == [sent["id"]]
    assert pending[0]["correlation_id"] == sent["correlation_id"]

    reply = restarted_room.reply(
        "session", from_agent_id="receiver", reply_to=sent["id"],
        content="feito, vou anexar a evidencia",
    )
    assert reply["status"] == "DELIVERED"
    assert reply["reply_to"] == sent["id"]
    assert reply["correlation_id"] == sent["correlation_id"]
    assert restarted_room.pending_replies("session", for_agent_id="receiver") == []

    # The retry after a crash is a read, not a second delivered message.
    duplicate = restarted_room.reply(
        "session", from_agent_id="receiver", reply_to=sent["id"],
        content="feito, vou anexar a evidencia",
    )
    assert duplicate["id"] == reply["id"]
    assert duplicate["idempotent"] is True
    assert len(restarted.list_agent_messages("session")) == 2


def test_mentions_and_assignment_reject_noncanonical_routes(tmp_path):
    store, runtime = _world(tmp_path)
    room = MissionRoom(object(), runtime=runtime)

    # Role and display-name mentions resolve to the same persisted id.
    role_message = room.send(
        "session", from_agent_id="sender", content="@BUILDER review this",
    )
    assert role_message["to_agent_id"] == "receiver"

    with pytest.raises(MentionResolutionError, match="membership ativo"):
        room.send("session", from_agent_id="sender", content="@Ghost hello")

    with pytest.raises(MentionResolutionError, match="assigned_agent_id"):
        room.send(
            "session", from_agent_id="sender", content="@Ghost diverging route",
            to_agent_id="outsider", task_id="task",
        )

    with pytest.raises(MentionResolutionError, match="membership ativo"):
        room.send(
            "session", from_agent_id="outsider", content="@Vulcan hello",
        )


def test_correlation_is_explicit_and_unique_for_persistent_messages(tmp_path):
    store, runtime = _world(tmp_path)
    room = MissionRoom(object(), runtime=runtime)
    first = room.send(
        "session", from_agent_id="sender", to_agent_id="receiver",
        content="first", correlation_id="v1comm_fixed",
    )
    retry = room.send(
        "session", from_agent_id="sender", to_agent_id="receiver",
        content="first", correlation_id="v1comm_fixed",
    )
    assert retry["id"] == first["id"]
    assert retry["idempotent"] is True

    with pytest.raises(ValueError, match="ja foi usada"):
        room.send(
            "session", from_agent_id="sender", to_agent_id="receiver",
            content="different", correlation_id="v1comm_fixed",
        )

    with pytest.raises(ValueError, match="destinatario canonico"):
        room.reply(
            "session", from_agent_id="receiver", reply_to=first["id"],
            content="wrong route", to_agent_id="sender",
        )
