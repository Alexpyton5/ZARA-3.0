# Auditoria de Integração IPC Frontend-Backend

## Frontend Invocações (preload.ts)
- `engine-change`
- `engine-list`
- `supercerebro-toggle`
- `supercerebro-status`
- `send-message`
- `interrupt`
- `conversation-history-list`
- `conversation-history-clear`
- `memory-galaxy-list`
- `action-execute`
- `action-list`
- `system-metrics`
- `system-info`
- `voice-start`
- `voice-stop`
- `voice-status`
- `voice-mic-chunk` (send)
- `voice-mute`
- `config-get`
- `config-set`
- `lab-state`
- `lab-send`
- `lab-proposal-create`
- `lab-proposal-decide`
- `reminder-create`
- `reminder-list` (state)
- `reminder-cancel`
- `window-minimize`
- `window-maximize`
- `window-close`
- Event listeners: `state-change`, `message`, `metrics`, `voice-level`, `voice-output-audio`, `supercerebro-change`, `reminder-created`, `reminder-fired`, `routing-telemetry`

## Backend Handlers Implementados (ipc_handlers.py)
Handlers presentes (async def handle_*):
- handle_voice_mic_chunk
- handle_reminder_create
- handle_reminder_list
- handle_reminder_cancel
- handle_memory_user_add
- handle_memory_user_search
- handle_memory_user_list
- handle_memory_user_forget
- handle_project_memory_get
- handle_project_memory_list
- handle_memory_galaxy_list
- handle_conversation_history_list
- handle_conversation_history_clear
- handle_message
- handle_lab_state
- handle_lab_send
- handle_lab_proposal_create
- handle_lab_proposal_decide
- handle_engine_change
- handle_supercerebro_toggle
- handle_send_message
- handle_interrupt
- handle_action_execute
- handle_action_confirm
- handle_action_confirm_cancel
- handle_system_metrics
- handle_voice_start
- handle_voice_mute
- handle_voice_stop
- handle_config_get
- handle_soul_get
- handle_self_status
- handle_config_set
- handle_engine_list
- handle_supercerebro_status
- handle_action_list
- handle_system_info
- handle_voice_status

## Diferenças Críticas (Frontend sem Backend Correspondente)
Os seguintes métodos são invocados pelo frontend mas **não possuem handler** no backend:
- `window-minimize`
- `window-maximize`
- `window-close`

## Observações
- Todos os outros métodos invocados pelo frontend têm handlers correspondentes no backend.
- Os três métodos de controle de janela são expostos pelo frontend mas não têm implementação no backend. Isso sugere que estes são tratados diretamente pelo Electron principal ou que há uma lacuna na implementação.

## Próximos Passos Recomendados
1. Implementar handlers ausentes para `window-minimize`, `window-maximize`, `window-close` no backend, seguindo o padrão dos outros handlers (ex.: `handle_window_minimize`, etc.).
2. Criar testes de aceitação para validar cada método IPC em ambos os lados.