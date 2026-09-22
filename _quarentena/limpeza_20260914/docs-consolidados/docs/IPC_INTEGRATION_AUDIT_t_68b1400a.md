# Auditoria de Integração IPC Frontend-Backend (t_68b1400a)

## Resumo
Mapeados todos os invocadores e listeners de IPC entre o frontend (renderer/preload.ts) e o backend (main.ts). Verificado correspondência one-to-one para invocações e detalhada divergência em um evento de escuta.

## Invocações (frontend → backend via ipcRenderer.invoke)
| Invocação (preload.ts) | Handler (main.ts) | Status |
|------------------------|-------------------|--------|
| engine.change          | engine-change     | OK |
| engine.list            | engine-list       | OK |
| supercerebro.toggle    | supercerebro-toggle | OK |
| supercerebro.status    | supercerebro-status | OK |
| message.send           | send-message      | OK |
| message.interrupt      | interrupt         | OK |
| conversationHistory.list | conversation-history-list | OK |
| conversationHistory.clear | conversation-history-clear | OK |
| memoryGalaxy.list      | memory-galaxy-list | OK |
| action.execute         | action-execute    | OK |
| action.list            | action-list       | OK |
| system.metrics         | system-metrics    | OK |
| system.info            | system-info       | OK |
| voice.start            | voice-start       | OK |
| voice.stop             | voice-stop        | OK |
| voice.status           | voice-status      | OK |
| voice.mute             | voice-mute        | OK |
| config.get             | config-get        | OK |
| config.set             | config-set        | OK |
| lab.state              | lab-state         | OK |
| lab.send               | lab-send          | OK |
| lab.proposal.create    | lab-proposal-create | OK |
| lab.proposal.decide    | lab-proposal-decide | OK |
| reminder.create        | reminder-create   | OK |
| reminder.list          | reminder-list     | OK |
| reminder.cancel        | reminder-cancel   | OK |
| voice.sendMicChunk     | (envia via ipcRenderer.send, não invoke) | OK (envio unidirecional) |
| window.minimize        | window-minimize   | OK |
| window.maximize        | window-maximize   | OK |
| window.close           | window-close      | OK |

## Event Listeners (frontend ← backend via ipcRenderer.on)
| Listener (preload.ts) | Emissão (main.ts) | Status |
|-----------------------|-------------------|--------|
| state-change          | webContents.send('state-change') | OK |
| message               | webContents.send('message') | OK |
| metrics               | webContents.send('metrics') | OK |
| voice-level           | webContents.send('voice-level') | OK |
| voice-output-audio    | webContents.send('voice-output-audio') | OK |
| supercerebro-change   | webContents.send('supercerebro-change') | OK |
| reminder-created      | webContents.send('reminder-created') | OK |
| reminder-fired        | webContents.send('reminder-fired') | OK |
| routing-telemetry     | **Nenhuma emissão encontrada** | **DIVERGÊNCIA** |

## Evidências
- **frontend/src/preload.ts** linhas 138-139:
  ```
  ipcRenderer.on('routing-telemetry', handler)
  return () => ipcRenderer.off('routing-telemetry', handler)
  ```
- Busca por `routing-telemetry` em `frontend/src/main.ts` retorna zero ocorrências de `ipcMain.handle` ou `webContents.send('routing-telemetry', ...)`.
- Todos os outros listeners têm emissoes correspondentes (exemplos acima na tabela).

## Conclusão
A integração IPC está consistente exceto pelo evento `routing-telemetry`, que é ouvido no frontend mas nunca disparado pelo backend. Recomenda-se implementar a emissão desse evento no backend (por exemplo, ao receber decisões de roteamento do modelo) ou remover o listener caso o evento não seja mais utilizado.

## Próximos passos sugeridos
1. Decidir se o evento `routing-telemetry` é necessário.
2. Se necessário, adicionar emissão no backend em pontos relevantes de roteamento.
3. Caso contrário, remover o listener do frontend para evitar escuta inútil.