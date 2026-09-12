# Skills do Claude — Regras de Operação

Sempre que Alex digitar um dos comandos abaixo no terminal, o comportamento padrão
é **suspenso** e eu ajo estritamente conforme a skill solicitada, até que a etapa
termine ou Alex mande parar.

---

## 1. `/grillme`

**Ação:** Iniciar uma entrevista detalhada sobre a funcionalidade que Alex quer construir.

**Regra:**
- Fazer perguntas **em rodadas** — uma etapa do projeto por vez, nunca um questionário inteiro de uma vez.
- Explorar casos extremos, lógicas de erro e regras de negócio.
- **NÃO escrever nenhum código nesta etapa.**
- Continuar perguntando até não restar nenhuma lacuna de contexto.

---

## 2. `/spec`

**Ação:** Ler o histórico da entrevista e gerar um arquivo de especificação do projeto.

**Regra:**
- O documento contém todas as regras de negócio e decisões arquiteturais.
- **É ESTRITAMENTE PROIBIDO incluir qualquer trecho de código neste documento.**
- Incluir também as ideias que foram **descartadas/recusadas** durante o `/grillme`, e o motivo.

---

## 3. `/tickets`

**Ação:** Ler o documento de especificação gerado e quebrar o projeto em tarefas isoladas (Tickets).

**Regra:**
- Dividir por **funcionalidades completas e testáveis** (Vertical Slice), **não** por camadas de infraestrutura.
- Cada ticket, ao ser concluído, deve resultar em algo que Alex possa **testar na prática**.

---

## 4. `/implement [nome do ticket]`

**Ação:** Iniciar a construção de um ticket específico.

**Regra:**
- **Antes** de escrever o código principal, escrever os critérios de sucesso e os testes (TDD).
- O código desenvolvido em seguida tem o **único objetivo** de passar nesses critérios, com a melhor arquitetura possível.

---

## 5. `/review`

**Ação:** Atuar como revisor de código Sênior imparcial (baseado no livro *Refactoring*, de Martin Fowler).

**Regra:**
- Ler o documento de especificação **e** o código implementado.
- Apontar falhas arquiteturais.
- Verificar duplicação de responsabilidades e evitar *shotgun surgery*.
- Garantir que o código reflete fielmente o documento de Spec.
- Ser crítico e sugerir as mudanças.

---

## Observações de aplicação

- Estes cinco comandos **convivem** com as regras de `CLAUDE.md` e `.claude/rules/`.
  Onde houver conflito sobre escrita em produção, evidência ou teste físico, as
  regras do projeto continuam valendo — elas existem por causa de prejuízo real.
- `/implement` é o único que escreve em produção. Continua sujeito a: tarefa
  delimitada, um escritor por área, ponto de rollback e teste físico.
- Alex é a autoridade final e pode suspender qualquer skill a qualquer momento.
