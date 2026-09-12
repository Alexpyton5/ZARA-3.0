# Arquitetura de Model Router — ZARA 3.0

## Descoberta principal desta sessão

**Um Model Router completo já existe**: `core/model_router.py` (800 linhas,
área do ENGENHEIRO_LATENCIA por `.claude/rules/time-zara.md`). Ele já tem:

| Conceito pedido na missão | Já existe como |
|---|---|
| `ModelDefinition` | `ModelConfig` (dataclass: id, provider, api_model, task_types, capabilities de tools/streaming, bias de smart/economy/speed, custo, prioridade) |
| `ModelRegistry` | `MODEL_REGISTRY: list[ModelConfig]` + `get_model_config(id)` |
| `ModelRouter` | `ModelRouter` (classe): `rank_models`, `get_best_model`, `get_fallback_chain`, `classify_intent` |
| Capability matching | `TaskType` enum + `ModelConfig.task_types` + `_score()` |
| Routing modes | `policy: "smart" \| "economy" \| "fast"` + `normalize_auto_engine()` (auto_fast/auto_smart/auto_economy) |
| Fallback determinístico | `get_fallback_chain()` — diversidade de provedor primeiro, sem loop infinito |
| Health/disponibilidade | `HealthState`, `HealthRecord`, `mark_success`/`mark_failure`, cooldown/exhausted/auth_invalid |
| Privacidade (LOCAL_ONLY) | `TaskType.LOCAL_PRIVATE`, `ModelProvider.HERMES` isolado do AUTO normal |

**Não construímos uma segunda versão disso.** Duplicar seria exatamente o
tipo de coisa que o Board 23 (Red Team) da missão pede para caçar
("ModelRouter duplicando provider logic") — e violaria a regra de "um
escritor por área" do projeto (`core/model_router.py` é do
ENGENHEIRO_LATENCIA, não desta sessão).

## O que esta sessão adicionou (aditivo, arquivo novo)

`core/ai_provider_contracts.py`:

- `ModelCapability` (enum enxuto: TEXT, REASONING, TOOLS, VOICE,
  LOCAL_PRIVATE) — mapeia para os `TaskType` já existentes.
- `ModelRequest`/`ModelResponse` — contrato de entrada/saída para quem
  precisa de "um modelo com tal capability", sem conhecer `ModelConfig`.
- `AIProvider` (Protocol) — contrato para invocação real de modelo
  (`.generate(model_id, prompt, **kwargs)`). **Sem implementação
  concreta** — `model_router.py` hoje só faz seleção, não invocação; quem
  chama a API de fato está espalhado em outros módulos (fora do escopo
  desta sessão tocar).
- `select_model(request)` — traduz capability → `TaskType` e delega para
  `core.model_router.router.rank_models()`. Testado contra o router real
  (não mockado): pediu REASONING+TOOLS, recebeu `nvidia_nemotron_ultra`;
  pediu TEXT com policy economy, recebeu `gemini_36_flash` — reflexo do
  catálogo e chaves configuradas nesta máquina agora, não um número fixo.

## Gemini — preservado, não tocado

`core/gemini_live_voice.py` não foi lido linha a linha nem editado.
`core/model_router.py` já trata Gemini como um provider entre outros
(`ModelProvider.GEMINI`, `gemini_live` com `auto_eligible=False` — a voz ao
vivo já é tratada como caso especial, fora do AUTO normal). Nada nesta
sessão muda esse comportamento.

## O que fica para depois (não implementado)

- `AIProvider` concreto (ex.: `GeminiAdapter`, `GroqAdapter`) que
  efetivamente chame a API via essa interface — hoje a invocação real
  continua onde já estava.
- Rotear o Planner para pedir modelo via `select_model()` em vez de nunca
  precisar de modelo (o `RulePlanner` desta sessão não usa modelo nenhum —
  é 100% determinístico).
- `LLMPlanner`, que usaria `select_model()` para escolher o modelo que vai
  gerar o plano estruturado — Board 19, não feito.
