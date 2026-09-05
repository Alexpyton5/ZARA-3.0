---
name: rotear-modelo-por-custo
description: Escolhe qual modelo executa cada pedaço do trabalho na ZARA — delega tarefa mecânica a um modelo barato via subagente e reserva o modelo forte para raciocínio causal e auditoria de evidência. Use SEMPRE antes de delegar qualquer coisa a um subagente, e sempre que uma tarefa for previsível, repetitiva ou de puro levantamento de fatos.
---

# Roteamento de modelo por custo

Alex paga R$110/mês e isso pesa. Gastar modelo caro em tarefa mecânica é desperdício
direto do dinheiro dele.

## O limite real (não fingir que não existe)

O modelo da conversa principal **não é trocável no meio da conversa**. Ele é escolhido por
Alex na interface. O que É trocável é o modelo de cada **subagente**.

Portanto o roteamento acontece por delegação, não por auto-troca:

```
conversa principal (modelo forte, escolhido por Alex)
   └── delega -> subagente com model: haiku   (mecânico)
   └── delega -> subagente com model: sonnet  (levantamento estruturado)
   └── mantém no principal                    (raciocínio causal, decisão)
```

## Tabela de decisão

| Natureza da tarefa | Modelo | Exemplos reais na ZARA |
|---|---|---|
| Mecânica, resultado verificável, sem julgamento | **haiku** | copiar arquivo, extrair lista de nomes de função, formatar relatório, coletar hashes/datas, gerar boilerplate |
| Levantamento estruturado, texto derivado de fatos dados | **sonnet** | mapear arquitetura, escrever SKILL.md a partir de instrução densa, auditar identidade de build, resumir log |
| Raciocínio causal, hipótese, decisão irreversível, auditoria | **opus** | achar a causa de uma regressão, decidir o menor delta, revisar evidência e caçar falso sucesso, aprovar patch |

## Regra do teto

Se errar custa **um retrabalho barato**, use o modelo barato.
Se errar custa **um build, o sono do Alex ou uma regressão em produção**, use o forte.

Auditoria nunca é barata. Um revisor fraco devolve elogio, não erro. Foi um revisor forte
que derrubou a conclusão errada de 2026-08-12 e achou o wake gate duplo.

## Subagentes já configurados

```
zara-readonly-architect        sonnet   mapear, rastrear registro, comparar doc x source
zara-build-auditor             sonnet   identidade de build, toolchain, hashes
zara-regression-investigator   opus     causa raiz de uma falha física
zara-evidence-reviewer         opus     auditar relatório, rejeitar promoção de evidência
```

## Como delegar barato de verdade

O custo de um subagente é dominado pelo que ele precisa **redescobrir**. Um subagente frio
gasta metade do orçamento só se localizando.

Portanto, ao delegar:

1. entregue os fatos já verificados no próprio prompt (caminhos, linhas, nomes de função)
2. delimite os arquivos permitidos
3. peça saída curta e estruturada, não relatório
4. nunca peça "analise o projeto" — peça uma pergunta respondível

Um prompt denso para haiku vale mais que um prompt vago para opus.

## Quando NÃO delegar

- a tarefa cabe em 1 ou 2 chamadas de ferramenta: fazer direto sai mais barato
- a resposta já está na memória ou num relatório em `.zara-dev/reports/`
- exige decidir se escreve em produção: isso não delega, é do Mentor

## O que NUNCA fazer

- usar modelo forte para copiar, listar, formatar ou contar
- usar modelo fraco para auditar evidência ou decidir causa raiz
- delegar sem `FILES_ALLOWED`
- rodar subagentes em paralelo escrevendo nos mesmos arquivos
- fingir que consigo trocar o modelo da conversa principal sozinho
