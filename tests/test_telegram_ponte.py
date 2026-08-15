"""ZARA-TELEGRAM-001 — Alex comandando pelo celular.

O risco desta ponte não é ela não funcionar: é ela funcionar para a pessoa
errada. Um bot de Telegram tem nome público; quem descobrir o nome consegue
mandar mensagem. Se a ZARA obedecer a qualquer um, o computador do Alex passa a
aceitar ordens de estranhos.

Por isso o teste mais importante aqui é o de dono, não o de roteamento.
"""
from __future__ import annotations

import time

import pytest

from core.telegram_ponte import PonteTelegram


def _ponte(**kw):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino, texto):
        recebidos.append((destino, texto))
        return "ok"

    p = PonteTelegram(kw.pop("token", "123:abc"), executar, **kw)
    p._recebidos = recebidos
    return p


# ---------- para quem é a mensagem ----------

@pytest.mark.parametrize("texto,destino,conteudo", [
    ("claude: conserta o volume", "claude", "conserta o volume"),
    ("claude conserta o volume", "claude", "conserta o volume"),
    ("codex: roda os testes", "codex", "roda os testes"),
    ("zara: diminui o volume", "zara", "diminui o volume"),
    ("diminui o volume", "zara", "diminui o volume"),
    ("CLAUDE: pode seguir", "claude", "pode seguir"),
    # ZARA-TELEGRAM-ROTEAMENTO-002. Alex escreveu com virgula e a mensagem foi
    # parar na ZARA, que respondeu "nao entendi". Ninguem chama alguem sem virgula.
    ("codex, tamo so testando a conexao", "codex", "tamo so testando a conexao"),
    ("claude, pode seguir", "claude", "pode seguir"),
    ("zara, aumenta o volume", "zara", "aumenta o volume"),
    ("codex - roda os testes", "codex", "roda os testes"),
    ("claude? ta ai", "claude", "ta ai"),
    # E o grupo, que nao existia como destino.
    ("todos- se voces 3 estao vendo esta mensagem responda sim",
     "todos", "se voces 3 estao vendo esta mensagem responda sim"),
    ("todo mundo: bom dia", "todos", "bom dia"),
    # ZARA-TELEGRAM-ROTEAMENTO-003. No Telegram, marcar alguem com @ e o gesto
    # natural. Alex escreveu "@claude de uma analisada nestes videos" e caiu na ZARA.
    ("@claude de uma analisada nestes videos", "claude", "de uma analisada nestes videos"),
    ("@codex roda os testes", "codex", "roda os testes"),
    ("@zara, aumenta o volume", "zara", "aumenta o volume"),
    ("@todos: bom dia", "todos", "bom dia"),
])
def test_roteamento(texto, destino, conteudo):
    assert PonteTelegram.rotear(texto) == (destino, conteudo)


@pytest.mark.parametrize("texto", [
    "codexplorer travou de novo",
    "zaragoza fica na espanha",
    "claudete mandou mensagem",
    "todosanto e uma cidade",
])
def test_palavra_que_so_comeca_igual_nao_vira_destino(texto):
    """Sem isto, "codexplorer" viraria mensagem para o Codex."""
    destino, conteudo = PonteTelegram.rotear(texto)
    assert destino == "zara"
    assert conteudo == texto


# ---------- segurança: só o dono ----------

@pytest.mark.asyncio
async def test_o_primeiro_que_falar_vira_dono(monkeypatch):
    ponte = _ponte()
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar", lambda *a, **k: enviados.append(k.get("text", "")) or {"ok": True}
    )

    await ponte._tratar({"message": {"text": "oi", "chat": {"id": 555}}})

    assert ponte.dono == 555
    assert ponte._recebidos == [], "a primeira mensagem só registra o dono"
    assert any("só você fala" in e for e in enviados)


@pytest.mark.asyncio
async def test_estranho_e_ignorado_em_silencio(monkeypatch):
    """Sem isto, quem descobrisse o nome do bot comandaria o computador dele."""
    ponte = _ponte(dono=555)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar", lambda *a, **k: enviados.append(k.get("text", "")) or {"ok": True}
    )

    await ponte._tratar({"message": {"text": "apaga tudo", "chat": {"id": 999}}})

    assert ponte._recebidos == [], "executou ordem de estranho"
    assert enviados == [], "nem responder para estranho, para não confirmar que o bot existe"


