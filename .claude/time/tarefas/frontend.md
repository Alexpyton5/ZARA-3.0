# TAREFA ATUAL — agente FRONTEND

TASK_ID: TASK-F002
STATUS: ABERTA
MODO: READ-ONLY — nao edite nenhum arquivo
ROLLBACK: nao se aplica, nada e escrito

## Contexto

Voce ja entregou o FRONTEND-ORIENTACAO-000. Confirmado e aceito: os 29 canais
batendo 1:1, a defesa do sidecar orfao em main.ts:804, e o barril
`zara/index.ts` sem nenhum importador (protótipo morto).

Esta tarefa e so o que voce mesmo apontou como NEXT_SMALLEST_STEP.

## O que responder

1. `npm run typecheck` e `npm run lint` — resultado exato. Decide se sua area
   esta sa antes de qualquer escrita.
2. Os diffs sujos de `main.ts`, `ZaraControlCenter.tsx` e `PainelConfiguracoes.tsx`
   — o que mudou? Toca o lifecycle do sidecar?

**Nao integre nem descarte o protótipo orfao.** A decisao e do Alex; eu levo a ele.

## Como reportar

`mcp__ccd_session_mgmt__send_message` com
session_id = `local_c4b07745-444f-448d-af42-4f997ccbe6b3`
