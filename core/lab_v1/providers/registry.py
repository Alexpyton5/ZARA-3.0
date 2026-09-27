"""ZARA LAB REAL V1 — provider registry.

The gateway the rest of the Lab talks to. It never decides *how* a provider
works — that is the adapter's job — it only holds the set of adapters by id
and can list their current `ProviderInfo` for the UI.

Registering an adapter here is a promise that it is honestly probed: an
adapter that is not installed/configured must probe to a real
`Availability` (OFFLINE / AUTH_REQUIRED / ...), never to AVAILABLE, and its
`complete()` must never fabricate a model answer. `codex_cli` uses the official app-server. The direct Anthropic API adapter
remains unavailable until its transport is implemented.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import re
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from time import monotonic, time

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.claude_cli import ClaudeCliAdapter
from core.lab_v1.providers.opencode import OpenCodeAdapter
from core.lab_v1.providers.nvidia import NvidiaApiAdapter
from core.lab_v1.providers.harness import DeepSeekHarnessAdapter
from core.lab_v1.providers.local_ollama import OllamaLocalAdapter
from core.lab_v1.providers.nine_router import NineRouterAdapter
from core.paths import api_keys_path, data_dir

__all__ = ["ProviderRegistry", "default_registry", "ClaudeCliAdapter", "CodexCliAdapter", "AnthropicApiAdapter", "NvidiaApiAdapter", "OllamaLocalAdapter", "OpenCodeAdapter"]


# Backward-compatible registry name; implementation uses the official app-server.
from core.lab_v1.providers.codex_app_server import CodexAppServerAdapter as CodexCliAdapter


class AnthropicApiAdapter(ProviderAdapter):
    """Direct Anthropic API — probe-only stub.

    Checks only whether a key is *configured*, in `config/api_keys.json`
    (key name `anthropic_api_key`) or the `ANTHROPIC_API_KEY` env var. Never
    logs, returns, or otherwise exposes the key value — only the boolean.
    There is currently no such key configured, so this probes
    AUTH_REQUIRED.
    """

    id = "anthropic_api"
    label = "Anthropic API"

    def _has_configured_key(self) -> bool:
        if os.environ.get("ANTHROPIC_API_KEY"):
            return True
        try:
            path = api_keys_path()
            if not path.exists():
                return False
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            value = data.get("anthropic_api_key")
            return bool(value and str(value).strip())
        except (OSError, json.JSONDecodeError, ValueError):
            # Unreadable/malformed config is not evidence of a configured
            # key; treat it the same as "not configured" rather than raising
            # out of a probe(), which must be cheap and never crash the UI.
            return False

    def probe(self) -> ProviderInfo:
        if self._has_configured_key():
            return ProviderInfo(
                id=self.id,
                label=self.label,
                adapter="anthropic_api",
                availability=Availability.AVAILABLE,
                detail="Chave da API Anthropic configurada.",
                models=[],
                supports_effort=False,
                supports_resume=False,
                installed=None,
                authenticated=None,
            )
        return ProviderInfo(
            id=self.id,
            label=self.label,
            adapter="anthropic_api",
            availability=Availability.AUTH_REQUIRED,
            detail="Falta configurar a chave da API Anthropic.",
            models=[],
            supports_effort=False,
            supports_resume=False,
            authenticated=False,
        )

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
        return ProviderResult(
            ok=False,
            availability=Availability.AUTH_REQUIRED,
            error="Falta configurar a chave da API Anthropic.",
        )


class OwnerDisabledAdapter(ProviderAdapter):
    """Preserve metadata/history but enforce the owner's revoked provider use."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.id, self.label = adapter.id, adapter.label

    @property
    def declared_models(self):
        return getattr(self.adapter, 'declared_models', ())

    def probe(self):
        info = self.adapter.probe()
        info.availability = Availability.DISABLED_BY_OWNER_POLICY
        info.detail = 'Desativado por Alex. Historico preservado; invocacao e selecao automatica bloqueadas.'
        return info

    def complete(self, **kwargs):
        return ProviderResult(False, availability=Availability.DISABLED_BY_OWNER_POLICY,
                              error=self.probe().detail)

    def complete_with_options(self, **kwargs):
        return self.complete(**kwargs)


