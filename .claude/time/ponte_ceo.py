"""Ponte Telegram -> CEO Mentor (aba do Claude Code).

Alex: "consigo criar um canal no telegram direto com o claude onde eu mando msg
e voce rege o time?"

Ele manda do celular, chega na aba do CEO, o CEO rege o time (Voz / Frontend /
Build) e a resposta volta para o celular. Serve para acompanhar de fora de casa.

**Por que um script separado e nao core/telegram_ponte.py.** Aquele arquivo e da
ZARA e pertence a area do agente VOZ. Um escritor por area. Este script e
infraestrutura do time, mora em .claude/time/ e nao entra no build da ZARA.

**Por que um bot proprio.** O Telegram entrega cada mensagem UMA vez so. Se a
ZARA e o CEO escutassem o mesmo bot, um roubaria a mensagem do outro e ela
sumiria sem deixar rastro. Bot separado, marcador separado.

As travas abaixo sao as mesmas que core/telegram_ponte.py aprendeu na pratica —
cada uma existe por um incidente real, nao por precaucao teorica.

Uso:
    python .claude/time/ponte_ceo.py escutar
    python .claude/time/ponte_ceo.py responder "texto"
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
_CHAVES = _RAIZ / "config" / "api_keys.json"
_MARCADOR = _RAIZ / "config" / "telegram_ceo_lido.json"
# ZARA-PONTE-NAO-PERDER-001. Alex: "e como eu faco para esta ponte nao cair mais?"
#
# A ponte cai toda vez que o Claude Code reinicia, e uma mensagem dele sumiu
# nessa queda. O stdout morre junto com a sessao; o disco nao. Toda mensagem e
# gravada aqui ANTES de virar notificacao, entao ao religar da para ler o que
# chegou enquanto o CEO estava morto.
_INBOX = _RAIZ / ".claude" / "time" / "inbox.jsonl"

# ZARA-PONTE-CEO-MORTO-001. Alex: "vou estar no trabalho mais tarde e nao posso
# deixar ela cair de la pq nao tenho acesso ao meu pc aqui."
#
# A ponte sobrevive ao Claude Code (Tarefa Agendada), mas o CEO nao. Longe de
# casa, ele nao tem como saber a diferenca entre "o CEO esta pensando" e "o CEO
# esta morto" — os dois parecem silencio. Entao a propria ponte responde quando
# ninguem esta em casa para responder. Silencio nao pode ser a resposta.
_BATIDA = _RAIZ / ".claude" / "time" / "ceo_vivo.txt"
_CEO_MORTO_APOS = 5 * 60  # segundos sem sinal do CEO ate a ponte assumir
_INTERVALO_AVISO = 15 * 60  # nao repetir o aviso de CEO morto a cada mensagem


def _ceo_vivo_ha() -> float:
    """Segundos desde o ultimo sinal de vida do CEO. Infinito se nunca houve."""
    try:
        return time.time() - _BATIDA.stat().st_mtime
    except Exception:
        return float("inf")


def _bater_ponto() -> None:
    """O CEO marca presenca. Chamado toda vez que ele responde."""
    try:
        _BATIDA.parent.mkdir(parents=True, exist_ok=True)
        _BATIDA.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    except Exception:
        pass

_API = "https://api.telegram.org/bot{token}/{metodo}"
_ESPERA_LONGA = 25      # segundos que o Telegram segura a conexao esperando
_LIMITE_MENSAGEM = 3500  # o Telegram corta em 4096; folga para o prefixo
_IDADE_MAXIMA = 60 * 60  # mensagem mais velha que isso nao acorda ninguem


def _dizer(texto: str) -> None:
    """Imprime se houver para onde imprimir. Sob pythonw.exe nao ha stdout, e a
    ponte tem de continuar viva mesmo sem ninguem lendo."""
    try:
        print(texto, flush=True)
    except Exception:
        pass


def _chamar(token: str, metodo: str, **parametros) -> dict | None:
    """Uma chamada a API do Telegram. Devolve None em qualquer falha.

    Falha de rede nao pode matar a ponte: o Monitor a manteria morta em
    silencio, e silencio e indistinguivel de "nada aconteceu".
    """
    url = _API.format(token=token, metodo=metodo)
    dados = urllib.parse.urlencode(
        {k: v for k, v in parametros.items() if v is not None}
    ).encode()
    try:
        with urllib.request.urlopen(url, data=dados, timeout=_ESPERA_LONGA + 10) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return corpo if corpo.get("ok") else None


def _token() -> str:
    """Le o token de config/api_keys.json. E o unico lugar de chave do projeto."""
    try:
        dados = json.loads(_CHAVES.read_text(encoding="utf-8"))
    except Exception:
        return ""
    token = str(dados.get("telegram_ceo_token") or "").strip()
    return "" if "COLE" in token.upper() else token


def _ler_marcador() -> dict:
    try:
        return json.loads(_MARCADOR.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_marcador(ultimo: int, dono: int | None) -> None:
    try:
        _MARCADOR.parent.mkdir(parents=True, exist_ok=True)
        _MARCADOR.write_text(
            json.dumps({"ultimo_update": ultimo, "dono": dono}), encoding="utf-8"
        )
    except Exception:
        pass  # perder o marcador atrasa, nao quebra


def _pular_acumulado(token: str) -> int:
    """Primeira vez de todas: descarta o que esta represado no Telegram.

    Sem isso, tudo que ele mandou antes da ponte existir chega de uma vez e o
    CEO trata como pedido de agora.
    """
    ultimo = 0
    pacote = _chamar(token, "getUpdates", offset=-1, timeout=0)
    for update in (pacote or {}).get("result") or []:
        ultimo = max(ultimo, int(update.get("update_id", 0)))
    if ultimo:
        _chamar(token, "getUpdates", offset=ultimo + 1, timeout=0)
    return ultimo


def _guardar_na_fila(texto: str) -> None:
    """Grava a mensagem em disco antes de virar notificacao.

    Se a ponte cair entre a gravacao e a leitura, a mensagem continua aqui.
    Falha de escrita nao pode derrubar a ponte: perder o registro e ruim,
    perder a ponte inteira e pior.
    """
    try:
        _INBOX.parent.mkdir(parents=True, exist_ok=True)
        linha = json.dumps(
            {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "texto": texto},
            ensure_ascii=False,
        )
        with _INBOX.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")
    except Exception:
        pass


def _sou_o_unico() -> object | None:
    """Trava de instancia unica. Devolve o socket segurando a vaga, ou None.

    Duas pontes no mesmo bot e pior que nenhuma: o Telegram entrega cada
    mensagem UMA vez, entao elas repartem as mensagens dele ao acaso e cada uma
    responde metade da conversa. Ja aconteceu — o .bat da inicializacao e um
    lancamento manual subiram juntos.

    Uma porta local resolve melhor que um arquivo de PID: o sistema operacional
    a devolve sozinho quando o processo morre, entao nao existe trava orfa.
    """
    import socket

    trava = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        trava.bind(("127.0.0.1", 47821))
        trava.listen(1)
    except OSError:
        trava.close()
        return None
    return trava


def escutar() -> int:
    """Long polling. Cada mensagem do Alex vira uma linha no stdout.

    O Monitor do Claude Code transforma cada linha numa notificacao que acorda
    a aba do CEO. Nada entra no computador por iniciativa de fora: e a ponte que
    pergunta ao Telegram se ha mensagem nova.
    """
    trava = _sou_o_unico()
    if trava is None:
        _dizer("[PONTE] ja existe uma ponte rodando; esta instancia sai sem tocar no Telegram")
        return 0

    token = _token()
    if not token:
        _dizer("[PONTE] sem token: falta telegram_ceo_token em config/api_keys.json")
        return 1

    eu = _chamar(token, "getMe")
    if not eu:
        _dizer("[PONTE] token recusado pelo Telegram; ponte nao ligou")
        return 1
    nome = (eu.get("result") or {}).get("username", "?")

    marcador = _ler_marcador()
    dono = marcador.get("dono")
    if marcador:
        ultimo = int(marcador.get("ultimo_update") or 0)
    else:
        # Vale o ARQUIVO existir, nao o numero ser maior que zero. Caixa vazia
        # na primeira abertura deixaria o marcador em 0 e toda abertura seguinte
        # seria tratada como a primeira.
        ultimo = _pular_acumulado(token)
        _gravar_marcador(ultimo, dono)

    _dizer(f"[PONTE] ligada como @{nome} — mande a primeira mensagem")

    ultimo_aviso = 0.0
    while True:
        pacote = _chamar(token, "getUpdates", offset=ultimo + 1, timeout=_ESPERA_LONGA)
        if pacote is None:
            time.sleep(3)  # queda de rede: espera e tenta de novo, sem morrer
            continue

        for update in pacote.get("result") or []:
            ultimo = max(ultimo, int(update.get("update_id", 0)))
            mensagem = update.get("message") or update.get("edited_message") or {}
            texto = str(mensagem.get("text") or "").strip()
            chat = (mensagem.get("chat") or {}).get("id")
            if not texto or chat is None:
                continue

            # So o dono fala. Sem isso, quem descobrisse o nome do bot teria o
            # CEO — e o CEO comanda quem escreve no codigo.
            if dono is None:
                dono = int(chat)
            elif int(chat) != int(dono):
                continue

            # Mensagem velha nao acorda ninguem, mesmo que o Telegram a
            # reentregue depois de 24h represada.
            if time.time() - int(mensagem.get("date") or 0) > _IDADE_MAXIMA:
                continue

            _guardar_na_fila(texto)
            _dizer(f"[ALEX] {texto}")
            _gravar_marcador(ultimo, dono)

            # Ninguem em casa: a ponte responde no lugar do CEO, uma vez por
            # janela. Guardada na fila, a mensagem sera lida quando ele voltar.
            if _ceo_vivo_ha() > _CEO_MORTO_APOS:
                if time.time() - ultimo_aviso > _INTERVALO_AVISO:
                    ultimo_aviso = time.time()
                    _chamar(
                        token,
                        "sendMessage",
                        chat_id=dono,
                        text=(
                            "Recebi e guardei, mas o CEO esta fora do ar agora "
                            "(Claude Code fechado no PC de casa).\n\n"
                            "Sua mensagem nao se perdeu. Ele le assim que voltar."
                        ),
                    )

        _gravar_marcador(ultimo, dono)


def responder(texto: str) -> int:
    """Manda a resposta do CEO para o celular do Alex."""
    token = _token()
    dono = _ler_marcador().get("dono")
    if not token or not dono:
        print("[PONTE] sem token ou sem dono; rode 'escutar' e mande uma mensagem antes")
        return 1
    corpo = str(texto or "").strip()
    if not corpo:
        return 1
    if len(corpo) > _LIMITE_MENSAGEM:
        corpo = corpo[:_LIMITE_MENSAGEM] + "\n\n[...] o resto esta no computador."
    ok = _chamar(token, "sendMessage", chat_id=dono, text=corpo)
    if ok:
        _bater_ponto()  # o CEO respondeu, logo o CEO esta vivo
    print("enviado" if ok else "falhou ao enviar")
    return 0 if ok else 1


def fila(quantas: int = 20) -> int:
    """Mostra as ultimas mensagens recebidas. E a primeira coisa que o CEO roda
    ao religar: sem isso ele responderia a ultima mensagem como se fosse a
    unica, ignorando tudo que chegou durante a queda.

    Nao apaga nada de proposito. Quem escuta em tempo real segue este mesmo
    arquivo; apagar aqui cegaria a escuta.
    """
    try:
        linhas = _INBOX.read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        print("fila vazia")
        return 0
    for linha in linhas[-quantas:]:
        try:
            item = json.loads(linha)
            print(f"{item['quando']}  {item['texto']}")
        except Exception:
            continue
    print(f"--- {len(linhas)} no total; ultimo sinal do CEO ha {_ceo_vivo_ha():.0f}s")
    return 0


if __name__ == "__main__":
    # Sob pythonw.exe (a ponte rodando por fora do Claude Code, sem janela) nao
    # existe stdout: sys.stdout e None e qualquer print derruba o processo na
    # primeira linha. A ponte precisa viver sem ninguem escutando — quem guarda
    # a mensagem e o inbox.jsonl, nao a tela.
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    comando = sys.argv[1] if len(sys.argv) > 1 else "escutar"
    if comando == "responder":
        raise SystemExit(responder(" ".join(sys.argv[2:])))
    if comando == "fila":
        raise SystemExit(fila())
    raise SystemExit(escutar())
