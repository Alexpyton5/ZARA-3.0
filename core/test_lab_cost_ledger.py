"""Testes do livro-caixa de custo do Lab.

16 checagens, lógica pura, zero custo/rede/quota: o livro-caixa registra
gasto real com teto e prova, ancorado nos 11 assentos fixos de verdade.
Roda nos 2 layouts (flat e pacote core.*), igual às outras peças do alicerce.
"""

from __future__ import annotations

from decimal import Decimal

try:
    from core.lab_cost_ledger import (CostLedger, LedgerError, _dinheiro,
                                      SEATS)
except ImportError:  # rodando flat
    from lab_cost_ledger import (CostLedger, LedgerError, _dinheiro, SEATS)


def _nova(**kw):
    kw.setdefault("relogio", lambda: 1)
    return CostLedger(**kw)


def test_11_assentos_ancorados():
    assert len(SEATS) == 11
    for s in ("CEO", "ENGINEER", "TESTER", "REVIEWER", "PACKAGER"):
        assert s in SEATS


def test_dinheiro_recusa_lixo():
    for ruim in (-1, "-0.5", float("nan"), float("inf"), "abc", None, ""):
        try:
            _dinheiro(ruim)
        except LedgerError:
            continue
        raise AssertionError(f"aceitou {ruim!r}")
    assert _dinheiro(0) == Decimal("0")
    assert _dinheiro("0.0000004") == Decimal("0")  # 6 casas, arredonda
    assert _dinheiro(0.0000005) == Decimal("0.000001")


def test_registro_basico_e_somas():
    l = _nova()
    l.registrar("C1", "ENGINEER", "corrigir-teste", "0.02")
    l.registrar("C1", "ENGINEER", "corrigir-teste", 0.03)
    l.registrar("C1", "TESTER", "rodar-suite", 0)
    assert l.gasto_tarefa("corrigir-teste") == Decimal("0.05")
    assert l.gasto_ciclo("C1") == Decimal("0.05")
    assert l.gasto_assento("ENGINEER") == Decimal("0.05")
    assert l.gasto_assento("ENGINEER", "C1") == Decimal("0.05")
    assert l.gasto_assento("TESTER", "C1") == Decimal("0")
    assert l.gasto_total() == Decimal("0.05")
    assert l.alertas == []  # dentro dos tetos, sem alarme


def test_assento_desconhecido_recusado():
    l = _nova()
    for assento in ("MEMBER", "CTO", "", "engineer"):
        try:
            l.registrar("C1", assento, "t1", 0.01)
        except LedgerError as e:
            assert "ASSENTO" in str(e)
            continue
        raise AssertionError(f"aceitou assento {assento!r}")


def test_campos_vazios_recusados():
    l = _nova()
    for ciclo, assento, tarefa in (("", "ENGINEER", "t"), ("C1", "", "t"),
                                   ("C1", "ENGINEER", "")):
        try:
            l.registrar(ciclo, assento, tarefa, 0.01)
        except LedgerError:
            continue
        raise AssertionError("aceitou campo vazio")


def test_teto_tarefa_flagra_e_alerta():
    l = _nova(teto_por_tarefa="0.10")
    a = l.registrar("C1", "ENGINEER", "tarefa-cara", "0.06")
    assert not a.over_cap and l.alertas == []
    b = l.registrar("C1", "ENGINEER", "tarefa-cara", "0.05")  # soma 0.11
    assert b.over_cap
    assert "TETO_TAREFA_ESTOURADO" in l.alertas
    # o gasto continua registrado (nunca esconde)
    assert l.gasto_tarefa("tarefa-cara") == Decimal("0.11")


def test_teto_ciclo_e_total():
    l = _nova(teto_por_ciclo="0.05", teto_total="0.08")
    l.registrar("C1", "ENGINEER", "t1", "0.04")
    assert l.ciclo_no_teto("C1")
    l.registrar("C1", "REVIEWER", "t2", "0.03")  # ciclo 0.07
    assert not l.ciclo_no_teto("C1")
    assert "TETO_CICLO_ESTOURADO" in l.alertas
    l.registrar("C2", "TESTER", "t3", "0.02")  # total 0.09
    assert "TETO_TOTAL_ESTOURADO" in l.alertas


