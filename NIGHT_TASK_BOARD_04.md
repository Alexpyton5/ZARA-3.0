# NIGHT_TASK_BOARD_04

Missão: Planner Foundation + Model Router Contracts.

[x] Board 1 — Current Architecture Mapping → `PLANNER_INTEGRATION_MAP.md`
[x] Board 2 — Planner Domain Model → `core/planner/models.py`
[x] Board 3 — Plan Validation → `core/planner/validation.py`
[x] Board 4 — Planner Interface → `core/planner/planner.py` (`Planner`, `RulePlanner`)
[x] Board 5 — Deterministic/Fast Path → resolvido por design: intent determinístico existente continua sendo o padrão; Planner é opt-in (ver `PLANNER_ARCHITECTURE.md`)
[x] Board 6 — Multi-step Foundation → suportado por `depends_on` + `topological_order` (testado)
[x] Board 7 — Execution Handoff → `core/planner/execution.py::execute_plan`
[x] Board 8 — Plan Execution State Foundation → `PlanStatus`/`StepStatus` em `models.py`
[x] Board 9 — Failure Propagation → testado em `test_failed_step_marks_dependents_blocked_not_run`
[x] Board 10 — Model Domain Contracts → **já existiam** em `core/model_router.py`; documentado, não duplicado
[x] Board 11 — AI Provider Contract → `core/ai_provider_contracts.py::AIProvider` (Protocol, sem implementação)
[!] Board 12 — Gemini Adapter Foundation → SKIPPED_REQUIRES_OWNER (ver `NIGHT_04_OWNER_DECISIONS.md` #1)
[x] Board 13 — Model Registry → já existe (`MODEL_REGISTRY` em `core/model_router.py`)
[x] Board 14 — Model Routing Rules → já existe (`rank_models`/`_score`)
[x] Board 15 — Routing Modes Foundation → já existe (`policy: smart/economy/fast`, `normalize_auto_engine`)
[x] Board 16 — Model Fallback → já existe (`get_fallback_chain`, diversidade de provedor)
[x] Board 17 — Capability Matching → `ModelCapability` (aditivo) mapeado para `TaskType` (existente)
[x] Board 18 — Planner ↔ Model Router Boundary → `select_model(ModelRequest(capabilities=[...]))`, nunca provider específico
[!] Board 19 — Structured Planner Output → NÃO FEITO (depende de Decision 3, `LLMPlanner`)
[x] Board 20 — Security Boundaries → revisado; Planner não tem shell/eval/import dinâmico (checado por leitura direta do código)
[x] Board 21 — Tests → 31 testes novos, todos SAFE, todos passando
[x] Board 22 — Compatibility Review → `tools/zara_validate.py --full` confirmou 0 regressões (45 falhas conhecidas, iguais antes/depois; 1571→1602 passando)
[~] Board 23 — Architecture Red Team → feito de forma leve (achado principal: duplicação evitada com model_router.py), não uma revisão hostil formal separada
[x] Board 24 — Documentation → `PLANNER_ARCHITECTURE.md`, `MODEL_ROUTER_ARCHITECTURE.md`, `PLANNER_TOOL_FLOW.md`, `MODEL_PROVIDER_CONTRACT.md`
[x] Board 25 — Final Incremental Validation → feito (`tools/zara_validate.py --full`, uma única vez, sequencial)
[!] Board 26 — Build Check → NÃO FEITO — mudanças são Python puro sem tocar build/runtime/Electron; build check não seria informativo

Boards 27+ (loop de continuação / PHASE2 / PHASE3): não iniciados. Ver
`NIGHT_MISSION_04_FINAL_REPORT.md`, seção "Remaining Safe Work", para o que
ficou como próximo passo em vez de continuar sozinho até esgotar todo
trabalho seguro possível.
