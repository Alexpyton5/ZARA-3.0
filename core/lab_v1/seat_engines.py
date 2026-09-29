"""Motor padrao de cada assento fixo do Lab — FRENTE 2 (MISSAO LAB VIVO, 28/09/2026).

Todo assento usa IA GRATIS (NVIDIA NIM) por padrao. A escada de fallback de
cada assento termina na Luna via Codex (usa a cota do Alex) — ela so entra
se TODOS os modelos gratis falharem.

Os model_ids abaixo vistos de verdade no catalogo NVIDIA em 28/09/2026
(via discover_models com a chave do Alex): Kimi K3, Nemotron 3 Ultra,
Nemotron 3.5 Lightning, GLM 5.3, Nemotron 3 Nano, DeepSeek V4.1 Flash.

Para trocar o motor de um assento sem mexer em codigo, o dono pode editar
o profile do agente (agent_profiles.py) — este arquivo e so o PADRAO.
"""
from __future__ import annotations

from core.lab_v1.fixed_seats import FIXED_SEATS
from core.lab_v1.providers.fallback import LadderRung

NVIDIA = "nvidia"
CODEX_CLI = "codex_cli"
FREELLMAPI = "freellmapi"
OLLAMA = "ollama"

# Modelo gratis padrao de cada assento (provedor, model_id).
SEAT_MODELS: dict[str, tuple[str, str]] = {
    "CEO":         (NVIDIA, "nvidia/nemotron-3-ultra-550b-a55b"),
    "ARCHITECT":   (NVIDIA, "moonshotai/kimi-k3"),
    "UI_DESIGNER": (NVIDIA, "z-ai/glm-5.3"),
    "ENGINEER":    (NVIDIA, "moonshotai/kimi-k3"),
    "SCRIBE":      (NVIDIA, "nvidia/nemotron-3.5-lightning-30b-a3b"),
    "REVIEWER":    (NVIDIA, "nvidia/nemotron-3-super-120b-a12b"),
    "CRITIC":      (NVIDIA, "nvidia/nemotron-3-super-120b-a12b"),
    "SECRETARY":   (NVIDIA, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"),
    "TESTER":      (NVIDIA, "deepseek-ai/deepseek-v4.1-flash"),
    "RESEARCHER":  (NVIDIA, "moonshotai/kimi-k3"),
    "PACKAGER":    (NVIDIA, "nvidia/nemotron-3.5-lightning-30b-a3b"),
}

# Degrau gratis barato usado como rede de seguranca antes da Luna.
_CHEAP_FALLBACK: tuple[str, str] = (NVIDIA, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")

# Ultimo recurso: Luna via Codex (cota paga do Alex). So entra se o gratis
# falhar — nunca e o padrao.
_PAID_LAST_RESORT: tuple[str, str] = (CODEX_CLI, "gpt-5.6-luna")

# Agregador local de planos gratuitos (FASE 2 peca 5, 28/09/2026): "auto"
# resolve para o primeiro modelo com chave colada no dashboard do Alex.
# Sem conta configurada o degrau e pulado pelo probe honesto — nunca finge.
_FREELLMAPI_AUTO: tuple[str, str] = (FREELLMAPI, "auto")

# Degrau local gratis/offline (infra do coordenador, 28/09/2026): Ollama com
# qwen3:8b instalado no PC do Alex. Entra DEPOIS do agregador remoto e ANTES
# da Luna: e o ultimo recurso gratis antes de gastar a cota paga do Alex.
# Sem o servidor Ollama no ar o degrau e pulado pelo probe honesto — nunca
# finge.
_OLLAMA_LOCAL: tuple[str, str] = (OLLAMA, "qwen3:8b")


def _role_value(role: object) -> str:
    return role.value if hasattr(role, "value") else str(role)


def engine_for(role: object) -> tuple[str, str]:
    """(provedor, modelo) padrao do assento. Desconhecido -> gratis barato."""
    return SEAT_MODELS.get(_role_value(role), _CHEAP_FALLBACK)


def default_ladder_for(role: object) -> list[LadderRung]:
    """Escada padrao do assento: modelo do assento -> gratis barato ->
    agregador local gratis (FreeLLMAPI) -> Ollama local (qwen3:8b) -> Luna.

    A ordem e gratis primeiro, pago por ultimo. Sem duplicados.
    """
    rungs = [LadderRung(*engine_for(role)), LadderRung(*_CHEAP_FALLBACK),
             LadderRung(*_FREELLMAPI_AUTO), LadderRung(*_OLLAMA_LOCAL),
             LadderRung(*_PAID_LAST_RESORT)]
    seen: set[tuple[str, str]] = set()
    unique: list[LadderRung] = []
    for rung in rungs:
        key = (rung.provider_id, rung.model)
        if key not in seen:
            seen.add(key)
            unique.append(rung)
    return unique


def seat_report() -> list[dict[str, str]]:
    """Tabela assento -> motor, para exibir na UI ou no relatorio."""
    return [
        {
            "seat": _role_value(role),
            "provider": engine_for(role)[0],
            "model": engine_for(role)[1],
            "ladder": " -> ".join(f"{r.provider_id}/{r.model.split('/')[-1]}"
                                  for r in default_ladder_for(role)),
        }
        for role in FIXED_SEATS
    ]
