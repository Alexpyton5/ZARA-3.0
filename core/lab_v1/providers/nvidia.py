"""NVIDIA hosted NIM adapter for the ZARA Lab provider contract."""
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
from core.paths import api_keys_path, data_dir

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
ULTRA_MODEL = 'nvidia/nemotron-3-ultra-550b-a55b'
# Lab plans, code edits and independent reviews need room for structured
# answers. The former 256-token ceiling truncated otherwise valid JSON.
NVIDIA_LAB_MAX_OUTPUT_TOKENS = 4096
HttpTransport = Callable[[str, str, dict[str, str], bytes | None, int], tuple[int, dict[str, str], bytes]]


class NvidiaApiAdapter(ProviderAdapter):
    id = "nvidia"
    label = "NVIDIA API Catalog"
    controlled_text_only = True

    def __init__(
        self,
        *,
        credential: str | None = None,
        config_path: Path | None = None,
        cache_path: Path | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._credential = credential if credential is not None else self._load_credential(config_path)
        self._cache_path = cache_path or (data_dir() / "lab" / "nvidia_models.json")
        self._transport = transport or self._urlopen_transport
        self._catalog = self._read_catalog()

    @staticmethod
    def _load_credential(config_path: Path | None) -> str:
        env_value = str(os.environ.get("NVIDIA_API_KEY") or "").strip()
        if env_value:
            return env_value
        path = config_path or api_keys_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return str(data.get("nvidia_api_key") or "").strip()
        except (OSError, ValueError, TypeError):
            return ""

    @property
    def declared_models(self) -> tuple[ModelDescriptor, ...]:
        models = self._catalog.get("models") if isinstance(self._catalog, dict) else None
        if not isinstance(models, list):
            return ()
        descriptors = []
        for item in models:
            if not isinstance(item, dict) or not isinstance(item.get("model_id"), str):
                continue
            descriptors.append(ModelDescriptor(
                provider_id=self.id,
                model_id=item["model_id"],
                display_name=str(item.get("display_name") or item["model_id"]),
                source=str(item.get("source") or "discovered"),
                observed_at=float(item["observed_at"]) if item.get("observed_at") else None,
                supports_effort=item['model_id'] == ULTRA_MODEL,
                effort_levels=('none', 'medium', 'high') if item['model_id'] == ULTRA_MODEL else (),
            ))
        return tuple(descriptors)

    def _read_catalog(self) -> dict[str, Any]:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_catalog(self, models: list[dict[str, Any]], observed_at: float) -> None:
        data = {"provider_id": self.id, "observed_at": observed_at, "models": models}
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self._cache_path)
        self._catalog = data

    def probe(self) -> ProviderInfo:
        if not self._credential:
            return ProviderInfo(
                self.id, self.label, "nvidia_api", Availability.AUTH_REQUIRED,
                "Credencial NVIDIA nao configurada no backend.", models=[],
                installed=None, authenticated=False,
            )
        models = [item.model_id for item in self.declared_models]
        verified = bool(models)
        return ProviderInfo(
            self.id, self.label, "nvidia_api",
            Availability.AVAILABLE if verified else Availability.UNKNOWN,
            "Credencial e catalogo NVIDIA verificados anteriormente." if verified
            else "Credencial NVIDIA configurada; acesso ainda nao verificado.",
            models=models, installed=None,
            authenticated=True if verified else None,
            quota_available=None,
        )

    def discover_models(self, *, timeout_s: int = 30) -> list[ModelDescriptor]:
        if not self._credential:
            raise NvidiaDiscoveryError(Availability.AUTH_REQUIRED, "Credencial NVIDIA ausente.")
        status, _headers, body = self._request("GET", "/models", None, timeout_s)
        if status != 200:
            availability, detail = self._normalize_error(status, body, model=None)
            raise NvidiaDiscoveryError(availability, detail)
        try:
            payload = json.loads(body.decode("utf-8"))
            rows = payload.get("data")
            ids = sorted({str(row.get("id")).strip() for row in rows if isinstance(row, dict) and row.get("id")})
        except (UnicodeError, ValueError, TypeError):
            raise NvidiaDiscoveryError(Availability.PROVIDER_ERROR, "Catalogo NVIDIA retornou JSON invalido.")
        if not ids:
            raise NvidiaDiscoveryError(Availability.PROVIDER_ERROR, "Catalogo NVIDIA nao retornou modelos.")
        observed_at = time.time()
        models = [{
            "model_id": model_id, "display_name": model_id,
            "source": "discovered", "observed_at": observed_at,
            "supports_effort": False, "effort_levels": [],
        } for model_id in ids]
        self._write_catalog(models, observed_at)
        return list(self.declared_models)

    def complete_with_options(self, **kwargs):
        options = kwargs.pop('options')
        return self.complete(**kwargs, effort=options.effort)

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        resume_session_id: str | None = None,
        timeout_s: int = 240,
        max_turns: int = 1,
        effort: str | None = None,
    ) -> ProviderResult:
        del resume_session_id, max_turns
        if not self._credential:
            return ProviderResult(False, availability=Availability.AUTH_REQUIRED,
                                  error="Credencial NVIDIA ausente.")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model, "messages": messages, "max_tokens": NVIDIA_LAB_MAX_OUTPUT_TOKENS,
            "temperature": 0, "stream": False,
        }
        if effort is not None:
            if model != ULTRA_MODEL or effort not in ('none', 'medium', 'high'):
                raise ValueError('Unsupported NVIDIA reasoning mode')
            payload['reasoning_effort'] = effort
        request_body = json.dumps(payload).encode("utf-8")
        started = time.perf_counter()
        status, headers, body = self._request("POST", "/chat/completions", request_body, timeout_s)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if status != 200:
            availability, detail = self._normalize_error(status, body, model=model)
            return ProviderResult(False, availability=availability, error=detail,
                                  duration_ms=duration_ms)
        try:
            payload = json.loads(body.decode("utf-8"))
            choices = payload.get("choices") or []
            message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str):
                raise ValueError("missing content")
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            reported = payload.get("model") if isinstance(payload.get("model"), str) else None
            request_id = payload.get("id") if isinstance(payload.get("id"), str) else None
            if request_id is None:
                request_id = headers.get("x-request-id")
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
                                  error="NVIDIA retornou uma resposta de sucesso invalida.",
                                  duration_ms=duration_ms)

    def _request(self, method: str, path: str, payload: bytes | None, timeout: int):
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._credential}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._transport(method, NVIDIA_BASE_URL + path, headers, payload, timeout)
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, {}, b""

    @staticmethod
    def _urlopen_transport(method, url, headers, payload, timeout):
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read()

    def _normalize_error(self, status: int, body: bytes, model: str | None) -> tuple[Availability, str]:
        try:
            payload = json.loads(body.decode("utf-8"))
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = error.get("message") if isinstance(error, dict) else error
            detail = detail if isinstance(detail, str) else ""
        except (UnicodeError, ValueError, TypeError):
            detail = ""
        detail = self._sanitize(detail) or f"NVIDIA API retornou HTTP {status or 'transport'}"
        lowered = detail.lower()
        if status in (401, 403):
            availability = Availability.AUTH_REQUIRED
        elif status == 429 and any(word in lowered for word in ("quota", "credit", "balance")):
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
        return re.sub(r"(?i)\b(?:bearer\s+)?nvapi-[A-Za-z0-9_-]+\b", "[REDACTED]", detail)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def __repr__(self) -> str:
        return f"NvidiaApiAdapter(credential_configured={bool(self._credential)}, models={len(self.declared_models)})"


class NvidiaDiscoveryError(RuntimeError):
    def __init__(self, availability: Availability, detail: str):
        super().__init__(detail)
        self.availability = availability
