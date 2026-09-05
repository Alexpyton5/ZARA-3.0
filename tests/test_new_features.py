"""Testes offline (sem microfone, sem rede) para as duas pecas isoladas do
plano 'Copiloto do Windows': core/multi_intent_parser.py e
tools/system_stats.py. Nenhum dos dois e chamado pelo pipeline de producao
ainda -- estes testes provam a peca em si (nivel SOURCE/TEST da taxonomia de
evidencia do projeto), nao o comportamento integrado."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.multi_intent_parser import parse_multi_intent, parse_multi_intent_json, split_into_clauses
from tools.system_stats import SystemSnapshot, read_stats

# --- multi_intent_parser -----------------------------------------------

def test_split_into_clauses_basic_comma():
    assert split_into_clauses("ajuste volume para 30, ligue a luz noturna") == [
        "ajuste volume para 30",
        "ligue a luz noturna",
    ]


def test_split_into_clauses_e_depois_and_depois():
    assert split_into_clauses("abra o chrome e depois abra o youtube") == [
        "abra o chrome",
        "abra o youtube",
    ]
    assert split_into_clauses("abra o chrome depois abra o youtube") == [
        "abra o chrome",
        "abra o youtube",
    ]


def test_split_into_clauses_strips_leading_zara_and_punctuation():
    assert split_into_clauses("Zara, aumente o volume, diminua o brilho.") == [
        "aumente o volume",
        "diminua o brilho",
    ]


def test_parse_multi_intent_example_from_alex():
    # "abra o navegador" (com artigo) não resolve alias de app hoje -- bug
    # pré-existente em core/pc_voice_intent.py, fora do escopo desta peça
    # isolada. Usando "abra o chrome" para não testar contra um bug alheio.
    result = parse_multi_intent(
        "ajuste volume para 30, ligue a luz noturna e abra o chrome"
    )

    assert [item["action"] for item in result] == [
        "os_volume",
        "os_night_light_on",
        "os_app",
    ]
    assert result[0]["param"] == "30"
    assert all(item["action"] is not None for item in result)


def test_parse_multi_intent_unrecognized_clause_is_reported_not_dropped():
    result = parse_multi_intent("aumente o volume, faça um bolo de chocolate")

    assert result[0]["action"] == "os_volume"
    assert result[1] == {"action": None, "param": None, "raw": "faça um bolo de chocolate"}


def test_parse_multi_intent_single_clause_still_works():
    result = parse_multi_intent("diminua muito o volume")

    assert len(result) == 1
    assert result[0]["action"] == "os_volume"
    assert result[0]["param"] == "down_muito"


def test_parse_multi_intent_json_is_valid_json_array():
    import json

    raw = parse_multi_intent_json("tire o som, abra o chrome")
    parsed = json.loads(raw)

    assert isinstance(parsed, list)
    assert parsed[0]["action"] == "audio_mute"
    assert parsed[1]["action"] == "os_app"


# --- system_stats --------------------------------------------------------

def test_read_stats_returns_populated_snapshot():
    snap = read_stats(cpu_interval=0.0)

    assert isinstance(snap, SystemSnapshot)
    assert 0.0 <= snap.cpu_percent <= 100.0
    assert 0.0 <= snap.ram_percent <= 100.0
    assert snap.ram_total_gb > 0
    assert snap.ram_used_gb <= snap.ram_total_gb + 0.5  # folga por arredondamento


def test_read_stats_battery_fields_are_consistent(monkeypatch):
    import tools.system_stats as system_stats_module

    class FakeBattery:
        percent = 42.0
        power_plugged = True

    monkeypatch.setattr(system_stats_module.psutil, "sensors_battery", lambda: FakeBattery())
    snap = read_stats(cpu_interval=0.0)

    assert snap.battery_percent == 42.0
    assert snap.battery_plugged is True


def test_read_stats_handles_no_battery_desktop(monkeypatch):
    import tools.system_stats as system_stats_module

    monkeypatch.setattr(system_stats_module.psutil, "sensors_battery", lambda: None)
    snap = read_stats(cpu_interval=0.0)

    assert snap.battery_percent is None
    assert snap.battery_plugged is None
