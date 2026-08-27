from pathlib import Path


def test_canonical_legacy_identity_module_source_is_preserved():
    project_root = Path(__file__).resolve().parents[1]

    assert (project_root / "core" / "identity.py").is_file()
