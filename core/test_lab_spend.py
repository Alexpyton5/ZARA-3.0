"""Testes do lab_spend — o caixa ligando o ledger ao turno e ao loop.

Roda contra o lab_cost_ledger.py REAL do app (puxado do PC) e o FIXED_SEATS
de verdade. Lógica pura, stdlib, zero custo/rede/quota.
"""

from decimal import Decimal

import pytest

try:
    from core.lab_spend import (registrar_gasto, autorizar_gasto, fechar_ciclo,
                                linhas_para_boletim, OK, NEGADO)
    from core.lab_cost_ledger import CostLedger, LedgerError, SEATS
except ImportError:
    from lab_spend import (registrar_gasto, autorizar_gasto, fechar_ciclo,
                           linhas_para_boletim, OK, NEGADO)
    from lab_cost_ledger import CostLedger, LedgerError, SEATS

CEO = "CEO" if "CEO" in SEATS else sorted(SEATS)[0]
OUTRO = "ENGINEER" if "ENGINEER" in SEATS and "ENGINEER" != CEO else sorted(SEATS)[-1]

CICLO = "LOOP-TESTE"


def _ledger(**kw):
    return CostLedger(teto_por_tarefa=Decimal("1"), **kw)


# -- registrar_gasto ---------------------------------------------------------
def test_registra_gasto_valido():
    led = _ledger()
    lanc, over = registrar_gasto(led, CICLO, CEO, "tarefa-1", "0.25")
    assert lanc.usd == Decimal("0.250000")
    assert lanc.assento == CEO and lanc.tarefa == "tarefa-1"
    assert over is False
    assert led.gasto_tarefa("tarefa-1") == Decimal("0.250000")


def test_registra_gasto_zero_prova_sem_custo():
    led = _ledger()
    lanc, over = registrar_gasto(led, CICLO, CEO, "tarefa-1", 0)
    assert lanc.usd == Decimal("0.000000") and over is False
    assert len(led.lancamentos) == 1  # zero também é evento registrado


def test_registra_assento_desconhecido_falha_fechada():
    led = _ledger()
    with pytest.raises(LedgerError):
        registrar_gasto(led, CICLO, "CHEFÃO", "tarefa-1", "0.10")
    assert len(led.lancamentos) == 0  # nada registrado pela metade


def test_registra_valor_negativo_falha_fechada():
    led = _ledger()
    with pytest.raises(LedgerError):
        registrar_gasto(led, CICLO, CEO, "tarefa-1", "-0.01")
    assert len(led.lancamentos) == 0


def test_registra_tarefa_vazia_falha_fechada():
    led = _ledger()
    with pytest.raises(LedgerError):
        registrar_gasto(led, CICLO, CEO, "   ", "0.10")
    assert len(led.lancamentos) == 0


def test_acima_do_teto_registra_e_flagra():
    led = _ledger()
    _, over1 = registrar_gasto(led, CICLO, CEO, "tarefa-cara", "0.60")
    _, over2 = registrar_gasto(led, CICLO, OUTRO, "tarefa-cara", "0.60")
    assert over1 is False and over2 is True  # registrou do mesmo jeito
    assert "TETO_TAREFA_ESTOURADO" in led.alertas
    assert led.gasto_tarefa("tarefa-cara") == Decimal("1.200000")


def test_decimal_exato_sem_float():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t1", "0.1")
    registrar_gasto(led, CICLO, CEO, "t1", "0.2")
    assert led.gasto_tarefa("t1") == Decimal("0.300000")  # float daria 0.30000000000000004


# -- autorizar_gasto ---------------------------------------------------------
def test_autoriza_quando_cabe():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t1", "0.40")
    r = autorizar_gasto(led, CICLO, "t1", "0.50")
    assert r["decisao"] == OK and r["motivo"] is None
    assert r["restante"] == "0.600000"


def test_autoriza_pedido_exato_no_limite():
    led = _ledger()
    r = autorizar_gasto(led, CICLO, "t1", "1.00")
    assert r["decisao"] == OK  # pedido == teto passa


