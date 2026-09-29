"""Comando de Use Computer em PT-BR: parser deterministico + execucao auditavel.

Caminho fim-a-fim:
    texto em PT-BR ("abra o bloco de notas e digite 'oi'")
        -> parse_computer_command() vira um plano de passos
        -> cada passo roda via ActionRegistry.execute (as travas valem
           para CADA passo, inclusive a do Supercerebro)

O QUE ESTE MODULO NAO FAZ (de proposito):
    - nao toca em pc_control_allowed, supercerebro_auto_off.py nem
      handle_supercerebro_toggle. A action daqui e capability PC_CONTROL,
      entao com a chave desligada o proprio registry recusa antes de
      qualquer clique. Fail-closed continua valendo.
    - nunca inventa acao: fora da lista fechada abaixo, recusa honesta.
    - nunca registra o CONTEUDO digitado no log (so a quantidade de
      caracteres): o audit nao vaza senha nem texto privado.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry

# --- tokens resolvidos na hora da execucao ---------------------------------
_HWND = "__HWND__"      # hwnd da janela ativa observada no passo 0
_CENTER = "__CENTER__"  # centro da janela ativa (para rolagem)

# --- vocabularios fechados ---------------------------------------------------
_APP_PT = {
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calculator",
    "calculator": "calculator",
    "paint": "paint",
    "chrome": "chrome",
    "navegador": "chrome",
    "edge": "edge",
    "configuracoes": "settings",
    "configurações": "settings",
    "gerenciador de tarefas": "task_manager",
    "ferramenta de captura": "snipping_tool",
}

_KEY_PT = {
    "tab": "tab",
    "enter": "enter",
    "entrar": "enter",
    "escape": "escape",
    "esc": "escape",
    "espaco": "space",
    "espaço": "space",
    "space": "space",
    "seta esquerda": "left",
    "seta direita": "right",
    "seta cima": "up",
    "seta baixo": "down",
    "inicio": "home",
    "início": "home",
    "fim": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "backspace": "backspace",
    "apagar": "backspace",
    "delete": "delete",
    "excluir": "delete",
}

_EXEMPLOS = (
    "abra o bloco de notas | clique em 500 300 | digite 'texto' | "
    "pressione enter | role para baixo 2 | traga o chrome para frente"
)

# --- parser ------------------------------------------------------------------

def _split_steps(text: str) -> list[str]:
    """Quebra em passos por ' e '/' , depois ' respeitando aspas."""
    parts, buf, quote = [], [], None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"“”":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        low = text[i:].lower()
        if low.startswith(" e depois ") or low.startswith(", depois "):
            parts.append("".join(buf).strip())
            buf = []
            i += 10 if low.startswith(" e depois ") else 9
            continue
        if low.startswith(" e ") and len("".join(buf).strip()) > 0:
            # " e " so separa se o que vem depois parece outro comando
            rest = text[i + 3:].strip().lower()
            if re.match(r"(abra|abrir|clique|click|digite|digita|escreva|pressione|aperte|role|rola|traga|foco)", rest):
                parts.append("".join(buf).strip())
                buf = []
                i += 3
                continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _parse_one(step: str) -> dict | None:
    s = step.strip()
    low = s.lower()

    m = re.fullmatch(r"(?:abra|abrir)\s+(?:o\s+|a\s+|os\s+|as\s+)?(.+?)\s*[.!?]*", low)
    if m:
        app = _APP_PT.get(m.group(1).strip())
        if app:
            return {"action": "os_app", "params": {"app": app}}
        return {"action": "os_app", "params": {"app": m.group(1).strip()}}  # os_app recusa se fora da allow-list

    m = re.fullmatch(r"(?:clique|click)(?:\s+em|\s+no\s+ponto)?\s+(\d{1,4})[\s,x×]+(\d{1,4})\s*[.!?]*", low)
    if m:
        return {"action": "computer_click",
                "params": {"x": int(m.group(1)), "y": int(m.group(2)), "expected_hwnd": _HWND}}

    m = re.fullmatch(r"(?:digite|digita|escreva|escreve)\s+['\"“”](.+?)['\"””]\s*[.!?]*", s, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return {"action": "computer_type_text",
                "params": {"text": m.group(1), "expected_hwnd": _HWND}}

    m = re.fullmatch(r"(?:pressione|aperte|tecle)\s+(.+?)\s*[.!?]*", low)
    if m:
        key = _KEY_PT.get(m.group(1).strip())
        if key:
            return {"action": "computer_press_key",
                    "params": {"key": key, "expected_hwnd": _HWND}}

    m = re.fullmatch(r"(?:role|rola)\s+para\s+(cima|baixo)(?:\s+(\d{1,2}))?\s*[.!?]*", low)
    if m:
        n = int(m.group(2)) if m.group(2) else 2
        n = max(1, min(5, n))
        steps = n if m.group(1) == "cima" else -n
        return {"action": "computer_scroll",
                "params": {"x": _CENTER, "y": _CENTER, "steps": steps, "expected_hwnd": _HWND}}

    m = re.fullmatch(r"(?:traga|coloque)\s+(?:o\s+|a\s+|os\s+|as\s+)?(?:janela\s+)?(.+?)\s+para\s+(?:a\s+)?frente\s*[.!?]*", low)
    if m:
        return {"action": "__focus_named__", "params": {"query": m.group(1).strip()}}
    m = re.fullmatch(r"foco\s+na\s+janela\s+(.+?)\s*[.!?]*", low)
    if m:
        return {"action": "__focus_named__", "params": {"query": m.group(1).strip()}}

    return None


def parse_computer_command(text: str) -> tuple[list[dict] | None, str]:
    """Vira texto PT-BR em plano de passos. Falha fechada: desconhecido -> (None, motivo)."""
    cleaned = re.sub(r"^(?:zara[,\s]+)", "", str(text or "").strip(), flags=re.IGNORECASE)
    if not cleaned:
        return None, "Comando vazio."
    raw_steps = _split_steps(cleaned)
    plan: list[dict] = []
    for raw in raw_steps:
        step = _parse_one(raw)
        if step is None:
            return None, (
                f"Não entendi o passo: '{raw}'. "
                f"Sei fazer: {_EXEMPLOS}"
            )
        plan.append(step)
    if not plan:
        return None, f"Não entendi. Sei fazer: {_EXEMPLOS}"
    return plan, ""


# --- auditoria (append-only, sem conteudo digitado) ----------------------------

def _audit_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    d = root / "data" / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / "computer_audit.jsonl"


def computer_audit(action: str, outcome: str, **details) -> None:
    """Registra UMA linha por acao de input. Nunca recebe o texto digitado."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "outcome": outcome,  # requested | success | error | blocked
    }
    for key in ("window", "x", "y", "steps", "key", "chars", "plan_steps", "error"):
        if key in details and details[key] is not None:
            value = details[key]
            entry[key] = str(value)[:200] if isinstance(value, str) else value
    try:
        with open(_audit_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # auditoria nunca quebra a execucao


# --- executor ------------------------------------------------------------------

def _resolve_focus_named(query: str) -> ActionResult:
    reg = get_registry()
    listed = reg.execute("computer_list_windows")
    if not listed.success:
        return listed
    windows = (listed.data or {}).get("windows", [])
    q = query.casefold()
    match = next((w for w in windows if q in str(w.get("title", "")).casefold()), None)
    if match is None:
        titles = [str(w.get("title", ""))[:40] for w in windows[:8]]
        return ActionResult(False, error=f"Janela '{query}' não encontrada. Visíveis: {', '.join(titles)}")
    return reg.execute("computer_focus_window", hwnd=int(match["hwnd"]))


@action(
    name="computer_command",
    category="computer",
    description="Executa um comando em PT-BR como plano de cliques/digitacao (exige Supercerebro ligado)",
    capability="PC_CONTROL",
)
def computer_command_action(command: str) -> ActionResult:
    """Plano PT-BR -> passos -> registry (trava do Supercerebro vale por passo)."""
    plan, refusal = parse_computer_command(command)
    if plan is None:
        return ActionResult(False, error=refusal)

    computer_audit("computer_command", "requested", plan_steps=len(plan))
    reg = get_registry()
    hwnd: int | None = None
    window_title = ""
    done: list[str] = []

    for idx, step in enumerate(plan):
        name = step["action"]
        params = dict(step["params"])

        if name == "__focus_named__":
            result = _resolve_focus_named(params["query"])
            computer_audit("computer_focus_window", "success" if result.success else "error",
                           window=str(params["query"])[:80],
                           error=None if result.success else result.error)
            if not result.success:
                return ActionResult(False, error=f"Passo {idx + 1} falhou: {result.error}")
            done.append(f"janela '{params['query']}' na frente")
            hwnd = None  # re-observar depois de trocar de janela
            continue

        if _HWND in params.values() or _CENTER in params.values():
            if hwnd is None:
                fg = reg.execute("computer_foreground")
                if not fg.success:
                    computer_audit(name, "blocked", error=fg.error)
                    return ActionResult(False, error=f"Passo {idx + 1}: {fg.error}")
                data = fg.data or {}
                hwnd = int(data.get("hwnd", 0)) or None
                window_title = str(data.get("title", ""))
                rect = data.get("rect") or {}
                if hwnd is None:
                    return ActionResult(False, error=f"Passo {idx + 1}: janela ativa indisponível.")
            params = {k: (hwnd if v == _HWND else v) for k, v in params.items()}
            if _CENTER in params.values():
                rect = (reg.execute("computer_foreground").data or {}).get("rect") or {}
                cx = (int(rect.get("left", 0)) + int(rect.get("right", 0))) // 2
                cy = (int(rect.get("top", 0)) + int(rect.get("bottom", 0))) // 2
                params = {k: (cx if v == _CENTER and k == "x" else cy if v == _CENTER and k == "y" else v)
                          for k, v in params.items()}

        result = reg.execute(name, **params)
        audit_extra: dict = {"window": window_title[:80]}
        if name == "computer_click":
            audit_extra.update(x=params.get("x"), y=params.get("y"))
        elif name == "computer_scroll":
            audit_extra.update(steps=params.get("steps"))
        elif name == "computer_press_key":
            audit_extra.update(key=params.get("key"))
        elif name == "computer_type_text":
            audit_extra.update(chars=len(str(params.get("text", ""))))
        computer_audit(name, "success" if result.success else "error",
                       error=None if result.success else result.error, **audit_extra)

        if not result.success:
            return ActionResult(
                False,
                error=f"Passo {idx + 1} de {len(plan)} falhou ({name}): {result.error}",
            )
        done.append(name)
        if "mudou" in (result.error or "") or "Mudou" in (result.error or ""):
            hwnd = None  # janela trocou no meio: re-observar no proximo passo

    return ActionResult(True, output="; ".join(done), verificado=True)
