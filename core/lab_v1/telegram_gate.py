"""ZARA-TELEGRAM-LAB-GATE-001 — Alex aprova ou restaura uma atualização do Lab pelo celular.

Alex mandou mensagem para o bot e não veio resposta nenhuma: nada da ZARA estava
escutando o Telegram. Este módulo fecha essa lacuna especificamente para o Lab —
avisar quando uma atualização candidata está pronta e aplicar (ou reverter) só
com autorização explícita dele, do jeito que `.claude/rules/physical-validation.md`
e `.claude/rules/evidence.md` exigem: sem fabricar "consertado" sem executor, sem
promover nada sem SIM humano, sem jamais aceitar instrução vinda de dentro de uma
mensagem recebida.

Este módulo NUNCA escreve um segundo mecanismo de reversão ou de decisão de
prontidão. Toda a máquina de promoção — ativar, checar saúde, reverter, decidir
se um candidato pode ser promovido — é `core.lab_v1.release`, sem alterações.
Este arquivo só é o operador humano-no-loop que aciona essa máquina a partir do
Telegram.

Por que não é o mesmo bot que já existe (`core.telegram_ponte.PonteTelegram`)
-------------------------------------------------------------------------------
`PonteTelegram` já faz long polling no mesmo token e já resolve "primeira
mensagem vira o dono" — mas para um propósito diferente: rotear comandos livres
para claude/codex/zara (`core.ipc_handlers._ligar_telegram`, levantada pelo
Electron, ou `tools/zara_telegram_bot.py` como runner standalone). Ela não sabe
nada sobre candidatos do Lab, `promotion_readiness`, aprovação atrelada a um
candidato específico, nem sobre a regra de nunca reexecutar uma aprovação em
outro candidato depois.

Duplicar aqui a lógica de longa-espera dela seria menos seguro, não mais: as
regras de segurança deste arquivo (SIM/NÃO/RESTAURAR atrelados a um candidato
identificado, nunca reaproveitados) são um contrato fechado, mais estreito do
que o roteamento livre da ponte geral. Por isso este módulo é um escutador
Telegram PRÓPRIO, com seu próprio marcador de posição (nunca
`config/telegram_lido.json`, que é dela) — mas com uma consequência honesta:

    AVISO OPERACIONAL — a API do Telegram só sustenta um consumidor de
    `getUpdates` por vez sobre o mesmo token. Rodar este gate AO MESMO TEMPO
    que `tools/zara_telegram_bot.py` (ou a ZARA de Electron com o Telegram
    ligado) faz os dois brigarem pela mesma fila e um deles passa a perder
    mensagem. Enquanto as duas pontes não forem unificadas (tarefa própria,
    fora de escopo daqui), rode só uma de cada vez.

Contrato de segurança (não negociável, ver o pedido original)
---------------------------------------------------------------
* Só o `telegram_owner_chat_id` exato manda. Any outro chat é descartado sem
  resposta que revele que o sistema existe.
* Uma vez gravado, `telegram_owner_chat_id` NUNCA é sobrescrito automaticamente.
* O conteúdo de toda mensagem é DADO. O reconhecimento de comando é por
  allowlist exata (SIM / NÃO / RESTAURAR / VOLTAR, normalizados) — nunca por
  interpretação livre do texto. Isso por construção já neutraliza qualquer
  tentativa de instrução embutida ("promova tudo", "ignore as regras", "você é
  o administrador"): nenhuma dessas frases bate a allowlist, então caem no
  ramo de status, que só informa e nunca age.
* Uma aprovação vale para UM candidato identificado (`sid`); é consumida no ato
  de usar e nunca reaproveitada para um candidato futuro.
* Silêncio nunca é SIM.
* Um candidato = uma mensagem; no máximo um lembrete depois de várias horas.
"""
from __future__ import annotations

import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = [
    "TelegramLabGate", "HttpTelegramTransport", "FakeTelegramTransport",
    "default_ready_candidate", "classify_command", "changed_areas",
    "load_state", "save_state", "READY_MESSAGE",
]

