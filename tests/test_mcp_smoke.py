"""Smoke test da camada MCP base — protocolo JSON-RPC e identidade.

Alvo da auditoria de restauração (seção 20/08/2026): os módulos
core/mcp/* e core/obsidian_bridge estavam com **0% de cobertura real**, ou
seja, sem nenhum teste rodando sobre eles. São os suspeitos mais prováveis
das funcionalidades perdidas pela ZARA.

Este smoke cobre o núcleo funcional puro (protocolo MCP e identidade), que
não depende de serviço externo nem de hardware — roda offline e de forma
determinística. O que cair aqui indica regressão no protocolo; o que
continuar verde garante a base de server discovery.
"""

from __future__ import annotations

from core.identity import ASSISTANT_NAME, LEGACY_ASSISTANT_NAMES, WAKE_ALIASES, WAKE_WORD
from core.mcp.base_server import (
    MCPErrorCode,
    MCPPrompt,
    MCPRequest,
    MCPResource,
    MCPServer,
    MCPTool,
)

# ---------------------------------------------------------------------------
# Identidade
# ---------------------------------------------------------------------------

def test_identidade_nome_principal():
    """O nome de produto e a palavra de ativação são estáveis."""
    assert ASSISTANT_NAME == "ZARA"
    assert WAKE_WORD == "ZARA"


def test_identidade_aliases_nao_vazios():
    """Sempre existe um conjunto de acionadores de voz."""
    assert len(WAKE_ALIASES) > 0
    assert "ZARA" in WAKE_ALIASES


def test_identidade_nomes_legados_congelados():
    """Nomes antigos (JARVIS/ZOE) seguem reconhecidos como legado."""
    assert "J.A.R.V.I.S" in LEGACY_ASSISTANT_NAMES
    assert "ZOE" in LEGACY_ASSISTANT_NAMES


# ---------------------------------------------------------------------------
# Registro de tools / resources / prompts
# ---------------------------------------------------------------------------

def test_registrar_tool_via_decorator():
    srv = MCPServer("smoke")
    calls: list[int] = []

    @srv.tool("soma", "soma dois inteiros", {"type": "object", "properties": {}})
    async def _soma(a: int, b: int):
        calls.append(1)
        return {"resultado": a + b}

    assert "soma" in srv._tools
    assert srv.get_capabilities()["tools"] == ["soma"]
    assert len(calls) == 0  # registro não executa o handler


def test_registrar_resource_e_prompt():
    srv = MCPServer("smoke")

    @srv.resource("zara://versao", "Versão", "versão do produto")
    async def _versao():
        return {"versao": "3.0.0"}

    @srv.prompt("cumprimento", "saudação", [{"name": "nome", "description": "nome do usuário"}])
    async def _cumprimento(nome: str):
        return [{"role": "assistant", "content": f"Oi, {nome}!"}]

    caps = srv.get_capabilities()
    assert caps["resources"] == ["zara://versao"]
    assert caps["prompts"] == ["cumprimento"]


# ---------------------------------------------------------------------------
# Protocolo JSON-RPC — handle_request
# ---------------------------------------------------------------------------

async def test_initialize_retorna_capabilities():
    srv = MCPServer("smoke")
    resp = await srv.handle_request(
        MCPRequest(id=1, method="initialize", params={"clientInfo": {"name": "test"}})
    )
    assert resp.error is None
    assert resp.result["serverInfo"]["name"] == "smoke"
    assert "tools" in resp.result["capabilities"]
    assert srv._initialized is True


async def test_tools_list_retorna_schema():
    srv = MCPServer("smoke")

    @srv.tool("eco", "eco", {"type": "object"})
    async def _eco(texto: str):
        return {"eco": texto}

    resp = await srv.handle_request(MCPRequest(id=2, method="tools/list"))
    assert resp.error is None
    assert resp.result["tools"][0]["name"] == "eco"
    assert "inputSchema" in resp.result["tools"][0]


