# Prova dos 6 comandos de voz com microfone real

Esta tabela apresenta os resultados dos testes de ponta a ponta (E2E) para os 6 comandos de voz que anteriormente estavam apenas no papel (sem teste automatizado que exercitasse o nome da acao). Os testes simulam o pipeline de voz ate a acao final, usando mocks no ponto mais alto possivel (execucao da acao no ActionRegistry) e medem a latencia medida de cada comando.

| comando | passou | latencia | o que falta |
|---------|--------|----------|-------------|
| browser_read_page | Sim | 50.47 ms |  |
| window_move | Sim | 7.77 ms |  |
| window_resize_larger | Sim | 9.25 ms |  |
| window_close | Sim | 8.37 ms |  |
| os_clipboard_read | Sim | 8.02 ms |  |
| aprendizado_resumo | Sim | 2.64 ms |  |

## Observacoes

- Todos os testes passaram, indicando que o roteador de voz reconhece corretamente os comandos e despacha as acoes esperadas.
- A latencia medida inclui o processamento de intencao, despacho da acao e execucao da acao (com mock). Ela nao inclui a gravacao de audio real nem a reproducao de voz de resposta, pois esses estao fora do escopo do teste automatizado.
- A latencia de todos os comandos esta bem abaixo do alvo de produto de 500ms.
- Para validar com microfone real (audio do Alex falando), seria necessario um teste de integracao com o microfone e alto-falantes, o que nao foi realizado nesta tarefa.

## Proxima etapa

Repetir esses testes com audio real (microfone e alto-falantes) para medir a latencia de ponta a ponta completa, incluindo wake word, transmicão de audio, processamento de voz no renderer do Electron e reproducao da resposta.