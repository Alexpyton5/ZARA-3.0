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

Nenhuma em execução. Turno CORUJÃO + sprint de 4h de 2026-09-05 fechados — ver
`.claude/TASK_BOARD.md`, série `T-2026-09-05-*`, e os relatórios em
`.zara-dev/reports/CORUJAO_2026-09-05.md` e
`.zara-dev/reports/SPRINT_4H_2026-09-05.md`.

O que mudou de método nesse turno: a Home passou a ser conferida
**renderizando**, não lendo código. `node .zara-tests/ui/run-ui-checks.mjs`
builda, sobe um servidor local e roda 7 probes contra o DOM real. Qualquer
sessão futura que mexer na Home roda isso antes de dizer que está bom.

## Owner da task

UI Director (time novo — agente ainda não criado; criado sob demanda quando
UI-001 iniciar, ver `.claude/ORG.md`).

## Files

A definir no brief do Pixel-Perfect Analyst para cada região (ver
`.claude/TASK_BOARD.md`, série UI-00x).

## Dependencies

—

## Status

`AGUARDANDO ALEX` — o que foi feito na madrugada está commitado e enviado
para `backup/estado-20260820-1143-xywufc`, mas **nada disso foi visto
rodando no Windows**. O nível de evidência de tudo é `RUNTIME_AUTOMATED`
(render headless), nunca `PACKAGED_RUNTIME` nem `PHYSICAL_BY_ALEX`.

## Next action

1. Empacotar um build com o estado atual e gravar `BUILD_INFO.json`
   (`.claude/rules/build-release.md`).
2. Pedir ao Alex o micro smoke físico de nível 1 — 3 comandos, com
   `ALEX_OPEN_THIS_EXE:` e caminho absoluto.
3. Só depois disso qualquer coisa da madrugada pode subir de nível de
   evidência.
