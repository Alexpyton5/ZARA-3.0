from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lab_snapshot_exposes_resident_health_fields():
    service = (ROOT / "core/lab_v1/service.py").read_text(encoding="utf-8")
    assert "data['resident_health']" in service
    assert "DISABLED_BY_POLICY" in service
    assert "data['autonomy_policy']" in service
    assert "data['central_memory']" in service
