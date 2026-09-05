---
name: auditing-roadmap-integrity
description: Audita o roadmap da ZARA antes de marcar item como feito, adiar, deduplicar ou substituir listas, distinguindo capacidade existente de prontidão física e empacotada e protegendo backlog WOW já registrado; use ao atualizar roadmap, declarar entrega ou receber uma lista nova de features.
---

# Integridade de roadmap

## Quando usar

- Antes de marcar qualquer item de roadmap como concluído.
- Ao receber uma lista nova de features e sentir vontade de substituir a antiga.
- Ao decidir se uma ideia é nova ou duplicata de algo já registrado.
- Ao reordenar prioridades ou adiar itens.

## Fluxo obrigatório

1. **Classifique o item em exatamente uma categoria:**
   - `CAPACIDADE_EXISTENTE` — o primitivo existe no source.
   - `PRONTIDÃO_FÍSICA` — Alex executou e o Windows mudou de verdade.
   - `PRONTIDÃO_EMPACOTADA` — funciona no EXE empacotado nomeado, não só em dev.
   - `BACKLOG_WOW` — desejo registrado, ainda não construído.
   - `FEATURE_ADIADA` — decidida e conscientemente empurrada, com motivo.
   - `IDEIA_NOVA` — ainda não avaliada.
2. **Aplique a regra dura: primitivo existir não é feature pronta.** Uma função em
   `core/actions/*.py` que ninguém alcança por voz não é uma feature entregue.
3. **Teste de dedupe antes de adicionar.** Procure o item no roadmap atual e em `.zara-dev/tasks/`.
   Marque explicitamente `DUPLICATA` ou `NET_NEW`. Nunca adicione sem essa checagem.
4. **Nunca substitua roadmap — faça merge.** Lista nova entra por adição e reclassificação;
   itens antigos só saem com decisão nomeada do Alex e motivo registrado.
5. **Preserve a tarefa `ZARA-CORUJAO-WOW-EXPANSION-003`**, status `SUSPENDED_FOR_P0_RECOVERY`,
   com seus **24 itens** intactos. Suspensa não é cancelada. Não reduza, não reescreva, não funda
   os 24 itens em resumos. Ela volta quando a Fase 1 fechar.
6. **Respeite a prioridade vigente (Alex, 2026-08-12).** Fase 1 antes de qualquer WOW novo:
   voz Kore real → latência mínima → microfone sem loop → voz que executa de verdade, inclusive
   comandos compostos.
7. **Emita o veredito por item:** categoria, evidência que sustenta, e o que falta para subir de
   categoria. "Falta empacotar e testar fisicamente" é um veredito válido e frequente.

## Regras de evidência

- Cada item marcado como feito precisa citar o nível de evidência que o sustenta:
  `SOURCE` → `TEST` → `RUNTIME_AUTOMATED` → `PACKAGED_RUNTIME` → `PHYSICAL_BY_ALEX` → `VOICE_PHYSICAL`.
- Item voice-first só é "feito" com `VOICE_PHYSICAL`. Texto passando e voz falhando = não feito.
- Feito com `PACKAGED_RUNTIME` mas sem `PHYSICAL_BY_ALEX` deve ser rotulado
  `PRONTO_PARA_TESTE_FÍSICO`, não `FEITO`.
- Registre o EXE que sustenta a afirmação (ver `validating-packaged-runtime`).
- Se não há evidência, escreva `NÃO_VERIFICADO`. Nunca deixe em branco e nunca chute otimista.

## O que NUNCA fazer

- Nunca marcar item como feito por ter lido o código que "deveria" fazer aquilo.
- Nunca apagar, truncar ou reescrever itens de backlog WOW já registrados.
- Nunca reduzir os 24 itens de `ZARA-CORUJAO-WOW-EXPANSION-003` nem alterar seu status sem Alex.
- Nunca sobrescrever um arquivo de roadmap com uma lista nova recebida no chat.
- Nunca inflar progresso agrupando itens ("controle de PC: feito") para esconder falhas por item.
- Nunca promover feature nova acima da Fase 1 sem decisão explícita do Alex.
