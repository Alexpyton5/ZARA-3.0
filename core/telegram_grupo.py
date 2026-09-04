"""ZARA-TELEGRAM-GRUPO-001 — a equipe conversando com a ZARA pelo grupo.

Até aqui a ponte do Telegram só obedecia ao dono (chat privado do Alex):
qualquer mensagem de grupo era ignorada em silêncio. O Alex quer o bot
@zara_project_group_bot dentro do grupo do projeto, onde ele e a equipe falam
com a ZARA, o Codex, o Claude ou com todos de uma vez.

O risco da ponte continua sendo o mesmo da ponte privada: um bot de Telegram
tem nome público, e quem descobrir o nome consegue mandar mensagem. Por isso
esta ponte NÃO aceita "qualquer grupo" — ela só atende o grupo cujo id está
salvo em config (``telegram_group_id``). Um grupo diferente é ignorado em
silêncio, exatamente como um estranho no privado.

Tudo o que já era seguro na ponte privada se mantém aqui: o marcador de leitura
vive em disco (não repete mensagem antiga), mensagem com mais de 1h não se
executa sozinha, e a mesma resposta não é enviada duas vezes seguidas.

Roteamento (idêntico ao privado, reutilizado):
    claude: ...  -> Claude Code
    codex: ...   -> Codex
    zara: ...    -> própria ZARA
    todos: ...   -> os três acima, um por um
    sem prefixo -> própria ZARA
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from core.telegram_ponte import _IDADE_MAXIMA, PonteTelegram, _chamar


class PonteGrupo(PonteTelegram):
    """Ponte que atende um grupo autorizado (em vez de um dono privado).

    Herda toda a robustez da PonteTelegram (marcador de leitura em disco,
    trava de idade, anti-repetição) e só troca a regra de autorização: em vez
    de "o primeiro que falar vira dono", ela só responde ao grupo cujo id está
    em ``grupo_id``.
    """

    def __init__(
        self,
        token: str,
        executar: Callable[[str, str], Awaitable[str]],
        *,
        grupo_id: int | None = None,
        dono_privado: int | None = None,
    ):
        super().__init__(token, executar, dono=grupo_id)
        # Nome explícito para ficar claro que é o grupo, não o dono privado.
        self.grupo_id = grupo_id
        # ZARA-TELEGRAM-GRUPO-002. O mesmo bot que entra no grupo também pode
        # ser usado no privado do Alex (ele já manda mensagem por lá). Sem isso
        # o bot novo ficaria mudo no privado até entrar num grupo.
        self.dono_privado = dono_privado

    # ------------------------------------------------------------------
    @staticmethod
    def _arquivo_marcador() -> Path | None:
        try:
            from core.paths import config_dir

            return config_dir() / "telegram_grupo_lido.json"
        except Exception:
            return None

    async def iniciar(self) -> bool:
        if not self.configurado or self._tarefa is not None:
            return False
        # Precisa de ao menos um alvo autorizado: o grupo ou o privado do Alex.
        if self.grupo_id is None and self.dono_privado is None:
            print("[TELEGRAM-GRUPO] sem grupo nem dono privado; ponte nao ligou", flush=True)
            return False
        eu = await asyncio.to_thread(_chamar, self.token, "getMe")
        if not eu:
            print("[TELEGRAM-GRUPO] token recusado pelo Telegram; ponte nao ligou", flush=True)
            return False
        nome = (eu.get("result") or {}).get("username", "?")
        if not self._carregar_marcador():
            await asyncio.to_thread(self._pular_acumulado)
        self._parar.clear()
        self._ultimo_sucesso = time.time()
        self._tarefa = asyncio.create_task(self._escutar(), name="zara-telegram-grupo")
        alvo = f"grupo {self.grupo_id}" if self.grupo_id is not None else f"privado {self.dono_privado}"
        print(
            f"[TELEGRAM-GRUPO] ponte ligada como @{nome} ({alvo}, "
            f"a partir de {self._ultimo_update})",
            flush=True,
        )
        return True

    # ------------------------------------------------------------------
    async def _tratar(self, update: dict) -> None:
        mensagem = update.get("message") or update.get("edited_message") or {}
        texto = str(mensagem.get("text") or "").strip()
        chat = (mensagem.get("chat") or {}).get("id")
        tipo_chat = (mensagem.get("chat") or {}).get("type", "")

        # Só grupo autorizado (ou o privado do Alex, se configurado). Qualquer
        # outro chat é ignorado em silêncio — não confirma nem que o bot existe.
        autorizado = False
        if self.grupo_id is not None and chat is not None and int(chat) == int(self.grupo_id):
            # O Telegram pode entregar de canal; segurança em cima do id.
            if not tipo_chat or tipo_chat in ("group", "supergroup"):
                autorizado = True
        if (
            not autorizado
            and self.dono_privado is not None
            and chat is not None
            and int(chat) == int(self.dono_privado)
            and (not tipo_chat or tipo_chat == "private")
        ):
            autorizado = True
        if not autorizado:
            return

        # ZARA-TELEGRAM-AUDIO-001 reaproveitado: áudio do grupo vira texto.
        transcrito = False
        if not texto and (mensagem.get("voice") or mensagem.get("audio")):
            from core.telegram_audio import transcrever

            texto, erro = await asyncio.to_thread(transcrever, self.token, mensagem)
            if erro:
                await self.avisar(f"Ouvi seu áudio mas {erro}.")
                return
            transcrito = True
            print(f"[TELEGRAM-GRUPO] audio transcrito: {texto[:60]!r}", flush=True)

        if not texto or chat is None:
            return

        # ZARA-TELEGRAM-SEM-REPETICAO-001 reaproveitado: mensagem velha não
        # executa sozinha (o estado do computador mudou desde então).
        quando = int(mensagem.get("date") or 0)
        atraso = time.time() - quando if quando else 0
        if atraso > _IDADE_MAXIMA:
            print(f"[TELEGRAM-GRUPO] mensagem antiga ({int(atraso)}s) nao executada", flush=True)
            horas = int(atraso // 3600)
            await self.avisar(
                f'Vi sua mensagem de {horas}h atrás ("{texto[:60]}"), mas não executei — '
                "muita coisa mudou desde então. Se ainda vale, é só repetir."
            )
            return

        destino, conteudo = self.rotear(texto)
        if not conteudo:
            await self.avisar("Chegou vazio. Manda o que você quer.")
            return

        try:
            resposta = await self.executar(destino, conteudo)
        except Exception as exc:
            resposta = f"Não consegui: {type(exc).__name__}"

        resposta = resposta or "Feito."
        if transcrito:
            resposta = f'Ouvi: "{texto}"\n\n{resposta}'
        await self.avisar(resposta)
