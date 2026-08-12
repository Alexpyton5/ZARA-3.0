"""Local coordination, audit, and approved-skill discovery for ZARA 3.0."""
from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from core.model_router import ModelProvider, ModelRouter, normalize_auto_engine, route_message

_SKILL_ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SENSITIVE_KEYS = {"api_key", "authorization", "credential", "password", "secret", "token"}
_BLOCKED_OUTCOME_MARKERS = (
    "confirmation required",
    "requires confirmation",
    "confirmação explícita",
    "ação com efeito externo",
    "tarefas livres de desktop estão bloqueadas",
    "não permitido",
    "not allowed",
)

CONVERSATIONAL_SYSTEM_PROMPT = (
    "Você é ZARA, a assistente pessoal de Alex. Responda em português do Brasil "
    "quando ele falar em português. Em conversa casual, soe humana, direta e "
    "acolhedora: normalmente use de uma a três frases curtas. Não transforme uma "
    "pergunta simples em lista, tutorial ou palestra, salvo quando Alex pedir ou "
    "quando isso for realmente necessário. Responda primeiro ao que foi perguntado "
    "e não encerre toda resposta com outra pergunta. Seja precisa e não invente certezas."
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _tool_result_status(result: Any) -> str:
    outcome = str(result or "").strip().lower()
    if any(marker in outcome for marker in _BLOCKED_OUTCOME_MARKERS):
        return "blocked"
    if "bloquead" in outcome or outcome.startswith("unknown tool"):
        return "blocked" if "bloquead" in outcome else "failed"
    if (outcome.startswith("tool '") and "failed:" in outcome) or outcome.startswith(("error", "erro", "failed")):
        return "failed"
    return "succeeded"

def recent_tool_events(base_dir: Path | None = None, limit: int = 12) -> list[dict[str, Any]]:
    """Read compact local action receipts without exposing argument values."""
    root = base_dir or _base_dir()
    audit_path = root / "memory" / "zara_tool_audit.jsonl"
    safe_limit = max(1, min(int(limit), 50))
    if not audit_path.is_file():
        return []
    events: deque[dict[str, Any]] = deque(maxlen=safe_limit)
    try:
        with audit_path.open("r", encoding="utf-8") as audit_file:
            for line in audit_file:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict) or event.get("event") != "tool_execution":
                    continue
                names = event.get("argument_names", [])
                safe_names = [
                    str(name)[:80]
                    for name in names
                    if str(name).lower() not in _SENSITIVE_KEYS
                ] if isinstance(names, list) else []
                status = str(event.get("status") or "").lower()
                if status not in {"succeeded", "blocked", "failed"}:
                    status = "succeeded" if event.get("succeeded", False) else "failed"
                events.append(
                    {
                        "timestamp": str(event.get("timestamp") or "")[:32],
                        "tool": str(event.get("tool") or "unknown")[:80],
                        "argument_names": safe_names,
                        "status": status,
                    }
                )
    except OSError:
        return []
    return list(reversed(events))

class ApprovedSkillRegistry:
    """Discovers local skill manifests without executing their entrypoints."""

    def __init__(self, base_dir: Path | None = None) -> None:
        root = base_dir or _base_dir()
        self.root = root / "zoe_skills"
        self.approved_dir = self.root / "approved"
        self.staging_dir = self.root / "staging"

    def ensure_layout(self) -> None:
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def approved_skills(self) -> list[dict[str, str]]:
        if not self.approved_dir.is_dir():
            return []
        skills: list[dict[str, str]] = []
        for skill_dir in self.approved_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / "manifest.json"
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    skills.append({
                        "id": manifest.get("id", skill_dir.name),
                        "name": manifest.get("name", skill_dir.name),
                        "version": manifest.get("version", "0.0.0"),
                        "description": manifest.get("description", ""),
                    })
                except (json.JSONDecodeError, OSError):
                    pass
        return skills


