"""SAFE: FRENTE 2 (MISSAO LAB VIVO) — escada de fallback, motores dos assentos
e rota cerebro-pesado. Nenhum teste chama API real: o adapter NVIDIA e
exercitado com transporte falso; a chamada real foi validada a parte
(script test_nim.py, 28/09/2026, modelo real respondeu NIM-OK).
"""
import json

import pytest

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult
from core.lab_v1.providers.fallback import (
    FallbackOutcome,
    complete_with_fallback,
)
from core.lab_v1.providers.nvidia import NvidiaApiAdapter


class StubAdapter:
    id = "stub"

    def __init__(self, availability=Availability.AVAILABLE, ok=True, text="ok",
                 calls=None):
        self._availability = availability
        self._ok = ok
        self._text = text
        self.calls = calls if calls is not None else []

    def probe(self):
        return ProviderInfo(self.id, "Stub", "stub",
                            self._availability, "stub",
                            models=[], installed=None, authenticated=False)

    def invoke(self, *, prompt, model, system=None, timeout_s=120, **kw):
        self.calls.append((prompt, model))
        if self._ok:
            return ProviderResult(True, text=self._text,
                                  availability=Availability.AVAILABLE)
        return ProviderResult(False, availability=Availability.PROVIDER_ERROR,
                              error="stub falhou")


class FakeRegistry:
    def __init__(self, adapters):
        self._adapters = adapters
        self.recorded = []

    def get(self, provider_id):
        return self._adapters.get(provider_id)

    def record_result(self, provider_id, model_id, result):
        self.recorded.append((provider_id, model_id, result.ok))


def _ladder(*pairs):
    return list(pairs)


def test_fallback_usa_primeiro_degrau_ok():
    a = StubAdapter(ok=True, text="primeiro")
    b = StubAdapter(ok=True, text="segundo")
    reg = FakeRegistry({"a": a, "b": b})
    out = complete_with_fallback(reg, _ladder(("a", "m1"), ("b", "m2")),
                                 prompt="oi")
    assert isinstance(out, FallbackOutcome)
    assert out.ok and out.result.text == "primeiro"
    assert out.provider_id == "a" and out.model == "m1"
    assert len(out.attempts) == 1
    assert b.calls == []  # segundo degrau nem foi chamado
    assert reg.recorded == [("a", "m1", True)]


def test_fallback_pula_degrau_falho_e_tenta_proximo():
    a = StubAdapter(ok=False)
    b = StubAdapter(ok=True, text="segundo venceu")
    reg = FakeRegistry({"a": a, "b": b})
    out = complete_with_fallback(reg, _ladder(("a", "m1"), ("b", "m2")),
                                 prompt="oi")
    assert out.ok and out.result.text == "segundo venceu"
    assert out.provider_id == "b"
    assert [x.provider_id for x in out.attempts] == ["a", "b"]
    assert not out.attempts[0].ok and out.attempts[1].ok


def test_fallback_pula_provedor_sem_credencial_sem_chamar():
    a = StubAdapter(availability=Availability.AUTH_REQUIRED)
    b = StubAdapter(ok=True, text="b")
    reg = FakeRegistry({"a": a, "b": b})
    out = complete_with_fallback(reg, _ladder(("a", "m1"), ("b", "m2")),
                                 prompt="oi")
    assert out.ok and out.provider_id == "b"
    assert a.calls == []  # pulado no probe, sem gastar chamada
    assert out.attempts[0].skipped


def test_fallback_tudo_falha_devolve_historico_sem_inventar():
    a = StubAdapter(ok=False)
    reg = FakeRegistry({"a": a})
    out = complete_with_fallback(reg, _ladder(("a", "m1"), ("nope", "m9")),
                                 prompt="oi")
    assert not out.ok
    assert out.result.text in (None, "")
    assert len(out.attempts) == 2  # degrau real + provedor inexistente


def test_nvidia_adapter_interpreta_resposta_real():
    def fake_transport(method, url, headers, payload, timeout):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer nvapi-fake"
        body = json.dumps({
            "id": "chatcmpl-teste",
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "choices": [{"message": {"role": "assistant",
                                     "content": "NIM-OK"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 2},
        }).encode()
        return 200, {"x-request-id": "req-1"}, body

    ad = NvidiaApiAdapter(credential="nvapi-fake", transport=fake_transport)
    res = ad.complete(prompt="diga NIM-OK",
                      model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    assert res.ok and res.text == "NIM-OK"
    assert res.availability is Availability.AVAILABLE
    assert res.input_tokens == 8 and res.output_tokens == 2


def test_nvidia_adapter_401_vira_auth_required():
    def fake_transport(method, url, headers, payload, timeout):
        return 401, {}, b'{"error": {"message": "Invalid API key"}}'

    ad = NvidiaApiAdapter(credential="nvapi-fake", transport=fake_transport)
    res = ad.complete(prompt="oi", model="qualquer")
    assert not res.ok
    assert res.availability is Availability.AUTH_REQUIRED
    assert "nvapi-fake" not in (res.error or "")


def test_assentos_tem_motor_gratis_e_escada():
    from core.lab_v1.fixed_seats import FIXED_SEATS
    from core.lab_v1 import seat_engines

    assert len(FIXED_SEATS) == 11
    for role in FIXED_SEATS:
        provider, model = seat_engines.engine_for(role)
        assert provider == "nvidia", f"{role.value} deveria ser gratis"
        assert model and "/" in model
        ladder = seat_engines.default_ladder_for(role)
        assert ladder[0].provider_id == "nvidia"  # gratis primeiro
        assert ladder[-1].provider_id == "codex_cli"  # pago por ultimo
        assert len({(r.provider_id, r.model) for r in ladder}) == len(ladder)


def test_zoe_brain_ida_e_volta(tmp_path, monkeypatch):
    from core.lab_v1 import zoe_brain

    monkeypatch.setenv(zoe_brain.INBOX_ENV, str(tmp_path))
    qid = zoe_brain.ask_zoe("Qual o sentido da vida do Lab?",
                            context="teste", asked_by="pytest")
    assert qid
    assert (tmp_path / f"PERGUNTA-ZOE-{qid}.md").exists()
    assert zoe_brain.read_zoe_answer(qid) is None  # ainda sem resposta
    (tmp_path / f"RESPOSTA-ZOE-{qid}.md").write_text("42", encoding="utf-8")
    assert zoe_brain.read_zoe_answer(qid) == "42"
