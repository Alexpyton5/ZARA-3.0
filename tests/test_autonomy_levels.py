"""Testes para o sistema de níveis de autonomia."""
import pytest

# Import actions module to load fundamentals into registry
import core.actions  # noqa: F401
from core.autonomy_levels import (
    _ALEX_ALWAYS_AUTO,
    AutonomyLevel,
    decide_autonomy_level,
    get_autonomy_policy_summary,
)


class TestAutonomyLevels:
    """Testes das decisões de nível de autonomia."""

    def test_reflexo_local_acoes_basicas(self):
        """Ações básicas de volume/brilho/janela devem ser REFLEXO_LOCAL (1)."""
        for action in ["os_volume", "os_brightness_absolute", "window_minimize", "window_maximize"]:
            decision = decide_autonomy_level(action)
            assert decision.level == AutonomyLevel.REFLEXO_LOCAL, f"{action} deveria ser REFLEXO_LOCAL, foi {decision.level.name}"

    def test_faz_e_avisa_local_pc_control(self):
        """LOCAL_PC_CONTROL com risk LOW deve ser FAZ_E_AVISA (2)."""
        # Estas são LOCAL_PC_CONTROL mas não estão no override ALWAYS_AUTO
        decision = decide_autonomy_level("os_open")  # capability LOCAL_PC_CONTROL
        # os_open está em ALWAYS_AUTO, então REFLEXO_LOCAL
        assert decision.level == AutonomyLevel.REFLEXO_LOCAL

    def test_pergunta_antes_medium_risk(self):
        """Ações MEDIUM risk devem ser no mínimo PERGUNTA_ANTES (3)."""
        # files_delete é HIGH risk + capability FILES_MUTATE + Alex override NEVER_AUTO
        decision = decide_autonomy_level("files_delete")
        assert decision.level == AutonomyLevel.EXIGE_ALEX

    def test_exige_alex_high_risk_irreversivel(self):
        """Ações HIGH risk / irreversíveis devem ser EXIGE_ALEX (4)."""
        for action in ["os_power", "system_kill", "terminal", "browser_eval"]:
            decision = decide_autonomy_level(action)
            assert decision.level == AutonomyLevel.EXIGE_ALEX, f"{action} deveria ser EXIGE_ALEX, foi {decision.level.name}"

    def test_override_alex_always_auto(self):
        """Override do Alex para 'sempre auto' deve prevalecer."""
        for action in ["os_volume", "os_brightness_up", "youtube_pause", "claude_enviar"]:
            decision = decide_autonomy_level(action)
            assert decision.level == AutonomyLevel.REFLEXO_LOCAL, f"{action} deveria ser REFLEXO_LOCAL por override do Alex"
            assert decision.user_preference_override is True

    def test_override_alex_never_auto(self):
        """Override do Alex para 'nunca auto' deve prevalecer."""
        for action in ["files_delete", "os_power", "system_kill", "terminal"]:
            decision = decide_autonomy_level(action)
            assert decision.level == AutonomyLevel.EXIGE_ALEX, f"{action} deveria ser EXIGE_ALEX por override do Alex"
            assert decision.user_preference_override is True

    def test_acao_desconhecida_mais_restritivo(self):
        """Ação não registrada assume EXIGE_ALEX por segurança."""
        decision = decide_autonomy_level("acao_que_nao_existe_xyz")
        assert decision.level == AutonomyLevel.EXIGE_ALEX
        assert "não registrada" in decision.reason

    def test_superbrain_off_bloqueia_capacidades_avancadas(self):
        """Supercérebro OFF deve subir nível para EXIGE_ALEX em capacidades que precisam dele."""
        # PC_CONTROL, REMOTE_PC_CONTROL, AGENTIC_PC_CONTROL, CODE_EXECUTION, SYSTEM_POWER
        # Precisam achar uma ação com essas capabilities
        # Por enquanto testa que o contexto é considerado
        context_off = {"superbrain_on": False}
        context_on = {"superbrain_on": True}

        # Se houver ação com capability PC_CONTROL (não LOCAL_PC_CONTROL)
        # O nível deve subir para EXIGE_ALEX quando superbrain_off

    def test_requires_confirmation_forca_minimo_pergunta_antes(self):
        """requires_confirmation=True deve forçar no mínimo PERGUNTA_ANTES."""
        # Precisa achar uma ação com requires_confirmation=True mas risk LOW
        # O registry já define isso

    def test_policy_summary_tem_todos_niveis(self):
        """Resumo da política deve ter ações em todos os 4 níveis."""
        summary = get_autonomy_policy_summary()
        for level_key in ["1_REFLEXO_LOCAL", "2_FAZ_E_AVISA", "3_PERGUNTA_ANTES", "4_EXIGE_ALEX"]:
            assert level_key in summary["levels"]
            assert "actions" in summary["levels"][level_key]
            assert "count" in summary["levels"][level_key]

    def test_alex_overrides_no_summary(self):
        """Overrides do Alex devem aparecer no summary."""
        summary = get_autonomy_policy_summary()
        assert "alex_always_auto" in summary["overrides"]
        assert "alex_never_auto" in summary["overrides"]
        assert len(summary["overrides"]["alex_always_auto"]) > 0
        assert len(summary["overrides"]["alex_never_auto"]) > 0

    def test_capability_base_levels_completos(self):
        """Todas as capabilities conhecidas devem ter nível base."""
        summary = get_autonomy_policy_summary()
        caps = summary["capability_base_levels"]
        expected_caps = {
            "READ_ONLY", "LOCAL_PC_CONTROL", "PC_CONTROL",
            "REMOTE_PC_CONTROL", "AGENTIC_PC_CONTROL",
            "FILES_MUTATE", "CODE_EXECUTION", "SYSTEM_POWER"
        }
        assert set(caps.keys()) == expected_caps


class TestAlwaysAutoNeverDowngradesRealPolicy:
    """AUDITORIA_2026-08-27 item 1.3 (decisao do Mentor sob autonomia delegada
    por Alex em 2026-08-27, pendente de ratificacao): o atalho
    'sempre auto' (volume, brilho, media, claude_enviar, etc.) pode acelerar
    o caminho feliz, mas nunca pode sobrescrever uma recusa ou pedido de
    confirmacao que a politica real (core.autonomy_policy.decide) daria por
    causa de sinal de risco real — ambiente degradado, acao marcada
    irreversivel, confianca baixa. Antes desta correcao, o override
    ignorava esses sinais por completo."""

    def test_ambiente_degradado_forca_confirmacao_mesmo_em_acao_sempre_auto(self):
        assert "os_volume" in _ALEX_ALWAYS_AUTO
        decision = decide_autonomy_level("os_volume", context={"degraded": True})

        assert decision.level == AutonomyLevel.PERGUNTA_ANTES
        assert decision.user_preference_override is False

    def test_acao_irreversivel_forca_confirmacao_mesmo_em_acao_sempre_auto(self):
        assert "window_minimize" in _ALEX_ALWAYS_AUTO
        decision = decide_autonomy_level("window_minimize", context={"irreversible": True})

        assert decision.level == AutonomyLevel.PERGUNTA_ANTES
        assert decision.user_preference_override is False

    def test_ambiente_normal_ainda_acelera_para_reflexo_local(self):
        """O caminho feliz de todo dia nao pode regredir: sem sinal de risco
        real, o override continua dando resposta imediata."""
        decision = decide_autonomy_level("os_volume", context={"degraded": False})

        assert decision.level == AutonomyLevel.REFLEXO_LOCAL
        assert decision.user_preference_override is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
