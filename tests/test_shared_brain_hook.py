import json
from pathlib import Path

import pytest

from core import obsidian_memory
from memory import second_brain_composition
from tools import shared_brain_hook


DEFAULT_BRIEFING = "briefing-tropa-dev-codex-2026-09-30.md"


@pytest.fixture
def hook_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    project = vault / "20-PROJETO-ZARA"
    project.mkdir(parents=True)
    (vault / "INDICE.md").write_text("INDEX-CURRENT", encoding="utf-8")
    (project / "VISAO-TROPA-DEV.md").write_text(
        "VISION-CURRENT [[briefing-tropa-dev-codex-2026-09-30]]", encoding="utf-8"
    )
    (project / DEFAULT_BRIEFING).write_text("BRIEFING-CURRENT", encoding="utf-8")
    manager = obsidian_memory.ObsidianMemoryManager(vault_path=vault)
    monkeypatch.setattr(obsidian_memory, "ObsidianMemoryManager", lambda: manager)

    def no_startup_query(**_kwargs):
        raise AssertionError("SessionStart must not build or search a derived index")

    monkeypatch.setattr(second_brain_composition, "build_shared_second_brain", no_startup_query)
    # The repository's current mission must never contaminate temporary-vault tests.
    workspace = tmp_path / "workspace"
    (workspace / ".claude").mkdir(parents=True)
    (workspace / ".claude/CURRENT_MISSION.md").write_text("RESUME-CURRENT", encoding="utf-8")
    monkeypatch.setattr(shared_brain_hook, "ROOT", workspace)
    return vault


def start_context():
    result = shared_brain_hook.hook({"hook_event_name": "SessionStart"})
    return result["hookSpecificOutput"]["additionalContext"]


def test_session_start_reads_canonical_notes_without_a_search(hook_vault):
    context = start_context()
    for marker in ("INDEX-CURRENT", "VISION-CURRENT", "BRIEFING-CURRENT", "RESUME-CURRENT"):
        assert marker in context
    assert "referência" in context
    assert "permiss" in context


def test_session_start_sees_file_edits_without_restart(hook_vault):
    assert "BRIEFING-CURRENT" in start_context()
    note = hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING
    note.write_text("BRIEFING-UPDATED", encoding="utf-8")
    context = start_context()
    assert "BRIEFING-UPDATED" in context
    assert "BRIEFING-CURRENT" not in context


def test_session_start_follows_the_briefing_link_in_the_current_vision(hook_vault):
    project = hook_vault / "20-PROJETO-ZARA"
    (project / "VISAO-TROPA-DEV.md").write_text(
        "VISION-NEXT [[briefing-tropa-dev-codex-2026-10-02|briefing vigente]]", encoding="utf-8"
    )
    (project / "briefing-tropa-dev-codex-2026-10-02.md").write_text("BRIEFING-NEXT", encoding="utf-8")
    context = start_context()
    assert "BRIEFING-NEXT" in context
    assert "BRIEFING-CURRENT" not in context


def test_missing_linked_briefing_is_reported_without_old_fallback(hook_vault):
    (hook_vault / "20-PROJETO-ZARA/VISAO-TROPA-DEV.md").write_text(
        "[[briefing-tropa-dev-codex-2026-10-02]]", encoding="utf-8"
    )
    context = start_context()
    assert "briefing-tropa-dev-codex-2026-10-02.md" in context
    assert "indispon" in context
    assert "BRIEFING-CURRENT" not in context


@pytest.mark.parametrize("link", [
    "briefing-tropa-dev-codex-2026-10-02.md",
    "20-PROJETO-ZARA/briefing-tropa-dev-codex-2026-10-02.md#Plano|briefing vigente",
])
def test_valid_obsidian_link_formats_select_the_current_briefing(hook_vault, link):
    project = hook_vault / "20-PROJETO-ZARA"
    (project / "VISAO-TROPA-DEV.md").write_text(f"VISION-NEXT [[{link}]]", encoding="utf-8")
    (project / "briefing-tropa-dev-codex-2026-10-02.md").write_text("BRIEFING-NEXT", encoding="utf-8")
    context = start_context()
    assert "BRIEFING-NEXT" in context
    assert "BRIEFING-CURRENT" not in context


def test_missing_vision_cannot_silently_select_the_old_briefing(hook_vault):
    (hook_vault / "20-PROJETO-ZARA/VISAO-TROPA-DEV.md").unlink()
    context = start_context()
    assert "BRIEFING-CURRENT" not in context
    assert "indispon" in context


def test_conflicting_briefing_links_are_reported_instead_of_picking_history(hook_vault):
    project = hook_vault / "20-PROJETO-ZARA"
    (project / "VISAO-TROPA-DEV.md").write_text(
        "Historico [[briefing-tropa-dev-codex-2026-09-30]]. "
        "Ordens vigentes [[briefing-tropa-dev-codex-2026-10-02|briefing vigente]].",
        encoding="utf-8"
    )
    (project / "briefing-tropa-dev-codex-2026-10-02.md").write_text("BRIEFING-NEXT", encoding="utf-8")
    context = start_context()
    assert "BRIEFING-CURRENT" not in context
    assert "BRIEFING-NEXT" not in context
    assert "amb" in context


def test_incomplete_current_link_cannot_make_a_historical_link_win(hook_vault):
    project = hook_vault / "20-PROJETO-ZARA"
    (project / "VISAO-TROPA-DEV.md").write_text(
        "Historico [[briefing-tropa-dev-codex-2026-09-30]]. "
        "Vigente [[briefing-tropa-dev-codex-2026-10-02.md", encoding="utf-8"
    )
    (project / "briefing-tropa-dev-codex-2026-10-02.md").write_text("BRIEFING-NEXT", encoding="utf-8")
    context = start_context()
    assert "BRIEFING-CURRENT" not in context
    assert "BRIEFING-NEXT" not in context
    assert "inválida" in context


