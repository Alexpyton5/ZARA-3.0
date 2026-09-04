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

## Refinamento visual pixel-perfect (UI Director)

**2026-09-04 (correção do Alex).** Para toda missão de interface, análise,
execução e aprovação são três passos separados — nunca o mesmo agente fazendo
os três. Ver papéis em `ORG.md`.

**Modelo:**
- Opus 5 (ou o mais próximo disponível de raciocínio forte) → análise visual,
  brief, revisão/aprovação final, decisão de escalar.
- Sonnet (ou o mais próximo disponível de execução rápida) → implementação
  React/CSS/animação a partir do brief.
- Nunca usar Opus para padding, rename, import, tsc, build — isso é Sonnet.
- Escalar Sonnet → Opus quando: falhar 2x na mesma região, geometria/
  perspectiva/material complexo, ou o problema exigir julgamento e não só CSS.
  Desescalar de volta para Sonnet assim que Opus definir causa/estratégia.

**Loop por região:**
```
Pixel-Perfect Analyst (Opus) → brief
  → Frontend/Motion Executor (Sonnet) → implementa
  → screenshot Electron
  → Visual QA (Opus) → APPROVED ou REWORK
  → se REWORK: no máximo 2 ciclos parecidos, depois o UI Director muda estratégia
```

**Brief obrigatório do Analyst** (formato, entregue ao Executor):
```
UI BRIEF
REGION:
MASTER:
CURRENT:
TOP DIFFERENCES: (até 5)
CHANGE:
DO NOT TOUCH:
FILES:
VALIDATION:
DONE WHEN:
```

**Output do Executor:** `IMPLEMENTED / FILES / VALIDATION / SCREENSHOT` —
sem narrar raciocínio.

**Output do Visual QA:** `RESULT: APPROVED|REWORK / MAJOR DIFFERENCES (até 3) / NEXT` —
nunca relatório longo.

**Regras de execução:**
- Uma task toca preferencialmente uma região (ver ordem em `TASK_BOARD.md`,
  série UI-00x). Não mexer em duas regiões não relacionadas na mesma task.
- Global composition (proporção, eixo central, colunas) é avaliada **antes**
  de refinar detalhe fino de qualquer região.
- Viewport fixo entre MASTER e Electron (mesma resolução, mesmo aspect
  ratio, zoom 100%) — registrar o viewport usado. Verdade é sempre o
  **Electron real**, nunca a viewport do browser do MASTER redimensionada.
- Screenshots de QA vão em `.zara-tests/ui/` (ou equivalente já existente) —
  nunca na raiz do repo.
- Pixel-perfect não pode regredir funcionalidade (voz, Core states, battery,
  telemetry, botões, IPC). Depois de mudança relevante, rodar só o teste
  impactado — nunca suíte completa por causa de CSS/padding.
- Não afirmar "100% pixel-perfect" sem prova. Usar `PIXEL-PERFECT PASS
  COMPLETE` + diferenças residuais, se houver.
- One file → one owner: Opus normalmente não edita arquivo; Sonnet é dono da
  implementação.

**Silêncio e continuidade:** aplica-se o "Silêncio operacional" e "Owner Rest
Mode" já definidos acima — região aprovada e próxima região segura seguem
automaticamente, sem perguntar "quer que eu continue?". Alex só recebe
`CHECKPOINT`/`BLOCKED`/`FINAL`, nunca a conversa interna entre Analyst,
Executor e QA.

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

## Fonte única de verdade

Uma interface oficial, um código ativo, um estado oficial (`ZARA_STATE.md`),
um sistema de testes. Terminologia fixa (ver `.claude/DECISIONS.md`):

- **ZARA CURRENT SOURCE** — o código no HEAD do branch de trabalho.
- **ZARA CURRENT BUILD** — o artefato empacotado apontado por
  `ZARA_ACTIVE_BUILD.json`/`.txt`.
- **ZARA CURRENT RUNTIME** — o processo em execução testado fisicamente.

Não existe "candidato"/"candidate"/"release candidate" nem "build novo vs.
build antigo" como conceito de trabalho — já é a regra vigente em
`.claude/rules/build-release.md`.

## Zero owner manual operations

**2026-09-04 (correção do Alex).** Regra permanente:

> ZERO OWNER MANUAL OPERATIONS:
> Never ask Alex to locate repositories, paths, files, screenshots, logs,
> commands or technical artifacts when the system can obtain them itself.

Antes de pedir qualquer coisa técnica ao Alex, o Chief tenta descobrir/gerar
sozinho: repo ativo, pasta, arquivo, screenshot, log, comando, path. Isso
inclui construir mecanismo permanente no runtime da ZARA (ex.: captura de
tela automática do Electron real, registro de viewport) em vez de pedir print
manual — ver `frontend/src/main.ts` (`captureElectronScreenshot`,
`writeViewportDiagnostics`) e `ZARA_INICIAR.bat` (commit automático de
`.zara-tests/ui/`), instalados em 2026-09-04 pro pipeline pixel-perfect
(UI-001).

Isto não relaxa a política de confirmação para ações sensíveis (push,
delete, publicação) nem os limites de escopo de `governance.md` — só remove
fricção que o próprio sistema consegue resolver. Continua existindo
`BLOCKED` de verdade quando algo depende de decisão de produto, autorização,
ou informação que só o Alex tem (não que só dá trabalho descobrir).

## Backlog não trava por teste manual pendente

Uma tarefa aguardando teste físico do Alex (ex.: F1.1) **não bloqueia** o
resto do backlog. Se houver outra tarefa `SAFE` e independente (não mexe nos
mesmos arquivos, não depende do resultado do teste pendente), o Chief segue
para ela em paralelo. Só trava tarefa que dependa diretamente do resultado
não confirmado.
