"""Testes da peca 4 da memoria compartilhada: a fiacao IPC.

Padrao da casa: unittest, roda no pytest do .venv do PC.
O dono e um duplo que grava send_response/send_error.
"""
import asyncio
import unittest

from core.lab_memory import LabMemory
from core.shared_memory_api import SharedMemoryAPI
from core.shared_memory_ipc import (
    SHARED_MEMORY_ROUTES,
    build_shared_memory_handlers,
)


def _mem():
    mem = LabMemory(now=lambda: 1700000000.0)
    mem.write("ENGINEER", "build.verde", "suite 2778/0")
    return mem


def _turns():
    return [{"role": "user", "content": "oi zara", "engine": "",
             "timestamp": 1759000001000}]


class _Msg:
    def __init__(self, request_id, payload):
        self.request_id = request_id
        self.payload = payload


class _Owner:
    def __init__(self, api=None):
        self._shared_memory_api = api
        self.responses = []
        self.errors = []

    async def send_response(self, request_id, result):
        self.responses.append((request_id, result))

    async def send_error(self, msg, text):
        self.errors.append((msg.request_id, text))


def _run(coro):
    return asyncio.run(coro)


class TestRoutes(unittest.TestCase):
    def test_rotas_registradas(self):
        self.assertEqual(
            set(SHARED_MEMORY_ROUTES),
            {"shared-memory-read", "shared-memory-validate",
             "shared-memory-describe"},
        )

    def test_build_handlers_liga_as_tres(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        self.assertEqual(set(handlers), set(SHARED_MEMORY_ROUTES))

    def test_read_devolve_visao(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-read"](
            _Msg("r1", {"spec": {"bot_id": "bot-1",
                                 "sources": ["lab", "zara"]}})))
        self.assertEqual(len(owner.responses), 1)
        self.assertEqual(len(owner.errors), 0)
        req_id, result = owner.responses[0]
        self.assertEqual(req_id, "r1")
        self.assertEqual(result["bot_id"], "bot-1")
        self.assertEqual(result["count"], 2)

    def test_read_sem_spec_erro(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-read"](_Msg("r2", {})))
        self.assertEqual(len(owner.errors), 1)
        self.assertEqual(owner.errors[0][0], "r2")

    def test_read_spec_invalida_erro_em_portugues(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-read"](
            _Msg("r3", {"spec": {"bot_id": "x",
                                 "sources": ["terra-do-nunca"]}})))
        self.assertEqual(len(owner.errors), 1)
        self.assertIn("desconhecida", owner.errors[0][1])

    def test_validate_ok(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-validate"](
            _Msg("r4", {"spec": {"bot_id": "bot-9"}})))
        self.assertEqual(len(owner.responses), 1)
        self.assertEqual(owner.responses[0][1]["bot_id"], "bot-9")

    def test_validate_invalida_erro(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-validate"](
            _Msg("r5", {"spec": {"bot_id": ""}})))
        self.assertEqual(len(owner.errors), 1)

    def test_describe(self):
        owner = _Owner(api=SharedMemoryAPI(
            lab_memory=_mem(), zara_turns=_turns))
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-describe"](_Msg("r6", {})))
        self.assertEqual(len(owner.responses), 1)
        self.assertEqual(owner.responses[0][1]["sources"], ["lab", "zara"])


class TestApiOfWiring(unittest.TestCase):
    def test_api_injetada_e_reusada(self):
        api = SharedMemoryAPI(lab_memory=_mem(), zara_turns=_turns)
        owner = _Owner(api=api)
        handlers = build_shared_memory_handlers(owner)
        _run(handlers["shared-memory-describe"](_Msg("r7", {})))
        self.assertIs(owner._shared_memory_api, api)

    def test_cria_api_do_historico_do_dono(self):
        from core.shared_memory_ipc import _api_of

        class Hist:
            def list_recent(self, limit=50):
                return _turns()

        owner = _Owner(api=None)
        owner.conversation_history = Hist()
        api = _api_of(owner)
        self.assertIsInstance(api, SharedMemoryAPI)
        result = api.read_view({"bot_id": "w", "sources": ["zara"]})
        self.assertEqual(result["count"], 1)
        # segunda chamada reusa a mesma api
        self.assertIs(_api_of(owner), api)


if __name__ == "__main__":
    unittest.main()
