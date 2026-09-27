# ZARA CURRENT VERIFIED STATE

Last validation: 2026-09-04_13-59-03
Commit: 2dff34e (branch `backup/estado-20260820-1143`)
Health: 100%
Root hygiene: CRITICAL

## WORKING

- SYS-DISK Espaço em disco
- TECH-001 Camada técnica (zara_validate.py)

## BROKEN

- nenhum

## DEGRADED

- nenhum

## UNVERIFIED

- nenhum

## KNOWN FAILURES (camada técnica, pytest)

- nenhuma

## PERFORMANCE (>5s)

- nada lento nesta rodada

## CAPABILITIES

- 2 checagens nesta rodada (modo sem abrir a ZARA, sem contagem total).

## IMPORTANT ARCHITECTURE

- Dispatcher central: `core/ipc_handlers.py` (classe `IPCHandler`)
- Intents de voz/texto: `core/pc_voice_intent.py` (`PcVoiceIntentDetector`)
- Registro/execução de ações: `core/action_registry.py`
- Mapa completo: `.claude/rules/path-rules/backend-core.md` e `frontend-electron.md`

## LAST CHANGES DETECTED

- ZARA_TESTAR_TUDO.bat
- tools/zara_selftest.py

## RECOMMENDED NEXT TESTS

- Nada crítico pendente. Rodar QUICK após qualquer mudança de código; FULL SAFE só se mudança tocar router/execução compartilhada.

## AGENT INSTRUCTIONS

Antes de auditar a ZARA de novo: compare `Commit` acima com `git rev-parse HEAD`.
Se forem iguais e nada relevante mudou, NÃO rode a suíte completa de novo --
este arquivo já é a resposta. Se HEAD mudou, rode `tools/zara_validate.py`
(incremental) antes de qualquer suíte completa. Ver `ZARA_AGENT_START_HERE.md`.
