"""Contratos de Model Router — ADITIVO, não substitui `core/model_router.py`.

IMPORTANTE PARA QUEM LER ISTO DEPOIS: `core/model_router.py` já existe, já é
um Model Router funcional e completo (registro de modelos, seleção
determinística por task_type/policy, health tracking, fallback chain,
diversidade de provedor) — é área do ENGENHEIRO_LATENCIA (ver
`.claude/rules/time-zara.md`). Este módulo NÃO o substitui nem duplica sua
lógica de seleção; ele só formaliza um contrato de "capability" para quem
consome o router (como o Planner) sem precisar conhecer `ModelConfig`/
`TaskType` diretamente, e sem editar `model_router.py`.

O que falta de verdade em `model_router.py` e que este arquivo também define
(mas não implementa: são contratos, não uma segunda implementação) é a
INVOCAÇÃO do modelo escolhido — `model_router.py` só faz seleção
(`get_best_model`/`rank_models`), quem chama a API de fato hoje é código
espalhado fora daqui. `AIProvider.generate()` é o contrato para quando isso
for formalizado — não tem implementação concreta nesta sessão (ver
MODEL_ROUTER_ARCHITECTURE.md, Board 12/19, SKIPPED_REQUIRES_OWNER).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ModelCapability(str, Enum):
    """Subconjunto do que a mission pediu — só o que já é diferenciável a
    partir do TaskType existente em `core.model_router`. Taxonomia enxuta de
    propósito: mais categorias que ninguém usa é dívida, não fundação."""

    TEXT = "TEXT"
    REASONING = "REASONING"
    TOOLS = "TOOLS"
    VOICE = "VOICE"
    LOCAL_PRIVATE = "LOCAL_PRIVATE"


# Mapa explícito capability -> TaskType do model_router.py existente. Mantido
# aqui (não lá) porque é o lado do consumidor que precisa traduzir, não o
# router que precisa saber sobre "capability".
_CAPABILITY_TO_TASK_TYPE = {
    ModelCapability.TEXT: "general_chat",
    ModelCapability.REASONING: "reasoning",
    ModelCapability.TOOLS: "tool_use",
    ModelCapability.VOICE: "voice",
    ModelCapability.LOCAL_PRIVATE: "local_private",
}


@dataclass
class ModelRequest:
    """O que um consumidor (ex.: Planner) pede — capability, nunca provider."""

    capabilities: list[ModelCapability]
    require_tools: bool = False
    policy: str = "smart"  # "smart" | "economy" | "fast" — espelha model_router.py
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """O que a seleção devolve — nunca o texto gerado (isso é invocação, não
    seleção; ver docstring do módulo)."""

    model_id: str | None
    provider: str | None
    accepted: bool
    rejection_reason: str | None = None
    fallback_model_ids: list[str] = field(default_factory=list)


class AIProvider(Protocol):
    """Contrato para quem efetivamente chama a API de um modelo.

    Não implementado nesta sessão — nenhuma classe concreta existe ainda.
    Este Protocol existe só para que, quando a invocação for formalizada, o
    Planner (ou qualquer chamador) dependa desta interface e não de um SDK
    específico. Ver MODEL_PROVIDER_CONTRACT.md.
    """

    def generate(self, model_id: str, prompt: str, **kwargs: Any) -> str:
        ...


def select_model(request: ModelRequest) -> ModelResponse:
    """Traduz um ModelRequest (capability) para uma seleção via o Model
    Router já existente (`core.model_router`), sem duplicar sua lógica.

    Uso pretendido: Planner pede "preciso de REASONING + TOOLS", esta função
    traduz para TaskType e delega a decisão real para
    `core.model_router.router.rank_models` — a fonte de verdade de seleção
    continua sendo um lugar só.
    """
    from core.model_router import TaskType, router

    try:
        task_types = [TaskType(_CAPABILITY_TO_TASK_TYPE[cap]) for cap in request.capabilities]
    except KeyError as exc:
        return ModelResponse(
            model_id=None,
            provider=None,
            accepted=False,
            rejection_reason=f"UNKNOWN_CAPABILITY: {exc}",
        )

    ranked = router.rank_models(
        task_types,
        policy=request.policy,
        require_tools=request.require_tools,
    )
    if not ranked:
        return ModelResponse(
            model_id=None,
            provider=None,
            accepted=False,
            rejection_reason="NO_CANDIDATE: nenhum modelo disponível para essas capabilities",
        )

    primary, *fallback = ranked
    return ModelResponse(
        model_id=primary.id,
        provider=primary.provider.value,
        accepted=True,
        fallback_model_ids=[m.id for m in fallback],
    )
