"""Testes do snapshot de estado do backlog (export_state/import_state).

Lógica pura, custo zero. Prova que o plug do Lab Vivo pode salvar e
recarregar o backlog em disco SEM fuçar nos privados _items/_seq.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab_backlog import (
    BacklogError,
    BacklogState,
    LabBacklog,
)


def _backlog():
    tick = {"n": 0}

    def clock():
        tick["n"] += 1
        return f"T{tick['n']:03d}"

    return LabBacklog(clock=clock)


def _cheio():
    """Backlog com 3 itens em estados diferentes, p/ exercitar o snapshot."""
    b = _backlog()
    a = b.propose(title="Corrigir teste quebrado da voz",
                  description="O teste X falha intermitente",
                  proposed_by="TESTER", impact=5, urgency=4, cost=2)
    c = b.propose(title="Fatiar o módulo gigante do backend",
                  description="Dividir em módulos menores",
                  proposed_by="ARCHITECT", impact=4, urgency=3, cost=4)
    d = b.propose(title="Documentar o protocolo da caixinha",
                  description="Escrever o guia de uso",
                  proposed_by="SCRIBE", impact=2, urgency=2, cost=1)
    b.approve(a.item_id, by="CEO")
    b.approve(c.item_id, by="CEO")
    b.claim(a.item_id, "ENGINEER-1")
    b.complete(a.item_id, "ENGINEER-1", note="ok")
    b.reject(d.item_id, by="CRITIC", reason="prioridade baixa")
    return b


def test_export_e_json():
    b = _cheio()
    snap = b.export_state()
    # serializa de verdade (é assim que vai pro disco)
    texto = json.dumps(snap, ensure_ascii=False)
    de_volta = json.loads(texto)
    assert de_volta["version"] == 1
    assert de_volta["seq"] == 3
    assert len(de_volta["items"]) == 3


def test_roundtrip_preserva_tudo():
    b = _cheio()
    snap = json.loads(json.dumps(b.export_state()))
    b2 = _backlog()
    n = b2.import_state(snap)
    assert n == 3
    for item_id in ("BLG-0001", "BLG-0002", "BLG-0003"):
        velho, novo = b.get(item_id), b2.get(item_id)
        assert novo.title == velho.title
        assert novo.state is velho.state
        assert novo.score == velho.score
        assert novo.claimed_by == velho.claimed_by
        assert novo.journal == velho.journal
        assert novo.seq == velho.seq
    # o contador continua de onde parou (nada colide)
    e = b2.propose(title="Nova proposta depois do reload",
                   description="x", proposed_by="CEO",
                   impact=3, urgency=3, cost=3)
    assert e.item_id == "BLG-0004"


def test_export_devolve_copia_nao_referencia():
    b = _cheio()
    snap = b.export_state()
    snap["items"][0]["title"] = "ADULTERADO"
    snap["items"].append({"lixo": True})
    snap["seq"] = 999
    assert b.get("BLG-0001").title != "ADULTERADO"
    assert b.export_state()["seq"] == 3  # intacto


def test_import_vazio():
    b2 = _backlog()
    n = b2.import_state({"version": 1, "seq": 0, "items": []})
    assert n == 0
    assert b2.ranked() == []


def test_import_substitui_conteudo():
    b2 = _backlog()
    b2.propose(title="Item que vai sumir", description="x",
               proposed_by="CEO", impact=1, urgency=1, cost=1)
    snap = _cheio().export_state()
    b2.import_state(snap)
    assert len(b2.ranked()) == 3
    # o item antigo sumiu: BLG-0001 agora é o do snapshot, não o proposto antes
    novo = b2.get("BLG-0001")
    assert novo.title == "Corrigir teste quebrado da voz"
    assert novo.state is BacklogState.DONE


def _espera_erro(snap_mutado_ou_invalido, b2):
    try:
        b2.import_state(snap_mutado_ou_invalido)
    except BacklogError:
        return
    raise AssertionError("import_state deveria ter recusado")


def test_import_recusa_lixo():
    b = _cheio()
    base = b.export_state()
    b2 = _backlog()
    _espera_erro("nao-um-dict", b2)
    _espera_erro([], b2)
    _espera_erro({"version": 1, "seq": 3}, b2)                    # sem items
    _espera_erro({"version": 1, "seq": 3, "items": [],
                  "extra": 1}, b2)                               # chave a mais
    _espera_erro({"version": 2, "seq": 3, "items": []}, b2)       # versão
    _espera_erro({"version": 1, "seq": -1, "items": []}, b2)      # seq negativo
    _espera_erro({"version": 1, "seq": "3", "items": []}, b2)     # seq texto
    _espera_erro({"version": 1, "seq": 3, "items": {}}, b2)       # items não-lista


def test_import_recusa_item_ruim():
    b = _cheio()
    b2 = _backlog()
    ruim = copy.deepcopy(b.export_state())
    ruim["items"][0]["state"] = "SUPER_APROVADO"
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["items"][1]["impact"] = 9
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["items"][0]["item_id"] = "BLG-0099"  # não confere com o seq
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["items"].append(copy.deepcopy(ruim["items"][0]))  # duplicado
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["items"][2]["journal"] = "nao-uma-lista"
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    del ruim["items"][0]["title"]  # campo faltando
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["items"][0]["titulo"] = "campo estranho"  # campo a mais
    _espera_erro(ruim, b2)

    ruim = copy.deepcopy(b.export_state())
    ruim["seq"] = 1  # contador menor que o maior item
    _espera_erro(ruim, b2)


def test_import_falhado_nao_mexe_em_nada():
    b2 = _backlog()
    vivo = b2.propose(title="Item vivo", description="x",
                      proposed_by="CEO", impact=2, urgency=2, cost=2)
    antes = b2.export_state()
    try:
        b2.import_state({"version": 1, "seq": 0, "items": [{"lixo": 1}]})
    except BacklogError:
        pass
    # intacto: mesmo conteúdo, mesmo contador
    assert b2.export_state() == antes
    assert b2.get(vivo.item_id).title == "Item vivo"


def test_import_nao_reloga():
    b = _cheio()
    snap = b.export_state()
    b2 = _backlog()
    b2.import_state(snap)
    # o journal veio do snapshot, sem "importado em ..." inventado
    assert b2.get("BLG-0001").journal == b.get("BLG-0001").journal


if __name__ == "__main__":
    nomes = [n for n in sorted(dir())
             if n.startswith("test_") and callable(globals()[n])]
    falhas = 0
    for n in nomes:
        try:
            globals()[n]()
            print(f"ok - {n}")
        except Exception as e:  # noqa: BLE001 - harness simples de teste
            falhas += 1
            print(f"FALHOU - {n}: {e}")
    print(f"{len(nomes) - falhas}/{len(nomes)} verdes")
    sys.exit(1 if falhas else 0)
