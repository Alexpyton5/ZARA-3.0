"""ZARA Lab roles — M050 (discussão natural e equipe dinâmica).

Fixed council roles plus a specialist pool fed by Alex's Agent Agency roster.
The CEO recruits specialists per task; every recruitment is logged to the
mission room feed so speech always corresponds to a real run record.

The Agency roster (the 313 agents Alex already has in the Zara Lab) is loaded
from ``agency-agents.json`` in the data dir when present. Each entry looks
like: {"name": "Agente X", "capabilities": ["pesquisa"], "description": "..."}.
When the file is absent, recruitment falls back to the built-in catalog.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

# Fixed council roles. ``can_run`` mirrors the Lab rule: council-only
# participation; production writes stay behind the approval gate.
FIXED_ROLES: tuple[dict[str, Any], ...] = (
    {
        "id": "ceo",
        "name": "CEO",
        "member": "mentor",
        "description": "Coordena a missão, convoca especialistas e prioriza propostas.",
        "can_run": True,
    },
    {
        "id": "reader",
        "name": "Leitor",
        "member": "openclaw",
        "description": "Lê o vault Obsidian permitido e entrega achados ao CEO.",
        "can_run": True,
    },
    {
        "id": "engineer",
        "name": "Engenheiro",
        "member": "opencode",
        "description": "Executa runs reais de engenharia no worktree isolado.",
        "can_run": True,
    },
    {
        "id": "reviewer",
        "name": "Revisor",
        "member": "zara",
        "description": "Revisão independente de patches e verificações.",
        "can_run": False,
    },
)

# Built-in fallback catalog used when no agency-agents.json roster exists.
BUILTIN_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "researcher",
        "name": "Pesquisador",
        "capabilities": ["pesquisa", "leitura", "fontes"],
        "description": "Pesquisa pública com URL e data visíveis.",
        "source": "builtin",
    },
    {
        "id": "analyst",
        "name": "Analista",
        "capabilities": ["análise", "dados", "diagnóstico"],
        "description": "Analisa achados e sugere priorização.",
        "source": "builtin",
    },
    {
        "id": "writer",
        "name": "Redator",
        "capabilities": ["texto", "documentação", "resumo"],
        "description": "Redige cartões, resumos e documentação da missão.",
        "source": "builtin",
    },
)

AGENCY_ROSTER_FILENAME = "agency-agents.json"


def load_agency_roster(data_dir: Path | str | None) -> list[dict[str, Any]]:
    """Load Alex's Agent Agency roster from ``agency-agents.json``.

    Returns an empty list when the file is missing or invalid — the caller
    then falls back to the built-in catalog.
    """
    if not data_dir:
        return []
    path = Path(data_dir) / AGENCY_ROSTER_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw if isinstance(raw, list) else raw.get("agents", [])
    roster: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        roster.append(
            {
                "id": str(item.get("id") or f"agency-{i}"),
                "name": name,
                "capabilities": [str(c) for c in (item.get("capabilities") or [])],
                "description": str(item.get("description") or ""),
                "source": "agency",
            }
        )
    return roster


def list_roles() -> list[dict[str, Any]]:
    return [dict(r) for r in FIXED_ROLES]


def list_specialists(roster: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Specialist pool: Alex's Agency roster when available, else built-in."""
    if roster:
        return [dict(s) for s in roster]
    return [dict(s) for s in BUILTIN_CATALOG]


def recruit_specialists(
    task: str,
    needed_capabilities: list[str] | None = None,
    mission: Any = None,
    roster: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """CEO recruits specialists for a task (M050).

    Matches ``needed_capabilities`` against the Agency roster (or the
    built-in catalog when no roster is loaded). The recruitment is logged
    to the mission room feed.
    """
    task = task.strip()
    if not task:
        raise ValueError("Tarefa vazia")
    needed = {str(c).strip().lower() for c in (needed_capabilities or []) if str(c).strip()}
    pool = list_specialists(roster)
    recruited: list[dict[str, Any]] = []
    for spec in pool:
        caps = {str(c).lower() for c in spec.get("capabilities", [])}
        if not needed or needed & caps:
            recruited.append(spec)
    recruitment_id = f"RECRUIT-{uuid.uuid4().hex[:6].upper()}"
    names = ", ".join(s["name"] for s in recruited) or "nenhum especialista disponível"
    if mission is not None:
        room = mission.ensure_room()
        mission.log_feed(
            room["id"], "ceo", "SPECIALISTS_RECRUITED",
            f"{recruitment_id}: [{names}] convocados para: {task}",
        )
    return {
        "id": recruitment_id,
        "task": task,
        "recruited": recruited,
        "pool_size": len(pool),
        "pool_source": "agency" if roster else "builtin",
        "created_at": time.time(),
    }
