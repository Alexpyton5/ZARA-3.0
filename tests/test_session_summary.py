"""Testes de core/session_summary: resumo estruturado persistido por sessao."""

import json

from core.session_summary import SessionRecorder, read_day_summaries


def test_persist_grava_jsonl_com_texto_redigido(tmp_path):
    rec = SessionRecorder(canal="voz", session_id="abc123", base_dir=tmp_path)
    rec.add_turn("usuario", "oi ZARA, meu cpf e 529.982.247-25")
    rec.add_turn("zara", "anotado, Alex")
    arquivo = rec.persist(resultado="ok")

    assert arquivo.exists()
    linhas = arquivo.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 1
    resumo = json.loads(linhas[0])
    assert resumo["session_id"] == "abc123"
    assert resumo["canal"] == "voz"
    assert resumo["total_turnos"] == 2
    assert resumo["turnos_usuario"] == 1
    assert resumo["resultado"] == "ok"
    # PII nao pode vazar no arquivo
    assert "529.982.247-25" not in arquivo.read_text(encoding="utf-8")
    assert "[CPF]" in resumo["pedidos"][0]


def test_topicos_extraem_palavras_relevantes(tmp_path):
    rec = SessionRecorder(base_dir=tmp_path)
    rec.add_turn("usuario", "quero automatizar a planilha de vendas da 4UP")
    rec.add_turn("usuario", "a planilha de vendas precisa de grafico mensal")
    resumo = rec.summary()
    assert "planilha" in resumo["topicos"]
    assert "vendas" in resumo["topicos"]


def test_turno_vazio_ignorado_e_leitura_do_dia(tmp_path):
    rec = SessionRecorder(base_dir=tmp_path)
    rec.add_turn("usuario", "   ")
    rec.add_turn("usuario", "bom dia")
    assert rec.summary()["total_turnos"] == 1
    rec.persist()

    dia = rec._arquivo().stem
    lidos = read_day_summaries(dia, base_dir=tmp_path)
    assert len(lidos) == 1
    assert lidos[0]["session_id"] == rec.session_id


def test_leitura_de_dia_sem_arquivo_retorna_lista_vazia(tmp_path):
    assert read_day_summaries("2099-01-01", base_dir=tmp_path) == []


def test_nota_tambem_redigida(tmp_path):
    rec = SessionRecorder(base_dir=tmp_path)
    rec.add_turn("usuario", "tudo certo")
    resumo = rec.summary(nota="ligar p/ alex.teste4up@gmail.com amanha")
    assert "[EMAIL]" in resumo["nota"]
    assert "alex.teste4up@gmail.com" not in resumo["nota"]
