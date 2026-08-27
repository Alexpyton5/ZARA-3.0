"""Autonomy Levels — Wrapper over the unified autonomy policy.

This module provides a simplified API for the 4-level autonomy system,
delegating to the core policy in `core.autonomy_policy`.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.autonomy_policy import (
    ActionRiskProfile,
    ApprovalSignal,
    AutonomyRequest,
    EnvironmentSignal,
    Verdict,
    decide,
)

# Re-export the core types
__all__ = [
    "AutonomyLevel",
    "decide_autonomy_level",
    "get_autonomy_policy_summary",
    "_ALEX_ALWAYS_AUTO",
    "_ALEX_NEVER_AUTO",
]


class AutonomyLevel:
    """Four autonomy levels (1=most permissive, 4=most restrictive)."""
    REFLEXO_LOCAL = 1      # Executa sem avisar
    FAZ_E_AVISA = 2        # Executa e avisa depois
    PERGUNTA_ANTES = 3     # Pede confirmação antes
    EXIGE_ALEX = 4         # Só com autorização explícita do Alex


# Override lists (populated from autonomy_policy if available)
_ALEX_ALWAYS_AUTO = {
    "os_volume", "os_brightness_up", "os_brightness_down",
    "youtube_pause", "youtube_play", "claude_enviar",
    "audio_mute", "audio_unmute", "window_minimize",
    "window_maximize", "window_restore", "media_play_pause",
}

_ALEX_NEVER_AUTO = {
    "files_delete", "os_power", "system_kill", "terminal",
    "browser_eval", "code_format", "code_test", "web_download",
}


def _risk_profile_from_action_name(action_name: str) -> ActionRiskProfile:
    """Get risk profile from action registry."""
    try:
        from core.action_registry import get_registry
        spec = get_registry().get_spec(action_name)
        if spec:
            return ActionRiskProfile(
                risk=spec.risk,
                capability=spec.capability,
                known=True,
                requires_confirmation=spec.requires_confirmation,
            )
    except Exception:
        pass
    # Unknown action = fail closed
    return ActionRiskProfile(risk="UNKNOWN", capability="UNKNOWN", known=False)


def decide_autonomy_level(action_name: str, context: dict | None = None) -> AutonomyDecision:
    """Decide autonomy level for an action.

    Args:
        action_name: Name of the action.
        context: Optional context with superbrain_on, network_available, degraded.

    Returns:
        AutonomyDecision with level, reason, and override flags.
    """
    ctx = context or {}
    env = EnvironmentSignal(
        degraded=ctx.get("degraded", False),
        superbrain_on=ctx.get("superbrain_on", True),
        network_available=ctx.get("network_available", True),
    )

    risk_profile = _risk_profile_from_action_name(action_name)
    request = AutonomyRequest(
        action_name=action_name,
        confidence=ctx.get("confidence", 0.95),
        irreversible=ctx.get("irreversible", False),
        configured_level=None,  # Could be derived from user preferences
        risk_profile=risk_profile,
        environment=env,
        approval=ApprovalSignal(),
    )

    decision = decide(request)

    # Map verdict to autonomy level
    level_map = {
        Verdict.AUTO: AutonomyLevel.REFLEXO_LOCAL,
        Verdict.AUTO_E_AVISA: AutonomyLevel.FAZ_E_AVISA,
        Verdict.PEDE_CONFIRMACAO: AutonomyLevel.PERGUNTA_ANTES,
        Verdict.RECUSA: AutonomyLevel.EXIGE_ALEX,
    }
    policy_level = level_map.get(decision.verdict, AutonomyLevel.EXIGE_ALEX)

    # Check user overrides.
    # AUDITORIA_2026-08-27 item 1.3 (decisao do Mentor sob autonomia delegada
    # por Alex, pendente de ratificacao — Alex nao escolheu entre as opcoes,
    # pediu para o Mentor decidir): o atalho "sempre auto"
    # so pode SUBIR a permissividade da politica real, nunca descer. Antes,
    # ele sobrescrevia RECUSA/PEDE_CONFIRMACAO (ambiente degradado, acao
    # marcada irreversivel, confianca baixa etc.) e forcava REFLEXO_LOCAL de
    # qualquer jeito — um bypass estrutural do risco real. Agora, se a
    # politica ja mandaria pedir confirmacao ou recusar, isso prevalece; o
    # override so acelera o caminho feliz (AUTO / AUTO_E_AVISA).
    user_override = False
    if action_name in _ALEX_ALWAYS_AUTO:
        if policy_level in (AutonomyLevel.REFLEXO_LOCAL, AutonomyLevel.FAZ_E_AVISA):
            user_override = True
            level = AutonomyLevel.REFLEXO_LOCAL
        else:
            level = policy_level
    elif action_name in _ALEX_NEVER_AUTO:
        user_override = True
        level = AutonomyLevel.EXIGE_ALEX
    else:
        level = policy_level

    return AutonomyDecision(
        level=level,
        reason=decision.reason,
        user_preference_override=user_override,
        verdict=decision.verdict,
    )


@dataclass
class AutonomyDecision:
    level: int
    reason: str
    user_preference_override: bool = False
    verdict: Verdict = Verdict.RECUSA


def get_autonomy_policy_summary() -> dict:
    """Get summary of all actions grouped by autonomy level."""
    from core.action_registry import get_registry

    registry = get_registry()
    summary = {
        "levels": {
            "1_REFLEXO_LOCAL": {"actions": [], "count": 0},
            "2_FAZ_E_AVISA": {"actions": [], "count": 0},
            "3_PERGUNTA_ANTES": {"actions": [], "count": 0},
            "4_EXIGE_ALEX": {"actions": [], "count": 0},
        },
        "overrides": {
            "alex_always_auto": sorted(_ALEX_ALWAYS_AUTO),
            "alex_never_auto": sorted(_ALEX_NEVER_AUTO),
        },
        "capability_base_levels": {
            "READ_ONLY": "REFLEXO_LOCAL",
            "LOCAL_PC_CONTROL": "FAZ_E_AVISA",
            "PC_CONTROL": "PERGUNTA_ANTES",
            "REMOTE_PC_CONTROL": "EXIGE_ALEX",
            "AGENTIC_PC_CONTROL": "EXIGE_ALEX",
            "FILES_MUTATE": "PERGUNTA_ANTES",
            "CODE_EXECUTION": "EXIGE_ALEX",
            "SYSTEM_POWER": "EXIGE_ALEX",
        },
    }

    for action_name in registry.list_actions():
        decision = decide_autonomy_level(action_name)
        level_key = f"{decision.level}_{decision.verdict.name}"
        if level_key in summary["levels"]:
            summary["levels"][level_key]["actions"].append(action_name)
            summary["levels"][level_key]["count"] += 1

    return summary