def test_gasto_zero_e_prova_de_gratis():
    l = _nova()
    l.registrar("C1", "CEO", "planejar", 0)
    assert l.gasto_total() == Decimal("0")
    assert l.alertas == []
    linhas = l.resumo_para_boletim("C1")
    assert any("US$ 0" in x for x in linhas)


def test_resumo_para_boletim():
    avisos = []
    l = _nova(teto_por_tarefa="0.01", teto_por_ciclo="1",
              notificar=lambda c, d: avisos.append((c, d)))
    l.registrar("C9", "ENGINEER", "tarefa-x", "0.05")
    linhas = l.resumo_para_boletim("C9")
    assert any("C9" in x and "US$" in x for x in linhas)
    assert any("tarefa-x" in x for x in linhas)  # nome, não detalhe
    assert any("alertas" in x for x in linhas)
    # notify recebe só nomes e estados
    assert avisos and avisos[0][0] == "TETO_TAREFA_ESTOURADO"
    assert set(avisos[0][1]) <= {"ciclo", "assento", "tarefa", "usd", "teto"}


def test_journal_auditavel_com_relogio():
    t = iter([10, 11, 12, 13])
    l = CostLedger(relogio=lambda: next(t))
    l.registrar("C1", "CEO", "t1", 0)
    evs = [j["evento"] for j in l.journal]
    assert evs[0] == "ledger_aberto"
    assert "gasto_registrado" in evs
    ts = [j["ts"] for j in l.journal]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)  # crescente e único


def test_lancamento_carrega_sequencia_e_ts():
    t = iter([99, 100, 101, 102, 103])
    l = CostLedger(relogio=lambda: next(t))
    a = l.registrar("C1", "CEO", "t1", "0.01")
    b = l.registrar("C1", "CEO", "t2", "0.02")
    assert (a.seq, b.seq) == (1, 2)
    assert a.ts == 100 and b.ts == 102  # 99=abertura, 100/102=ts, 101/103=logs
    assert a.teto_tarefa == Decimal("1")  # padrão


def test_multiplos_ciclos_isolados():
    l = _nova()
    l.registrar("C1", "ENGINEER", "t1", "0.10")
    l.registrar("C2", "ENGINEER", "t1", "0.20")
    assert l.gasto_ciclo("C1") == Decimal("0.10")
    assert l.gasto_ciclo("C2") == Decimal("0.20")
    # teto por tarefa soma entre ciclos (a tarefa é a mesma)
    l2 = _nova(teto_por_tarefa="0.25")
    l2.registrar("C1", "ENGINEER", "t1", "0.10")
    b = l2.registrar("C2", "ENGINEER", "t1", "0.20")
    assert b.over_cap


def test_sem_teto_ciclo_sempre_cabe():
    l = _nova()
    l.registrar("C1", "ENGINEER", "t1", "999.99")
    assert l.ciclo_no_teto("C1")
    assert "TETO_CICLO_ESTOURADO" not in l.alertas


def test_erro_nao_quebra_o_ledger():
    l = _nova()
    try:
        l.registrar("C1", "CTO", "t1", 1)
    except LedgerError:
        pass
    l.registrar("C1", "CEO", "t1", "0.01")
    assert l.gasto_total() == Decimal("0.01")
    assert len(l.lancamentos) == 1


def test_decimal_exato_sem_float():
    l = _nova()
    l.registrar("C1", "ENGINEER", "t1", 0.1)
    l.registrar("C1", "ENGINEER", "t1", 0.2)
    assert l.gasto_tarefa("t1") == Decimal("0.3")  # 0.1+0.2 sem erro de float


def test_tarefa_com_nome_grande_recusada():
    l = _nova()
    try:
        l.registrar("C1", "CEO", "x" * 121, 0)
    except LedgerError as e:
        assert "TAREFA" in str(e)
        return
    raise AssertionError("aceitou tarefa gigante")
