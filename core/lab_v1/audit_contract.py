"""Offline contracts for the future natural-language Luna audit.

This module contains no provider calls and does not create or mutate a Lab
mission. It only validates the boundary that a live Luna run will use.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from core.lab_v1.domain import Availability

AUDIT_AREAS = (
    "mission_controller", "agents_teams", "codex_openai", "nvidia",
    "claude_policy", "routing", "delegation", "persistence_restart",
    "verification", "hermes", "voice", "golden_path", "manual_exit",
)
AUDIT_STATUSES = ("WORKING", "PARTIAL", "BLOCKED", "NOT_PROVEN", "NOT_IMPLEMENTED")


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def is_luna_audit_intent(text: str) -> bool:
    """Recognize only the owner's natural Luna-audit request, not a model ID."""
    folded = _fold(text)
    return bool(
        re.search(r"\bluna\b", folded)
        and re.search(r"\b(audit|auditoria|auditar|verificar|revisar)\w*\b", folded)
        and re.search(r"\b(zara|voce|voces|propria)\b", folded)
    )


def resolve_luna_agent(agents: Iterable[Any]) -> dict[str, Any] | None:
    """Resolve an existing, distinct Luna profile without claiming availability.

    The returned record is routing intent only. Live availability and a real Run
    remain provider evidence and are deliberately not inferred here.
    """
    for agent in agents:
        row = agent.to_dict() if hasattr(agent, "to_dict") else dict(agent)
        if row.get("archived") or row.get("provider_id") != "codex_cli":
            continue
        if row.get("model") == "gpt-5.6-luna" or _fold(row.get("name", "")) == "luna":
            return {
                "agent_id": row.get("id"), "name": row.get("name", "Luna"),
                "provider_id": "codex_cli", "model": "gpt-5.6-luna",
                "effort": row.get("effort") or "medium", "availability": "UNPROVEN",
            }
    return None


def build_luna_audit_task(session_id: str, resolved: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic task envelope; persistence happens only live."""
    if not session_id or not resolved.get("agent_id") or resolved.get("model") != "gpt-5.6-luna":
        raise ValueError("A Luna AgentInstance is required")
    return {
        "id": f"{session_id}:luna-audit",
        "title": "Auditoria factual da ZARA",
        "assigned_agent_id": resolved["agent_id"],
        "provider_id": "codex_cli", "model": "gpt-5.6-luna", "effort": resolved.get("effort", "medium"),
        "instruction": "Audite somente evidencias persistidas da ZARA e classifique cada area com status e evidencia.",
        "acceptance": "Relatorio estruturado com areas, status factual, evidencia, principal bloqueio e capacidade atual.",
    }


def normalize_audit_result(report: Any) -> dict[str, Any]:
    """Validate the small result envelope ZARA may later summarize."""
    if not isinstance(report, dict):
        raise ValueError("Audit result must be an object")
    areas = report.get("areas")
    if not isinstance(areas, list) or not areas:
        raise ValueError("Audit result needs at least one area")
    normalized = []
    seen = set()
    for item in areas:
        if not isinstance(item, dict):
            raise ValueError("Audit area must be an object")
        area, status = str(item.get("area", "")), str(item.get("status", ""))
        if area not in AUDIT_AREAS or area in seen or status not in AUDIT_STATUSES:
            raise ValueError("Audit area or status is outside the evidence contract")
        evidence = str(item.get("evidence", "")).strip()
        if not evidence or len(evidence) > 600:
            raise ValueError("Every audit area needs bounded evidence")
        seen.add(area)
        normalized.append({"area": area, "status": status, "evidence": evidence})
    blocker = str(report.get("main_blocker", "")).strip()
    today = str(report.get("can_do_today", "")).strip()
    if not blocker or not today:
        raise ValueError("Audit result needs a blocker and today's capability")
    return {"areas": normalized, "main_blocker": blocker[:600], "can_do_today": today[:600]}


def summarize_for_owner(report: Any) -> str:
    """Turn a validated technical audit into plain Portuguese for Alex."""
    data = normalize_audit_result(report)
    labels = {"WORKING": "funcionando", "PARTIAL": "parcialmente", "BLOCKED": "bloqueado",
              "NOT_PROVEN": "ainda não comprovado", "NOT_IMPLEMENTED": "ainda não implementado"}
    counts = {status: sum(item["status"] == status for item in data["areas"]) for status in AUDIT_STATUSES}
    parts = ["Alex, o Luna terminou a auditoria da ZARA."]
    parts.append(f"Hoje há {counts['WORKING']} área(s) comprovadamente funcionando e {counts['PARTIAL']} parcialmente funcionando.")
    if counts["BLOCKED"] or counts["NOT_PROVEN"] or counts["NOT_IMPLEMENTED"]:
        pending = counts["BLOCKED"] + counts["NOT_PROVEN"] + counts["NOT_IMPLEMENTED"]
        parts.append(f"Ainda existem {pending} área(s) bloqueada(s), não comprovada(s) ou não implementada(s).")
    parts.append(f"O principal bloqueio é: {data['main_blocker']}")
    parts.append(f"Hoje eu consigo: {data['can_do_today']}")
    return " ".join(parts)


def quota_wait_state(availability: Availability | str) -> str:
    """Map quota exhaustion to a resumable wait, never permanent failure."""
    value = availability.value if isinstance(availability, Availability) else str(availability)
    return "WAITING_PROVIDER" if value in {"QUOTA_EXHAUSTED", "RATE_LIMITED", "BUSY"} else value


def resume_preserves_owner_touch(metrics: dict[str, Any]) -> bool:
    return metrics.get("owner_touches") == 1 and metrics.get("session_id") and not metrics.get("create_new_mission")
