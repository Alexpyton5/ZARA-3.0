"""Caixa da operação — o adaptador que liga o livro-caixa ao turno e ao loop.

O loop (lab_loop) CONCEDE orçamento por ciclo e o turno (lab_turn) carrega
budget_usd por tarefa, mas até aqui ninguém registrava o gasto REAL nem
consultava o teto ANTES de gastar. Este módulo fecha esse buraco, em lógica
pura, sem chamar modelo nenhum (custo/rede/quota = zero):

- `registrar_gasto(...)`: anota um gasto de verdade no ledger (quem, qual
  tarefa, qual ciclo, quanto). Falha fechada: dado inválido → LedgerError,
  nada é registrado pela metade.
- `autorizar_gasto(...)`: o turno consulta ANTES de executar um passo pago —
  "posso gastar X nesta tarefa neste ciclo?". Acima do teto → NEGADO com o
  motivo, nunca crasha o turno.
- `fechar_ciclo(...)`: o loop chama no fim de cada ciclo — devolve gasto,
  se coube no teto, alertas e tarefas acima do teto.
- `linhas_para_boletim(...)`: custo em linhas prontas p/ o boletim da CEO,
  no teto do modo silencioso (máx 4 linhas por padrão) — o boletim mostra
  "gasto do ciclo: US$ 0.000000", nunca detalhe de journal.

Regras duras:
- dinheiro passa pelo `_dinheiro` do ledger (Decimal, 6 casas) — float nunca
  guarda dinheiro;
- o adaptador NUNCA recebe conteúdo de arquivo: só nomes e estados — por
  desenho, não por promessa (a assinatura não tem campo de conteúdo);
- gastar acima do teto REGISTRA do mesmo jeito (nunca esconde gasto), mas
  `autorizar_gasto` NEGA o próximo pedido;
- sem teto de ciclo configurado, o ciclo sempre cabe (comportamento antigo);
- journal auditável é o do ledger; este módulo não cria journal próprio.

Peça do alicerce LAB VIVO. Lógica pura, stdlib, zero custo/rede/quota.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.lab_cost_ledger import CostLedger, Lancamento, LedgerError, _dinheiro
except ImportError:  # rodando flat (testes locais)
    from lab_cost_ledger import CostLedger, Lancamento, LedgerError, _dinheiro

NEGADO = "NEGADO"
OK = "OK"


# -- registro --------------------------------------------------------------
def registrar_gasto(ledger: CostLedger, ciclo: str, assento: str, tarefa: str,
                    usd: Any) -> Tuple[Lancamento, bool]:
    """Registra um gasto real no ledger. Retorna (lançamento, over_cap).

    Falha fechada: assento desconhecido, tarefa/ciclo vazios ou valor
    inválido → LedgerError e NADA é registrado.
    """
    lanc = ledger.registrar(ciclo=ciclo, assento=assento, tarefa=tarefa,
                            usd=usd)
    return lanc, lanc.over_cap


# -- autorização prévia (o turno consulta antes do passo pago) -------------
def autorizar_gasto(ledger: CostLedger, ciclo: str, tarefa: str,
                    pedido_usd: Any,
                    teto_tarefa_usd: Optional[Any] = None
                    ) -> Dict[str, Any]:
    """Pode gastar `pedido_usd` nesta tarefa, neste ciclo?

    Devolve {"decisao": "OK"/"NEGADO", "motivo": None/código,
             "restante": "0.000000"}. Nunca levanta exceção por teto:
    acima do teto é NEGADO, não crash.
    """
    try:
        pedido = _dinheiro(pedido_usd)
    except LedgerError:
        return {"decisao": NEGADO, "motivo": "PEDIDO_INVALIDO",
                "restante": "0.000000"}
    try:
        tarefa_ok = ledger._texto(tarefa, "TAREFA", maximo=120)
        ciclo_ok = ledger._texto(ciclo, "CICLO", maximo=40)
    except LedgerError:
        return {"decisao": NEGADO, "motivo": "IDENTIFICACAO_INVALIDA",
                "restante": "0.000000"}

    teto = (_dinheiro(teto_tarefa_usd) if teto_tarefa_usd is not None
            else ledger.teto_por_tarefa)
    restante = teto - ledger.gasto_tarefa(tarefa_ok)
    if restante < 0:
        restante = Decimal("0")
    if pedido > restante:
        return {"decisao": NEGADO, "motivo": "TETO_TAREFA",
                "restante": str(restante.quantize(
                    Decimal("0.000001")))}

    if ledger.teto_por_ciclo is not None:
        restante_ciclo = ledger.teto_por_ciclo - ledger.gasto_ciclo(ciclo_ok)
        if restante_ciclo < 0:
            restante_ciclo = Decimal("0")
        if pedido > restante_ciclo:
            return {"decisao": NEGADO, "motivo": "TETO_CICLO",
                    "restante": str(restante_ciclo.quantize(
                        Decimal("0.000001")))}
        restante = min(restante, restante_ciclo)

    return {"decisao": OK, "motivo": None,
            "restante": str(restante.quantize(Decimal("0.000001")))}


# -- fechamento do ciclo (o loop chama no fim de cada ciclo) ---------------
def fechar_ciclo(ledger: CostLedger, ciclo: str) -> Dict[str, Any]:
    """Fecha a conta do ciclo: gasto, coube no teto, alertas, acima do teto.

    Os alertas vêm do journal: só os DESTE ciclo (ou os globais, como
    TETO_TOTAL, que não carregam ciclo). Alerta de outro ciclo não entra
    na conta deste.
    """
    ciclo_ok = ledger._texto(ciclo, "CICLO", maximo=40)
    acima = sorted({l.tarefa for l in ledger.lancamentos
                    if l.ciclo == ciclo_ok and l.over_cap})
    alertas = [e["codigo"] for e in ledger.journal
               if e.get("evento") == "alerta"
               and ("ciclo" not in e or e.get("ciclo") == ciclo_ok)]
    return {
        "ciclo": ciclo_ok,
        "gasto_usd": str(ledger.gasto_ciclo(ciclo_ok)),
        "no_teto": ledger.ciclo_no_teto(ciclo_ok),
        "alertas": alertas,
        "acima_do_teto": acima,
    }


# -- linhas p/ o boletim da CEO --------------------------------------------
def linhas_para_boletim(ledger: CostLedger, ciclo: str,
                        max_linhas: int = 4) -> List[str]:
    """Custo em linhas prontas p/ o boletim, no teto do modo silencioso.

    Sempre ≤ max_linhas (padrão 4): nomes e números, sem detalhe de journal.
    """
    linhas = ledger.resumo_para_boletim(ciclo)
    if len(linhas) <= max_linhas:
        return linhas
    cortadas = max_linhas - 1
    resto = len(linhas) - cortadas
    return (linhas[:cortadas]
            + [f"+{resto} linhas de custo no journal"])