@pytest.mark.parametrize("private_note", ["INDICE.md", "20-PROJETO-ZARA/VISAO-TROPA-DEV.md",
                                          "20-PROJETO-ZARA/" + DEFAULT_BRIEFING])
def test_a_secret_after_the_excerpt_boundary_is_never_rendered(hook_vault, private_note):
    (hook_vault / private_note).write_text("PUBLIC " * 1800 + "password=private-example", encoding="utf-8")
    context = start_context()
    assert "private-example" not in context
    assert "PUBLIC" not in context
    assert "omitid" in context


def test_unavailable_vault_is_explicit(hook_vault):
    hook_vault.rename(hook_vault.with_name("offline"))
    context = start_context()
    assert "indispon" in context
    assert "VISION-CURRENT" not in context


def test_missing_notes_are_explicit_and_do_not_hide_available_notes(hook_vault):
    (hook_vault / "INDICE.md").unlink()
    context = start_context()
    assert "INDICE.md" in context and "indispon" in context
    assert "VISION-CURRENT" in context


def test_a_negative_mention_of_api_keys_does_not_hide_the_briefing(hook_vault):
    original = "BRIEFING-CURRENT: local, sem API key, sem custo."
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(
        original, encoding="utf-8"
    )
    assert original in start_context()


@pytest.mark.parametrize("assignment", ["sem API key=private-example", "sem API key: private-example"])
def test_a_negative_key_assignment_after_the_excerpt_omits_the_whole_note(hook_vault, assignment):
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(
        "PUBLIC " * 1800 + assignment, encoding="utf-8"
    )
    context = start_context()
    assert "private-example" not in context
    assert "PUBLIC" not in context
    assert "omitid" in context


def test_negative_key_mention_cannot_hide_an_actual_key_assignment(hook_vault):
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(
        "Local, sem API key, sem custo.\napi_key=private-example", encoding="utf-8"
    )
    context = start_context()
    assert "private-example" not in context
    assert "Local, sem API key" not in context
    assert "omitid" in context


def test_the_documented_decision_function_is_not_mistaken_for_a_key(hook_vault):
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(
        "BRIEFING-CURRENT: use core.decision_service.ask_decision(state, questions).", encoding="utf-8"
    )
    context = start_context()
    assert "BRIEFING-CURRENT: use" in context
    assert "ask_decision(state, questions)" in context


def test_documented_function_cannot_hide_a_real_key_in_the_same_note(hook_vault):
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(
        "Use ask_decision(state, questions).\napi_key=private-example", encoding="utf-8"
    )
    context = start_context()
    assert "private-example" not in context
    assert "Use ask_decision" not in context


def test_large_public_notes_are_bounded_and_truncation_is_explicit(hook_vault):
    for note in hook_vault.rglob("*.md"):
        note.write_text("PUBLIC-CONTEXT " * 3500, encoding="utf-8")
    context = start_context()
    assert len(context) <= 24000
    assert "limitad" in context
    assert "VISAO-TROPA-DEV.md" in context
    assert DEFAULT_BRIEFING in context


def test_symlink_escape_is_not_read(hook_vault, monkeypatch):
    note = hook_vault / "INDICE.md"
    original_resolve = Path.resolve

    def outside_for_index(path, *args, **kwargs):
        if path == note:
            return hook_vault.parent / "outside.md"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", outside_for_index)
    context = start_context()
    assert "INDEX-CURRENT" not in context
    assert "omitid" in context


def test_replacement_between_resolve_and_open_cannot_render_an_external_file(hook_vault, monkeypatch):
    outside = hook_vault.parent / "outside.md"
    outside.write_text("EXTERNAL-CONTEXT", encoding="utf-8")
    note = hook_vault / "INDICE.md"
    original_open = Path.open

    def replaced_open(path, *args, **kwargs):
        if path == note:
            return original_open(outside, *args, **kwargs)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replaced_open)
    context = start_context()
    assert "EXTERNAL-CONTEXT" not in context
    assert "omitid" in context


def test_unknown_events_are_ignored():
    assert shared_brain_hook.hook({"hook_event_name": "OtherEvent"}) == {}


def test_prompt_submit_retains_query_specific_context(monkeypatch):
    brain = object()
    monkeypatch.setattr(obsidian_memory, "ObsidianMemoryManager", lambda: object())
    monkeypatch.setattr(second_brain_composition, "build_shared_second_brain", lambda **_kwargs: brain)
    from memory import pilot_context

    calls = []

    def build(actual_brain, prompt, **_kwargs):
        calls.append((actual_brain, prompt))
        return {"context": "QUERY-CURRENT"}

    monkeypatch.setattr(pilot_context, "build_pilot_context", build)
    result = shared_brain_hook.hook({"hook_event_name": "UserPromptSubmit", "prompt": "Qual entrega falta?"})
    assert calls == [(brain, "Qual entrega falta?")]
    assert result["hookSpecificOutput"]["additionalContext"] == "QUERY-CURRENT"


def test_main_emits_only_valid_json(hook_vault, monkeypatch, capsys):
    from io import StringIO
    original = "BRIEFING-CURRENT: sem API key, use ask_decision(state, questions)."
    (hook_vault / "20-PROJETO-ZARA" / DEFAULT_BRIEFING).write_text(original, encoding="utf-8")
    monkeypatch.setattr(shared_brain_hook.sys, "stdin", StringIO('{"hook_event_name":"SessionStart"}'))
    assert shared_brain_hook.main() == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert "VISION-CURRENT" in result["hookSpecificOutput"]["additionalContext"]
    assert original in result["hookSpecificOutput"]["additionalContext"]
