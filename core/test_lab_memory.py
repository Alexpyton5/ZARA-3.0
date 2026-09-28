"""Portao da memoria compartilhada do Lab: 18 checagens, custo zero."""
import pytest

from core.lab_memory import LabMemory, MemoryDenied
from core.lab_v1.domain import RoleName
from core.lab_v1.fixed_seats import FIXED_SEATS


def mem():
    return LabMemory(now=lambda: 1700000000.0)


def test_write_read_roundtrip():
    m = mem()
    m.write(RoleName.ENGINEER, "voz.kore.cota", "ok")
    assert m.read("voz.kore.cota") == "ok"


def test_all_eleven_seats_can_write():
    m = mem()
    for i, role in enumerate(FIXED_SEATS):
        m.write(role, f"fato.{i}", "v")
    assert len(m.list()) == 11


def test_unknown_seat_refused():
    m = mem()
    with pytest.raises(MemoryDenied, match="SEAT_UNKNOWN"):
        m.write("DIRETOR", "a.b", "v")


def test_role_outside_fixed_seats_refused():
    m = mem()
    # MEMBER e BUILDER existem no enum, mas nao sao dos 11 assentos
    for role in (RoleName.MEMBER, RoleName.BUILDER):
        with pytest.raises(MemoryDenied, match="SEAT_UNKNOWN"):
            m.write(role, "a.b", "v")


def test_key_invalid():
    m = mem()
    for bad in ("", "CAIXA.ALTA", "com espaco", "x" * 65, "traco_-ok".upper()):
        with pytest.raises(MemoryDenied, match="KEY_INVALID"):
            m.write(RoleName.SCRIBE, bad, "v")


def test_value_empty_refused():
    m = mem()
    with pytest.raises(MemoryDenied, match="VALUE_INVALID"):
        m.write(RoleName.SCRIBE, "a.b", "")


def test_value_too_large_refused():
    m = mem()
    with pytest.raises(MemoryDenied, match="VALUE_INVALID"):
        m.write(RoleName.SCRIBE, "a.b", "x" * 4097)
    m.write(RoleName.SCRIBE, "a.b", "x" * 4096)  # limite passa


def test_overwrite_by_writer_ok():
    m = mem()
    m.write(RoleName.TESTER, "gate.suite", "vermelha")
    m.write(RoleName.TESTER, "gate.suite", "verde")
    assert m.read("gate.suite") == "verde"
    assert len(m.history("gate.suite")) == 2


def test_overwrite_by_other_seat_refused():
    m = mem()
    m.write(RoleName.TESTER, "gate.suite", "vermelha")
    with pytest.raises(MemoryDenied, match="MEMORY_LOCKED"):
        m.write(RoleName.REVIEWER, "gate.suite", "verde")
    assert m.read("gate.suite") == "vermelha"  # intacto


def test_overwrite_by_ceo_ok():
    m = mem()
    m.write(RoleName.TESTER, "gate.suite", "vermelha")
    m.write(RoleName.CEO, "gate.suite", "verde")
    assert m.read("gate.suite") == "verde"


def test_retract_by_writer_ok():
    m = mem()
    m.write(RoleName.ARCHITECT, "plano.x", "v1")
    m.retract(RoleName.ARCHITECT, "plano.x")
    assert m.read("plano.x") is None
    assert "plano.x" not in m.list()


def test_retract_by_other_refused():
    m = mem()
    m.write(RoleName.ARCHITECT, "plano.x", "v1")
    with pytest.raises(MemoryDenied, match="MEMORY_LOCKED"):
        m.retract(RoleName.CRITIC, "plano.x")
    assert m.read("plano.x") == "v1"  # intacto


def test_retract_by_ceo_ok():
    m = mem()
    m.write(RoleName.ARCHITECT, "plano.x", "v1")
    m.retract(RoleName.CEO, "plano.x")
    assert m.read("plano.x") is None


def test_retract_missing_refused():
    m = mem()
    with pytest.raises(MemoryDenied, match="MEMORY_MISSING"):
        m.retract(RoleName.CEO, "nunca.existiu")


def test_history_ordered():
    m = mem()
    m.write(RoleName.SECRETARY, "ata.1", "a")
    m.write(RoleName.SECRETARY, "ata.1", "b")
    m.retract(RoleName.SECRETARY, "ata.1")
    hist = m.history("ata.1")
    assert [h.op for h in hist] == ["WRITE", "WRITE", "RETRACT"]
    assert [h.seq for h in hist] == sorted(h.seq for h in hist)
    assert all(h.seat == "SECRETARY" for h in hist)


def test_journal_clock_injectable():
    ticks = iter([100.0, 200.0])
    m = LabMemory(now=lambda: next(ticks))
    m.write(RoleName.RESEARCHER, "achado.1", "x")
    m.retract(RoleName.RESEARCHER, "achado.1")
    j = m.journal()
    assert [l.ts for l in j] == [100.0, 200.0]


def test_provenance():
    m = mem()
    m.write(RoleName.PACKAGER, "build.99", "ok")
    prov = m.provenance("build.99")
    assert prov["seat"] == "PACKAGER"
    assert prov["seq"] == 1
    assert m.provenance("ausente") is None


def test_facts_with_provenance():
    m = mem()
    m.write(RoleName.UI_DESIGNER, "tela.home", "pronta")
    f = m.facts()["tela.home"]
    assert f == {"value": "pronta", "seat": "UI_DESIGNER",
                "seq": 1, "written_at": 1700000000.0}
