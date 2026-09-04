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
