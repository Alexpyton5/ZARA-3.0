"""FRENTE G - Identificacao por rosto/voz: teste em simulacao.

Criterio de aceite: pessoa autorizada passa; estranho ouve a frase EXATA
"você é um estranho" e e ignorado.
"""
import json

import pytest

from core.identidade_rosto_voz import (
    FRASE_ESTRANHO,
    PAPEIS_VALIDOS,
    IdentityGate,
    IdentityStore,
    ProvedorSimulacao,
)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    return IdentityStore()


def _portao_com_cadastro(store, mapa):
    prov = ProvedorSimulacao(mapa=mapa)
    gate = IdentityGate(store=store, prov_rosto=prov, prov_voz=prov)
    for papel in ("dono", "esposa"):
        for modalidade in ("rosto", "voz"):
            gate.cadastrar(papel, modalidade, [b"a1", b"a2", b"a3"],
                           qualidade=0.9)
    return gate


# --- G2: autorizado passa --------------------------------------------------------

def test_dono_autorizado_passa(store):
    gate = _portao_com_cadastro(store, {("dono", "voz"): 0.92})
    d = gate.gate_interaction({"voz": b"amostra"})
    assert d.decisao == "autorizado"
    assert d.pessoa == "dono"
    assert d.ignorar is False
    assert d.fala is None


def test_esposa_autorizada_fala_normal(store):
    gate = _portao_com_cadastro(store, {("esposa", "voz"): 0.88})
    d = gate.gate_interaction({"voz": b"amostra"})
    assert d.decisao == "autorizado"
    assert d.pessoa == "esposa"
    assert d.ignorar is False
    assert d.fala is None  # fala normal: nenhuma frase de bloqueio


def test_rosto_tambem_autoriza(store):
    gate = _portao_com_cadastro(store, {("dono", "rosto"): 0.75})
    d = gate.gate_interaction({"rosto": b"frame"})
    assert d.decisao == "autorizado"
    assert d.pessoa == "dono"


# --- G2: estranho ouve a frase exata e e ignorado --------------------------------

def test_estranho_ouve_frase_exata_e_ignorado(store):
    gate = _portao_com_cadastro(store, {})  # ninguem pontua
    d = gate.gate_interaction({"voz": b"amostra", "rosto": b"frame"})
    assert d.decisao == "estranho"
    assert d.fala == "você é um estranho"
    assert d.fala == FRASE_ESTRANHO
    assert d.ignorar is True


def test_latch_ignora_em_silencio_sem_repetir_frase(store):
    gate = _portao_com_cadastro(store, {})
    primeira = gate.gate_interaction({"voz": b"x"})
    assert primeira.fala == "você é um estranho"
    assert gate.estranho_ativo is True
    segunda = gate.gate_interaction({"voz": b"y"})
    assert segunda.decisao == "estranho"
    assert segunda.fala is None  # nao repete a frase
    assert segunda.ignorar is True


def test_latch_libera_quando_dono_reconhecido(store):
    gate = _portao_com_cadastro(store, {("dono", "voz"): 0.9})
    gate.gate_interaction({"voz": b"estranho?"})  # mapa nao cobre -> estranho
    # simula o dono falando depois: injeta pontuacao alta no mapa
    gate.prov_voz.mapa[("dono", "voz")] = 0.95
    d = gate.gate_interaction({"voz": b"dono"})
    assert d.decisao == "autorizado"
    assert gate.estranho_ativo is False


def test_pontuacao_ambigua_e_fail_closed(store):
    # 0.55 esta na faixa ambigua [0.45, 0.60) do rosto -> estranho
    gate = _portao_com_cadastro(store, {("dono", "rosto"): 0.55})
    d = gate.gate_interaction({"rosto": b"frame"})
    assert d.decisao == "estranho"
    assert d.fala == "você é um estranho"
    assert d.ignorar is True


# --- G3: sem cadastro nao trava o app --------------------------------------------

def test_store_novo_nasce_vazio_sem_biometria_inventada(store):
    assert store.algum_cadastro() is False
    assert store.pessoas() == {}


def test_sem_cadastro_portao_passa_sem_travar(store):
    gate = IdentityGate(store=store)
    d = gate.gate_interaction({"voz": b"qualquer"})
    assert d.decisao == "nao_cadastrado"
    assert d.ignorar is False


# --- cadastro: validacoes + persistencia honesta ---------------------------------

def test_cadastro_exige_papel_valido(store):
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao())
    with pytest.raises(ValueError):
        gate.cadastrar("vizinho", "voz", [b"a", b"b", b"c"])


def test_cadastro_exige_minimo_de_amostras(store):
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao())
    with pytest.raises(ValueError):
        gate.cadastrar("dono", "voz", [b"a"])


def test_cadastro_exige_qualidade_minima(store):
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao())
    with pytest.raises(ValueError):
        gate.cadastrar("dono", "voz", [b"a", b"b", b"c"], qualidade=0.1)


def test_cadastro_persiste_apenas_hash_e_metadados(store):
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao())
    amostras = [b"amostra-voz-1", b"amostra-voz-2", b"amostra-voz-3"]
    tpl = gate.cadastrar("esposa", "voz", amostras, qualidade=0.9)
    assert tpl.papel == "esposa"
    assert tpl.modalidade == "voz"
    dados = json.loads(store.caminho.read_text(encoding="utf-8"))
    voz = dados["pessoas"]["esposa"]["voz"]
    assert voz["hash_embedding"]
    # nenhum dado cru no disco: as amostras nao aparecem no JSON
    bruto = store.caminho.read_text(encoding="utf-8")
    for a in amostras:
        assert a.decode() not in bruto


def test_remover_cadastro_apaga_referencia(store):
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao())
    gate.cadastrar("dono", "voz", [b"a", b"b", b"c"])
    assert store.remover("dono", "voz") is True
    assert store.algum_cadastro() is False


def test_papeis_validos_sao_dono_e_esposa():
    assert set(PAPEIS_VALIDOS) == {"dono", "esposa"}


# --- auditoria -------------------------------------------------------------------

def test_eventos_de_identidade_vao_para_auditoria(store, tmp_path):
    from core.audit_log import AuditLog
    audit = AuditLog(db_path=tmp_path / "audit.db")
    gate = _portao_com_cadastro(store, {})
    gate._audit = lambda a, r, o, e=None: audit.record(f"identidade.{a}", r, o, e)
    gate.gate_interaction({"voz": b"x"})
    acoes = [r["action"] for r in audit.recent(10)]
    assert "identidade.estranho" in acoes
