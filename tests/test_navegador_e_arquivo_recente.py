"""Frases de navegador, mídia, data e arquivo recente que não chegavam a lugar
nenhum.

Todas tinham action registrada e funcionando; faltava só o padrão que liga a
fala do Alex a ela. Sem o padrão, a frase cai no LLM — que responde como se
tivesse voltado a página, aberto a aba ou lido o arquivo.
"""

import pytest

from core.action_registry import get_registry
from core.file_voice_intent import detect_file_intent
from core.pc_voice_intent import PcVoiceIntentDetector

import core.actions  # noqa: F401


@pytest.mark.parametrize(
    ("frase", "action"),
    [
        # navegador
        ("volte a página", "browser_back"),
        ("volte na página", "browser_back"),
        ("volte no navegador", "browser_back"),
        ("avance a página", "browser_forward"),
        ("nova aba", "browser_new_tab"),
        ("aba nova", "browser_new_tab"),
        ("abra uma nova aba", "browser_new_tab"),
        ("leia a página", "browser_read_page"),
        ("resuma essa página", "browser_read_page"),
        # mídia
        ("outra música desse artista", "youtube_another_by_artist"),
        ("outra dele", "youtube_another_by_artist"),
        # data e hora saem da MESMA leitura de sistema
        ("que dia é hoje", "system_time"),
        ("qual é a data", "system_time"),
        ("que horas são", "system_time"),
    ],
)
def test_frase_natural_chega_na_action_certa(frase, action):
    result = PcVoiceIntentDetector().detect(frase)
    assert result.is_pc_intent is True, frase
    assert result.blocked is False, frase
    assert result.action == action
    assert get_registry().get_spec(action) is not None


@pytest.mark.parametrize(
    ("frase", "url"),
    [
        ("abra o gmail", "https://mail.google.com/"),
        ("abra meu email", "https://mail.google.com/"),
        ("abra o drive", "https://drive.google.com/"),
        ("abra a agenda", "https://calendar.google.com/"),
        ("abra o calendário", "https://calendar.google.com/"),
    ],
)
def test_destinos_fixos_de_navegador_nao_sao_apps(frase, url):
    """A URL é constante no padrão — nunca vem da fala."""
    result = PcVoiceIntentDetector().detect(frase)
    assert result.action == "browser_open_url"
    assert result.param == url
    assert result.blocked is False


@pytest.mark.parametrize(
    "frase",
    [
        "abra o último arquivo",
        "abra o ultimo arquivo baixado",
        "abra o arquivo mais recente",
        "abra o último download",
        "abra o último arquivo que eu baixei",
    ],
)
def test_arquivo_mais_recente_usa_downloads_por_padrao(frase):
    intent = detect_file_intent(frase)
    assert intent is not None, frase
    assert intent.action == "files_open_latest"
    assert intent.params == {"folder": "downloads"}
    assert intent.mutating is False


def test_pasta_explicita_vence_o_padrao():
    intent = detect_file_intent("abra o último arquivo em documentos")
    assert intent is not None
    assert intent.params == {"folder": "documents"}


@pytest.mark.parametrize(
    "frase",
    [
        "abra o chrome",                    # app, não arquivo
        "abra o último capítulo do livro",  # conversa
    ],
)
def test_frase_que_nao_e_arquivo_nao_vira_arquivo(frase):
    assert detect_file_intent(frase) is None


@pytest.mark.parametrize(
    "frase",
    [
        "me fale sobre uma nova aba de conversa",
        "me diga o que é o gmail",
    ],
)
def test_conversa_parecida_nao_vira_comando(frase):
    result = PcVoiceIntentDetector().detect(frase)
    assert result.is_pc_intent is False
