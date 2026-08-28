"""Evolution Report for ZARA Project.

Generates a human-readable report showing the evolution of the project
based on decisions log and mentor events.
"""
from __future__ import annotations

from memory.project_memory import ProjectMemory


def generate_evolution_report(pm: ProjectMemory) -> str:
    """Generate a markdown report of project evolution.

    Args:
        pm: An instance of ProjectMemory.

    Returns:
        A markdown string with the evolution report.
    """
    lines = []
    lines.append("# Relatório de Evolução do Projeto ZARA\n")

    # Decisions log
    decisions_doc = pm.get_doc("decisions")
    if decisions_doc and decisions_doc.get("content"):
        lines.append("## Diário de Decisões\n")
        lines.append(decisions_doc["content"])
        lines.append("\n")
    else:
        lines.append("## Diário de Decisões\n")
        lines.append("Nenhuma decisão registrada ainda.\n\n")

    # Mentor events
    events = pm.recent_events(limit=50)  # get up to 50 recent events
    if events:
        lines.append("## Eventos do Mentor (últimos 50)\n")
        for ev in events:
            # Format timestamp
            from datetime import datetime
            ts = datetime.fromtimestamp(ev["ts"])
            timestamp_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- [{timestamp_str}] {ev.get('status', 'N/A')}: {ev.get('summary', '')}")
        lines.append("\n")
    else:
        lines.append("## Eventos do Mentor\n")
        lines.append("Nenhum evento registrado ainda.\n\n")

    # Project state (optional)
    state_doc = pm.get_doc("state")
    if state_doc and state_doc.get("content"):
        lines.append("## Estado Atual do Projeto\n")
        lines.append(state_doc["content"])
        lines.append("\n")

    return "\n".join(lines)


if __name__ == "__main__":
    # For direct testing
    pm = ProjectMemory()
    print(generate_evolution_report(pm))