from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, RoleName
from core.lab_v1.workforce_policy import ResourceClass, WorkforcePolicy


def test_alex_authorized_nvidia_free_fallback_models_are_exactly_allowlisted():
    policy = WorkforcePolicy(WorkforcePolicy.default_document())
    models = ('moonshotai/kimi-k3', 'z-ai/glm-5.3', 'z-ai/glm-5.3-flash')

    for model in models:
        agent = AgentProfile('agent-' + model, 'worker', 'nvidia', model, role=RoleName.BUILDER)
        provider = ProviderInfo('nvidia', 'NVIDIA', 'fixture', Availability.AVAILABLE,
                                models=list(models))
        decision = policy.authorize(agent, provider, model_available=True)
        assert decision.allowed
        assert decision.resource_class is ResourceClass.OWNER_REPORTED_FREE

    unknown = AgentProfile('unknown', 'worker', 'nvidia', 'moonshotai/other', role=RoleName.BUILDER)
    provider = ProviderInfo('nvidia', 'NVIDIA', 'fixture', Availability.AVAILABLE,
                            models=['moonshotai/other'])
    decision = policy.authorize(unknown, provider, model_available=True)
    assert not decision.allowed
    assert decision.code == 'MODEL_NOT_AUTHORIZED'
    assert policy.resource_class('nvidia', 'moonshotai/other') is ResourceClass.UNKNOWN_COST
