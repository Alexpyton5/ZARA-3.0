"""Adaptador FreeLLMAPI para o contrato de provedores do Lab — FASE 2 PECA 5 (28/09/2026).

O FreeLLMAPI (github.com/tashfeenahmed/freellmapi, MIT) roda no proprio PC
do Alex em http://localhost:3001 e agrega os planos GRATUITOS de 34
provedores (Groq, Gemini, Mistral, Cerebras, NVIDIA, Cloudflare...) num
endpoint OpenAI-compatible local: POST /v1/chat/completions.

Papel na escada (seat_engines.default_ladder_for): degrau gratis DEPOIS
dos NVIDIA e ANTES da Luna paga. Quando a cota da NVIDIA morre, o app
desce para o agregador local; so se ele tambem falhar a Luna entra.
Enquanto o Alex nao criar a conta no dashboard nem colar as chaves
gratuitas, o probe responde AUTH_REQUIRED e a escada PULA o degrau sem
gastar chamada — nunca finge que funciona.

Regras duras (contrato do ProviderAdapter):
- probe() nunca chama modelo: sao 1 ou 2 GETs baratos no localhost.
- complete() faz exatamente UMA chamada real e nunca inventa resposta.
- A chave do dashboard nunca aparece em log, erro ou detalhe.
- model="auto" resolve para o primeiro modelo listado em /v1/models
  (o Alex escolhe os modelos colando as chaves; o Lab nao chuta id).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.paths import api_keys_path

DEFAULT_BASE_URL = "http://localhost:3001/v1"
AUTO_MODEL = "auto"
HttpTransport = Callable[[str, str, dict[str, str], bytes | None, int], tuple[int, dict[str, str], bytes]]


class FreeLLMAPIAdapter(ProviderAdapter):
    id = "freellmapi"
    label = "FreeLLMAPI (agregador local gratis)"
    controlled_text_only = True

    def __init__(
        self,
        *,
        credential: str | None = None,
        base_url: str | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._credential = credential if credential is not None else self._load_credential()
        self._base_url = (base_url or os.environ.get("FREELLMAPI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._transport = transport or self._urlopen_transport
        self._models: list[str] = []
        self._last_success_at = 0.0

    @staticmethod
    def _load_credential() -> str:
        env_value = str(os.environ.get("FREELLMAPI_API_KEY") or "").strip()
        if env_value:
            return env_value
        try:
            data = json.loads(api_keys_path().read_text(encoding="utf-8-sig"))
            return str(data.get("freellmapi_api_key") or "").strip()
        except (OSError, ValueError, TypeError):
            return ""

    @property
    def declared_models(self) -> tuple[ModelDescriptor, ...]:
        return tuple(
            ModelDescriptor(
                provider_id=self.id,
                model_id=model_id,
                display_name=model_id,
                source="discovered",
            )
            for model_id in self._models
        )

    def _dashboard_url(self) -> str:
        base = self._base_url
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base + "/"

    def _request(self, method: str, path: str, payload: bytes | None, timeout: int,
                 *, auth: bool = True):
        headers = {"Accept": "application/json"}
        if auth and self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"
        elif auth:
            # Sem chave o proxy responde 401; o chamador classifica.
            headers["Authorization"] = "Bearer "
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._transport(method, self._base_url + path, headers, payload, timeout)
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
        except (urllib.error.URLError, TimeoutError, OSError, ConnectionError):
            return 0, {}, b""

    @staticmethod
    def _urlopen_transport(method, url, headers, payload, timeout):
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read()

    @staticmethod
    def _parse_model_ids(body: bytes) -> list[str]:
        try:
            payload = json.loads(body.decode("utf-8"))
            rows = payload.get("data")
            ids = sorted({str(row.get("id")).strip() for row in rows
                          if isinstance(row, dict) and row.get("id")})
            return [i for i in ids if i]
        except (UnicodeError, ValueError, TypeError, AttributeError):
            return []

    def _server_up(self, timeout: int = 3) -> bool:
        """O dashboard responde sem autenticacao; prova que o servidor esta no ar."""
        try:
            status, _headers, _body = self._transport(
                "GET", self._dashboard_url(), {"Accept": "text/html"}, None, timeout)
            return 200 <= status < 500
        except Exception:
            return False

    def probe(self) -> ProviderInfo:
        if not self._server_up():
            return ProviderInfo(
                self.id, self.label, "freellmapi", Availability.OFFLINE,
                "Servidor FreeLLMAPI fora do ar em localhost:3001.",
                models=[], installed=None, authenticated=None,
            )
        if not self._credential:
            return ProviderInfo(
                self.id, self.label, "freellmapi", Availability.AUTH_REQUIRED,
                "Falta criar a conta no dashboard (http://localhost:3001) e colar as chaves gratuitas.",
                models=[], installed=True, authenticated=False,
            )
        status, _headers, body = self._request("GET", "/models", None, 10)
        if status in (401, 403):
            return ProviderInfo(
                self.id, self.label, "freellmapi", Availability.AUTH_REQUIRED,
                "Chave do FreeLLMAPI rejeitada; conferir a conta no dashboard.",
                models=[], installed=True, authenticated=False,
            )
        if status != 200:
            return ProviderInfo(
                self.id, self.label, "freellmapi", Availability.PROVIDER_ERROR,
                f"FreeLLMAPI respondeu HTTP {status or 'inacessivel'} ao listar modelos.",
                models=[], installed=True, authenticated=None,
            )
        self._models = self._parse_model_ids(body)
        if not self._models:
            return ProviderInfo(
                self.id, self.label, "freellmapi", Availability.AUTH_REQUIRED,
                "Conta criada, mas nenhum provedor com chave colada no dashboard.",
                models=[], installed=True, authenticated=True,
            )
        recently_verified = time.monotonic() - self._last_success_at < 300 if self._last_success_at else False
        return ProviderInfo(
            self.id, self.label, "freellmapi",
            Availability.AVAILABLE if recently_verified else Availability.UNKNOWN,
            "Chamada real concluida nesta sessao." if recently_verified else
            f"Servidor no ar com {len(self._models)} modelo(s); chamada real ainda nao verificada.",
            models=list(self._models), installed=True,
            authenticated=True if recently_verified else None,
        )

    def _resolve_model(self, model: str) -> str | None:
        """'auto' vira o primeiro modelo descoberto; sem modelo, None (honesto)."""
        if model != AUTO_MODEL:
            return model
        if not self._models:
            status, _headers, body = self._request("GET", "/models", None, 10)
            if status == 200:
                self._models = self._parse_model_ids(body)
        return self._models[0] if self._models else None

    def identifies_model(self, requested: str, reported: str | None) -> bool:
        # "auto" e apelido: o id canonico que o proxy devolve nunca vai ser
        # igual ao apelido; exigir igualdade rejeitaria toda chamada real.
        if requested == AUTO_MODEL:
            return True
        return super().identifies_model(requested, reported)

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        resume_session_id: str | None = None,
        timeout_s: int = 240,
        max_turns: int = 1,
    ) -> ProviderResult:
        del resume_session_id, max_turns
        if not self._server_up():
            return ProviderResult(False, availability=Availability.OFFLINE,
                                  error="Servidor FreeLLMAPI fora do ar em localhost:3001.")
        if not self._credential:
            return ProviderResult(False, availability=Availability.AUTH_REQUIRED,
                                  error="Falta criar a conta no dashboard (http://localhost:3001).")
        resolved = self._resolve_model(model)
        if resolved is None:
            return ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE,
                                  error="Nenhum modelo disponivel no FreeLLMAPI (sem chaves coladas).")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        request_body = json.dumps({
            "model": resolved, "messages": messages,
            "max_tokens": 512, "temperature": 0, "stream": False,
        }).encode("utf-8")
        started = time.perf_counter()
        status, headers, body = self._request("POST", "/chat/completions", request_body, timeout_s)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if status != 200:
            availability, detail = self._normalize_error(status, body, model=resolved)
            return ProviderResult(False, availability=availability, error=detail,
                                  duration_ms=duration_ms)
        try:
            payload = json.loads(body.decode("utf-8"))
            choices = payload.get("choices") or []
            message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError("missing content")
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            reported = payload.get("model") if isinstance(payload.get("model"), str) else None
            request_id = payload.get("id") if isinstance(payload.get("id"), str) else None
            if request_id is None:
                request_id = headers.get("x-request-id")
            self._last_success_at = time.monotonic()
            return ProviderResult(
                True, text=text, availability=Availability.AVAILABLE,
                provider_session_id=request_id, cost_usd=None,
                cost_basis=CostBasis.UNKNOWN,
                input_tokens=self._optional_int(usage.get("prompt_tokens")),
                output_tokens=self._optional_int(usage.get("completion_tokens")),
                duration_ms=duration_ms, model_reported=reported,
            )
        except (UnicodeError, ValueError, TypeError, IndexError):
            return ProviderResult(False, availability=Availability.PROVIDER_ERROR,
                                  error="FreeLLMAPI retornou uma resposta de sucesso invalida.",
                                  duration_ms=duration_ms)

    def _normalize_error(self, status: int, body: bytes, model: str | None) -> tuple[Availability, str]:
        try:
            payload = json.loads(body.decode("utf-8"))
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = error.get("message") if isinstance(error, dict) else error
            detail = detail if isinstance(detail, str) else ""
        except (UnicodeError, ValueError, TypeError):
            detail = ""
        detail = self._sanitize(detail) or f"FreeLLMAPI retornou HTTP {status or 'inacessivel'}"
        lowered = detail.lower()
        if status in (401, 403):
            availability = Availability.AUTH_REQUIRED
        elif status == 429 and any(word in lowered for word in ("quota", "credit", "balance", "cota")):
            availability = Availability.QUOTA_EXHAUSTED
        elif status == 429:
            availability = Availability.RATE_LIMITED
        elif status in (400, 404, 422) and model:
            availability = Availability.MODEL_UNAVAILABLE
        elif status == 0:
            availability = Availability.OFFLINE
        else:
            availability = Availability.PROVIDER_ERROR
        return availability, detail[:300]

    def _sanitize(self, detail: str) -> str:
        if self._credential:
            detail = detail.replace(self._credential, "[REDACTED]")
        return re.sub(r"(?i)\bbearer\s+[A-Za-z0-9_-]{16,}\b", "bearer [REDACTED]", detail)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def __repr__(self) -> str:
        return f"FreeLLMAPIAdapter(configured={bool(self._credential)}, models={len(self._models)})"
