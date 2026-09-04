# Regras de evidência — ZARA 3.0

## Níveis (nunca colapsar, nunca promover)

| Nível | O que prova | O que NÃO prova |
|---|---|---|
| `SOURCE` | o código existe e parece logicamente conectado | que executa |
| `TEST` | teste unitário/integração passou | que o runtime de produção funciona |
| `RUNTIME_AUTOMATED` | ação real executada automaticamente com postcondição observada | que o EXE que Alex usa funciona |
| `PACKAGED_RUNTIME` | o build empacotado executou a ação e a postcondição foi observada | validação humana |
| `PHYSICAL_BY_ALEX` | Alex viu a feature funcionar no app | que funciona por voz |
| `VOICE_PHYSICAL` | Alex falou o comando e viu a execução real | — |

Regra dura: **TEXT PASS + VOICE FAIL = PRODUTO FALHOU** para capacidade voice-first.
Texto serve como fallback, debug, acessibilidade e uso silencioso. Não substitui prontidão de voz.

## Conversões proibidas

- "o código está lá" → "funciona"
- "62 testes passaram" → "o app funciona"
- "o script automatizado executou" → "o EXE do Alex executa"
- "a ação foi despachada" → "a ação teve sucesso"
- "a resposta disse que fez" → "o Windows mudou"
- "passou uma vez" → "está estável"

## Linguagem de sucesso é regulada

Só usar "feito", "abri", "pesquisei", "diminuí", "aumentei", "ativei", "desativei",
"minimizei", "maximizei", "movi", "copiei", "criei" quando existe resultado real de
executor, e de preferência readback/postcondição.

Se a verificação falhar, a resposta diz que falhou. Isso vale para a ZARA respondendo ao
Alex **e** para o Mentor respondendo ao Alex.

## Rotulagem obrigatória em todo relatório

```
WHAT_IS_PROVEN:
WHAT_IS_INFERRED:
WHAT_IS_UNKNOWN:
```

`WHAT_IS_UNKNOWN` vazio é sinal de relatório desonesto. Sempre há algo não verificado.

## KNOWN_BROKEN é permanente até prova em contrário

Um item quebrado conhecido não desaparece de um relatório porque a tarefa mudou de assunto.
Ele só sai da lista quando existe evidência do nível apropriado de que foi corrigido.

Relatório sem seção `KNOWN_BROKEN` não fecha tarefa.

## Falha de teste nunca é escondida

Testes que falharam são reportados com nome, quantidade e motivo. Não é aceitável relatar
"maioria passou". Não é aceitável desabilitar/pular teste para fechar tarefa.

## Evidência de terceiros

Relatório de outro agente (Codex, Hermes, subagente) é **alegação**, não evidência, até que
o caminho citado seja verificado. Ao herdar um relatório antigo, rebaixar tudo para
`INFERRED` e reverificar o que importa.
