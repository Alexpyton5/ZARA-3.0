"""Real Lab adapters for CODEX-NOVA-UI-FIACAO-20260930.

Contract: sole backend writer; only this module, its isolated tests and minimal
IPC registration. Baseline 8e790a1, dirty work preserved; no build/commit/push.
Evidence: SOURCE + isolated TEST, never packaged or physical validation.

State (no wrapper):
  success: bool; paused: bool | None; error?: str
  projects: [{id: str, nome: str, membros: [{avatar: Avatar,
             status: 'trabalhando'|'pausado'|'disponivel', tarefaAtual?: str}]}]
  work: [{id: str, titulo: str, descricao: str, responsavel: Avatar,
          estado: 'andamento'|'entregue'|'pausado', atualizadoEm: str}]
  activity: [{id: str, titulo: str, descricao: str, responsavel: Avatar,
              concluidoEm: str, entregavelUrl?: str}]
  decisions: [{id: str, pergunta: str, contexto: str, opcoes: list[str]}]
  components: dict[str, {success: bool, paused: bool | None, code?: str,
                         error?: str, ...real component evidence}]
  unknown: [{component: str, id: str, reason: str,
             project_id?: str, source_status?: str | None}]
  Avatar = {id: str, nome: str, papel: str}
Projects project persisted Lab teams;
avatars use real memberships/bindings. Unsupported statuses/unknown owners are
reported in unknown, never relabelled as available, delivered or paused.
Dates are stored timestamps as UTC ISO 8601; entregavelUrl is a stored path/URL.
Decisions accept {id: str, option: str}. Proposal IDs go to decide_proposal;
mission IDs go to the existing durable admission protocol. An admission ACK
is not execution: lab-v1-confirm-operation must receive its operation_id.

Limits: Autopilot.pause is cooperative; a provider/controller attempt already
running may finish. Cancelling an asyncio.to_thread waiter does not stop its
worker. computer_agent.run_goal has no status or stop API in this baseline:
general pause/resume must therefore return a component failure, not a UI flag.
No work_mode, cost/approval bypass, fabricated roster or second scheduler.
pause_background gates automatic admissions, not explicit owner submissions;
that separate unsupported scope is also returned as a component failure.
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any


_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_OWNER_WAIT = {"BLOCKED", "BLOCKED_NEEDS_OWNER", "WAITING_OWNER", "READY_FOR_OWNER"}
_TASK_STATES = {"CREATED": "andamento", "ASSIGNED": "andamento", "RUNNING": "andamento",
                "COMPLETED": "entregue"}
_TASK_REFS = ("_supervisor_task", "_scheduler_task", "_operation_consumer_task", "_provider_discovery_task")


def _row(value: Any) -> dict:
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _stamp(value: Any) -> str | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            dt = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str) and value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
        else:
            return None
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def _failure(code: str, error: str, **extra) -> dict:
    return {"success": False, "paused": None, "code": code, "error": error, **extra}


def _pc_limit() -> dict:
    return _failure("COMPUTER_AGENT_CONTROL_UNAVAILABLE",
                    "O agente do PC não expõe estado/cancelamento. Parada ou retomada não confirmada.")


def _admission_limit() -> dict:
    return _failure("OWNER_ADMISSION_UNCONTROLLED",
                    "A pausa existente bloqueia admissão autônoma, mas não novos comandos explícitos do proprietário.")


def _paused(components: dict) -> bool | None:
    # This control pauses the team's background work, not explicit PC commands.
    values = [components[name].get("paused") for name in ("lab", "autopilot", "legacy_lab")
              if name in components]
    if any(value is False for value in values):
        return False
    return True if values and all(value is True for value in values) else None


def _empty_state(error: str) -> dict:
    return {"success": False, "paused": None, "projects": [], "work": [], "activity": [],
            "decisions": [], "components": {}, "unknown": [], "error": error}


def _read_store(service) -> dict:
    """Read all teams/sessions, not snapshot's selected team or 50-row window."""
    store = service._get_runtime().store
    teams = [_row(t) for t in store.list_teams(include_archived=True)]
    sessions = []
    # SQLite LIMIT -1 is unbounded: a global pause must not miss row 51/201.
    for value in store.list_sessions(limit=-1):
        session = _row(value)
        sid = session["id"]
        sessions.append({**session, "tasks": [_row(t) for t in store.list_tasks(sid)],
                         "runs": [_row(r) for r in store.list_runs(sid)],
                         "artifacts": [_row(a) for a in store.list_artifacts(sid)],
                         "mission": store.mission_snapshot(sid),
                         "autonomy": store.autonomy_snapshot(sid)})
    return {"teams": teams, "agents": [_row(a) for a in store.list_agents(include_archived=True)],
            "memberships": {t["id"]: [_row(m) for m in store.list_memberships(t["id"])] for t in teams},
            "bindings": {t["id"]: [_row(b) for b in store.list_bindings(t["id"])] for t in teams},
            "sessions": sessions}


