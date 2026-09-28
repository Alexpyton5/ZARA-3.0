"""Boletim do ciclo da CEO — o resumo que a CEO lê para decidir.

O condutor do loop (lab_loop) roda ciclos e devolve CycleReports. Este módulo
transforma esses relatórios num Relatorio (lab_report) que passa no portão do
modo silencioso: é o boletim que alimenta a decisão no resume() e o bilhete
do despertar.

Tipo do boletim (modo silencioso, regra permanente do Alex):
- BLOQUEIO: o loop pausou (backoff) e a CEO precisa decidir → DECISÃO PEDIDA.
- PROGRESSO: houve tarefa concluída → fim de ciclo.
- STATUS: ciclo ocioso ou quieto, sem decisão pendente.

Regras duras:
- só nomes e estados, nunca conteúdo de arquivo: o detalhe do journal NUNCA
  entra nas linhas — só contagens, ciclos e nomes de eventos;
- o boletim sempre passa no portão (pode_falar() == True): tipo válido, teto
  de 10 linhas, FEITO no PROGRESSO e DECISÃO PEDIDA no BLOQUEIO são garantidos
  aqui, não na chamada.

Os CycleReports são lidos por duck-typing (cycle, idle, idle_reason,
dispatched, completed, failed, stuck_released, released_failed, paused,
journal) — o boletim não puxa o loop nem o backlog.

Lógica pura, stdlib, zero custo/rede/quota. Peça do alicerce LAB VIVO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

try:
    from core.lab_report import BLOQUEIO, PROGRESSO, STATUS, MAX_LINHAS, Relatorio
except ImportError:  # rodando flat (testes locais)
    from lab_report import BLOQUEIO, PROGRESSO, STATUS, MAX_LINHAS, Relatorio


class BriefError(Exception):
    """O boletim não pôde ser composto dentro do protocolo."""


# Motivos de ociosidade vindos do lab_loop (strings, sem importar o loop).
IDLE_PT = {
    "NO_APPROVED_WORK": "fila de aprovados vazia",
    "NO_ASSIGNABLE": "aprovados sem assento capaz",
    "BUDGET_EXHAUSTED": "orçamento do loop esgotado",
    "PAUSED": "loop pausado (falhas seguidas)",
}

# Eventos do journal que contam como alerta (só nomes, nunca detalhe).
ALERT_EVENTS = frozenset(
    {
        "loop_paused",
        "watchdog_released",
        "watchdog_release_failed",
        "cycle_failed",
        "cycle_turn_crashed",
        "failed_released",
        "failed_release_failed",
    }
)


@dataclass
class ResumoCiclos:
    """Agregado de vários CycleReports, só com nomes/estados/números."""

    ciclos: List[int]
    despachadas: int = 0
    concluidas: int = 0
    falharam: int = 0
    travadas_devolvidas: List[str] = None  # item_ids (nomes, não conteúdo)
    falhas_devolvidas: List[str] = None
    alertas: int = 0
    pausou: bool = False
    idle_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.travadas_devolvidas is None:
            self.travadas_devolvidas = []
        if self.falhas_devolvidas is None:
            self.falhas_devolvidas = []


def agregar(reports: Sequence[Any]) -> ResumoCiclos:
    """Soma os CycleReports num resumo. Não lê journal.detail (segredo)."""
    res = ResumoCiclos(ciclos=[])
    for r in reports:
        res.ciclos.append(int(getattr(r, "cycle", 0)))
        res.despachadas += int(getattr(r, "dispatched", 0) or 0)
        res.concluidas += int(getattr(r, "completed", 0) or 0)
        res.falharam += int(getattr(r, "failed", 0) or 0)
        res.travadas_devolvidas.extend(getattr(r, "stuck_released", None) or [])
        res.falhas_devolvidas.extend(getattr(r, "released_failed", None) or [])
        if getattr(r, "paused", False):
            res.pausou = True
        # conta só o NOME do evento — o detalhe nunca entra no boletim
        for entry in getattr(r, "journal", None) or []:
            if isinstance(entry, dict) and entry.get("event") in ALERT_EVENTS:
                res.alertas += 1
        # o motivo de ociosidade mais recente (último ciclo não-nulo)
        idle_reason = getattr(r, "idle_reason", None)
        if idle_reason:
            res.idle_reason = str(idle_reason)
    return res


def _intervalo(ciclos: List[int]) -> str:
    if not ciclos:
        return "0"
    if len(ciclos) == 1:
        return str(ciclos[0])
    return "%d-%d" % (ciclos[0], ciclos[-1])


def _caber(feito: List[str], estado: List[str], erro: List[str],
           sugestao: List[str]) -> Relatorio:
    """Monta o Relatorio garantindo o teto de MAX_LINHAS (corta ESTADO/ERRO)."""
    rel = Relatorio(tipo=STATUS, feito=list(feito), estado=list(estado),
                    erro=list(erro), sugestao=list(sugestao))
    # FEITO e SUGESTÃO são o essencial; ESTADO/ERRO encolhem se estourar.
    while rel.total_linhas() > MAX_LINHAS and len(rel.estado) > 1:
        rel.estado.pop()
    while rel.total_linhas() > MAX_LINHAS and len(rel.erro) > 1:
        rel.erro.pop()
    while rel.total_linhas() > MAX_LINHAS and rel.estado:
        rel.estado.pop()
    while rel.total_linhas() > MAX_LINHAS and rel.erro:
        rel.erro.pop()
    if rel.total_linhas() > MAX_LINHAS:
        raise BriefError("boletim não coube no teto de %d linhas" % MAX_LINHAS)
    return rel


def montar_brief(resumo: ResumoCiclos, *,
                 budget_used_usd: float = 0.0,
                 loop_state: str = "RUNNING") -> Relatorio:
    """Compõe o boletim da CEO a partir do resumo. Sempre passa no portão."""
    intervalo = _intervalo(resumo.ciclos)
    feito: List[str] = []
    estado: List[str] = []
    erro: List[str] = []
    sugestao: List[str] = []

    if resumo.concluidas > 0:
        feito.append(
            "ciclo(s) %s: %d tarefa(s) concluída(s) de %d despachada(s)"
            % (intervalo, resumo.concluidas, resumo.despachadas)
        )
    if resumo.travadas_devolvidas:
        feito.append(
            "%d item(ns) travado(s) devolvido(s) pra fila pelo watchdog"
            % len(resumo.travadas_devolvidas)
        )

    estado.append("loop: %s" % ("PAUSADO" if resumo.pausou else loop_state))
    estado.append("ciclos rodados: %d" % len(resumo.ciclos))
    if budget_used_usd > 0:
        estado.append("orçamento usado: US$ %.2f" % budget_used_usd)
    if resumo.idle_reason:
        estado.append("ocioso: %s"
                      % IDLE_PT.get(resumo.idle_reason, resumo.idle_reason))

    if resumo.falharam > 0:
        erro.append("%d tarefa(s) falharam e voltaram pra fila"
                    % resumo.falharam)
    if resumo.alertas > 0:
        erro.append("%d alerta(s) no journal do loop" % resumo.alertas)

    if resumo.pausou:
        tipo = BLOQUEIO
        decisao = "retomar o loop (resume) ou não"
        sugestao.append("a CEO decide: retomar o loop ou não")
    elif resumo.concluidas > 0:
        tipo = PROGRESSO
        decisao = ""
        sugestao.append("seguir o plano do turno")
    else:
        tipo = STATUS
        decisao = ""
        if resumo.idle_reason == "NO_APPROVED_WORK":
            sugestao.append("aprovar mais propostas no backlog")
        elif resumo.idle_reason == "NO_ASSIGNABLE":
            sugestao.append("revisar tipos sem assento no plano da CEO")
        elif resumo.idle_reason == "BUDGET_EXHAUSTED":
            sugestao.append("a CEO define se amplia o orçamento")
        elif resumo.falharam > 0:
            sugestao.append("investigar a causa raiz das falhas")
        else:
            sugestao.append("nada pendente — loop segue")

    rel = _caber(feito, estado, erro, sugestao)
    rel.tipo = tipo
    rel.decisao_pedida = decisao
    violacoes = rel.validar()
    if violacoes:
        raise BriefError("boletim inválido: " + "; ".join(violacoes))
    return rel


def texto_brief(rel: Relatorio) -> str:
    """Devolve o texto do boletim. Só fala se passar no portão."""
    if not rel.pode_falar():
        raise BriefError("boletim não passou no portão do modo silencioso")
    return rel.formatar()


def boletim_de_ciclos(reports: Sequence[Any], *,
                      budget_used_usd: float = 0.0,
                      loop_state: str = "RUNNING") -> str:
    """Atalho: agrega os CycleReports e devolve o texto do boletim pronto."""
    return texto_brief(montar_brief(agregar(reports),
                                    budget_used_usd=budget_used_usd,
                                    loop_state=loop_state))
