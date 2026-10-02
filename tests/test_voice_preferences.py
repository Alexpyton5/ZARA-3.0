import json

from core.voice_preferences import load_voice_output_engine, save_voice_output_engine


def test_voice_output_defaults_to_kore_when_preferences_are_missing(tmp_path):
    assert load_voice_output_engine(tmp_path / "voice_preferences.json") == "kore"


def test_voice_output_preference_persists_only_the_selection(tmp_path):
    path = tmp_path / "config" / "voice_preferences.json"

    # OmniVoice removido (02/10): o nome antigo mapeia pra "kore".
    assert save_voice_output_engine("omnivoice", path) == "kore"
    assert load_voice_output_engine(path) == "kore"
    assert json.loads(path.read_text(encoding="utf-8")) == {"output_engine": "kore"}


def test_invalid_voice_output_preference_fails_closed_to_kore(tmp_path):
    path = tmp_path / "voice_preferences.json"
    path.write_text('{"output_engine":"unknown"}', encoding="utf-8")

    assert load_voice_output_engine(path) == "kore"
    assert save_voice_output_engine("unknown", path) == "kore"
