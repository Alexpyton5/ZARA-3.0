from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage


class Project:
    def list_docs(self): return ["state"]
    def get_doc(self, key): return {"title": "Estado real", "content": "CONTEUDO_PROJETO_35", "updated_at": 1}
    def load_mentor_context(self): return "CONTEXTO_REAL_35"


class User:
    def list(self):
        return [
            {"id": "u1", "category": "preference", "fact": "FATO_REAL_35", "status": "active", "source": "voice", "updated_at": 2},
            {"id": "u2", "category": "preference", "fact": "NAO_EXIBIR", "status": "forgotten", "source": "voice"},
        ]


class History:
    def list_recent(self, limit):
        assert limit == 30
        return [{"id": "h1", "role": "user", "content": "HISTORICO_REAL_35", "timestamp": 3}]


def handler(project=Project(), user=User(), history=History()):
    instance = IPCHandler.__new__(IPCHandler)
    instance.project_memory = project
    instance.user_memory = user
    instance.conversation_history = history
    instance.responses = []

    async def send_response(request_id, response=None, **_kwargs):
        instance.responses.append(response)

    instance.send_response = send_response
    return instance


@pytest.mark.asyncio
async def test_memory_galaxy_uses_real_sources_and_content_matches():
    instance = handler()
    await instance.handle_memory_galaxy_list(IPCMessage(type="memory-galaxy-list", payload={}, request_id="g1"))
    response = instance.responses[0]
    assert response["read_only"] is True
    assert response["count"] == 4
    assert {node["kind"] for node in response["nodes"]} == {"project", "user", "context", "history"}
    contents = {node["content"] for node in response["nodes"]}
    assert {"CONTEUDO_PROJETO_35", "FATO_REAL_35", "CONTEXTO_REAL_35", "HISTORICO_REAL_35"} <= contents
    assert "NAO_EXIBIR" not in contents


@pytest.mark.asyncio
async def test_memory_galaxy_empty_sources_are_honest_and_add_no_fake_nodes():
    instance = handler(None, None, None)
    await instance.handle_memory_galaxy_list(IPCMessage(type="memory-galaxy-list", payload={}, request_id="g2"))
    response = instance.responses[0]
    assert response["nodes"] == []
    assert response["count"] == 0
    assert set(response["sources"].values()) == {"OFFLINE"}