@pytest.mark.asyncio
async def test_o_dono_e_atendido(monkeypatch):
    ponte = _ponte(dono=555)
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *a, **k: {"ok": True})

    await ponte._tratar({"message": {"text": "codex: roda os testes", "chat": {"id": 555}}})

    assert ponte._recebidos == [("codex", "roda os testes")]


# ---------- robustez ----------

@pytest.mark.asyncio
async def test_mensagem_vazia_nao_vira_comando(monkeypatch):
    ponte = _ponte(dono=555)
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *a, **k: {"ok": True})

    await ponte._tratar({"message": {"text": "claude:   ", "chat": {"id": 555}}})

    assert ponte._recebidos == []


@pytest.mark.asyncio
async def test_falha_ao_executar_vira_resposta_honesta(monkeypatch):
    async def explode(destino, texto):
        raise RuntimeError("executor caiu")

    ponte = PonteTelegram("123:abc", explode, dono=555)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar", lambda *a, **k: enviados.append(k.get("text", "")) or {"ok": True}
    )

    await ponte._tratar({"message": {"text": "zara: faz algo", "chat": {"id": 555}}})

    assert any("Não consegui" in e for e in enviados)


@pytest.mark.asyncio
async def test_mensagem_gigante_e_cortada(monkeypatch):
    """O Telegram recusa acima de 4096 caracteres; cortar é melhor que sumir."""
    ponte = _ponte(dono=555)
    enviados: list[str] = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar", lambda *a, **k: enviados.append(k.get("text", "")) or {"ok": True}
    )

    await ponte.avisar("x" * 9000)

    assert len(enviados[0]) < 4096
    assert "no computador" in enviados[0]


def test_sem_token_a_ponte_fica_desligada():
    assert PonteTelegram("", lambda d, t: None).configurado is False
    assert PonteTelegram("COLE-AQUI-O-TOKEN", lambda d, t: None).configurado is False
    assert PonteTelegram("123:abc", lambda d, t: None).configurado is True


@pytest.mark.asyncio
async def test_token_invalido_nao_derruba_a_zara(monkeypatch):
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *a, **k: None)
    ponte = _ponte()

    assert await ponte.iniciar() is False


# ---------- ZARA-TELEGRAM-SEM-REPETICAO-001 ----------
#
# Alex: "a zara ta mandando isso aqui o tempo todo no telegram".
#
# Não eram mensagens diferentes: era a MESMA mensagem dele sendo reexecutada a
# cada abertura da ZARA. O Telegram guarda 24h de mensagens não confirmadas e
# reentrega tudo; o marcador de leitura vivia só na memória e voltava a zero.
# Estes testes existem para esse laço não voltar.


@pytest.mark.asyncio
async def test_mensagem_velha_nao_e_executada(monkeypatch):
    """Pedido de horas atrás não é pedido de agora."""
    ponte = _ponte(dono=7)
    enviados = []
    monkeypatch.setattr(ponte, "avisar", lambda t: enviados.append(t) or _ok())

    await ponte._tratar({
        "update_id": 1,
        "message": {
            "chat": {"id": 7},
            "text": "claude conserta o volume",
            "date": int(time.time()) - 7200,
        },
    })

    assert ponte._recebidos == [], "pedido de horas atrás não pode ser executado sozinho"
    assert enviados and "não executei" in enviados[0], "mas ele precisa saber disso"


@pytest.mark.asyncio
async def test_mensagem_recente_e_executada(monkeypatch):
    """O corte de idade não pode engolir o que ele acabou de mandar."""
    ponte = _ponte(dono=7)
    monkeypatch.setattr(ponte, "avisar", lambda t: _ok())

    await ponte._tratar({
        "update_id": 2,
        "message": {"chat": {"id": 7}, "text": "claude oi", "date": int(time.time())},
    })

    assert ponte._recebidos == [("claude", "oi")]


