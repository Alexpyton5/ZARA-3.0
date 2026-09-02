"""
ZARA Smart Router 001
- AUTO • INTELIGENTE: quality/task-fit first, zero-cost eligible only.
- AUTO • ECONÔMICO: fast/light/free-quota preserving first.
- MANUAL: explicit model choice is respected; no silent fallback.
- Provider/model health: auth, rate-limit, quota and transient failures.
- Hermes is NEVER part of normal AUTO; Supercérebro remains explicit.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.paths import user_data_dir


class ModelProvider(StrEnum):
    GROQ = "groq"
    NVIDIA = "nvidia"
    GEMINI = "gemini"
    ZAI = "zai"
    XAI = "xai"
    HERMES = "hermes"
    OLLAMA = "ollama"


class TaskType(StrEnum):
    CODING = "coding"
    REASONING = "reasoning"
    GENERAL_CHAT = "general_chat"
    CREATIVE = "creative"
    QUICK_FACTS = "quick_facts"
    VOICE = "voice"
    LOCAL_PRIVATE = "local_private"
    TOOL_USE = "tool_use"


class HealthState(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    COOLDOWN = "COOLDOWN"
    EXHAUSTED = "EXHAUSTED"
    AUTH_INVALID = "AUTH_INVALID"
    ERROR = "ERROR"


@dataclass
class HealthRecord:
    state: HealthState = HealthState.AVAILABLE
    until: float = 0.0
    last_status: int | None = None
    last_error: str = ""
    failures: int = 0
    updated_at: float = 0.0


@dataclass
class ModelConfig:
    id: str
    name: str
    provider: ModelProvider
    api_model: str
    task_types: list[TaskType]
    api_key_env: str
    base_url: str
    max_tokens: int
    free_tier_limit: str
    priority: int
    smart_bias: int = 0
    economy_bias: int = 0
    # ZARA-VELOCIDADE-001 (Alex, 2026-08-28 noite): "qualquer coisa que ela
    # ouvir, tem que responder no menor tempo possivel". Escala de bias
    # igual a smart_bias/economy_bias, so que pra latencia -- usado quando
    # policy="fast" no _score(). Valores INFERIDOS de caracteristica publica
    # de infraestrutura de cada provedor (Groq = LPU, documentado como o
    # mais rapido; Gemini Flash/Flash-Lite = otimizado pra latencia pelo
    # proprio Google; Nemotron grande via NIM = MEDIDO lento em outro
    # contexto hoje, 2-16s) -- NAO e medicao real desta app ainda. Ver
    # skill medir-latencia-da-zara antes de declarar "ficou mais rapido".
    speed_bias: int = 0
    supports_streaming: bool = True
    supports_tools: bool = False
    auto_eligible: bool = True
    zero_cost_eligible: bool = True


MODEL_REGISTRY: list[ModelConfig] = [
    # Ollama — Local models with no API key needed
    ModelConfig(
        id="ollama_qwen3_8b",
        name="Ollama qwen3:8b",
        provider=ModelProvider.OLLAMA,
        api_model="qwen3:8b",
        task_types=[TaskType.REASONING, TaskType.CODING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT],
        api_key_env="OLLAMA_API_KEY",
        base_url="http://127.0.0.1:11434",
        max_tokens=16384,
        free_tier_limit="Ollama • Local unlimited",
        priority=1,
        smart_bias=30,
        economy_bias=30,
        speed_bias=12,
        supports_tools=True,
        zero_cost_eligible=True,
    ),
    ModelConfig(
        id="ollama_qwen3_4b",
        name="Ollama qwen3:4b",
        provider=ModelProvider.OLLAMA,
        api_model="qwen3:4b",
        task_types=[TaskType.REASONING, TaskType.CODING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT],
        api_key_env="OLLAMA_API_KEY",
        base_url="http://127.0.0.1:11434",
        max_tokens=16384,
        free_tier_limit="Ollama • Local unlimited",
        priority=2,
        smart_bias=25,
        economy_bias=25,
        speed_bias=16,
        supports_tools=True,
        zero_cost_eligible=True,
    ),
    # NVIDIA NIM — free prototype endpoints / trial limits apply.
    ModelConfig(
        id="nvidia_nemotron_ultra",
        name="Nemotron 3 Ultra 550B (NVIDIA)",
        provider=ModelProvider.NVIDIA,
        api_model="nvidia/nemotron-3-ultra-550b-a55b",
        task_types=[TaskType.REASONING, TaskType.CODING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT],
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        max_tokens=16384,
        free_tier_limit="NVIDIA NIM • Free endpoint/trial limits",
        priority=1,
        smart_bias=22,
        economy_bias=1,
        speed_bias=2,
        supports_tools=True,
    ),
    ModelConfig(
        id="nvidia_deepseek_v4_pro",
        name="DeepSeek V4 Pro (NVIDIA NIM)",
        provider=ModelProvider.NVIDIA,
        api_model="deepseek-ai/deepseek-v4-pro",
        task_types=[TaskType.CODING, TaskType.REASONING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT],
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        max_tokens=16384,
        free_tier_limit="NVIDIA NIM • Free endpoint/trial limits",
        priority=1,
        smart_bias=20,
        economy_bias=2,
        speed_bias=3,
        supports_tools=True,
    ),
    ModelConfig(
        id="nvidia_nemotron_super",
        name="Nemotron 3 Super 120B (NVIDIA)",
        provider=ModelProvider.NVIDIA,
        api_model="nvidia/nemotron-3-super-120b-a12b",
        task_types=[TaskType.TOOL_USE, TaskType.REASONING, TaskType.CODING, TaskType.GENERAL_CHAT],
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        max_tokens=16384,
        free_tier_limit="NVIDIA NIM • Free endpoint/trial limits",
        priority=2,
        smart_bias=15,
        economy_bias=6,
        speed_bias=4,
        supports_tools=True,
    ),
    ModelConfig(
        id="nvidia_glm52",
        name="GLM-5.2 (NVIDIA NIM)",
        provider=ModelProvider.NVIDIA,
        api_model="z-ai/glm-5.2",
        task_types=[TaskType.CODING, TaskType.REASONING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT, TaskType.CREATIVE],
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        max_tokens=16384,
        free_tier_limit="NVIDIA NIM • Free endpoint/trial limits",
        priority=2,
        smart_bias=16,
        economy_bias=3,
        speed_bias=6,
        supports_tools=True,
    ),

    # Groq — Free plan has explicit rate limits. Avoid models scheduled for shutdown.
    ModelConfig(
        id="groq_gpt_oss_120b",
        name="GPT-OSS 120B (Groq)",
        provider=ModelProvider.GROQ,
        api_model="openai/gpt-oss-120b",
        task_types=[TaskType.CODING, TaskType.REASONING, TaskType.TOOL_USE, TaskType.GENERAL_CHAT],
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        max_tokens=16384,
        free_tier_limit="Groq • Free plan limits",
        priority=1,
        smart_bias=18,
        economy_bias=10,
        speed_bias=26,
        supports_tools=True,
    ),
    ModelConfig(
        id="groq_gpt_oss_20b",
        name="GPT-OSS 20B (Groq)",
        provider=ModelProvider.GROQ,
        api_model="openai/gpt-oss-20b",
        task_types=[TaskType.QUICK_FACTS, TaskType.GENERAL_CHAT, TaskType.TOOL_USE, TaskType.CODING, TaskType.REASONING],
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        max_tokens=8192,
        free_tier_limit="Groq • Free plan limits",
        priority=2,
        smart_bias=10,
        economy_bias=24,
        speed_bias=30,
        supports_tools=True,
    ),

    # Gemini — current stable free-tier candidates.
    ModelConfig(
        id="gemini_36_flash",
        name="Gemini 3.6 Flash",
        provider=ModelProvider.GEMINI,
        api_model="gemini-3.6-flash",
        task_types=[TaskType.GENERAL_CHAT, TaskType.CODING, TaskType.REASONING, TaskType.CREATIVE, TaskType.TOOL_USE, TaskType.QUICK_FACTS],
        api_key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        max_tokens=16384,
        free_tier_limit="Gemini • Free tier limits",
        priority=1,
        smart_bias=21,
        economy_bias=13,
        speed_bias=20,
        supports_tools=True,
    ),
    ModelConfig(
        id="gemini_35_flash_lite",
        name="Gemini 3.5 Flash-Lite",
        provider=ModelProvider.GEMINI,
        api_model="gemini-3.5-flash-lite",
        task_types=[TaskType.QUICK_FACTS, TaskType.GENERAL_CHAT, TaskType.TOOL_USE, TaskType.CREATIVE, TaskType.CODING],
        api_key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        max_tokens=8192,
        free_tier_limit="Gemini • Free tier limits",
        priority=2,
        smart_bias=10,
        economy_bias=27,
        speed_bias=24,
        supports_tools=True,
    ),
    ModelConfig(
        id="gemini_25_pro",
        name="Gemini 2.5 Pro",
        provider=ModelProvider.GEMINI,
        api_model="gemini-2.5-pro",
        task_types=[TaskType.REASONING, TaskType.CODING, TaskType.GENERAL_CHAT],
        api_key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        max_tokens=16384,
        free_tier_limit="Gemini • Free tier limits",
        priority=2,
        smart_bias=17,
        economy_bias=1,
        speed_bias=5,
        supports_tools=True,
    ),
    ModelConfig(
        id="gemini_25_flash",
        name="Gemini 2.5 Flash",
        provider=ModelProvider.GEMINI,
        api_model="gemini-2.5-flash",
        task_types=[TaskType.GENERAL_CHAT, TaskType.QUICK_FACTS, TaskType.CREATIVE, TaskType.CODING],
        api_key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        max_tokens=8192,
        free_tier_limit="Gemini • Free tier limits",
        priority=3,
        smart_bias=8,
        economy_bias=18,
        speed_bias=18,
        supports_tools=True,
    ),

    # Optional Z.AI direct adapter. No key today; remains dormant.
    ModelConfig(
        id="zai_glm47_flash",
        name="Z.AI GLM-4.7 Flash",
        provider=ModelProvider.ZAI,
        api_model="glm-4.7-flash",
        task_types=[TaskType.CREATIVE, TaskType.GENERAL_CHAT, TaskType.CODING],
        api_key_env="ZAI_API_KEY",
        base_url="https://api.z.ai/api/paas/v4",
        max_tokens=16384,
        free_tier_limit="Provider limits apply",
        priority=4,
        smart_bias=5,
        economy_bias=7,
        speed_bias=15,
        supports_tools=True,
    ),

    # Paid provider: manual-only by zero-cost policy.
    ModelConfig(
        id="xai_grok45",
        name="Grok 4.5 (xAI)",
        provider=ModelProvider.XAI,
        api_model="grok-4.5",
        task_types=[TaskType.CODING, TaskType.REASONING, TaskType.GENERAL_CHAT, TaskType.CREATIVE],
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        max_tokens=16384,
        free_tier_limit="PAID • never AUTO under R$0 policy",
        priority=9,
        smart_bias=0,
        economy_bias=0,
        speed_bias=8,
        supports_tools=True,
        auto_eligible=False,
        zero_cost_eligible=False,
    ),

    # Voice transport: not a normal text engine.
    ModelConfig(
        id="gemini_live",
        name="Gemini 3.1 Flash Live • Kore",
        provider=ModelProvider.GEMINI,
        api_model="gemini-3.1-flash-live-preview",
        task_types=[TaskType.VOICE],
        api_key_env="GEMINI_API_KEY",
        base_url="wss://generativelanguage.googleapis.com/v1beta",
        max_tokens=8192,
        free_tier_limit="Gemini Live limits apply",
        priority=1,
        supports_streaming=True,
        supports_tools=True,
        auto_eligible=False,
    ),

    # Explicit Supercérebro path only.
    ModelConfig(
        id="hermes_gateway",
        name="Hermes Gateway (Supercérebro)",
        provider=ModelProvider.HERMES,
        api_model="hermes_gateway",
        task_types=[TaskType.LOCAL_PRIVATE, TaskType.TOOL_USE, TaskType.CODING, TaskType.REASONING],
        api_key_env="HERMES_API_KEY",
        base_url="http://127.0.0.1:8642/v1",
        max_tokens=32768,
        free_tier_limit="Local",
        priority=1,
        supports_streaming=True,
        supports_tools=True,
        auto_eligible=False,
    ),
]


INTENT_PATTERNS = {
    TaskType.CODING: [
        r"\b(código|code|programa|function|class|debug|erro|bug|api|endpoint|database|sql|python|javascript|typescript|react|vue|docker|kubernetes)\b",
        r"\b(como fazer|how to|implementar|criar|escrever|refatorar|otimizar|testar)\b.*\b(código|função|script|app|aplicação)\b",
    ],
    TaskType.REASONING: [
        r"\b(analisar|analyze|raciocinar|reason|logic|lógica|prova|proof|deduzir|deduce|inferir|infer)\b",
        r"\b(por que|why|explique|explain|justifique|justify|compare|comparar|avalie|evaluate)\b",
        r"\b(problema|problem|complexo|complex|difícil|hard|desafio|challenge)\b",
    ],
    TaskType.CREATIVE: [
        r"\b(escreva|write|criar|create|invente|invent|história|story|poema|poem|roteiro|script|letra|lyrics)\b",
        r"\b(criativo|creative|imaginativo|imaginative|ficção|fiction|conto|tale|romance|novel)\b",
    ],
    TaskType.QUICK_FACTS: [
        r"\b(qual|what|quem|who|quando|when|onde|where|quanto|how much|definição|definition)\b",
        r"\b(fato|fact|dado|data|estatística|statistic|número|number|população|population)\b",
        r"\b(resumo|summary|resuma|summarize|tl;dr|tldr)\b",
    ],
    TaskType.VOICE: [
        r"\b(fale|speak|diga|say|voz|voice|áudio|audio|ouça|listen|pronuncie|pronounce)\b",
    ],
    TaskType.LOCAL_PRIVATE: [
        r"\b(privado|private|local|offline|seguro|secure|sem internet|no internet|confidencial|confidential)\b",
        r"\b(meus dados|my data|pessoal|personal|sensível|sensitive)\b",
    ],
    TaskType.TOOL_USE: [
        r"\b(execute|run|rode|faça|do|action|ação|comando|command|terminal|shell|arquivo|file|web|browser)\b",
        r"\b(abra|open|feche|close|clique|click|digite|type|pesquise|search|baixe|download)\b",
    ],
}


class ModelRouter:
    """Zero-cost-first model router with runtime health awareness."""

    def __init__(self):
        self.api_keys: dict[str, str] = {}
        self.usage_stats: dict[str, dict[str, Any]] = {}
        self.provider_health: dict[str, HealthRecord] = {}
        self.model_health: dict[str, HealthRecord] = {}
        self.catalog_snapshot: dict[str, Any] = {}
        self._load_api_keys()
        self._load_usage_stats()
        self._load_catalog_snapshot()

    def _load_api_keys(self) -> None:
        from core.paths import config_dir

        config_file = config_dir() / "api_keys.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                key_map = {
                    "groq_api_key": "GROQ_API_KEY",
                    "gemini_api_key": "GEMINI_API_KEY",
                    "nvidia_api_key": "NVIDIA_API_KEY",
                    "zai_api_key": "ZAI_API_KEY",
                    "xai_api_key": "XAI_API_KEY",
                    "hermes_api_key": "HERMES_API_KEY",
                }
                for config_key, env_key in key_map.items():
                    value = str(config.get(config_key) or "").strip()
                    if value:
                        self.api_keys[env_key] = value
                        os.environ[env_key] = value
            except Exception:
                pass

        for model in MODEL_REGISTRY:
            value = str(os.environ.get(model.api_key_env) or "").strip()
            if value:
                self.api_keys[model.api_key_env] = value

    def _load_usage_stats(self) -> None:
        path = user_data_dir() / "model_usage_stats.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.usage_stats = data if isinstance(data, dict) else {}
            except Exception:
                self.usage_stats = {}

    def _save_usage_stats(self) -> None:
        path = user_data_dir() / "model_usage_stats.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.usage_stats, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_catalog_snapshot(self) -> None:
        path = user_data_dir() / "model_catalog_snapshot.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.catalog_snapshot = data
        except Exception:
            self.catalog_snapshot = {}

    def refresh_catalog_snapshot(self) -> None:
        self.catalog_snapshot = {}
        self._load_catalog_snapshot()

    def _catalog_allows(self, model: ModelConfig) -> bool:
        if model.provider in {ModelProvider.HERMES, ModelProvider.XAI}:
            return True
        providers = self.catalog_snapshot.get("providers")
        if not isinstance(providers, dict):
            return True
        models = providers.get(model.provider.value)
        if not isinstance(models, list) or not models:
            return True
        return model.api_model in {str(item) for item in models}

    def classify_intent(self, message: str, context: dict | None = None) -> list[TaskType]:
        message_lower = message.lower()
        detected: list[TaskType] = []
        for task_type, patterns in INTENT_PATTERNS.items():
            if any(re.search(pattern, message_lower, re.IGNORECASE) for pattern in patterns):
                detected.append(task_type)
        if not detected:
            detected = [TaskType.GENERAL_CHAT]
        if context:
            if context.get("voice_mode"):
                detected.insert(0, TaskType.VOICE)
            if context.get("require_tools"):
                detected.insert(0, TaskType.TOOL_USE)
            if context.get("private_mode"):
                detected.insert(0, TaskType.LOCAL_PRIVATE)
        return detected

    def _record(self, mapping: dict[str, HealthRecord], key: str) -> HealthRecord:
        if key not in mapping:
            mapping[key] = HealthRecord()
        return mapping[key]

    def _effective_record(self, model: ModelConfig) -> HealthRecord:
        now = time.time()
        provider = self._record(self.provider_health, model.provider.value)
        item = self._record(self.model_health, model.id)
        for record in (provider, item):
            if record.state in {HealthState.COOLDOWN, HealthState.ERROR, HealthState.EXHAUSTED} and record.until and now >= record.until:
                record.state = HealthState.AVAILABLE
                record.until = 0.0
                record.last_error = ""
        blocking = {
            HealthState.AUTH_INVALID: 6,
            HealthState.EXHAUSTED: 5,
            HealthState.COOLDOWN: 4,
            HealthState.ERROR: 3,
            HealthState.LIMITED: 2,
            HealthState.AVAILABLE: 1,
        }
        return provider if blocking[provider.state] >= blocking[item.state] else item

    def health_for(self, model_id: str) -> dict[str, Any]:
        model = get_model_config(model_id)
        if not model:
            return {"state": HealthState.ERROR.value}
        r = self._effective_record(model)
        return {
            "state": r.state.value,
            "until": r.until,
            "last_status": r.last_status,
            "failures": r.failures,
        }

    def mark_success(self, model_id: str) -> None:
        model = get_model_config(model_id)
        if not model:
            return
        now = time.time()
        for mapping, key in ((self.provider_health, model.provider.value), (self.model_health, model.id)):
            r = self._record(mapping, key)
            r.state = HealthState.AVAILABLE
            r.until = 0.0
            r.last_status = 200
            r.last_error = ""
            r.updated_at = now

    def mark_failure(self, model_id: str, error: str) -> None:
        model = get_model_config(model_id)
        if not model:
            return
        text = str(error or "")
        lower = text.lower()
        match = re.search(r"\b(?:error\s*)?(\d{3})\b", lower)
        status = int(match.group(1)) if match else None
        now = time.time()

        if status in {401, 403} or "invalid_api_key" in lower or "unauthorized" in lower:
            r = self._record(self.provider_health, model.provider.value)
            r.state = HealthState.AUTH_INVALID
            r.until = 0.0  # requires config reload / successful call
        elif status == 429 or "rate limit" in lower or "too many requests" in lower:
            r = self._record(self.provider_health, model.provider.value)
            r.state = HealthState.COOLDOWN
            r.until = now + 75.0
        elif status == 402 or "insufficient_quota" in lower or "quota exhausted" in lower or "billing" in lower:
            r = self._record(self.provider_health, model.provider.value)
            r.state = HealthState.EXHAUSTED
            r.until = now + 900.0
        elif status == 404 or "model not found" in lower:
            r = self._record(self.model_health, model.id)
            r.state = HealthState.ERROR
            r.until = now + 1800.0
        else:
            r = self._record(self.model_health, model.id)
            r.state = HealthState.ERROR
            r.until = now + 30.0

        r.last_status = status
        r.failures += 1
        r.last_error = text[:500]
        r.updated_at = now

    def _routable(self, model: ModelConfig, include_paid: bool = False, include_hermes: bool = False) -> bool:
        if model.provider == ModelProvider.HERMES:
            return include_hermes
        if not model.auto_eligible:
            return False
        if not include_paid and not model.zero_cost_eligible:
            return False
        if model.api_key_env not in self.api_keys:
            return False
        if not self._catalog_allows(model):
            return False
        state = self._effective_record(model).state
        return state in {HealthState.AVAILABLE, HealthState.LIMITED}

    def _score(self, model: ModelConfig, task_types: list[TaskType], policy: str) -> int:
        score = 0
        for request_index, task_type in enumerate(task_types):
            if task_type in model.task_types:
                model_index = model.task_types.index(task_type)
                score += 120 - (request_index * 8) - (model_index * 14)
        if score <= 0:
            return -10_000
        score -= model.priority * 3
        if policy == "economy":
            score += model.economy_bias
        elif policy == "fast":
            score += model.speed_bias
        else:
            score += model.smart_bias
        return score

    def rank_models(
        self,
        task_types: list[TaskType],
        policy: str = "smart",
        require_tools: bool = False,
        require_streaming: bool = True,
        include_hermes: bool = False,
    ) -> list[ModelConfig]:
        ranked: list[tuple[int, ModelConfig]] = []
        for model in MODEL_REGISTRY:
            if not self._routable(model, include_paid=False, include_hermes=include_hermes):
                continue
            if require_tools and not model.supports_tools:
                continue
            if require_streaming and not model.supports_streaming:
                continue
            score = self._score(model, task_types, policy)
            if score > -10_000:
                ranked.append((score, model))
        ranked.sort(key=lambda item: (item[0], -item[1].priority), reverse=True)
        if not ranked:
            return []

        # Provider diversity first in fallback, so a provider-wide incident does not
        # cause several guaranteed failures before trying another provider.
        primary = ranked[0][1]
        other_provider = [m for _, m in ranked[1:] if m.provider != primary.provider]
        same_provider = [m for _, m in ranked[1:] if m.provider == primary.provider]
        return [primary, *other_provider, *same_provider]

    def get_best_model(
        self,
        task_types: list[TaskType],
        require_tools: bool = False,
        require_streaming: bool = True,
        include_hermes: bool = False,
        policy: str = "smart",
    ) -> ModelConfig | None:
        ranked = self.rank_models(task_types, policy, require_tools, require_streaming, include_hermes)
        return ranked[0] if ranked else None

    def get_fallback_chain(
        self,
        task_types: list[TaskType],
        require_tools: bool = False,
        include_hermes: bool = False,
        policy: str = "smart",
    ) -> list[ModelConfig]:
        ranked = self.rank_models(task_types, policy, require_tools, True, include_hermes)
        return ranked[1:] if len(ranked) > 1 else []

    def record_usage(self, model_id: str, tokens: int = 0, success: bool = True) -> None:
        item = self.usage_stats.setdefault(model_id, {"requests": 0, "tokens": 0, "errors": 0})
        item["requests"] = int(item.get("requests", 0)) + 1
        item["tokens"] = int(item.get("tokens", 0)) + max(0, int(tokens or 0))
        if not success:
            item["errors"] = int(item.get("errors", 0)) + 1
        self._save_usage_stats()

    def get_available_models(self, include_hermes: bool = True, include_paid: bool = False) -> list[ModelConfig]:
        available: list[ModelConfig] = []
        for model in MODEL_REGISTRY:
            if model.id == "gemini_live":
                continue
            if model.provider == ModelProvider.HERMES:
                if not include_hermes:
                    continue
                import urllib.request
                try:
                    with urllib.request.urlopen(model.base_url.replace("/v1", "/health"), timeout=2) as resp:
                        if resp.status == 200:
                            available.append(model)
                except Exception:
                    pass
                continue
            if not include_paid and not model.zero_cost_eligible:
                continue
            if model.api_key_env not in self.api_keys:
                continue
            if not self._catalog_allows(model):
                continue
            if self._effective_record(model).state in {HealthState.AVAILABLE, HealthState.LIMITED}:
                available.append(model)
        return available

    def configured_model_status(self, include_paid: bool = False) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for model in MODEL_REGISTRY:
            if model.provider == ModelProvider.HERMES or model.id == "gemini_live":
                continue
            if not include_paid and not model.zero_cost_eligible:
                continue
            if model.api_key_env not in self.api_keys:
                continue
            if not self._catalog_allows(model):
                continue
            rows.append({
                "id": model.id,
                "name": model.name,
                "provider": model.provider.value,
                "api_model": model.api_model,
                "free_tier": model.free_tier_limit,
                "health": self.health_for(model.id),
            })
        return rows


router = ModelRouter()


def normalize_auto_engine(engine: str | None) -> str:
    raw = str(engine or "").strip().lower()
    if raw in {"", "auto", "auto_router", "auto_fast"}:
        # ZARA-VELOCIDADE-001: "auto_fast" é o padrão agora -- resposta por
        # voz tem que ser rápida por padrão, sem precisar pedir. "auto"/""
        # (o que já existia antes) também cai aqui, não em auto_smart, pra
        # não regredir quem já tinha o engine salvo como vazio/"auto".
        return "auto_fast"
    if raw == "auto_smart":
        return "auto_smart"
    if raw == "auto_economy":
        return "auto_economy"
    return raw


def route_message(
    message: str,
    context: dict | None = None,
    require_tools: bool = False,
    require_streaming: bool = True,
    include_hermes: bool = False,
    policy: str = "smart",
) -> tuple[ModelConfig | None, list[ModelConfig]]:
    task_types = router.classify_intent(message, context)
    ranked = router.rank_models(
        task_types,
        policy=policy,
        require_tools=require_tools,
        require_streaming=require_streaming,
        include_hermes=include_hermes,
    )
    return (ranked[0], ranked[1:]) if ranked else (None, [])


def get_model_config(model_id: str) -> ModelConfig | None:
    for model in MODEL_REGISTRY:
        if model.id == model_id:
            return model
    return None


































