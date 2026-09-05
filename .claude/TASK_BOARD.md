# ZARA — Task Board

Formato simples. Não virar burocracia.

## DONE

- ID: T-2026-09-05-07
  owner: Chief of Staff (turno CORUJÃO)
  scope: harness de UI — um comando builda, serve e roda 7 probes contra o DOM
  files: `.zara-tests/ui/run-ui-checks.mjs` + 7 `probe-*.mjs`
  DoD: `node .zara-tests/ui/run-ui-checks.mjs` -> 7/7 (commit `c027e74`+)

- ID: T-2026-09-05-06
  owner: Chief of Staff (turno CORUJÃO)
  scope: botão de voz do dock deixou de contar história própria; segue `voice-status` e cai junto com o Core
  files: `frontend/src/renderer/components/zara-home/VoiceDock.tsx`
  DoD: `probe-voz.mjs` 4/4 (commit `4bb0a3d`)

- ID: T-2026-09-05-05
  owner: Chief of Staff (turno CORUJÃO)
  scope: Ferramentas parou de fingir que abriu — rótulo vem do executor, tile some quando o app não existe
  files: `ToolsCard.tsx`, `zara-home.css`
  DoD: `probe-ferramentas.mjs` 6/6 (commit `c027e74`)

- ID: T-2026-09-05-04
  owner: Chief of Staff (turno CORUJÃO)
  scope: remover TODO dado inventado da Home (João/WhatsApp, reunião 14:00, 12/3/5/7, 61%)
  files: `ForYouCard.tsx`, `CommunicationsCard.tsx`, `ActiveProjectCard.tsx`, `useHomeSignals.ts`, `zara-home.css`
  DoD: `probe-sem-mentira.mjs` 9/9, com backend cheio e vazio (commit `014b10b`)

- ID: T-2026-09-05-03
  owner: Chief of Staff (turno CORUJÃO)
  scope: estados do Core presos (SUCCESS/ERROR eternos) e "Aguardando autorização" que nunca acendia
  files: `useZaraCoreState.ts`, `frontend/src/main.ts`
  DoD: `probe-estados.mjs` 12/12 (commit `9070fa6`)

- ID: T-2026-09-05-02
  owner: Chief of Staff (turno CORUJÃO)
  scope: comando de texto passou a ter volta na tela (tira de conversa, voz e texto na mesma tira)
  files: `ConversationStrip.tsx`, `TextCommandInput.tsx`, `ZaraHome.tsx`, `zara-home.css`
  DoD: `probe-texto.mjs` 5/5, incluindo resposta vazia e erro de IPC (commit `987cc16`)

- ID: T-2026-09-05-01
  owner: Chief of Staff (turno CORUJÃO)
  scope: 10 dos 11 itens da Sidebar não levavam a lugar nenhum; agora cada um lê um canal IPC que já existia
  files: `SectionView.tsx`, `ZaraHome.tsx`, `core/actions/os_ops.py` (`os_app_list`), `zara-home.css`
  DoD: `probe-sections.mjs` 11/11 (commit `f2c8c36`)

- ID: T-2026-09-05-00
  owner: Chief of Staff (turno CORUJÃO)
  scope: plataforma, dock e painel Sistema medidos pixel a pixel contra a MASTER
  files: `zara-home.css`, `SystemPanel.tsx`, `VoiceDock.tsx`
  DoD: render local comparado com `master.png` região a região (commit `bb39c82`)

- ID: T-2026-09-04-01
  owner: Chief of Staff
  scope: instalar modelo de operação permanente (Chief of Staff + hierarquia)
  files: `.claude/ORG.md`, `.claude/WORKING_MODEL.md`, `.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`, `.claude/DECISIONS.md`
  DoD: 5 arquivos criados e preenchidos, boot order registrado, checkpoint git feito

- ID: T-2026-09-04-00
  owner: (sessão anterior)
  scope: menu `ZARA_INICIAR.bat` + estado verificado `ZARA_STATE.md`/`json`
  files: `ZARA_TESTAR_TUDO.bat`, `ZARA_INICIAR.bat`, `tools/zara_selftest.py`
  DoD: commit `1745a29` — feito e enviado (push) para
  `backup/estado-20260820-1143`

## REVIEW

—

## BLOCKED

