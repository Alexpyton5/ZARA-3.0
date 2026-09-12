---
name: auditing-action-truth
description: Audita quando a ZARA diz "pronto", "abri" ou "diminuí" mas o Windows não mudou, rastreando a origem da string final de resposta até o resultado real do executor e exigindo ação despachada, resultado, postcondição e resposta derivada do observado; use em qualquer suspeita de falsa confirmação.
---

# Auditoria de verdade da ação

## Quando usar

- Alex relata: "ela disse que fez, mas não fez".
- A resposta usa linguagem de sucesso ("abri", "diminuí", "ativei", "minimizei", "pronto")
  e não há postcondição verificada.
- Ao revisar qualquer código novo que produza texto de confirmação.
- Antes de aceitar como concluída qualquer ação de controle de PC.

## Fluxo obrigatório

1. **Reproduza** o comando e capture a string final exata que a ZARA falou/escreveu.
2. **Rastreie a origem dessa string.** Ela veio de onde? Três origens possíveis:
   (a) resultado real do executor; (b) texto fixo no dispatcher; (c) saída de modelo de linguagem.
   Só (a) é aceitável como confirmação de ação.
3. **Verifique o contrato de verdade completo:**
   `COMANDO → DISPATCH → EXECUÇÃO → POSTCONDIÇÃO → RESPOSTA`.
   Nunca `COMANDO → DISPATCH → "pronto"`. Cada seta precisa de um artefato observável.
4. **Ação despachada.** Confirme no trace `[VOICE_TRACE] stage=ACTION_DISPATCH` que a ação certa
   saiu do dispatcher em `core/ipc_handlers.py`, com os parâmetros certos.
5. **Resultado do executor.** Vá até `core/action_registry.py` e o módulo em `core/actions/*.py`.
   O executor devolveu sucesso ou exceção engolida? Exceção silenciosa vira "pronto" mentiroso.
6. **Postcondição.** Releia o estado real do Windows (volume atual, brilho atual, janela em foco,
   arquivo existente). Sem readback, a confirmação é inferência — rotule como inferência.
7. **Resposta derivada.** A string final deve ser construída a partir do resultado observado.
   Em `core/ipc_handlers.py`, o retorno de `_try_pc_intent` deve vir de
   `getattr(result, "output")`, não de texto fixo. Se estiver hardcoded, é o bug.
8. **Se a verificação falhar, a ZARA deve dizer que falhou.** Corrigir a mensagem faz parte do
   conserto, não é opcional.

## Regras de evidência

- Ação despachada ≠ ação bem-sucedida. String de resposta ≠ prova de que o Windows mudou.
- **Padrão perigoso, procure ativamente:** uma resposta de modelo de linguagem sendo falada como se
  fosse prova de ação. O LLM produz frases plausíveis de sucesso sem nenhum executor ter rodado.
  Se a cadeia de intents caiu no fallback LLM, nada foi executado — mesmo que soe perfeito.
- Segundo padrão perigoso: texto de sucesso literal no dispatcher, independente do `result`.
- Registre o veredito com três campos: `WHAT_IS_PROVEN` (postcondição lida),
  `WHAT_IS_INFERRED` (executor retornou ok mas sem readback), `WHAT_IS_UNKNOWN`.
- Só `PHYSICAL_BY_ALEX` ou readback de estado fecha uma ação de controle de PC.

## O que NUNCA fazer

- Nunca aceitar texto de confirmação como evidência de execução.
- Nunca deixar `except` engolir falha de executor e ainda responder sucesso.
- Nunca deixar o fallback LLM responder por uma ação local determinística — isso é o que produz
  a mentira mais convincente. Reforce o guard `_looks_like_unhandled_local_action`.
- Nunca escrever linguagem de sucesso em texto fixo dentro do dispatcher.
- Nunca fechar a auditoria sem apontar exatamente qual linha gerou a string mentirosa.
- Nunca "suavizar" a resposta de falha. Se falhou, a ZARA diz que falhou.
