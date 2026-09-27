"""ZARA Lab per-bot configuration — M070.

Each bot gets: editable SOUL text, a primary model, up to five ordered
fallbacks, and one-click restore of the default. A 429-triggered model swap
is recorded in the mission room feed.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

MAX_FALLBACKS = 5

_DEFAULTS: dict[str, dict[str, Any]] = {
    "zara": {
        "soul": "Núcleo da assistente: objetiva, prestativa, fala português do Brasil.",
        "primary_model": "auto",
        "fallbacks": [],
    },
    "mentor": {
        "soul": "CEO e arquiteto do ZARA Lab: coordena a missão e prioriza com evidência.",
        "primary_model": "auto",
        "fallbacks": [],
    },
    "opencode": {
        "soul": "Lead Developer: conselho técnico objetivo, sem executar mudanças.",
        "primary_model": "zara-gemini/gemini-3.5-flash-lite",
        "fallbacks": [],
    },
    "openclaw": {
        "soul": "Agent Runtime & Evolution Director: propõe pesquisa e automação.",
        "primary_model": "google/gemini-3.5-flash-lite",
        "fallbacks": [],
    },
    "hermes": {
        "soul": "Gateway local: operações Windows com segurança.",
        "primary_model": "local",
        "fallbacks": [],
    },
}


class LabBotConfig:
    def __init__(self, db_path: Any) -> None:
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mission_bot_config (
                    bot_id TEXT PRIMARY KEY,
                    soul TEXT NOT NULL DEFAULT '',
                    primary_model TEXT NOT NULL DEFAULT 'auto',
                    fallbacks_json TEXT NOT NULL DEFAULT '[]',
                    is_default INTEGER NOT NULL DEFAULT 1,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_model_swaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    from_model TEXT NOT NULL,
                    to_model TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )
            now = time.time()
            for bot_id, default in _DEFAULTS.items():
                exists = conn.execute(
                    "SELECT bot_id FROM mission_bot_config WHERE bot_id = ?", (bot_id,)
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO mission_bot_config(bot_id, soul, primary_model,"
                        " fallbacks_json, is_default, updated_at) VALUES(?,?,?,?,?,?)",
                        (bot_id, default["soul"], default["primary_model"],
                         json.dumps(default["fallbacks"], ensure_ascii=False), 1, now),
                    )

    def get_config(self, bot_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_bot_config WHERE bot_id = ?", (bot_id.strip(),)
            ).fetchone()
            if not row:
                raise ValueError(f"Bot desconhecido: {bot_id}")
            return self._decode(dict(row))

    def list_configs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_bot_config ORDER BY bot_id"
            ).fetchall()
            return [self._decode(dict(r)) for r in rows]

    def set_config(
        self,
        bot_id: str,
        soul: str | None = None,
        primary_model: str | None = None,
        fallbacks: list[str] | None = None,
        mission: Any = None,
    ) -> dict[str, Any]:
        """Edit SOUL / primary model / ordered fallbacks (max 5)."""
        bot_id = bot_id.strip()
        self.get_config(bot_id)  # validates existence
        fields: dict[str, Any] = {"is_default": 0, "updated_at": time.time()}
        if soul is not None:
            soul = soul.strip()
            if not soul:
                raise ValueError("SOUL não pode ser vazio")
            fields["soul"] = soul
        if primary_model is not None:
            primary_model = primary_model.strip()
            if not primary_model:
                raise ValueError("Modelo principal não pode ser vazio")
            fields["primary_model"] = primary_model
        if fallbacks is not None:
            cleaned = [str(f).strip() for f in fallbacks if str(f).strip()]
            # de-duplicate preserving order
            seen: set[str] = set()
            ordered: list[str] = []
            for model in cleaned:
                if model not in seen:
                    seen.add(model)
                    ordered.append(model)
            if len(ordered) > MAX_FALLBACKS:
                raise ValueError(
                    f"Máximo de {MAX_FALLBACKS} fallbacks ordenados (recebidos {len(ordered)})"
                )
            fields["fallbacks_json"] = json.dumps(ordered, ensure_ascii=False)
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE mission_bot_config SET {assignments} WHERE bot_id = ?",
                (*fields.values(), bot_id),
            )
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(room["id"], "alex", "BOT_CONFIG_UPDATED",
                            f"{bot_id}: SOUL/modelo/fallbacks atualizados.")
        return self.get_config(bot_id)

    def restore_default(self, bot_id: str, mission: Any = None) -> dict[str, Any]:
        bot_id = bot_id.strip()
        default = _DEFAULTS.get(bot_id)
        if default is None:
            raise ValueError(f"Bot desconhecido: {bot_id}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE mission_bot_config SET soul = ?, primary_model = ?,"
                " fallbacks_json = ?, is_default = 1, updated_at = ? WHERE bot_id = ?",
                (default["soul"], default["primary_model"],
                 json.dumps(default["fallbacks"], ensure_ascii=False),
                 time.time(), bot_id),
            )
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(room["id"], "alex", "BOT_CONFIG_RESTORED",
                            f"{bot_id}: configuração padrão restaurada.")
        return self.get_config(bot_id)

    def record_429_swap(
        self, bot_id: str, from_model: str, to_model: str, reason: str = "",
        mission: Any = None,
    ) -> dict[str, Any]:
        """Log a 429-triggered model swap in the room (M070)."""
        bot_id, from_model, to_model = bot_id.strip(), from_model.strip(), to_model.strip()
        if not bot_id or not from_model or not to_model:
            raise ValueError("bot_id, from_model e to_model são obrigatórios")
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO mission_model_swaps(bot_id, from_model, to_model, reason, created_at)"
                " VALUES(?,?,?,?,?)",
                (bot_id, from_model, to_model, reason.strip(), now),
            )
            entry = {"id": cur.lastrowid, "bot_id": bot_id, "from_model": from_model,
                     "to_model": to_model, "reason": reason.strip(), "created_at": now}
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(
                room["id"], bot_id, "MODEL_429_SWAP",
                f"429 em {from_model} → trocado para {to_model}. {reason.strip()}".strip(),
            )
        return entry

    def list_swaps(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_model_swaps ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["fallbacks"] = json.loads(row.pop("fallbacks_json") or "[]")
        except Exception:
            row["fallbacks"] = []
        row["is_default"] = bool(row.get("is_default"))
        return row
