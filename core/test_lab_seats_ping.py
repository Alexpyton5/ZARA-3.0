"""Ping dos 11 assentos fixos do Lab (core/lab_v1/fixed_seats.py).

Prova o portao fail-closed SEM chamar modelo nenhum:
- os 11 assentos existem e estao na ordem oficial;
- assento vazio NAO inventa agente (VACANT) e NAO libera turno;
- convite sem autorizacao de recurso NAO passa;
- assento ocupado + autorizado FALA (caminho positivo, sem modelo).
Custo: zero. Rede: nenhuma. Quota: nenhuma.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.lab_v1.domain import AgentProfile, RoleName
from core.lab_v1.fixed_seats import (
    FIXED_SEATS,
    GATED_TEAM_NAMES,
    InvitationDenied,
    invited_agents,
    requires_fixed_seat,
    run_invited_turn,
    seat_snapshot,
)

EXPECTED_ORDER = [
    "CEO", "ARCHITECT", "UI_DESIGNER", "ENGINEER", "SCRIBE", "REVIEWER",
    "CRITIC", "SECRETARY", "TESTER", "RESEARCHER", "PACKAGER",
]


@dataclass
class FakeBinding:
    agent_id: str


@dataclass
class FakeMember:
    agent_id: str
    left_at: object = None


@dataclass
class FakeTeam:
    name: str
    archived: bool = False


class FakeStore:
    """Loja minima em memoria: sem disco, sem rede, sem modelo."""

    def __init__(self):
        self.bindings: dict[tuple[str, RoleName], str] = {}
        self.agents: dict[str, AgentProfile] = {}
        self.members: dict[str, list[FakeMember]] = {}
        self.teams: dict[str, FakeTeam] = {}

    def active_binding(self, team_id, role):
        agent_id = self.bindings.get((team_id, role))
        return FakeBinding(agent_id) if agent_id else None

    def get_agent(self, agent_id):
        return self.agents.get(agent_id)

    def list_memberships(self, team_id):
        return self.members.get(team_id, [])

    def get_team(self, team_id):
        return self.teams.get(team_id)

    def occupy(self, team_id, role, agent_id="agent-1", capabilities=("model.text",)):
        agent = AgentProfile(
            id=agent_id, name=f"bot-{role.value.lower()}", provider_id="local",
            model="local", role=role, capabilities=list(capabilities),
        )
        self.agents[agent_id] = agent
        self.bindings[(team_id, role)] = agent_id
        self.members.setdefault(team_id, []).append(FakeMember(agent_id))
        return agent


@pytest.fixture
def store():
    s = FakeStore()
    s.teams["lab"] = FakeTeam("ZARA Lab")
    return s


def test_onze_assentos_na_ordem_oficial():
    assert [r.value for r in FIXED_SEATS] == EXPECTED_ORDER


def test_assento_vazio_nao_inventa_agente(store):
    snap = seat_snapshot(store, "lab")
    assert len(snap) == 11
    assert all(row["status"] == "VACANT" and row["agent_id"] is None for row in snap)


def test_convite_em_assento_vazio_e_negado(store):
    with pytest.raises(InvitationDenied, match="SEAT_VACANT:CEO"):
        invited_agents(store, "lab", [RoleName.CEO], authorize=lambda a: True)


def test_turno_em_assento_vazio_e_negado(store):
    with pytest.raises(InvitationDenied, match="SEAT_VACANT"):
        run_invited_turn(store, "lab", [RoleName.CEO],
                         authorize=lambda a: True, speak=lambda a: None)


def test_time_arquivado_e_negado(store):
    store.teams["lab"].archived = True
    with pytest.raises(InvitationDenied, match="TEAM_UNAVAILABLE"):
        invited_agents(store, "lab", [RoleName.CEO], authorize=lambda a: True)


def test_papel_fora_dos_assentos_e_negado(store):
    with pytest.raises(InvitationDenied, match="ROLE_NOT_INVITABLE"):
        invited_agents(store, "lab", [RoleName.MEMBER], authorize=lambda a: True)


def test_sem_autorizacao_de_recurso_e_negado(store):
    store.occupy("lab", RoleName.CEO)
    with pytest.raises(InvitationDenied, match="RESOURCE_NOT_AUTHORIZED:CEO"):
        invited_agents(store, "lab", [RoleName.CEO], authorize=lambda a: False)


def test_assento_ocupado_e_autorizado_fala(store):
    agent = store.occupy("lab", RoleName.CEO)
    falados = []
    resultado = run_invited_turn(
        store, "lab", [RoleName.CEO],
        authorize=lambda a: True, speak=lambda a: falados.append(a.id),
    )
    assert falados == [agent.id]
    assert resultado["spoken_agent_ids"] == [agent.id]
    assert len(resultado["silent_agent_ids"]) == 0  # demais seguem vagos


def test_agente_sem_capacidade_de_texto_nao_ocupa(store):
    store.occupy("lab", RoleName.CEO, capabilities=("tools.only",))
    snap = seat_snapshot(store, "lab")
    ceo = next(row for row in snap if row["role"] == "CEO")
    assert ceo["status"] == "VACANT"


def test_time_que_nao_optou_nao_exige_assento():
    assert requires_fixed_seat(FakeTeam("Time Legado"), RoleName.CEO) is False
    assert requires_fixed_seat(FakeTeam("ZARA Lab"), RoleName.CEO) is True
    assert requires_fixed_seat(None, RoleName.CEO) is False