class ZaraOrchestrator:
    """Main orchestrator for ZARA 3.0 - routes messages, coordinates components."""

    def __init__(self):
        self.model_router = ModelRouter()
        self.initialized = False
        self.last_engine_used: str | None = None
        self.last_route_policy: str | None = None

    async def initialize(self):
        """Initialize orchestrator components"""
        # Model router loads API keys on init
        self.initialized = True
        print("[Orchestrator] Initialized with ModelRouter")

    async def process_message(
        self,
        message: str,
        engine: str = None,
        context: dict = None,
        history: list[dict] | None = None,
        require_tools: bool = False,
        stream: bool = False
    ) -> str:
        """Route a user message according to AUTO SMART/ECONOMY or a manual engine."""
        if not self.initialized:
            await self.initialize()

        normalized_engine = normalize_auto_engine(engine)

        # Manual means manual: never silently leave the selected engine.
        if normalized_engine not in {"auto_smart", "auto_economy"}:
            self.last_route_policy = "manual"
            self.last_engine_used = normalized_engine
            response = await self._call_model_direct(
                message, normalized_engine, stream, history=history
            )
            if self._is_error_response(response):
                self.model_router.mark_failure(normalized_engine, response)
                self.model_router.record_usage(normalized_engine, success=False)
            else:
                self.model_router.mark_success(normalized_engine)
                self.model_router.record_usage(normalized_engine, success=True)
            return response

        route_context = dict(context or {})
        if require_tools:
            route_context["require_tools"] = True

        policy = "economy" if normalized_engine == "auto_economy" else "smart"
        self.last_route_policy = policy
        primary_model, fallback_chain = route_message(
            message=message,
            context=route_context,
            require_tools=require_tools,
            require_streaming=stream,
            policy=policy,
        )

        if not primary_model:
            self.last_engine_used = None
            return "Erro: Nenhum motor R$0 saudável e compatível está disponível no momento."

        models_to_try = [primary_model, *fallback_chain]
        last_error = None

        for model in models_to_try:
            response = await self._call_model_direct(
                message, model.id, stream, history=history
            )
            if response and not self._is_error_response(response):
                self.model_router.mark_success(model.id)
                self.model_router.record_usage(model.id, success=True)
                self.last_engine_used = model.id
                return response

            last_error = response
            self.model_router.mark_failure(model.id, str(response))
            self.model_router.record_usage(model.id, success=False)
            print(f"[Orchestrator] AUTO {policy}: {model.id} unavailable -> fallback")

        self.last_engine_used = None
        return f"Erro: Todos os motores R$0 disponíveis falharam. Último erro: {last_error}"

    @staticmethod
    def _is_error_response(response: object) -> bool:
        normalized = str(response or "").strip().lower()
        # Resposta vazia ou so com espacos = falha do provider, nunca sucesso.
        return (not normalized) or normalized.startswith(("error", "erro", "failed"))

    async def _call_model_direct(
        self,
        message: str,
        model_id: str,
        stream: bool = False,
        history: list[dict] | None = None,
    ) -> str:
        """Call a specific model directly"""
        from core.model_router import get_model_config

        model_config = get_model_config(model_id)
        if not model_config:
            return f"Error: Model {model_id} not found"

        # Check if Hermes (local)
        if model_config.provider == ModelProvider.HERMES:
            return await self._call_hermes(message, model_config, stream, history)

        # For cloud models, use httpx to call API
        return await self._call_cloud_model(message, model_config, stream, history)

    @staticmethod
    def _normalized_history(
        history: list[dict] | None, current_message: str
    ) -> list[dict[str, str]]:
        """Keep valid recent turns and drop a duplicated current user message."""
        normalized: list[dict[str, str]] = []
        for turn in (history or [])[-16:]:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", "")).strip().lower()
            content = str(turn.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        if (
            normalized
            and normalized[-1]["role"] == "user"
            and normalized[-1]["content"] == current_message.strip()
        ):
            normalized.pop()
        return normalized

    async def _call_hermes(
        self, message: str, model_config, stream: bool = False, history=None
    ) -> str:
        """Call Hermes Gateway"""
        try:
            import httpx

            api_key = model_config.api_key_env
            import os
            key = os.environ.get(api_key, "zara-hermes-bridge-key-2026")

            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model_config.id,
                    "messages": [
                        {"role": "system", "content": CONVERSATIONAL_SYSTEM_PROMPT},
                        *self._normalized_history(history, message),
                        {"role": "user", "content": message}
                    ],
                    "stream": stream,
                }

                if stream:
                    # For streaming, we'd need to handle SSE - simplified for now
                    pass

                resp = await client.post(
                    f"{model_config.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=120.0
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                else:
                    return f"Error: Hermes returned {resp.status_code}"

        except Exception as e:
            return f"Error calling Hermes: {e}"

    async def _call_cloud_model(
        self, message: str, model_config, stream: bool = False, history=None
    ) -> str:
        """Call cloud model API (Groq, Gemini, NVIDIA, Z.AI)"""
        try:
            import os

            import httpx

            api_key = os.environ.get(model_config.api_key_env)
            if not api_key:
                return f"Error: API key not configured for {model_config.provider.value}"

            async with httpx.AsyncClient(timeout=120.0) as client:
                if model_config.provider == ModelProvider.GEMINI:
                    return await self._call_gemini(message, model_config, api_key, client, history)
                else:
                    return await self._call_openai_compatible(message, model_config, api_key, client, history)

        except Exception as e:
            return f"Error calling {model_config.provider.value}: {e}"

    async def _call_openai_compatible(self, message: str, model_config, api_key: str, client: httpx.AsyncClient, history=None) -> str:
        """Call OpenAI-compatible API (Groq, NVIDIA, Z.AI)"""
        payload = {
            "model": model_config.api_model,
            "messages": [
                {"role": "system", "content": CONVERSATIONAL_SYSTEM_PROMPT},
                *self._normalized_history(history, message),
                {"role": "user", "content": message}
            ],
            "max_tokens": model_config.max_tokens,
            "temperature": 0.7,
        }

        payload["model"] = model_config.api_model

        # Nemotron 3 hosted examples recommend these sampling values.
        if model_config.id in {"nvidia_nemotron_ultra", "nvidia_nemotron_super"}:
            payload["temperature"] = 1.0
            payload["top_p"] = 0.95

        resp = await client.post(
            f"{model_config.base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=120.0
        )

        if resp.status_code == 200:
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            error_text = (await resp.aread()).decode(errors="replace")
            return f"Error {resp.status_code}: {error_text[:800]}"

    async def _call_gemini(self, message: str, model_config, api_key: str, client: httpx.AsyncClient, history=None) -> str:
        """Call Gemini API"""
        model_name = model_config.api_model

        payload = {
            "systemInstruction": {
                "parts": [{"text": CONVERSATIONAL_SYSTEM_PROMPT}]
            },
            "contents": [
                *[
                    {
                        "role": "model" if turn["role"] == "assistant" else "user",
                        "parts": [{"text": turn["content"]}],
                    }
                    for turn in self._normalized_history(history, message)
                ],
                {"role": "user", "parts": [{"text": message}]}
            ],
            "generationConfig": {
                "maxOutputTokens": model_config.max_tokens,
            }
        }

        resp = await client.post(
            f"{model_config.base_url}/models/{model_name}:generateContent",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            },
            timeout=120.0
        )

        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""
        else:
            error_text = (await resp.aread()).decode(errors="replace")
            return f"Error {resp.status_code}: {error_text[:800]}"

    def get_available_models(self) -> list[dict]:
        """Get list of available models with API keys configured"""
        return [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider.value,
                "task_types": [t.value for t in m.task_types],
                "free_tier": m.free_tier_limit,
                "available": m.provider == ModelProvider.HERMES or m.api_key_env in self.model_router.api_keys
            }
            for m in self.model_router.get_available_models()
        ]
