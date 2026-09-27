# Plano de ondas de melhoria da ZARA

## Sequência solicitada

1. Concluir as 50 tarefas atuais.
2. Após validação, criar uma onda com 2.000 candidatos.
3. Após validação dessa onda, criar a onda final com mais 2.000 candidatos.
4. Encerrar a grande missão após validar a segunda onda de 2.000, mantendo apenas correções necessárias e melhorias que surjam dos testes reais.

## Regra de qualidade

As ondas representam **backlogs de candidatos**, não milhares de alterações automáticas. Cada candidato precisa de objetivo, risco, arquivos-alvo, teste, evidência e rollback. Ideias repetidas, inseguras, inviáveis ou sem benefício mensurável serão descartadas.

## Critério para liberar a próxima onda

A onda atual só termina quando:

- o código estiver salvo;
- os testes focados e de regressão passarem;
- nenhuma regressão conhecida permanecer sem registro;
- a documentação estiver atualizada;
- o estado do build e das integrações estiver honesto;
- os itens que dependem de Windows real estiverem separados para teste físico.

## Limite operacional

A missão pode continuar enquanto houver sessão, recursos e ambiente disponíveis. Ela não pode garantir execução infinita depois que a sessão for encerrada. Quando houver bloqueio de permissão, volume, dependência ou validação física, o bloqueio será registrado em vez de ser mascarado.

## Ordem de prioridade

Controle Windows, voz, navegador, visão, memória, Lab, desempenho, segurança, estabilidade, interface e testes. A ZARA deve ganhar capacidade real, não apenas uma lista maior de ideias.
