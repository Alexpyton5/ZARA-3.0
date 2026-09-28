"""
ZARA Lab — Primeiras propostas do backlog (alicerce da Fase D "LAB VIVO").

A CEO (zoe) semeia as primeiras propostas de melhoria a partir do mapa
VERIFICADO do app. Cada item carrega:
- Motivo: por que fazer (o valor pro Alex).
- Risco: o que pode dar errado (avaliado antes, não depois).
- Origem: de onde veio (TRIAGEM-42, MAPA-VIVO, RECON, TURNO).

Regras:
- Idempotente: rodar duas vezes NÃO duplica (marcador estável [seed:<slug>]
  no fim da descrição de cada item).
- As propostas entram como PROPOSED: o Lab avalia no primeiro ciclo e só a
  CEO aprova (regra do lab_backlog.py — "a zoe dá a DIREÇÃO").
- Lógica pura: sem rede, sem modelo, custo zero.
"""

from __future__ import annotations

from typing import Dict, List

try:  # dentro do app (pacote core.*)
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
except ImportError:  # teste flat
    from lab_backlog import BacklogError, BacklogState, LabBacklog

__all__ = ["SEED_PROPOSALS", "seed_marker", "seeded_keys", "seed"]


def seed_marker(slug: str) -> str:
    """Marcador estável que identifica um item semeado."""
    return f"[seed:{slug}]"


