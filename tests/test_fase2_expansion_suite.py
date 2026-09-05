"""Testes offline (sem rede real, sem tocar o repositório real) para as
peças construídas em 2026-08-28 sob autorização ampla do Alex: bridge com
Claude, protocolo anti-regressão, macros, smart clipboard, organizador de
arquivos, entendimento de tela, RAG local, price watch e transcritor de
reuniões. Nenhuma delas é chamada pelo pipeline de produção ainda.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.local_rag import Document, build_index, load_documents, query
from core.macro_engine import build_end_of_day_macro, get_macro, list_macros
from core.screen_understanding import describe_screen
from tools.file_organizer import classify_content, extract_text, plan_reorganization
from tools.meeting_transcriber import summarize_transcript, transcribe_audio_file
from tools.price_watch import extract_prices_from_text, parse_duckduckgo_html
from tools.smart_clipboard import parse_clipboard_text
from tools.zara_claude_bridge import format_prompt_for_claude

# --- tools/zara_claude_bridge.py -------------------------------------------

def test_format_prompt_for_claude_basic():
    prompt = format_prompt_for_claude("organize a pasta downloads")

    assert "organize a pasta downloads" in prompt


def test_format_prompt_for_claude_includes_context_when_given():
    prompt = format_prompt_for_claude("faz isso", context="referente ao projeto X")

    assert "referente ao projeto X" in prompt


def test_format_prompt_for_claude_empty_raises():
    with pytest.raises(ValueError):
        format_prompt_for_claude("   ")


# --- tests/regression_suite.py ---------------------------------------------

def test_run_golden_path_smoke_reports_real_outcome_honestly():
    """Não assume 'sempre verde' -- este repo tem 1 falha pré-existente e
    conhecida em test_brightness_control.py (item KNOWN_BROKEN, não
    relacionado a esta sessão). O que se prova aqui é que a função REFLETE
    o resultado real do pytest, não que o repo está sempre limpo."""
    from tests.regression_suite import run_golden_path_smoke

    result = run_golden_path_smoke()

    assert isinstance(result.passed, bool)
    assert result.passed == (result.exit_code == 0)
    assert result.summary  # nunca vazio -- sempre diz o que aconteceu
    assert "failed" in result.summary or "passed" in result.summary


def test_run_golden_path_smoke_missing_python_raises():
    from tests.regression_suite import RegressionSuiteError, run_golden_path_smoke

    with pytest.raises(RegressionSuiteError):
        run_golden_path_smoke(python_exe="C:/nao/existe/python.exe")


def test_create_restore_point_and_rollback_command(tmp_path):
    import subprocess

    from tests.regression_suite import create_restore_point, rollback_command_for

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    tag = create_restore_point("teste-x", cwd=tmp_path)

    assert tag == "restore-point-teste-x"
    assert rollback_command_for(tag) == f"git reset --hard {tag}"


# --- core/macro_engine.py ---------------------------------------------------

def test_night_mode_macro_is_registered():
    assert "modo_noite" in list_macros()
    macro = get_macro("modo_noite")
    assert macro.steps[0].action == "os_night_light_on"


def test_end_of_day_macro_hibernate_is_last_step():
    macro = build_end_of_day_macro(commit_suggestion="feat: x", summary_text="resumo do dia")

    assert macro.steps[-1].action == "os_power"
    assert macro.steps[-1].param == "hibernate"
    assert macro.steps[0].action is None  # sugestão de commit, nunca executada aqui


def test_end_of_day_macro_without_extras_still_hibernates_last():
    macro = build_end_of_day_macro()

    assert macro.steps[-1].param == "hibernate"
    assert len(macro.steps) == 2  # fecha abas + hiberna


# --- tools/smart_clipboard.py -----------------------------------------------

def test_parse_clipboard_text_extracts_email_and_phone():
    text = "Fale com joao@example.com ou (11) 91234-5678, CEP 01310-100."
    result = parse_clipboard_text(text)

    assert "joao@example.com" in result["emails"]
    assert result["ceps"] == ["01310-100"]


def test_parse_clipboard_text_detects_json():
    result = parse_clipboard_text('{"nome": "Ana", "idade": 30}')

    assert result["json"] == {"nome": "Ana", "idade": 30}


def test_parse_clipboard_text_detects_table():
    result = parse_clipboard_text("a,b,c\n1,2,3\n4,5,6")

    assert result["is_table"] is True


def test_parse_clipboard_text_empty_input():
    result = parse_clipboard_text("")

    assert result["emails"] == []
    assert result["json"] is None


# --- tools/file_organizer.py ------------------------------------------------

def test_extract_text_reads_txt(tmp_path):
    file_path = tmp_path / "nota.txt"
    file_path.write_text("conteúdo simples", encoding="utf-8")

    assert extract_text(file_path) == "conteúdo simples"


def test_extract_text_unsupported_format_returns_empty(tmp_path):
    file_path = tmp_path / "foto.png"
    file_path.write_bytes(b"\x89PNG")

    assert extract_text(file_path) == ""


def test_classify_content_recognizes_conta_de_luz():
    text = "Sua fatura de energia elétrica. Consumo: 320 kwh. Distribuidora: Enel."
    category, confidence = classify_content(text)

    assert category == "conta_luz"
    assert confidence == "alta"


def test_classify_content_unknown_text():
    category, confidence = classify_content("um texto qualquer sem palavra-chave conhecida")

    assert category == "desconhecido"
    assert confidence == "nenhuma"


def test_plan_reorganization_suggests_name_with_period(tmp_path):
    file_path = tmp_path / "Scan_00123.txt"
    file_path.write_text("Conta de energia elétrica. kwh consumido. Vencimento 08/2026.", encoding="utf-8")

    plans = plan_reorganization([str(file_path)])

    assert plans[0].category == "conta_luz"
    assert plans[0].suggested_name == "Conta_Luz_Agosto_2026.txt"


def test_plan_reorganization_missing_file_is_reported():
    plans = plan_reorganization(["/nao/existe/arquivo.txt"])

    assert plans[0].category == "arquivo_nao_encontrado"
    assert plans[0].suggested_name is None


# --- core/screen_understanding.py -------------------------------------------

def test_describe_screen_missing_file_returns_none():
    assert describe_screen("/nao/existe/print.png") is None


def test_describe_screen_unsupported_format_returns_none(tmp_path):
    file_path = tmp_path / "captura.bmp"
    file_path.write_bytes(b"BM")

    assert describe_screen(str(file_path)) is None


def test_describe_screen_no_api_key_returns_none(tmp_path, monkeypatch):
    file_path = tmp_path / "captura.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert describe_screen(str(file_path)) is None


def test_describe_screen_success_with_mocked_http(tmp_path, monkeypatch):
    import core.screen_understanding as module

    file_path = tmp_path / "captura.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Uma janela do VS Code aberta."}]}}]}

    class FakeHttpx:
        @staticmethod
        def post(url, json, timeout):
            assert "fake-key" in url
            return FakeResponse()

    monkeypatch.setattr(module, "httpx", FakeHttpx, raising=False)
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "httpx", FakeHttpx)

    result = describe_screen(str(file_path), "o que tem na tela?")

    assert result == "Uma janela do VS Code aberta."


# --- core/local_rag.py -------------------------------------------------------

def test_load_documents_reads_txt_and_md(tmp_path):
    (tmp_path / "a.txt").write_text("texto sobre latência de voz", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Documento\nfala sobre volume e brilho", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")

    docs = load_documents(str(tmp_path))

    assert len(docs) == 2


def test_query_finds_relevant_document():
    docs = [
        Document(path="a.txt", text="a latência de voz da zara é medida em milissegundos"),
        Document(path="b.txt", text="receita de bolo de chocolate com farinha e ovos"),
    ]
    index = build_index(docs)

    hits = query(index, "latência de voz")

    assert hits[0].path == "a.txt"
    assert hits[0].score > 0


def test_query_no_match_returns_empty():
    docs = [Document(path="a.txt", text="texto qualquer")]
    index = build_index(docs)

    assert query(index, "termo completamente ausente xyzabc") == []


def test_query_empty_index_returns_empty():
    index = build_index([])

    assert query(index, "qualquer coisa") == []


# --- tools/price_watch.py ---------------------------------------------------

def test_extract_prices_from_text_finds_brl_values():
    prices = extract_prices_from_text("De R$ 1.999,90 por R$ 1.499,00 à vista")

    assert prices == [1999.90, 1499.00]


def test_extract_prices_from_text_no_price_returns_empty():
    assert extract_prices_from_text("nenhum preço aqui") == []


def test_parse_duckduckgo_html_extracts_results():
    html = (
        '<a class="result__a" href="https://loja.com/monitor">Monitor 27 polegadas</a>'
        '<a class="result__snippet" href="x">Por R$ 899,00 na loja.</a>'
    )
    results = parse_duckduckgo_html(html)

    assert len(results) == 1
    assert results[0]["title"] == "Monitor 27 polegadas"
    assert results[0]["prices"] == [899.00]


def test_parse_duckduckgo_html_no_results():
    assert parse_duckduckgo_html("<html><body>nada aqui</body></html>") == []


# --- tools/meeting_transcriber.py -------------------------------------------

def test_transcribe_audio_file_missing_file_returns_none():
    assert transcribe_audio_file("/nao/existe/audio.wav") is None


def test_transcribe_audio_file_success_with_mocked_whisper(tmp_path, monkeypatch):
    import types

    audio_path = tmp_path / "reuniao.wav"
    audio_path.write_bytes(b"RIFF")

    class FakeSegment:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, language="pt"):
            return [FakeSegment("Olá pessoal,"), FakeSegment(" vamos começar a reunião.")], object()

    fake_module = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    result = transcribe_audio_file(str(audio_path))

    assert result == "Olá pessoal, vamos começar a reunião."


def test_summarize_transcript_empty_returns_none():
    assert summarize_transcript("") is None


def test_summarize_transcript_no_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    assert summarize_transcript("texto de reunião qualquer") is None
