"""Testes do protocolo de relatório dos agentes (MODO SILENCIOSO).

Roda com: python test_lab_report.py  (stdlib apenas)
Verde = o portão do silêncio funciona: relatório fora do formato não fala.
"""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from lab_report import (  # noqa: E402
    BLOQUEIO,
    MAX_LINHAS,
    PROGRESSO,
    STATUS,
    Relatorio,
    analisar,
    cortar_em_linhas,
)


def test_progresso_valido_pode_falar():
    r = Relatorio(
        tipo=PROGRESSO,
        feito=["suíte focada 15/15 verde", "push 3c12d01 confirmado"],
        estado=["fase de voz fechada", "full segue nos 41 do baseline"],
        erro=["nenhum"],
        sugestao=["incluir o pré-voo no gate final"],
    )
    assert r.pode_falar(), r.validar()


def test_progresso_sem_feito_nao_pode_falar():
    r = Relatorio(tipo=PROGRESSO, estado=["trabalhei bastante"])
    assert not r.pode_falar()
    assert any("FEITO" in v for v in r.validar())


def test_bloqueio_exige_decisao_pedida():
    r = Relatorio(tipo=BLOQUEIO, erro=["typecheck travado no tsx"], sugestao=["aguardar"])
    assert not r.pode_falar()
    assert any("decisão" in v for v in r.validar())


def test_bloqueio_com_decisao_pode_falar():
    r = Relatorio(
        tipo=BLOQUEIO,
        erro=["typecheck travado em SupercerebroKey.tsx"],
        decisao_pedida="zoe corrige o componente ou eu contorno?",
    )
    assert r.pode_falar(), r.validar()


def test_mais_de_10_linhas_nao_pode_falar():
    r = Relatorio(
        tipo=PROGRESSO,
        feito=["item %d" % i for i in range(MAX_LINHAS + 1)],
    )
    assert not r.pode_falar()
    assert any("10" in v for v in r.validar())


def test_exatamente_10_linhas_pode_falar():
    r = Relatorio(
        tipo=PROGRESSO,
        feito=["item %d" % i for i in range(MAX_LINHAS)],
    )
    assert r.pode_falar(), r.validar()


def test_tipo_invalido_nao_pode_falar():
    r = Relatorio(tipo="FOFOCA", feito=["x"])
    assert not r.pode_falar()
    assert any("tipo inválido" in v for v in r.validar())


def test_linha_com_quebra_interna_nao_pode_falar():
    r = Relatorio(tipo=PROGRESSO, feito=["linha um\nlinha dois"])
    assert not r.pode_falar()
    assert any("quebra interna" in v for v in r.validar())


def test_formatar_monta_as_4_secoes():
    r = Relatorio(
        tipo=BLOQUEIO,
        feito=["g1 passou"],
        estado=["g2 em curso"],
        erro=["travei no gate"],
        sugestao=["pedir decisão"],
        decisao_pedida="continuo ou paro?",
    )
    texto = r.formatar()
    for secao in ("FEITO:", "ESTADO:", "ERRO:", "SUGESTÃO:"):
        assert secao in texto, secao
    assert "DECISÃO PEDIDA: continuo ou paro?" in texto
    assert "RELATÓRIO (BLOQUEIO)" in texto


def test_formatar_invalido_levanta_erro():
    r = Relatorio(tipo=PROGRESSO)
    try:
        r.formatar()
    except ValueError:
        return
    raise AssertionError("formatar() de relatório inválido deveria levantar ValueError")


def test_formatar_preenche_nada_quando_secao_vazia():
    r = Relatorio(tipo=PROGRESSO, feito=["só isso"])
    texto = r.formatar()
    assert texto.count("(nada)") == 3


def test_analisar_recupera_relatorio_formatado():
    original = Relatorio(
        tipo=BLOQUEIO,
        feito=["g1 verde"],
        estado=["g2 andando"],
        erro=["portão travou"],
        sugestao=["desviar"],
        decisao_pedida="posso seguir?",
    )
    texto = original.formatar()
    lido = analisar(texto)
    assert lido.tipo == BLOQUEIO
    assert lido.feito == ["g1 verde"]
    assert lido.estado == ["g2 andando"]
    assert lido.erro == ["portão travou"]
    assert lido.sugestao == ["desviar"]
    assert lido.decisao_pedida == "posso seguir?"
    assert lido.pode_falar()


def test_analisar_ignora_nada():
    lido = analisar("RELATÓRIO (PROGRESSO)\nFEITO:\n- fiz\nERRO:\n- (nada)\n")
    assert lido.erro == []


def test_cortar_em_linhas_respeita_o_teto():
    texto = "\n".join("linha %d" % i for i in range(30))
    cortadas = cortar_em_linhas(texto)
    assert len(cortadas) == MAX_LINHAS


def test_cortar_em_linhas_remove_vazias():
    cortadas = cortar_em_linhas("  a  \n\n  b\n")
    assert cortadas == ["a", "b"]


def test_status_e_tipo_valido():
    r = Relatorio(tipo=STATUS, estado=["ronda ok"])
    assert r.pode_falar()


def _todas():
    return sorted(
        (nome, fn)
        for nome, fn in list(globals().items())
        if nome.startswith("test_") and callable(fn)
    )


if __name__ == "__main__":
    falhas = 0
    total = 0
    for nome, fn in _todas():
        total += 1
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - corredor de testes simples
            falhas += 1
            print("FALHOU %s: %r" % (nome, e))
    print("%d/%d verdes" % (total - falhas, total))
    sys.exit(1 if falhas else 0)
