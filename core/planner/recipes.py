"""Receitas multi-step prontas para o Planner — NÃO é arquitetura nova.

Cada função aqui só monta `explicit_steps` (dicts) para um `PlannerRequest`,
reaproveitando tools que já existem em `core/actions/*.py`. Nenhuma delas
executa nada — quem executa é sempre `core.planner.execution.execute_plan`.

Restrição de propósito desta fase: nenhum step pode depender do RESULTADO
de um step anterior (o Planner ainda não faz binding dinâmico de argumento
entre steps — isso seria fundação nova, fora do escopo desta missão). Toda
receita aqui é desenhada para funcionar sem isso: ou porque a segunda tool
opera sobre estado compartilhado (a página atual do browser), ou porque
ambos os argumentos já são conhecidos de antemão pelo chamador.
"""
from __future__ import annotations

from urllib.parse import quote_plus


def browser_search_and_screenshot(query: str, screenshot_path: str = "") -> list[dict]:
    """"Abra o navegador, pesquise X e tire uma captura da página."

    browser_navigate muda a página atual do contexto Playwright;
    browser_screenshot captura essa mesma página — não precisa saber nada
    que só existiria depois do navigate rodar.
    """
    text = str(query or "").strip()
    if not text:
        raise ValueError("query vazia")
    search_url = f"https://www.google.com/search?q={quote_plus(text)}"
    return [
        {
            "id": "navigate",
            "tool_name": "browser_navigate",
            "arguments": {"url": search_url},
            "description": f"Pesquisar '{text}'",
        },
        {
            "id": "screenshot",
            "tool_name": "browser_screenshot",
            "arguments": ({"path": screenshot_path} if screenshot_path else {}),
            "description": "Capturar a página de resultados",
            "depends_on": ["navigate"],
        },
    ]


def browser_search_and_extract(query: str, selectors: dict[str, str]) -> list[dict]:
    """"Pesquise X e extraia [seletores conhecidos] da página de resultado."

    `selectors` é fornecido pelo chamador (ex.: {"first_result": "h3"}) —
    não depende de nada que o navigate produza em runtime.
    """
    text = str(query or "").strip()
    if not text:
        raise ValueError("query vazia")
    if not selectors:
        raise ValueError("selectors vazio")
    search_url = f"https://www.google.com/search?q={quote_plus(text)}"
    return [
        {
            "id": "navigate",
            "tool_name": "browser_navigate",
            "arguments": {"url": search_url},
            "description": f"Pesquisar '{text}'",
        },
        {
            "id": "extract",
            "tool_name": "browser_extract",
            "arguments": {"selectors": selectors},
            "description": "Extrair dados da página de resultados",
            "depends_on": ["navigate"],
        },
    ]


def screenshot_and_ocr(image_path: str, lang: str = "por+eng") -> list[dict]:
    """"Tire um print da tela e leia o texto que está nela."

    Ambos os steps recebem o MESMO `image_path`, combinado de antemão pelo
    chamador — vision_ocr não precisa do retorno de vision_screenshot para
    saber onde ler.
    """
    path = str(image_path or "").strip()
    if not path:
        raise ValueError("image_path vazio")
    return [
        {
            "id": "screenshot",
            "tool_name": "vision_screenshot",
            "arguments": {"path": path},
            "description": "Capturar a tela",
        },
        {
            "id": "ocr",
            "tool_name": "vision_ocr",
            "arguments": {"image_path": path, "lang": lang},
            "description": "Ler o texto da captura",
            "depends_on": ["screenshot"],
        },
    ]


def list_folder_and_summarize_file(folder_path: str, file_path: str) -> list[dict]:
    """"Liste os arquivos da pasta X e resuma o arquivo Y."

    `file_path` é conhecido de antemão pelo chamador (ex.: "resuma o
    README.md da pasta X") — não precisa vir do resultado do files_list.
    """
    folder = str(folder_path or "").strip()
    target = str(file_path or "").strip()
    if not folder or not target:
        raise ValueError("folder_path e file_path são obrigatórios")
    return [
        {
            "id": "list",
            "tool_name": "files_list",
            "arguments": {"path": folder},
            "description": f"Listar arquivos em '{folder}'",
        },
        {
            "id": "summarize",
            "tool_name": "files_text_summary",
            "arguments": {"path": target},
            "description": f"Resumir '{target}'",
            "depends_on": ["list"],
        },
    ]
