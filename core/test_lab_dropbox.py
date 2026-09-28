"""Testes do protocolo da caixinha (core/lab_dropbox.py).

Regras provadas aqui: ordem de chegada, claim idempotente, ninguém lê
recado dos outros, broadcast chega pra cada assento, RESPOSTA sem fio
é recusada, conteúdo gigante é recusado, destinatário inválido é recusado,
arquivo no disco nunca fica pela metade.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab_dropbox import (
    ASSENTOS,
    BROADCAST,
    CONTEUDO_MAX,
    Dropbox,
    DropboxError,
)


def nova_caixinha(tmp_path):
    relogio = lambda: "2026-09-28T01:35:00-03:00"
    return Dropbox(tmp_path, clock=relogio)


def test_depositar_e_ler(tmp_path):
    db = nova_caixinha(tmp_path)
    r = db.depositar("CEO", "ENGINEER", "RECADO", "constrói o módulo X")
    assert r.msg_id == "MSG-0001"
    assert r.seq == 1
    pend = db.pendentes("ENGINEER")
    assert len(pend) == 1 and pend[0].msg_id == "MSG-0001"
    # outro assento não vê
    assert db.pendentes("SCRIBE") == []


def test_ordem_de_chegada(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "RECADO", "primeiro")
    db.depositar("CEO", "ENGINEER", "RECADO", "segundo")
    db.depositar("CEO", "ENGINEER", "RECADO", "terceiro")
    pend = db.pendentes("ENGINEER")
    assert [p.conteudo for p in pend] == ["primeiro", "segundo", "terceiro"]


def test_reclamar_idempotente(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "RECADO", "faz X")
    r1 = db.reclamar("MSG-0001", "ENGINEER")
    r2 = db.reclamar("MSG-0001", "ENGINEER")  # de novo: ok, sem duplicar
    assert r1.reclamado_por == ["ENGINEER"] == r2.reclamado_por
    assert db.pendentes("ENGINEER") == []  # sumiu da fila dele


def test_nao_le_recado_dos_outros(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "RECADO", "segredo de engenharia")
    try:
        db.reclamar("MSG-0001", "SCRIBE")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "não pode ler recado dos outros" in str(e)


def test_broadcast_chega_pra_cada_assento(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "TODOS", "ALERTA", "reunião em 5 min")
    assert len(db.pendentes("ENGINEER")) == 1
    assert len(db.pendentes("SCRIBE")) == 1
    db.reclamar("MSG-0001", "ENGINEER")
    assert db.pendentes("ENGINEER") == []      # ele já leu
    assert len(db.pendentes("SCRIBE")) == 1   # o outro ainda não


def test_resposta_mantem_o_fio(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "PERGUNTA", "quanto tempo leva?")
    resp = db.responder("MSG-0001", "ENGINEER", "2 horas")
    assert resp.tipo == "RESPOSTA"
    assert resp.correlation_id == "MSG-0001"
    assert resp.para == "CEO"  # volta pro remetente
    fio = db.fio("MSG-0001")
    assert [m.msg_id for m in fio] == ["MSG-0001", "MSG-0002"]


def test_resposta_sem_fio_recusada(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("ENGINEER", "CEO", "RESPOSTA", "resposta solta")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "correlation_id" in str(e)


def test_conteudo_gigante_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("CEO", "ENGINEER", "RECADO", "x" * (CONTEUDO_MAX + 1))
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "limite" in str(e)


def test_conteudo_vazio_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("CEO", "ENGINEER", "RECADO", "   ")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "vazio" in str(e)


def test_destinatario_invalido_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("CEO", "BATMAN", "RECADO", "oi")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "inválido" in str(e)


def test_remetente_todos_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("TODOS", "ENGINEER", "RECADO", "oi")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "TODOS" in str(e)


def test_tipo_invalido_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.depositar("CEO", "ENGINEER", "FOFOCA", "oi")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "tipo inválido" in str(e)


def test_reclamar_inexistente_recusado(tmp_path):
    db = nova_caixinha(tmp_path)
    try:
        db.reclamar("MSG-9999", "ENGINEER")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "não existe" in str(e)


def test_todos_nao_reclama(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "TODOS", "RECADO", "oi geral")
    try:
        db.reclamar("MSG-0001", "TODOS")
        assert False, "deveria ter recusado"
    except DropboxError as e:
        assert "TODOS não reclama" in str(e)


def test_onze_assentos_reconhecidos():
    assert len(ASSENTOS) == 11
    assert "CEO" in ASSENTOS and "PACKAGER" in ASSENTOS


def test_arquivo_no_disco_e_valido(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "PERGUNTA", "tudo bem?")
    caminho = os.path.join(str(tmp_path), "MSG-0001.json")
    assert os.path.exists(caminho)
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)  # JSON íntegro, nunca pela metade
    assert dados["de"] == "CEO" and dados["tipo"] == "PERGUNTA"
    # seq persiste entre instâncias (outro processo continua a contagem)
    db2 = nova_caixinha(tmp_path)
    r = db2.depositar("CEO", "ENGINEER", "RECADO", "continua")
    assert r.msg_id == "MSG-0002"


def test_journal_audita_tudo(tmp_path):
    db = nova_caixinha(tmp_path)
    db.depositar("CEO", "ENGINEER", "RECADO", "faz X")
    db.reclamar("MSG-0001", "ENGINEER")
    j = db.journal()
    assert [e["evento"] for e in j] == ["depositar", "reclamar"]
    assert all(e["ts"] == "2026-09-28T01:35:00-03:00" for e in j)


if __name__ == "__main__":
    import tempfile

    falhas = 0
    for nome, fn in sorted(
        [(k, v) for k, v in globals().items() if k.startswith("test_")]
    ):
        try:
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as td:
                    fn(td)
            else:
                fn()
            print(f"OK   {nome}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"FALHOU {nome}: {e}")
    print(f"\n{18 - falhas}/18 verdes" if falhas else "\n18/18 verdes")
    sys.exit(1 if falhas else 0)
