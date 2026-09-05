"""Contratos offline da ponte Telegram privada."""
from __future__ import annotations

import time

import pytest

from core.telegram_ponte import PonteTelegram


def _ponte(*, dono=7):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino: str, texto: str) -> str:
        recebidos.append((destino, texto))
        return "ok"

    ponte = PonteTelegram("123:abc", executar, dono=dono)
    ponte._recebidos = recebidos
    return ponte


async def _ok(_texto: str) -> bool:
    return True


@pytest.mark.asyncio
async def test_audio_do_dono_e_transcrito_e_repassado_com_confirmacao(monkeypatch):
    ponte = _ponte()
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda _token, _mensagem: ("claude: pode seguir", ""),
    )

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "voice": {"file_id": "abc"},
                "date": int(time.time()),
            }
        }
    )

    assert ponte._recebidos == [("claude", "pode seguir")]
    assert enviados == ['Ouvi: "claude: pode seguir"\n\nok']


@pytest.mark.asyncio
async def test_audio_de_estranho_nao_e_transcrito_nem_executado(monkeypatch):
    ponte = _ponte()
    transcricoes: list[dict] = []
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda _token, mensagem: transcricoes.append(mensagem) or ("zara: oi", ""),
    )

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 99},
                "voice": {"file_id": "abc"},
                "date": int(time.time()),
            }
        }
    )

    assert transcricoes == []
    assert ponte._recebidos == []


@pytest.mark.asyncio
async def test_resposta_repetida_e_suprimida_e_marcador_sobrevive(monkeypatch, tmp_path):
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs["text"]) or {"ok": True},
    )
    marcador = tmp_path / "telegram_lido.json"
    monkeypatch.setattr(PonteTelegram, "_arquivo_marcador", staticmethod(lambda: marcador))
    ponte = _ponte()
    ponte._ultimo_update = 42
    ponte._gravar_marcador()
    await ponte.avisar("mesma resposta")
    await ponte.avisar("mesma resposta")

    restaurada = _ponte(dono=None)
    assert restaurada._carregar_marcador() is True
    assert restaurada._ultimo_update == 42
    assert restaurada.dono == 7
    assert enviados == ["mesma resposta"]


@pytest.mark.parametrize(
    ("texto", "destino", "conteudo"),
    [
        ("claude: conserta o volume", "claude", "conserta o volume"),
        ("claude conserta o volume", "claude", "conserta o volume"),
        ("codex, roda os testes", "codex", "roda os testes"),
        ("zara: diminui o volume", "zara", "diminui o volume"),
        ("diminui o volume", "zara", "diminui o volume"),
        ("CLAUDE: pode seguir", "claude", "pode seguir"),
        ("todos- responda sim", "todos", "responda sim"),
        ("todo mundo: bom dia", "todos", "bom dia"),
        ("@claude pode seguir", "claude", "pode seguir"),
    ],
)
def test_roteamento_aceita_prefixos_e_mencoes(texto, destino, conteudo):
    assert PonteTelegram.rotear(texto) == (destino, conteudo)


@pytest.mark.parametrize(
    "texto",
    ["codexplorer travou", "zaragoza fica na espanha", "claudete escreveu"],
)
def test_prefixo_parcial_nao_vira_destino(texto):
    assert PonteTelegram.rotear(texto) == ("zara", texto)


@pytest.mark.asyncio
async def test_primeira_mensagem_registra_dono_sem_executar_pelo_adapter(monkeypatch):
    ponte = _ponte(dono=None)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs.get("text", "")) or {"ok": True},
    )

    await ponte._tratar({"message": {"text": "oi", "chat": {"id": 555}}})

    assert ponte.dono == 555
    assert ponte._recebidos == []
    assert any("só você fala" in texto for texto in enviados)


@pytest.mark.asyncio
async def test_mensagem_de_estranho_e_ignorada_em_silencio(monkeypatch):
    ponte = _ponte(dono=555)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs.get("text", "")) or {"ok": True},
    )

    await ponte._tratar({"message": {"text": "apaga tudo", "chat": {"id": 999}}})

    assert ponte._recebidos == []
    assert enviados == []


