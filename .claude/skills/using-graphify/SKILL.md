---
name: using-graphify
description: Usa o snapshot de grafo do Graphify para mapeamento cross-file e análise de impacto na ZARA antes de grep amplo, mantendo saída compacta e tratando o grafo como evidência de navegação e nunca como prova de runtime; use em perguntas amplas de "quem chama o quê" e "o que quebra se eu mudar isto".
---

# Uso do Graphify

## Quando usar

- Pergunta ampla de estrutura: "quem chama `_try_pc_intent`?", "onde nasce a resposta final?",
  "o que depende de `action_registry`?".
- Análise de impacto antes de alterar uma função tocada por muitos caminhos.
- Mapeamento de área desconhecida do repositório, antes de decidir onde ler.
- **Não** use quando a tarefa já nomeia o arquivo exato — nesse caso, leia o arquivo e pronto.

## Fluxo obrigatório

1. **Verifique a existência do grafo antes de qualquer coisa.** Caminho canônico (verificado em
   2026-08-13, gerado do source real deste repositório):
   `C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002/graphify-out/graph.json`
   Confirme que o arquivo existe e anote seu timestamp.
   Se não existir, diga isso, não invente conteúdo, e caia para busca direta no repositório.
   O snapshot antigo `C:/Users/alexp/ZARA-GRAPHIFY-SNAPSHOT/graphify-out/graph.json` é uma cópia
   congelada de 2026-08-11 e **não** é mais a fonte; não apagar (dado protegido), não usar.
2. **Cheque a idade do snapshot.** Grafo mais velho que o último commit relevante descreve um
   passado. Rotule como possivelmente defasado e confirme achados lendo o arquivo real.
3. **Graphify primeiro, grep depois**, para perguntas amplas. O grafo reduz o espaço de busca;
   evita varredura cega em `core/ipc_handlers.py` (~2700 linhas) e em `core/actions/*.py`.
4. **Formule a consulta como pergunta de grafo**: chamadores, chamados, alcançabilidade, ou
   componentes que tocam um símbolo. Não peça "tudo sobre X".
5. **Confirme cada nó relevante lendo o source.** O grafo aponta onde olhar; a leitura decide.
6. **Mantenha a saída compacta.** Retorne no máximo os arquivos e símbolos que importam para a
   decisão, com caminho absoluto. Nunca despeje o grafo inteiro nem listas longas de nós.
7. **Feche com a lista de impacto:** arquivos que precisam mudar, arquivos que só precisam ser
   lidos, e caminhos de runtime que precisarão de teste físico.

## Comandos (binário: `C:/Users/alexp/.local/bin/graphify.exe`, versão 0.9.39)

Rodar sempre a partir da raiz do projeto. O grafo default é `graphify-out/graph.json`.

```
graphify query "quem chama _try_pc_intent" --budget 1500
graphify affected "_speak_response" --depth 2
graphify path "handle_send_message" "execute_action"
graphify explain "PcVoiceIntentDetector"
graphify god-nodes --top 10
graphify update .            # re-extrai só o que mudou, sem LLM, sem custo de API
```

Também existe servidor MCP registrado em `.mcp.json` (`graphify-mcp.exe`), apontando para o
mesmo `graph.json`. As ferramentas MCP e a CLI leem o mesmo arquivo — não são fontes distintas.

**Atualizar o grafo depois de mudar código é obrigatório antes de confiar nele.**
`graphify update .` é barato (AST local). Nunca rodar `label`/`cluster-only` com LLM sem Alex
pedir: 138 comunidades = chamada de modelo paga.

## Regras de evidência

- Grafo de source é **evidência de navegação**, nível `SOURCE`. Nunca é prova de runtime.
- "O grafo diz que A chama B" não significa que esse caminho executa em produção: pode estar atrás
  de um gate, de um try/except, ou de um branch morto. Só o trace `[VOICE_TRACE]` no runtime
  empacotado prova execução.
- Rotule explicitamente: `SNAPSHOT_VERIFICADO: SIM/NÃO`, com timestamp quando sim.
- Achado vindo só do grafo, sem leitura do arquivo, é `WHAT_IS_INFERRED`, não `WHAT_IS_PROVEN`.
- Se grafo e leitura discordarem, a leitura do arquivo vence e o grafo é marcado como defasado.

## O que NUNCA fazer

- Nunca afirmar que o snapshot existe sem ter verificado nesta sessão.
- Nunca tratar o grafo como prova de que uma feature funciona.
- Nunca usar o Graphify para justificar edição sem antes ler o arquivo alvo.
- Nunca despejar o `graph.json` ou grandes trechos dele no contexto — mata o orçamento de leitura.
- Nunca regenerar, mover ou apagar o snapshot: é dado protegido pelo CLAUDE.md.
- Nunca substituir a análise de impacto real por "o grafo não mostrou nada, então não afeta nada".
