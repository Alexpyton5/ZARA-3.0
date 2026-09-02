# Arquitetura do Planner — ZARA 3.0

Código em `core/planner/`. Este documento descreve o que existe de verdade
(commit `d43c02f` e seguintes), não uma visão aspiracional.

## Princípio central

```
PlannerRequest -> Planner.plan() -> PlannerResponse (Plan | rejeição)
Plan validado -> execute_plan() -> ToolRouter.route() -> PlanResult
```

O Planner **nunca executa**. `Planner.plan()` é puro: não chama rede,
hardware, subprocess ou `ToolRouter`. A única função que fala com
`ToolRouter` é `core.planner.execution.execute_plan`.

## Domínio (`core/planner/models.py`)

- `Plan`: `id`, `goal`, `steps`, `status` (`PlanStatus`), `created_at`,
  `metadata`.
- `PlanStep`: `id`, `tool_name`, `arguments`, `description`, `depends_on`,
  `status` (`StepStatus`), `risk_hint`, `requires_verification`, `result`,
  `error`, `metadata`.
- `PlanStatus`: CREATED → VALIDATED → RUNNING → {COMPLETED, PARTIAL, FAILED,
  CANCELLED, BLOCKED}.
- `StepStatus`: PENDING → READY → RUNNING → {VERIFIED, FAILED, SKIPPED,
  CANCELLED, BLOCKED}. (`READY` existe no enum para uso futuro de um
  scheduler mais fino — `execute_plan` hoje vai direto de PENDING para
  RUNNING via ordem topológica, não usa READY como estado intermediário
  ainda.)
- `PlanResult`, `PlanningContext`, `PlannerRequest`, `PlannerResponse`.

## Validação (`core/planner/validation.py`)

`validate_plan(plan, known_tool_names, blocked_tool_names)` — determinística,
sem IA. Detecta: plano vazio, id duplicado, tool desconhecida, tool
bloqueada, argumento que não é dict, dependência inexistente,
auto-dependência, e ciclo de dependência (DFS branco/cinza/preto). Levanta
`PlanValidationError` com **todos** os motivos encontrados, não só o
primeiro.

`topological_order(plan)` — ordem de execução respeitando dependências.
Assume plano já validado (sem ciclo); não valida de novo.

## Planner (`core/planner/planner.py`)

- `Planner` — interface abstrata.
- `RulePlanner` — única implementação desta fase. Regra KISS: exige
  `PlannerRequest.explicit_steps` (não inventa passos a partir de linguagem
  natural). Valida e retorna `PlannerResponse(accepted=False, ...)` se algo
  estiver errado, nunca aceita um plano inválido silenciosamente.
- `LLMPlanner`/`HybridPlanner` — **não implementados**. Ver Board 19 do
  `NIGHT_MISSION_04` no `NIGHT_MISSION_04_FINAL_REPORT.md`.

### Por que "fast path" não tem uma classe própria ainda

A missão pediu um "fast path" para comandos simples não passarem por Planner
pesado. Isso já existe fisicamente: o caminho de intent determinístico em
`core/pc_voice_intent.py`/`core/action_registry.py` **continua sendo o
padrão** para comandos simples — o Planner só entra quando alguém decide
explicitamente montar um `PlannerRequest`. Não foi necessário criar um
"decisor" adicional porque o próprio ponto de entrada (quem cria o
`PlannerRequest`) já é essa decisão. Formalizar isso como uma função de
decisão automática fica para quando houver um consumidor real do Planner.

## Execução (`core/planner/execution.py`)

`execute_plan(plan, tool_router=None)`:

1. Recusa rodar um plano que não esteja `VALIDATED`/`RUNNING`/`PARTIAL`.
2. Ordena steps topologicamente.
3. Para cada step: se alguma dependência falhou (está em `blocked_ids`),
   marca o step como `BLOCKED` e pula — nunca despacha.
4. Caso contrário, despacha via
   `tool_router.route(ToolRequest(tool_name=..., parameters=...))`.
5. Sucesso → `VERIFIED`; falha → `FAILED`, e o id entra em `blocked_ids`
   para propagar aos dependentes.
6. `Plan.status` final: `COMPLETED` (tudo ok), `FAILED` (nada completou),
   `PARTIAL` (mistura de sucesso/falha/bloqueio).

`tool_router` é injetável — em produção, `core.tool_router.get_tool_router()`;
em teste, qualquer objeto com `.route(request) -> resultado com .success`.

## Garantias de segurança (verificadas por teste, não só descritas)

- `test_planner_never_calls_tool_router_itself` — um `RulePlanner` que
  rejeita um plano nunca deixa nada chegar a um router (real ou fake).
- `test_unvalidated_plan_refuses_to_run` — `execute_plan` recusa um `Plan`
  que não passou por `validate_plan` primeiro (status ainda `CREATED`).
- `test_failed_step_marks_dependents_blocked_not_run` — comprovado que um
  step bloqueado nunca é despachado ao router.
- Nenhum módulo em `core/planner/` importa `subprocess`, `os.system`,
  `eval`, `exec`, ou faz import dinâmico — checável por `grep` direto nos
  arquivos.

## O que falta (não implementado nesta sessão)

- Nenhum `Planner` que raciocine sobre linguagem natural (LLMPlanner).
- Nenhuma persistência de `Plan` (fica só em memória, quem chama decide o
  que fazer com o resultado).
- Nenhum scheduler paralelo de steps independentes — `execute_plan` roda
  sequencial na ordem topológica, mesmo quando dois steps não dependem um
  do outro. Correto, não otimizado.
- Nenhuma integração real com `core/ipc_handlers.py`/`core/pc_voice_intent.py`
  — o Planner existe como biblioteca, ninguém o chama ainda em produção.
