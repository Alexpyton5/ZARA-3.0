"""Log interno de operações da ZARA (FRENTE D3).

O progresso detalhado do trabalho vai para cá — um JSONL local, com
rotação limitada. Nunca aparece para o Alex: a interface dele só recebe
"pronto" ou "travei" (ver core/silent_mode.py).

Regras:
  - Nunca registra parâmetros crus de ações (sem segredos, sem PII).
  - Falha de escrita nunca quebra o caminho principal (log é acessório).
  - Rotação: arquivo único limitado a ~2 MB; ao estourar, arquiva .1 e
    recomeça (mantém no máximo 2 arquivos).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.paths import user_data_dir

_MAX_BYTES = 2 * 1024 * 1024
_SENSITIVE_HINTS = ("secret", "token", "password", "senha", "key", "credential", "auth")


def _ops_path() -> Path:
    root = user_data_dir() / "data" / "ops"
    root.mkdir(parents=True, exist_ok=True)
    return root / "zara_ops.jsonl"


def _scrub(details: Any) -> Any:
    if details is None or isinstance(details, (bool, int, float)):
        return details
    if isinstance(details, dict):
        return {
            str(k)[:64]: ("<redacted>" if any(h in str(k).lower() for h in _SENSITIVE_HINTS) else _scrub(v))
            for k, v in list(details.items())[:32]
        }
    if isinstance(details, (list, tuple)):
        return [_scrub(v) for v in list(details)[:32]]
    text = str(details)
    return text[:2000]


class OpsLog:
    """Registro interno de progresso. Uso: ops_log().record(...)."""

    def __init__(self, path: Path | None = None):
        self.path = path or _ops_path()
        self._lock = threading.RLock()

    def _rotate_if_needed(self) -> None:
        try:
            if self.path.is_file() and self.path.stat().st_size >= _MAX_BYTES:
                backup = self.path.with_suffix(".jsonl.1")
                if backup.is_file():
                    backup.unlink()
                os.replace(self.path, backup)
        except OSError:
            pass

    def record(
        self,
        kind: str,
        source: str,
        message: str,
        details: Any = None,
    ) -> None:
        """Registra um evento de progresso interno. Nunca levanta exceção."""
        try:
            with self._lock:
                self._rotate_if_needed()
                entry = {
                    "ts": time.time(),
                    "kind": str(kind)[:32],
                    "source": str(source)[:64],
                    "message": str(message)[:500],
                    "details": _scrub(details),
                }
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # log interno nunca quebra o trabalho

    def recent(self, limit: int = 50, kind: str | None = None) -> list[dict]:
        """Lê os eventos mais recentes (para diagnóstico, não para o Alex)."""
        events: list[dict] = []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if kind and event.get("kind") != kind:
                        continue
                    events.append(event)
        except OSError:
            return []
        return events[-max(1, min(int(limit), 500)):]


_ops = OpsLog()


def ops_log() -> OpsLog:
    return _ops
