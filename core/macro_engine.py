"""ZARA-MACRO-ENGINE-001 (Alex, 2026-08-28). Peça isolada, não plugada.

Item (j) do "Motor Universal" do backlog -- macros/cenários que agrupam
várias ações já existentes num comando conceitual só ("modo noite", "fechar
o dia"). Reusa NOMES de ações já registradas no ActionRegistry
(core/action_registry.py) em vez de reimplementar controle de PC -- este
módulo só monta a SEQUÊNCIA, no mesmo formato de
`core/multi_intent_parser.py` (`[{"action":..., "param":...}]`). Não executa
nada sozinho: quem consumir a lista decide, passo a passo, os mesmos gates
de segurança que qualquer ação já passa hoje (capability, allowlist).

Traz pronto o "Modo Encerramento de Expediente" pedido por Alex: sugere
mensagem de commit (tools/git_assistant.py, nunca commita sozinho), fecha
abas do navegador, resume o dia (via texto passado por quem chamar -- este
módulo não inventa o que foi feito), e devolve a ação de hibernar como
ÚLTIMO passo da lista, nunca disparada por conta própria.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MacroStep:
    action: str | None
    param: str | None = None
    note: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    when: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Macro:
    name: str
    steps: tuple[MacroStep, ...]


_REGISTRY: dict[str, Macro] = {}


def register_macro(macro: Macro) -> None:
    name = str(macro.name or "").strip().lower()
    if not name:
        raise ValueError("Macro precisa de nome")
    if not macro.steps:
        raise ValueError("Macro precisa de pelo menos um passo")
    _REGISTRY[name] = Macro(name=name, steps=tuple(macro.steps))


def unregister_macro(name: str) -> bool:
    return _REGISTRY.pop(str(name or "").strip().lower(), None) is not None


def get_macro(name: str) -> Macro | None:
    return _REGISTRY.get(str(name or "").strip().lower())


def list_macros() -> list[str]:
    return sorted(_REGISTRY)


def macro_from_dict(data: dict[str, Any]) -> Macro:
    steps = []
    for raw in data.get("steps") or []:
        if not isinstance(raw, dict):
            raise ValueError("Cada passo da macro deve ser um objeto")
        action_name = raw.get("action")
        if action_name is not None:
            action_name = str(action_name).strip()
            if not action_name:
                raise ValueError("Nome de acao vazio")
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params deve ser um objeto")
        when = raw.get("when")
        if when is not None and not isinstance(when, dict):
            raise ValueError("when deve ser um objeto")
        steps.append(MacroStep(action_name, raw.get("param"), str(raw.get("note") or ""), params, when))
    return Macro(name=str(data.get("name") or ""), steps=tuple(steps))


def macro_to_dict(macro: Macro) -> dict[str, Any]:
    return {
        "name": macro.name,
        "steps": [
            {"action": step.action, "param": step.param, "note": step.note, "params": step.params, "when": step.when}
            for step in macro.steps
        ],
    }


def resolve_dynamic(value: Any, parameters: dict[str, Any]) -> Any:
    """Resolve only explicit ``{name}`` placeholders; unknown names fail."""
    if isinstance(value, str):
        if value.startswith("{") and value.endswith("}") and value.count("{") == 1:
            key = value[1:-1]
            if key not in parameters:
                raise KeyError(key)
            return parameters[key]
        try:
            return value.format_map(parameters)
        except KeyError:
            raise
    if isinstance(value, list):
        return [resolve_dynamic(item, parameters) for item in value]
    if isinstance(value, dict):
        return {key: resolve_dynamic(item, parameters) for key, item in value.items()}
    return value


def condition_matches(condition: dict[str, Any] | None, parameters: dict[str, Any], results: list[dict[str, Any]]) -> bool:
    if not condition:
        return True
    if "param" in condition:
        actual = parameters.get(str(condition["param"]))
        if "equals" in condition:
            return actual == condition["equals"]
        if "not_equals" in condition:
            return actual != condition["not_equals"]
        return bool(actual)
    if "step" in condition:
        index = int(condition["step"])
        if index < 0 or index >= len(results):
            return False
        expected = bool(condition.get("success", True))
        return bool(results[index].get("success")) is expected
    raise ValueError("Condicao precisa usar param ou step")


def build_end_of_day_macro(*, commit_suggestion: str | None = None, summary_text: str | None = None) -> Macro:
    """Monta o 'Modo Encerramento de Expediente'. `commit_suggestion` vem de
    `tools.git_assistant.generate_smart_commit` (chamado por quem monta o
    macro, não aqui, pra não misturar responsabilidade). Hibernar é sempre o
    ÚLTIMO passo."""
    steps: list[MacroStep] = []
    if commit_suggestion:
        steps.append(MacroStep(
            action=None,
            param=commit_suggestion,
            note="Sugestão de commit -- executar exige confirmação humana, esta peça nunca commita sozinha.",
        ))
    steps.append(MacroStep(action="browser_close_tab", param="all", note="Fecha as abas do navegador."))
    if summary_text:
        steps.append(MacroStep(action="os_notify", param=summary_text, note="Resumo do dia."))
    steps.append(MacroStep(action="os_power", param="hibernate", note="ÚLTIMO passo -- hiberna a máquina."))
    return Macro(name="modo_encerramento_expediente", steps=tuple(steps))


def build_night_mode_macro() -> Macro:
    """'Modo Noite' -- exemplo simples de macro puramente de reflexo local
    (sem dependência de rede), combinando ações já existentes."""
    steps = (
        MacroStep(action="os_night_light_on", param="on"),
        MacroStep(action="os_volume", param="down_muito"),
        MacroStep(action="os_brightness_absolute", param="20"),
    )
    return Macro(name="modo_noite", steps=steps)


register_macro(build_night_mode_macro())
