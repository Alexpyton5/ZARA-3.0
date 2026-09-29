"""Testes determinísticos locais do grupo único do ZARA Lab (group_chat).

Sem mock de modelo, sem provider, sem rede: só SQLite temporário.
"""
from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path

try:
    from core.lab_v1.group_chat import (
        GROUP_SESSION_ID,
        GROUP_TEAM_NAME,
        EngineError,
        MentionResolutionError,
        agent_inbox,
        answer_inbox,
        ensure_group_chat,
        mirror_journal,
        post_agent_message,
        post_user_message,
        read_thread,
        reply_to,
        speak_with_engine,
    )
    from core.lab_v1.domain import (
        AgentProfile, Availability, ProviderResult, RoleName, TeamMembership,
        new_id,
    )
    from core.lab_v1.store import LabStore
except ImportError:  # execução direta na cópia de trabalho plana
    from group_chat import (  # type: ignore[no-redef]
        GROUP_SESSION_ID,
        GROUP_TEAM_NAME,
        EngineError,
        MentionResolutionError,
        agent_inbox,
        answer_inbox,
        ensure_group_chat,
        mirror_journal,
        post_agent_message,
        post_user_message,
        read_thread,
        reply_to,
        speak_with_engine,
    )
    from domain import AgentProfile, Availability, ProviderResult, RoleName, TeamMembership, new_id  # type: ignore[no-redef]
    from store import LabStore  # type: ignore[no-redef]


class GroupChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LabStore(db_path=Path(self._tmp.name) / "grupo.db")
        self.session = ensure_group_chat(self.store)
        self.team_id = self.session.team_id

    def tearDown(self) -> None:
        # No Windows, uma conexão SQLite presa em ciclo de referência segura
        # o arquivo do banco; o gc explícito fecha antes de apagar o diretório
        # (no Linux isso nunca aparece — unlink de arquivo aberto é permitido).
        self.store = None
        self.session = None
        gc.collect()
        self._tmp.cleanup()

    def _add_agent(self, agent_id: str, name: str) -> AgentProfile:
        agent = AgentProfile(
            id=agent_id,
            name=name,
            provider_id="test",
            model="test-model",
            role=RoleName.ENGINEER,
        )
        self.store.save_agent(agent)
        self.store.save_membership(
            TeamMembership(id=new_id("mem"), team_id=self.team_id, agent_id=agent_id)
        )
        return agent

    # 1. ensure_group_chat idempotente
    def test_ensure_group_chat_idempotente(self) -> None:
        first = ensure_group_chat(self.store)
        second = ensure_group_chat(self.store)
        self.assertEqual(first.id, GROUP_SESSION_ID)
        self.assertEqual(second.id, GROUP_SESSION_ID)
        self.assertEqual(first.team_id, second.team_id)
        teams = [t for t in self.store.list_teams() if t.name == GROUP_TEAM_NAME]
        self.assertEqual(len(teams), 1)
        self.assertFalse(teams[0].archived)

    # 2. dois agentes trocam @menção; resposta via reply_to; thread em ordem
    def test_mencao_e_resposta_entre_agentes(self) -> None:
        self._add_agent("ag_a", "Alfa")
        self._add_agent("ag_b", "Beta")

        posted = post_agent_message(
            self.store, self.session.id, "ag_a", "@Beta, revisa o plano?"
        )
        self.assertEqual(posted["to_agent_id"], "ag_b")
        self.assertEqual(posted["kind"], "AGENT")

        inbox_b = agent_inbox(self.store, self.session.id, "ag_b")
        self.assertEqual([m["id"] for m in inbox_b], [posted["id"]])

        answer = reply_to(
            self.store, self.session.id, "ag_b", posted["id"], "Revisado, tá ok."
        )
        self.assertEqual(answer["reply_to"], posted["id"])
        self.assertEqual(answer["to_agent_id"], "ag_a")
        self.assertEqual(answer["correlation_id"], posted["correlation_id"])

        thread = read_thread(self.store, self.session.id)
        self.assertEqual([m["id"] for m in thread], [posted["id"], answer["id"]])

        # A mensagem original foi respondida: ninguém tem pendência.
        self.assertEqual(agent_inbox(self.store, self.session.id, "ag_a"), [])
        self.assertEqual(agent_inbox(self.store, self.session.id, "ag_b"), [])

    # 3. broadcast do Alex aparece para ambos no read_thread
    def test_broadcast_do_alex(self) -> None:
        self._add_agent("ag_a", "Alfa")
        self._add_agent("ag_b", "Beta")
        msg = post_user_message(self.store, self.session.id, "Alex", "Bom dia, time!")
        self.assertIsNone(msg["to_agent_id"])
        self.assertEqual(msg["to_role"], "ALL")
        self.assertEqual(msg["kind"], "USER")
        thread = read_thread(self.store, self.session.id)
        self.assertIn(msg["id"], [m["id"] for m in thread])

    # 4. @desconhecido levanta MentionResolutionError (fail-closed)
    def test_mencao_desconhecida_falha_fechada(self) -> None:
        with self.assertRaises(MentionResolutionError):
            post_user_message(
                self.store, self.session.id, "Alex", "@fulano_que_nao_existe oi"
            )

    def test_multiplas_mencoes_sao_rejeitadas(self) -> None:
        self._add_agent("ag_a", "Alfa")
        self._add_agent("ag_b", "Beta")
        with self.assertRaises(MentionResolutionError):
            post_agent_message(
                self.store, self.session.id, "ag_a", "@Beta e @Alfa, oi"
            )

    # 5. remetente fora do time é rejeitado
    def test_remetente_fora_do_time_rejeitado(self) -> None:
        outsider = AgentProfile(
            id="ag_x", name="X", provider_id="test", model="test-model"
        )
        self.store.save_agent(outsider)  # sem membership
        with self.assertRaises(ValueError):
            post_agent_message(self.store, self.session.id, "ag_x", "oi")

    def test_remetente_arquivado_rejeitado(self) -> None:
        agent = self._add_agent("ag_y", "Ipsilon")
        agent.archived = True
        self.store.save_agent(agent)
        with self.assertRaises(ValueError):
            post_agent_message(self.store, self.session.id, "ag_y", "oi")

    def test_remetente_nao_responde_a_propria_mensagem(self) -> None:
        self._add_agent("ag_a", "Alfa")
        with self.assertRaises(ValueError):
            post_agent_message(
                self.store, self.session.id, "ag_a", "oi", to_agent_id="ag_a"
            )

    def test_reply_so_pelo_destinatario_canonico(self) -> None:
        self._add_agent("ag_a", "Alfa")
        self._add_agent("ag_b", "Beta")
        self._add_agent("ag_c", "Ceci")
        posted = post_agent_message(self.store, self.session.id, "ag_a", "@Beta oi")
        with self.assertRaises(ValueError):
            reply_to(self.store, self.session.id, "ag_c", posted["id"], "não sou eu")
        with self.assertRaises(ValueError):
            reply_to(self.store, self.session.id, "ag_b", "msg_inexistente", "oi")

    def test_mirror_journal_nunca_quebra(self) -> None:
        result = mirror_journal(self.store, {"content": "teste de espelho"})
        self.assertIn("mirrored", result)
        self.assertIsInstance(result["mirrored"], bool)


class _StubAdapter:
    """Adapter de mentira SÓ para testar a fiação (sem rede).

    A escada real (fallback.py) já foi testada de verdade pela FRENTE 2;
    aqui o que está sob teste é: escada -> chamada -> Run -> post.
    """

    id = "stub"

    def __init__(self, text="resposta do motor", ok=True):
        self.text = text
        self.ok = ok
        self.calls = []

    def probe(self):
        from types import SimpleNamespace
        return SimpleNamespace(availability=Availability.AVAILABLE, detail="ok")

    def invoke(self, *, prompt, model, system=None, timeout_s=120, **kwargs):
        self.calls.append({"prompt": prompt, "model": model})
        if self.ok:
            return ProviderResult(
                ok=True, text=self.text, availability=Availability.AVAILABLE,
                model_reported=model,
            )
        return ProviderResult(
            ok=False, availability=Availability.ERROR, error="motor quebrou",
        )


