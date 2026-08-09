"""Focused natural-language coverage for the existing PC volume capability."""

import pytest

from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("utterance", "expected_param"),
    [
        ("Zara, abaixa um pouco o som", "down"),
        ("por favor diminui o volume", "down"),
        ("menos som", "down"),
        ("Zara, aumenta um pouco o volume", "up"),
        ("sobe o som", "up"),
        ("mais volume", "up"),
        ("coloca o volume em 30%", "30"),
        ("Zara, põe o som no 45", "45"),
    ],
)
def test_volume_language_variants_map_to_existing_action(utterance, expected_param):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(utterance)

    assert result.is_pc_intent is True
    assert result.action == "os_volume"
    assert result.param == expected_param
    assert result.blocked is False
    assert result.physical_effect == 1


def test_natural_volume_command_preserves_supercerebro_gate():
    result = PcVoiceIntentDetector(pc_control_allowed=False).detect(
        "Zara, abaixa um pouco o som"
    )

    assert result.is_pc_intent is True
    assert result.action == "os_volume"
    assert result.param == "down"
    assert result.blocked is True
    assert result.physical_effect == 0
    assert "Supercérebro" in result.reply


def test_volume_description_is_not_mistaken_for_a_command():
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(
        "o som está baixo hoje"
    )

    assert result.is_pc_intent is False
