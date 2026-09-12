"""Renderer must validate backend Run provenance instead of inferring it from selection."""
from pathlib import Path


def test_renderer_requires_backend_provenance_for_conversational_response():
    root = Path(__file__).parents[1]
    source = (root / 'frontend/src/renderer/components/zara-home/frontBrainProvenance.ts').read_text(encoding='utf-8')
    component = (root / 'frontend/src/renderer/components/zara-home/TextCommandInput.tsx').read_text(encoding='utf-8')
    assert 'export function validateFrontBrainProvenance' in source
    for field in ('run_id', 'model_requested', 'model_reported', 'provider', 'provenance_status'):
        assert field in source
    assert 'model_requested: selected' not in source
    assert "response.response_origin === 'local_deterministic'" in source
    assert "response.response_origin !== 'front_brain_run'" in source
    assert 'response.engine !== selected' in source
    assert 'validateFrontBrainProvenance(response, selected)' in component