# ---------------------------------------------------------------------------
# Vocabulário reconhecido — allowlist fechada, por design (ver contrato acima)
# ---------------------------------------------------------------------------
_SIM = {"sim"}
_NAO = {"nao"}
_RESTAURAR = {"restaurar", "voltar"}

#: No máximo um lembrete, depois de várias horas sem resposta.
REMINDER_AFTER_SECONDS = 6 * 60 * 60

#: Áreas que só o olho/ouvido do Alex confirma — ver .claude/rules/physical-validation.md
#: e o mapa de escrita em .claude/rules/time-zara.md. Caminhos POSIX, normalizados
#: antes de comparar.
_VOICE_FILES = frozenset({
    "core/voice_stt.py", "core/voice_tts.py", "core/gemini_live_voice.py",
})
_AUDIO_FILES = frozenset({
    "frontend/src/renderer/lib/aecaudio.ts", "core/windows_audio.py",
})
_INTERFACE_PREFIX = "frontend/src/"

READY_MESSAGE = (
    "A ZARA tem uma atualização pronta. Já foi testada e revisada antes de "
    "chegar até aqui.\n\nResponda SIM para aplicar, ou NÃO para deixar como está."
)


# ---------------------------------------------------------------------------
# Normalização e classificação de comando — sem interpretação livre de texto
# ---------------------------------------------------------------------------
def _fold(text: Any) -> str:
    """Minúsculas, sem acento, sem pontuação nas bordas, espaços colapsados."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(stripped.split()).strip(" .!?,;:-").casefold()


def classify_command(text: Any) -> str:
    """Devolve 'SIM' / 'NAO' / 'RESTAURAR' / 'UNKNOWN'.

    Allowlist exata e fechada — de propósito. Qualquer frase que não seja
    EXATAMENTE uma destas palavras (normalizada) cai em 'UNKNOWN', que é o
    ramo que só informa e nunca executa nada. Isso é a defesa contra conteúdo
    malicioso: não existe caminho de código onde o TEXTO da mensagem decide
    o que fazer além de citar uma destas quatro palavras.
    """
    folded = _fold(text)
    if folded in _SIM:
        return "SIM"
    if folded in _NAO:
        return "NAO"
    if folded in _RESTAURAR:
        return "RESTAURAR"
    return "UNKNOWN"


def changed_areas(paths: Any) -> set[str]:
    """Classifica os caminhos alterados em {'voice', 'audio', 'interface'}.

    Evidência real (lista de arquivos que a missão declarou como escopo),
    nunca heurística de string sobre o texto livre da missão — como o pedido
    exige.
    """
    areas: set[str] = set()
    for raw in paths or ():
        normalized = str(raw).replace("\\", "/").lstrip("./").casefold()
        if normalized in _VOICE_FILES:
            areas.add("voice")
        elif normalized in _AUDIO_FILES:
            areas.add("audio")
        elif normalized.startswith(_INTERFACE_PREFIX):
            areas.add("interface")
    return areas


def _physical_message(areas: set[str]) -> str:
    if "voice" in areas:
        parte = "uma mudança na voz da ZARA"
    elif "audio" in areas:
        parte = "uma mudança no microfone/áudio"
    else:
        parte = "uma mudança na tela"
    return (
        f"Tem {parte} pronta. Isso só dá para confirmar vendo ou ouvindo — "
        "preciso que você teste na frente do computador quando puder. "
        "Não é para responder SIM/NÃO agora."
    )


# ---------------------------------------------------------------------------
# Estado persistido — só o offset do Telegram, o pedido pendente e o
# histórico de candidatos já tratados. O dono fica em config/api_keys.json
# (campo designado pelo próprio pedido), nunca duplicado aqui.
# ---------------------------------------------------------------------------
def _default_state() -> dict:
    return {"last_update_id": 0, "pending": None, "handled": {}}


def load_state(path: Path) -> dict:
    path = Path(path)
    state = _default_state()
    if not path.is_file():
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if isinstance(data, dict):
        for key in state:
            if key in data:
                state[key] = data[key]
    return state


def save_state(path: Path, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Transporte HTTP — isolado atrás de uma interface simples para o teste trocar
# por um fake. Nunca loga o token.
# ---------------------------------------------------------------------------
class HttpTelegramTransport:
    """Chamadas reais à API do Telegram, via urllib (sem dependência nova)."""

    def __init__(self, token: str):
        self._token = str(token or "").strip()

    def get_updates(self, offset: int, timeout: int = 0) -> list[dict]:
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        data = urllib.parse.urlencode({"offset": offset, "timeout": timeout}).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=timeout + 15) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return []
        return list(body.get("result") or []) if body.get("ok") else []

    def send_message(self, chat_id: int, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return False
        return bool(body.get("ok"))

    def get_me(self) -> dict | None:
        url = f"https://api.telegram.org/bot{self._token}/getMe"
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        return body.get("result") if body.get("ok") else None


class FakeTelegramTransport:
    """Seam de teste: fila de updates em memória, nenhuma chamada de rede."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self._updates: list[dict] = []
        self._next_update_id = 1

    def push_message(self, chat_id: int, text: str) -> None:
        self._updates.append({
            "update_id": self._next_update_id,
            "message": {"chat": {"id": chat_id}, "text": text, "date": int(time.time())},
        })
        self._next_update_id += 1

    def get_updates(self, offset: int, timeout: int = 0) -> list[dict]:
        return [u for u in self._updates if u["update_id"] >= offset]

    def send_message(self, chat_id: int, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


# ---------------------------------------------------------------------------
# Descoberta do candidato pronto — leitura pura, nunca instancia SourceMission
# (o construtor dela pode retomar um candidato em sandbox como efeito
# colateral via CandidateSource.resume()). Só lê o documento que
# SourceMission.report() já persistiu via save_meta(promotion_gate=...).
# ---------------------------------------------------------------------------
def default_ready_candidate(store) -> dict | None:
    """Primeiro candidato cujo `promotion_gate` já persistido está ELIGIBLE.

    Leitura somente-SELECT na tabela `mission_autonomy`; nunca escreve, nunca
    constrói `SourceMission`. A elegibilidade é sempre reconferida do zero por
    `promotion_readiness` no momento em que SIM realmente tenta promover (ver
    `TelegramLabGate._approve_pending`) — esta função só decide se vale a pena
    mandar o aviso, nunca decide se pode promover.
    """
    try:
        with store._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mission_autonomy'"
            ).fetchone()
            if not exists:
                return None
            rows = conn.execute("SELECT session_id, document FROM mission_autonomy").fetchall()
    except Exception:
        return None
    for sid, raw in rows:
        try:
            document = json.loads(raw)
        except (TypeError, ValueError):
            continue
        source_work = (document or {}).get("source_work") or {}
        gate = source_work.get("promotion_gate") or {}
        if gate.get("state") != "ELIGIBLE":
            continue
        receipt = gate.get("candidate")
        workspace = source_work.get("workspace")
        if not isinstance(receipt, dict) or not workspace:
            continue
        return {"sid": sid, "receipt": receipt, "workspace": workspace,
                "source_paths": list(source_work.get("source_paths") or [])}
    return None


