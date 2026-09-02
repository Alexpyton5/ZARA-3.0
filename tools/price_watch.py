"""ZARA-PRICE-WATCH-001 (Alex, 2026-08-28). Peça isolada.

`web_search`/`web_fetch` (core/actions/web.py) já existem no ActionRegistry
-- este módulo é a camada de cima: busca (via DuckDuckGo HTML, sem chave de
API) e extrai preço em Real de um texto (regex, sem IA). Rede real só em
`search_product_prices`/`fetch_page_text`; `extract_prices_from_text` é pura
e testável offline.
"""
from __future__ import annotations

import re

_PRICE_RE = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})")
_DEFAULT_TIMEOUT_S = 15.0


def extract_prices_from_text(text: str) -> list[float]:
    """Acha valores em R$ num texto e devolve como float (ponto decimal).
    Formato fechado (R$ 1.234,56) de propósito -- não tenta adivinhar
    outros formatos de moeda."""
    values: list[float] = []
    for match in _PRICE_RE.findall(str(text or "")):
        normalized = match.replace(".", "").replace(",", ".")
        try:
            values.append(float(normalized))
        except ValueError:
            continue
    return values


def search_product_prices(query: str, *, max_results: int = 5, timeout_s: float = _DEFAULT_TIMEOUT_S) -> list[dict]:
    """Busca o termo no DuckDuckGo (HTML, sem chave de API) e devolve
    título/link/preços encontrados no snippet de cada resultado. []
    honesto quando a rede falhar ou não achar nada -- nunca inventa preço."""
    text = str(query or "").strip()
    if not text:
        return []

    try:
        import httpx
    except Exception:
        return []

    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": text},
            headers={"User-Agent": "Mozilla/5.0 (ZARA price-watch)"},
            timeout=timeout_s,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return []
    except Exception:
        return []

    return parse_duckduckgo_html(response.text, max_results=max_results)


def parse_duckduckgo_html(html: str, *, max_results: int = 5) -> list[dict]:
    """Parser leve (regex) do HTML de resultado do DuckDuckGo -- separado
    da chamada de rede pra ser testável com HTML estático."""
    results: list[dict] = []
    blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    for url, title_html, snippet_html in blocks[:max_results]:
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "prices": extract_prices_from_text(snippet),
        })
    return results
