"""lab_ceo_decision.py — A DECISÃO da CEO quando o loop pausa.

O boletim (lab_cycle_brief) termina com "DECISÃO PEDIDA" (ex.: "retomar o loop
ou não"). Este módulo formaliza a decisão: ela vira registro auditável, pode
expirar (retomada com limite de ciclos), e se APLICA de verdade no loop e no
backlog. Lógica pura: sem modelo, sem rede, custo zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class DecisionType(str, Enum):
    RETOMAR = "RETOMAR"                        # loop volta a rodar, mesmos termos
    RETOMAR_COM_LIMITE = "RETOMAR_COM_LIMITE"   # retoma com teto (ciclos e/ou verba)
    ARQUIVAR_TAREFA = "ARQUIVAR_TAREFA"         # uma tarefa problemática sai da fila
    ENCERRAR = "ENCERRAR"                       # o loop não volta (fica pausado)
    ESCALAR = "ESCALAR"                         # chama o Alex (só nomes e estados)


DECIDIDORES = ("CEO", "ALEX")

_MAX_LINHAS_MOTIVO = 5
_MAX_CHARS_LINHA = 140
_CHAVES_LIMITE = ("max_cycles", "budget_usd")


class DecisionError(Exception):
    """Decisão malformada ou aplicação impossível."""


def _check_motivo(motivo: Any) -> str:
    if not isinstance(motivo, str) or not motivo.strip():
        raise DecisionError("motivo é obrigatório")
    linhas = [l for l in motivo.strip().splitlines() if l.strip()]
    if len(linhas) > _MAX_LINHAS_MOTIVO:
        raise DecisionError(f"motivo passa do teto de {_MAX_LINHAS_MOTIVO} linhas")
    for l in linhas:
        if len(l) > _MAX_CHARS_LINHA:
            raise DecisionError("linha do motivo passa de 140 caracteres")
    return "\n".join(linhas)


@dataclass(frozen=True)
class CeoDecision:
    decision_id: str
    cycle: int
    tipo: DecisionType
    motivo: str
    decidido_por: str
    targets: Tuple[str, ...]
    limite: Tuple[Tuple[str, Any], ...]
    expires_after_cycle: Optional[int]
    quando: str

    def limite_dict(self) -> Dict[str, Any]:
        return dict(self.limite)


class DecisionRegistry:
    """O caderno de decisões da CEO. Uma decisão, um registro, um journal."""

    def __init__(self, clock: Optional[Callable[[], str]] = None) -> None:
        self._clock = clock or (lambda: "?")
        self._decisions: List[CeoDecision] = []
        self._journal: List[Dict[str, Any]] = []
        self._seq = 0

    # ---------- registro ----------

    def registrar(
        self,
        tipo: Any,
        cycle: int,
        motivo: str,
        decidido_por: str = "CEO",
        targets: Tuple[str, ...] = (),
        limite: Optional[Dict[str, Any]] = None,
    ) -> CeoDecision:
        try:
            tipo = DecisionType(tipo)
        except ValueError:
            raise DecisionError(f"tipo de decisão inválido: {tipo}")
        if not isinstance(cycle, int) or cycle < 1:
            raise DecisionError("cycle precisa ser inteiro >= 1")
        motivo_ok = _check_motivo(motivo)
        if decidido_por not in DECIDIDORES:
            raise DecisionError("só a CEO ou o ALEX decidem")
        targets_t = tuple(targets)
        for t in targets_t:
            if not isinstance(t, str) or not t.strip():
                raise DecisionError("target precisa ser nome não vazio")
        self._checar_pertinencia(tipo, targets_t, limite)
        limite_t, expires = self._validar_limite(tipo, limite, cycle)

        self._seq += 1
        d = CeoDecision(
            decision_id=f"d{self._seq}",
            cycle=cycle,
            tipo=tipo,
            motivo=motivo_ok,
            decidido_por=decidido_por,
            targets=targets_t,
            limite=limite_t,
            expires_after_cycle=expires,
            quando=self._clock(),
        )
        self._decisions.append(d)
        self._log("decision_registered", decision_id=d.decision_id,
                  tipo=tipo.value, cycle=cycle, by=decidido_por)
        return d

    def _validar_limite(
        self, tipo: DecisionType, limite: Optional[Dict[str, Any]], cycle: int
    ) -> Tuple[Tuple[Tuple[str, Any], ...], Optional[int]]:
        if tipo is not DecisionType.RETOMAR_COM_LIMITE:
            return (), None
        if not isinstance(limite, dict) or not limite:
            raise DecisionError("RETOMAR_COM_LIMITE exige limite (max_cycles e/ou budget_usd)")
        for k in limite:
            if k not in _CHAVES_LIMITE:
                raise DecisionError(f"chave de limite inválida: {k}")
        if "max_cycles" in limite:
            mc = limite["max_cycles"]
            if not isinstance(mc, int) or mc < 1:
                raise DecisionError("max_cycles precisa ser inteiro >= 1")
        if "budget_usd" in limite:
            bu = limite["budget_usd"]
            if not isinstance(bu, (int, float)) or bu <= 0:
                raise DecisionError("budget_usd precisa ser número > 0")
        expires = cycle + limite["max_cycles"] if "max_cycles" in limite else None
        return tuple(sorted(limite.items())), expires

    def _checar_pertinencia(
        self, tipo: DecisionType, targets: Tuple[str, ...],
        limite: Optional[Dict[str, Any]],
    ) -> None:
        if tipo in (DecisionType.RETOMAR, DecisionType.ENCERRAR, DecisionType.ESCALAR):
            if targets:
                raise DecisionError(f"{tipo.value} não aceita targets")
            if limite:
                raise DecisionError(f"{tipo.value} não aceita limite")
        if tipo is DecisionType.ARQUIVAR_TAREFA and not targets:
            raise DecisionError("ARQUIVAR_TAREFA exige ao menos 1 target")

    # ---------- leitura ----------

    def get(self, decision_id: str) -> CeoDecision:
        for d in self._decisions:
            if d.decision_id == decision_id:
                return d
        raise DecisionError(f"decisão desconhecida: {decision_id}")

    def todas(self) -> List[CeoDecision]:
        return list(self._decisions)

    def journal(self) -> List[Dict[str, Any]]:
        return list(self._journal)

    def _log(self, event: str, **kw: Any) -> None:
        entry = {"ts": self._clock(), "event": event}
        entry.update(kw)
        self._journal.append(entry)


# ---------- validade ----------

def decisao_valida(d: CeoDecision, ciclo_atual: int) -> bool:
    """Decisão com limite de ciclos expira: o loop precisa pedir de novo."""
    if d.expires_after_cycle is None:
        return True
    return ciclo_atual <= d.expires_after_cycle


def ciclos_restantes(d: CeoDecision, ciclo_atual: int) -> Optional[int]:
    if d.expires_after_cycle is None:
        return None
    return max(0, d.expires_after_cycle - ciclo_atual)


# ---------- aplicação ----------

def resumir_para_boletim(d: CeoDecision) -> List[str]:
    """Até 4 linhas prontas pro próximo boletim. Só nomes e estados."""
    linhas = [f"DECISÃO {d.decision_id}: {d.tipo.value} (ciclo {d.cycle}, por {d.decidido_por})"]
    primeira = d.motivo.splitlines()[0]
    resto = len(d.motivo.splitlines()) - 1
    linhas.append(f"Motivo: {primeira}" + (f" (+{resto} linhas)" if resto else ""))
    if d.targets:
        linhas.append("Alvo(s): " + ", ".join(d.targets))
    if d.limite:
        limites = ", ".join(f"{k}={v}" for k, v in d.limite)
        linhas.append(f"Limite: {limites}")
    if d.expires_after_cycle is not None:
        linhas.append(f"Vale até o ciclo {d.expires_after_cycle}")
    else:
        linhas.append("Sem expiração")
    return linhas[:4]


def aplicar(
    d: CeoDecision,
    loop: Any,
    backlog: Any = None,
    notify: Optional[Callable[[str, str], None]] = None,
    registry: Optional[DecisionRegistry] = None,
) -> Dict[str, Any]:
    """Aplica a decisão no loop (duck-typing: precisa de resume()/state).

    RETOMAR/RETOMAR_COM_LIMITE -> loop.resume(). ARQUIVAR_TAREFA -> backlog.
    archive() por target. ENCERRAR -> não retoma (loop fica pausado).
    ESCALAR -> notify("ALERTA", linhas) com só nomes e estados.
    """
    efeito: Dict[str, Any] = {"decision_id": d.decision_id, "tipo": d.tipo.value}

    if d.tipo in (DecisionType.RETOMAR, DecisionType.RETOMAR_COM_LIMITE):
        loop.resume()
        efeito["efeito"] = "loop_retomado"
        if d.limite:
            efeito["limite"] = d.limite_dict()
            efeito["efeito"] = "loop_retomado_com_limite"
    elif d.tipo is DecisionType.ARQUIVAR_TAREFA:
        if backlog is None:
            raise DecisionError("ARQUIVAR_TAREFA precisa do backlog")
        arquivados = []
        for t in d.targets:
            backlog.archive(t, by=d.decidido_por, reason=d.motivo)
            arquivados.append(t)
        efeito["efeito"] = "tarefas_arquivadas"
        efeito["arquivados"] = arquivados
    elif d.tipo is DecisionType.ENCERRAR:
        efeito["efeito"] = "loop_encerrado"  # não retoma: fica pausado
    elif d.tipo is DecisionType.ESCALAR:
        if notify is None:
            raise DecisionError("ESCALAR precisa de notify")
        notify("ALERTA", "\n".join(resumir_para_boletim(d)))
        efeito["efeito"] = "escalado_para_alex"

    if registry is not None:
        registry._log("decision_applied", decision_id=d.decision_id,
                      efeito=efeito["efeito"])
    return efeito
