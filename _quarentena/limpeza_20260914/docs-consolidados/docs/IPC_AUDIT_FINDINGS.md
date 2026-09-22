# Auditoria de Integração IPC Frontend-Backend

## Resumo
- Frontend invoca 29 canais via `ipcRenderer.invoke` (preload.ts).
- Backend implementa handlers para os mesmos 29 canais (main.ts, setupIPC).
- Frontend escuta 9 eventos via `ipcRenderer.on` (preload.ts).
- Backend emite 8 eventos correspondentes (main.ts, handlePythonEvent).
- **Divergência**: evento `routing-telemetry` é escutado no frontend mas não emitido pelo backend.

## Detalhes

### Canais de Invocação (invoke) - 29
1. engine-change
2. engine-list
3. supercerebro-toggle
4. supercerebro-status
5. send-message
6. interrupt
7. conversation-history-list
8. conversation-history-clear
9. memory-galaxy-list
10. action-execute
11. action-list
12. system-metrics
13. system-info
14. voice-start
15. voice-stop
16. voice-status
17. voice-mute
18. config-get
19. config-set
20. lab-state
21. lab-send
22. lab-proposal-create
23. lab-proposal-decide
24. reminder-create
25. reminder-list
26. reminder-cancel
27. window-minimize
28. window-maximize
29. window-close

### Eventos de Escuta (on) - 9
1. state-change
2. message
3. metrics
4. voice-level
5. voice-output-audio
6. supercerebro-change
7. reminder-created
8. reminder-fired
9. routing-telemetry  ← **faz falta no backend**

### Eventos Emitidos pelo Backend - 8
- state-change
- message
- metrics
- voice-level
- voice-output-audio
- supercerebro-change
- reminder-created
- reminder-fired

## Recomendações
1. Implementar o envio do evento `routing-telemetry` pelo backend (ex: ao receber decisões de roteamento do modelo).
2. Ou remover o listener do frontend se o evento não for utilizado (verificar uso em componentes).

## Localização das Provas
- Frontend invocação: `frontend/src/preload.ts` linhas 11-90
- Frontend escuta: `frontend/src/preload.ts` linhas 92-140
- Backend handlers: `frontend/src/main.ts` linhas 679-734
- Backend emissões: `frontend/src/main.ts` linhas 441-488 (função handlePythonEvent)