def _default_release_module():
    from core.lab_v1 import release
    return release


# ---------------------------------------------------------------------------
# O portão em si
# ---------------------------------------------------------------------------
class TelegramLabGate:
    """Escuta o Telegram, protege por chat_id e opera a máquina de release.py.

    Toda dependência de efeito colateral (transporte HTTP, fábrica da
    ReleaseQueue, fonte do candidato pronto, módulo de release, relógio) é
    injetada — é o que permite testar a decisão real (allowlist de comando,
    trava de dono, consumo de aprovação, classificação de área) sem tocar
    rede nem o banco real do Lab.
    """

    def __init__(
        self,
        *,
        transport,
        state_path,
        api_keys_path,
        candidate_source: Callable[[], dict | None],
        queue_factory: Callable[[], Any],
        release_module=None,
        build=None,
        now: Callable[[], float] = time.time,
    ):
        self.transport = transport
        self.state_path = Path(state_path)
        self.api_keys_path = Path(api_keys_path)
        self.candidate_source = candidate_source
        self.queue_factory = queue_factory
        self.release = release_module or _default_release_module()
        self.build = build
        self._now = now
        self._state = load_state(self.state_path)

    # -- estado -----------------------------------------------------------
    def _save_state(self) -> None:
        save_state(self.state_path, self._state)

    # -- dono (config/api_keys.json::telegram_owner_chat_id) --------------
    def _current_owner(self) -> int | None:
        value = _read_json(self.api_keys_path).get("telegram_owner_chat_id")
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    def _link_owner(self, chat_id: int) -> None:
        """Primeira mensagem de sempre: grava o dono. Nunca sobrescreve depois."""
        data = _read_json(self.api_keys_path)
        if data.get("telegram_owner_chat_id"):
            # Alguém correu na frente entre a leitura de _current_owner e
            # aqui (ou o valor já existia); a regra dura é nunca sobrescrever.
            return
        data["telegram_owner_chat_id"] = int(chat_id)
        _write_json_atomic(self.api_keys_path, data)
        self._send(chat_id, (
            "Pronto! A partir de agora, só respondo a você por aqui sobre as "
            "atualizações da ZARA."
        ))

    # -- envio --------------------------------------------------------------
    def _send(self, chat_id: int, text: str) -> None:
        try:
            self.transport.send_message(chat_id, text)
        except Exception as exc:  # nunca derruba o laço por falha de rede
            print(f"[LAB-TELEGRAM] falha ao responder: {type(exc).__name__}: {exc}", flush=True)

    # -- ciclo de leitura -----------------------------------------------------
    def poll_once(self, timeout: int = 0) -> None:
        try:
            updates = self.transport.get_updates(self._state["last_update_id"] + 1, timeout=timeout)
        except Exception as exc:
            print(f"[LAB-TELEGRAM] getUpdates falhou: {type(exc).__name__}: {exc}", flush=True)
            return
        for update in updates or []:
            update_id = update.get("update_id")
            if update_id is not None:
                self._state["last_update_id"] = max(self._state["last_update_id"], int(update_id))
                self._save_state()  # confirma ANTES de tratar: falha não repete a mesma mensagem
            message = update.get("message") or update.get("edited_message") or {}
            text = str(message.get("text") or "").strip()
            chat = (message.get("chat") or {}).get("id")
            if not text or chat is None:
                continue
            self._process_text_message(int(chat), text)

    def _dispatch_command(self, command: str) -> str:
        """Decide a resposta para um comando já classificado.

        Função pura sobre o estado do gate (sem tocar rede) — é o que sobra
        depois de separar "decidir o que fazer" de "escutar o Telegram".
        Reusada tanto pelo runner standalone (`_process_text_message`, via
        `poll_once`/`run_forever`) quanto por quem incorpora o gate como
        biblioteca (`handle_message`, ver ZARA-TELEGRAM-LAB-BRIDGE-001).
        """
        if command == "SIM":
            return self._approve_pending()
        if command == "NAO":
            return self._refuse_pending()
        if command == "RESTAURAR":
            return self._restore_last_known_good()
        return self._status_reply()

    def _process_text_message(self, chat_id: int, text: str) -> None:
        owner = self._current_owner()
        if owner is None:
            self._link_owner(chat_id)
            return
        if int(chat_id) != int(owner):
            # Descartada, registrada em log, NUNCA executada — e nenhuma
            # resposta que confirme para um estranho que o sistema existe.
            print(f"[LAB-TELEGRAM] mensagem de chat nao autorizado ignorada: {chat_id}", flush=True)
            return
        self._send(owner, self._dispatch_command(classify_command(text)))

    # -- biblioteca para quem já tem o PRÓPRIO escutador de Telegram --------
    #
    # ZARA-TELEGRAM-LAB-BRIDGE-001
    #
    # Este gate nasceu com seu próprio laço de polling (`run_forever`) porque,
    # rodando sozinho (`tools/run_lab_telegram_gate.py`), não havia outra
    # opção. Mas empacotado junto da ZARA, já existe `core.telegram_ponte.
    # PonteTelegram` fazendo long polling no MESMO token para outro propósito
    # (rotear claude:/codex:/zara:). A API do Telegram só sustenta UM
    # consumidor de getUpdates por vez sobre um token — então dois laços
    # brigando pela mesma fila fazem os dois perderem mensagem de forma
    # intermitente. A decisão (ver DECISIONS.md) foi: só a ponte que já sobe
    # com a ZARA consome getUpdates; este gate vira biblioteca chamada por
    # ela para decidir "isto é um comando do Lab?", sem loop próprio.
    def handle_message(self, chat_id: int, text: str) -> str | None:
        """Devolve a resposta do Lab para esta mensagem, ou None se não for
        um comando do Lab (a mensagem deve seguir pelo caminho normal de
        quem chamou).

        Só responde quando: `telegram_owner_chat_id` já está gravado em
        `config/api_keys.json`, a mensagem vem exatamente desse chat_id, e o
        texto é EXATAMENTE SIM / NÃO / RESTAURAR / VOLTAR (a allowlist
        fechada de `classify_command` — nunca interpretação livre do texto).
        Qualquer outra coisa — chat errado, dono ainda não vinculado, texto
        que não bate a allowlist — devolve None: não é uma recusa, é "isto
        não é comigo", para o chamador tratar como sempre tratou.

        Nunca faz a vinculação automática de dono aqui (`_link_owner`) — isso
        é papel do runner standalone. Enquanto `telegram_owner_chat_id` não
        existir, o gate fica inativo por construção, e quem chama recebe
        None e segue normalmente (é assim que a ZARA sobe sem erro mesmo sem
        o Lab estar configurado).
        """
        owner = self._current_owner()
        if owner is None or int(chat_id) != int(owner):
            return None
        command = classify_command(text)
        if command == "UNKNOWN":
            return None
        return self._dispatch_command(command)

    # -- comandos -----------------------------------------------------------
    def _clear_pending(self, sid: str, status: str) -> None:
        handled = self._state.setdefault("handled", {})
        handled[sid] = {"status": status, "at": self._now()}
        self._state["pending"] = None
        self._save_state()

    def _approve_pending(self) -> str:
        pending = self._state.get("pending")
        if not pending or pending.get("kind") != "promotion":
            return self._status_reply()
        sid = pending["sid"]
        receipt = pending["receipt"]
        workspace = pending["workspace"]
        # Consumida no ato: mesmo que a promoção falhe ou demore, este SIM já
        # não serve para nenhum outro candidato depois.
        self._clear_pending(sid, status="approved")
        readiness = self.release.promotion_readiness(receipt, workspace, self.build)
        if not readiness.get("eligible"):
            return (
                "Não consegui aplicar — isso não está mais disponível "
                f"({readiness.get('reason')}). Nada foi mudado."
            )
        try:
            queue = self.queue_factory()
            queue.schedule_source_candidate(sid, receipt, workspace)
            queue.package_ready(sid, receipt["package"], {
                "BUILD_ID": receipt.get("build_id"),
                "SOURCE_SHA256": receipt.get("source_sha256"),
                "ASAR_SHA256": receipt.get("asar_sha256"),
                "BACKEND_SHA256": receipt.get("backend_sha256"),
            })
            queue.accept_canary(sid, receipt["canary_report"])
            promotion = self.release.SourcePromotion(workspace, receipt, build=self.build)
            doc = queue.promote(
                sid,
                activate=promotion.activate,
                monitor=promotion.health,
                rollback=promotion.rollback,
                commit=promotion.commit,
            )
        except Exception as exc:
            return (
                f"Tentei aplicar, mas deu um problema ({type(exc).__name__}). "
                "Se algo chegou a mudar, a trava de segurança já devolveu o estado anterior."
            )
        state = doc.get("state")
        if state == "ACTIVE":
            return "Prontinho! Apliquei a atualização. Testei antes e continua funcionando depois."
        if state == "ROLLED_BACK":
            return (
                "Tentei aplicar, mas a checagem de segurança não passou — voltei tudo "
                "para como estava antes. Nada mudou pra pior."
            )
        return (
            f"Não terminou como eu esperava (estado: {state}). Não vou tentar de novo "
            "sozinho — melhor você conferir comigo antes do próximo passo."
        )

    def _refuse_pending(self) -> str:
        pending = self._state.get("pending")
        if not pending or pending.get("kind") != "promotion":
            return self._status_reply()
        self._clear_pending(pending["sid"], status="refused")
        return "Combinado, não aplico agora. Se quiser, é só me avisar quando puder testar."

    def _restore_last_known_good(self) -> str:
        try:
            info = self.release.most_recent_promotion(self.build)
        except Exception as exc:
            return f"Não consegui checar o histórico de atualizações ({type(exc).__name__})."
        if not info:
            return "Não tem nada para restaurar — eu nunca cheguei a aplicar nenhuma atualização."
        try:
            promotion = self.release.SourcePromotion.from_journal(info["journal"], build=self.build)
            promotion.rollback()
        except ValueError:
            return (
                "Não tem nada para restaurar agora — a última atualização já não está "
                "mais valendo (ou nunca chegou a valer de verdade)."
            )
        except Exception as exc:
            return f"Tentei restaurar, mas não consegui ({type(exc).__name__}). Nada mudou além do que já estava."
        return "Pronto, voltei para a versão de antes. Pode testar."

    def _status_reply(self) -> str:
        pending = self._state.get("pending")
        if pending and pending.get("kind") == "promotion":
            return "Tem uma atualização esperando sua resposta. Responda SIM para aplicar ou NÃO para deixar como está."
        if pending and pending.get("kind") == "physical":
            return "Tem uma novidade pronta, mas ela precisa que você teste na frente do computador."
        return "Tudo certo por aqui. Nenhuma atualização esperando."

    # -- ciclo de aviso -------------------------------------------------------
    def check_and_notify(self) -> None:
        """Avisa sobre um candidato novo, no máximo uma vez, com no máximo um lembrete."""
        owner = self._current_owner()
        if owner is None:
            return  # ninguém para avisar ainda
        now = self._now()
        pending = self._state.get("pending")
        if pending:
            if pending.get("reminded_at") is None and (now - pending["notified_at"]) > REMINDER_AFTER_SECONDS:
                reminder = (
                    "Ainda esperando sua resposta sobre a atualização (SIM ou NÃO)."
                    if pending["kind"] == "promotion" else
                    "Ainda esperando você testar a novidade pronta, quando der."
                )
                self._send(owner, reminder)
                pending["reminded_at"] = now
                self._save_state()
            return  # uma coisa pendente por vez
        try:
            candidate = self.candidate_source()
        except Exception as exc:
            print(f"[LAB-TELEGRAM] candidate_source falhou: {type(exc).__name__}: {exc}", flush=True)
            return
        if not candidate:
            return
        sid = candidate.get("sid")
        if not sid or sid in self._state.get("handled", {}):
            return  # um candidato = uma mensagem, mesmo depois de resolvido
        areas = changed_areas(candidate.get("source_paths"))
        if areas:
            self._state["pending"] = {
                "sid": sid, "kind": "physical", "areas": sorted(areas),
                "notified_at": now, "reminded_at": None,
            }
            self._save_state()
            self._send(owner, _physical_message(areas))
            return
        self._state["pending"] = {
            "sid": sid, "kind": "promotion", "receipt": candidate["receipt"],
            "workspace": str(candidate["workspace"]), "notified_at": now, "reminded_at": None,
        }
        self._save_state()
        self._send(owner, READY_MESSAGE)

    # -- laço de produção -----------------------------------------------------
    def run_forever(self, poll_interval: float = 5.0, notify_interval: float = 60.0) -> None:  # pragma: no cover
        """Laço bloqueante para o runner standalone. Nunca sobe sozinho em testes."""
        last_notify = 0.0
        while True:
            self.poll_once(timeout=0)
            now = self._now()
            if now - last_notify >= notify_interval:
                self.check_and_notify()
                last_notify = now
            time.sleep(poll_interval)