def test_nega_quando_estoura_tarefa():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t1", "0.80")
    r = autorizar_gasto(led, CICLO, "t1", "0.30")
    assert r["decisao"] == NEGADO and r["motivo"] == "TETO_TAREFA"
    assert r["restante"] == "0.200000"


def test_nega_pedido_invalido_sem_crash():
    led = _ledger()
    r = autorizar_gasto(led, CICLO, "t1", "muito")
    assert r["decisao"] == NEGADO and r["motivo"] == "PEDIDO_INVALIDO"


def test_nega_identificacao_invalida_sem_crash():
    led = _ledger()
    r = autorizar_gasto(led, "", "", "0.10")
    assert r["decisao"] == NEGADO and r["motivo"] == "IDENTIFICACAO_INVALIDA"


def test_nega_quando_ciclo_estoura():
    led = CostLedger(teto_por_tarefa=Decimal("10"),
                     teto_por_ciclo=Decimal("0.50"))
    registrar_gasto(led, CICLO, CEO, "t1", "0.40")
    r = autorizar_gasto(led, CICLO, "t2", "0.20")  # tarefa cabe, ciclo não
    assert r["decisao"] == NEGADO and r["motivo"] == "TETO_CICLO"


# -- fechar_ciclo ------------------------------------------------------------
def test_fechar_ciclo_resume_a_conta():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t1", "0.30")
    registrar_gasto(led, "OUTRO-CICLO", OUTRO, "t2", "9.99")
    f = fechar_ciclo(led, CICLO)
    assert f["ciclo"] == CICLO
    assert f["gasto_usd"] == "0.300000"  # só este ciclo
    assert f["no_teto"] is True
    assert f["acima_do_teto"] == [] and f["alertas"] == []


def test_fechar_ciclo_vazio():
    led = _ledger()
    f = fechar_ciclo(led, "CICLO-FANTASMA")
    assert f["gasto_usd"] == "0.000000" and f["no_teto"] is True


def test_fechar_ciclo_lista_acima_do_teto():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t-cara", "1.50")
    f = fechar_ciclo(led, CICLO)
    assert f["acima_do_teto"] == ["t-cara"]
    assert "TETO_TAREFA_ESTOURADO" in f["alertas"]


# -- linhas_para_boletim -----------------------------------------------------
def test_linhas_no_teto_do_silencio():
    led = _ledger()
    linhas = linhas_para_boletim(led, CICLO)
    assert 1 <= len(linhas) <= 4
    assert any("gasto do ciclo" in l for l in linhas)


def test_linhas_truncam_com_resumo():
    led = CostLedger(teto_por_tarefa=Decimal("0.01"))
    for i in range(8):  # 8 tarefas acima do teto → muitas linhas
        registrar_gasto(led, CICLO, CEO, f"t-{i}", "0.10")
    linhas = linhas_para_boletim(led, CICLO, max_linhas=4)
    assert len(linhas) == 4  # teto respeitado de verdade
    assert linhas[-1].startswith("+") and "journal" in linhas[-1]


def test_linhas_sem_detalhe_de_journal():
    led = _ledger()
    registrar_gasto(led, CICLO, CEO, "t1", "0.10")
    texto = "\n".join(linhas_para_boletim(led, CICLO))
    assert "gasto_registrado" not in texto  # evento interno não vaza


# -- por desenho, não por promessa -------------------------------------------
def test_sem_campo_de_conteudo_na_assinatura():
    import inspect
    try:
        from core.lab_spend import registrar_gasto as rg
        from core.lab_cost_ledger import Lancamento as Lc
    except ImportError:
        from lab_spend import registrar_gasto as rg
        from lab_cost_ledger import Lancamento as Lc
    params = set(inspect.signature(rg).parameters)
    assert "conteudo" not in params and "dados" not in params
    campos = set(Lc.__dataclass_fields__)
    assert "conteudo" not in campos  # o lançamento nem TEM onde guardar conteúdo
