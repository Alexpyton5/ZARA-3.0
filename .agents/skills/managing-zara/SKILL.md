---
name: managing-zara
description: Coordena qualquer tarefa de engenharia da ZARA 3.0 aplicando modelo de autoridade, contrato de escopo TASK_ID, um escritor por área e taxonomia de evidência; use ao iniciar, delegar, revisar ou fechar qualquer trabalho no repositório ZARA, antes de tocar em qualquer arquivo.
---

# Coordenação de tarefas da ZARA

## Quando usar

- Ao receber qualquer pedido de engenharia na raiz `C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002`.
- Antes de abrir qualquer edição em `core/`, `memory/`, `frontend/src/`, `integrations/`, `tests/`.
- Ao delegar para subagentes ou ao consolidar relatório para Alex.
- Quando o pedido chega vago ("melhora a ZARA", "arruma isso", "continua").

## Fluxo obrigatório

1. **Autoridade.** Alex decide direção e pausa/cancela. Codex é Mentor: arquiteto, auditor
   de evidência, protetor contra loop de regressão. Otimize por resultado visível, não por volume.
2. **Recuse o vago.** Se o pedido não vira uma tarefa delimitada, devolva a pergunta antes de escrever.
3. **Escreva o contrato de tarefa** antes de qualquer edição:
   `TASK_ID / GOAL / SCOPE / FILES_ALLOWED / FILES_FORBIDDEN / BASELINE / EXPECTED_DELTA /
   TESTS / PACKAGED_TEST / PHYSICAL_TEST / ROLLBACK / STOP_CONDITION`.
4. **Um escritor por área.** Nenhum agente concorrente edita os mesmos arquivos. `core/ipc_handlers.py`
   é área crítica de escritor único.
5. **Um delta causal pequeno** → build → 1–3 testes físicos → aceitar ou reverter. Nunca misturar
   numa mesma tarefa recuperação + redesenho + upgrade de dependências + features novas.
6. **Anti-loop.** Uma hipótese principal, até duas correções pequenas. Travou duas vezes na mesma
   hipótese: marque `BLOCKED`, capture evidência, mude de área.
7. **Feche com o relatório obrigatório** do AGENTS.md. Sem `KNOWN_BROKEN` a tarefa não fecha.
8. **Cheque integridade de roadmap** antes de declarar item concluído (ver `auditing-roadmap-integrity`).

## Regras de evidência

- Taxonomia, nunca colapsada:
  `SOURCE` → `TEST` → `RUNTIME_AUTOMATED` → `PACKAGED_RUNTIME` → `PHYSICAL_BY_ALEX` → `VOICE_PHYSICAL`.
- Rotule toda afirmação com o nível que a sustenta. Se sabemos, prove. Se inferimos, rotule.
  Se não sabemos, diga que não sabemos.
- Verde na suíte não fecha tarefa. Empacote e peça o teste físico correspondente.
- **TEXT PASS + VOICE FAIL = PRODUTO FALHOU.** A ZARA é voice-first.
- Prioridade Fase 1 definida por Alex (2026-08-12), nesta ordem, antes de qualquer WOW novo:
  voz Kore real na saída → latência mínima → microfone sem loop com a própria voz →
  voz que entende e executa de verdade, inclusive comandos compostos.

## O que NUNCA fazer

- Nunca abrir sessão ampla e autônoma de escrita ("vou refatorar tudo enquanto você dorme").
- Nunca editar source sem baseline conhecida e ponto de rollback declarado.
- Nunca rodar `git reset --hard` cego, `git clean -fd`, `git checkout -- .` amplo,
  `git restore .` amplo, stash destrutivo ou upgrade amplo de dependências.
- Nunca apagar artefato desconhecido nem dado protegido: Context Sync, Operational Context,
  Project Memory, User Memory, Conversation History, lembretes, dados do LAB, snapshot do
  Graphify, trabalho sujo, config local legítima e `.zara-dev/` inteira.
- Nunca converter código-fonte em evidência de runtime, teste unitário em runtime empacotado,
  runtime automatizado em evidência física, ou ação despachada em ação bem-sucedida.
- Nunca dizer "pronto" sem postcondição observada (ver `auditing-action-truth`).
- Nunca deixar dois agentes escrevendo na mesma área ao mesmo tempo.
