"""Roundtrip test: Lab V1 seats talking to each other (zero model cost).

Proves the agent-to-agent conversation mechanics work end to end against the
REAL protocol modules (domain.py / messages.py / mentions.py) without calling
any model: no Run row, no provider, no quota.

This is groundwork for MISSÃO GIGANTE 2 "LAB VIVO" Fase B (bots conversando
entre si com prova real de tarefa dividida): the routing layer is verified
here; the mission wires real seats and a task through it.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.lab_v1.domain import Message, MessageKind, RoleName
from core.lab_v1.messages import (
    MESSAGE_MAX_CHARS,
    MentionResolutionError,
    message_provenance,
    new_correlation_id,
    normalize_message_text,
    pending_reply_ids,
    resolve_recipient_ids,
)

TEAM = "team-zara-core"


@dataclass
class FakeMembership:
    agent_id: str
    left_at: float | None = None


@dataclass
class FakeAgent:
    id: str
    name: str
    archived: bool = False


@dataclass
class FakeBinding:
    agent_id: str


@dataclass
class FakeTask:
    session_id: str | None
    assigned_agent_id: str | None


class FakeStore:
    """Minimal store satisfying the messages/mentions protocol interface."""

    def __init__(self):
        self.members = {
            "ag-eng-01": FakeMembership("ag-eng-01"),
            "ag-rev-01": FakeMembership("ag-rev-01"),
            "ag-sec-01": FakeMembership("ag-sec-01"),
            "ag-help-01": FakeMembership("ag-help-01"),
            "ag-help-02": FakeMembership("ag-help-02"),
            "ag-left-01": FakeMembership("ag-left-01", left_at=1.0),
        }
        self.agents = {
            "ag-eng-01": FakeAgent("ag-eng-01", "Motor"),
            "ag-rev-01": FakeAgent("ag-rev-01", "Revisor"),
            "ag-sec-01": FakeAgent("ag-sec-01", "Secretaria"),
            "ag-help-01": FakeAgent("ag-help-01", "Ajudante"),
            "ag-help-02": FakeAgent("ag-help-02", "Ajudante"),
            "ag-arch-01": FakeAgent("ag-arch-01", "Velho", archived=True),
            "ag-left-01": FakeAgent("ag-left-01", "Saido"),
        }
        self.bindings = {
            RoleName.ENGINEER: FakeBinding("ag-eng-01"),
            RoleName.REVIEWER: FakeBinding("ag-rev-01"),
        }
        self.tasks = {
            "task-diff-1": FakeTask("sess-1", "ag-eng-01"),
        }

    def list_memberships(self, team_id):
        assert team_id == TEAM
        return list(self.members.values())

    def get_agent(self, agent_id):
        return self.agents.get(agent_id)

    def active_binding(self, team_id, role):
        assert team_id == TEAM
        return self.bindings.get(role)

    def get_task(self, task_id):
        return self.tasks.get(task_id)


def _store():
    return FakeStore()


def _msg(msg_id, author_agent_id, content, to_agent_id=None, reply_to=None,
         correlation_id=None, kind=MessageKind.AGENT, session_id="sess-1",
         run_id=None):
    return Message(
        id=msg_id,
        session_id=session_id,
        kind=kind,
        author="test",
        content=content,
        author_agent_id=author_agent_id,
        to_agent_id=to_agent_id,
        reply_to=reply_to,
        correlation_id=correlation_id,
        run_id=run_id,
    )


# ---------------------------------------------------------------- addressing

def test_mention_role_resolves_to_seated_agent():
    recipients, assignment = resolve_recipient_ids(
        _store(), team_id=TEAM, text="Ei @REVIEWER, revisa o diff")
    assert recipients == ["ag-rev-01"]
    assert assignment is None


def test_mention_by_display_name_resolves():
    recipients, _ = resolve_recipient_ids(
        _store(), team_id=TEAM, text="@Revisor, ve isso aqui")
    assert recipients == ["ag-rev-01"]


def test_explicit_to_agent_id_routes():
    recipients, assignment = resolve_recipient_ids(
        _store(), team_id=TEAM, to_agent_id="ag-sec-01")
    assert recipients == ["ag-sec-01"]
    assert assignment is None


def test_task_assignment_routes_to_assigned_agent():
    recipients, assignment = resolve_recipient_ids(
        _store(), team_id=TEAM, task_id="task-diff-1")
    assert recipients == ["ag-eng-01"]
    assert assignment == {"task_id": "task-diff-1",
                          "assigned_agent_id": "ag-eng-01"}


def test_explicit_recipient_diverging_from_task_fails():
    store = _store()
    try:
        resolve_recipient_ids(store, team_id=TEAM,
                              task_id="task-diff-1", to_agent_id="ag-rev-01")
    except MentionResolutionError:
        return
    raise AssertionError("divergent recipient must raise")


# ------------------------------------------------------------- the roundtrip

def test_engineer_reviewer_roundtrip_clears_pending():
    turn = new_correlation_id()
    root = _msg("m-root-1", "ag-eng-01",
                normalize_message_text("  @REVIEWER  revisa\n o diff  "),
                to_agent_id="ag-rev-01", correlation_id=turn)
    assert root.content == "@REVIEWER revisa o diff"
    assert root.correlation_id == turn
    # Reviewer did NOT reply yet: the root is pending on him.
    assert pending_reply_ids([root], for_agent_id="ag-rev-01") == {"m-root-1"}
    # Reviewer replies on the same turn.
    reply = _msg("m-reply-1", "ag-rev-01", normalize_message_text("ok, aprovado"),
                 to_agent_id="ag-eng-01", reply_to="m-root-1",
                 correlation_id=turn)
    rows = [root, reply]
    assert pending_reply_ids(rows) == set()
    assert pending_reply_ids(rows, for_agent_id="ag-rev-01") == set()
    # And now the engineer owes a (non-existent) follow-up — nothing pending.
    assert pending_reply_ids(rows, for_agent_id="ag-eng-01") == set()


def test_unreplied_message_stays_pending():
    root = _msg("m-root-2", "ag-eng-01", "anota isso",
                to_agent_id="ag-sec-01")
    assert pending_reply_ids([root]) == {"m-root-2"}
    assert pending_reply_ids([root], for_agent_id="ag-rev-01") == set()


def test_legacy_broadcast_row_is_not_pending():
    legacy = _msg("m-legacy", "ag-eng-01", "aviso geral")  # to_agent_id=None
    assert pending_reply_ids([legacy]) == set()


# ------------------------------------------------------------------ safety

def test_mention_nonmember_fails():
    try:
        resolve_recipient_ids(_store(), team_id=TEAM, text="@ZeNinguem")
    except MentionResolutionError:
        return
    raise AssertionError("unknown mention must raise")


def test_mention_vacant_role_fails():
    try:
        resolve_recipient_ids(_store(), team_id=TEAM, text="@CRITIC")
    except MentionResolutionError:
        return
    raise AssertionError("vacant role mention must raise")


def test_ambiguous_display_name_fails():
    try:
        resolve_recipient_ids(_store(), team_id=TEAM, text="@Ajudante")
    except MentionResolutionError:
        return
    raise AssertionError("ambiguous mention must raise")


def test_archived_and_left_members_cannot_receive():
    store = _store()
    for agent_id in ("ag-arch-01", "ag-left-01"):
        try:
            resolve_recipient_ids(store, team_id=TEAM, to_agent_id=agent_id)
        except MentionResolutionError:
            continue
        raise AssertionError(f"{agent_id} must not be routable")


def test_empty_message_rejected():
    for bad in ("", "   ", None):
        try:
            normalize_message_text(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} must raise")


def test_message_too_long_rejected():
    try:
        normalize_message_text("x" * (MESSAGE_MAX_CHARS + 1))
    except ValueError:
        return
    raise AssertionError("oversize message must raise")


def test_correlation_id_has_canonical_prefix():
    assert new_correlation_id().startswith("v1comm")


def test_provenance_carries_ids_not_display_names():
    root = _msg("m-root-3", "ag-eng-01", "faz isso", to_agent_id="ag-rev-01",
                run_id="run-9")
    prov = message_provenance(root, task_id="task-diff-1",
                              assigned_agent_id="ag-eng-01")
    assert prov["author_agent_id"] == "ag-eng-01"
    assert prov["to_agent_id"] == "ag-rev-01"
    assert prov["run_id"] == "run-9"
    assert prov["task_id"] == "task-diff-1"
    assert "Revisor" not in str(prov.values())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} verdes")
    raise SystemExit(1 if failed else 0)
