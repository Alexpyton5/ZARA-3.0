"""9Router adapter for ZARA Lab — proxies the local 9Router OpenAI-compatible gateway.

Reads the same config Codex itself uses (CODEX_HOME/config.toml → [model_providers.9router]).
This is the cheap mechanical worker: PLAN_INCLUDED via 9Router own subscription,
never guessing cost. If 9Router is not configured, probe is AUTH_REQUIRED.

Wire: uses /v1/responses (wire_api=responses) like Codex does, with fallback to
/v1/chat/completions for legacy models. Only one real call per complete().
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import tomllib
from pathlib import Path
from typing import Any

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter, classify_error_text
from core.paths import data_dir

DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
_PROBE_CACHE_SECONDS = 15.0

def _read_9router_config(settings_path: Path | None = None) -> tuple[str, dict[str, str]]:
    """Load the relay configuration without making Codex itself depend on it.

    New Codex versions reject a numeric provider name in ``config.toml``.
    ZARA therefore owns this local relay configuration under its own data
    directory.  The legacy Codex location remains a read-only migration path
    for older installs until the local file has been created.
    """
    base_url = DEFAULT_BASE_URL
    headers: dict[str, str] = {}
    try:
        path = settings_path or (data_dir() / "lab" / "nine_router_config.json")
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("base_url"), str) and data["base_url"].strip():
                base_url = data["base_url"].strip().rstrip("/")
            http_headers = data.get("http_headers") or {}
            if isinstance(http_headers, dict):
                for k, v in http_headers.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        headers[k] = v.strip()
            return base_url, headers

        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        legacy_path = home / "config.toml"
        if legacy_path.is_file():
            data = tomllib.loads(legacy_path.read_text(encoding="utf-8"))
            prov = data.get("model_providers", {}).get("9router") or {}
            if isinstance(prov.get("base_url"), str) and prov["base_url"].strip():
                base_url = prov["base_url"].strip().rstrip("/")
            http_headers = prov.get("http_headers") or {}
            if isinstance(http_headers, dict):
                for k, v in http_headers.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        headers[k] = v.strip()
    except Exception:
        pass
    return base_url, headers

class NineRouterAdapter(ProviderAdapter):
    id = "nine_router"
    label = "9Router \u00b7 Muse Spark Free"
    controlled_text_only = True

    def __init__(self, *, cache_path: Path | None = None, base_url: str | None = None,
                 headers: dict[str, str] | None = None, settings_path: Path | None = None):
        self._base_url, cfg_headers = _read_9router_config(settings_path)
        if base_url:
            self._base_url = base_url.rstrip("/")
        self._headers = {**cfg_headers, **(headers or {})}
        self._cache_path = cache_path or (data_dir() / "lab" / "nine_router_models.json")
        self._catalog = self._read_catalog()
        self._last_probe_at = 0.0
        self._last_probe: ProviderInfo | None = None

    def _read_catalog(self) -> dict[str, Any]:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_catalog(self, models: list[dict[str, Any]]) -> None:
        data = {"provider_id": self.id, "observed_at": time.time(), "models": models}
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._cache_path)
        self._catalog = data

    def _request(self, method: str, path: str, body: bytes | None, timeout_s: int) -> tuple[int, bytes]:
        url = self._base_url + path
        req_headers = {"Content-Type": "application/json"}
        req_headers.update(self._headers)
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() or b""
        except Exception as exc:
            raise exc

    @property
    def declared_models(self) -> tuple[ModelDescriptor, ...]:
        models = self._catalog.get("models") if isinstance(self._catalog, dict) else None
        if not isinstance(models, list):
            return ()
        out = []
        for item in models:
            if not isinstance(item, dict) or not isinstance(item.get("model_id"), str):
                continue
            out.append(ModelDescriptor(
                provider_id=self.id,
                model_id=item["model_id"],
                display_name=str(item.get("display_name") or item["model_id"]),
                source=str(item.get("source") or "discovered"),
                observed_at=float(item["observed_at"]) if item.get("observed_at") else None,
                supports_effort=False,
                effort_levels=(),
            ))
        return tuple(out)

    def discover_models(self, *, timeout_s: int = 15) -> list[ModelDescriptor]:
        if not self._headers.get("Authorization"):
            raise RuntimeError("9Router Authorization missing in config.toml")
        status, body = self._request("GET", "/models", None, timeout_s)
        if status != 200:
            raise RuntimeError(f"9Router /models HTTP {status}: {body[:300]!r}")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"9Router models decode failed: {exc}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise RuntimeError("9Router /models missing data list")
        models = []
        now = time.time()
        for entry in data:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            mid = entry["id"]
            models.append({"model_id": mid, "display_name": mid, "source": "discovered", "observed_at": now})
        self._write_catalog(models)
        return list(self.declared_models)

    def probe(self) -> ProviderInfo:
        if not self._headers.get("Authorization"):
            return ProviderInfo(self.id, self.label, "nine_router", Availability.AUTH_REQUIRED,
                "9Router nao configurado em ~/.codex/config.toml (falta model_providers.9router.http_headers.Authorization).",
                models=[], installed=None, authenticated=False)
        stamp = time.monotonic()
        if self._last_probe is not None and stamp - self._last_probe_at < _PROBE_CACHE_SECONDS:
            return self._last_probe
        try:
            # A persisted model catalog proves only past discovery.  The Lab
            # must not hand a mission to a dead local gateway just because an
            # old cache exists; /models is a bounded, non-inference liveness
            # check that also refreshes the catalog when the relay is healthy.
            self.discover_models(timeout_s=3)
            models = [m.model_id for m in self.declared_models]
            if models:
                info = ProviderInfo(self.id, self.label, "nine_router", Availability.AVAILABLE,
                    f"9Router gateway ativo ({len(models)} modelos) via {self._base_url}.",
                    models=models, installed=True, authenticated=True, supports_effort=False)
                self._last_probe_at, self._last_probe = stamp, info
                return info
        except Exception as exc:
            info = ProviderInfo(self.id, self.label, "nine_router", Availability.OFFLINE,
                f"9Router nao respondeu em {self._base_url}: {str(exc)[:160]}",
                models=[], installed=True, authenticated=None)
            self._last_probe_at, self._last_probe = stamp, info
            return info
        info = ProviderInfo(self.id, self.label, "nine_router", Availability.UNKNOWN,
            "9Router configurado mas catalogo vazio.", models=[], installed=True, authenticated=True)
        self._last_probe_at, self._last_probe = stamp, info
        return info

    def complete(self, *, prompt: str, model: str, system: str | None = None, resume_session_id: str | None = None, timeout_s: int = 240, max_turns: int = 1) -> ProviderResult:
        if resume_session_id:
            return ProviderResult(False, availability=Availability.ERROR, error="9Router nao suporta resume")
        if not self._headers.get("Authorization"):
            return ProviderResult(False, availability=Availability.AUTH_REQUIRED, error="9Router Authorization ausente")
        if model not in {m.model_id for m in self.declared_models}:
            try:
                self.discover_models(timeout_s=8)
            except Exception:
                pass
            if model not in {m.model_id for m in self.declared_models}:
                return ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE, error=f"Model {model} ausente no catalogo 9Router")
        started = time.monotonic()
        try:
            body = {
                "model": model,
                "input": prompt,
                "max_output_tokens": 8192,
                
            }
            if system and system.strip():
                body["instructions"] = system.strip()[:8000]
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            status, resp_body = self._request("POST", "/responses", raw, timeout_s)
            if status == 404:
                chat_body = {
                    "model": model,
                    "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}],
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "stream": False,
                }
                raw2 = json.dumps(chat_body, ensure_ascii=False).encode("utf-8")
                status, resp_body = self._request("POST", "/chat/completions", raw2, timeout_s)
                if status != 200:
                    avail = Availability.AUTH_REQUIRED if status in (401,403) else (Availability.RATE_LIMITED if status==429 else Availability.BUSY if status==503 else Availability.ERROR)
                    return ProviderResult(False, availability=avail, error=f"9Router chat HTTP {status}: {resp_body[:300].decode('utf-8', errors='ignore')}", duration_ms=int((time.monotonic()-started)*1000))
                try:
                    payload = json.loads(resp_body.decode("utf-8"))
                    text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not isinstance(text, str) or not text.strip():
                        text = ""
                    if not text.strip():
                        return ProviderResult(False, availability=Availability.ERROR, error="9Router retornou resposta vazia", duration_ms=int((time.monotonic()-started)*1000))
                    return ProviderResult(True, text=text.strip(), availability=Availability.AVAILABLE, cost_basis=CostBasis.UNKNOWN, model_reported=payload.get("model"), duration_ms=int((time.monotonic()-started)*1000))
                except Exception as exc:
                    return ProviderResult(False, availability=classify_error_text(str(exc)), error=str(exc)[:300], duration_ms=int((time.monotonic()-started)*1000))
            if status != 200:
                avail = Availability.AUTH_REQUIRED if status in (401,403) else (Availability.RATE_LIMITED if status==429 else Availability.QUOTA_EXHAUSTED if status==402 else Availability.BUSY if status==503 else classify_error_text(resp_body.decode("utf-8", errors="ignore")[:300]))
                detail = resp_body[:400].decode("utf-8", errors="ignore")
                return ProviderResult(False, availability=avail, error=f"9Router responses HTTP {status}: {detail[:300]}", duration_ms=int((time.monotonic()-started)*1000))
            try:
                text_raw = resp_body.decode("utf-8").strip()
                if "data:" in text_raw:
                    idx = text_raw.find("data:")
                    json_part = text_raw[:idx].strip()
                else:
                    json_part = text_raw
                payload = json.loads(json_part)
                output = payload.get("output") or []
                text_parts = []
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "message" and item.get("role") == "assistant":
                        for c in item.get("content") or []:
                            if isinstance(c, dict) and c.get("type") == "output_text":
                                t = c.get("text")
                                if isinstance(t, str) and t.strip():
                                    text_parts.append(t.strip())
                text = "\n".join(text_parts).strip()
                if not text:
                    detail = payload.get("incomplete_details")
                    if detail:
                        reason = detail.get("reason") if isinstance(detail, dict) else str(detail)
                        if reason == "max_output_tokens":
                            return ProviderResult(False, availability=Availability.ERROR, error=f"9Router incompleto por limite de tokens ({detail}); tente novamente com prompt menor ou aumente max_output_tokens", duration_ms=int((time.monotonic()-started)*1000))
                        return ProviderResult(False, availability=Availability.ERROR, error=f"9Router incomplete: {detail}", duration_ms=int((time.monotonic()-started)*1000))
                    return ProviderResult(False, availability=Availability.ERROR, error="9Router retornou sem texto", duration_ms=int((time.monotonic()-started)*1000))
                return ProviderResult(True, text=text, availability=Availability.AVAILABLE, cost_basis=CostBasis.UNKNOWN, model_reported=payload.get("model"), duration_ms=int((time.monotonic()-started)*1000), input_tokens=(payload.get("usage") or {}).get("input_tokens"), output_tokens=(payload.get("usage") or {}).get("output_tokens"))
            except Exception as exc:
                return ProviderResult(False, availability=classify_error_text(str(exc)), error=f"9Router parse falhou: {str(exc)[:200]}", duration_ms=int((time.monotonic()-started)*1000))
        except Exception as exc:
            err = str(exc)[:300]
            return ProviderResult(False, availability=classify_error_text(err), error=err or "9Router falhou", duration_ms=int((time.monotonic()-started)*1000))



