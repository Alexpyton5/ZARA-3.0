import json

from core.lab_v1.domain import Availability
from core.lab_v1.providers.nine_router import NineRouterAdapter


class StubNineRouter(NineRouterAdapter):
    def __init__(self, responses, **kwargs):
        self.responses = list(responses)
        super().__init__(**kwargs)

    def _request(self, method, path, body, timeout_s):
        assert method == 'GET' and path == '/models' and body is None
        return self.responses.pop(0)


def test_cached_catalog_does_not_claim_a_dead_gateway_is_available(tmp_path):
    cache = tmp_path / 'models.json'
    cache.write_text(json.dumps({'models': [{'model_id': 'alex'}]}), encoding='utf-8')
    adapter = StubNineRouter(
        [(503, b'gateway unavailable')], cache_path=cache,
        base_url='http://router.invalid/v1', headers={'Authorization': 'Bearer test'},
    )

    assert adapter.probe().availability is Availability.OFFLINE


def test_live_gateway_refreshes_catalog_before_becoming_available(tmp_path):
    adapter = StubNineRouter(
        [(200, json.dumps({'data': [{'id': 'oc/free-model'}]}).encode('utf-8'))],
        cache_path=tmp_path / 'models.json', base_url='http://router.invalid/v1',
        headers={'Authorization': 'Bearer test'},
    )

    info = adapter.probe()

    assert info.availability is Availability.AVAILABLE
    assert info.models == ['oc/free-model']


def test_zara_owned_relay_config_does_not_need_a_codex_provider_section(tmp_path):
    settings = tmp_path / 'nine_router_config.json'
    settings.write_text(json.dumps({
        'base_url': 'http://router.invalid/v1',
        'http_headers': {'Authorization': 'Bearer test'},
    }), encoding='utf-8')
    adapter = StubNineRouter(
        [(200, json.dumps({'data': [{'id': 'oc/free-model'}]}).encode('utf-8'))],
        cache_path=tmp_path / 'models.json', settings_path=settings,
    )

    assert adapter.probe().availability is Availability.AVAILABLE
