"""Deterministic NVIDIA foundation tests; all HTTP responses are fake."""
from __future__ import annotations

import json

import pytest

from core.lab_v1.domain import Availability
from core.lab_v1.providers.nvidia import NvidiaApiAdapter, NvidiaDiscoveryError
from core.lab_v1.providers.registry import ProviderRegistry, default_registry

DUMMY_SECRET = "nvapi-" + "x" * 48


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, payload, timeout):
        self.calls.append((method, url, headers, payload, timeout))
        return self.responses.pop(0)


def response(status, payload, headers=None):
    return status, headers or {}, json.dumps(payload).encode()


def adapter(tmp_path, http, credential=DUMMY_SECRET):
    return NvidiaApiAdapter(credential=credential, cache_path=tmp_path / "models.json", transport=http)


def test_missing_credential_is_auth_required(tmp_path):
    item = adapter(tmp_path, FakeHttp([]), credential="")
    assert item.probe().availability is Availability.AUTH_REQUIRED
    assert item.complete(prompt="x", model="m").availability is Availability.AUTH_REQUIRED


def test_ultra_reasoning_none_is_explicit_and_scoped(tmp_path):
    from core.lab_v1.providers.nvidia import ULTRA_MODEL
    http = FakeHttp([response(200, {'choices': [{'message': {'content': 'OK'}}]})])
    item = adapter(tmp_path, http)
    assert item.complete(prompt='OK', model=ULTRA_MODEL, effort='none').ok
    assert json.loads(http.calls[0][3])['reasoning_effort'] == 'none'
    with pytest.raises(ValueError): item.complete(prompt='OK', model='other', effort='none')
    assert len(http.calls) == 1


def test_auth_failure_is_normalized_and_secret_redacted(tmp_path):
    http = FakeHttp([response(401, {"error": {"message": f"invalid {DUMMY_SECRET}"}})])
    result = adapter(tmp_path, http).complete(prompt="x", model="m")
    assert result.availability is Availability.AUTH_REQUIRED
    assert DUMMY_SECRET not in (result.error or "")


def test_real_catalog_shape_is_parsed_and_cached(tmp_path):
    http = FakeHttp([response(200, {"data": [{"id": "nvidia/nemotron"}, {"id": "other/model"}]})])
    item = adapter(tmp_path, http)
    discovered = item.discover_models()
    assert [model.model_id for model in discovered] == ["nvidia/nemotron", "other/model"]
    assert all(model.source == "discovered" and model.observed_at for model in discovered)
    reopened = NvidiaApiAdapter(credential=DUMMY_SECRET, cache_path=tmp_path / "models.json", transport=FakeHttp([]))
    assert [model.model_id for model in reopened.declared_models] == ["nvidia/nemotron", "other/model"]
    assert DUMMY_SECRET not in (tmp_path / "models.json").read_text()


def test_cached_catalog_and_configured_key_do_not_prove_inference(tmp_path):
    http = FakeHttp([response(200, {"data": [{"id": "nvidia/nemotron"}]})])
    item = adapter(tmp_path, http)
    item.discover_models()
    before = len(http.calls)
    info = item.probe()
    assert info.availability is Availability.UNKNOWN
    assert info.authenticated is None
    assert info.models == ["nvidia/nemotron"]
    assert len(http.calls) == before


def test_successful_inference_temporarily_verifies_provider(tmp_path):
    http = FakeHttp([response(200, {"choices": [{"message": {"content": "OK"}}]})])
    item = adapter(tmp_path, http)
    assert item.probe().availability is Availability.UNKNOWN
    assert item.complete(prompt="Reply exactly OK", model="nvidia/test").ok
    assert item.probe().availability is Availability.AVAILABLE
    item._last_success_at -= 301
    assert item.probe().availability is Availability.UNKNOWN


def test_empty_success_payload_does_not_verify_provider(tmp_path):
    http = FakeHttp([response(200, {"choices": [{"message": {"content": ""}}]})])
    item = adapter(tmp_path, http)
    result = item.complete(prompt="Reply exactly OK", model="nvidia/test")
    assert not result.ok and result.availability is Availability.PROVIDER_ERROR
    assert item.probe().availability is Availability.UNKNOWN


def test_registry_list_models_never_calls_remote(tmp_path):
    http = FakeHttp([response(200, {"data": [{"id": "nvidia/nemotron"}]})])
    item = adapter(tmp_path, http)
    item.discover_models()
    calls = len(http.calls)
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(item)
    assert registry.list_models("nvidia")[0]["model_id"] == "nvidia/nemotron"
    assert len(http.calls) == calls


def test_success_parses_provenance_usage_and_request_id(tmp_path):
    http = FakeHttp([response(200, {
        "id": "request-safe", "model": "nvidia/reported-model",
        "choices": [{"message": {"content": "ZARA_NVIDIA_OK"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    })])
    result = adapter(tmp_path, http).complete(prompt="Return OK", model="nvidia/requested")
    assert result.ok and result.text == "ZARA_NVIDIA_OK"
    assert result.model_reported == "nvidia/reported-model"
    assert result.provider_session_id == "request-safe"
    assert (result.input_tokens, result.output_tokens) == (5, 3)
    assert result.cost_usd is None and result.cost_basis.value == "UNKNOWN"
    request_payload = json.loads(http.calls[0][3])
    assert request_payload["max_tokens"] == 256 and request_payload["stream"] is False


@pytest.mark.parametrize("status,message,expected", [
    (429, "rate limit exceeded", Availability.RATE_LIMITED),
    (429, "quota exhausted", Availability.QUOTA_EXHAUSTED),
    (404, "model not found", Availability.MODEL_UNAVAILABLE),
    (503, "service unavailable", Availability.PROVIDER_ERROR),
])
def test_error_normalization(tmp_path, status, message, expected):
    http = FakeHttp([response(status, {"error": {"message": message}})])
    result = adapter(tmp_path, http).complete(prompt="x", model="m")
    assert result.availability is expected


def test_health_update_and_secret_never_persisted(tmp_path):
    registry = ProviderRegistry(tmp_path / "health.json")
    item = adapter(tmp_path, FakeHttp([response(401, {"error": {"message": DUMMY_SECRET}})]))
    registry.register(item)
    result = item.complete(prompt="private prompt", model="m")
    registry.record_result("nvidia", "m", result)
    persisted = (tmp_path / "health.json").read_text()
    assert DUMMY_SECRET not in persisted
    assert "private prompt" not in persisted
    assert registry.health_snapshot()["provider:nvidia"]["availability"] == "AUTH_REQUIRED"


def test_repr_and_serialization_do_not_expose_credential(tmp_path):
    item = adapter(tmp_path, FakeHttp([]))
    assert DUMMY_SECRET not in repr(item)
    assert DUMMY_SECRET not in json.dumps(item.probe().to_dict())


def test_registry_includes_nvidia_without_remote_discovery(monkeypatch, tmp_path):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    registry = default_registry()
    assert registry.get("nvidia") is not None
    assert registry.list_models("nvidia") == []


def test_discovery_error_is_typed(tmp_path):
    item = adapter(tmp_path, FakeHttp([response(404, {"error": {"message": "not supported"}})]))
    with pytest.raises(NvidiaDiscoveryError) as caught:
        item.discover_models()
    assert caught.value.availability is Availability.PROVIDER_ERROR
