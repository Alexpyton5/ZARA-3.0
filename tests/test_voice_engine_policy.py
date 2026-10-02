from core.voice_engine_policy import normalize_voice_engine, voice_output_order


def test_kore_is_default_with_edge_then_kokoro_fallbacks():
    assert voice_output_order(
        "kore", kore_ready=True, edge_ready=True,
        kokoro_ready=True,
    ) == ("kore", "edge", "kokoro")


def test_legacy_omnivoice_selection_maps_to_kore():
    # OmniVoice removido (02/10, decisao do Alex): o nome antigo nao pode
    # quebrar — cai pra kore.
    assert normalize_voice_engine("omnivoice") == "kore"
    assert voice_output_order(
        "omnivoice", kore_ready=True, edge_ready=True,
        kokoro_ready=True,
    ) == ("kore", "edge", "kokoro")


def test_missing_kore_starts_with_edge_then_kokoro():
    assert voice_output_order(
        "kore", kore_ready=False, edge_ready=True,
        kokoro_ready=True,
    ) == ("edge", "kokoro")


def test_only_kokoro_ready_yields_kokoro_alone():
    assert voice_output_order(
        "kore", kore_ready=False, edge_ready=False,
        kokoro_ready=True,
    ) == ("kokoro",)


def test_nothing_ready_yields_empty_order():
    assert voice_output_order(
        "kore", kore_ready=False, edge_ready=False,
        kokoro_ready=False,
    ) == ()


def test_unrecognized_preference_fails_closed_to_kore_policy():
    assert voice_output_order(
        "unknown", kore_ready=True, edge_ready=True,
        kokoro_ready=False,
    ) == ("kore", "edge")
