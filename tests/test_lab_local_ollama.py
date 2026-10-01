"""Tests for the Ollama local provider adapter.

A real fake HTTP server (http.server on an ephemeral port) backs the happy
paths, so the adapter's actual URL/JSON contract is exercised — not a mock of
itself. Transport-injected failure modes cover refused connections and
timeouts. No real Ollama install is needed.
"""
from __future__ import annotations

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.lab_v1.domain import Availability
from core.lab_v1.providers.local_ollama import OllamaLocalAdapter, OLLAMA_MODELS


# ---------------------------------------------------------------------------
# Fake Ollama server (OpenAI-compatible surface only)
# ---------------------------------------------------------------------------

class _FakeOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence test output
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [
                {"id": "qwen2.5-coder:7b", "object": "model"},
                {"id": "llama3.1:8b", "object": "model"},
            ]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        if request.get("model") == "missing-model":
            self._send(404, {"error": {"message": "model 'missing-model' not found, try pulling it first"}})
            return
        self._send(200, {
            "id": "cmpl-test", "object": "chat.completion", "model": request.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ola da ZARA local"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        })


class _RateLimitedHandler(_FakeOllamaHandler):
    def do_POST(self):  # noqa: N802
        if self.path == "/v1/chat/completions":
            # Consume the request before closing the HTTP/1.0 connection; an
            # unread body can reset the connection before the client reads 429.
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._send(429, {"error": {"message": "too many requests, please slow down"}})
            return
        super().do_POST()


@pytest.fixture()
def server_base_url():
    # Let the HTTP server bind port 0 directly. Probing a free port with a
    # temporary socket and binding it afterward leaves a race with other
    # processes during the full suite.
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def rate_limited_base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RateLimitedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# probe()
# ---------------------------------------------------------------------------

def test_probe_reachable_server_is_available_with_models(server_base_url):
    info = OllamaLocalAdapter(base_url=server_base_url).probe()
    assert info.availability is Availability.AVAILABLE
    assert info.models == ["llama3.1:8b", "qwen2.5-coder:7b"]


def test_probe_down_server_is_offline_not_available():
    # An ephemeral port with nothing listening: connection must be refused.
    info = OllamaLocalAdapter(base_url="http://127.0.0.1:1/v1").probe()
    assert info.availability is Availability.OFFLINE
    assert info.models == []


def test_probe_timeout_is_offline():
    def hanging_transport(method, url, headers, payload, timeout):
        raise TimeoutError("timed out")

    info = OllamaLocalAdapter(transport=hanging_transport).probe()
    assert info.availability is Availability.OFFLINE


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------

def test_complete_happy_path_echoes_model_and_folds_system(server_base_url):
    adapter = OllamaLocalAdapter(base_url=server_base_url)
    result = adapter.complete(
        prompt="Ola?", model="qwen2.5-coder:7b", system="Seja concisa.", timeout_s=10,
    )
    assert result.ok is True
    assert result.text == "ola da ZARA local"
    assert result.model_reported == "qwen2.5-coder:7b"
    assert result.input_tokens == 5 and result.output_tokens == 3
    # Ollama echoes the exact id, so strict identifies_model default must hold.
    assert adapter.identifies_model("qwen2.5-coder:7b", result.model_reported) is True
    assert adapter.identifies_model("qwen3:8b", result.model_reported) is False


def test_complete_unknown_model_is_model_unavailable(server_base_url):
    result = OllamaLocalAdapter(base_url=server_base_url).complete(
        prompt="oi", model="missing-model", timeout_s=10,
    )
    assert result.ok is False
    assert result.availability is Availability.MODEL_UNAVAILABLE


def test_complete_http_429_is_rate_limited(rate_limited_base_url):
    result = OllamaLocalAdapter(base_url=rate_limited_base_url).complete(
        prompt="oi", model="qwen3:8b", timeout_s=10,
    )
    assert result.ok is False
    assert result.availability is Availability.RATE_LIMITED


def test_complete_timeout_is_offline_and_never_raises():
    def slow_transport(method, url, headers, payload, timeout):
        raise TimeoutError("read timed out")

    result = OllamaLocalAdapter(transport=slow_transport).complete(
        prompt="oi", model="qwen3:8b", timeout_s=1,
    )
    assert result.ok is False
    assert result.availability is Availability.OFFLINE


def test_complete_refused_connection_is_offline():
    result = OllamaLocalAdapter(base_url="http://127.0.0.1:1/v1").complete(
        prompt="oi", model="qwen3:8b", timeout_s=5,
    )
    assert result.ok is False
    assert result.availability is Availability.OFFLINE


def test_complete_invalid_success_payload_is_provider_error_not_ok(server_base_url):
    def empty_choices_transport(method, url, headers, payload, timeout):
        return 200, {}, json.dumps({"choices": [], "model": "qwen3:8b"}).encode("utf-8")

    result = OllamaLocalAdapter(transport=empty_choices_transport).complete(
        prompt="oi", model="qwen3:8b", timeout_s=5,
    )
    assert result.ok is False
    assert result.availability is Availability.PROVIDER_ERROR


# ---------------------------------------------------------------------------
# declared models + base_url configurability
# ---------------------------------------------------------------------------

def test_declared_models_offer_recommended_set_even_when_down():
    info = OllamaLocalAdapter(base_url="http://127.0.0.1:1/v1").probe()
    assert info.availability is Availability.OFFLINE
    declared = [item.model_id for item in OllamaLocalAdapter.declared_models]
    assert declared == list(OLLAMA_MODELS)
    assert "qwen2.5-coder:7b" in declared and "gpt-oss:20b" in declared


def test_base_url_is_configurable_for_compatible_servers():
    adapter = OllamaLocalAdapter(base_url="http://localhost:1234/v1/")
    assert adapter._base_url == "http://localhost:1234/v1"


def test_registry_end_to_end_via_real_http(server_base_url):
    from core.lab_v1.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    registry.register(OllamaLocalAdapter(base_url=server_base_url))
    assert registry.get("ollama") is not None
    models = registry.list_models("ollama")
    assert any(item["model_id"] == "qwen2.5-coder:7b" for item in models)
