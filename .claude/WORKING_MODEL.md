# ZARA — Modelo de Trabalho (Claude Operating Model)

Este arquivo é estável. Só muda por decisão explícita do Alex.

## Delegação

- Uma tarefa → um dono. Um arquivo → um dono ativo por vez.
- Antes de delegar: definir quem possui cada arquivo da tarefa.
- Não sobre-delegar: mudança pequena → 1 worker. Integração grande → Lead +
  poucos workers especializados. KISS.
- Não paralelizar tarefas que mexem no mesmo arquivo, disputam a mesma janela,
  o mesmo browser, o mesmo foco, ou dependem do resultado uma da outra.
  Paralelo só para leitura/diagnóstico; escrita é sequencial quando as áreas
  se cruzam (regra já vigente em `governance.md`).

## Brief obrigatório

Toda tarefa delegada a um Lead/Worker leva:

```
TASK / OBJECTIVE / FILES / CONTEXT / DO NOT TOUCH / CONSTRAINTS
DEFINITION OF DONE / VALIDATION / OUTPUT REQUIRED
```

Sem prompt vago.

## O Chief não aceita "pronto" sem prova

Nunca aceitar só "done/fixed/works". Exigir evidência: diff, teste, screenshot,
processo verificado, build, resultado de runtime. Ver a escada de evidência em
`.claude/rules/evidence.md` — ela já define os níveis (SOURCE → TEST →
RUNTIME_AUTOMATED → PACKAGED_RUNTIME → PHYSICAL_BY_ALEX → VOICE_PHYSICAL) e
continua valendo por cima deste arquivo.

## Fluxo

```
Pedido do Alex → Chief interpreta → Missão → Leads → Tasks → Workers
→ Validação → Revisão do Lead → Revisão do Chief → Integração → Owner Summary
```

## Anti-loop

Se um worker repetir duas tentativas parecidas sem progresso: **parar**.
O Lead reduz escopo, muda estratégia, troca worker/modelo, pede revisão, ou
reverte a mudança ruim. Nunca deixar preso. (Reforça `governance.md`.)

## Timebox

- Trabalho normal: 10–15 min → progresso tangível esperado.
- 20–30 min sem resultado → intervenção do Lead.
- Não permitir investigação de horas sem output.

## Escolha de modelo

- Sonnet: execução normal, código, CSS, wiring, testes, refactor simples.
- Opus: arquitetura difícil, bug persistente, visual final, integração
  complexa, revisão difícil.
- Fable: só quando disponível e a tarefa exigir altíssima fidelidade/
  complexidade.
- Escolher o melhor modelo disponível para o papel; o Alex não escolhe modelo.

## UI — regra do MASTER

MASTER é fonte absoluta de verdade visual (URL em `ORG.md`). Fluxo: MASTER →
Electron real → mesma viewport → screenshot → diff → correção → screenshot →
validação. Copiar, não redesenhar, não "melhorar".

Tarefa visual grande vira várias tarefas pequenas, uma região por vez
(ex.: Core, depois Platform, depois Dock, depois Header). Nunca um prompt
gigante para um worker visual de uma vez.

## Testes — ordem de leitura antes de auditar

Antes de qualquer auditoria grande, ler primeiro (nessa ordem):
`ZARA_AGENT_START_HERE.md` → `.zara-tests/latest/ZARA_STATE.md` →
`.zara-tests/latest/ZARA_CAPABILITIES.json` →
`.zara-tests/latest/ZARA_TEST_REPORT.md`.

Comparar `Commit` do `ZARA_STATE.md` com `git rev-parse HEAD`. Se bater e nada
relevante mudou: **não** re-auditar tudo, **não** rodar suíte completa à toa —
o `ZARA_STATE.md` já é a resposta.

Isto é o mesmo protocolo de `.claude/rules/test-run-policy.md` — este arquivo
não o substitui, só o cita como passo 1 do boot.

## Validação incremental

