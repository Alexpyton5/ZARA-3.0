from core.model_router import ModelConfig, ModelRouter, ModelProvider, TaskType


def test_cost_safe_accepts_only_factual_local_free(monkeypatch):
    router = ModelRouter()
    local = ModelConfig('local', 'Local', ModelProvider.OLLAMA, 'local', [TaskType.GENERAL_CHAT], 'OLLAMA_API_KEY', 'http://127.0.0.1', 100, 'local', 1, cost_status='LOCAL_FREE')
    unknown = ModelConfig('unknown', 'Unknown', ModelProvider.NVIDIA, 'unknown', [TaskType.GENERAL_CHAT], 'NVIDIA_API_KEY', 'https://example', 100, 'unknown', 1, cost_status='UNKNOWN_COST')
    router.api_keys = {'OLLAMA_API_KEY': 'local', 'NVIDIA_API_KEY': 'configured'}
    monkeypatch.setattr('core.model_router.MODEL_REGISTRY', [local, unknown])
    assert [m.id for m in router.cost_safe_candidates([TaskType.GENERAL_CHAT])] == ['local']
    assert router.get_best_model([TaskType.GENERAL_CHAT], cost_safe=True).id == 'local'


def test_premium_brains_are_manual_only_contract():
    assert ModelRouter.ACTIVE_BRAIN_DEFAULT == 'gpt-5.6-luna'
    assert ModelRouter.MANUAL_ONLY_BRAINS == {'gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra'}
