# Regras de governança — ZARA 3.0

## Por que estas regras existem

O projeto entrou num loop real, observado por semanas:
conserta volume → muda roteamento → brilho regride → corrige brilho → YouTube regride →
rebuild → voz diverge → corrige voz → mexe em ambiente/lifecycle → novo candidato →
comportamento físico pior que antes.

A causa não foi falta de código. Foi **largura de escopo por sessão**. Sessões longas e
autônomas misturaram reparo de ambiente, mutação de dependências, revisão de arquitetura,
correções de source, mudanças de roteamento, build, empacotamento, testes de runtime e
roadmap. Com isso, quando algo quebrava, era impossível atribuir a causa.

Regra derivada: **atribuição vale mais que velocidade**.

## Limites de escopo por tarefa

Uma tarefa = um objetivo = um delta causal.

Proibido numa mesma tarefa:
- recuperação de regressão + feature nova
- correção de source + upgrade de dependência
- correção de source + mudança de build/empacotamento
- redesenho de arquitetura + qualquer outra coisa

Se a tarefa precisar de duas dessas, ela vira duas tarefas com relatório entre elas.

## Protocolo de tarefa

```
TASK_ID:
GOAL:
SCOPE:
FILES_ALLOWED:
FILES_FORBIDDEN:
BASELINE:
EXPECTED_DELTA:
TESTS:
PACKAGED_TEST:
PHYSICAL_TEST:
ROLLBACK:
STOP_CONDITION:
```

`FILES_ALLOWED` é uma lista fechada. Se durante a execução ficar claro que o fix exige um
arquivo fora da lista, **parar e reportar**, não ampliar sozinho.

## Anti-loop

Por hipótese: uma abordagem principal + no máximo duas correções pequenas + reteste.
Se continuar falhando:

1. marcar `BLOCKED`
2. registrar a evidência coletada
3. registrar o que foi descartado e por quê
4. mudar para outra área segura de diagnóstico

Nunca repetir a mesma abordagem esperando resultado diferente. Isso é o que queimou créditos.

## Um escritor por área

Nunca dois agentes editando os mesmos arquivos. Subagentes servem para raciocínio paralelo
read-only (mapear, rastrear, auditar), não para mutação paralela.

## Sem sessão noturna ampla em produção

Autonomia ampla é aceitável para: leitura, mapeamento, busca, Graphify, análise de log,
planejamento de teste, diagnóstico, e **produzir uma proposta de patch**.

Escrita em produção exige: tarefa delimitada + ponto de rollback conhecido + autorização
explícita de Alex para aquela tarefa específica.

## Operações git proibidas sem autorização nomeada

- `git reset --hard`
- `git clean -fd`
- `git checkout -- .` amplo
- `git restore .` amplo
- `git stash drop` / stash destrutivo
- rebase/rewrite de branch com trabalho não publicado
- merge com testes conhecidos falhando

Antes de qualquer operação git: `git status`, `git stash list`, e verificar resíduos como
`.git/AUTO_MERGE`, `.git/MERGE_HEAD`, `.git/ORIG_HEAD`.

## Dados protegidos

`.zara-dev/` (protocolo, tarefas, relatórios, rollbacks), Context Sync, Operational Context,
Project Memory, User Memory, Conversation History, lembretes, dados do LAB, snapshot Graphify,
trabalho sujo não commitado, configuração local legítima, `config/api_keys*.json`.

Não resetar, limpar, restaurar ou apagar nenhum desses por suposição.

## Custo e tempo de Alex

Alex já perdeu semanas e créditos de duas contas neste loop.
O Mentor protege tempo, sono e créditos. Isso significa:

- parar cedo quando a evidência não fecha
- dizer "não sei" em vez de tentar mais uma vez no escuro
- pedir 1–3 testes físicos, nunca 90
- não gerar relatório longo quando um resultado curto basta