@pytest.mark.asyncio
async def test_mensagem_vazia_do_dono_nao_vira_comando(monkeypatch):
    ponte = _ponte(dono=555)
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *_args, **_kwargs: {"ok": True})

    await ponte._tratar({"message": {"text": "claude:   ", "chat": {"id": 555}}})

    assert ponte._recebidos == []


@pytest.mark.asyncio
async def test_resposta_grande_e_cortada_antes_do_envio(monkeypatch):
    ponte = _ponte(dono=555)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs["text"]) or {"ok": True},
    )

    assert await ponte.avisar("x" * 9000) is True

    assert len(enviados[0]) < 4096
    assert "no computador" in enviados[0]


def test_token_vazio_ou_placeholder_nao_configura_ponte():
    assert PonteTelegram("", lambda _destino, _texto: None).configurado is False
    assert PonteTelegram("COLE-AQUI-O-TOKEN", lambda _destino, _texto: None).configurado is False
    assert PonteTelegram("123:abc", lambda _destino, _texto: None).configurado is True


@pytest.mark.asyncio
async def test_token_invalido_nao_derruba_a_ponte(monkeypatch):
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *_args, **_kwargs: None)

    assert await _ponte().iniciar() is False


@pytest.mark.asyncio
async def test_mensagem_antiga_avisa_e_nao_executa(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []
    monkeypatch.setattr(ponte, "avisar", lambda texto: enviados.append(texto) or _ok(texto))

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "text": "claude conserta o volume",
                "date": int(time.time()) - 7200,
            }
        }
    )

    assert ponte._recebidos == []
    assert enviados and "não executei" in enviados[0]


@pytest.mark.asyncio
async def test_mensagem_recente_e_executada(monkeypatch):
    ponte = _ponte(dono=7)
    monkeypatch.setattr(ponte, "avisar", lambda texto: _ok(texto))

    await ponte._tratar(
        {"message": {"chat": {"id": 7}, "text": "claude oi", "date": int(time.time())}}
    )

    assert ponte._recebidos == [("claude", "oi")]


@pytest.mark.asyncio
async def test_resposta_igual_e_suprimida_no_intervalo(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs["text"]) or {"ok": True},
    )

    await ponte.avisar("Não consegui: caixa não apareceu.")
    await ponte.avisar("Não consegui: caixa não apareceu.")
    await ponte.avisar("Outra mensagem.")

    assert enviados == ["Não consegui: caixa não apareceu.", "Outra mensagem."]


@pytest.mark.asyncio
async def test_audio_confirma_transcricao_antes_da_resposta(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []
    monkeypatch.setattr(ponte, "avisar", lambda texto: enviados.append(texto) or _ok(texto))
    monkeypatch.setattr(
        "core.telegram_audio.transcrever", lambda _token, _mensagem: ("aumenta o volume", "")
    )

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "voice": {"file_id": "abc"},
                "date": int(time.time()),
            }
        }
    )

    assert ponte._recebidos == [("zara", "aumenta o volume")]
    assert enviados and 'Ouvi: "aumenta o volume"' in enviados[0]


@pytest.mark.asyncio
async def test_erro_de_transcricao_avisa_sem_executar(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []
    monkeypatch.setattr(ponte, "avisar", lambda texto: enviados.append(texto) or _ok(texto))
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda _token, _mensagem: ("", "não consegui ouvir nenhuma fala nesse áudio"),
    )

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "voice": {"file_id": "abc"},
                "date": int(time.time()),
            }
        }
    )

    assert ponte._recebidos == []
    assert enviados and "nenhuma fala" in enviados[0]