class _StubRegistry:
    def __init__(self, adapter):
        self._adapter = adapter
        self.recorded = []

    def get(self, provider_id):
        return self._adapter

    def record_result(self, provider_id, model, result):
        self.recorded.append((provider_id, model, result.ok))


class _StubRuntime:
    def __init__(self, store, adapter):
        self.store = store
        self.registry = _StubRegistry(adapter)


class EngineSpeechTests(unittest.TestCase):
    """O assento fala pela escada: Run de prova + mensagem postada."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LabStore(db_path=Path(self._tmp.name) / "grupo.db")
        self.session = ensure_group_chat(self.store)
        self.team_id = self.session.team_id

    def tearDown(self) -> None:
        self.store = None
        self.session = None
        gc.collect()
        self._tmp.cleanup()

    def _add_agent(self, agent_id, name, role=RoleName.ENGINEER):
        agent = AgentProfile(
            id=agent_id, name=name, provider_id="nvidia",
            model="moonshotai/kimi-k3", role=role,
            capabilities=["model.text"],
        )
        self.store.save_agent(agent)
        self.store.save_membership(
            TeamMembership(id=new_id("m"), team_id=self.team_id, agent_id=agent_id)
        )
        return agent

    def _runtime(self, text="resposta do motor", ok=True):
        return _StubRuntime(self.store, _StubAdapter(text=text, ok=ok))

    def test_speak_posts_engine_text_with_run_proof(self):
        self._add_agent("a1", "Teca")
        runtime = self._runtime(text="olá do motor")
        result = speak_with_engine(
            runtime, GROUP_SESSION_ID, "a1", prompt="diga olá",
        )
        message = result["message"]
        self.assertEqual(message["content"], "olá do motor")
        self.assertEqual(message["author_agent_id"], "a1")
        self.assertEqual(message["run_id"], result["run_id"])
        # A escada do ENGINEER começa no degrau grátis da NVIDIA.
        self.assertEqual(result["provider_id"], "nvidia")
        run = self.store.get_run(result["run_id"])
        self.assertIsNotNone(run)
        self.assertEqual(run.state.value, "COMPLETED")
        self.assertEqual(run.model, "moonshotai/kimi-k3")

    def test_speak_fails_closed_when_ladder_fails(self):
        self._add_agent("a1", "Teca")
        runtime = self._runtime(ok=False)
        before = len(read_thread(self.store, GROUP_SESSION_ID))
        with self.assertRaises(EngineError):
            speak_with_engine(runtime, GROUP_SESSION_ID, "a1", prompt="diga olá")
        # Nada foi postado e o Run ficou como falha (prova honesta).
        self.assertEqual(len(read_thread(self.store, GROUP_SESSION_ID)), before)
        runs = self.store.list_runs(GROUP_SESSION_ID)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].state.value, "FAILED")

    def test_answer_inbox_replies_with_engine(self):
        self._add_agent("a1", "Teca")
        self._add_agent("b1", "Beto", role=RoleName.SCRIBE)
        post_agent_message(self.store, GROUP_SESSION_ID, "a1", "@Beto me ajuda?")
        runtime = self._runtime(text="claro, estou aqui")
        result = answer_inbox(runtime, GROUP_SESSION_ID, "b1")
        self.assertIsNotNone(result)
        message = result["message"]
        self.assertEqual(message["content"], "claro, estou aqui")
        self.assertIsNotNone(message["reply_to"])
        self.assertEqual(message["author_agent_id"], "b1")
        # A escada do SCRIBE também começa no grátis.
        self.assertEqual(result["provider_id"], "nvidia")
        # Sem pendência, devolve None e não chama motor nenhum.
        runtime2 = self._runtime()
        self.assertIsNone(answer_inbox(runtime2, GROUP_SESSION_ID, "b1"))
        self.assertEqual(len(runtime2.registry._adapter.calls), 0)


if __name__ == "__main__":
    unittest.main()
