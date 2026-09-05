# Auditoria de Integração Frontend-Backend (IPC) - ZARA 3.0

## Métodos invocados pelo frontend (preload.ts)

### Invoke (requisição com resposta)
- engine-change
- engine-list
- supercerebro-toggle
- supercerebro-status
- send-message
- interrupt
- conversation-history-list
- conversation-history-clear
- memory-galaxy-list
- action-execute
- action-list
- system-metrics
- system-info
- voice-start
- voice-stop
- voice-status
- voice-mute
- config-get
- config-set
- lab-state
- lab-send
- lab-proposal-create
- lab-proposal-decide
- reminder-create
- reminder-list
- reminder-cancel
- window-minimize
- window-maximize
- window-close

### Send (notificação sem resposta)
- voice-mic-chunk

## Eventos ouvidos pelo frontend (preload.ts)
- state-change
- message
- metrics
- voice-level
- voice-output-audio
- supercerebro-change
- reminder-created
- reminder-fired
- routing-telemetry

## Handlers implementados no backend (core/ipc_handlers.py)

Handlers presentes no `handler_map` (linhas 2827-2868):
- engine-change
- engine-list
- supercerebro-toggle
- supercerebro-status
- send-message
- interrupt
- voice-mute
- voice-mic-chunk
- action-execute
- action-confirm
- action-confirm-cancel
- action-list
- soul-get
- self-status
- system-metrics
- system-info
- voice-start
- voice-stop
- voice-status
- config-get
- config-set
- lab-state
- lab-send
- lab-proposal-create
- lab-proposal-decide
- reminder-create
- reminder-list
- reminder-cancel
- memory-user-add
- memory-user-search
- memory-user-list
- memory-user-forget
- project-memory-get
- project-memory-list
- memory-galaxy-list
- conversation-history-list
- conversation-history-clear

## Eventos enviados pelo backend (via `send_event`)
- voice-output-audio
- state-change (múltiplas: LISTENING, THINKING, STANDBY, SPEAKING)
- voice-level (múltiplas)
- message (múltiplas)
- reminder-created
- reminder-fired
- supercerebro-change
- metrics
- voice-mute-change

## Divergências identificadas

### Críticas (frontend chama, backend não implementa)
1. **Controles de janela**: 
   - Frontend invoca: `window-minimize`, `window-maximize`, `window-close`
   - Backend: **nenhum handler encontrado** para esses tipos.

2. **Evento de telemetria**:
   - Frontend escuta: `routing-telemetry`
   - Backend: **nenhum evento enviado** desse tipo.

### Observações
- Todos os outros métodos invocados pelo frontend têm correspondência no backend.
- O frontend também envia `voice-mic-chunk` via `send`, que é tratado pelo backend.
- O backend implementa handlers adicionais não expostos diretamente pelo preload.ts (como `action-confirm`, `soul-get`, etc.), possivelmente usados por outros mecanismos.

## Recomendações
- Implementar handlers no backend para os controles de janela ou remover as chamadas do frontend se não forem necessárias.
- Implementar o envio do evento `routing-telemetry` pelo backend ou remover o listener do frontend se não for utilizado.
- Considerar padronização de nomes e documentação dos contratos IPC para evitar futuras divergências.

## Prova de verificação
- Comandos utilizados: `search_files` e `read_file` sobre o diretório `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`.
- Saídas reais foram capturadas nos arquivos:
  - `frontend/src/preload.ts`
  - `core/ipc_handlers.py`
- Nenhum arquivo foi modificado durante a auditoria.