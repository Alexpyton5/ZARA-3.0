# -*- coding: utf-8 -*-
"""Testes da FRENTE C — nunca mentir (MISSAO GIGANTE 3 "JARVIS REAL").

- O registro da verdade cobre os 4 canais de comunicacao como ASSUMIDO
  (atalho, sem numero falso).
- Nenhuma superficie "real" pode existir sem fonte de dado documentada.
- Trava C3: nenhum dado falso conhecido pode existir no backend Python.
"""

from pathlib import Path

import pytest

from core.truth_registry import (
    DEMO_FALSE_FINGERPRINTS,
    VALID_STATUS,
    assert_no_fake_backend_strings,
    get_registry,
    honest_summary,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_registry_covers_all_comm_channels_as_shortcut():
    reg = get_registry()
    for key in ("comms.whatsapp", "comms.telegram", "comms.instagram", "comms.gmail"):
        assert key in reg, f"canal {key} sem registro da verdade"
        assert reg[key].status == "assumido", f"{key} nao pode exibir numero"


def test_every_surface_has_a_real_source_or_honest_status():
    for key, surface in get_registry().items():
        assert surface.status in VALID_STATUS, key
        assert surface.source and surface.source.strip(), key
        assert surface.evidence and surface.evidence.strip(), key


def test_demo_false_entries_are_flagged_never_legit():
    reg = get_registry()
    demos = [s for s in reg.values() if s.status == "demo"]
    assert demos, "o dado falso conhecido precisa estar listado para ser cacado"
    for s in demos:
        assert "NENHUMA" in s.source or "falso" in s.label.lower() or "ficticio" in s.source.lower()


def test_trava_c3_no_fake_strings_in_backend():
    found = assert_no_fake_backend_strings(REPO_ROOT)
    assert found == []


def test_trava_c3_detects_known_fingerprints(tmp_path, monkeypatch):
    core = tmp_path / "core"
    core.mkdir()
    (core / "mentiroso.py").write_text(
        'X = "17 rotinas ativas"\n', encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="TRAVA C3 FALHOU"):
        assert_no_fake_backend_strings(tmp_path)


def test_honest_summary_lists_ligado_vs_assumido():
    summary = honest_summary()
    assert len(summary["ligado"]) >= 4, "espera-se sistema/memoria/lembretes/lab ligados"
    assert len(summary["assumido"]) == 4, "os 4 canais sao atalho"
    assert summary["demo_falso"], "o demo falso precisa estar listado"
