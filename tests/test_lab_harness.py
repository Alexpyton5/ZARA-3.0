import json
import time
import urllib.request
import urllib.error
import pytest
from core.lab_v1.providers.harness import DeepSeekHarnessAdapter, TextGateway, patch_config, MODEL, DISABLED
from core.lab_v1.domain import Availability, ProviderResult


class Provider:
    def __init__(self): self.calls = []
    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return ProviderResult(True, text='HARNESS_FIXTURE_OK', availability=Availability.AVAILABLE,
            model_reported='fixture-reported', provider_session_id='fixture-id', input_tokens=2, output_tokens=3)


def request(gateway, **overrides):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'Hello'}], **overrides}
    return urllib.request.Request(f'http://127.0.0.1:{gateway.server.server_port}/chat/completions',
        data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + gateway.token})


def test_gateway_calls_once_and_preserves_provider_identity():
    provider = Provider()
    with TextGateway(provider, MODEL, time.monotonic() + 10) as gateway:
        with urllib.request.urlopen(request(gateway), timeout=3) as response:
            text = response.read().decode()
        assert 'fixture-id' in text and 'fixture-reported' in text
        with pytest.raises(urllib.error.HTTPError): urllib.request.urlopen(request(gateway), timeout=3)
        assert len(provider.calls) == 1


def test_gateway_rejects_tools_before_provider_call():
    provider = Provider()
    with TextGateway(provider, MODEL, time.monotonic() + 10) as gateway:
        with pytest.raises(urllib.error.HTTPError): urllib.request.urlopen(request(gateway, tools=[{'name': 'shell'}]), timeout=3)
        assert not provider.calls


def test_patch_excludes_effects_persistence_and_retries():
    patches = {p['id']: p for p in patch_config('http://127.0.0.1:1')}
    assert all(patches[row]['disabled'] for row in DISABLED)
    assert patches['llm-deepseek']['config']['retryPolicy']['maxRetries'] == 0
    assert 'sessions' in DISABLED and 'persistent-pwsh' in DISABLED and 'str-replace-editor' in DISABLED


def test_missing_pin_cannot_dispatch(tmp_path):
    provider = Provider()
    result = DeepSeekHarnessAdapter(root=tmp_path, provider=provider).complete(prompt='x', model=MODEL)
    assert not result.ok and not provider.calls


def test_official_pinned_harness_with_local_fixture():
    provider = Provider()
    adapter = DeepSeekHarnessAdapter(provider=provider)
    if not adapter._verify_pin(): pytest.skip('Pinned optional Harness runtime not installed')
    result = adapter.complete(prompt='Return exactly HARNESS_FIXTURE_OK', model=MODEL, timeout_s=15)
    assert result.ok and result.text == 'HARNESS_FIXTURE_OK'
    assert result.model_reported == 'fixture-reported' and len(provider.calls) == 1
