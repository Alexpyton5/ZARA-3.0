"""Versioned, Windows-safe agent customization profiles.

Profiles are data, not executable instructions.  They let the owner edit an
agent's soul, model preference and permissions without changing Python code.
Every write keeps a JSON snapshot and a Markdown soul file, plus a bounded
history for rollback/audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Mapping


_MAX_SOUL = 24000
_MAX_HISTORY = 30
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SENSITIVE = re.compile(r"(?:api[_-]?key|password|passwd|secret|token|bearer)\s*[:=]", re.I)


class AgentProfileError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_json(v) for v in value]
    return str(value)


class AgentProfileStore:
    """Persistent profiles rooted in the app data directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _validate_id(self, agent_id: str) -> str:
        value = str(agent_id or "").strip()
        if not _SAFE_ID.fullmatch(value):
            raise AgentProfileError("agent_id inválido")
        return value

    def _paths(self, agent_id: str) -> tuple[Path, Path, Path]:
        agent_id = self._validate_id(agent_id)
        folder = self.root / agent_id
        return folder / "profile.json", folder / "soul.md", folder / "history.json"

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return default

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)

    def _default(self, agent_id: str) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "provider_id": "codex_cli",
            "model": None,
            "permissions": ["read_workspace", "write_sandbox", "run_tests"],
            "version": 0,
            "updated_at": None,
        }

    def get(self, agent_id: str) -> dict[str, Any]:
        profile_path, soul_path, history_path = self._paths(agent_id)
        with self._lock:
            profile = self._read_json(profile_path, self._default(agent_id))
            if not isinstance(profile, dict):
                profile = self._default(agent_id)
            profile = {**self._default(agent_id), **_safe_json(profile)}
            try:
                profile["soul"] = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""
            except OSError:
                profile["soul"] = ""
            history = self._read_json(history_path, [])
            profile["history_count"] = len(history) if isinstance(history, list) else 0
            profile["history"] = list(reversed(history)) if isinstance(history, list) else []
            return profile

    def history(self, agent_id: str) -> list[dict[str, Any]]:
        """Return newest-first immutable profile snapshots for owner rollback."""
        _, _, history_path = self._paths(agent_id)
        with self._lock:
            history = self._read_json(history_path, [])
            if not isinstance(history, list):
                return []
            return list(reversed([dict(item) for item in history if isinstance(item, dict)]))

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for folder in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
            if folder.is_dir() and _SAFE_ID.fullmatch(folder.name):
                rows.append(self.get(folder.name))
        return rows

    @staticmethod
    def validate_update(*, soul: str | None = None, provider_id: str | None = None,
                        model: str | None = None, permissions: list[str] | None = None) -> None:
        if soul is not None:
            soul = str(soul)
            if len(soul) > _MAX_SOUL:
                raise AgentProfileError("soul.md excede o limite permitido")
            if _SENSITIVE.search(soul):
                raise AgentProfileError("soul.md não pode conter credenciais")
        if provider_id is not None:
            provider_id = str(provider_id).strip()
            if not provider_id or len(provider_id) > 80:
                raise AgentProfileError("provider_id inválido")
        if model is not None and len(str(model).strip()) > 160:
            raise AgentProfileError("modelo inválido")
        if permissions is not None:
            if not isinstance(permissions, list) or len(permissions) > 32:
                raise AgentProfileError("permissões inválidas")
            if any(len(str(item).strip()) > 120 for item in permissions):
                raise AgentProfileError("permissão excede o limite")

    def update(self, agent_id: str, *, soul: str | None = None,
               provider_id: str | None = None, model: str | None = None,
               permissions: list[str] | None = None) -> dict[str, Any]:
        profile_path, soul_path, history_path = self._paths(agent_id)
        with self._lock:
            self.validate_update(soul=soul, provider_id=provider_id, model=model,
                                 permissions=permissions)
            current = self.get(agent_id)
            if soul is not None:
                soul = str(soul)
                current["soul"] = soul
            if provider_id is not None:
                provider_id = str(provider_id).strip()
                current["provider_id"] = provider_id
            if model is not None:
                model = str(model).strip()
                current["model"] = model or None
            if permissions is not None:
                clean = [str(item).strip() for item in permissions if str(item).strip()]
                current["permissions"] = sorted(set(clean), key=str.casefold)
            history = self._read_json(history_path, [])
            if not isinstance(history, list):
                history = []
            previous = {key: value for key, value in current.items() if key not in {"soul", "history", "history_count"}}
            version = int(current.get("version") or 0) + 1
            current.update({"version": version, "updated_at": _now(), "agent_id": agent_id})
            history.append({**previous, "soul": current.get("soul", ""), "version": version, "updated_at": current["updated_at"]})
            history = history[-_MAX_HISTORY:]
            disk_profile = {key: value for key, value in current.items() if key not in {"soul", "history", "history_count"}}
            self._atomic_text(profile_path, json.dumps(disk_profile, ensure_ascii=False, indent=2))
            self._atomic_text(soul_path, current.get("soul", ""))
            self._atomic_text(history_path, json.dumps(history, ensure_ascii=False, indent=2))
            current["history_count"] = len(history)
            current["history"] = list(reversed(history))
            return current

    def rollback(self, agent_id: str, version: int) -> dict[str, Any]:
        _, _, history_path = self._paths(agent_id)
        history = self._read_json(history_path, [])
        if not isinstance(history, list):
            raise AgentProfileError("histórico inválido")
        target = next((item for item in history if int(item.get("version", -1)) == int(version)), None)
        if not isinstance(target, dict):
            raise AgentProfileError("versão não encontrada")
        return self.update(agent_id, soul=target.get("soul", ""),
                           provider_id=target.get("provider_id"),
                           model=target.get("model"),
                           permissions=target.get("permissions", []))


__all__ = ["AgentProfileError", "AgentProfileStore"]
