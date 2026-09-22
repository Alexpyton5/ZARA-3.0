# Auditoria de Integração IPC Frontend-Backend

## Contratos IPC do Frontend (preload.ts)

Arquivo: `frontend/src/preload.ts`

### Invocações via `ipcRenderer.invoke`

| Evento | Linha |
|--------|-------|
| engine-change | 11 |
| engine-list | 12 |
| supercerebro-toggle | 17 |
| supercerebro-status | 18 |
| send-message | 24 |
| interrupt | 25 |
| conversation-history-list | 30 |
| conversation-history-clear | 31 |
| memory-galaxy-list | 35 |
| action-execute | 40 |
| action-list | 41 |
| system-metrics | 46 |
| system-info | 47 |
| voice-start | 52 |
| voice-stop | 53 |
| voice-status | 54 |
| voice-mute | 60 |
| config-get | 65 |
| config-set | 66 |
| lab-state | 71 |
| lab-send | 72 |
| lab-proposal-create | 73 |
| lab-proposal-decide | 74 |
| reminder-create | 78 |
| reminder-list | 79 |
| reminder-cancel | 80 |
| window-minimize | 85 |
| window-maximize | 86 |
| window-close | 87 |

### Escutas via `ipcRenderer.on`

| Evento | Linha |
|--------|-------|
| state-change | 94 |
| message | 99 |
| metrics | 104 |
| voice-level | 109 |
| voice-output-audio | 118 |
| supercerebro-change | 123 |
| reminder-created | 128 |
| reminder-fired | 133 |
| routing-telemetry | 138 |

## Handlers do Backend (ipc_handlers.py)

Arquivo: `core/ipc_handlers.py`

### Handler map (linhas 2828-2867)

| Evento | Handler |
|--------|---------|
| engine-change | handle_engine_change |
| engine-list | handle_engine_list |
| supercerebro-toggle | handle_supercerebro_toggle |
| supercerebro-status | handle_supercerebro_status |
| send-message | handle_send_message |
| interrupt | handle_interrupt |
| voice-mute | handle_voice_mute |
| voice-mic-chunk | handle_voice_mic_chunk |
| action-execute | handle_action_execute |
| action-confirm | handle_action_confirm |
| action-confirm-cancel | handle_action_confirm_cancel |
| action-list | handle_action_list |
| soul-get | handle_soul_get |
| self-status | handle_self_status |
| system-metrics | handle_system_metrics |
| system-info | handle_system_info |
| voice-start | handle_voice_start |
| voice-stop | handle_voice_stop |
| voice-status | handle_voice_status |
| config-get | handle_config_get |
| config-set | handle_config_set |
| lab-state | handle_lab_state |
| lab-send | handle_lab_send |
| lab-proposal-create | handle_lab_proposal_create |
| lab-proposal-decide | handle_lab_proposal_decide |
| reminder-create | handle_reminder_create |
| reminder-list | handle_reminder_list |
| reminder-cancel | handle_reminder_cancel |
| memory-user-add | handle_memory_user_add |
| memory-user-search | handle_memory_user_search |
| memory-user-list | handle_memory_user_list |
| memory-user-forget | handle_memory_user_forget |
| project-memory-get | handle_project_memory_get |
| project-memory-list | handle_project_memory_list |
| memory-galaxy-list | handle_memory_galaxy_list |
| conversation-history-list | handle_conversation_history_list |
| conversation-history-clear | handle_conversation_history_clear |

### Eventos enviados via `send_event` (amostra)

- state-change
- message
- metrics
- voice-level
- voice-output-audio
- supercerebro-change
- reminder-created
- reminder-fired
- routing-telemetry
- (outros vistos em todo o arquivo)

## Divergências Reais

### 1. Eventos invocados pelo frontend **sem handler** no backend

Esses eventos são chamados pelo frontend via `ipcRenderer.invoke` mas não possuem handler corrispondente no `handler_map` do backend:

| Evento | Linha no frontend |
|--------|-------------------|
| window-minimize | 85 |
| window-maximize | 86 |
| window-close | 87 |

### 2. Handlers do backend **não invocados** pelo frontend

Estes handlers existem no backend mas não há chamada corrispondente no frontend (pode ser usado por outros clientes, como Telegram, ou ser órfão):

| Handler | Linha no backend |
|---------|------------------|
| action-confirm | 2839 |
| action-confirm-cancel | 2840 |
| soul-get | 2843 |
| (outros como `self-status` são usados? verificar) |

### 3. Eventos enviados pelo backend e escutados pelo frontend

Estes eventos são enviados pelo backend via `send_event` e possuem listener no frontend (consistente):

| Evento | Backend (send_event) | Frontend (ipcRenderer.on) |
|--------|----------------------|---------------------------|
| state-change | múltiplas linhas | linha 94 |
| message | múltiplas linhas | linha 99 |
| metrics | múltiplas linhas | linha 104 |
| voice-level | múltiplas linhas | linha 109 |
| voice-output-audio | múltiplas linhas | linha 118 |
| supercerebro-change | múltiplas linhas | linha 123 |
| reminder-created | múltiplas linhas | linha 128 |
| reminder-fired | múltiplas linhas | linha 133 |
| routing-telemetry | múltiplas linhas | linha 138 |

## Conclusão

- Três eventos críticos de controle de janela estão faltando no backend, o que pode causar falhas silenciosas quando o frontend tenta minimizar, maximizar ou fechar a janela.
- Alguns handlers do backend podem estar órfãos ou destinados a outros canais (ex: Telegram). Recomenda-se verificar uso antes de remover.
- A maioria dos contratos de voz, memória, ações, sistema e laboratório está consistente entre frontend e backend.

## Próximos passos sugeridos

1. Implementar handlers ausentes para `window-minimize`, `window-maximize`, `window-close` no backend.
2. Criar testes de aceitação que invoquem cada contrato via `ipcRenderer.invoke` e verifiquem a resposta ou efeito esperado.
3. Avaliar se os handlers do backend não usados pelo frontend (`action-confirm`, `soul-get`, etc.) são destinados a outros clientes ou podem ser removidos após confirmação de uso interno.