—

## IN PROGRESS

- ID: T-BACKLOG-F1.1
  owner: Voice Lead → `voice-lead` (time novo)
  scope: voz Kore funcionando na saída (Fase 1, prioridade 1)
  files: `core/gemini_live_voice.py`, `core/voice_tts.py`, `core/ipc_handlers.py` (_speak_response, trava)
  DoD: teste físico — Alex ouve a voz Kore, sem fallback silencioso pra SAPI

## TODO

- ID: T-BACKLOG-F1.2
  owner: Memory/Intelligence Lead (time novo — agente ainda não criado)
  scope: latência mínima de resposta medida e reduzida
  files: `core/model_router.py`
  DoD: número em ms, antes/depois, medido por `[VOICE_TRACE]` + SQLite
  nota: não bloqueado por teste físico pendente de F1.1 — pode iniciar
  (`.claude/DECISIONS.md`, 2026-09-04)

- ID: T-BACKLOG-F1.3
  owner: Voice Lead → `voice-lead` (time novo)
  scope: microfone sem loop com a própria voz da ZARA
  files: `frontend/src/renderer/lib/aecAudio.ts`, `core/windows_audio.py`
  DoD: teste físico — ZARA não se ouve, barge-in corta áudio de verdade

- ID: T-BACKLOG-F1.4
  owner: Backend Lead (time novo — agente ainda não criado)
  scope: comando falado executa ação real no PC (voz = texto)
  files: `core/ipc_handlers.py`, `core/pc_voice_intent.py`, `core/action_registry.py`
  DoD: mesma frase por voz e por texto, mesmo resultado físico no Windows

