# Mapa de integração do Planner — ZARA 3.0

Objetivo prático, não auditoria completa: onde o Planner se encaixa no que
já existe, sem reescrever nada disso.

## Cadeia atual (voz e texto), sem Planner

```
entrada (voz via core/voice_stt.py -> core/ipc_handlers.py::_process_voice_message
         texto via core/ipc_handlers.py::handle_send_message)
  -> _try_jarvis_multi_action / _try_pc_intent / ... (core/pc_voice_intent.py)
  -> core/action_registry.py (ActionRegistry.execute)
  -> função @action em core/actions/*.py
  -> resposta falada via core/voice_tts.py
```

Isso continua existindo, inalterado. O Planner não substitui esse caminho —
é um caminho PARALELO para quando o pedido não cabe num único intent
determinístico.

## Onde o Planner se conecta

- `core/tool_router.py` já existe e é o alvo de execução do Planner
  (`ToolRouter.route(ToolRequest(...))`) — mesmo caminho que
  `core/tool_registry.py`/`ExecutionWrapper`/`ToolVerifier` já usam.
- `core/action_registry.py` continua sendo a fonte de tools conhecidas via o
  adapter em `core/tool_registry.py::adapt_from_action_registry` — o Planner
  não precisa de uma segunda fonte de "quais tools existem".
- `core/model_router.py` **já é** um Model Router completo (registro,
  seleção, health, fallback) — ver `MODEL_ROUTER_ARCHITECTURE.md`. O Planner
  não fala com ele diretamente; fala com `core/ai_provider_contracts.py`
  (camada aditiva desta sessão) por capability.
- `core/gemini_live_voice.py` **não foi tocado** — é o caminho de voz ao
  vivo, fora do escopo desta missão (ver Board 12: SKIPPED_REQUIRES_OWNER
  para qualquer integração que precisasse mexer nele).
- `core/intent_classifier.py`/`core/autonomy_engine.py` foram lidos, não
  alterados — são candidatos naturais para, no futuro, alimentar
  `PlannerRequest.explicit_steps` quando uma saída de modelo for
  formalizada (Board 19, não feito nesta sessão).

## Duplicação encontrada e evitada

`core/model_router.py` já resolve quase tudo que a missão pedia para
"Model Router contracts" (Boards 10, 11, 13, 14, 15, 16, 17). Construir uma
segunda implementação teria sido exatamente o tipo de "ModelRouter
duplicando provider logic" que o próprio Board 23 (Red Team) pede para
caçar. Em vez disso, `core/ai_provider_contracts.py` é uma casca fina por
cima do que já existe — ver `MODEL_ROUTER_ARCHITECTURE.md`.

## O que NÃO foi mapeado a fundo (fora do necessário para este board)

`core/gemini_live_voice.py`, `core/ipc_handlers.py` (2700 linhas) e
`core/autonomy_engine.py` foram identificados como pontos de integração
futuros, não lidos linha a linha — não era necessário para decidir onde o
Planner se encaixa sem quebrar nada.