- Mudança pequena → teste impactado (`tools/zara_validate.py`, incremental).
- Mudança de frontend → typecheck/build/render.
- Mudança de voz → suíte de voz.
- Mudança de router/model_router → testes de router/tool.
- Suíte completa (FULL) só quando necessário — nunca em paralelo com outra
  suíte completa (regra dura de `test-run-policy.md`, mantida sem exceção).

## Silêncio operacional

Durante execução normal: não narrar ("agora vou...", "encontrei...",
"estou analisando..."). Trabalhar. Falar com o Alex só em:

- `CHECKPOINT` — ponto de controle relevante no meio de tarefa longa
- `BLOCKED` — parou e precisa de decisão do Owner
- `FINAL` — tarefa terminada
- `OWNER SUMMARY` — formato abaixo

```
OWNER SUMMARY
FEITO
- ...
VALIDADO
- ...
PENDENTE
- ...
OWNER REQUIRED
- ...
```

Isto formaliza o que já está em `CLAUDE.md` (SHORT MODE) — mesmo espírito,
vocabulário de status um pouco mais explícito para tarefas longas/delegadas.

## Owner Rest Mode

Quando o Alex disser que vai dormir, trabalhar em outra coisa ou sair: entrar
em modo de continuar sozinho tarefas seguras, reversíveis e testáveis, sem
interromper por coisas técnicas comuns. Relatório só de novidades quando ele
voltar. (Já é a prática registrada em memória — "modo sono do Alex" — este
arquivo só formaliza.)

## Owner Required — quando interromper de verdade

Só interromper o Alex por: risco de perda de dado, ação destrutiva, segurança
crítica, secrets, pagamento, publicação externa, decisão de produto que não dá
para inferir, hardware ao vivo perigoso. Todo o resto se resolve internamente.

Isto é mais permissivo que a política padrão do Claude Code para ações
irreversíveis/visíveis a terceiros (push, publicar, deletar) — aquela política
de confirmação explícita **continua valendo por cima** deste arquivo; "Owner
Required" aqui é sobre quando *interromper o Alex tecnicamente*, não uma
licença para pular a confirmação de ações sensíveis já definida no nível do
sistema.

## Git safety

Nunca `git reset --hard`, `git clean -fd`, `git push --force` casualmente.
Checkpoint (commit) antes de mudança grande. Nunca destruir trabalho
desconhecido. (Reforça `governance.md`, que já lista o conjunto completo de
operações proibidas sem autorização nomeada.)

Com autorização explícita do Alex em 2026-09-25, cada bloco relevante de
progresso validado da ZARA deve terminar com checkpoint Git e `push` normal da
branch de trabalho para `origin`, mantendo o GitHub como backup atualizado.
Antes do commit, revisar o staged diff e excluir secrets, bancos/perfis locais,
caches, builds/binários e outros artefatos de runtime. Nunca usar force-push.

## Fonte única de verdade

Uma interface oficial, um código ativo, um estado oficial (`ZARA_STATE.md`),
um sistema de testes. Não trabalhar com múltiplos "candidatos" — já é a regra
vigente em `.claude/rules/build-release.md`.

Na árvore `frontend/` deve permanecer somente o build apontado por
`ZARA_ACTIVE_BUILD.json`. Qualquer build anterior é preservado em
`_quarentena/` com manifesto; não é excluído diretamente.

## ZARA Lab visível — regra de execução real

- Missão real dos agentes começa no **Lab canônico visível**, nunca em harness
  isolado usado como substituto do produto.
- Para iniciar trabalho autônomo fora do campo de texto da UI, usar
  `python tools/zara_lab_visible_mission.py "<objetivo>"`.
- O launcher só aceita o diretório real `%LOCALAPPDATA%\ZARA3`, exige o build
  indicado por `ZARA_ACTIVE_BUILD.json` aberto e persiste no mesmo
  `zara_lab_v1.db` que a tela consulta.
- Alex precisa conseguir abrir a mesma `session_id` e acompanhar mensagens,
  tarefas, runs, participantes e artefatos. Sem essa observabilidade, a missão
  não vale como prova de autonomia real.
- Testes isolados podem proteger código contra regressão, mas nunca fecham um
  gate de produto nem substituem a missão visível no app.
