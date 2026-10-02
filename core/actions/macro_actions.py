"""Persistent macro actions; every nested action keeps its own safety gate."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from core.action_registry import ActionResult, action, get_registry
from core.macro_engine import (
    Macro,
    condition_matches,
    get_macro,
    list_macros,
    macro_from_dict,
    macro_to_dict,
    register_macro,
    resolve_dynamic,
    unregister_macro,
)

_lock = threading.RLock()


def _store_path() -> Path:
    from core.paths import user_data_dir

    path = user_data_dir() / "data" / "macros" / "macros.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_persistent() -> None:
    path = _store_path()
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw if isinstance(raw, list) else []:
            register_macro(macro_from_dict(item))
    except (OSError, ValueError, TypeError):
        return


def _save_persistent() -> None:
    macros = [macro_to_dict(get_macro(name)) for name in list_macros() if get_macro(name) is not None]
    path = _store_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(macros, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@action(name="macro_create", category="automation", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Cria ou atualiza uma macro persistente")
def macro_create_action(name: str, steps: list[dict[str, Any]]) -> ActionResult:
    try:
        macro = macro_from_dict({"name": name, "steps": steps})
        registry = get_registry()
        unknown = sorted({step.action for step in macro.steps if step.action and registry.get(step.action) is None})
        if unknown:
            return ActionResult(False, error=f"Acoes desconhecidas na macro: {', '.join(unknown)}")
        with _lock:
            register_macro(macro)
            _save_persistent()
        persisted = get_macro(name)
        if persisted is None:
            return ActionResult(False, error="A macro nao ficou registrada")
        return ActionResult(True, f"Macro {persisted.name} salva e verificada.", data=macro_to_dict(persisted))
    except (OSError, ValueError, KeyError) as exc:
        return ActionResult(False, error=f"Nao consegui criar a macro: {exc}")


@action(name="macro_list", category="automation", description="Lista macros registradas")
def macro_list_action() -> ActionResult:
    with _lock:
        _load_persistent()
        data = [macro_to_dict(get_macro(name)) for name in list_macros() if get_macro(name) is not None]
    return ActionResult(True, f"Macros encontradas: {len(data)}", data=data)


@action(name="macro_delete", category="automation", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Remove uma macro persistente")
def macro_delete_action(name: str) -> ActionResult:
    with _lock:
        _load_persistent()
        if not unregister_macro(name):
            return ActionResult(False, error=f"Macro {name!r} nao encontrada")
        try:
            _save_persistent()
        except OSError as exc:
            return ActionResult(False, error=f"A macro saiu da memoria, mas nao foi removida do disco: {exc}", verificado=False)
    return ActionResult(True, f"Macro {name} removida e verificada.")


@action(name="macro_run", category="automation", description="Executa uma macro pelos gates normais de cada acao")
def macro_run_action(name: str, parameters: dict[str, Any] | None = None) -> ActionResult:
    with _lock:
        _load_persistent()
        macro: Macro | None = get_macro(name)
    if macro is None:
        return ActionResult(False, error=f"Macro {name!r} nao encontrada")
    values = dict(parameters or {})
    results: list[dict[str, Any]] = []
    registry = get_registry()
    all_verified = True
    for index, step in enumerate(macro.steps):
        try:
            if not condition_matches(step.when, values, results):
                results.append({"index": index, "action": step.action, "success": True, "skipped": True})
                continue
            if step.action is None:
                results.append({"index": index, "action": None, "success": True, "skipped": True, "note": step.note})
                continue
            kwargs = resolve_dynamic(step.params, values)
            if step.param is not None and not kwargs:
                spec = registry.get_spec(step.action)
                names = list((spec.parameters.get("properties") or {}).keys()) if spec else []
                if len(names) == 1:
                    kwargs[names[0]] = resolve_dynamic(step.param, values)
                else:
                    return ActionResult(False, error=f"Passo {index} precisa usar params explicitos", data=results)
            nested = registry.execute(step.action, **kwargs)
            item = {
                "index": index, "action": step.action, "success": nested.success,
                "verified": nested.verificado, "output": nested.output, "error": nested.error,
            }
            results.append(item)
            all_verified = all_verified and nested.verificado
            if not nested.success:
                return ActionResult(False, error=f"Macro interrompida no passo {index} ({step.action}): {nested.error}", data=results)
        except (KeyError, TypeError, ValueError) as exc:
            return ActionResult(False, error=f"Macro invalida no passo {index}: {exc}", data=results)
    return ActionResult(True, f"Macro {name} executada em {len(results)} passos.", data=results, verificado=all_verified)
# ---------------------------------------------------------------------------
# Atalhos de comando: frase curta -> macro (EQUIPE 2, rodada 2026-10-02)
#
# Camada deterministica "frase exata -> macro" (item 7 do backlog de pesquisa
# competitiva, PESQUISA-CONCORRENTES.md - padrao VoiceAttack/Talon): comandos
# curtos de voz/ditado resolvem direto para uma macro, sem passar pelo LLM.
# A execucao delega para a action "macro_run", entao cada passo da macro
# continua passando pelos mesmos portoes de seguranca (fronteira de dinheiro,
# trava do supercerebro, confirmacao de alto risco). O atalho e so um apelido.
# ---------------------------------------------------------------------------


def _normalize_phrase(phrase: str) -> str:
    """Normaliza frase de comando: sem acentos, minusculas, espacos colapsados.

    O STT as vezes devolve "musica" em vez de "musica"; a normalizacao faz os
    dois casarem com o mesmo atalho.
    """
    import unicodedata

    text = unicodedata.normalize("NFD", str(phrase))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _alias_store_path() -> Path:
    path = _store_path().parent / "aliases.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_aliases() -> dict:
    path = _alias_store_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _save_aliases(aliases: dict) -> None:
    path = _alias_store_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(aliases, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


@action(name="macro_alias_set", category="automation", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Cria ou atualiza um atalho de comando (frase curta -> macro)")
def macro_alias_set_action(phrase: str, macro: str) -> ActionResult:
    key = _normalize_phrase(phrase)
    if not key:
        return ActionResult(False, error="Frase do atalho vazia")
    with _lock:
        _load_persistent()
        if get_macro(macro) is None:
            return ActionResult(False, error=f"Macro {macro!r} nao encontrada")
        aliases = _load_aliases()
        existed = key in aliases
        aliases[key] = macro
        try:
            _save_aliases(aliases)
        except OSError as exc:
            return ActionResult(False, error=f"Nao consegui salvar o atalho: {exc}")
    return ActionResult(
        True,
        f"Atalho {'atualizado' if existed else 'criado'}: {key!r} -> {macro}",
        data={"phrase": key, "macro": macro},
    )


@action(name="macro_alias_remove", category="automation", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Remove um atalho de comando (frase curta)")
def macro_alias_remove_action(phrase: str) -> ActionResult:
    key = _normalize_phrase(phrase)
    with _lock:
        aliases = _load_aliases()
        if key not in aliases:
            return ActionResult(False, error=f"Atalho {phrase!r} nao encontrado")
        del aliases[key]
        try:
            _save_aliases(aliases)
        except OSError as exc:
            return ActionResult(
                False,
                error=f"O atalho saiu da memoria, mas nao foi removido do disco: {exc}",
                verificado=False,
            )
    return ActionResult(True, f"Atalho {key!r} removido.")


@action(name="macro_alias_list", category="automation", description="Lista os atalhos de comando registrados")
def macro_alias_list_action() -> ActionResult:
    with _lock:
        aliases = _load_aliases()
    return ActionResult(
        True,
        f"Atalhos encontrados: {len(aliases)}",
        data=dict(sorted(aliases.items())),
    )


@action(name="macro_run_phrase", category="automation", description="Executa a macro do atalho de comando (frase curta), pelos gates normais")
def macro_run_phrase_action(phrase: str, parameters: dict | None = None) -> ActionResult:
    key = _normalize_phrase(phrase)
    with _lock:
        aliases = _load_aliases()
        macro_name = aliases.get(key)
    if macro_name is None:
        return ActionResult(False, error=f"Nenhum atalho para {phrase!r}")
    # Chamada direta a funcao (nao via registry.execute): o parametro da action
    # se chama "name" e colidiria com o proprio parametro "name" do execute() -
    # limitacao pre-existente do registry (vale tambem p/ macro_create/delete).
    # Os gates continuam valendo: macro_run_action executa cada passo aninhado
    # via registry.execute, com todos os portoes de seguranca.
    return macro_run_action(macro_name, parameters or {})
