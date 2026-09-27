from core.voice_engine_policy import voice_output_order


def test_kore_is_default_and_omnivoice_is_the_first_local_fallback():
    assert voice_output_order(
        "kore", kore_ready=True, omnivoice_ready=True, edge_ready=True,
        kokoro_ready=True,
    ) == ("kore", "omnivoice", "edge", "kokoro")


def test_manual_omnivoice_selection_starts_local_without_kore():
    assert voice_output_order(
        "omnivoice", kore_ready=True, omnivoice_ready=True, edge_ready=True,
        kokoro_ready=True,
    ) == ("omnivoice", "edge", "kokoro")


def test_missing_selected_omnivoice_degrades_to_ready_kore_then_local_fallbacks():
    assert voice_output_order(
        "omnivoice", kore_ready=True, omnivoice_ready=False, edge_ready=True,
        kokoro_ready=True,
    ) == ("kore", "edge", "kokoro")


def test_missing_kore_starts_with_omnivoice_without_breaking_other_fallbacks():
    assert voice_output_order(
        "kore", kore_ready=False, omnivoice_ready=True, edge_ready=False,
        kokoro_ready=True,
    ) == ("omnivoice", "kokoro")


def test_unrecognized_preference_fails_closed_to_kore_policy():
    assert voice_output_order(
        "unknown", kore_ready=True, omnivoice_ready=True, edge_ready=True,
        kokoro_ready=False,
    ) == ("kore", "omnivoice", "edge")
