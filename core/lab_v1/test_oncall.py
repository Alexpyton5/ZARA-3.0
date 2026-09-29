"""Testes do plantão elástico (oncall).

Banco SQLite temporário; sem rede, sem modelo, sem API paga.
"""
from __future__ import annotations

import gc
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_flat_package_shim() -> None:
    """Mapeia `core.lab_v1.*` para os arquivos lado a lado deste diretório.

    No checkout real esses módulos vivem no pacote `core.lab_v1`; aqui em
    `lab_v1_origem/` eles estão achatados. O shim aponta o `__path__` do
    pacote para este diretório para o teste rodar igual nos dois lugares.
    """
    if "core.lab_v1" in sys.modules:
        return
    base = str(Path(__file__).resolve().parent)
    core_pkg = types.ModuleType("core")
    core_pkg.__path__ = [base]
    lab_pkg = types.ModuleType("core.lab_v1")
    lab_pkg.__path__ = [base]
    paths_mod = types.ModuleType("core.paths")
    paths_mod.data_dir = lambda: Path(tempfile.gettempdir()) / "zara_lab_v1_test"
    sys.modules["core"] = core_pkg
    sys.modules["core.lab_v1"] = lab_pkg
    sys.modules["core.paths"] = paths_mod


_install_flat_package_shim()

try:
    from core.lab_v1.domain import AgentProfile, Lifecycle, RoleName, Team, TeamMembership, new_id
    from core.lab_v1.store import LabStore
    from core.lab_v1.mentions import MentionResolutionError, resolve_mentions
    from core.lab_v1.oncall import (
        OncallError,
        count_oncall,
        list_oncall,
        register_oncall,
        stand_down,
    )
except ImportError:  # Allows direct execution from the project checkout.
    from domain import AgentProfile, Lifecycle, RoleName, Team, TeamMembership, new_id
    from store import LabStore
    from mentions import MentionResolutionError, resolve_mentions
    from oncall import (
        OncallError,
        count_oncall,
        list_oncall,
        register_oncall,
        stand_down,
    )


class OncallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_tmp)
        self.store = LabStore(Path(self._tmp.name) / "lab.db")
        self.store.initialize()
        self.team_id = "team_plantao"
        self.store.save_team(Team(id=self.team_id, name="Time Plantão"))

    def _cleanup_tmp(self) -> None:
        # No Windows, uma conexão SQLite presa em ciclo de referência segura
        # o arquivo do banco; o gc explícito fecha antes de apagar o diretório
        # (no Linux isso nunca aparece — unlink de arquivo aberto é permitido).
        self.store = None
        gc.collect()
        self._tmp.cleanup()

    def _register(self, name: str, **kwargs) -> AgentProfile:
        params = {"provider_id": "nvidia", "model": "kimi-k3"}
        params.update(kwargs)
        return register_oncall(self.store, self.team_id, name=name, **params)

    def test_register_two_plantonistas_list_sorted_and_counted(self) -> None:
        zeca = self._register("Zeca")
        ana = self._register("Ana", model="nemotron-3")

        self.assertEqual(zeca.lifecycle, Lifecycle.TEMPORARY)
        self.assertEqual(ana.lifecycle, Lifecycle.TEMPORARY)

        oncall = list_oncall(self.store, self.team_id)
        self.assertEqual([agent.name for agent in oncall], ["Ana", "Zeca"])
        self.assertEqual(count_oncall(self.store, self.team_id), 2)

    def test_duplicate_active_name_is_rejected_case_insensitive(self) -> None:
        self._register("Zeca")
        with self.assertRaises(OncallError):
            self._register("zeca")
        with self.assertRaises(OncallError):
            self._register("  ZECA  ")

    def test_name_must_have_1_to_80_chars(self) -> None:
        with self.assertRaises(OncallError):
            self._register("")
        with self.assertRaises(OncallError):
            self._register("   ")
        with self.assertRaises(OncallError):
            self._register("x" * 81)
        ok = self._register("y" * 80)
        self.assertEqual(len(ok.name), 80)

    def test_permanent_members_are_not_oncall(self) -> None:
        fixed = AgentProfile(
            id=new_id("agent"), name="Chefe", provider_id="anthropic",
            model="claude-opus-5", role=RoleName.CEO,
            lifecycle=Lifecycle.PERMANENT,
        )
        self.store.save_agent(fixed)
        self.store.save_membership(
            TeamMembership(id=new_id("membership"), team_id=self.team_id, agent_id=fixed.id)
        )
        self._register("Zeca")

        self.assertEqual([agent.name for agent in list_oncall(self.store, self.team_id)], ["Zeca"])
        self.assertEqual(count_oncall(self.store, self.team_id), 1)

    def test_mention_resolves_new_plantonista(self) -> None:
        zeca = self._register("Zeca")

        resolved = resolve_mentions(self.store, self.team_id, "Oi @Zeca, me ajuda aqui")
        self.assertEqual(resolved, [zeca.id])

    def test_stand_down_removes_from_mentions_but_keeps_history(self) -> None:
        zeca = self._register("Zeca")
        self.assertEqual(resolve_mentions(self.store, self.team_id, "@Zeca oi"), [zeca.id])

        stand_down(self.store, self.team_id, zeca.id)

        self.assertEqual(list_oncall(self.store, self.team_id), [])
        self.assertEqual(count_oncall(self.store, self.team_id), 0)
        with self.assertRaises(MentionResolutionError):
            resolve_mentions(self.store, self.team_id, "@Zeca oi")

        # Histórico preservado: agente continua no banco e a membership
        # antiga segue lá, só que encerrada.
        self.assertIsNotNone(self.store.get_agent(zeca.id))
        memberships = self.store.list_memberships(self.team_id)
        self.assertEqual(len(memberships), 1)
        self.assertEqual(memberships[0].agent_id, zeca.id)
        self.assertIsNotNone(memberships[0].left_at)

    def test_stand_down_unknown_agent_fails(self) -> None:
        with self.assertRaises(OncallError):
            stand_down(self.store, self.team_id, "agent_inexistente")

    def test_name_can_be_reused_after_stand_down(self) -> None:
        zeca = self._register("Zeca")
        stand_down(self.store, self.team_id, zeca.id)

        zeca2 = self._register("Zeca")
        self.assertNotEqual(zeca2.id, zeca.id)
        self.assertEqual(resolve_mentions(self.store, self.team_id, "@Zeca oi"), [zeca2.id])


if __name__ == "__main__":
    unittest.main()