def _active(session: dict) -> bool:
    return (session.get("mission") or session).get("state") not in _TERMINAL


def _inflight(session: dict) -> bool:
    return (any(run.get("state") == "STARTED" for run in session["runs"])
            or any(step.get("status") in {"DISPATCHED", "RUNNING"}
                   for step in (session.get("mission") or {}).get("steps", [])))


def _autopilot_status(facts: dict) -> dict:
    active = [s for s in facts["sessions"] if _active(s)]
    uncontrolled = [s["id"] for s in active if not s.get("mission")
                    and (_inflight(s) or any(t.get("state") not in _TERMINAL for t in s["tasks"]))]
    if uncontrolled:
        return _failure("UNCONTROLLED_LAB_WORK", "Conversas do Lab sem controle de pausa por missão.",
                        session_ids=uncontrolled)
    # An open, idle chat is not an executing uncontrolled mission.
    active = [s for s in active if s.get("mission")]
    inflight = [s["id"] for s in facts["sessions"] if _inflight(s)]
    if inflight:
        return _failure("IN_FLIGHT_WORK", "Há execução em curso; pausa solicitada no próximo ponto seguro.",
                        paused=False, session_ids=inflight)
    flags = [(s.get("autonomy") or {}).get("pause_requested") for s in active]
    if any(type(flag) is not bool for flag in flags):
        return _failure("MISSION_PAUSE_UNKNOWN", "Estado de pausa de uma missão não confirmado.")
    return {"success": True, "paused": all(flags), "session_ids": [s["id"] for s in active]}


def _lab_status(service, policy: dict) -> dict:
    enabled = policy.get("background_enabled")
    if type(enabled) is not bool:
        return _failure("BACKGROUND_STATE_UNKNOWN", "Política de execução em segundo plano não confirmada.")
    running = [name for name in _TASK_REFS
               if getattr(service, name, None) is not None and not getattr(service, name).done()]
    if not enabled and running:
        return _failure("BACKGROUND_STILL_RUNNING", "Há consumidores do Lab ainda em execução.",
                        running_tasks=running)
    return {"success": True, "paused": not enabled, "background_enabled": enabled,
            "running_tasks": running}


def _avatar(agent: dict, role: str | None = None) -> dict | None:
    data = {"id": _text(agent.get("id")), "nome": _text(agent.get("name")),
            "papel": role or _text(agent.get("role"))}
    return data if all(data.values()) else None