@pytest.mark.asyncio
async def test_nao_manda_a_mesma_resposta_duas_vezes_seguidas(monkeypatch):
    """Última trava: mesmo que algo dispare duas vezes, ele recebe uma."""
    enviados = []
    monkeypatch.setattr(
        "core.telegram_ponte._chamar",
        lambda token, metodo, **kw: enviados.append(kw.get("text")) or {"ok": True},
    )
    ponte = _ponte(dono=7)

    await ponte.avisar("Não consegui: a caixa não apareceu.")
    await ponte.avisar("Não consegui: a caixa não apareceu.")
    await ponte.avisar("Outra coisa qualquer.")

    assert enviados == ["Não consegui: a caixa não apareceu.", "Outra coisa qualquer."]


@pytest.mark.asyncio
async def test_o_marcador_de_leitura_sobrevive_ao_reinicio(monkeypatch, tmp_path):
    """O motivo real do laço: o marcador voltava a zero e tudo era reentregue."""
    arquivo = tmp_path / "telegram_lido.json"
    monkeypatch.setattr(PonteTelegram, "_arquivo_marcador", staticmethod(lambda: arquivo))

    primeira = _ponte(dono=7)
    primeira._ultimo_update = 4242
    primeira._gravar_marcador()

    depois_do_reinicio = _ponte()
    assert depois_do_reinicio._carregar_marcador() is True
    assert depois_do_reinicio._ultimo_update == 4242
    assert depois_do_reinicio.dono == 7, "o dono também não pode ser esquecido"


# ---------- ZARA-TELEGRAM-AUDIO-001 ----------
#
# Alex: "eu mandei um audio la no bot da zara e ate agora ninguem respondeu".
# A ponte só olhava `text`, então áudio entrava e sumia. Ele prefere falar a
# digitar — uma ponte de celular só-texto obriga justamente o esforço que a
# ZARA existe para eliminar.


@pytest.mark.asyncio
async def test_audio_vira_texto_e_segue_pela_mesma_porta(monkeypatch):
    ponte = _ponte(dono=7)
    enviados = []
    monkeypatch.setattr(ponte, "avisar", lambda t: enviados.append(t) or _ok())
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda token, msg: ("claude pode seguir", ""),
    )

    await ponte._tratar({
        "update_id": 3,
        "message": {
            "chat": {"id": 7},
            "voice": {"file_id": "abc", "duration": 4},
            "date": int(time.time()),
        },
    })

    assert ponte._recebidos == [("claude", "pode seguir")], "áudio tem de rotear igual a texto"


@pytest.mark.asyncio
async def test_ela_mostra_o_que_entendeu_do_audio(monkeypatch):
    """Transcrição errada com resposta confiante executa a coisa errada calado."""
    ponte = _ponte(dono=7)
    enviados = []
    monkeypatch.setattr(ponte, "avisar", lambda t: enviados.append(t) or _ok())
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda token, msg: ("aumenta o volume", ""),
    )

    await ponte._tratar({
        "update_id": 4,
        "message": {
            "chat": {"id": 7},
            "voice": {"file_id": "abc"},
            "date": int(time.time()),
        },
    })

    assert enviados and 'Ouvi: "aumenta o volume"' in enviados[0]


@pytest.mark.asyncio
async def test_falha_na_transcricao_vira_recado_e_nao_silencio(monkeypatch):
    ponte = _ponte(dono=7)
    enviados = []
    monkeypatch.setattr(ponte, "avisar", lambda t: enviados.append(t) or _ok())
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda token, msg: ("", "não consegui ouvir nenhuma fala nesse áudio"),
    )

    await ponte._tratar({
        "update_id": 5,
        "message": {
            "chat": {"id": 7},
            "voice": {"file_id": "abc"},
            "date": int(time.time()),
        },
    })

    assert enviados and "nenhuma fala" in enviados[0]
    assert ponte._recebidos == [], "sem transcrição não se executa nada"


@pytest.mark.asyncio
async def test_audio_de_estranho_nem_e_transcrito(monkeypatch):
    """Transcrever custa token. Estranho não gasta o dele."""
    ponte = _ponte(dono=7)
    chamou = []
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda token, msg: chamou.append(1) or ("oi", ""),
    )

    await ponte._tratar({
        "update_id": 6,
        "message": {
            "chat": {"id": 999},
            "voice": {"file_id": "abc"},
            "date": int(time.time()),
        },
    })

    assert chamou == []
    assert ponte._recebidos == []


async def _ok():
    return True