@pytest.mark.parametrize(
    "texto,destino,conteudo",
    [
        ("claude: conserta o volume", "claude", "conserta o volume"),
        ("claude conserta o volume", "claude", "conserta o volume"),
        ("codex: roda os testes", "codex", "roda os testes"),
        ("zara: diminui o volume", "zara", "diminui o volume"),
        ("diminui o volume", "zara", "diminui o volume"),
        ("CLAUDE: pode seguir", "claude", "pode seguir"),
        ("codex, tamo so testando a conexao", "codex", "tamo so testando a conexao"),
        ("claude, pode seguir", "claude", "pode seguir"),
        ("zara, aumenta o volume", "zara", "aumenta o volume"),
        ("codex - roda os testes", "codex", "roda os testes"),
        ("claude? ta ai", "claude", "ta ai"),
        ("todos- se voces 3 estao vendo esta mensagem responda sim", "todos", "se voces 3 estao vendo esta mensagem responda sim"),
        ("todo mundo: bom dia", "todos", "bom dia"),
        ("@claude de uma analisada nestes videos", "claude", "de uma analisada nestes videos"),
        ("@codex roda os testes", "codex", "roda os testes"),
        ("@zara, aumenta o volume", "zara", "aumenta o volume"),
        ("@todos: bom dia", "todos", "bom dia"),
    ],
)
def test_roteamento_legado(texto, destino, conteudo):
    assert PonteTelegram.rotear(texto) == (destino, conteudo)


@pytest.mark.parametrize(
    "texto",
    ["codexplorer travou de novo", "zaragoza fica na espanha", "claudete mandou mensagem", "todosanto e uma cidade"],
)
def test_palavra_com_prefixo_parcial_nao_muda_destino(texto):
    assert PonteTelegram.rotear(texto) == ("zara", texto)


@pytest.mark.asyncio
async def test_primeira_mensagem_registra_dono_sem_executar(monkeypatch):
    ponte = _ponte(dono=None)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    await ponte._tratar({"message": {"text": "oi", "chat": {"id": 555}}})

    assert ponte.dono == 555
    assert ponte._recebidos == []
    assert any("só você fala" in texto for texto in enviados)


@pytest.mark.asyncio
async def test_texto_de_estranho_e_ignorado_em_silencio(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    await ponte._tratar({"message": {"text": "zara: apaga tudo", "chat": {"id": 99}}})

    assert ponte._recebidos == []
    assert enviados == []


@pytest.mark.asyncio
async def test_texto_vazio_nao_vira_comando(monkeypatch):
    ponte = _ponte(dono=7)
    monkeypatch.setattr(ponte, "avisar", _ok)

    await ponte._tratar({"message": {"text": "claude:   ", "chat": {"id": 7}}})

    assert ponte._recebidos == []


@pytest.mark.asyncio
async def test_resposta_grande_e_limitada_ao_telegram(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda *_args, **kwargs: enviados.append(kwargs["text"]) or {"ok": True},
    )

    await ponte.avisar("x" * 9000)

    assert len(enviados[0]) < 4096
    assert "no computador" in enviados[0]


def test_token_ausente_ou_placeholder_nao_configura_ponte():
    assert PonteTelegram("", lambda _destino, _texto: None).configurado is False
    assert PonteTelegram("COLE-AQUI-O-TOKEN", lambda _destino, _texto: None).configurado is False
    assert PonteTelegram("123:abc", lambda _destino, _texto: None).configurado is True


@pytest.mark.asyncio
async def test_token_invalido_nao_inicia_laco(monkeypatch):
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *_args, **_kwargs: None)
    assert await _ponte(dono=None).iniciar() is False


@pytest.mark.asyncio
async def test_mensagem_velha_avisa_sem_executar(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    await ponte._tratar(
        {"message": {"chat": {"id": 7}, "text": "claude conserta", "date": int(time.time()) - 7200}}
    )

    assert ponte._recebidos == []
    assert enviados and "não executei" in enviados[0]


@pytest.mark.asyncio
async def test_mensagem_recente_do_dono_e_executada(monkeypatch):
    ponte = _ponte(dono=7)
    monkeypatch.setattr(ponte, "avisar", _ok)

    await ponte._tratar(
        {"message": {"chat": {"id": 7}, "text": "claude oi", "date": int(time.time())}}
    )

    assert ponte._recebidos == [("claude", "oi")]


@pytest.mark.asyncio
async def test_erro_de_transcricao_vira_recado_sem_executar(monkeypatch):
    ponte = _ponte(dono=7)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda _token, _mensagem: ("", "não consegui ouvir nenhuma fala nesse áudio"),
    )
    await ponte._tratar(
        {"message": {"chat": {"id": 7}, "voice": {"file_id": "abc"}, "date": int(time.time())}}
    )

    assert ponte._recebidos == []
    assert enviados and "nenhuma fala" in enviados[0]
