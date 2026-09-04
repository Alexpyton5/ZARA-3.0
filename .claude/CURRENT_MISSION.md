# ZARA — Missão Atual

Atualizar conforme o trabalho progride. Não é histórico — é só o estado agora.

## Objetivo atual

**ZARA MASTER PIXEL-PERFECT FINALIZATION** (aberta por Alex, 2026-09-04).

Fazer a interface real Electron/React da ZARA ficar visualmente o mais
idêntica possível ao MASTER, sem reconstruir/redesenhar/reinterpretar:

```
Electron visual fidelity + animations + widgets + preservar funcionalidade
```

MASTER absoluto: `https://zara-titanium-emerald.p9jpk5w4m6.chatgpt.site/`
(ver `.claude/ORG.md`). Executada pela cadeia UI Director → Pixel-Perfect
Analyst → Frontend/Motion Executor → Visual QA, política em
`.claude/WORKING_MODEL.md` ("Refinamento visual pixel-perfect"), decisão em
`.claude/DECISIONS.md`.

Backlog padrão de voz (ordem fixa definida em `.claude/rules/time-zara.md`,
Fase 1) segue registrado e não foi cancelado — F1.1 continua aguardando
teste físico do Alex — mas deixou de ser a única frente ativa: Alex abriu a
missão de UI explicitamente, e teste manual pendente de F1.1 não bloqueia
trabalho `SAFE`/independente em paralelo (`.claude/DECISIONS.md`, 2026-09-04):

```
F1.1 VOZ KORE → F1.2 LATÊNCIA → F1.3 MICROFONE SEM LOOP → F1.4 VOZ → AÇÃO REAL
```

## Task ativa

Nenhuma em execução ainda. Próxima: **UI-001 GLOBAL COMPOSITION**
(Pixel-Perfect Analyst / Opus — analisar MASTER vs. Electron atual antes de
qualquer CSS).

## Owner da task

UI Director (time novo — agente ainda não criado; criado sob demanda quando
UI-001 iniciar, ver `.claude/ORG.md`).

## Files

A definir no brief do Pixel-Perfect Analyst para cada região (ver
`.claude/TASK_BOARD.md`, série UI-00x).

## Dependencies

—

## Status

`IDLE` — política instalada, nenhuma região iniciada.

## Next action

UI-001 GLOBAL COMPOSITION: Pixel-Perfect Analyst compara MASTER vs. Electron
atual (viewport fixo) e produz o primeiro brief. Depois, Frontend Executor
implementa.
