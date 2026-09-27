"""Read-only Agency roster discovery for Lab V1.

Catalog presence does not authorize membership, a turn, or a provider call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROSTER_FILENAME = 'agency-agents.json'
MAX_ROSTER_BYTES = 2 * 1024 * 1024
MAX_AGENTS = 1000


def default_roster_directory() -> Path:
    """Mirror the per-user ZARA data location without creating any directory."""
    configured_home = os.environ.get('ZARA3_HOME')
    base = Path(configured_home) if configured_home else Path(
        os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
    ) / 'ZARA3'
    return base / 'data'


def _result(status: str, agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = agents or []
    return {'status': status, 'count': len(records), 'agents': records,
            'dispatch_enabled': False}


def inspect_agency_roster(
    configured_path: str | None, *, default_directory: Path | str,
) -> dict[str, Any]:
    """Inspect an Agency catalog without changing team membership or dispatching it.

    A configured path must be absolute and must name ``agency-agents.json``.
    Without one, the per-user ZARA data directory is checked. Missing or
    malformed input never produces runnable participants.
    """
    if configured_path is not None and not isinstance(configured_path, str):
        return _result('INVALID_CONFIG')
    path = Path(configured_path) if configured_path else Path(default_directory) / ROSTER_FILENAME
    if not path.is_absolute() or path.name.casefold() != ROSTER_FILENAME:
        return _result('INVALID_CONFIG')
    if path.drive.upper() == 'D:':
        return _result('INVALID_CONFIG')
    try:
        path = path.resolve(strict=False)
        if path.drive.upper() == 'D:' or path.name.casefold() != ROSTER_FILENAME:
            return _result('INVALID_CONFIG')
        if not path.exists():
            return _result('DORMANT')
        if not path.is_file() or path.stat().st_size > MAX_ROSTER_BYTES:
            return _result('INVALID')
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _result('INVALID')

    if isinstance(raw, dict):
        if raw.get('schema_version', 1) != 1:
            return _result('INVALID')
        items = raw.get('agents')
    else:
        items = raw  # Compatibility with the legacy top-level list.
    if not isinstance(items, list) or len(items) > MAX_AGENTS:
        return _result('INVALID')

    agents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            return _result('INVALID')
        agent_id, name = item.get('id'), item.get('name')
        capabilities = item.get('capabilities', [])
        description = item.get('description', '')
        if (not isinstance(agent_id, str) or not agent_id.strip()
                or not isinstance(name, str) or not name.strip()
                or not isinstance(capabilities, list)
                or any(not isinstance(cap, str) or not cap.strip() for cap in capabilities)
                or not isinstance(description, str)):
            return _result('INVALID')
        key = agent_id.strip().casefold()
        if key in seen:
            return _result('INVALID')
        seen.add(key)
        agents.append({'id': agent_id.strip(), 'name': name.strip(),
                       'capabilities': [cap.strip() for cap in capabilities],
                       'description': description.strip(), 'source': 'agency'})
    return _result('READY' if agents else 'DORMANT', agents)
