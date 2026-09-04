# ZARA — Task Board

Formato simples. Não virar burocracia.

## DONE

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
