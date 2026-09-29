# -*- coding: utf-8 -*-
"""Registro da verdade (FRENTE C — MISSAO GIGANTE 3 "JARVIS REAL").

Para cada superficie da interface que exibe numero ou texto, este modulo diz
qual e a fonte de dado real por tras — ou declara ASSUMIDO ("e atalho — abre
o app", sem numero falso). E a lista publicada do que foi LIGADO de verdade
vs. ASSUMIDO como atalho (criterio de aceite da frente C).

Status possiveis:
- "real": o valor exibido vem de fonte viva (psutil, IPC do backend etc.).
- "assumido": e atalho — abre o app/servico real; NENHUM numero e exibido.
- "demo": DADO FALSO conhecido, proibido de aparecer. Listado aqui SOMENTE
  para cacar e remover; nunca como fonte legitima.

Trava C3: `assert_no_fake_backend_strings()` varre o backend Python atras das
impressoes digitais dos dados falsos conhecidos e falha se achar qualquer uma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

VALID_STATUS = ("real", "assumido", "demo")


@dataclass(frozen=True)
class Surface:
    """Uma superficie da UI que exibe numero ou texto."""

    key: str
    label: str
    status: str
    source: str
    evidence: str


_REGISTRY: List[Surface] = [
    # ---- Comunicacoes: ASSUMIDO (atalho, sem numero falso) ----
    Surface(
        key="comms.whatsapp",
        label="Card Comunicacoes — WhatsApp",
        status="assumido",
        source="atalho para https://web.whatsapp.com/ (desktop.openExternal)",
        evidence="frontend/src/main.ts:526; CommunicationsCard mostra '—' + "
        "'contagem de mensagens nao conectada'",
    ),
    Surface(
        key="comms.telegram",
        label="Card Comunicacoes — Telegram",
        status="assumido",
        source="atalho para https://web.telegram.org/ (desktop.openExternal)",
        evidence="frontend/src/main.ts:527; CommunicationsCard mostra '—'",
    ),
    Surface(
        key="comms.instagram",
        label="Card Comunicacoes — Instagram",
        status="assumido",
        source="atalho para https://www.instagram.com/ (desktop.openExternal)",
        evidence="frontend/src/main.ts:528; CommunicationsCard mostra '—'",
    ),
    Surface(
        key="comms.gmail",
        label="Card Comunicacoes — Gmail",
        status="assumido",
        source="atalho para https://mail.google.com/ (desktop.openExternal)",
        evidence="frontend/src/main.ts:529; CommunicationsCard mostra '—'",
    ),
    # ---- Sistema: LIGADO (dado real) ----
    Surface(
        key="system.metrics",
        label="Painel Sistema — CPU/RAM/disco",
        status="real",
        source="psutil.cpu_percent / virtual_memory / disk_usage",
        evidence="core/ipc_handlers.py:5343-5348",
    ),
    Surface(
        key="system.info",
        label="Painel Sistema — plataforma/hardware",
        status="real",
        source="platform.system/version/machine + psutil (cpu_count, boot_time...)",
        evidence="core/ipc_handlers.py:6271-6286",
    ),
    Surface(
        key="memory.galaxy",
        label="Card 'Para voce' — memorias",
        status="real",
        source="zaraIPC.memoryGalaxy.list() (backend real; UI tolera falha)",
        evidence="ForYouCard.tsx: contagem so aparece se o IPC responder",
    ),
    Surface(
        key="reminders.next",
        label="Card 'Para voce' — proximo lembrete",
        status="real",
        source="zaraIPC.reminders.list('SCHEDULED') (backend real)",
        evidence="ForYouCard.tsx: 'Nenhum lembrete agendado' quando vazio",
    ),
    Surface(
        key="lab.tasks",
        label="Card 'Para voce' — tarefas do ZARA Lab",
        status="real",
        source="zaraIPC.lab.state() (sessoes reais do Lab)",
        evidence="ForYouCard.tsx: taskCount null => sem numero exibido",
    ),
    # ---- Demo: DADO FALSO conhecido — caçar e remover ----
    Surface(
        key="demo.titanium_fallback",
        label="Demo zara-titanium-emerald — objeto Dm (fallback com dados inventados)",
        status="demo",
        source="NENHUMA — '17 rotinas ativas', '8 dispositivos conectados', "
        "'CPU 12%', '14 memorias relacionadas', 'Ultima conversa ha 18 min', "
        "'20:42 Analisando sistema', '09:00 Reuniao de alinhamento' etc.",
        evidence="frontend/public/zara-titanium-emerald (bundle no app.asar); "
        "ACAO: remover do bundle ou marcar 'DEMONSTRACAO — dados ficticios'",
    ),
]

# Impressoes digitais dos dados falsos conhecidos. Se qualquer uma aparecer
# num .py do backend (core/), a trava C3 falha.
DEMO_FALSE_FINGERPRINTS = (
    "rotinas ativas",
    "dispositivos conectados",
    "Analisando sistema",
    "Sincronizando arquivos",
    "memorias relacionadas",
    "Ultima conversa ha",
    "Reuniao de alinhamento",
    "Apresentacao do projeto",
    "Sessao de foco",
    "Revisao de entregas",
    "Wi-Fi 5 GHz conectado",
    "VPN desconectada",
    "Monitor, telefone, relogio e iluminacao",
)

# Arquivos que PODEM citar as impressoes digitais (o proprio registro).
_FINGERPRINT_ALLOWLIST = ("truth_registry.py",)


def get_registry() -> Dict[str, Surface]:
    return {s.key: s for s in _REGISTRY}


def status(key: str) -> Optional[Surface]:
    return get_registry().get(key)


def honest_summary() -> Dict[str, List[str]]:
    """Lista publicada: o que foi LIGADO de verdade vs. ASSUMIDO como atalho."""
    out = {"ligado": [], "assumido": [], "demo_falso": []}
    for s in _REGISTRY:
        if s.status == "real":
            out["ligado"].append(f"{s.label} — fonte: {s.source}")
        elif s.status == "assumido":
            out["assumido"].append(f"{s.label} — {s.source}")
        else:
            out["demo_falso"].append(f"{s.label} — {s.source}")
    return out


def assert_no_fake_backend_strings(repo_root: "str | Path | None" = None) -> List[str]:
    """Trava C3: falha se dado falso conhecido existir no backend Python.

    Retorna a lista de ocorrencias encontradas (vazia = trava passou).
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    found: List[str] = []
    patterns = [re.compile(re.escape(fp), re.IGNORECASE) for fp in DEMO_FALSE_FINGERPRINTS]
    for py in sorted((root / "core").rglob("*.py")):
        if py.name in _FINGERPRINT_ALLOWLIST:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat, fp in zip(patterns, DEMO_FALSE_FINGERPRINTS):
                if pat.search(line):
                    rel = py.relative_to(root)
                    found.append(f"{rel}:{lineno}: '{fp}' -> {line.strip()[:120]}")
    if found:
        raise AssertionError(
            "TRAVA C3 FALHOU — dado falso conhecido no backend:\n" + "\n".join(found)
        )
    return found
