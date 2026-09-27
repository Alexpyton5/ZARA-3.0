"""ZARA LAB REAL V1 — synchronous SQLite persistence.

Why synchronous
---------------
The runtime above this module already owns its own threading/async story
(see `core/lab_coordinator.py` for the pattern this mirrors: plain
`sqlite3`, one connection per call, `asyncio.to_thread` at the call site
when the caller is async). Baking async into the store itself would just
move that decision into a place that cannot see the caller's event loop.

Why a brand-new DB file
------------------------
`lab/zara_lab.db` (LAB-AUTONOMY-001, see `core/lab_coordinator.py`) is a
council room with its own schema and its own meaning for "task" and
"message". This store never opens it, never migrates it, and does not
reuse any of its table names — V1 owns `lab/zara_lab_v1.db` alone, as
required by `core/lab_v1/domain.py`.

Row-shape rule
--------------
Every `save_*` method takes and returns the dataclass from `domain.py`
unchanged. Enums are persisted as their `.value` string and rehydrated
with the matching enum constructor; JSON-shaped fields (`list[str]`,
`dict`) are stored as TEXT and decoded on read. Nothing here invents a
field domain.py does not already declare.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.lab_v1.domain import (
    AgentProfile,
    Artifact,
    CapabilityGap,
    CostBasis,
    Decision,
    Handoff,
    LabEvent,
    LabLesson,
    Lifecycle,
    Message,
    MessageKind,
    RoleBinding,
    RoleName,
    Run,
    RunState,
    Session,
    SessionState,
    Task,
    TaskState,
    Team,
    TeamMembership,
)
from core.paths import data_dir

SCHEMA_VERSION = 1


class LabStore:
    """Synchronous SQLite persistence for the V1 Lab domain."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (data_dir() / "lab" / "zara_lab_v1.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """Idempotent schema creation. Safe to call every process start."""
        if self._initialized:
            return
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    role TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    capabilities TEXT NOT NULL DEFAULT '[]',
                    lifecycle TEXT NOT NULL,
                    reports_to TEXT,
                    fallback_agent_id TEXT,
                    effort TEXT,
                    max_turns INTEGER NOT NULL DEFAULT 1,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS role_bindings (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    designation TEXT NOT NULL DEFAULT 'PERMANENT',
                    bound_at REAL NOT NULL,
                    unbound_at REAL,
                    reason TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS team_memberships (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    joined_at REAL NOT NULL,
                    left_at REAL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    state TEXT NOT NULL,
                    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
                    max_delegations INTEGER NOT NULL DEFAULT 4,
                    max_cost_usd REAL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deleted_sessions (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id), deleted_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_authorities (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
                    owner TEXT NOT NULL CHECK(owner IN ('V1','MISSION')),
                    token TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author_agent_id TEXT,
                    run_id TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    model_reported TEXT,
                    state TEXT NOT NULL,
                    task_id TEXT,
                    provider_session_id TEXT,
                    cost_usd REAL,
                    cost_basis TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    duration_ms INTEGER,
                    error TEXT,
                    started_at REAL NOT NULL,
                    ended_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    created_by_agent_id TEXT NOT NULL,
                    assigned_agent_id TEXT,
                    state TEXT NOT NULL,
                    acceptance TEXT NOT NULL DEFAULT '',
                    result TEXT,
                    max_turns INTEGER NOT NULL DEFAULT 1,
                    budget_usd REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);

                CREATE TABLE IF NOT EXISTS handoffs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    from_agent_id TEXT,
                    to_agent_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    context_summary TEXT NOT NULL DEFAULT '',
                    unfinished_task_ids TEXT NOT NULL DEFAULT '[]',
                    outcome TEXT NOT NULL DEFAULT 'COMPLETED',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_handoffs_session ON handoffs(session_id);

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    author_agent_id TEXT,
                    statement TEXT NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_id TEXT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    path TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);

                CREATE TABLE IF NOT EXISTS capability_gaps (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    required TEXT NOT NULL,
                    available INTEGER NOT NULL DEFAULT 0,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_capability_gaps_session
                    ON capability_gaps(session_id);

                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    session_id TEXT,
                    entity_id TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    occurred_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);

                CREATE TABLE IF NOT EXISTS memory_outbox (
                    event_id TEXT PRIMARY KEY,
                    memory_ref TEXT,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lab_lessons (
                    id TEXT PRIMARY KEY,
                    source_event_id TEXT NOT NULL UNIQUE,
                    source_session_id TEXT,
                    statement TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lab_lessons_created
                    ON lab_lessons(created_at DESC);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._migrate_additive_columns(conn)
        self._initialized = True

    def _migrate_additive_columns(self, conn: sqlite3.Connection) -> None:
        """Additive-only migrations for columns added after a DB already
        exists on disk.

        `CREATE TABLE IF NOT EXISTS` above does nothing once the table
        already exists, so a column added later (e.g. `runs.model_reported`)
        would silently never appear on an existing `zara_lab_v1.db`. This
        checks `PRAGMA table_info` and runs `ALTER TABLE ... ADD COLUMN`
        only when the column is missing. Never drops or recreates a table:
        that would destroy real mission history that already happened.
        """
        existing_run_columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        if 'effort' not in existing_run_columns:
            conn.execute('ALTER TABLE runs ADD COLUMN effort TEXT')
        if "model_reported" not in existing_run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN model_reported TEXT")

        # Phase 1 "Organization": message addressing. Additive only — legacy
        # rows keep NULL in every new column, which reads as implicit
        # addressing (legible by every role).
        existing_message_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        for column in ("to_agent_id", "to_role", "reply_to", "correlation_id"):
            if column not in existing_message_columns:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {column} TEXT")

    # ------------------------------------------------------------------
    # Team
    # ------------------------------------------------------------------

    def save_team(self, team: Team) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO teams(id, name, objective, created_at, archived)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, objective=excluded.objective,
                    archived=excluded.archived
                """,
                (team.id, team.name, team.objective, team.created_at, int(team.archived)),
            )

    def get_team(self, team_id: str) -> Team | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
        return self._row_to_team(row) if row else None

    def list_teams(self, include_archived: bool = False) -> list[Team]:
        query = "SELECT * FROM teams"
        if not include_archived:
            query += " WHERE archived=0"
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [self._row_to_team(r) for r in rows]

    @staticmethod
    def _row_to_team(row: sqlite3.Row) -> Team:
        return Team(
            id=row["id"], name=row["name"], objective=row["objective"],
            created_at=row["created_at"], archived=bool(row["archived"]),
        )

    # ------------------------------------------------------------------
    # Agent
    # ------------------------------------------------------------------
    # AgentProfile has no `team_id` field — membership to a team is its own
    # dataclass (TeamMembership), on purpose: an agent can belong to more
    # than one team over its life, and a team's roster at a point in time
    # is a query, not a foreign key on the agent. So `list_agents(team_id=…)`
    # joins through team_memberships (open ones: left_at IS NULL) instead of
    # adding a column domain.py does not declare.

    def save_agent(self, agent: AgentProfile) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents(
                    id, name, provider_id, model, role, instructions, capabilities,
                    lifecycle, reports_to, fallback_agent_id, effort, max_turns,
                    archived, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, provider_id=excluded.provider_id,
                    model=excluded.model, role=excluded.role,
                    instructions=excluded.instructions, capabilities=excluded.capabilities,
                    lifecycle=excluded.lifecycle, reports_to=excluded.reports_to,
                    fallback_agent_id=excluded.fallback_agent_id, effort=excluded.effort,
                    max_turns=excluded.max_turns, archived=excluded.archived
                """,
                (
                    agent.id, agent.name, agent.provider_id, agent.model, agent.role.value,
                    agent.instructions, json.dumps(list(agent.capabilities)),
                    agent.lifecycle.value, agent.reports_to, agent.fallback_agent_id,
                    agent.effort, agent.max_turns, int(agent.archived), agent.created_at,
                ),
            )

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return self._row_to_agent(row) if row else None

    def list_agents(
        self, team_id: str | None = None, include_archived: bool = False
    ) -> list[AgentProfile]:
        params: list[Any] = []
        if team_id is not None:
            query = (
                "SELECT agents.* FROM agents "
                "JOIN team_memberships ON team_memberships.agent_id = agents.id "
                "WHERE team_memberships.team_id=? AND team_memberships.left_at IS NULL"
            )
            params.append(team_id)
            if not include_archived:
                query += " AND agents.archived=0"
        else:
            query = "SELECT * FROM agents"
            if not include_archived:
                query += " WHERE archived=0"
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_agent(r) for r in rows]

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> AgentProfile:
        return AgentProfile(
            id=row["id"], name=row["name"], provider_id=row["provider_id"],
            model=row["model"], role=RoleName(row["role"]),
            instructions=row["instructions"],
            capabilities=json.loads(row["capabilities"]),
            lifecycle=Lifecycle(row["lifecycle"]), reports_to=row["reports_to"],
            fallback_agent_id=row["fallback_agent_id"], effort=row["effort"],
            max_turns=row["max_turns"], archived=bool(row["archived"]),
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Role binding
    # ------------------------------------------------------------------

    def save_role_binding(self, binding: RoleBinding) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO role_bindings(
                    id, team_id, role, agent_id, designation, bound_at, unbound_at, reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    team_id=excluded.team_id, role=excluded.role, agent_id=excluded.agent_id,
                    designation=excluded.designation, bound_at=excluded.bound_at,
                    unbound_at=excluded.unbound_at, reason=excluded.reason
                """,
                (
                    binding.id, binding.team_id, binding.role.value, binding.agent_id,
                    binding.designation, binding.bound_at, binding.unbound_at, binding.reason,
                ),
            )

    def close_role_binding(self, binding_id: str, unbound_at: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE role_bindings SET unbound_at=? WHERE id=?",
                (unbound_at, binding_id),
            )

    def active_binding(self, team_id: str, role: RoleName) -> RoleBinding | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM role_bindings
                WHERE team_id=? AND role=? AND unbound_at IS NULL
                ORDER BY bound_at DESC, rowid DESC LIMIT 1
                """,
                (team_id, role.value),
            ).fetchone()
        return self._row_to_binding(row) if row else None

    def list_bindings(self, team_id: str) -> list[RoleBinding]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM role_bindings WHERE team_id=? ORDER BY bound_at ASC",
                (team_id,),
            ).fetchall()
        return [self._row_to_binding(r) for r in rows]

    @staticmethod
    def _row_to_binding(row: sqlite3.Row) -> RoleBinding:
        return RoleBinding(
            id=row["id"], team_id=row["team_id"], role=RoleName(row["role"]),
            agent_id=row["agent_id"], designation=row["designation"],
            bound_at=row["bound_at"], unbound_at=row["unbound_at"], reason=row["reason"],
        )

    # ------------------------------------------------------------------
    # Team membership
    # ------------------------------------------------------------------

    def save_membership(self, membership: TeamMembership) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO team_memberships(id, team_id, agent_id, joined_at, left_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    team_id=excluded.team_id, agent_id=excluded.agent_id,
                    joined_at=excluded.joined_at, left_at=excluded.left_at
                """,
                (membership.id, membership.team_id, membership.agent_id,
                 membership.joined_at, membership.left_at),
            )

    def list_memberships(self, team_id: str) -> list[TeamMembership]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM team_memberships WHERE team_id=? ORDER BY joined_at ASC",
                (team_id,),
            ).fetchall()
        return [
            TeamMembership(
                id=r["id"], team_id=r["team_id"], agent_id=r["agent_id"],
                joined_at=r["joined_at"], left_at=r["left_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def save_session(self, session: Session) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    id, team_id, objective, state, acceptance_criteria,
                    max_delegations, max_cost_usd, revision, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    team_id=excluded.team_id, objective=excluded.objective,
                    state=excluded.state, acceptance_criteria=excluded.acceptance_criteria,
                    max_delegations=excluded.max_delegations, max_cost_usd=excluded.max_cost_usd,
                    revision=excluded.revision, updated_at=excluded.updated_at
                """,
                (
                    session.id, session.team_id, session.objective, session.state.value,
                    json.dumps(list(session.acceptance_criteria)), session.max_delegations,
                    session.max_cost_usd, session.revision, session.created_at,
                    session.updated_at,
                ),
            )

    def get_session(self, session_id: str) -> Session | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def mission_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Read an opt-in mission extension without migrating or starting it."""
        conn = self._connect()
        try:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mission_controls'").fetchone():
                return None
            row = conn.execute("SELECT document FROM mission_controls WHERE session_id=?", (session_id,)).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def autonomy_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Read-only UI projection, including historical databases without extensions."""
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='mission_autonomy'").fetchone():
                return None
            row = conn.execute('SELECT document FROM mission_autonomy WHERE session_id=?', (session_id,)).fetchone()
            if not row:
                return None
            result = json.loads(row[0])
            result['gaps'] = [dict(gap) for gap in conn.execute(
                'SELECT stage,reason,owner_action_required,risk,occurrences FROM autonomy_gaps WHERE session_id=?', (session_id,))]
            return result

    def claim_v1(self, session_id: str, token: str) -> str | None:
        """Atomic with mission adoption. Crash leaves a busy token, never an automatic replay."""
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM sessions WHERE id=?', (session_id,)).fetchone():
                raise ValueError('Unknown session')
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='mission_controls'").fetchone():
                if conn.execute('SELECT 1 FROM mission_controls WHERE session_id=?', (session_id,)).fetchone():
                    return 'MISSION_CONTROLLED'
            row = conn.execute('SELECT owner,token FROM session_authorities WHERE session_id=?',
                               (session_id,)).fetchone()
            if row and row['owner'] == 'MISSION':
                return 'MISSION_CONTROLLED'
            if row and row['token']:
                return 'BUSY'
            conn.execute("INSERT INTO session_authorities VALUES(?,'V1',?) ON CONFLICT(session_id) "
                         "DO UPDATE SET token=excluded.token", (session_id, token))
            conn.commit()
            return None
        finally:
            conn.close()

    def release_v1(self, session_id: str, token: str):
        with self._connect() as conn:
            conn.execute("UPDATE session_authorities SET token=NULL WHERE session_id=? AND owner='V1' AND token=?",
                         (session_id, token))

    def list_sessions(self, team_id: str | None = None, limit: int = 50) -> list[Session]:
        query = "SELECT s.* FROM sessions s WHERE NOT EXISTS (SELECT 1 FROM deleted_sessions d WHERE d.session_id=s.id)"
        params: list[Any] = []
        if team_id is not None:
            query += " AND s.team_id=?"
            params.append(team_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def hide_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO deleted_sessions(session_id, deleted_at) VALUES(?, ?)", (session_id, time.time()))

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"], team_id=row["team_id"], objective=row["objective"],
            state=SessionState(row["state"]),
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            max_delegations=row["max_delegations"], max_cost_usd=row["max_cost_usd"],
            revision=row["revision"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------

    def add_message(self, message: Message) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(
                    id, session_id, kind, author, content, author_agent_id, run_id, created_at,
                    to_agent_id, to_role, reply_to, correlation_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind, author=excluded.author, content=excluded.content,
                    author_agent_id=excluded.author_agent_id, run_id=excluded.run_id,
                    to_agent_id=excluded.to_agent_id, to_role=excluded.to_role,
                    reply_to=excluded.reply_to, correlation_id=excluded.correlation_id
                """,
                (
                    message.id, message.session_id, message.kind.value, message.author,
                    message.content, message.author_agent_id, message.run_id,
                    message.created_at,
                    message.to_agent_id, message.to_role, message.reply_to,
                    message.correlation_id,
                ),
            )

    def list_messages(
        self, session_id: str, limit: int = 200, for_role: str | None = None,
    ) -> list[Message]:
        # `created_at ASC, rowid ASC`: two messages written in the same
        # wall-clock tick (float seconds, easy to collide under a tight
        # loop) must still come back in insertion order. rowid is
        # monotonic per insert regardless of clock resolution.
        #
        # `for_role` is the Phase 1 "Organization" role filter: NULL
        # addressing columns mean legacy/implicit (legible by everyone) and
        # worker↔worker traffic (DELEGATE/REVIEW) stays out of the reader's
        # window, except a REVIEW escalated to the OWNER.
        with self._connect() as conn:
            if for_role is None:
                rows = conn.execute(
                    """
                    SELECT * FROM messages WHERE session_id=?
                    ORDER BY created_at ASC, rowid ASC LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM messages WHERE session_id=?
                    AND (
                        (kind NOT IN ('DELEGATE', 'REVIEW')
                         AND (to_role IS NULL OR to_role IN (?, 'ALL')))
                        OR (kind='REVIEW' AND to_role='OWNER')
                    )
                    ORDER BY created_at ASC, rowid ASC LIMIT ?
                    """,
                    (session_id, for_role, limit),
                ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def delete_messages_for_run(self, session_id: str, run_id: str) -> int:
        """Remove only canonical messages promoted from one interrupted Run."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM messages WHERE session_id=? AND run_id=?",
                (session_id, run_id),
            )
            return int(cursor.rowcount)

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"], session_id=row["session_id"], kind=MessageKind(row["kind"]),
            author=row["author"], content=row["content"],
            author_agent_id=row["author_agent_id"], run_id=row["run_id"],
            to_agent_id=row["to_agent_id"], to_role=row["to_role"],
            reply_to=row["reply_to"], correlation_id=row["correlation_id"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def save_run(self, run: Run) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(
                    id, session_id, agent_id, provider_id, model, model_reported, state,
                    task_id, provider_session_id, cost_usd, cost_basis, input_tokens,
                    output_tokens, duration_ms, error, started_at, ended_at, effort
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id=excluded.session_id, agent_id=excluded.agent_id,
                    provider_id=excluded.provider_id, model=excluded.model,
                    model_reported=excluded.model_reported, state=excluded.state,
                    task_id=excluded.task_id,
                    provider_session_id=excluded.provider_session_id,
                    cost_usd=excluded.cost_usd, cost_basis=excluded.cost_basis,
                    input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                    duration_ms=excluded.duration_ms, error=excluded.error,
                    ended_at=excluded.ended_at, effort=excluded.effort
                """,
                (
                    run.id, run.session_id, run.agent_id, run.provider_id, run.model,
                    run.model_reported, run.state.value, run.task_id, run.provider_session_id,
                    run.cost_usd, run.cost_basis.value, run.input_tokens, run.output_tokens,
                    run.duration_ms, run.error, run.started_at, run.ended_at, run.effort,
                ),
            )

    def get_run(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self, session_id: str) -> list[Run]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE session_id=? ORDER BY started_at ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"], session_id=row["session_id"], agent_id=row["agent_id"],
            provider_id=row["provider_id"], model=row["model"],
            model_reported=row["model_reported"], state=RunState(row["state"]),
            task_id=row["task_id"], provider_session_id=row["provider_session_id"],
            cost_usd=row["cost_usd"], cost_basis=CostBasis(row["cost_basis"]),
            input_tokens=row["input_tokens"], output_tokens=row["output_tokens"],
            duration_ms=row["duration_ms"], error=row["error"],
            started_at=row["started_at"], ended_at=row["ended_at"], effort=row['effort'],
        )

    def total_cost(self, session_id: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT SUM(cost_usd) AS total FROM runs WHERE session_id=? AND cost_usd IS NOT NULL",
                (session_id,),
            ).fetchone()
        total = row["total"] if row else None
        return float(total) if total is not None else 0.0

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    def save_task(self, task: Task) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                    id, session_id, title, instruction, created_by_agent_id,
                    assigned_agent_id, state, acceptance, result, max_turns,
                    budget_usd, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, instruction=excluded.instruction,
                    assigned_agent_id=excluded.assigned_agent_id, state=excluded.state,
                    acceptance=excluded.acceptance, result=excluded.result,
                    max_turns=excluded.max_turns, budget_usd=excluded.budget_usd,
                    updated_at=excluded.updated_at
                """,
                (
                    task.id, task.session_id, task.title, task.instruction,
                    task.created_by_agent_id, task.assigned_agent_id, task.state.value,
                    task.acceptance, task.result, task.max_turns, task.budget_usd,
                    task.created_at, task.updated_at,
                ),
            )

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(self, session_id: str) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"], session_id=row["session_id"], title=row["title"],
            instruction=row["instruction"], created_by_agent_id=row["created_by_agent_id"],
            assigned_agent_id=row["assigned_agent_id"], state=TaskState(row["state"]),
            acceptance=row["acceptance"], result=row["result"], max_turns=row["max_turns"],
            budget_usd=row["budget_usd"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # Handoff
    # ------------------------------------------------------------------

    def save_handoff(self, handoff: Handoff) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO handoffs(
                    id, session_id, team_id, role, from_agent_id, to_agent_id, reason,
                    context_summary, unfinished_task_ids, outcome, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    reason=excluded.reason, context_summary=excluded.context_summary,
                    unfinished_task_ids=excluded.unfinished_task_ids, outcome=excluded.outcome
                """,
                (
                    handoff.id, handoff.session_id, handoff.team_id, handoff.role.value,
                    handoff.from_agent_id, handoff.to_agent_id, handoff.reason,
                    handoff.context_summary, json.dumps(list(handoff.unfinished_task_ids)),
                    handoff.outcome, handoff.created_at,
                ),
            )

    def list_handoffs(self, session_id: str | None = None) -> list[Handoff]:
        query = "SELECT * FROM handoffs"
        params: list[Any] = []
        if session_id is not None:
            query += " WHERE session_id=?"
            params.append(session_id)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_handoff(r) for r in rows]

    @staticmethod
    def _row_to_handoff(row: sqlite3.Row) -> Handoff:
        return Handoff(
            id=row["id"], session_id=row["session_id"], team_id=row["team_id"],
            role=RoleName(row["role"]), from_agent_id=row["from_agent_id"],
            to_agent_id=row["to_agent_id"], reason=row["reason"],
            context_summary=row["context_summary"],
            unfinished_task_ids=json.loads(row["unfinished_task_ids"]),
            outcome=row["outcome"], created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def save_decision(self, decision: Decision) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions(
                    id, session_id, author_agent_id, statement, rationale, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    statement=excluded.statement, rationale=excluded.rationale
                """,
                (decision.id, decision.session_id, decision.author_agent_id,
                 decision.statement, decision.rationale, decision.created_at),
            )

    def list_decisions(self, session_id: str) -> list[Decision]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [
            Decision(
                id=r["id"], session_id=r["session_id"],
                author_agent_id=r["author_agent_id"], statement=r["statement"],
                rationale=r["rationale"], created_at=r["created_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Artifact
    # ------------------------------------------------------------------

    @staticmethod
    def _save_artifact_row(conn: sqlite3.Connection, artifact: Artifact) -> None:
        conn.execute(
            """
            INSERT INTO artifacts(
                id, session_id, task_id, kind, title, body, path, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind=excluded.kind, title=excluded.title, body=excluded.body,
                path=excluded.path
            """,
            (artifact.id, artifact.session_id, artifact.task_id, artifact.kind,
             artifact.title, artifact.body, artifact.path, artifact.created_at),
        )

    def save_artifact(self, artifact: Artifact) -> None:
        with self._connect() as conn:
            self._save_artifact_row(conn, artifact)

    def save_bound_model_response(self, response: Artifact, binding: Artifact) -> None:
        """Commit one model response and its exact attempt/Run binding together."""
        if (response.kind != "MODEL_TEXT" or binding.kind != "MODEL_RESPONSE_BINDING"
                or response.session_id != binding.session_id
                or response.task_id != binding.task_id):
            raise ValueError("MODEL_RESPONSE_BINDING_INVALID")
        with self._connect() as conn:
            self._save_artifact_row(conn, response)
            self._save_artifact_row(conn, binding)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE id=?", (artifact_id,)
            ).fetchone()
        if row is None:
            return None
        return Artifact(
            id=row["id"], session_id=row["session_id"], task_id=row["task_id"],
            kind=row["kind"], title=row["title"], body=row["body"], path=row["path"],
            created_at=row["created_at"],
        )

    def list_artifacts(self, session_id: str) -> list[Artifact]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [
            Artifact(
                id=r["id"], session_id=r["session_id"], task_id=r["task_id"],
                kind=r["kind"], title=r["title"], body=r["body"], path=r["path"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Durable Builder -> Reviewer evidence transport
    # ------------------------------------------------------------------

    @staticmethod
    def _evidence_packet_json(value: Any) -> str:
        """Canonical packet bytes, matching review_evidence_packet._json."""
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    @classmethod
    def _read_evidence_packet(cls, artifact: Artifact) -> tuple[dict[str, Any], str] | None:
        if artifact.kind != "REVIEW_EVIDENCE_PACKET":
            return None
        try:
            envelope = json.loads(artifact.body)
            packet = envelope["packet"]
            packet_sha256 = envelope["packet_sha256"]
        except (TypeError, ValueError, KeyError):
            return None
        if not isinstance(packet, dict) or not isinstance(packet_sha256, str):
            return None
        return packet, packet_sha256

    def _evidence_packet_artifact(
        self, session_id: str | None, packet_id: str | None,
    ) -> tuple[Artifact, dict[str, Any], str] | None:
        """Resolve a packet from the canonical artifacts table, not memory."""
        if session_id is not None:
            artifacts = self.list_artifacts(session_id)
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE kind=? ORDER BY created_at ASC",
                    ("REVIEW_EVIDENCE_PACKET",),
                ).fetchall()
            artifacts = [Artifact(
                id=row["id"], session_id=row["session_id"], task_id=row["task_id"],
                kind=row["kind"], title=row["title"], body=row["body"],
                path=row["path"], created_at=row["created_at"],
            ) for row in rows]
        candidates = []
        for artifact in artifacts:
            parsed = self._read_evidence_packet(artifact)
            if parsed is None:
                continue
            packet, packet_sha256 = parsed
            if packet_id is not None and artifact.id != packet_id:
                continue
            if session_id is not None and packet.get("session_id") != session_id:
                continue
            candidates.append((artifact, packet, packet_sha256))
        return candidates[-1] if candidates else None

    def _evidence_handoff_document(
        self, artifact: Artifact, packet: dict[str, Any], packet_sha256: str,
    ) -> dict[str, Any]:
        """Rehydrate all packet-adjacent facts in one restart-safe read model."""
        session_id = artifact.session_id
        artifacts = self.list_artifacts(session_id)
        messages = self.list_messages(session_id)
        handoffs = self.list_handoffs(session_id)
        runs = self.list_runs(session_id)
        indexed = {item.id: item for item in artifacts}

        receipt_map = packet.get("receipts") if isinstance(packet.get("receipts"), dict) else {}
        resolved_receipts: dict[str, dict[str, Any]] = {}
        action_receipts: list[dict[str, Any]] = []
        for name, raw_ref in receipt_map.items():
            ref_id = raw_ref.get("id") if isinstance(raw_ref, dict) else raw_ref
            if not isinstance(ref_id, str):
                continue
            receipt_artifact = indexed.get(ref_id)
            if receipt_artifact is None:
                continue
            resolved = receipt_artifact.to_dict()
            resolved_receipts[name] = resolved
            if receipt_artifact.kind in {
                "SOURCE_DIFF", "REAL_TESTS", "LOCAL_PRESERVATION",
                "SOURCE_SNAPSHOT", "SOURCE_BUILD",
            }:
                action_receipts.append(resolved)

        plan: dict[str, Any] = {}
        plan_task = self.get_task(session_id + ":plan")
        if plan_task is not None:
            plan["task"] = plan_task.to_dict()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT document FROM mission_controls WHERE session_id=?",
                    (session_id,),
                ).fetchone()
            if row is not None:
                document = json.loads(row["document"])
                if isinstance(document, dict):
                    plan.update({
                        "version": document.get("plan_version"),
                        "state": document.get("state"),
                        "liveness_state": document.get("liveness_state"),
                        "steps": document.get("steps", []),
                    })
        except (sqlite3.Error, TypeError, ValueError):
            pass

        run_by_id = {run.id: run for run in runs}
        bindings: list[dict[str, Any]] = []
        provenance_runs: list[dict[str, Any]] = []
        for binding_artifact in artifacts:
            if binding_artifact.kind != "MODEL_RESPONSE_BINDING":
                continue
            try:
                binding = json.loads(binding_artifact.body)
            except (TypeError, ValueError):
                continue
            if not isinstance(binding, dict):
                continue
            binding_copy = dict(binding)
            run_id = binding_copy.get("run_id")
            run = run_by_id.get(run_id) if isinstance(run_id, str) else None
            if run is not None:
                binding_copy["run"] = run.to_dict()
                provenance_runs.append(run.to_dict())
            bindings.append(binding_copy)
        known_run_ids = {item["id"] for item in provenance_runs}
        for run in runs:
            if run.id not in known_run_ids:
                provenance_runs.append(run.to_dict())

        continuity: list[dict[str, Any]] = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM agent_continuity WHERE session_id=? ORDER BY rowid ASC",
                    (session_id,),
                ).fetchall()
            for row in rows:
                try:
                    state = json.loads(row["state_json"])
                except (TypeError, ValueError):
                    state = {}
                continuity.append({
                    "session_id": row["session_id"], "agent_id": row["agent_id"],
                    "cursor": row["cursor"], "summary": row["summary"],
                    "state": state, "revision": int(row["revision"]),
                    "updated_at": float(row["updated_at"]),
                })
        except (sqlite3.Error, KeyError, TypeError, ValueError):
            pass

        tests = packet.get("tests") if isinstance(packet.get("tests"), dict) else {}
        diff = packet.get("diff") if isinstance(packet.get("diff"), dict) else {}
        measurements = {
            "baseline": tests.get("baseline"),
            "candidate": tests.get("candidate"),
            "diff": {key: diff.get(key) for key in
                      ("files_changed", "lines_added", "lines_deleted") if key in diff},
        }
        integrity_digest = hashlib.sha256(
            self._evidence_packet_json(packet).encode("utf-8")
        ).hexdigest()
        integrity = {
            "expected_sha256": packet_sha256,
            "computed_sha256": integrity_digest,
            "matches": integrity_digest == packet_sha256,
            "status": "VALID" if integrity_digest == packet_sha256 else "TAMPERED",
        }
        return {
            "version": 1,
            "packet_id": artifact.id,
            "packet_sha256": packet_sha256,
            "session_id": session_id,
            "task_id": artifact.task_id,
            "objective": packet.get("objective"),
            "acceptance": packet.get("acceptance"),
            "plan": plan,
            "source_identity": packet.get("source_identity", {}),
            "candidate_identity": packet.get("candidate_identity", {}),
            "artifacts": [item.to_dict() for item in artifacts],
            "diff": diff,
            "receipts": receipt_map,
            "resolved_receipts": resolved_receipts,
            "action_receipts": action_receipts,
            "baseline": tests.get("baseline"),
            "measurements": measurements,
            "limitations": list(packet.get("limitations", [])),
            "provenance": {
                "runs": provenance_runs,
                "bindings": bindings,
                "handoffs": [item.to_dict() for item in handoffs],
                "continuity": continuity,
            },
            "messages": [item.to_dict() for item in messages],
            "handoffs": [item.to_dict() for item in handoffs],
            "packet": packet,
            "integrity": integrity,
            "transport": {
                "source": "LabStore.artifacts",
                "durable": True,
                "restart_recoverable": True,
            },
        }

    def get_evidence_handoff(
        self, session_id: str | None = None, packet_id: str | None = None,
        *, packet_sha256: str | None = None,
    ) -> dict[str, Any] | None:
        """Return one complete Builder -> Reviewer handoff after restart."""
        self.initialize()
        if packet_id is None and isinstance(session_id, str) \
                and session_id.startswith("REVIEW_EVIDENCE_PACKET:"):
            packet_id, session_id = session_id, None
        resolved = self._evidence_packet_artifact(session_id, packet_id)
        if resolved is None:
            return None
        artifact, packet, stored_sha256 = resolved
        if packet_sha256 is not None and packet_sha256 != stored_sha256:
            return None
        return self._evidence_handoff_document(artifact, packet, stored_sha256)

    get_review_evidence_packet = get_evidence_handoff
    get_builder_reviewer_evidence = get_evidence_handoff

    def list_evidence_handoffs(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """Return every durable packet, oldest-first, for a mission or Lab."""
        self.initialize()
        if session_id is not None:
            packet_artifacts = [item for item in self.list_artifacts(session_id)
                                if item.kind == "REVIEW_EVIDENCE_PACKET"]
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM artifacts WHERE kind=? ORDER BY created_at ASC",
                    ("REVIEW_EVIDENCE_PACKET",),
                ).fetchall()
            packet_artifacts = [Artifact(
                id=row["id"], session_id=row["session_id"], task_id=row["task_id"],
                kind=row["kind"], title=row["title"], body=row["body"],
                path=row["path"], created_at=row["created_at"],
            ) for row in rows]
        result = []
        for artifact in packet_artifacts:
            parsed = self._read_evidence_packet(artifact)
            if parsed is None:
                continue
            packet, packet_sha256 = parsed
            result.append(self._evidence_handoff_document(artifact, packet, packet_sha256))
        return result

    list_review_evidence_packets = list_evidence_handoffs

    # ------------------------------------------------------------------
    # Capability gap
    # ------------------------------------------------------------------

    def save_capability_gap(self, gap: CapabilityGap) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO capability_gaps(
                    id, session_id, required, available, detail, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    required=excluded.required, available=excluded.available,
                    detail=excluded.detail
                """,
                (gap.id, gap.session_id, gap.required, int(gap.available), gap.detail,
                 gap.created_at),
            )

    def list_capability_gaps(self, session_id: str | None = None) -> list[CapabilityGap]:
        query = "SELECT * FROM capability_gaps"
        params: list[Any] = []
        if session_id is not None:
            query += " WHERE session_id=?"
            params.append(session_id)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CapabilityGap(
                id=r["id"], session_id=r["session_id"], required=r["required"],
                available=bool(r["available"]), detail=r["detail"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Event
    # ------------------------------------------------------------------

    def append_event(self, event: LabEvent) -> LabEvent:
        """Inserts ignoring the caller's `seq` and returns the row with the
        real one. `seq` is AUTOINCREMENT so ordering survives concurrent
        writers without the caller ever guessing the next number."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events(id, type, session_id, entity_id, payload, occurred_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (event.id, event.type, event.session_id, event.entity_id,
                 json.dumps(event.payload), event.occurred_at),
            )
            seq = cur.lastrowid
        return LabEvent(
            id=event.id, seq=seq, type=event.type, session_id=event.session_id,
            entity_id=event.entity_id, payload=event.payload,
            occurred_at=event.occurred_at,
        )

    def list_events(
        self, session_id: str | None = None, after_seq: int = 0, limit: int = 200
    ) -> list[LabEvent]:
        clauses = ["seq > ?"]
        params: list[Any] = [after_seq]
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        query = "SELECT * FROM events WHERE " + " AND ".join(clauses)
        query += " ORDER BY seq ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            LabEvent(
                id=r["id"], seq=r["seq"], type=r["type"], session_id=r["session_id"],
                entity_id=r["entity_id"], payload=json.loads(r["payload"]),
                occurred_at=r["occurred_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Memory outbox
    # ------------------------------------------------------------------
    # Exists so a crash between "wrote to ZARA memory" and "recorded that
    # we did" cannot double-write a memory later: the caller checks
    # `memory_outbox_seen` before writing to memory, and records only
    # after the write succeeds.

    def memory_outbox_seen(self, event_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_outbox WHERE event_id=?", (event_id,)
            ).fetchone()
        return row is not None

    def memory_outbox_record(self, event_id: str, memory_ref: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_outbox(event_id, memory_ref, created_at)
                VALUES(?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET memory_ref=excluded.memory_ref
                """,
                (event_id, memory_ref, time.time()),
            )

    # ------------------------------------------------------------------
    # Central marked-verified lessons
    # ------------------------------------------------------------------

    def promote_lesson(self, source_event_id: str) -> LabLesson:
        """Promote one ``lesson.marked_verified`` event into central memory.

        The marker must point to an earlier durable event in the same session.
        This proves traceability, not the truth of the lesson. Promotion is
        transactional and keyed by its marker, so replay returns the original
        row without adding another ``lesson.promoted`` event.
        """
        from core.lab_v1.domain import EventType

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM lab_lessons WHERE source_event_id=?",
                (source_event_id,),
            ).fetchone()
            if existing is not None:
                return self._row_to_lesson(existing)

            source = conn.execute(
                "SELECT * FROM events WHERE id=?", (source_event_id,)
            ).fetchone()
            if source is None or source["type"] != EventType.LESSON_MARKED_VERIFIED:
                raise ValueError("Only a marked-verified lesson event can be promoted")
            if source["session_id"] is None or conn.execute(
                "SELECT 1 FROM sessions WHERE id=?", (source["session_id"],)
            ).fetchone() is None:
                raise ValueError("A lesson requires an existing source session")

            payload = json.loads(source["payload"])
            statement = " ".join(str(payload.get("lesson") or "").split())
            evidence_event_id = " ".join(str(payload.get("evidence_event_id") or "").split())
            if not statement or not evidence_event_id:
                raise ValueError("A marked-verified lesson requires lesson and evidence_event_id")
            evidence = conn.execute(
                "SELECT * FROM events WHERE id=?", (evidence_event_id,)
            ).fetchone()
            if (
                evidence is None
                or evidence["session_id"] != source["session_id"]
                or evidence["seq"] >= source["seq"]
            ):
                raise ValueError("Lesson evidence must resolve to an earlier event in the same session")
            evidence_ref = f"event:{evidence_event_id}"

            lesson = LabLesson(
                id=f"lesson:{source_event_id}",
                source_event_id=source_event_id,
                source_session_id=source["session_id"],
                statement=statement,
                evidence_ref=evidence_ref,
                created_at=time.time(),
            )
            conn.execute(
                """
                INSERT INTO lab_lessons(
                    id, source_event_id, source_session_id, statement,
                    evidence_ref, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson.id, lesson.source_event_id, lesson.source_session_id,
                    lesson.statement, lesson.evidence_ref, lesson.created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO events(id, type, session_id, entity_id, payload, occurred_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    f"lesson-promoted:{source_event_id}",
                    EventType.LESSON_PROMOTED,
                    lesson.source_session_id,
                    lesson.id,
                    json.dumps({
                        "source_event_id": source_event_id,
                        "evidence_ref": lesson.evidence_ref,
                    }),
                    lesson.created_at,
                ),
            )
        return lesson

    def list_lessons(self, limit: int = 100) -> list[LabLesson]:
        """Return central lessons across every Lab mission, newest first."""
        if int(limit) <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lab_lessons ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (min(int(limit), 500),),
            ).fetchall()
        return [self._row_to_lesson(row) for row in rows]

    def lesson_context(self, session_id: str, limit: int = 10) -> list[str]:
        """Read global lessons for a known mission's bounded context packet."""
        if self.get_session(session_id) is None:
            raise ValueError("Unknown session")
        return [lesson.statement for lesson in self.list_lessons(limit=limit)]

    @staticmethod
    def _row_to_lesson(row: sqlite3.Row) -> LabLesson:
        return LabLesson(
            id=row["id"],
            source_event_id=row["source_event_id"],
            source_session_id=row["source_session_id"],
            statement=row["statement"],
            evidence_ref=row["evidence_ref"],
            created_at=row["created_at"],
        )
