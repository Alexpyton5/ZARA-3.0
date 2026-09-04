# Quarentena — screenshots e scripts de comparação UI (2026-09-04)

## O que é

Um exercício pontual, já concluído, de comparar a UI Electron real com uma referência
(localhost/protótipo) — visível nos relatórios `UI_FIDELITY_GOALS.md`,
`UI_FIDELITY_HANDOFF.md`, `UI_FIDELITY_TASK_BOARD.md` (esses continuam na raiz, são
REPORTS, não foram tocados).

## O que foi movido

23 imagens sem nenhuma referência em código (`comparativo-final.png`, `crop-*.png` x6,
`electron-final/identico/logo/p1-p6.png` x9, `localhost-final/p1/p1b/p3/p5/p6.png` x6) +
`ZARA_AUDIT_20260901.zip` (zip redundante — os 5 `.md` dentro dele já existem soltos na
raiz, é só um backup datado) + os 3 scripts PowerShell que geravam essas imagens
(`montage.ps1`, `screenshot.ps1` com `-TargetPid 19108` hardcoded de um processo que já
não existe mais, `list-electron.ps1`).

## O que NÃO foi movido (tem referência real em código, fica no lugar)

- `master.png` — usado por `core/ipc_handlers.py`, `core/actions/os_ops.py`,
  `frontend/src/renderer/components/zara-home/ZaraHome.tsx`
- `localhost.png` — usado por `core/url_security.py`, `frontend/src/main.ts`, testes
- `interface nova.jpg` — usado por `core/ipc_handlers.py`, `frontend/src/renderer/lib/aparencia.ts`, testes
- `electron-check.png` — era o input do `montage.ps1`/`screenshot.ps1` movidos; como o
  script que o gera também foi pra quarentena junto, não sobrou nada dependendo dele no
  lugar antigo.

## Decisão

Nada apagado — só isolado. Se precisar recriar a comparação, os 3 scripts estão aqui,
juntos, prontos pra rodar de novo (ajustando o PID do processo do Electron atual).

Data: 2026-09-04
