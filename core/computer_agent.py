"""Agente de Use Computer - loop observe -> age -> verifica.

FRENTE A (2026-09-29): o use-computer antes eram chamadas avulsas sem ninguem
dirigindo. Este modulo e o AGENTE: recebe um objetivo em PT-BR ("abra o bloco
de notas e digite 'oi'") e executa o loop dirigido, vendo a tela entre os
passos (nada de comando cego em sequencia).

    1. TRAVA fail-closed: com o Supercerebro desligado (pc_control_allowed=False)
       o agente RECUSA na hora. A trava NUNCA e removida aqui - os simbolos
       banidos (work_mode_active / work_mode_sentinel /
       _watch_supercerebro_work_mode) nao existem neste modulo.
    2. DECOMPOR: parse_computer_command quebra o objetivo em passos (com as
       extensoes do agente: "clique em '<texto>'" -> vision_click_text,
       "aguarde o texto '<texto>'" -> vision_wait_for_text) + grounding por
       visao (vision_find_text acha as coordenadas de elementos nomeados).
    3. Cada passo: EXECUTA via ActionRegistry (a trava vale por passo) ->
       VERIFICA vendo a tela (o clique acertou? o texto apareceu?) -> falhou?
       1 tentativa de recuperacao com re-grounding por visao -> falhou de
       novo? ABORTA com relatorio claro do que travou.
    4. Eventos computer_agent_started / computer_agent_stopped para o frontend
       (borda colorida) - barramento interno simples; o handler IPC faz a ponte
       para o canal de eventos do backend.

Tudo in-process, rapido, sem enrolacao. A auditoria reaproveita
computer_audit (nunca registra o conteudo digitado, so a quantidade de
caracteres).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

from core.action_registry import ActionResult, get_registry
from core.actions import computer_command as _cc

# --- gatilhos de chat/voz/celular -------------------------------------------
# "use o computador para abrir o bloco de notas"
_AGENT_TRIGGERS = (
    "use o computador para",
    "usa o computador para",
    "no computador,",
)


def extract_goal(text: str) -> str | None:
    """Se o texto comeca com um gatilho do agente, devolve o objetivo.

    Devolve None quando nao e um pedido para o agente (o chat segue normal).
    """
    cleaned = re.sub(r"^(?:zara[,\s]+)", "", str(text or "").strip(), flags=re.IGNORECASE)
    low = cleaned.casefold()
    for trigger in _AGENT_TRIGGERS:
        if low.startswith(trigger):
            goal = cleaned[len(trigger):].strip(" ,.:;!?")
            return goal or None
    return None


# --- barramento de eventos interno (simples) ---------------------------------
# O handler IPC assina aqui e repassa para o canal de eventos do backend
# (send_event). Em testes, da para assinar e conferir inicio/fim sem backend.
_listeners: list[Callable[[str, dict], None]] = []


def add_event_listener(fn: Callable[[str, dict], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def remove_event_listener(fn: Callable[[str, dict], None]) -> None:
    try:
        _listeners.remove(fn)
    except ValueError:
        pass


def _emit(event: str, payload: dict) -> None:
    for fn in list(_listeners):
        try:
            fn(event, payload)
        except Exception:
            pass  # evento nunca quebra o agente


# --- verificacao --------------------------------------------------------------
# STRONG: o passo so conta se o efeito for observado na tela.
# WEAK: a execucao OK conta como passo OK, mas registra "nao confirmado"
# (ex.: pressionar Tab quase nunca muda o texto do OCR - abortar por isso
# seria desonesto; o registry ja garantiu que a tecla foi para a janela certa).
_STRONG_VERIFY = {
    "computer_click", "vision_click_text", "computer_type_text",
    "vision_wait_for_text", "os_app", "computer_focus_window", "__focus_named__",
}


def _screen_words(reg) -> frozenset[str] | None:
    """Conjunto normalizado das palavras visiveis na tela (OCR). None = falhou."""
    try:
        result = reg.execute("vision_read_screen")
    except Exception:
        return None
    if not result.success:
        return None
    words = (result.data or {}).get("words") or []
    return frozenset(
        str(w.get("text", "")).casefold()
        for w in words
        if str(w.get("text", "")).strip()
    )


def _ground(reg, name: str, params: dict, hwnd: int | None,
            window_title: str) -> tuple[dict | None, int | None, str, str]:
    """Resolve __HWND__/__CENTER__ observando a janela ativa. (erro) = 4o item."""
    resolved = dict(params)
    if _cc._HWND in resolved.values() or _cc._CENTER in resolved.values():
        if hwnd is None:
            fg = reg.execute("computer_foreground")
            if not fg.success:
                return None, hwnd, window_title, fg.error or "Janela ativa indisponivel."
            data = fg.data or {}
            hwnd = int(data.get("hwnd", 0)) or None
            window_title = str(data.get("title", ""))
            if hwnd is None:
                return None, hwnd, window_title, "Janela ativa indisponivel."
        resolved = {k: (hwnd if v == _cc._HWND else v) for k, v in resolved.items()}
        if _cc._CENTER in resolved.values():
            rect = (reg.execute("computer_foreground").data or {}).get("rect") or {}
            cx = (int(rect.get("left", 0)) + int(rect.get("right", 0))) // 2
            cy = (int(rect.get("top", 0)) + int(rect.get("bottom", 0))) // 2
            resolved = {
                k: (cx if v == _cc._CENTER and k == "x"
                    else cy if v == _cc._CENTER and k == "y" else v)
                for k, v in resolved.items()
            }
    return resolved, hwnd, window_title, ""


def _sanitized_params(name: str, params: dict) -> dict:
    """Params sem conteudo digitado (o relatorio nao vaza texto privado)."""
    if name == "computer_type_text":
        return {"chars": len(str(params.get("text", "")))}
    return {k: v for k, v in params.items()}


def _verify(reg, name: str, params: dict, result: ActionResult,
            before: frozenset[str] | None) -> tuple[bool, bool, str, frozenset[str] | None]:
    """Verifica o passo vendo a tela.

    Devolve (ok, verificado_forte, nota, palavras_depois).
    """
    after = _screen_words(reg)
    if after is not None:
        changed = before is not None and after != before
    else:
        changed = False

    if name == "computer_type_text":
        # A propria action confirma via UIA se o texto entrou no campo.
        if result.verificado:
            return True, True, "texto confirmado no campo", after
        return False, False, f"digitacao nao confirmada: {result.error}", after
    if name == "vision_wait_for_text":
        if result.success:
            return True, True, "texto apareceu na tela", after
        return False, False, result.error or "texto nao apareceu", after
    if name in ("computer_click", "vision_click_text"):
        if changed:
            return True, True, "tela mudou apos o clique", after
        return False, False, "clique sem efeito visivel na tela", after
    if name in ("os_app", "computer_focus_window", "__focus_named__"):
        if result.verificado:
            return True, True, "janela confirmada", after
        return False, False, result.error or "janela nao confirmada", after
    # WEAK: tecla/rolagem e leituras - execucao OK conta, sem abortar por
    # "efeito nao visivel".
    if changed:
        return True, True, "efeito observado na tela", after
    return True, False, "enviado; efeito nao confirmado na tela", after


# --- o loop -------------------------------------------------------------------

def run_goal(goal: str, context: dict | None = None) -> dict:
    """Executa o objetivo: observar -> agir -> verificar, passo a passo.

    Nunca levanta excecao: todo problema vira um dicionario de relatorio.
    """
    started_at = time.monotonic()
    ctx = dict(context or {})
    timeout_s = float(ctx.get("timeout_s", 120) or 120)
    goal_text = str(goal or "").strip()

    _emit("computer_agent_started", {"goal": goal_text})
    summary: dict[str, Any] = {
        "success": False,
        "goal": goal_text,
        "steps": [],
        "refused": False,
        "verified": False,
        "travou_no_passo": None,
        "error": None,
        "duration_ms": 0.0,
    }

    def _finish(**kw) -> dict:
        summary.update(kw)
        summary["duration_ms"] = round((time.monotonic() - started_at) * 1000, 1)
        _emit("computer_agent_stopped", {
            "goal": goal_text,
            "success": summary["success"],
            "refused": summary["refused"],
            "verified": summary["verified"],
            "steps": len(summary["steps"]),
            "error": summary["error"],
        })
        return summary

    try:
        reg = get_registry()

        # 1. TRAVA fail-closed: sem Supercerebro, recusa imediata.
        if not getattr(reg, "pc_control_allowed", False):
            _cc.computer_audit("computer_agent", "blocked", goal_chars=len(goal_text))
            return _finish(
                refused=True,
                error=("Supercerebro desligado: o agente recusou mexer no computador. "
                       "Ligue a chave do Supercerebro para permitir."),
            )

        if not goal_text:
            return _finish(error="Objetivo vazio.")

        # 2. DECOMPOR o objetivo em passos.
        plan, refusal = _cc.parse_computer_command(goal_text)
        if plan is None:
            return _finish(error=refusal)
        _cc.computer_audit("computer_agent", "requested",
                           goal_chars=len(goal_text), plan_steps=len(plan))

        hwnd: int | None = None
        window_title = ""
        last_words: frozenset[str] | None = None
        all_verified = True

        # 3. Para cada passo: EXECUTA -> VERIFICA -> (1 recuperacao) -> ou aborta.
        for idx, step in enumerate(plan):
            if time.monotonic() - started_at > timeout_s:
                return _finish(
                    travou_no_passo=idx + 1,
                    error=f"Tempo esgotado ({timeout_s:.0f}s) no passo {idx + 1}.",
                )
            name = step["action"]
            params = dict(step["params"])
            rec: dict[str, Any] = {
                "n": idx + 1,
                "action": name,
                "params": _sanitized_params(name, params),
                "outcome": "falhou",
                "detail": "",
            }
            remaining = max(2.0, timeout_s - (time.monotonic() - started_at))

            attempt = 0
            while True:
                if last_words is None:
                    last_words = _screen_words(reg)

                if name == "__focus_named__":
                    result = _cc._resolve_focus_named(params.get("query", ""))
                    hwnd = None  # trocou de janela: re-observar no proximo passo
                    last_words = None
                    grounded: dict | None = {}
                    gerr = "" if result.success else (result.error or "falhou")
                else:
                    grounded, hwnd, window_title, gerr = _ground(
                        reg, name, params, hwnd, window_title)
                    if gerr:
                        result = ActionResult(False, error=gerr, verificado=False)
                    else:
                        exec_params = dict(grounded or {})
                        if name == "vision_wait_for_text":
                            exec_params["timeout_seconds"] = min(15.0, remaining)
                        result = reg.execute(name, **exec_params)

                _cc.computer_audit(
                    "computer_agent_step",
                    "success" if result.success else "error",
                    step=f"{idx + 1}/{len(plan)}:{name}",
                    window=window_title[:80] or None,
                    error=None if result.success else result.error,
                )

                if result.success:
                    ok, verified, note, after = _verify(
                        reg, name, params, result, last_words)
                    last_words = after if after is not None else last_words
                else:
                    ok, verified, note = False, False, result.error or "falhou"
                    # Janela pode ter trocado no meio do passo: re-observar.
                    if "mudou" in (result.error or "").casefold():
                        hwnd = None

                rec["detail"] = note
                if ok:
                    if attempt > 0:
                        rec["outcome"] = "recuperado"
                    else:
                        rec["outcome"] = "ok" if verified else "ok-sem-verificar"
                    if not verified:
                        all_verified = False
                    summary["steps"].append(rec)
                    break

                # Falhou: 1 tentativa de recuperacao com re-grounding por visao.
                attempt += 1
                if attempt >= 2:
                    rec["outcome"] = "falhou"
                    summary["steps"].append(rec)
                    _cc.computer_audit("computer_agent", "error",
                                       travou_no_passo=idx + 1, error=note[:200])
                    return _finish(
                        travou_no_passo=idx + 1,
                        error=(f"Travou no passo {idx + 1} de {len(plan)} "
                               f"({name}): {note}"),
                    )
                rec["detail"] = f"{note} - tentando de novo com nova leitura da tela"
                rec["outcome"] = "recuperando"
                hwnd = None       # re-observa a janela ativa
                last_words = None  # re-le a tela (re-grounding por visao)

        _cc.computer_audit("computer_agent", "success", plan_steps=len(plan))
        return _finish(success=True, verified=all_verified)
    except Exception as exc:  # o agente nunca quebra o backend
        try:
            _cc.computer_audit("computer_agent", "error", error=f"{type(exc).__name__}"[:200])
        except Exception:
            pass
        return _finish(error=f"Erro interno do agente: {type(exc).__name__}")


def reply_for_result(result: dict) -> str:
    """Resumo curto em PT-BR simples para o chat/voz (nada de jargao)."""
    if result.get("refused"):
        return ("Nao mexi em nada: o Supercerebro esta desligado. "
                "Ligue a chave verde na barra lateral e peca de novo.")
    steps = result.get("steps") or []
    ok_n = sum(1 for s in steps
               if s.get("outcome") in ("ok", "ok-sem-verificar", "recuperado"))
    if not steps and result.get("error"):
        return str(result["error"])
    if result.get("success"):
        ver = ("todos com efeito confirmado na tela"
               if result.get("verified")
               else "efeitos enviados (nem todos confirmados na tela)")
        return f"Pronto: {ok_n} passo(s) executados, {ver}."
    n = result.get("travou_no_passo")
    return (f"Travei no passo {n} de {len(steps)}: {result.get('error')} "
            f"({ok_n} passo(s) concluidos antes).")
