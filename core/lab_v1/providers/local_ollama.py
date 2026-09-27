"""Ollama local adapter for the ZARA Lab provider contract.

Talks to Ollama's OpenAI-compatible HTTP API (`/v1/models`, `/v1/chat/completions`)
on localhost by default. Because the surface is the OpenAI-compatible one, the
same adapter also covers LM Studio (`http://localhost:1234/v1`), Jan
(`http://localhost:1337/v1`) and llama-server by changing `base_url` alone.

Like `nvidia.py`, this adapter uses only the stdlib (`urllib`) and accepts an
injectable transport so tests never need a real Ollama install. `probe()` is a
single cheap GET and never spends a token; `complete()` makes exactly one POST
and never fabricates an answer — Ollama echoes back the exact model id it was
given, so the strict `identifies_model` default holds and is not overridden.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter, classify_error_text

OLLAMA_BASE_URL = "http://localhost:11434/v1"

#: Models ZARA offers even while the server is down (probe cannot see them).
#: These are the ids Ollama itself uses (`ollama pull <id>`).
OLLAMA_MODELS = (
    "qwen2.5-coder:7b",
    "qwen3:8b",
    "llama3.1:8b",
    "phi4-mini",
    "gpt-oss:20b",
)

HttpTransport = Callable[[str, str, dict[str, str], bytes | None, int], tuple[int, dict[str, str], bytes]]


class OllamaLocalAdapter(ProviderAdapter):
    id = "ollama"
    label = "Ollama Local"
    # A local model server produces text and nothing else: no shell, no tools.
    controlled_text_only = True
    declared_models = tuple(
        ModelDescriptor(provider_id="ollama", model_id=model, display_name=model)
        for model in OLLAMA_MODELS
    )

    def __init__(self, *, base_url: str = OLLAMA_BASE_URL, transport: HttpTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or self._urlopen_transport

    # ------------------------------------------------------------------ probe
    def probe(self) -> ProviderInfo:
        """Cheap GET /v1/models. Never a completion, never fabricated success."""
        status, _headers, body = self._request("GET", "/models", None, timeout_s=2)
        if status == 0:
            return ProviderInfo(
                id=self.id, label=self.label, adapter=self.id,
                availability=Availability.OFFLINE,
                detail="Servidor Ollama nao respondeu (esta rodando? 'ollama serve' na porta 11434).",
                models=[],
                installed=None, authenticated=None,
            )
        if status != 200:
            detail = self._extract_error_detail(body) or f"HTTP {status}"
            return ProviderInfo(
                id=self.id, label=self.label, adapter=self.id,
                availability=classify_error_text(detail) if status == 429 else Availability.PROVIDER_ERROR,
                detail=f"{self.label} respondeu HTTP {status}: {detail}"[:300],
                models=[],
                installed=None, authenticated=None,
            )
        models = self._parse_model_ids(body)
        if not models:
            # Reachable but empty: still usable in principle, nothing to run yet.
            return ProviderInfo(
                id=self.id, label=self.label, adapter=self.id,
                availability=Availability.AVAILABLE,
                detail="Servidor Ollama acessivel, mas nenhum modelo instalado ('ollama pull <modelo>').",
                models=[],
                installed=True, authenticated=True,
            )
        return ProviderInfo(
            id=self.id, label=self.label, adapter=self.id,
            availability=Availability.AVAILABLE,
            detail=f"Servidor Ollama acessivel com {len(models)} modelo(s).",
            models=models,
            installed=True, authenticated=True,
        )

    # --------------------------------------------------------------- complete
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
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "stream": False}
        request_body = json.dumps(payload).encode("utf-8")
        started = time.perf_counter()
        status, headers, body = self._request("POST", "/chat/completions", request_body, timeout_s)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if status != 200:
            availability, detail = self._normalize_error(status, body)
            return ProviderResult(False, availability=availability, error=detail,
                                  duration_ms=duration_ms)
        try:
            payload = json.loads(body.decode("utf-8"))
            choices = payload.get("choices") or []
            message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str):
                raise ValueError("missing content")
            reported = payload.get("model") if isinstance(payload.get("model"), str) else None
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
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
                                  error="Ollama retornou uma resposta de sucesso invalida.",
                                  duration_ms=duration_ms)

    # ----------------------------------------------------------------- inner
    def _request(self, method: str, path: str, payload: bytes | None, timeout_s: int):
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._transport(method, self._base_url + path, headers, payload, timeout_s)
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            # Connection refused, timeout, DNS failure — the server is simply
            # not there. status 0 means "transport-level failure" downstream.
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
            return [item for item in ids if item]
        except (UnicodeError, ValueError, TypeError):
            return []

    @staticmethod
    def _extract_error_detail(body: bytes) -> str:
        try:
            payload = json.loads(body.decode("utf-8"))
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = error.get("message") if isinstance(error, dict) else error
            return detail if isinstance(detail, str) else ""
        except (UnicodeError, ValueError, TypeError):
            return ""

    def _normalize_error(self, status: int, body: bytes) -> tuple[Availability, str]:
        detail = self._extract_error_detail(body)
        if status == 0:
            return Availability.OFFLINE, (
                "Servidor Ollama nao respondeu (timeout ou conexao recusada)."
            )
        lowered = detail.lower()
        if status == 404 and ("model" in lowered or "not found" in lowered):
            return Availability.MODEL_UNAVAILABLE, (
                detail or f"Modelo nao encontrado no Ollama (HTTP {status})."
            )
        if status == 429:
            return Availability.RATE_LIMITED, detail or "Ollama retornou HTTP 429."
        if status in (401, 403):
            return Availability.AUTH_REQUIRED, detail or f"Ollama retornou HTTP {status}."
        if not detail:
            detail = f"Ollama retornou HTTP {status}."
        if status in (400, 404, 422):
            return Availability.MODEL_UNAVAILABLE, detail or f"Ollama retornou HTTP {status}."
        # Fall through to the shared free-text classifier so wording stays
        # consistent with every other adapter by construction.
        availability = classify_error_text(detail or f"Ollama retornou HTTP {status}.")
        return availability, detail[:300]

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def __repr__(self) -> str:
        return f"OllamaLocalAdapter(base_url={self._base_url!r})"