# As 8 primeiras propostas — todas de recon VERIFICADO, nada inventado.
# impact/urgency/cost: 1..5 (fórmula do lab_backlog: impacto*3 + urgência*2 - custo*2).
SEED_PROPOSALS: List[Dict[str, object]] = [
    {
        "slug": "suite-42-falhas",
        "title": "Zerar as 41 falhas persistentes da suíte Python",
        "description": (
            "Motivo: o portão final da MISSÃO GIGANTE exige suíte verde de verdade "
            "antes de qualquer push; enquanto 41 testes falharem, nada publica. "
            "Origem: TRIAGEM-42 (grupos: build/home 5, lab 11, mídia 6, memória 2, "
            "relay 9, canal 3, janelas 5) — 41/42 já falhavam no baseline, não são "
            "regressão. Risco: mexer em teste pra fingir verde é PROIBIDO (gate "
            "permanente); corrigir por causa raiz, um grupo por vez."
        ),
        "impact": 5, "urgency": 4, "cost": 4,
    },
    {
        "slug": "vosk-modelo-offline",
        "title": "Garantir o modelo Vosk PT offline (voz que não abandona)",
        "description": (
            "Motivo: a voz PT-BR local (Vosk) é a rede de segurança da cascata "
            "Kore→OmniVoice→edge→kokoro quando a internet cai; se o modelo não "
            "estiver no pacote, a reserva falha justo na hora que mais importa "
            "(critério nº 1 do Alex: não deixar na mão). Origem: RECON voz "
            "(gemini_live_voice.py:365 lê %LOCALAPPDATA%\\ZARA3\\models\\vosk). "
            "Risco: o modelo pesa ~50MB; baixar em runtime sem avisar pode "
            "surpreender — avisar no pré-voo antes."
        ),
        "impact": 4, "urgency": 3, "cost": 2,
    },
    {
        "slug": "flag-smart-router",
        "title": "Ligar a flag ZARA_SMART_ROUTER (roteador já plugado)",
        "description": (
            "Motivo: o roteador inteligente está plugado no app (smart_router.py + "
            "smart_router_plug.py, 25 testes verdes) mas a flag vem desligada por "
            "segurança; ligar faz o hint CHAT/LEVE/PESADO guiar o model_router sem "
            "mudar nada quando off. Origem: TURNO 22:41 (plug verificado 12/12 "
            "contra o model_router real). Risco: ligar cedo demais muda o "
            "roteamento de produção; ligar com o Lab observando e rollback pronto."
        ),
        "impact": 3, "urgency": 3, "cost": 1,
    },
    {
        "slug": "ipc-handlers-fatiar",
        "title": "Fatiar core/ipc_handlers.py (6.716 linhas)",
        "description": (
            "Motivo: o 'telefonista' virou uma cidade — ninguém conhece tudo; cada "
            "mudança ali é cirurgia às cegas e o risco de quebrar outra coisa "
            "cresce a cada linha. Origem: MAPA-VIVO (1.932 → 6.716 linhas). "
            "Risco: refatorar à toa quebra fiação viva; fatiar por domínio com a "
            "suíte como rede de segurança, um pedaço por vez."
        ),
        "impact": 4, "urgency": 3, "cost": 5,
    },
    {
        "slug": "scheduler-executor",
        "title": "Ligar o scheduler ao executor (hoje agenda mas não executa)",
        "description": (
            "Motivo: o agendador existe mas não tem executor — lembrete agendado "
            "que nunca dispara é promessa quebrada pro Alex. Origem: MAPA-VIVO "
            "(peças de museu). Risco: executor mal feito dispara ação na hora "
            "errada; começar só com ações de leitura/notificação."
        ),
        "impact": 3, "urgency": 2, "cost": 3,
    },
    {
        "slug": "paineis-menu-mortos",
        "title": "Implementar ou remover os 4 painéis não implementados do menu",
        "description": (
            "Motivo: botão que não faz nada é vitrine — e o Alex descarta vitrine "
            "na hora (regra permanente: nada de peça de museu). Origem: MAPA-VIVO "
            "(peças de museu). Risco: remover painel que alguém usa; checar uso "
            "real antes de cortar."
        ),
        "impact": 3, "urgency": 2, "cost": 3,
    },
    {
        "slug": "memory-galaxy",
        "title": "Resolver o Memory Galaxy (placeholder) ou remover",
        "description": (
            "Motivo: placeholder no app é dívida visível; ou vira função real "
            "ligada à memória do Lab, ou sai (regra: nada de peça de museu). "
            "Origem: MAPA-VIVO (peças de museu). Risco: virar função real pode "
            "duplicar a memória operacional do Lab (lab_memory.py) — integrar, "
            "não duplicar."
        ),
        "impact": 2, "urgency": 2, "cost": 2,
    },
    {
        "slug": "chat-tsx-mortos",
        "title": "Ressuscitar ou remover Chat.tsx e ConversaInstrumento.tsx",
        "description": (
            "Motivo: dois componentes de chat completos (561 + 218 linhas) que "
            "nada renderiza — ou o Chat.tsx vira a base da conversa única "
            "(FASE C), ou sai do repo. Origem: RECON 23:50 (mapa da conversa "
            "única). Risco: ressuscitar código morto traz dependências velhas; "
            "auditar imports antes."
        ),
        "impact": 2, "urgency": 2, "cost": 2,
    },
]


def seeded_keys(backlog: LabBacklog) -> Dict[str, str]:
    """slug -> item_id dos itens já semeados (qualquer estado)."""
    found: Dict[str, str] = {}
    for item in backlog.ranked():
        for proposal in SEED_PROPOSALS:
            slug = str(proposal["slug"])
            if slug not in found and seed_marker(slug) in item.description:
                found[slug] = item.item_id
    return found


def seed(backlog: LabBacklog) -> List[str]:
    """Registra as propostas que ainda não estão no backlog. Idempotente.

    Devolve os item_ids criados nesta chamada (lista vazia = nada novo).
    """
    done = seeded_keys(backlog)
    created: List[str] = []
    for proposal in SEED_PROPOSALS:
        slug = str(proposal["slug"])
        if slug in done:
            continue
        description = f"{proposal['description']} {seed_marker(slug)}"
        item = backlog.propose(
            title=str(proposal["title"]),
            description=description,
            proposed_by="CEO",
            impact=int(proposal["impact"]),
            urgency=int(proposal["urgency"]),
            cost=int(proposal["cost"]),
        )
        if item.state is not BacklogState.PROPOSED:
            raise BacklogError("seed deve criar itens PROPOSED")
        created.append(item.item_id)
    return created
