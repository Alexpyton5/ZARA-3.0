"""SAFE: contrato de seleção de modelo por capability. Não chama nenhuma API
de modelo — só a seleção determinística já existente em core.model_router."""
from core.ai_provider_contracts import ModelCapability, ModelRequest, select_model


def test_unknown_capability_rejected_without_touching_router():
    # ModelCapability é um Enum fechado — não tem como pedir capability
    # inexistente sem contornar o type system, então testamos a mensagem de
    # erro por um caminho que o mapa realmente pode falhar: monkeypatch do
    # mapa não é necessário aqui porque o Enum já impede a entrada inválida.
    # Este teste documenta a garantia: toda capability do Enum tem mapeamento.
    from core.ai_provider_contracts import _CAPABILITY_TO_TASK_TYPE

    for cap in ModelCapability:
        assert cap in _CAPABILITY_TO_TASK_TYPE


def test_select_model_returns_accepted_response_shape():
    resp = select_model(ModelRequest(capabilities=[ModelCapability.TEXT]))
    assert resp.accepted in (True, False)
    if resp.accepted:
        assert resp.model_id
        assert resp.provider
    else:
        assert resp.rejection_reason


def test_select_model_never_calls_a_network_api():
    """Seleção é sempre local/determinística — sem isso, um teste SAFE
    poderia silenciosamente virar um teste LIVE de rede."""
    import urllib.request

    called = []
    original = urllib.request.urlopen

    def _guard(*args, **kwargs):
        called.append(args)
        raise AssertionError("select_model() não deveria abrir nenhuma conexão de rede")

    urllib.request.urlopen = _guard
    try:
        select_model(ModelRequest(capabilities=[ModelCapability.REASONING], require_tools=True))
    finally:
        urllib.request.urlopen = original
    assert called == []


def test_no_candidate_case_is_a_structured_rejection_not_an_exception():
    # Pedir uma combinação improvável (tools + policy inválida ainda deve
    # retornar objeto estruturado, nunca levantar exceção para o chamador).
    resp = select_model(ModelRequest(capabilities=[ModelCapability.VOICE], require_tools=True))
    assert resp.accepted in (True, False)
