"""ZARA Auto-Reparo — FRENTE F (MISSÃO GIGANTE 3, 2026-09-28).

"Ela" conserta sozinha o que é simples e salva a memória do reparo no
Obsidian (como quebrou + como consertou). O que não é simples vira um
aviso curto pedindo permissão: "quebrei a voz, posso consertar?"

F1 — Classificar erros "simples": só é SIMPLES o erro com causa conhecida +
     reparo registrado, seguro e reversível. O padrão é COMPLEXO
     (fail-closed): erro desconhecido nunca é consertado sozinho.
F2 — Auto-reparo: detectou -> consertou sozinho -> salvou a nota no
     `aprendizados/` do segundo-cérebro (Obsidian do Alex).
F3 — Erro complexo: mensagem curta em linguagem simples pedindo permissão.

Fronteiras duras (nunca violadas):
- Dinheiro/pagamento/cartão: SEMPRE bloqueado, nunca auto-reparado.
- Quarentena: reparo nunca toca em nada do supercérebro
  (`work_mode_active` / `work_mode_sentinel` / `_watch_supercerebro_work_mode`
  continuam proibidos) nem em grants/autorizações.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("auto_repair")

__all__ = [
    "ErrorClass",
    "Classification",
    "RepairOutcome",
    "RepairMemory",
    "classify_error",
    "handle_error",
    "ask_permission",
    "resolve_segundo_cerebro",
]


class ErrorClass:
    """Classificação de severidade do erro para auto-reparo."""
    SIMPLE = "simples"    # dá pra consertar sem decisão humana
    COMPLEX = "complexo"  # avisa curto e pede permissão


@dataclass
class Classification:
    error_class: str
    reason: str
    blocked: bool = False  # True = nunca auto-repara (dinheiro/quarentena)


@dataclass
class RepairOutcome:
    """Resultado de uma tentativa de reparo."""
    fixed: bool
    error_class: str
    strategy: str | None = None
    note_path: str | None = None
    message: str | None = None  # pedido de permissão, quando complexo
    detail: str = ""


# ---------------------------------------------------------------------------
# Fronteiras: o que NUNCA é auto-reparado
# ---------------------------------------------------------------------------

_MONEY_WORDS = re.compile(
    r"(pagamento|pagar|cart[aã]o|cr[eé]dito|d[eé]bito|dinheiro|pix|boleto|"
    r"fatura|compra|checkout|stripe|mercadopago|saldo|transfer[eê]ncia|"
    r"assinatura|cobran[cç]a)",
    re.IGNORECASE,
)

# Quarentena permanente do Alex: nada aqui é tocado por reparo automático.
_QUARANTINE_PARTS = ("supercerebro", "whatsapp_grant", "work_mode")


def _blocked_reason(exc: BaseException, context: dict | None) -> str | None:
    """Devolve o motivo do bloqueio, ou None se não há bloqueio."""
    haystack = " ".join(
        [
            type(exc).__name__,
            str(exc),
            str((context or {}).get("operation", "")),
            str((context or {}).get("component", "")),
            str((context or {}).get("target_path", "")),
        ]
    )
    if _MONEY_WORDS.search(haystack):
        return "envolve dinheiro/pagamento — bloqueado por construção"
    lowered = haystack.lower()
    if any(part in lowered for part in _QUARANTINE_PARTS):
        return "área em quarentena (supercérebro/grant) — nunca tocada por reparo"
    return None


# ---------------------------------------------------------------------------
# F1 — Classificação
# ---------------------------------------------------------------------------

# Exceções que nunca são simples, não importa o contexto.
_NEVER_SIMPLE = (PermissionError, MemoryError, SystemError, KeyboardInterrupt, SystemExit)

# Tipos transitórios: retry com backoff costuma resolver.
_TRANSIENT_TYPES = (TimeoutError, ConnectionError)
_TRANSIENT_NAMES = ("timeout", "timed out", "temporarily", "connection reset", "connection aborted")


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_TYPES):
        return True
    try:
        import socket
        if isinstance(exc, socket.timeout):
            return True
    except Exception:
        pass
    msg = f"{type(exc).__name__} {exc}".lower()
    return any(name in msg for name in _TRANSIENT_NAMES)


def _is_sqlite_locked(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()


def _is_corrupt_cache(exc: BaseException, context: dict | None) -> bool:
    if not isinstance(exc, json.JSONDecodeError):
        return False
    target = str((context or {}).get("target_path", "")).lower().replace("\\", "/")
    if not target.endswith(".json"):
        return False
    return any(part in target for part in ("cache", "tmp", "temp"))


def _is_missing_dir(exc: BaseException, context: dict | None) -> bool:
    if not isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return False
    return bool((context or {}).get("target_path"))


def _is_config_default(exc: BaseException, context: dict | None) -> bool:
    if not isinstance(exc, KeyError):
        return False
    defaults = (context or {}).get("defaults")
    if not isinstance(defaults, dict):
        return False
    key = exc.args[0] if exc.args else None
    return key in defaults


def classify_error(
    exc: BaseException,
    context: dict[str, Any] | None = None,
    *,
    retry_available: bool = False,
) -> Classification:
    """F1: classifica o erro em SIMPLES ou COMPLEXO.

    Fail-closed: qualquer coisa não listada explicitamente abaixo é COMPLEXA.
    """
    context = context or {}

    blocked = _blocked_reason(exc, context)
    if blocked:
        return Classification(ErrorClass.COMPLEX, blocked, blocked=True)

    if isinstance(exc, _NEVER_SIMPLE):
        return Classification(
            ErrorClass.COMPLEX,
            f"{type(exc).__name__} nunca é consertado sozinho (pode ser política do sistema)",
        )

    if _is_transient(exc):
        if retry_available:
            return Classification(ErrorClass.SIMPLE, "falha transitória — repetir a operação costuma resolver")
        return Classification(ErrorClass.COMPLEX, "falha transitória mas sem como repetir a operação")

    if _is_sqlite_locked(exc):
        if retry_available:
            return Classification(ErrorClass.SIMPLE, "banco travado momentaneamente — esperar e repetir resolve")
        return Classification(ErrorClass.COMPLEX, "banco travado mas sem como repetir a operação")

    if _is_missing_dir(exc, context):
        return Classification(ErrorClass.SIMPLE, "pasta/arquivo esperado não existe — recriar é seguro")

    if _is_corrupt_cache(exc, context):
        return Classification(ErrorClass.SIMPLE, "cache JSON corrompido — reconstruir a partir do padrão é seguro")

    if _is_config_default(exc, context):
        return Classification(ErrorClass.SIMPLE, "chave de configuração com valor padrão conhecido — preencher é seguro")

    return Classification(
        ErrorClass.COMPLEX,
        f"causa desconhecida ({type(exc).__name__}) — sem reparo registrado, não mexo sozinho",
    )


# ---------------------------------------------------------------------------
# F2 — Estratégias de reparo (runbook)
# ---------------------------------------------------------------------------

@dataclass
class _Strategy:
    name: str
    description: str

    def matches(self, exc: BaseException, context: dict) -> bool:  # noqa: D102
        raise NotImplementedError

    def fix(self, exc: BaseException, context: dict, retry: Callable | None) -> str:
        """Aplica o reparo. Devolve descrição do que foi feito. Levanta se falhar."""
        raise NotImplementedError

    def verify(self, exc: BaseException, context: dict) -> bool:
        """Confere que o reparo segurou. False = escalar para complexo."""
        raise NotImplementedError


class _TransientRetry(_Strategy):
    def matches(self, exc, context):
        return _is_transient(exc) or _is_sqlite_locked(exc)

    def fix(self, exc, context, retry):
        if retry is None:
            raise RuntimeError("sem operação para repetir")
        last: BaseException | None = None
        for attempt, wait in enumerate((0.3, 0.8, 1.5), start=1):
            try:
                retry()
                return f"operação repetida com sucesso na tentativa {attempt}"
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(wait)
        raise RuntimeError(f"3 tentativas falharam; última: {last}")

    def verify(self, exc, context):
        return True  # fix() só retorna se retry() não levantou


class _MissingDir(_Strategy):
    def matches(self, exc, context):
        return _is_missing_dir(exc, context)

    def fix(self, exc, context, retry):
        target = Path(str(context["target_path"]))
        target.mkdir(parents=True, exist_ok=True)
        return f"pasta recriada: {target}"

    def verify(self, exc, context):
        return Path(str(context["target_path"])).exists()


class _CorruptCache(_Strategy):
    def matches(self, exc, context):
        return _is_corrupt_cache(exc, context)

    def fix(self, exc, context, retry):
        target = Path(str(context["target_path"]))
        default = context.get("cache_default", {})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"cache reconstruído com valor padrão em {target}"

    def verify(self, exc, context):
        try:
            json.loads(Path(str(context["target_path"])).read_text(encoding="utf-8"))
            return True
        except Exception:
            return False


class _ConfigDefault(_Strategy):
    def matches(self, exc, context):
        return _is_config_default(exc, context)

    def fix(self, exc, context, retry):
        key = exc.args[0]
        value = context["defaults"][key]
        setter = context.get("config_set")
        config = context.get("config")
        if callable(setter):
            setter(key, value)
        elif isinstance(config, dict):
            config[key] = value
        else:
            raise RuntimeError("sem onde gravar o valor padrão")
        return f"chave '{key}' preenchida com o valor padrão"

    def verify(self, exc, context):
        key = exc.args[0] if exc.args else None
        getter = context.get("config_get")
        config = context.get("config")
        if callable(getter):
            try:
                getter(key)
                return True
            except KeyError:
                return False
        return isinstance(config, dict) and key in config


_STRATEGIES: list[_Strategy] = [
    _TransientRetry("retry_transitorio", "repetir operação transitória com backoff"),
    _MissingDir("recriar_pasta", "recriar pasta/arquivo esperado ausente"),
    _CorruptCache("reconstruir_cache", "reconstruir cache JSON corrompido"),
    _ConfigDefault("preencher_padrao", "preencher configuração com valor padrão conhecido"),
]


# ---------------------------------------------------------------------------
# Memória do reparo no Obsidian (segundo-cérebro)
# ---------------------------------------------------------------------------

def _scan_user_profiles_for_obsidian(users_root: Path | str | None = None) -> Path | None:
    """Fallback: procura o obsidian.json nos perfis de usuário da máquina.

    O app pode rodar como um usuário de serviço (ex.: `zoe`) enquanto o
    Obsidian do Alex está no perfil dele. Varre `C:\\Users\\*` e pega o
    vault usado mais recentemente que ainda exista no disco.
    """
    try:
        users_root = Path(users_root) if users_root else Path("C:/Users")
        if not users_root.is_dir():
            return None
        best: Path | None = None
        best_ts = -1
        for config in users_root.glob("*/AppData/Roaming/obsidian/obsidian.json"):
            try:
                data = json.loads(config.read_text(encoding="utf-8"))
            except Exception:
                continue
            for entry in (data.get("vaults") or {}).values():
                vault_path = Path(entry.get("path", ""))
                ts = entry.get("ts", 0)
                if vault_path.is_dir() and ts > best_ts:
                    best, best_ts = vault_path, ts
        return best
    except Exception:
        return None


def resolve_segundo_cerebro(explicit: Path | str | None = None) -> Path | None:
    """Resolve a pasta do segundo-cérebro do Alex.

    Ordem: caminho explícito > OBSIDIAN_VAULT_PATH > detecção real via
    obsidian.json. Se existir `segundo-cerebro/` dentro do vault detectado,
    usa ele; senão, o próprio vault. None = cofre indisponível (best-effort).
    """
    if explicit is not None:
        vault = Path(explicit)
        vault = vault if vault.is_dir() else None
    else:
        env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
        vault = Path(env_path) if env_path else None
        if vault is None:
            try:
                from memory.project_memory import _detect_real_obsidian_vault
                vault = _detect_real_obsidian_vault()
            except Exception:
                vault = None
        if vault is None:
            vault = _scan_user_profiles_for_obsidian()
    if vault is None or not vault.is_dir():
        return None
    nested = vault / "segundo-cerebro"
    return nested if nested.is_dir() else vault


def _slug(text: str, limit: int = 40) -> str:
    clean = re.sub(r"[^\w\- ]+", "", str(text or "").strip().lower())
    return (clean.replace(" ", "-") or "reparo")[:limit]


class RepairMemory:
    """Salva a memória do reparo no Obsidian: como quebrou + como consertou.

    Best-effort por construção: cofre indisponível nunca quebra o reparo —
    devolve None em vez de levantar.
    """

    def __init__(self, vault_path: Path | str | None = None):
        self._explicit = Path(vault_path) if vault_path is not None else None

    def save_repair_note(
        self,
        *,
        title: str,
        component: str,
        error_text: str,
        how_broke: str,
        how_fixed: str,
        verification: str = "",
        simulated: bool = False,
    ) -> str | None:
        """Escreve a nota em `aprendizados/` do segundo-cérebro. Devolve o
        caminho salvo, ou None se o cofre não estiver disponível."""
        try:
            vault = resolve_segundo_cerebro(self._explicit)
            if vault is None:
                return None
            folder = vault / "aprendizados"
            folder.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now().astimezone()
            fname = f"reparo-{stamp.strftime('%Y%m%d-%H%M%S')}-{_slug(title)}.md"
            note_path = folder / fname

            sim_tag = "\n> **Nota:** reparo SIMULADO (teste da MISSÃO GIGANTE 3) — não foi um erro real.\n" if simulated else ""
            body = (
                f"# Reparo automático: {title}\n"
                f"\n**Data:** {stamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Componente:** {component}\n"
                f"**Erro:** `{error_text}`\n"
                f"{sim_tag}"
                f"\n## Como quebrou\n{how_broke}\n"
                f"\n## Como consertou\n{how_fixed}\n"
                f"\n**Verificação:** {verification or 'não registrada'}\n"
                f"\n[[INDICE]]\n"
            )
            note_path.write_text(body, encoding="utf-8")
            return str(note_path)
        except Exception as e:  # noqa: BLE001
            log.warning("não consegui salvar a nota de reparo no Obsidian: %s", e)
            return None


def _audit(action: str, outcome: str, error: str | None = None) -> None:
    """Registra o reparo no audit log. Auditoria nunca quebra o reparo."""
    try:
        from core.audit_log import audit_log
        audit_log().record(action, "LOW", outcome, error)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# F3 — Erro complexo: aviso curto pedindo permissão
# ---------------------------------------------------------------------------

def _short_cause(exc: BaseException) -> str:
    msg = (str(exc) or type(exc).__name__).strip().splitlines()[0]
    msg = re.sub(r"\s+", " ", msg)
    return msg[:70]


def ask_permission(exc: BaseException, context: dict[str, Any] | None = None) -> str:
    """F3: mensagem curta em linguagem simples pedindo permissão para consertar.

    Formato do Alex: "quebrei a voz, posso consertar?"
    """
    context = context or {}
    classification = classify_error(exc, context)
    component = str(context.get("component_pt") or context.get("component") or "o app")
    cause = _short_cause(exc)
    if classification.blocked and "dinheiro" in classification.reason:
        return f"Quebrei {component}: isso envolve dinheiro — não mexo sem você mandar."
    return f"Quebrei {component}: {cause}. Posso tentar consertar?"


# ---------------------------------------------------------------------------
# Orquestração: detectou -> classificou -> consertou -> salvou memória
# ---------------------------------------------------------------------------

def handle_error(
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
    retry: Callable[[], Any] | None = None,
    vault_path: Path | str | None = None,
    simulated: bool = False,
) -> RepairOutcome:
    """Pipeline completo do auto-reparo.

    - Erro simples: aplica a estratégia registrada, verifica, salva a nota
      no Obsidian e registra na auditoria. Sem intervenção humana.
    - Erro complexo (ou reparo que falhou na verificação): devolve o pedido
      curto de permissão — a zoe avisa o Alex e espera.
    Nunca levanta exceção por causa do próprio reparo.
    """
    context = dict(context or {})
    classification = classify_error(exc, context, retry_available=retry is not None)
    error_text = f"{type(exc).__name__}: {_short_cause(exc)}"
    component = str(context.get("component") or context.get("operation") or "desconhecido")

    if classification.error_class != ErrorClass.SIMPLE:
        message = ask_permission(exc, context)
        _audit("auto_repair", "escalated", error_text[:200])
        log.info("erro complexo (%s): %s", classification.reason, error_text)
        return RepairOutcome(
            fixed=False,
            error_class=ErrorClass.COMPLEX,
            message=message,
            detail=classification.reason,
        )

    strategy = next((s for s in _STRATEGIES if s.matches(exc, context)), None)
    if strategy is None:
        # Não deveria acontecer (classify só marca SIMPLE com estratégia),
        # mas fail-closed: escalar em vez de inventar reparo.
        message = ask_permission(exc, context)
        _audit("auto_repair", "escalated", error_text[:200])
        return RepairOutcome(
            fixed=False, error_class=ErrorClass.COMPLEX,
            message=message, detail="sem estratégia registrada",
        )

    try:
        how_fixed = strategy.fix(exc, context, retry)
    except Exception as e:  # noqa: BLE001
        message = ask_permission(exc, context)
        _audit("auto_repair", "fix_failed", f"{error_text[:120]} | {e}"[:200])
        log.warning("reparo '%s' falhou: %s", strategy.name, e)
        return RepairOutcome(
            fixed=False, error_class=ErrorClass.COMPLEX,
            strategy=strategy.name, message=message,
            detail=f"tentativa de reparo falhou: {e}",
        )

    verified = strategy.verify(exc, context)
    if not verified:
        message = ask_permission(exc, context)
        _audit("auto_repair", "verify_failed", error_text[:200])
        return RepairOutcome(
            fixed=False, error_class=ErrorClass.COMPLEX,
            strategy=strategy.name, message=message,
            detail="reparo aplicado mas a verificação não confirmou",
        )

    how_broke = str(context.get("how_broke") or f"Ocorreu {error_text} durante '{component}'.")
    note_path = RepairMemory(vault_path).save_repair_note(
        title=context.get("note_title") or f"{component} — {type(exc).__name__}",
        component=component,
        error_text=error_text,
        how_broke=how_broke,
        how_fixed=how_fixed,
        verification=f"verificação da estratégia '{strategy.name}' confirmou o reparo",
        simulated=simulated,
    )
    _audit("auto_repair", "fixed", error_text[:200])
    log.info("reparo '%s' aplicado e verificado: %s", strategy.name, error_text)
    return RepairOutcome(
        fixed=True,
        error_class=ErrorClass.SIMPLE,
        strategy=strategy.name,
        note_path=note_path,
        detail=how_fixed,
    )
