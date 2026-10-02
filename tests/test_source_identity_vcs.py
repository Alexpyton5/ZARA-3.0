from tools import build_current


def write(root, path, content):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def test_nested_git_metadata_is_not_runtime_source(tmp_path, monkeypatch):
    monkeypatch.setattr(build_current, 'ROOT', tmp_path)
    write(tmp_path, 'tools/vendor/worker.py', 'value = 1')
    before = build_current.source_identity()
    write(tmp_path, 'tools/vendor/.git/config', 'metadata')
    write(tmp_path, 'tools/vendor/.git/objects/pack/tmp_pack_transient', 'transient')
    assert build_current.source_identity() == before


def test_git_worktree_pointer_is_not_runtime_source(tmp_path, monkeypatch):
    monkeypatch.setattr(build_current, 'ROOT', tmp_path)
    write(tmp_path, 'tools/worktree/worker.py', 'value = 1')
    before = build_current.source_identity()
    write(tmp_path, 'tools/worktree/.git', 'gitdir: ../metadata')
    assert build_current.source_identity() == before


def test_real_vendor_code_and_git_named_project_files_remain_in_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(build_current, 'ROOT', tmp_path)
    write(tmp_path, 'tools/vendor/worker.py', 'value = 1')
    write(tmp_path, 'tools/vendor/.gitignore', 'generated')
    write(tmp_path, 'tools/vendor/.github/workflows/check.yml', 'name: check')
    before = build_current.source_identity()
    assert {entry['path'] for entry in before['files']} == {
        'tools/vendor/worker.py', 'tools/vendor/.gitignore', 'tools/vendor/.github/workflows/check.yml'
    }
    write(tmp_path, 'tools/vendor/worker.py', 'value = 2')
    assert build_current.source_identity()['sha256'] != before['sha256']
