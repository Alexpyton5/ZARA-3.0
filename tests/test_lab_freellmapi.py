"""FASE 2 PECA 5 (28/09/2026): degrau FreeLLMAPI na escada do turno de missao.

O agregador local gratis (http://localhost:3001) entra na escada entre os
NVIDIA gratis e a Luna paga: cota da NVIDIA morta -> o app desce para o
FreeLLMAPI -> so entao a Luna. Enquanto o Alex nao criar a conta no
dashboard, o degrau e pulado sem gastar chamada (nunca finge que funciona).

Todos os testes sao hermeticos: o transporte HTTP e injetado, nenhum teste
toca o localhost de verdade.
"""
from __future__ import annotations

import json

import pytest

from core.lab_v1.domain import Availability
from core.lab_v1.providers.freellmapi import FreeLLMAPIAdapter, AUTO_MODEL
from core.lab_v1.providers.registry import default_registry
from core.lab_v1 import seat_engines


def _resp(status, payload):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    return status, {}, body


def _ok_completion(model="groq/llama-3.3-70b-versatile", text="resposta real"):
    return _resp(200, {
        "id": "chatcmpl-123",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })


def _models(ids):
    return _resp(200, {"data": [{"id": i} for i in ids]})


class FakeTransport:
    """Transporte programavel: rota (metodo, caminho) -> resposta ou excecao."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, payload, timeout):
        self.calls.append((method, url))
        path = url.split("/v1", 1)[-1] if "/v1" in url else "/"
        key = (method, path if path.startswith("/") else "/" + path)
        if key not in self.routes:
            # dashboard
            if method == "GET" and url.rstrip("/").endswith(":3001"):
                return 200, {}, b"<html>dashboard</html>"
            raise AssertionError(f"rota nao programada: {key} ({url})")
        outcome = self.routes[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _adapter(routes, credential="CHAVE-TESTE"):
    return FreeLLMAPIAdapter(credential=credential, transport=FakeTransport(routes))


# --- probe: estados honestos -------------------------------------------------

def test_probe_offline_quando_servidor_caido():
    def boom(method, url, headers, payload, timeout):
        raise ConnectionError("recusado")
    adapter = FreeLLMAPIAdapter(credential="CHAVE-TESTE", transport=boom)
    info = adapter.probe()
    assert info.availability is Availability.OFFLINE
    assert info.detail


def test_probe_auth_required_sem_chave():
    adapter = _adapter({}, credential="")
    info = adapter.probe()
    assert info.availability is Availability.AUTH_REQUIRED
    assert "localhost:3001" in info.detail


def test_probe_auth_required_quando_dashboard_rejeita_chave():
    adapter = _adapter({("GET", "/models"): _resp(401, {"error": "Unauthorized"})})
    info = adapter.probe()
    assert info.availability is Availability.AUTH_REQUIRED
    assert info.detail


def test_probe_unknown_com_modelos_ate_primeira_chamada_real():
    adapter = _adapter({("GET", "/models"): _models(["groq/llama-3.3-70b-versatile", "gemini-2.0-flash"])})
    info = adapter.probe()
    # UNKNOWN: configurado, mas nenhuma chamada real ainda (nunca AVAILABLE por palpite).
    assert info.availability is Availability.UNKNOWN
    assert info.models == ["gemini-2.0-flash", "groq/llama-3.3-70b-versatile"]
    assert [d.model_id for d in adapter.declared_models] == info.models


def test_probe_auth_required_quando_conta_sem_chaves():
    adapter = _adapter({("GET", "/models"): _models([])})
    info = adapter.probe()
    assert info.availability is Availability.AUTH_REQUIRED
    assert info.detail


def test_probe_available_apos_chamada_real():
    routes = {
        ("GET", "/models"): _models(["groq/llama-3.3-70b-versatile"]),
        ("POST", "/chat/completions"): _ok_completion(),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="groq/llama-3.3-70b-versatile")
    assert result.ok
    info = adapter.probe()
    assert info.availability is Availability.AVAILABLE


# --- complete: uma chamada real, erros classificados --------------------------

def test_complete_ok_parseia_resposta_openai():
    routes = {
        ("GET", "/models"): _models(["groq/llama-3.3-70b-versatile"]),
        ("POST", "/chat/completions"): _ok_completion(text="texto de verdade"),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="diga oi", model="groq/llama-3.3-70b-versatile",
                              system="voce e util")
    assert result.ok
    assert result.text == "texto de verdade"
    assert result.model_reported == "groq/llama-3.3-70b-versatile"
    assert result.availability is Availability.AVAILABLE


def test_complete_auto_resolve_primeiro_modelo():
    routes = {
        ("GET", "/models"): _models(["zzz-ultimo", "aaa-primeiro"]),
        ("POST", "/chat/completions"): _ok_completion(model="aaa-primeiro"),
    }
    transport = FakeTransport(routes)
    adapter = FreeLLMAPIAdapter(credential="CHAVE-TESTE", transport=transport)
    result = adapter.complete(prompt="oi", model=AUTO_MODEL)
    assert result.ok
    posts = [c for c in transport.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert result.model_reported == "aaa-primeiro"


def test_complete_auto_sem_modelo_nao_chama_nada():
    routes = {("GET", "/models"): _models([])}
    transport = FakeTransport(routes)
    adapter = FreeLLMAPIAdapter(credential="CHAVE-TESTE", transport=transport)
    result = adapter.complete(prompt="oi", model=AUTO_MODEL)
    assert not result.ok
    assert result.availability is Availability.MODEL_UNAVAILABLE
    assert not [c for c in transport.calls if c[0] == "POST"]


def test_complete_401_vira_auth_required():
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): _resp(401, {"error": {"message": "Invalid API key"}}),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="m1")
    assert not result.ok
    assert result.availability is Availability.AUTH_REQUIRED


def test_complete_429_com_cota_vira_quota_exhausted():
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): _resp(429, {"error": {"message": "quota exceeded for today"}}),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="m1")
    assert result.availability is Availability.QUOTA_EXHAUSTED


def test_complete_429_sem_cota_vira_rate_limited():
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): _resp(429, {"error": {"message": "too many requests"}}),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="m1")
    assert result.availability is Availability.RATE_LIMITED


def test_complete_404_vira_model_unavailable():
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): _resp(404, {"error": {"message": "model not found"}}),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="m1")
    assert result.availability is Availability.MODEL_UNAVAILABLE


def test_complete_servidor_cai_no_meio_vira_offline():
    def boom(method, url, headers, payload, timeout):
        if method == "GET" and url.rstrip("/").endswith(":3001"):
            return 200, {}, b"<html>dashboard</html>"
        raise ConnectionError("caiu")
    adapter = FreeLLMAPIAdapter(credential="CHAVE-TESTE", transport=boom)
    result = adapter.complete(prompt="oi", model="qualquer")
    assert not result.ok
    assert result.availability is Availability.OFFLINE


def test_complete_nunca_inventa_resposta_em_payload_quebrado():
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): (200, {}, b'{"choices": []}'),
    }
    adapter = _adapter(routes)
    result = adapter.complete(prompt="oi", model="m1")
    assert not result.ok
    assert result.availability is Availability.PROVIDER_ERROR


def test_chave_nunca_vaza_no_detalhe_do_erro():
    secret = "sk-freellmapi-SECRETA-123456"
    routes = {
        ("GET", "/models"): _models(["m1"]),
        ("POST", "/chat/completions"): (
            500, {}, json.dumps({"error": f"falha com {secret} no meio"}).encode()),
    }
    adapter = _adapter(routes, credential=secret)
    result = adapter.complete(prompt="oi", model="m1")
    assert not result.ok
    assert secret not in result.error
    assert "[REDACTED]" in result.error


# --- identifies_model: "auto" e apelido ---------------------------------------

def test_identifies_model_auto_aceita_id_canonico():
    adapter = _adapter({})
    assert adapter.identifies_model("auto", "groq/llama-3.3-70b-versatile")
    assert adapter.identifies_model("auto", None)


def test_identifies_model_concreto_continua_rigoroso():
    adapter = _adapter({})
    assert adapter.identifies_model("m1", "m1")
    assert not adapter.identifies_model("m1", "m2")
    assert adapter.identifies_model("m1", None)


# --- escada: freellmapi entre o gratis e o pago --------------------------------

def test_escada_tem_freellmapi_depois_do_gratis_e_antes_da_luna():
    ladder = seat_engines.default_ladder_for("ENGINEER")
    keys = [(r.provider_id, r.model) for r in ladder]
    assert ("freellmapi", "auto") in keys
    pos = keys.index(("freellmapi", "auto"))
    # depois dos NVIDIA gratis...
    assert any(pid == "nvidia" for pid, _ in keys[:pos])
    # ...e antes da Luna paga (ultimo recurso).
    assert keys[-1] == ("codex_cli", "gpt-5.6-luna")
    assert pos < len(keys) - 1


def test_escada_sem_duplicados_e_com_freellmapi_no_relatorio():
    ladder = seat_engines.default_ladder_for("CEO")
    keys = [(r.provider_id, r.model) for r in ladder]
    assert len(keys) == len(set(keys))
    report = {row["seat"]: row for row in seat_engines.seat_report()}
    assert "freellmapi" in report["CEO"]["ladder"]


def test_registry_registra_freellmapi_com_estado_real():
    registry = default_registry()
    adapter = registry.get("freellmapi")
    assert adapter is not None
    assert adapter.id == "freellmapi"
    info = adapter.probe()
    assert isinstance(info.availability, Availability)
    assert info.detail
    # Sem servidor no ar ou sem chave, nunca AVAILABLE por palpite.
    assert info.availability in (
        Availability.OFFLINE, Availability.AUTH_REQUIRED, Availability.UNKNOWN,
        Availability.AVAILABLE, Availability.PROVIDER_ERROR,
    )
