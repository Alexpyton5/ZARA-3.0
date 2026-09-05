# Fluxo Planner -> Tool — ZARA 3.0

```
PlannerRequest(goal, context, explicit_steps)
        |
        v
   RulePlanner.plan()
        |
        v
   validate_plan()  --- inválido --> PlannerResponse(accepted=False, rejection_reason=[...])
        |
        v (válido)
   Plan(status=VALIDATED)
        |
        v
   execute_plan(plan, tool_router)
        |
        v (por step, em ordem topológica)
   ToolRequest(tool_name, parameters)
        |
        v
   ToolRouter.route(request)          <-- MESMO caminho de qualquer chamada de tool hoje
        |                                 (capability/risk/permission/audit já aplicados aqui,
        |                                  o Planner não pula nada disso)
        v
   ToolResult(success, error, data, verificado)
        |
        v
   PlanStep.status = VERIFIED | FAILED
   step falhou? -> todo dependente vira BLOCKED, nunca despachado
        |
        v
   PlanResult(status, completed_steps, failed_steps, skipped_steps)
```

## Exemplo concreto (testado em `tests/test_planner_execution.py`)

```
Plan "verificar disco e avisar":
  s1: files_list(path=".")
  s2: os_volume(level=30)          depends_on=[]
  s3: notification_send(...)       depends_on=[s1]

Se s1 falha:
  s3 fica BLOCKED (nunca chama notification_send)
  s2 roda normalmente (independente)
  Plan.status = PARTIAL
```

## Por que não existe atalho

`execute_plan` só tem um caminho de despacho: `tool_router.route(...)`. Não
há branch para "se for uma tool simples, chama direto"; isso eliminaria a
garantia de permissão/auditoria para exatamente os casos mais simples, que é
o oposto do que se quer. O "fast path" da missão (Board 5) é sobre *quando*
formar um Plan (ou nem formar, e usar o intent determinístico direto), não
sobre um segundo caminho de execução dentro do Planner.