def _project(snapshot: dict, facts: dict) -> tuple[list, list, list, list]:
    projects, work, activity, unknown = [], [], [], []
    agents = {a["id"]: a for a in facts["agents"]}
    sessions = facts["sessions"]
    participation = snapshot.get("participation") or {}

    for team in facts["teams"]:
        if team.get("archived"):
            continue
        tid = team["id"]
        working = {r["agent_id"] for s in sessions if s.get("team_id") == tid
                   for r in s["runs"] if r.get("state") == "STARTED"}
        if not _text(team.get("name")):
            unknown.append({"component": "projects", "id": tid, "reason": "Nome do time não confirmado."})
            continue
        bindings = {b["agent_id"]: b for b in facts["bindings"][tid] if b.get("active") is True}
        members = {m["agent_id"] for m in facts["memberships"][tid] if m.get("left_at") is None}
        members.update(bindings)
        rows = []
        for aid in sorted(members):
            agent = agents.get(aid)
            if agent and agent.get("archived"):
                continue
            avatar = _avatar(agent or {}, _text(bindings.get(aid, {}).get("role")) or None)
            assigned = [t for s in sessions if s.get("team_id") == tid for t in s["tasks"]
                        if t.get("assigned_agent_id") == aid and t.get("state") not in _TERMINAL]
            agent_paused = any((s.get("autonomy") or {}).get("pause_requested") is True
                               and not _inflight(s) and _active(s)
                               and any(t.get("assigned_agent_id") == aid for t in s["tasks"])
                               for s in sessions if s.get("team_id") == tid)
            status = ("trabalhando" if aid in working else "pausado" if agent_paused
                      else "disponivel" if participation.get(aid) == "IDLE" else None)
            if avatar is None or status is None:
                unknown.append({"component": "members", "id": aid, "project_id": tid,
                                "reason": "Identidade ou status não representável/confirmado.",
                                "source_status": participation.get(aid)})
                continue
            row = {"avatar": avatar, "status": status}
            current_ids = {r.get("task_id") for s in sessions for r in s["runs"]
                           if r.get("agent_id") == aid and r.get("state") == "STARTED"}
            current = next((t for t in assigned if t["id"] in current_ids), None)
            if current and _text(current.get("title")):
                row["tarefaAtual"] = current["title"]
            rows.append(row)
        projects.append({"id": tid, "nome": team["name"], "membros": rows})

    # The owner's projects are persisted sessions; a team is their shared crew.
    # Keeping only teams would make newly created objectives disappear from this UI.
    crews = {project["id"]: project for project in projects}
    session_projects = []
    used_teams = set()
    for session in sessions:
        title = _text(session.get("objective"))
        if not title:
            continue
        tid = session.get("team_id")
        crew = crews.get(tid)
        session_projects.append({"id": session["id"], "nome": title,
                                 "membros": crew["membros"] if crew else []})
        used_teams.add(tid)
    projects = session_projects + [p for p in projects if p["id"] not in used_teams]

    for session in sessions:
        paused = (session.get("autonomy") or {}).get("pause_requested") is True and not _inflight(session)
        for task in session["tasks"]:
            aid = task.get("assigned_agent_id")
            avatar = _avatar(agents.get(aid, {}))
            stamp = _stamp(task.get("updated_at"))
            state = _TASK_STATES.get(task.get("state"))
            if not avatar or not stamp or not state or not _text(task.get("title")):
                unknown.append({"component": "work", "id": task.get("id"),
                                "reason": "Responsável, data ou estado não representável/confirmado.",
                                "source_status": task.get("state")})
                continue
            if paused and task["state"] != "COMPLETED":
                state = "pausado"
            row = {"id": task["id"], "titulo": task["title"], "descricao": _text(task.get("instruction")),
                   "responsavel": avatar, "estado": state, "atualizadoEm": stamp}
            work.append(row)
            if state == "entregue":
                delivery = {"id": task["id"], "titulo": task["title"],
                            "descricao": _text(task.get("result")) or row["descricao"],
                            "responsavel": avatar, "concluidoEm": stamp}
                artifact = next((a for a in reversed(session["artifacts"])
                                 if a.get("task_id") == task["id"] and _text(a.get("path"))), None)
                if artifact:
                    delivery["entregavelUrl"] = artifact["path"]
                activity.append(delivery)
    work.sort(key=lambda row: datetime.fromisoformat(row["atualizadoEm"].replace("Z", "+00:00")), reverse=True)
    activity.sort(key=lambda row: datetime.fromisoformat(row["concluidoEm"].replace("Z", "+00:00")), reverse=True)
    return projects, work, activity, unknown


