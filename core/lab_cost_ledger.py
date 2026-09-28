"""Livro-caixa de custo do Lab — quem gastou o quê, com teto e prova.

O loop (lab_loop) concede orçamento por ciclo. Este módulo registra o gasto
REAL: cada vez que um assento usa um recurso com custo (modelo, API), o gasto
entra aqui com assento, tarefa, ciclo e valor. O Alex odeia custo-surpresa: o
ledger é a prova auditável de que o "custo pago zero" é verdade — e o alarme
quando não é.

Regras duras:
- dinheiro em Decimal com 6 casas (microdólar); float nunca guarda dinheiro;
- rejeita valor negativo, NaN, infinito, assento/tarefa/ciclo vazios;
- assento válido = um dos 11 assentos fixos (ancorado em FIXED_SEATS de
  verdade, igual ao lab_memory);
- teto por tarefa: gasto acima do teto REGISTRA do mesmo jeito, mas flagra
  over_cap=True e vira ALERTA — nunca esconde gasto;
- teto por ciclo e teto total: estourou → ALERTA; nunca crasha o chamador;
- gasto zero é evento válido: é assim que o Lab prova "sem chamada paga";
- journal auditável com relógio injetável; o notify (se dado) recebe só nomes
  e estados, nunca conteúdo de arquivo;
- `resumo_para_boletim()` devolve linhas prontas p/ o ciclo da CEO (nomes e
  números, sem detalhe).

Lógica pura, stdlib, zero custo/rede/quota. Peça do alicerce LAB VIVO.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional

try:
    from core.lab_v1.fixed_seats import FIXED_SEATS
except ImportError:  # rodando flat (testes locais)
    from lab_v1.fixed_seats import FIXED_SEATS

SEATS = frozenset(role.value for role in FIXED_SEATS)

CASAS = Decimal("0.000001")  # microdólar: precisão honesta p/ custo de modelo


class LedgerError(Exception):
    """O livro-caixa recusou um lançamento inválido."""


def _dinheiro(valor: Any) -> Decimal:
    """Converte p/ Decimal com 6 casas; rejeita o que não é dinheiro válido."""
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise LedgerError("VALOR_INVALIDO")
    if d.is_nan() or d.is_infinite():
        raise LedgerError("VALOR_INVALIDO")
    if d < 0:
        raise LedgerError("VALOR_NEGATIVO")
    return d.quantize(CASAS, rounding=ROUND_HALF_UP)


@dataclass
class Lancamento:
    """Um gasto registrado: quem, em qual tarefa, em qual ciclo, quanto."""

    seq: int
    ciclo: str
    assento: str
    tarefa: str
    usd: Decimal
    teto_tarefa: Decimal
    over_cap: bool = False
    ts: Any = None


@dataclass
class CostLedger:
    """O livro-caixa. Um por Lab; ciclos e tetos configuráveis."""

    teto_por_tarefa: Decimal = field(default_factory=lambda: Decimal("1"))
    teto_por_ciclo: Optional[Decimal] = None
    teto_total: Optional[Decimal] = None
    relogio: Callable[[], Any] = field(default=lambda: __import__("time").time())
    notificar: Optional[Callable[[str, Dict[str, Any]], None]] = None

    lancamentos: List[Lancamento] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)
    journal: List[Dict[str, Any]] = field(default_factory=list)
    _seq: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        self.teto_por_tarefa = _dinheiro(self.teto_por_tarefa)
        if self.teto_por_ciclo is not None:
            self.teto_por_ciclo = _dinheiro(self.teto_por_ciclo)
        if self.teto_total is not None:
            self.teto_total = _dinheiro(self.teto_total)
        self._log("ledger_aberto", {})

    # -- utilidades internas -------------------------------------------------
    def _log(self, evento: str, dados: Dict[str, Any]) -> None:
        self.journal.append({"ts": self.relogio(), "evento": evento, **dados})

    def _avisa(self, codigo: str, dados: Dict[str, Any]) -> None:
        self.alertas.append(codigo)
        self._log("alerta", {"codigo": codigo, **dados})
        if self.notificar is not None:
            # só nomes e estados, nunca conteúdo de arquivo
            self.notificar(codigo, {k: v for k, v in dados.items()
                                    if k in ("ciclo", "assento", "tarefa",
                                             "usd", "teto")})

    @staticmethod
    def _texto(valor: Any, campo: str, minimo: int = 1, maximo: int = 120) -> str:
        if not isinstance(valor, str):
            raise LedgerError(f"{campo}_INVALIDO")
        v = valor.strip()
        if not (minimo <= len(v) <= maximo):
            raise LedgerError(f"{campo}_INVALIDO")
        return v

    # -- lançamentos ---------------------------------------------------------
    def registrar(self, ciclo: str, assento: str, tarefa: str,
                  usd: Any) -> Lancamento:
        """Registra um gasto. Nunca crasha por teto: flagra + alerta."""
        ciclo = self._texto(ciclo, "CICLO", maximo=40)
        assento = self._texto(assento, "ASSENTO", maximo=40)
        if assento not in SEATS:
            raise LedgerError("ASSENTO_DESCONHECIDO")
        tarefa = self._texto(tarefa, "TAREFA", maximo=120)
        valor = _dinheiro(usd)

        self._seq += 1
        gasto_tarefa = self.gasto_tarefa(tarefa) + valor
        over = gasto_tarefa > self.teto_por_tarefa
        lanc = Lancamento(seq=self._seq, ciclo=ciclo, assento=assento,
                          tarefa=tarefa, usd=valor,
                          teto_tarefa=self.teto_por_tarefa,
                          over_cap=over, ts=self.relogio())
        self.lancamentos.append(lanc)
        self._log("gasto_registrado",
                  {"ciclo": ciclo, "assento": assento, "tarefa": tarefa,
                   "usd": str(valor), "over_cap": over})

        if over:
            self._avisa("TETO_TAREFA_ESTOURADO",
                        {"ciclo": ciclo, "assento": assento, "tarefa": tarefa,
                         "usd": str(gasto_tarefa),
                         "teto": str(self.teto_por_tarefa)})
        if self.teto_por_ciclo is not None:
            gasto_ciclo = self.gasto_ciclo(ciclo)
            if gasto_ciclo > self.teto_por_ciclo:
                self._avisa("TETO_CICLO_ESTOURADO",
                            {"ciclo": ciclo, "usd": str(gasto_ciclo),
                             "teto": str(self.teto_por_ciclo)})
        if self.teto_total is not None:
            total = self.gasto_total()
            if total > self.teto_total:
                self._avisa("TETO_TOTAL_ESTOURADO",
                            {"usd": str(total), "teto": str(self.teto_total)})
        return lanc

    # -- consultas -----------------------------------------------------------
    def gasto_tarefa(self, tarefa: str) -> Decimal:
        return sum((l.usd for l in self.lancamentos if l.tarefa == tarefa),
                   Decimal("0")).quantize(CASAS)

    def gasto_ciclo(self, ciclo: str) -> Decimal:
        return sum((l.usd for l in self.lancamentos if l.ciclo == ciclo),
                   Decimal("0")).quantize(CASAS)

    def gasto_assento(self, assento: str, ciclo: Optional[str] = None) -> Decimal:
        return sum((l.usd for l in self.lancamentos
                    if l.assento == assento and (ciclo is None or l.ciclo == ciclo)),
                   Decimal("0")).quantize(CASAS)

    def gasto_total(self) -> Decimal:
        return sum((l.usd for l in self.lancamentos),
                   Decimal("0")).quantize(CASAS)

    def ciclo_no_teto(self, ciclo: str) -> bool:
        """True se o ciclo ainda cabe no teto (sem teto = sempre cabe)."""
        if self.teto_por_ciclo is None:
            return True
        return self.gasto_ciclo(ciclo) <= self.teto_por_ciclo

    def resumo_para_boletim(self, ciclo: str) -> List[str]:
        """Linhas prontas p/ o boletim da CEO: nomes e números, sem detalhe."""
        gasto = self.gasto_ciclo(ciclo)
        linhas = [f"gasto do ciclo {ciclo}: US$ {gasto}"]
        if self.teto_por_ciclo is not None:
            linhas.append(f"teto do ciclo: US$ {self.teto_por_ciclo}")
        estourados = sorted({l.tarefa for l in self.lancamentos
                             if l.ciclo == ciclo and l.over_cap})
        for t in estourados[:5]:
            linhas.append(f"tarefa acima do teto: {t}")
        if len(estourados) > 5:
            linhas.append(f"+{len(estourados) - 5} tarefas acima do teto")
        if self.alertas:
            linhas.append(f"alertas de custo: {len(self.alertas)}")
        return linhas
