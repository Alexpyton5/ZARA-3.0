"""Testes da peca 1 da memoria compartilhada (shared_memory_spec).

Logica pura, stdlib, custo zero. Roda no .venv real do PC.
"""
import pytest

from core.shared_memory_spec import (
    KNOWN_SOURCES,
    SharedEntry,
    SharedMemoryError,
    SharedMemorySpec,
    build_view,
    entry_from_lab_fact,
    from_dict,
    to_dict,
)
from core.lab_memory import LabMemory


def _entry(**kw):
    base = dict(source="lab", key="versao.app", value="3.0.1",
                author="CEO", written_at=1700000000.0)
    base.update(kw)
    return SharedEntry(**base)


def _spec(**kw):
    base = dict(bot_id="bot-teste")
    base.update(kw)
    return SharedMemorySpec(**base)


# -- spec ---------------------------------------------------------------
def test_spec_minima_vale():
    spec = _spec()
    assert spec.bot_id == "bot-teste"
    assert set(spec.sources) == {"lab", "zara"}


def test_spec_fonte_desconhecida_recusada():
    with pytest.raises(SharedMemoryError):
        _spec(sources=("lab", "instagram"))


def test_spec_sources_vazio_recusado():
    with pytest.raises(SharedMemoryError):
        _spec(sources=())


def test_spec_bot_id_invalido_recusado():
    for bad in ("", "BOT GRANDE", "bot_teste!", "a" * 41):
        with pytest.raises(SharedMemoryError):
            _spec(bot_id=bad)


def test_spec_max_entries_fora_do_teto_recusado():
    for bad in (0, 501, -3, "100", True):
        with pytest.raises(SharedMemoryError):
            _spec(max_entries=bad)


def test_from_dict_campo_desconhecido_recusado():
    with pytest.raises(SharedMemoryError):
        from_dict({"bot_id": "x", "campo_novo": 1})


def test_from_dict_nao_dicionario_recusado():
    with pytest.raises(SharedMemoryError):
        from_dict(["bot_id"])


def test_to_dict_from_dict_ida_e_volta():
    spec = _spec(sources=("lab",), max_entries=10, include_provenance=False)
    clone = from_dict(to_dict(spec))
    assert clone == spec


# -- entry --------------------------------------------------------------
def test_entry_valida():
    entry = _entry()
    assert entry.source in KNOWN_SOURCES


def test_entry_fonte_desconhecida_recusada():
    with pytest.raises(SharedMemoryError):
        _entry(source="whatsapp")


def test_entry_valor_vazio_ou_grande_recusado():
    with pytest.raises(SharedMemoryError):
        _entry(value="")
    with pytest.raises(SharedMemoryError):
        _entry(value="x" * 4097)


def test_entry_sem_procedencia_recusada():
    with pytest.raises(SharedMemoryError):
        _entry(author="   ")
    with pytest.raises(SharedMemoryError):
        _entry(written_at=0)


def test_entry_chave_invalida_recusada():
    with pytest.raises(SharedMemoryError):
        _entry(key="Chave Com Espaco")


# -- adaptador do lab real ----------------------------------------------
def test_entry_from_lab_fact_converte_fato_real():
    mem = LabMemory(now=lambda: 1700000000.0)
    mem.write("ENGINEER", "build.verde", "suite 2778/0")
    facts = mem.facts()
    entry = entry_from_lab_fact("build.verde", facts["build.verde"])
    assert entry.source == "lab"
    assert entry.author == "ENGINEER"
    assert entry.value == "suite 2778/0"
    assert entry.written_at == 1700000000.0


def test_entry_from_lab_fact_incompleto_recusado():
    with pytest.raises(SharedMemoryError):
        entry_from_lab_fact("k", {"value": "v"})


# -- build_view ----------------------------------------------------------
def test_build_view_monta_com_procedencia_e_ordem():
    spec = _spec()
    view = build_view(spec, [
        _entry(source="zara", key="b", author="ZARA"),
        _entry(source="lab", key="a", author="CEO"),
    ])
    keys = [(e.source, e.key) for e in view.list()]
    assert keys == [("lab", "a"), ("zara", "b")]  # ordem deterministica
    assert view.get("lab", "a").author == "CEO"


def test_build_view_fonte_fora_da_spec_recusada():
    spec = _spec(sources=("lab",))
    with pytest.raises(SharedMemoryError):
        build_view(spec, [_entry(source="zara", key="b")])


def test_build_view_item_nao_entry_recusado():
    spec = _spec()
    with pytest.raises(SharedMemoryError):
        build_view(spec, [{"source": "lab"}])


def test_build_view_respeita_max_entries():
    spec = _spec(max_entries=2)
    view = build_view(spec, [_entry(key=f"k{i}") for i in range(5)])
    assert len(view.list()) == 2


def test_view_e_congelada():
    view = build_view(_spec(), [_entry()])
    with pytest.raises(Exception):
        view.entries = ()


def test_describe_tem_teto_e_mostra_procedencia():
    spec = _spec(max_entries=30)
    view = build_view(spec, [_entry(key=f"k{i:02d}") for i in range(20)])
    lines = view.describe()
    assert len(lines) <= 12
    assert any("(por CEO)" in line for line in lines)
    assert any("e mais" in line for line in lines)


def test_describe_sem_procedencia_quando_desligada():
    spec = _spec(include_provenance=False)
    view = build_view(spec, [_entry()])
    assert view.include_provenance is False
    assert not any("(por " in line for line in view.describe())
