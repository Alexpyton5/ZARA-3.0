from pathlib import Path

from core.project_index import ProjectIndexer


def test_initial_scan_indexes_supported_files_and_emits_events(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    events = []
    indexer = ProjectIndexer(tmp_path, event_sink=events.append)

    result = indexer.scan()

    assert {item.relative_path for item in result.changed} == {"README.md", "src/main.py"}
    assert ".env" not in indexer.snapshot()
    assert [event["type"] for event in events] == ["project.file_indexed", "project.file_indexed"]
    assert all("secret" not in str(event) for event in events)


def test_incremental_scan_only_reindexes_changed_files_and_removes_deleted(tmp_path: Path):
    target = tmp_path / "note.md"
    target.write_text("one", encoding="utf-8")
    indexer = ProjectIndexer(tmp_path)
    indexer.scan()
    target.write_text("two", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")

    result = indexer.scan()
    assert {item.relative_path for item in result.changed} == {"note.md", "new.txt"}
    target.unlink()
    result = indexer.scan()
    assert result.removed == ("note.md",)
    assert "note.md" not in indexer.snapshot()


def test_state_is_reusable_and_ignores_secret_like_names(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "api_keys.json").write_text('{"key":"secret"}', encoding="utf-8")
    (tmp_path / "safe.md").write_text("safe", encoding="utf-8")
    state = tmp_path / "index.json"
    first = ProjectIndexer(tmp_path, state_path=state)
    first.scan()
    second = ProjectIndexer(tmp_path, state_path=state)
    result = second.scan()
    assert result.changed == ()
    assert set(second.snapshot()) == {"safe.md"}
