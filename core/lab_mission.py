"""ZARA Lab Living Team Mission — ZARA-LAB-LIVING-TEAM-20260925.

Persistent mission engine for the Lab council room:

- M010 — single persistent room ("ZARA Core"), single chronological feed,
  mission cards, reopening on the active mission.
- M020 — resume incomplete work on open; when nothing is pending, start exactly
  one cycle; restarts never duplicate cycles, messages, tasks or patches.
- Milestone rule (mission-wide): a milestone may only move to ``done`` when
  evidence references are provided AND Alex confirms. Code, isolated tests or
  bot speech alone are never enough — this is enforced in
  :meth:`LabMission.set_milestone_state`.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

MISSION_ID = "ZARA-LAB-LIVING-TEAM-20260925"
ROOM_NAME = "ZARA Core"

STATE_DONE = "done"
STATE_PARTIAL = "partial"
STATE_PENDING = "pending"
_VALID_STATES = {STATE_DONE, STATE_PARTIAL, STATE_PENDING}

# Seed definition: (code, title, description, initial_state, initial_evidence)
_MILESTONES: tuple[tuple[str, str, str, str, list[str]], ...] = (
    (
        "M000",
        "Verdade operacional",
        "Identidade, hashes, árvore de processos, interface inicial real, banco, "
        "leases, histórico ambíguo, worktree e rollback reconciliados.",
        STATE_DONE,
        [".unlazy/zara-lab-living-team-20260925/M000/FACTS.md"],
    ),
    (
        "M010",
        "Sala persistente",
        "Uma entrada ZARA Core, feed cronológico único, cartões de missões novas "
        "e reabertura na missão ativa.",
        STATE_PARTIAL,
        [".unlazy/zara-lab-living-team-20260925/GATES.md"],
    ),
    (
        "M020",
        "Inicialização e retomada",
        "Retomar trabalho incompleto ao abrir; sem trabalho pendente, iniciar um "
        "único ciclo; reiniciar sem duplicar chamadas, mensagens, tarefas ou patches.",
        STATE_PARTIAL,
        [".unlazy/zara-lab-living-team-20260925/GATES.md"],
    ),
    (
        "M030",
        "Obsidian verdadeiro",
        "Leitor, CEO, engenheiro e revisor consultam o mesmo vault permitido com "
        "fonte e data visíveis.",
        STATE_PARTIAL,
        [".unlazy/zara-lab-living-team-20260925/M030/GATES.md"],
    ),
    (
        "M040",
        "Leitura e pesquisa proativas",
        "Leitores entregam achados de source ao CEO; pesquisa pública mostra URL e "
        "data; CEO prioriza uma proposta ou justifica não alterar.",
        STATE_PENDING,
        [],
    ),
    (
        "M050",
        "Discussão natural e equipe dinâmica",
        "CEO convoca especialistas conforme a tarefa, inclusive do catálogo Agent "
        "Agency; falas em português correspondem a runs reais e mostram decisões.",
        STATE_PENDING,
        [],
    ),
    (
        "M060",
        "Código, validação, revisão e promoção",
        "Uma melhoria pequena atravessa patch delimitado, verificação real, revisão "
        "independente e política de promoção, com diff e artefatos visíveis.",
        STATE_PENDING,
        [],
    ),
    (
        "M070",
        "Configuração por bot e fallback",
        "Editor de SOUL, modelo principal, até cinco fallbacks ordenados e "
        "restauração do padrão; troca por 429 registrada na sala.",
        STATE_PENDING,
        [],
    ),
    (
        "M080",
        "Build único e ciclo completo",
        "Build oficial com SHA256 e ponteiro atualizado; uma ZARA aberta; sala, "
        "retomada, pesquisa, recrutamento e melhoria real comprovados no pacote.",
        STATE_PENDING,
        [],
    ),
)


class LabMission:
    """Persistent state machine for the Living Team mission."""

    def __init__(self, db_path: Any) -> None:
        self.db_path = str(db_path)

    # ------------------------------------------------------------------ #
    # storage
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """Create tables, ensure the single room and seed milestones (idempotent)."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mission_rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    mission_id TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_milestones (
                    mission_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    state TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (mission_id, code)
                );
                CREATE TABLE IF NOT EXISTS mission_feed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(room_id) REFERENCES mission_rooms(id)
                );
                CREATE TABLE IF NOT EXISTS mission_cycles (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mission_cards (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
        self.ensure_room()
        self._seed_milestones()

    def ensure_room(self, name: str = ROOM_NAME) -> dict[str, Any]:
        """Return the single persistent room, creating it once (M010)."""
        now = time.time()
        room_id = f"room-{name.lower().replace(' ', '-')}"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_rooms WHERE name = ?", (name,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE mission_rooms SET is_active = 1, mission_id = ?, updated_at = ? WHERE id = ?",
                    (MISSION_ID, now, row["id"]),
                )
                return dict(row)
            conn.execute(
                "INSERT INTO mission_rooms(id, name, mission_id, is_active, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?)",
                (room_id, name, MISSION_ID, 1, now, now),
            )
            conn.execute(
                "INSERT INTO mission_feed(room_id, actor, event, detail, created_at)"
                " VALUES(?,?,?,?,?)",
                (room_id, "system", "ROOM_CREATED",
                 f"Sala persistente '{name}' criada para a missão {MISSION_ID}.", now),
            )
            row = conn.execute(
                "SELECT * FROM mission_rooms WHERE id = ?", (room_id,)
            ).fetchone()
            return dict(row)

    def _seed_milestones(self) -> None:
        now = time.time()
        with self._connect() as conn:
            for code, title, description, state, evidence in _MILESTONES:
                exists = conn.execute(
                    "SELECT code FROM mission_milestones WHERE mission_id = ? AND code = ?",
                    (MISSION_ID, code),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO mission_milestones(mission_id, code, title, description, state, evidence_json, updated_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (MISSION_ID, code, title, description, state,
                     json.dumps(evidence, ensure_ascii=False), now),
                )

    # ------------------------------------------------------------------ #
    # milestones
    # ------------------------------------------------------------------ #
    def list_milestones(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, title, description, state, evidence_json, updated_at"
                " FROM mission_milestones WHERE mission_id = ? ORDER BY code",
                (MISSION_ID,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
            except Exception:
                item["evidence"] = []
            out.append(item)
        return out

    def set_milestone_state(
        self,
        code: str,
        state: str,
        evidence: list[str] | None = None,
        confirmed_by: str | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        """Move a milestone to a new state.

        Mission rule enforced here: ``done`` requires at least one evidence
        reference AND explicit confirmation by Alex. Anything else raises.
        """
        code = code.strip().upper()
        state = state.strip().lower()
        if state not in _VALID_STATES:
            raise ValueError(f"Estado inválido: {state}")
        evidence = [str(e).strip() for e in (evidence or []) if str(e).strip()]
        if state == STATE_DONE:
            if not evidence:
                raise ValueError(
                    f"{code}: marcar como concluído exige referências de evidência "
                    "(FACTS.md/GATES.md, captura do pacote, etc.)."
                )
            if (confirmed_by or "").strip().lower() != "alex":
                raise ValueError(
                    f"{code}: marcar como concluído exige confirmação explícita do Alex."
                )
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT code FROM mission_milestones WHERE mission_id = ? AND code = ?",
                (MISSION_ID, code),
            ).fetchone()
            if not row:
                raise ValueError(f"Marco desconhecido: {code}")
            conn.execute(
                "UPDATE mission_milestones SET state = ?, evidence_json = ?, updated_at = ?"
                " WHERE mission_id = ? AND code = ?",
                (state, json.dumps(evidence, ensure_ascii=False), now, MISSION_ID, code),
            )
        room = self.ensure_room()
        self.log_feed(
            room["id"], confirmed_by or "system", "MILESTONE_STATE",
            f"{code} → {state.upper()}. {note}".strip(),
        )
        return {"code": code, "state": state, "evidence": evidence}

    # ------------------------------------------------------------------ #
    # feed (single chronological feed per room — M010)
    # ------------------------------------------------------------------ #
    def log_feed(self, room_id: str, actor: str, event: str, detail: str = "") -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO mission_feed(room_id, actor, event, detail, created_at)"
                " VALUES(?,?,?,?,?)",
                (room_id, actor.strip() or "system", event.strip(), detail.strip(), now),
            )
            entry_id = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM mission_feed WHERE id = ?", (entry_id,)
            ).fetchone()
            return dict(row)

    def get_feed(self, room_id: str, limit: int = 80) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_feed WHERE room_id = ?"
                " ORDER BY created_at ASC, id ASC LIMIT ?",
                (room_id, max(1, min(limit, 500))),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # cycles — resume incomplete work, never duplicate (M020)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cycle_key(objective: str) -> str:
        normalized = " ".join(objective.strip().lower().split())
        return f"{MISSION_ID}:{normalized}"

    def resume_or_start_cycle(self, objective: str) -> dict[str, Any]:
        """M020: resume the open cycle if one exists, else start exactly one.

        Idempotent: calling twice with the same objective never creates a
        second cycle; restarts return the already-open cycle.
        """
        objective = objective.strip()
        if not objective:
            raise ValueError("Objetivo vazio")
        key = self._cycle_key(objective)
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_cycles WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row:
                cycle = dict(row)
                if cycle["status"] == "OPEN":
                    conn.execute(
                        "UPDATE mission_cycles SET updated_at = ? WHERE id = ?",
                        (now, cycle["id"]),
                    )
                    cycle["resumed"] = True
                    return cycle
                cycle["resumed"] = False
                cycle["reopened"] = False
                return cycle
            # No cycle for this objective: is there any other OPEN cycle?
            other = conn.execute(
                "SELECT * FROM mission_cycles WHERE mission_id = ? AND status = 'OPEN'"
                " ORDER BY updated_at DESC LIMIT 1",
                (MISSION_ID,),
            ).fetchone()
            if other:
                cycle = dict(other)
                cycle["resumed"] = True
                cycle["note"] = "Ciclo anterior ainda aberto foi retomado em vez de criar um novo."
                conn.execute(
                    "UPDATE mission_cycles SET updated_at = ? WHERE id = ?",
                    (now, cycle["id"]),
                )
                return cycle
            cycle_id = f"CYCLE-{uuid.uuid4().hex[:8].upper()}"
            conn.execute(
                "INSERT INTO mission_cycles(id, mission_id, objective, status, idempotency_key, summary, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (cycle_id, MISSION_ID, objective, "OPEN", key, "", now, now),
            )
            row = conn.execute(
                "SELECT * FROM mission_cycles WHERE id = ?", (cycle_id,)
            ).fetchone()
            cycle = dict(row)
            cycle["resumed"] = False
        room = self.ensure_room()
        self.log_feed(room["id"], "system", "CYCLE_STARTED", f"{cycle_id}: {objective}")
        return cycle

    def complete_cycle(self, cycle_id: str, summary: str = "") -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_cycles WHERE id = ?", (cycle_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Ciclo desconhecido: {cycle_id}")
            conn.execute(
                "UPDATE mission_cycles SET status = 'DONE', summary = ?, updated_at = ? WHERE id = ?",
                (summary.strip(), now, cycle_id),
            )
            updated = dict(conn.execute(
                "SELECT * FROM mission_cycles WHERE id = ?", (cycle_id,)
            ).fetchone())
        room = self.ensure_room()
        self.log_feed(room["id"], "system", "CYCLE_COMPLETED", f"{cycle_id}: {summary.strip()}")
        return updated

    def active_cycle(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_cycles WHERE mission_id = ? AND status = 'OPEN'"
                " ORDER BY updated_at DESC LIMIT 1",
                (MISSION_ID,),
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # mission cards (M010)
    # ------------------------------------------------------------------ #
    def create_card(self, title: str, summary: str) -> dict[str, Any]:
        title, summary = title.strip(), summary.strip()
        if not title or not summary:
            raise ValueError("Título e resumo do cartão são obrigatórios")
        now = time.time()
        card_id = f"CARD-{uuid.uuid4().hex[:6].upper()}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO mission_cards(id, mission_id, title, summary, status, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (card_id, MISSION_ID, title, summary, "OPEN", now, now),
            )
            row = conn.execute(
                "SELECT * FROM mission_cards WHERE id = ?", (card_id,)
            ).fetchone()
        room = self.ensure_room()
        self.log_feed(room["id"], "alex", "MISSION_CARD_CREATED", f"{card_id}: {title}")
        return dict(row)

    def list_cards(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_cards WHERE mission_id = ? ORDER BY updated_at DESC",
                (MISSION_ID,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # snapshot
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict[str, Any]:
        room = self.ensure_room()
        return {
            "mission_id": MISSION_ID,
            "room": room,
            "milestones": self.list_milestones(),
            "feed": self.get_feed(room["id"]),
            "active_cycle": self.active_cycle(),
            "cards": self.list_cards(),
        }
