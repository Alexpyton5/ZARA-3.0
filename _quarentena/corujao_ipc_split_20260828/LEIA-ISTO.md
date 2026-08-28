# Quarentena: refactor abandonado do "Corujao" (2026-08-28)

6 arquivos (ipc_actions, ipc_config, ipc_protocol, ipc_router, ipc_telegram,
ipc_voice) criados pelo processo Codex nao autorizado que o Alex mandou
remover. Eram a tarefa "T1: Decompor IPCHandler (5 modulos)" do plano dele
(ACTIVE_TASK_STATE.md, ja removido).

Ficou pela metade e morto:
- nenhum arquivo vivo do projeto importa nenhum dos 6; eles so se importam
  entre si (verificado por grep antes de mover).
- nenhum estava rastreado no git.
- core/ipc_voice.py tinha import quebrado de verdade: importava
  `_looks_like_unhandled_local_action` de core.pc_voice_intent, onde essa
  funcao nunca existiu (ela mora em core/ipc_handlers.py). Ou seja,
  `_voice_turn_needs_executor` daquele arquivo quebraria se fosse chamado --
  duplicata quebrada da funcao real, que segue viva e correta em
  ipc_handlers.py:1295 e e a que o produto realmente usa.

Nada apagado, so movido.