class ProviderRegistry:
    """Holds adapters by id. Does not own their lifecycle beyond that."""

    _ADVERSE = {Availability.AUTH_REQUIRED, Availability.QUOTA_EXHAUSTED, Availability.RATE_LIMITED}
    _ADVERSE_RETRY_SECONDS = {
        Availability.RATE_LIMITED: 300,
        Availability.AUTH_REQUIRED: 900,
        # Quota exhaustion is temporary for this app: do not require a
        # restart or a settings change when the monthly allowance returns.
        # Re-probe after five minutes and let the next real request recover
        # the provider health automatically.
        Availability.QUOTA_EXHAUSTED: 300,
    }
    # The provider list is polled every few seconds.  Keep this short enough
    # that an explicit refresh or a real result is promptly visible, while
    # avoiding repeated expensive auth/process probes on every UI render.
    _PROBE_CACHE_TTL_SECONDS = 5.0
    _PROBE_CACHE_MAX_ENTRIES = 64

    def __init__(self, health_path: Path | None = None, *, probe_ttl_s: float | None = None) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        self._health_path = health_path or (data_dir() / "lab" / "provider_health.json")
        self._health_lock = threading.Lock()
        self._health = self._read_health()
        self._probe_cache_lock = threading.RLock()
        self._probe_cache: OrderedDict[str, tuple[float, ProviderInfo]] = OrderedDict()
        self._probe_locks: dict[str, threading.Lock] = {}
        self._probe_ttl_s = (self._PROBE_CACHE_TTL_SECONDS if probe_ttl_s is None
                             else max(0.0, float(probe_ttl_s)))

    def _read_health(self) -> dict[str, dict]:
        try:
            data = json.loads(self._health_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_health(self) -> None:
        self._health_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._health_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._health, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self._health_path)

    def register(self, adapter: ProviderAdapter) -> None:
        with self._probe_cache_lock:
            self._adapters[adapter.id] = adapter
            self._probe_cache.pop(adapter.id, None)
            self._probe_locks.setdefault(adapter.id, threading.Lock())

    def invalidate_probe_cache(self, provider_id: str | None = None) -> None:
        """Forget cached factual probes, optionally for one provider."""
        with self._probe_cache_lock:
            if provider_id is None:
                self._probe_cache.clear()
            else:
                self._probe_cache.pop(provider_id, None)

    def get(self, provider_id: str) -> ProviderAdapter | None:
        return self._adapters.get(provider_id)

    def list_providers(self, *, force_refresh: bool = False) -> list[ProviderInfo]:
        """Return current provider info, probing only after the short TTL.

        Cached entries are factual adapter results.  Every returned object is
        a copy, because the adverse health overlay below is a projection and
        must never mutate the cached fact.
        """
        with self._probe_cache_lock:
            adapter_ids = tuple(self._adapters)
        infos = [self._probe_one(provider_id, force_refresh=force_refresh)
                 for provider_id in adapter_ids]
        for info in infos:
            self._overlay_health(info)
        return infos

    def _probe_one(self, provider_id: str, *, force_refresh: bool = False) -> ProviderInfo:
        """Probe one adapter with a per-provider lock and bounded cache."""
        with self._probe_cache_lock:
            adapter = self._adapters.get(provider_id)
            if adapter is None:
                return ProviderInfo(id=provider_id, label=provider_id, adapter=provider_id)
            probe_lock = self._probe_locks.setdefault(provider_id, threading.Lock())
        with probe_lock:
            with self._probe_cache_lock:
                cached = self._probe_cache.get(provider_id)
                if (not force_refresh and cached is not None
                        and monotonic() - cached[0] < self._probe_ttl_s):
                    info = deepcopy(cached[1])
                    self._probe_cache.move_to_end(provider_id)
                    return info
            info = deepcopy(adapter.probe())
            # Record completion time: a slow probe must receive its full TTL.
            with self._probe_cache_lock:
                self._probe_cache[provider_id] = (monotonic(), deepcopy(info))
                self._probe_cache.move_to_end(provider_id)
                while len(self._probe_cache) > self._PROBE_CACHE_MAX_ENTRIES:
                    self._probe_cache.popitem(last=False)
            return info

    def _overlay_health(self, info: ProviderInfo) -> None:
        with self._health_lock:
            observed = deepcopy(self._health.get(f"provider:{info.id}"))
        if (info.availability != Availability.DISABLED_BY_OWNER_POLICY and observed
                and observed.get("availability") in {item.value for item in self._ADVERSE}):
            adverse = Availability(observed["availability"])
            observed_at = float(observed.get("timestamp") or 0)
            retry_after = observed.get('retry_after')
            retry_due = float(retry_after) if isinstance(retry_after, (int, float)) else (
                observed_at + self._ADVERSE_RETRY_SECONDS[adverse])
            if time() < retry_due:
                info.availability = adverse
                info.detail = str(observed.get("detail") or info.detail)
                info.observed_at = observed_at or info.observed_at
            elif info.availability is Availability.AVAILABLE:
                info.detail = 'Bloqueio anterior expirou; a proxima execucao real revalida o recurso.'

    def list_models(self, provider_id: str | None = None) -> list[dict]:
        """Return declared/cached metadata without probing or making remote calls."""
        adapters = self._adapters.values() if provider_id is None else [self._adapters.get(provider_id)]
        return [
            descriptor.to_dict()
            for adapter in adapters if adapter is not None
            for descriptor in getattr(adapter, "declared_models", ())
        ]

    def discover_models(self, provider_id: str) -> list[dict]:
        adapter = self._adapters.get(provider_id)
        discover = getattr(adapter, "discover_models", None) if adapter is not None else None
        if not callable(discover):
            return []
        return [item.to_dict() for item in discover()]

    def record_result(self, provider_id: str, model_id: str, result: ProviderResult, *, observed_at=None) -> None:
        """Persist only sanitized availability metadata from a real result."""
        availability = result.availability
        scope = "model" if result.ok else (
            "provider" if availability in {Availability.AUTH_REQUIRED, Availability.QUOTA_EXHAUSTED} else "model"
        )
        key = f"{scope}:{provider_id}" + (f":{model_id}" if scope == "model" else "")
        raw_detail = str(result.error or ("Chamada concluida." if result.ok else availability.value))
        raw_detail = re.sub(r"(?i)\b(?:bearer\s+)?(?:nvapi-|sk-(?:proj-|ant-)?)?[A-Za-z0-9_-]{32,}\b", "[REDACTED]", raw_detail)
        detail = " ".join(raw_detail.split())[:300]
        record = {
            "availability": Availability.AVAILABLE.value if result.ok else availability.value,
            "scope": scope,
            "source": "provider_result",
            "timestamp": time() if observed_at is None else float(observed_at),
            "detail": detail,
            "retry_after": None,
        }
        with self._health_lock:
            self._health[key] = record
            if result.ok:
                previous = self._health.get(f'provider:{provider_id}')
                if (previous and previous.get('availability') in {a.value for a in self._ADVERSE}
                        and previous.get('timestamp', 0) <= record['timestamp']):
                    self._health[f'provider:{provider_id}'] = {**record, 'scope': 'provider',
                        'recovered_by_model': model_id, 'previous_adverse': previous}
            self._write_health()
        # A real invocation is fresher evidence than the cached probe.  The
        # next projection must revalidate the adapter while retaining this
        # result's adverse overlay immediately.
        self.invalidate_probe_cache(provider_id)

    def model_status(self, provider_id: str, model_id: str, *, providers=None) -> dict:
        """One truth projection for router/UI; provider denial wins over stale success."""
        if providers is None:
            info = self._probe_one(provider_id)
            self._overlay_health(info)
        else:
            info = next((p for p in providers if p.id == provider_id), None)
        model = self._health.get(f'model:{provider_id}:{model_id}', {})
        if info is None or info.availability != Availability.AVAILABLE:
            return {'availability': info.availability.value if info else 'UNKNOWN',
                    'detail': info.detail if info else 'Provider not registered'}
        if model.get('source') == 'provider_result':
            return {'availability': model['availability'], 'detail': model.get('detail'),
                    'observed_at': model.get('timestamp')}
        return {'availability': 'DISCOVERED_UNPROVEN', 'detail': 'Catalog is not inference proof'}

    def health_snapshot(self) -> dict[str, dict]:
        return {key: dict(value) for key, value in self._health.items()}


def default_registry() -> ProviderRegistry:
    """The standard provider set the Lab UI shows."""
    registry = ProviderRegistry()
    # Registered unwrapped since 2026-09-10 (MORNING-01): Alex re-authorized
    # `claude_cli` as an internal Lab worker, reusing the Claude Code CLI session
    # already authenticated on this machine. `anthropic_api` below is a *different*
    # provider (direct API key) and stays revoked.
    registry.register(ClaudeCliAdapter())
    registry.register(CodexCliAdapter())
    registry.register(DeepSeekHarnessAdapter())
    registry.register(OwnerDisabledAdapter(AnthropicApiAdapter()))
    registry.register(NvidiaApiAdapter())
    registry.register(OllamaLocalAdapter())
    registry.register(NineRouterAdapter())
    # OpenCode — 35 modelos gratuitos via instalação local, sem custo extra.
    # Usa login do usuário já configurado no OpenCode no PC.
    registry.register(OpenCodeAdapter())
    return registry
