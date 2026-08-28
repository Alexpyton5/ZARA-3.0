# Auditoria de Proatividade e Memória da ZARA

## Resumo
Foi realizada inspeção dos componentes de memória (aprendizado, histórico de conversas, lembretes) e de proatividade (Initiative Engine) na ZARA 3.0 CLEAN 002. Não foram feitas alterações nos arquivos; apenas leitura e execução de testes.

## Memória

### Aprendizado (`core/aprendizado.py`)
- Implementa registro de ações e reações do usuário (elogio/reclamação) dentro de janela de 90 segundos.
- Lições são salvas em tabela `licoes` com contagem de acertos e erros por forma do pedido e ação.
- Método `licao_para` retorna lição se houver mais erros que acertos.
- Testes unitários (`tests/test_aprendizado.py`) passaram (21/21).

### Histórico de Conversas (`core/conversation_history.py`)
- Armazena mensagens locais com limite de 500 mensagens e retenção de 180 dias.
- Métodos `append` e `list_recent` garantem poda automática.
- Não há evidência de uso insuficiente ou excessivo na inspeção rápida.

### Lembretes (`core/reminder_engine.py`)
- Persistência comprovada com readback obrigatório após criação (evita falso sucesso de persistência).
- Estados: SCHEDULED → FIRING → FIRED | CANCELLED | MISSED.
- Janela de overdue de 1 hora (OVERDUE_WINDOW_SECONDS = 3600).
- Rotina de limpeza de resolvidos após 7 dias.

## Proatividade

### Initiative Engine (`core/initiative/engine.py`)
- Loop background que verifica condições silenciosas, taxa de interrupção, utilidade e histórico.
- Placeholder para utilidade (retorna 0.5) e conselho estático.
- Não há integração evidente com o IPC handlers (nenhuma referência a `InitiativeEngine` em `core/ipc_handlers.py`).
- Documentação em `docs/ENGENHARIA-REVERSA-MARK-LI.md` menciona `proactive_audio` e `affective_dialog` como recursos do Gemini Live que a ZARA deve replicar.

## Falso Sucesso
- Em `core/ipc_handlers.py` linha 109 há comentário sobre resposta falsa: `"pronto, diminui o brilho" sem nada ter acontecido no Windows.` (apontado como exemplo de falso sucesso a evitar).
- Nenhuma ocorrência real de retorno de sucesso sem verificação foi encontrada na inspeção rápida.

## Riscos e Lacunas
1. **Falta de integração do Initiative Engine**: O motor de proatividade está implementado, mas não está sendo chamado pelo fluxo principal de IPC.
2. **UtilidadePlaceholder**: O método `_get_utility` retorna valor fixo; deveria usar contexto real (volume, brilho, lembretes, etc.).
3. **Histórico de conselhos limitado**: Baseado apenas em hash de texto; poderia se beneficiar de contextualização temporal mais sofisticada.
4. **Memória de longo prazo**: O aprendizado é baseado em forma do pedido; não há evidência de integração com memória semântica ou de projetos (embora existam métodos `absorver_do_projeto` e `onde_estamos` em aprendizado.py).

## Próximos Sugeridos
- Integrar o `InitiativeEngine` no `ipc_handlers.py` (por exemplo, iniciar no construtor e chamar verificações em pontos de idle).
- Substituir o placeholder de utilidade por uma função que avalie o contexto operacional recente.
- Considerar tornar o motor de proatividade configurável via flags (como no Mark-LI).
- Verificar se os testes de iniciativa existem e, se não, criar testes unitários para o engine.