- ID: UI-001
  owner: UI Director → Pixel-Perfect Analyst (time novo — agente ainda não criado)
  scope: GLOBAL COMPOSITION — viewport, colunas principais, eixo central, proporção, composição vertical, espaçamento geral
  files: a definir no brief (Opus compara MASTER vs. Electron atual primeiro, antes de qualquer CSS)
  DoD: brief `UI BRIEF` entregue ao Frontend Executor; screenshot Electron no mesmo viewport do MASTER
  status: master.png RESOLVIDO sem pedir nada ao Alex — `master.png` já
  existia na raiz do repo (git-tracked, legenda própria "Prévia visual ·
  dados da MASTER", commit `1322fcf`), verificado por leitura visual e
  copiado pra `.zara-tests/ui/master.png` (1440×900).
  electron-real.png: WAITING — pipeline completo e automático (2026-09-05,
  correção de transporte). `frontend/src/main.ts`:
  `captureElectronScreenshot` tira o print real ~2,5s depois da janela
  aparecer em primeiro plano (e de novo a cada resize/maximize);
  `syncUiSnapshotIfNeeded` dá `git pull --ff-only`, compara sha256 do PNG +
  `git HEAD` + `.zara-tests/ui/QA_REQUEST.flag`, e só commita/`push` (escopo
  só `.zara-tests/ui`, nunca `--force`, nunca junto de código do Alex)
  quando algo realmente mudou — abrir a ZARA normalmente NÃO gera commit
  sozinho. Bug corrigido nesta rodada: a versão anterior calculava o
  caminho de `.zara-tests/ui` a partir de `app.getAppPath()` com um `../..`
  fixo que só é válido em dev — no build empacotado (que é o que o Alex
  realmente roda) apontava pra dentro de `win-unpacked/`, não pro repo.
  `findRepoRoot()` agora sobe a árvore procurando `.git`, funciona nos dois
  modos. `QA_REQUEST.flag` já criado pra esta task — na próxima abertura
  normal da ZARA o pull traz o pedido, ela captura e sincroniza sozinha, e
  o flag some. Commits `d326675`, `72bc83c`, `bc36977` + commit seguinte
  desta sessão (correção de transporte).
  Também grava `current_viewport.json` (largura/altura da janela, content
  bounds, devicePixelRatio, zoom) no mesmo gatilho.
  Não validado por typecheck real nesta sessão (node_modules não instalado
  aqui); revisão manual do diff contra o padrão existente do arquivo.

  MUDANÇA VISUAL REAL (2026-09-05): achei e corrigi um bug de verdade sem
  precisar de screenshot novo, só lendo `zara-home.css` + `main.ts`. A
  composição já está calibrada contra MASTER 1671×941 (`.zh-content-top`
  fixo em até 1377px + sidebar até 222px + padding ≈ 1650px), mas a janela
  do Electron abria em 1500px de largura (minWidth 1200px) — mais estreita
  que a composição. `.zh-content` tem só `overflow-y: auto`, e pela spec de
  CSS isso vira `overflow-x: auto` também: a coluna direita (Ferramentas
  com Docker, botão "Continuar" — ambos já existem no código, não estavam
  faltando) ficava fora da área visível, só alcançável rolando a tela pro
  lado, sem barra de rolagem óbvia. Corrigido em `frontend/src/main.ts`
  (`createWindow`): `width: 1680, height: 980, minWidth: 1500`. Verificado
  por leitura de `ToolsCard.tsx`/`ActiveProjectCard.tsx` (Docker e
  "Continuar" já implementados) + aritmética das larguras do CSS, não por
  screenshot. Ícones de status (shield/wifi/cloud) NÃO foram tocados — são
  intencionalmente monocromáticos/opacos quando não há conexão real
  (comentário em `zara-home.css` linha ~141, regra anti-falso-sucesso);
  parecer "menos coloridos que o MASTER" aqui está correto, não é bug.

- ID: UI-002
  owner: UI Director (time novo — agente ainda não criado)
  scope: CORE — diâmetro relativo, forma, glass/crystal, reflexos, rim emerald, escuridão interna, escala/profundidade do logo ZA, integração com fundo
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-003
  owner: UI Director (time novo — agente ainda não criado)
  scope: ZA LOGO — escala e profundidade do logotipo dentro do Core
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-004
  owner: UI Director (time novo — agente ainda não criado)
  scope: PLATFORM — perspectiva, geometria de elipse, espessura física, camadas, metal, reflexos, anéis emerald, eixo central, sombra de contato
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-005
  owner: UI Director (time novo — agente ainda não criado)
  scope: DOCK — largura, altura, relação com platform, glass, radius, proeminência do botão de voz, espaçamento
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-006
  owner: UI Director (time novo — agente ainda não criado)
  scope: HEADER
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-007
  owner: UI Director (time novo — agente ainda não criado)
  scope: SIDEBAR
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-008
  owner: UI Director (time novo — agente ainda não criado)
  scope: PARA VOCÊ
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-009
  owner: UI Director (time novo — agente ainda não criado)
  scope: COMMUNICATIONS
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-010
  owner: UI Director (time novo — agente ainda não criado)
  scope: ACTIVE PROJECT
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-011
  owner: UI Director (time novo — agente ainda não criado)
  scope: TOOLS
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-012
  owner: UI Director (time novo — agente ainda não criado)
  scope: SYSTEM PANEL
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-013
  owner: UI Director (time novo — agente ainda não criado)
  scope: BACKGROUND
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-014
  owner: UI Director (time novo — agente ainda não criado)
  scope: TYPOGRAPHY — hierarquia, peso visual, equilíbrio, densidade
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-015
  owner: UI Director (time novo — agente ainda não criado)
  scope: MATERIALITY — smoked titanium, dark crystal, silver reflection, emerald accent, premium glass (evitar dark SaaS genérico/cyberpunk)
  files: a definir no brief
  DoD: Visual QA `APPROVED` — passa obrigatoriamente por Opus

- ID: UI-016
  owner: UI Director (time novo — agente ainda não criado)
  scope: MOTION — sensação premium/smooth/restrained/purposeful, não bouncy/gamer/excessivo
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-017
  owner: UI Director (time novo — agente ainda não criado)
  scope: WIDGET INTERACTIONS — hover, waveform, voice states, widget transitions, telemetry animations, card transitions, active states
  files: a definir no brief
  DoD: Visual QA `APPROVED`

- ID: UI-018
  owner: UI Director (Visual QA — Opus, final pass)
  scope: FINAL COMPOSITION / FINAL QA — MASTER vs. Electron lado a lado, listar diferenças residuais de maior impacto, sem editar antes de listar
  files: —
  DoD: só fecha quando todas as regiões acima passaram; relatar `PIXEL-PERFECT PASS COMPLETE` + diferenças residuais (nunca "100%" sem prova)