def _decisions(legacy: dict, facts: dict) -> tuple[list, dict]:
    rows, routes = [], {}
    for proposal in legacy.get("proposals", []):
        if proposal.get("status") not in {"DISCUSSION", "APPROVAL_REQUIRED"}:
            continue
        pid, title = _text(proposal.get("id")), _text(proposal.get("title"))
        if pid and title:
            rows.append({"id": pid, "pergunta": title, "contexto": _text(proposal.get("summary")),
                         "opcoes": ["Aprovar", "Recusar"]})
            routes[pid] = {"Aprovar": ("proposal", "APPROVE"), "Recusar": ("proposal", "REJECT")}
    for session in facts["sessions"]:
        mission = session.get("mission") or {}
        blocker = _text(mission.get("blocker"))
        sid = session["id"]
        if mission.get("state") in _OWNER_WAIT and blocker:
            if sid in routes:
                # Never disambiguate a real ID by inventing an ID or choosing a source.
                routes[sid] = {}
                continue
            rows.append({"id": sid, "pergunta": blocker, "contexto": session.get("objective", ""),
                         "opcoes": ["Cancelar missão"]})
            routes[sid] = {"Cancelar missão": ("admission", "lab.v1.cancel")}
    return rows, routes


class NovaUIIPC:
    def __init__(self, host):
        self.host = host
        self._lock = asyncio.Lock()
        self._legacy_stopping_task = None

    async def _reply(self, msg, result):
        await self.host.send_response(msg.request_id, result)

    async def _legacy_state(self) -> dict:
        lab = getattr(self.host, "lab", None)
        if lab is None:
            return {"proposals": []}
        state = await lab.get_state()
        if not isinstance(state, dict) or state.get("success") is False:
            raise RuntimeError("Estado de propostas do Lab indisponível.")
        return state

    async def _legacy_status(self) -> dict:
        lab = getattr(self.host, "lab", None)
        if lab is None:
            return {"success": True, "paused": True, "state": "NOT_LOADED"}
        state = await lab.autonomy_status()
        if not isinstance(state, dict) or state.get("success") is False:
            return _failure("LEGACY_STATUS_UNAVAILABLE", "Estado do conselho indisponível.")
        detached = self._legacy_stopping_task
        if detached is not None and not detached.done():
            return _failure("LEGACY_CYCLE_STILL_RUNNING", "Ciclo do conselho ainda terminando.", paused=False)
        enabled, running = state.get("enabled"), state.get("running")
        if type(enabled) is not bool or type(running) is not bool:
            return _failure("LEGACY_STATUS_UNKNOWN", "Estado do conselho não confirmado.")
        return {"success": True, "paused": not enabled and not running, "enabled": enabled, "running": running}

    async def state(self, msg):
        service = getattr(self.host, "lab_v1", None)
        if service is None:
            await self._reply(msg, _empty_state("ZARA Lab V1 indisponível; nenhuma equipe foi criada."))
            return
        try:
            snapshot = await service.snapshot()
            if not isinstance(snapshot, dict) or snapshot.get("success") is not True:
                await self._reply(msg, _empty_state(_text((snapshot or {}).get("error")) or "Estado do Lab não confirmado."))
                return
            facts = await asyncio.to_thread(_read_store, service)
            policy = await asyncio.to_thread(service._get_supervisor().policy)
            projects, work, activity, unknown = _project(snapshot, facts)
            decisions, _routes = _decisions(await self._legacy_state(), facts)
            components = {"lab": _lab_status(service, policy), "autopilot": _autopilot_status(facts),
                          "legacy_lab": await self._legacy_status(), "computer_agent": _pc_limit()}
            # success here means the projection was read, not that pause is confirmed.
            result = {"success": True, "paused": _paused(components), "scope": "team", "projects": projects,
                      "work": work, "activity": activity, "decisions": decisions,
                      "components": components, "unknown": unknown}
            if unknown:
                result["warning"] = "Parte dos dados não está confirmada e foi separada da atividade conhecida."
            await self._reply(msg, result)
        except Exception as exc:
            await self._reply(msg, _empty_state(f"Falha ao ler a UI nova: {exc}"))

    async def pause(self, msg):
        await self._control(msg, resume=False)

    async def resume(self, msg):
        await self._control(msg, resume=True)

    async def _control(self, msg, *, resume: bool):
        async with self._lock:
            service = getattr(self.host, "lab_v1", None)
            components = {"computer_agent": _pc_limit()}
            if not resume:
                components["lab_admission"] = _admission_limit()
            if service is None:
                components["lab"] = _failure("LAB_UNAVAILABLE", "ZARA Lab V1 indisponível.")
                components["autopilot"] = _failure("LAB_UNAVAILABLE", "Missões não puderam ser observadas.")
            else:
                # Disable future automatic admissions before touching in-flight missions.
                try:
                    supervisor = service._get_supervisor()
                    if not resume:
                        await asyncio.to_thread(supervisor.pause_background)
                    facts = await asyncio.to_thread(_read_store, service)
                    engine = None
                    failures = []
                    for session in facts["sessions"]:
                        if not session.get("mission") or not _active(session):
                            continue
                        if resume and (session.get("autonomy") or {}).get("pause_requested") is not True:
                            continue
                        try:
                            if engine is None:
                                engine = service._get_autopilot()
                            method = engine.resume if resume else engine.pause
                            receipt = await asyncio.to_thread(method, session["id"])
                            if not isinstance(receipt, dict) or receipt.get("success") is not True:
                                failures.append({"id": session["id"], "result": receipt})
                        except Exception as exc:
                            failures.append({"id": session["id"], "error": str(exc)})
                    if resume:
                        await asyncio.to_thread(supervisor.resume_background)
                    tasks_before_stop = [getattr(service, name, None) for name in _TASK_REFS]
                    receipt = await (service.start_background() if resume else service.stop_background())
                    policy = await asyncio.to_thread(supervisor.policy)
                    after = await asyncio.to_thread(_read_store, service)
                    components["lab"] = _lab_status(service, policy)
                    if not isinstance(receipt, dict) or receipt.get("success") is not True:
                        components["lab"] = _failure("BACKGROUND_CONTROL_FAILED", "Lab recusou o controle de execução.", result=receipt)
                    elif components["lab"].get("paused") is not (not resume):
                        components["lab"] = _failure("BACKGROUND_CONTROL_UNCONFIRMED", "Lab não confirmou o estado solicitado.", result=receipt)
                    elif not resume and any(task is not None and not task.done() for task in tasks_before_stop):
                        components["lab"] = _failure("BACKGROUND_STILL_RUNNING", "Uma tarefa do Lab foi desvinculada, mas ainda está em execução.")
                    elif resume and (getattr(service, "_supervisor_task", None) is None
                                     or service._supervisor_task.done()):
                        components["lab"] = _failure("BACKGROUND_CONTROL_UNCONFIRMED", "Supervisor do Lab não está em execução.", result=receipt)
                    components["autopilot"] = _autopilot_status(after)
                    # For resume an empty workload is quiescent, not a resume failure.
                    active = [s for s in after["sessions"] if _active(s) and s.get("mission")]
                    wrong = [s["id"] for s in active if (s.get("autonomy") or {}).get("pause_requested") is not (not resume)]
                    if failures or wrong:
                        components["autopilot"] = _failure("MISSION_CONTROL_UNCONFIRMED", "Uma ou mais missões não confirmaram o controle.",
                                                            failures=failures, session_ids=wrong)
                    elif resume and components["autopilot"].get("code") == "IN_FLIGHT_WORK":
                        components["autopilot"] = {"success": True, "paused": False,
                                                  "session_ids": [s["id"] for s in active]}
                except Exception as exc:
                    components["lab"] = _failure("LAB_CONTROL_FAILED", str(exc))
                    components["autopilot"] = _failure("MISSION_CONTROL_UNKNOWN", "Resultado do controle das missões não confirmado.")
                    if not resume:
                        # A broken observation must not prevent a best-effort stop.
                        try:
                            stop = await service.stop_background()
                            components["lab"]["stop_result"] = stop
                        except Exception as stop_exc:
                            components["lab"]["stop_error"] = str(stop_exc)
            # Continue to the other component even when Lab control failed.
            try:
                lab = getattr(self.host, "lab", None)
                if lab is not None:
                    detached = self._legacy_stopping_task
                    if resume and detached is not None and not detached.done():
                        components["legacy_lab"] = _failure("LEGACY_CYCLE_STILL_RUNNING", "Ciclo anterior ainda termina; retomada criaria outro ciclo.", paused=False)
                        lab = None
                if lab is not None:
                    if not resume:
                        task = getattr(getattr(lab, "lab_autonomy", None), "_task", None)
                        if task is not None:
                            self._legacy_stopping_task = task
                    receipt = await (lab.autonomy_start() if resume else lab.autonomy_stop())
                    if isinstance(receipt, dict) and receipt.get("success") is False:
                        components["legacy_lab"] = _failure("LEGACY_CONTROL_FAILED", "Conselho recusou o controle.", result=receipt)
                    else:
                        components["legacy_lab"] = await self._legacy_status()
                        if components["legacy_lab"].get("paused") is not (not resume) and components["legacy_lab"].get("success"):
                            components["legacy_lab"] = _failure("LEGACY_CONTROL_UNCONFIRMED", "Conselho não confirmou o estado solicitado.")
                else:
                    if "legacy_lab" not in components:
                        components["legacy_lab"] = await self._legacy_status()
            except Exception as exc:
                components["legacy_lab"] = _failure("LEGACY_CONTROL_FAILED", str(exc))
            success = all(components[name].get("success") is True
                          for name in ("lab", "autopilot", "legacy_lab"))
            result = {"success": success, "paused": _paused(components), "scope": "team", "components": components,
                      "notice": "Controle do trabalho automático da equipe. Comandos explícitos no PC continuam separados."}
            if not success:
                result["error"] = "Retomada da equipe não confirmada." if resume else "Pausa da equipe não confirmada; há trabalho em curso ou indisponível."
            await self._reply(msg, result)

    async def decision(self, msg):
        async with self._lock:
            payload = msg.payload
            if not isinstance(payload, dict):
                await self._reply(msg, {"success": False, "error": "Payload da decisão inválido."})
                return
            pid = payload.get("id")
            option = payload.get("option", payload.get("opcao", payload.get("decision")))
            if not isinstance(pid, str) or not pid.strip() or not isinstance(option, str):
                await self._reply(msg, {"success": False, "error": "id e option precisam ser textos válidos."})
                return
            option = {"APPROVE": "Aprovar", "REJECT": "Recusar"}.get(option, option)
            try:
                service = getattr(self.host, "lab_v1", None)
                facts = await asyncio.to_thread(_read_store, service) if service is not None else {"sessions": []}
                _rows, routes = _decisions(await self._legacy_state(), facts)
                route = routes.get(pid, {}).get(option)
                if route is None:
                    await self._reply(msg, {"success": False, "error": "Decisão ou opção não está pendente com esse ID real."})
                    return
                kind, action = route
                if kind == "proposal":
                    result = await self.host.lab.decide_proposal(pid, action)
                    expected = "APPROVED" if action == "APPROVE" else "REJECTED"
                    if not isinstance(result, dict) or result.get("success") is False:
                        await self._reply(msg, result if isinstance(result, dict) else {"success": False, "error": "Resultado da decisão desconhecido."})
                        return
                    confirmed = result.get("id") == pid and result.get("status") == expected
                    await self._reply(msg, {**result, "success": confirmed,
                                           **({} if confirmed else {"error": "Decisão não confirmada pela API de propostas."})})
                else:
                    result, _new = await service.admit_operation_for_dispatch(
                        msg.request_id, action, {"session_id": pid})
                    # No authorization/dispatch before renderer acknowledges this ACK.
                    await self._reply(msg, {**result, "id": pid, "confirmed": False, "completed": False})
            except Exception as exc:
                await self._reply(msg, {"success": False, "error": str(exc)})


def build_nova_ui_handlers(host) -> dict:
    controller = getattr(host, "_nova_ui_ipc", None)
    if controller is None:
        controller = NovaUIIPC(host)
        host._nova_ui_ipc = controller
    return {"nova-ui-state": controller.state, "nova-ui-pause": controller.pause,
            "nova-ui-resume": controller.resume, "nova-ui-decision": controller.decision}
