"""ZARA Lab — persistent council and development orchestration core.

LAB CORE 001 intentionally separates discussion/approval from code execution.
It provides a real local council room, persistent proposals/tasks, worker health,
and direct ZARA/Hermes participation. Code workers are registered but are not
allowed to edit production until the execution runtime is explicitly enabled in
a later, separately validated module.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.autonomy_lab_bridge import AutonomyLabBridge
from core.lab_worker_runtime import LabWorkerRuntime
from core.mentor_relay import MentorRelay
from core.paths import data_dir


@dataclass
class WorkerState:
    id: str
    name: str
    role: str
    state: str
    detail: str
    executable: str | None = None
    can_chat: bool = False
    can_execute: bool = False


class LabCoordinator:
    """Persistent council + approval gate for ZARA's development laboratory."""

    def __init__(self, orchestrator: Any = None, hermes: Any = None, worker_runtime: LabWorkerRuntime | None = None):
        self.orchestrator = orchestrator
        self.hermes = hermes
        self.worker_runtime = worker_runtime or LabWorkerRuntime()
        self.root = data_dir() / "lab"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "zara_lab.db"
        self.autonomy = AutonomyLabBridge(self.db_path)
        self.mentor_relay = MentorRelay()
        self.dev_config_path = data_dir() / "dev-team-config.json"
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_db)
            migration = await asyncio.to_thread(self.autonomy.migrate_approved_from_lab_db)
            if migration.get("created"):
                await asyncio.to_thread(
                    self._activity_sync,
                    "autonomy",
                    "AUTONOMY_MIGRATION",
                    f"{migration['created']} task(s) approved imported to Autonomy Core.",
                    time.time(),
                )
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    author TEXT NOT NULL,
                    target TEXT NOT NULL,
                    content TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'chat',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    cost TEXT NOT NULL DEFAULT 'R$ 0',
                    approved_by TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    proposal_id TEXT,
                    title TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(proposal_id) REFERENCES proposals(id)
                );
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )
            row = conn.execute("SELECT COUNT(*) AS n FROM activity").fetchone()
            if row and int(row["n"]) == 0:
                conn.execute(
                    "INSERT INTO activity(actor,event,detail,created_at) VALUES(?,?,?,?)",
                    ("system", "LAB_INITIALIZED", "ZARA Lab Core 001 criado. Approval Gate ativo.", time.time()),
                )

    def _dev_config(self) -> dict[str, Any]:
        try:
            if self.dev_config_path.exists():
                with self.dev_config_path.open(encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _resolve_tool(self, tool: str, fallback: str | None = None) -> str | None:
        cfg = self._dev_config().get("tools", {})
        configured = cfg.get(tool) if isinstance(cfg, dict) else None
        if configured and Path(str(configured)).exists():
            return str(configured)
        found = shutil.which(tool)
        if found:
            return found
        if fallback and Path(fallback).exists():
            return fallback
        return None

    async def worker_states(self) -> list[dict[str, Any]]:
        hermes_connected = False
        if self.hermes:
            try:
                hermes_connected = bool(await self.hermes.health_check())
            except Exception:
                hermes_connected = False

        opencode = self._resolve_tool("opencode")
        cline = self._resolve_tool("cline")
        aider = self._resolve_tool("aider", str(Path.home() / "aider-env" / "venv" / "Scripts" / "aider.exe"))
        openclaw = self._resolve_tool("openclaw")
        runtime = self.worker_runtime.status() if self.worker_runtime else {}
        oc = runtime.get("opencode", {})
        claw = runtime.get("openclaw", {})
        oc_state = str(oc.get("state") or ("INSTALLED" if opencode else "NOT INSTALLED"))
        oc_detail = str(oc.get("detail") or "Lead Developer.")
        if oc_state == "ERROR":
            oc_state = "DEFERRED"
            oc_detail = "Integração de chat adiada; OpenCode permanece instalado para retomada futura."

        states = [
            WorkerState("alex", "ALEX", "OWNER / APPROVAL", "ONLINE", "Autoridade final do produto.", can_chat=True),
            WorkerState("zara", "ZARA", "CORE / COUNCIL", "ONLINE" if self.orchestrator else "OFFLINE", "Núcleo da assistente.", can_chat=bool(self.orchestrator)),
            WorkerState(
                "mentor",
                "MENTOR",
                "CEO / ARCHITECT",
                self.mentor_relay.status().state,
                self.mentor_relay.status().detail,
                can_chat=True,
            ),
            WorkerState("hermes", "HERMES", "LOCAL OPS", "ONLINE" if hermes_connected else "OFFLINE", "Gateway local e operações Windows.", can_chat=hermes_connected),
            WorkerState("opencode", "OPENCODE", "LEAD DEVELOPER", oc_state, oc_detail, executable=opencode, can_chat=bool(oc.get("can_chat")) and oc_state not in {"DEFERRED", "ERROR"}, can_execute=False),
            WorkerState("openclaw", "OPENCLAW", "AGENT RUNTIME / R&D", str(claw.get("state") or ("INSTALLED" if openclaw else "NOT INSTALLED")), str(claw.get("detail") or "Runtime persistente de agentes e pesquisa."), executable=openclaw, can_chat=bool(claw.get("can_chat")), can_execute=False),
            WorkerState("cline", "CLINE", "QA / HEADLESS", "LIMITED" if cline else "NOT INSTALLED", "Instalado; hardware local abaixo da recomendação para executor principal.", executable=cline, can_chat=False, can_execute=False),
            WorkerState("aider", "AIDER", "PATCH / GIT", "INSTALLED" if aider else "NOT INSTALLED", "Especialista em patches cirúrgicos; execução ainda bloqueada.", executable=aider, can_chat=False, can_execute=False),
        ]
        return [asdict(s) for s in states]

    async def get_state(self) -> dict[str, Any]:
        await self.initialize()
        await self._sync_mentor_replies()
        workers = await self.worker_states()
        async with self._lock:
            return await asyncio.to_thread(self._read_state, workers)

    def _read_state(self, workers: list[dict[str, Any]]) -> dict[str, Any]:
        with self._connect() as conn:
            messages = [dict(row) for row in conn.execute(
                "SELECT * FROM messages ORDER BY created_at DESC LIMIT 120"
            ).fetchall()][::-1]
            proposals = [dict(row) for row in conn.execute(
                "SELECT * FROM proposals ORDER BY updated_at DESC LIMIT 40"
            ).fetchall()]
            legacy_tasks = [dict(row) for row in conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 40"
            ).fetchall()]
            activity = [dict(row) for row in conn.execute(
                "SELECT * FROM activity ORDER BY created_at DESC LIMIT 60"
            ).fetchall()]

        try:
            tasks = self.autonomy.lab_tasks(limit=100)
            autonomy = self.autonomy.summary()
        except Exception as exc:
            # Lab itself must remain usable even if the autonomy DB has a problem.
            tasks = legacy_tasks
            autonomy = {
                "status": "ERROR",
                "persistent": False,
                "execution_enabled": False,
                "total_tasks": len(legacy_tasks),
                "counts": {},
                "online_workers": 0,
                "error": type(exc).__name__,
            }

        return {
            "version": "LAB-AUTONOMY-001",
            "execution_runtime": "AUTONOMY ONLINE • WORKER EXECUTION LOCKED",
            "approval_gate": True,
            "workers": workers,
            "messages": messages,
            "proposals": proposals,
            "tasks": tasks,
            "activity": activity,
            "autonomy": autonomy,
            "mentor_relay": self.mentor_relay.snapshot(),
        }

    async def send_message(self, author: str, target: str, content: str) -> dict[str, Any]:
        await self.initialize()
        author = (author or "alex").strip().lower()
        target = (target or "zara").strip().lower()
        content = (content or "").strip()
        if not content:
            raise ValueError("Mensagem vazia")
        if target not in {"zara", "hermes", "mentor", "opencode", "openclaw", "cline", "aider"}:
            raise ValueError(f"Participante desconhecido: {target}")

        await self._insert_message(author, target, content, "chat")
        await self._activity(author, "MESSAGE_SENT", f"@{target}: {content[:120]}")

        response = ""
        state = "OK"
        try:
            if target == "zara":
                if not self.orchestrator:
                    raise RuntimeError("ZARA Core indisponível")
                prompt = (
                    "Você está participando do ZARA LAB como membro do conselho. "
                    "Discuta a ideia sem executar mudanças no código. Seja objetiva e deixe claro quando algo precisa da aprovação do Alex.\n\n"
                    f"Alex: {content}"
                )
                response = str(await self.orchestrator.process_message(prompt, engine="auto"))
            elif target == "hermes":
                if not self.hermes or not await self.hermes.health_check():
                    raise RuntimeError("Hermes Gateway offline")
                response = str(await self.hermes.send_message(
                    content,
                    history=[],
                    team="general",
                ))
            elif target == "mentor":
                queued = self.mentor_relay.enqueue(author, content)
                await self._activity("mentor-relay", "MENTOR_QUEUED", queued["relay_id"])
                # Do not fabricate a Mentor answer. The real external answer will
                # arrive through inbox/ and be persisted by _sync_mentor_replies().
                return {
                    "success": True,
                    "state": "QUEUED",
                    "relay_id": queued["relay_id"],
                    "relay_online": self.mentor_relay.status().online,
                }
            elif target in {"opencode", "openclaw"}:
                if not self.worker_runtime:
                    raise RuntimeError("Worker Runtime indisponível")
                result = await self.worker_runtime.chat(target, content)
                response = str(result.get("response") or "")
                if not response:
                    raise RuntimeError(f"{target.upper()} retornou resposta vazia")
                state = "OK"
            else:
                state = "INSTALLED"
                response = (
                    f"{target.upper()} permanece registrado, mas sua execução ainda não foi habilitada nesta etapa."
                )
        except Exception as exc:
            state = "ERROR"
            response = str(exc)

        await self._insert_message(target, author, response, "agent" if state == "OK" else "status")
        await self._activity(target, "MESSAGE_RESULT", state)
        return {"success": state in {"OK", "EXTERNAL", "INSTALLED"}, "state": state, "response": response}

    async def _sync_mentor_replies(self) -> None:
        """Import real Mentor replies delivered by Hermes continuity."""
        replies = await asyncio.to_thread(self.mentor_relay.drain_replies, 20)
        for item in replies:
            relay_id = str(item["relay_id"])
            # Idempotency: relay_id is stored inside message id.
            msg_id = f"mentor-relay-{relay_id}"
            now = float(item.get("created_at") or time.time())
            async with self._lock:
                inserted = await asyncio.to_thread(
                    self._insert_mentor_reply_sync,
                    msg_id,
                    relay_id,
                    str(item["content"]),
                    now,
                )
            if inserted:
                await self._activity("mentor", "MENTOR_REPLY_IMPORTED", relay_id)
            await asyncio.to_thread(self.mentor_relay.mark_outbound_processed, relay_id)

    def _insert_mentor_reply_sync(self, msg_id: str, relay_id: str, content: str, now: float) -> bool:
        with self._connect() as conn:
            exists = conn.execute("SELECT id FROM messages WHERE id=?", (msg_id,)).fetchone()
            if exists:
                return False
            conn.execute(
                "INSERT INTO messages(id,author,target,content,kind,created_at) VALUES(?,?,?,?,?,?)",
                (msg_id, "mentor", "alex", content, "agent", now),
            )
            return True

    async def create_proposal(self, title: str, summary: str, risk: str = "MEDIUM", owner: str = "opencode") -> dict[str, Any]:
        await self.initialize()
        title, summary = title.strip(), summary.strip()
        if not title or not summary:
            raise ValueError("Título e resumo são obrigatórios")
        if owner not in {"opencode", "cline", "aider", "hermes"}:
            owner = "opencode"
        risk = risk.upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            risk = "MEDIUM"
        now = time.time()
        proposal_id = f"ZARA-{uuid.uuid4().hex[:6].upper()}"
        async with self._lock:
            await asyncio.to_thread(self._create_proposal_sync, proposal_id, title, summary, risk, owner, now)
        await self._activity("alex", "PROPOSAL_CREATED", proposal_id)
        return {"id": proposal_id, "status": "DISCUSSION"}

    def _create_proposal_sync(self, pid: str, title: str, summary: str, risk: str, owner: str, now: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO proposals(id,title,summary,status,risk,owner,cost,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (pid, title, summary, "DISCUSSION", risk, owner, "R$ 0", now, now),
            )

    async def decide_proposal(self, proposal_id: str, decision: str) -> dict[str, Any]:
        await self.initialize()
        decision = decision.upper().strip()
        if decision not in {"APPROVE", "REJECT"}:
            raise ValueError("Decisão inválida")
        async with self._lock:
            result = await asyncio.to_thread(self._decide_sync, proposal_id, decision)

        if decision == "APPROVE":
            try:
                autonomy_task = await asyncio.to_thread(self.autonomy.ensure_from_proposal, proposal_id)
                result["autonomy_task_id"] = autonomy_task.id
                result["autonomy_state"] = autonomy_task.state
            except Exception as exc:
                await self._activity("autonomy", "AUTONOMY_TASK_CREATE_FAILED", f"{proposal_id}: {type(exc).__name__}")
                raise RuntimeError(
                    f"Proposta aprovada, mas a tarefa persistente não pôde ser criada: {type(exc).__name__}"
                ) from exc

        await self._activity("alex", "PROPOSAL_APPROVED" if decision == "APPROVE" else "PROPOSAL_REJECTED", proposal_id)
        return result

    def _decide_sync(self, proposal_id: str, decision: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            proposal = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not proposal:
                raise ValueError("Proposta não encontrada")
            if decision == "REJECT":
                conn.execute("UPDATE proposals SET status='REJECTED',approved_by='alex',updated_at=? WHERE id=?", (now, proposal_id))
                return {"id": proposal_id, "status": "REJECTED"}

            conn.execute("UPDATE proposals SET status='APPROVED',approved_by='alex',updated_at=? WHERE id=?", (now, proposal_id))
            task_id = f"TASK-{proposal_id}"
            existing = conn.execute("SELECT id FROM tasks WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO tasks(id,proposal_id,title,owner,status,progress,current_step,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (task_id, proposal_id, proposal["title"], proposal["owner"], "QUEUED", 0, "Aguardando Execution Runtime", now, now),
                )
            return {"id": proposal_id, "status": "APPROVED", "task_id": task_id, "execution": "LOCKED"}

    async def _insert_message(self, author: str, target: str, content: str, kind: str) -> None:
        now = time.time()
        msg_id = uuid.uuid4().hex
        async with self._lock:
            await asyncio.to_thread(self._insert_message_sync, msg_id, author, target, content, kind, now)

    def _insert_message_sync(self, msg_id: str, author: str, target: str, content: str, kind: str, now: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(id,author,target,content,kind,created_at) VALUES(?,?,?,?,?,?)",
                (msg_id, author, target, content, kind, now),
            )

    async def _activity(self, actor: str, event: str, detail: str = "") -> None:
        now = time.time()
        async with self._lock:
            await asyncio.to_thread(self._activity_sync, actor, event, detail, now)

    def _activity_sync(self, actor: str, event: str, detail: str, now: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO activity(actor,event,detail,created_at) VALUES(?,?,?,?)",
                (actor, event, detail, now),
            )
