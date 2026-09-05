"""Web Search Skill — wraps core web search action."""
from __future__ import annotations

from core.action_registry import get_registry
from core.actions.web import web_search_action

PLUGIN = {
    "name": "web_search",
    "description": (
        "Search the web using DuckDuckGo (no API key required). "
        "Returns title, URL, and snippet for each result. Use for general questions, "
        "fact-checking, finding current information. "
        "Does NOT fetch full page content (use web_fetch for that)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "Search query",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Max results (default: 10, max: 10)",
                "default": 10,
                "minimum": 1,
                "maximum": 10,
            },
            "region": {
                "type": "STRING",
                "description": "Region code (default: wt-wt)",
                "default": "wt-wt",
            },
            "timeout": {
                "type": "NUMBER",
                "description": "Total search deadline in seconds (default: 30)",
                "default": 30,
                "minimum": 0.1,
                "maximum": 30,
            },
        },
        "required": ["query"],
    },
    "category": "web",
    "version": "1.0.0",
    "author": "ZARA",
}


def run(parameters: dict, context=None) -> str:
    query = parameters.get("query")
    if not query:
        return "Erro: 'query' é obrigatório para web_search."

    registry = get_registry()

    try:
        result = registry.execute(
            "web_search",
            query=query,
            max_results=parameters.get("max_results", 10),
            region=parameters.get("region", "wt-wt"),
            timeout=parameters.get("timeout", 30),
        )

        if result.success:
            # Format results nicely for speech
            data = result.data
            results = data.get("results", [])
            if not results:
                return f"Nenhum resultado encontrado para: {query}"

            # Build spoken response
            spoken_parts = [f"Encontrei {len(results)} resultado(s) para '{query}'."]
            for i, res in enumerate(results[:3], 1):  # Speak top 3
                title = res.get("title", "Sem título")
                snippet = res.get("snippet", "")
                spoken_parts.append(f"{i}. {title}. {snippet}")

            if len(results) > 3:
                spoken_parts.append(f"E mais {len(results) - 3} resultado(s).")

            return " ".join(spoken_parts)
        return f"Falha na busca: {result.error}"
    except Exception as e:
        return f"Erro na skill web_search: {e}"