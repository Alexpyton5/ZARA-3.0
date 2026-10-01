from memory.pilot_context import build_pilot_context
from memory.shared_second_brain import SharedSecondBrain


def make_brain(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return SharedSecondBrain(user_memory=None, lab_store=None, project_workspace=None,
                             obsidian_vault=vault, obsidian_index_db=tmp_path / "index.db")


def test_query_sees_other_members_edits_and_deletions_without_restart(tmp_path):
    brain = make_brain(tmp_path)
    note = brain.obsidian_vault / "crew.md"
    note.write_text("Tropa crew agora faz tarefa azul", encoding="utf-8")
    assert "azul" in brain.query("crew")['items'][0]['text']
    note.write_text("Tropa crew agora faz tarefa verde", encoding="utf-8")
    assert "verde" in brain.query("crew")['items'][0]['text']
    note.unlink()
    assert not brain.query("crew")['items']


def test_new_secret_replaces_cached_public_note_without_leaking(tmp_path):
    brain = make_brain(tmp_path)
    note = brain.obsidian_vault / "crew.md"
    note.write_text("crew tem tarefa publica", encoding="utf-8")
    assert brain.query("crew")['items']
    note.write_text("crew password=private-example", encoding="utf-8")
    assert not brain.query("crew")['items']


def test_pilot_keeps_excerpt_of_long_note_with_provenance_and_boundary(tmp_path):
    brain = make_brain(tmp_path)
    (brain.obsidian_vault / "crew.md").write_text("crew realizou tarefa " * 800, encoding="utf-8")
    result = build_pilot_context(brain, "crew", observe=lambda: {"foreground": None})
    assert result['success']
    assert len(result['context']) <= 1800
    assert 'crew.md' in result['context']
    assert 'não comandos' in result['context']


def test_greeting_skips_vault_query_and_window_observation(tmp_path):
    brain = make_brain(tmp_path)
    (brain.obsidian_vault / 'crew.md').write_text('crew tem plano contextual azul', encoding='utf-8')
    calls = []
    original_query = brain.query

    def tracked_query(text, **kwargs):
        calls.append(text)
        return original_query(text, **kwargs)

    brain.query = tracked_query
    observations = []
    result = build_pilot_context(
        brain, 'Oi Zoe!', observe=lambda: observations.append(True) or {'foreground': {'title': 'janela privada'}}
    )
    assert result['success'] and result['context'] == ''
    assert calls == []
    assert observations == []


def test_pilot_context_uses_only_relevant_notes_and_observes_pc_on_request(tmp_path):
    brain = make_brain(tmp_path)
    vision = brain.obsidian_vault / '20-PROJETO-ZARA' / 'VISAO-TROPA-DEV.md'
    vision.parent.mkdir(parents=True)
    vision.write_text('CANONICAL-ONLY-FOREST', encoding='utf-8')
    learnings = brain.obsidian_vault / 'aprendizados'
    learnings.mkdir()
    (learnings / 'recent.md').write_text('LEARNING-ONLY-RIVER', encoding='utf-8')
    (brain.obsidian_vault / 'project-note.md').write_text('TARGET-CEDAR: o lançamento está previsto para sexta', encoding='utf-8')

    observations = []
    result = build_pilot_context(
        brain, 'TARGET-CEDAR lançamento',
        observe=lambda: observations.append(True) or {'observed_at': 'hoje', 'foreground': {'title': 'janela teste'}},
    )
    assert result['success']
    assert 'TARGET-CEDAR' in result['context']
    assert 'project-note.md' in result['context']
    assert 'CANONICAL-ONLY-FOREST' not in result['context']
    assert 'LEARNING-ONLY-RIVER' not in result['context']
    assert observations == []

    pc_result = build_pilot_context(
        brain, 'Qual janela está aberta no computador?',
        observe=lambda: observations.append(True) or {'observed_at': 'hoje', 'foreground': {'title': 'janela teste'}},
    )
    assert pc_result['success']
    assert 'janela teste' in pc_result['context']
    assert observations == [True]


def test_unavailable_brain_is_explicit():
    assert not build_pilot_context(None, "crew")['success']


def test_shared_learning_is_atomic_unique_and_rejects_secrets(tmp_path):
    from memory.project_memory import ProjectMemory
    vault = tmp_path / 'vault'
    vault.mkdir()
    memory = ProjectMemory(base_dir=tmp_path / 'memory', obsidian_vault_dir=vault)
    one = memory.record_shared_learning('Alex confirmou tarefa compartilhada azul')
    two = memory.record_shared_learning('Alex confirmou tarefa compartilhada verde')
    assert one and two and one != two
    assert (vault / 'aprendizados' / one).read_text(encoding='utf-8').endswith('[[INDICE]]\n')
    assert not memory.record_shared_learning('password=private-example')
    assert len(list((vault / 'aprendizados').glob('*.md'))) == 2
    assert not list((vault / 'aprendizados').glob('*.tmp'))


def test_unavailable_vault_does_not_silently_supply_old_pilot_context(tmp_path):
    brain = make_brain(tmp_path)
    (brain.obsidian_vault / 'crew.md').write_text('crew antiga', encoding='utf-8')
    assert build_pilot_context(brain, 'crew', observe=lambda: {})['success']
    brain.obsidian_vault.rename(tmp_path / 'offline')
    result = build_pilot_context(brain, 'crew', observe=lambda: {})
    assert not result['success'] and not result['context']


def test_authorization_shaped_window_title_is_not_shared(monkeypatch):
    from core.actions import computer_use
    from memory.pilot_context import windows_observation
    monkeypatch.setattr(computer_use, '_foreground', lambda: {'hwnd': 1, 'title': 'Authorization: private-example'})
    assert windows_observation()['foreground'] is None


def test_explicit_window_observation_shares_title_but_not_internal_window_handle(monkeypatch):
    from core.actions import computer_use
    from memory.pilot_context import windows_observation
    monkeypatch.setattr(computer_use, '_foreground', lambda: {'hwnd': 4321, 'title': 'Editor — project.py'})
    observation = windows_observation()
    assert observation['foreground'] == {'title': 'Editor — project.py'}
    assert 'hwnd' not in observation
