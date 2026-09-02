"""ZARA-SNIPPET-FINDER-001 (Alex, 2026-08-28)

Peca isolada. Tabela FIXA de trechos de codigo comuns -- decisao deliberada
de nao usar IA aqui: e busca por topico conhecido, nao geracao livre, entao
uma tabela fechada e mais rapida (zero latencia) e mais confiavel (nunca
inventa sintaxe errada) do que uma chamada de modelo.
"""
from __future__ import annotations

_SNIPPETS: dict[str, str] = {
    "httpx_async": (
        "import httpx\n\n"
        "async def fetch(url: str) -> str:\n"
        "    async with httpx.AsyncClient() as client:\n"
        "        response = await client.get(url)\n"
        "        response.raise_for_status()\n"
        "        return response.text\n"
    ),
    "read_file": (
        "from pathlib import Path\n\n"
        "content = Path('arquivo.txt').read_text(encoding='utf-8')\n"
    ),
    "write_file": (
        "from pathlib import Path\n\n"
        "Path('arquivo.txt').write_text('conteúdo', encoding='utf-8')\n"
    ),
    "fastapi_route": (
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/status')\n"
        "async def status():\n"
        "    return {'ok': True}\n"
    ),
    "read_json": (
        "import json\n"
        "from pathlib import Path\n\n"
        "data = json.loads(Path('dados.json').read_text(encoding='utf-8'))\n"
    ),
    "context_manager": (
        "from contextlib import contextmanager\n\n"
        "@contextmanager\n"
        "def recurso():\n"
        "    print('abrindo')\n"
        "    try:\n"
        "        yield\n"
        "    finally:\n"
        "        print('fechando')\n"
    ),
    "dataclass": (
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Ponto:\n"
        "    x: int\n"
        "    y: int\n"
    ),
}

# Sinônimos -> chave real em _SNIPPETS, pra aceitar frase natural sem
# duplicar o snippet em si.
_ALIASES: dict[str, str] = {
    "requisicao assincrona": "httpx_async",
    "requisição assíncrona": "httpx_async",
    "http assincrono": "httpx_async",
    "ler arquivo": "read_file",
    "leitura de arquivo": "read_file",
    "escrever arquivo": "write_file",
    "salvar arquivo": "write_file",
    "rota fastapi": "fastapi_route",
    "endpoint fastapi": "fastapi_route",
    "ler json": "read_json",
    "gerenciador de contexto": "context_manager",
    "context manager": "context_manager",
}


def get_code_snippet(topic: str) -> str:
    """Devolve o bloco de código pro tópico pedido, ou uma mensagem
    honesta com os tópicos disponíveis se não reconhecer -- nunca inventa
    sintaxe pra um tópico que não está na tabela."""
    key = " ".join(str(topic or "").strip().lower().split())
    resolved = key if key in _SNIPPETS else _ALIASES.get(key)

    if resolved is None:
        available = ", ".join(sorted(_SNIPPETS))
        return f"Não tenho um snippet pronto para '{topic}'. Tópicos disponíveis: {available}."
    return _SNIPPETS[resolved]