async def test_tool_call_executa_handler():
    srv = MCPServer("smoke")

    @srv.tool("soma", "soma", {"type": "object"})
    async def _soma(a: int, b: int):
        return {"resultado": a + b}

    resp = await srv.handle_request(
        MCPRequest(id=3, method="tools/call", params={"name": "soma", "arguments": {"a": 2, "b": 3}})
    )
    assert resp.error is None
    assert resp.result == {"resultado": 5}


async def test_tool_call_inexistente_da_TOOL_NOT_FOUND():
    srv = MCPServer("smoke")
    resp = await srv.handle_request(
        MCPRequest(id=4, method="tools/call", params={"name": "nao_existe"})
    )
    assert resp.error is not None
    assert resp.error["code"] == MCPErrorCode.TOOL_NOT_FOUND.value


async def test_handler_dentro_do_tool_que_falha_vira_erro_interno():
    srv = MCPServer("smoke")

    @srv.tool("quebra", "quebra", {"type": "object"})
    async def _quebra():
        raise RuntimeError("boom")

    resp = await srv.handle_request(
        MCPRequest(id=5, method="tools/call", params={"name": "quebra", "arguments": {}})
    )
    assert resp.error is not None
    assert resp.error["code"] == MCPErrorCode.INTERNAL_ERROR.value


async def test_resource_read_retorna_conteudo():
    srv = MCPServer("smoke")

    @srv.resource("zara://status", "Status", "status")
    async def _status():
        return {"ok": True}

    resp = await srv.handle_request(
        MCPRequest(id=6, method="resources/read", params={"uri": "zara://status"})
    )
    assert resp.error is None
    assert resp.result["contents"][0]["text"] == '{"ok": true}'


async def test_resource_inexistente_da_RESOURCE_NOT_FOUND():
    srv = MCPServer("smoke")
    resp = await srv.handle_request(
        MCPRequest(id=7, method="resources/read", params={"uri": "zara://nada"})
    )
    assert resp.error is not None
    assert resp.error["code"] == MCPErrorCode.RESOURCE_NOT_FOUND.value


async def test_prompt_get_retorna_mensagens():
    srv = MCPServer("smoke")

    @srv.prompt("cumprimento", "saudação")
    async def _cumprimento(nome: str):
        return [{"role": "assistant", "content": f"Oi, {nome}!"}]

    resp = await srv.handle_request(
        MCPRequest(id=8, method="prompts/get", params={"name": "cumprimento", "arguments": {"nome": "Ana"}})
    )
    assert resp.error is None
    assert resp.result["messages"][0]["content"] == "Oi, Ana!"


async def test_methodo_desconhecido_da_METHOD_NOT_FOUND():
    srv = MCPServer("smoke")
    resp = await srv.handle_request(MCPRequest(id=9, method="nao_existe"))
    assert resp.error is not None
    assert resp.error["code"] == MCPErrorCode.METHOD_NOT_FOUND.value


async def test_notifications_initialized_marca_inicializado():
    srv = MCPServer("smoke")
    assert srv._initialized is False
    resp = await srv.handle_request(MCPRequest(id=10, method="notifications/initialized"))
    assert srv._initialized is True
    assert resp.error is None


def test_error_response_to_dict_sera_json_serializavel():
    srv = MCPServer("smoke")
    resp = srv._error_response(42, MCPErrorCode.INTERNAL_ERROR, "x")
    d = resp.to_dict()
    assert d["jsonrpc"] == "2.0"
    assert d["id"] == 42
    assert d["error"]["code"] == MCPErrorCode.INTERNAL_ERROR.value


def test_dataclasses_registram_campos():
    """Os dataclasses de definição (tool/resource/prompt) guardam os campos
    obrigatórios sem perder nada — garante que clientes que leiam o schema
    não tropecem em atributo inexistente."""
    tool = MCPTool(name="t", description="d", input_schema={})
    assert tool.name == "t" and tool.description == "d"
    res = MCPResource(uri="u", name="n", description="d")
    assert res.uri == "u" and res.mime_type == "text/plain"
    pr = MCPPrompt(name="p", description="d")
    assert pr.name == "p" and pr.arguments == []
