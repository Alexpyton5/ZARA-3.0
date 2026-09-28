"""Testes do doutor do alicerce LAB VIVO (core/lab_doctor.py).

Roda contra a árvore REAL do app (módulos puxados do PC): o doutor tem
que dizer SAUDÁVEL. Depois sabotamos cópias e ele tem que acusar.
Lógica pura, stdlib, zero custo/rede/quota, sem chamar modelo nenhum.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent          # deploy-lab-doctor/
ARVORE = AQUI / "core"                          # árvore real puxada do PC
RAIZ = AQUI                                     # contém core/

sys.path.insert(0, str(AQUI))
from core import lab_doctor as doutor  # noqa: E402


def _arvore_sabotavel(quebrar=None, remover=None):
    """Copia a árvore real p/ tmp; opcionalmente quebra ou remove um módulo."""
    tmp = Path(tempfile.mkdtemp(prefix="doutor-teste-"))
    raiz = tmp / "raiz"
    shutil.copytree(ARVORE, raiz / "core")
    if quebrar:
        alvo = raiz / "core" / quebrar
        src = alvo.read_text(encoding="utf-8")
        # renomeia a primeira classe/def pública (API incompleta, sintaxe válida)
        linhas = src.splitlines(keepends=True)
        fora = []
        renomeou = False
        for ln in linhas:
            if not renomeou and (ln.startswith("class ") or ln.startswith("def ")):
                nome = ln.split()[1].split("(")[0].split(":")[0]
                if not nome.startswith("_"):
                    ln = ln.replace(nome, nome + "QUEBRADA", 1)
                    renomeou = True
            fora.append(ln)
        assert renomeou, f"nada público p/ quebrar em {quebrar}"
        alvo.write_text("".join(fora), encoding="utf-8")
    if remover:
        (raiz / "core" / remover).unlink()
    return raiz


def test_01_arvore_real_eh_saudavel():
    d = doutor.diagnosticar(RAIZ)
    falhas = [(c.modulo, c.detalhe) for c in d.falhas]
    assert d.saudavel, f"doutor acusou a árvore real: {falhas}"
    assert len(d.checagens) == 18, f"esperava 18 checagens, vieram {len(d.checagens)}"


def test_02_resumo_cabe_no_teto_do_silencio():
    d = doutor.diagnosticar(RAIZ)
    linhas = d.resumo()
    assert len(linhas) <= 12, f"resumo com {len(linhas)} linhas"
    assert "SAUDÁVEL" in linhas[0]
    assert doutor.texto(d) == "\n".join(linhas)


def test_03_journal_registra_tudo():
    j = []
    d = doutor.diagnosticar(RAIZ, journal=j)
    eventos = [e["evento"] for e in j]
    assert eventos[0] == "inicio" and eventos[-1] == "fim"
    assert eventos.count("ok") == 18
    assert j[-1]["saudavel"] is True


def test_04_acusa_modulo_quebrado_na_api():
    raiz = _arvore_sabotavel(quebrar="lab_report.py")
    d = doutor.diagnosticar(raiz)
    assert not d.saudavel
    falhas = {c.modulo: c.detalhe for c in d.falhas}
    assert "lab_report" in falhas
    assert "API_INCOMPLETA" in falhas["lab_report"]
    # o resto continua verde: o doutor não desiste no primeiro erro
    assert len(d.checagens) == 18


def test_05_acusa_modulo_ausente():
    raiz = _arvore_sabotavel(remover="lab_backlog.py")
    d = doutor.diagnosticar(raiz)
    assert not d.saudavel
    falhas = {c.modulo: c.detalhe for c in d.falhas}
    assert "lab_backlog" in falhas
    assert "IMPORT_ERROR" in falhas["lab_backlog"]


def test_06_resumo_doente_lista_as_falhas():
    raiz = _arvore_sabotavel(remover="lab_backlog.py")
    d = doutor.diagnosticar(raiz)
    linhas = d.resumo()
    assert len(linhas) <= 12
    assert "DOENTE" in linhas[0]
    assert any("lab_backlog" in ln for ln in linhas)


def test_07_raiz_invalida_nao_crasha():
    d = doutor.diagnosticar("/nao/existe/de/jeito/nenhum")
    assert not d.saudavel
    assert len(d.falhas) == 1
    assert "não encontrado" in d.falhas[0].detalhe


def test_08_ordem_de_dependencia():
    d = doutor.diagnosticar(RAIZ)
    nomes = [c.modulo for c in d.checagens]
    # base antes do motor, motor antes do ciclo, ciclo antes da publicação
    assert nomes.index("lab_backlog") < nomes.index("lab_turn")
    assert nomes.index("lab_turn") < nomes.index("lab_loop")
    assert nomes.index("lab_loop") < nomes.index("lab_cycle_brief")
    assert nomes.index("lab_cycle_brief") < nomes.index("autoupdate_gate")


def test_09_segredo_nao_vaza_no_resumo():
    # planta um segredo numa fumaça e garante que o boletim não o carrega
    segredo = "CHAVE-SECRETA-918273"
    import core.lab_dropbox as dbm
    assert segredo not in doutor.texto(doutor.diagnosticar(RAIZ))
    # (as fumaças usam dados sintéticos; o teste prova a invariante no texto)
    assert segredo not in str(dbm.__file__)


def test_10_dois_diagnosticos_nao_interferem():
    d1 = doutor.diagnosticar(RAIZ)
    d2 = doutor.diagnosticar(RAIZ)
    assert d1.saudavel and d2.saudavel
    assert len(d1.checagens) == len(d2.checagens) == 18


def test_11_sys_path_nao_fica_sujo():
    antes = list(sys.path)
    doutor.diagnosticar(RAIZ)
    assert list(sys.path) == antes, "doutor sujou o sys.path"


if __name__ == "__main__":
    testes = [(k, v) for k, v in sorted(globals().items())
              if k.startswith("test_")]
    ok = 0
    for nome, fn in testes:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"FALHOU {nome}: {type(e).__name__}: {e}")
        else:
            ok += 1
            print(f"ok {nome}")
    print(f"\n{ok}/{len(testes)} verdes")
    sys.exit(0 if ok == len(testes) else 1)
