# ZARA — Decisões Permanentes

Só decisão estável/importante. Não é log de rotina — isso fica no git.

- **2026-08-20** — Existe uma hierarquia fechada de 9 papéis, um escritor por
  área (`.claude/rules/time-zara.md`).

- **2026-09-04 (correção do Alex, mesmo dia da instalação)** — O modelo Chief
  of Staff **não** reaproveita os 9 agentes de `time-zara.md`. Alex pediu
  explicitamente um time novo, "tudo novo para não conflitar". Decisão:
  - Os 9 agentes antigos (`zara-engenheiro-*`, `zara-qa-evidencia`,
    `zara-build-auditor`, `zara-evidence-reviewer`, `zara-readonly-architect`,
    `zara-regression-investigator`, `zara-revisor-hostil`) ficam **retirados**
    — não deletados (evita ação destrutiva sem necessidade), só não recebem
    mais tarefa nova a partir de agora.
  - Motivo de não deletar/renomear os arquivos antigos agora: outras
    12 skills do projeto (`.claude/skills/*`) e `.claude/rules/time-zara.md`
    citam esses nomes por texto. Apagar ou renomear quebraria essas
    referências sem ganho real — a retirada funcional (não despachar mais
    tarefa) já resolve o conflito de dois agentes escrevendo o mesmo arquivo,
    que era o risco real por trás do pedido do Alex.
  - Agentes novos são criados **um por vez, sob demanda**, no arquivo do Lead
    correspondente em `.claude/agents/`, com área de escrita própria — não
    necessariamente igual à área do agente antigo equivalente (ex.: o
    `voice-lead` novo junta voz de saída + microfone, que antes eram dois
    donos separados).
  - Primeiro agente novo criado: `voice-lead` (`.claude/agents/voice-lead.md`),
    para tocar F1.1 (voz Kore).

- **2026-09-04** — Instalado o modelo de operação permanente Chief of Staff +
  CTO/Product/QA (`ORG.md`, `WORKING_MODEL.md`). Alex não escolhe mais
  worker/modelo/divisão de tarefa por padrão; só define objetivo e aprova
  ações sensíveis (push, delete, publicação, etc. — política padrão do
  sistema, não relaxada por este modelo).

- **MASTER é a referência visual absoluta da UI.** URL declarada pelo Alex:
  `https://zara-titanium-emerald.p9jpk5w4m6.chatgpt.site/`. Não verificado
  por este agente ainda (não navegado). Fluxo obrigatório: MASTER → Electron
  real, mesma viewport → screenshot → diff → correção. Copiar, não redesenhar.

- **Existe uma única ZARA ativa por vez.** Um build ativo
  (`ZARA_ACTIVE_BUILD.json`/`.txt`) — já formalizado em
  `.claude/rules/build-release.md` desde 2026-09-04.

- **2026-09-04 (correção do Alex) — terminologia fixa, "candidato" abolido
  dos documentos operacionais.** Nos documentos de estado persistente
  (`CURRENT_MISSION.md`, `TASK_BOARD.md`, `ORG.md`, `WORKING_MODEL.md`, este
  arquivo), não usar mais "candidate"/"candidato"/"release candidate"/
  "build antigo vs. novo candidato". Existem só três conceitos:
  - **ZARA CURRENT SOURCE** — código no HEAD do branch de trabalho.
  - **ZARA CURRENT BUILD** — artefato empacotado apontado por
    `ZARA_ACTIVE_BUILD.json`/`.txt`.
  - **ZARA CURRENT RUNTIME** — processo em execução testado fisicamente.
  Documentação histórica fora desse conjunto (ex.: `.claude/rules/build-release.md`,
  nomes literais de pastas em disco como `frontend/release-candidate-*/`,
  agentes/skills que citam o histórico do incidente de 2026-08) não foi
  reescrita — são nomes reais de arquivo/pasta e relato de um incidente
  passado, não o conceito de trabalho atual.

- **2026-09-04 (correção do Alex) — pixel-perfect UI usa análise, execução e
  QA visual separados.** Nunca um único agente analisando, editando e
  julgando o próprio trabalho de interface. UI Director/Pixel-Perfect
  Analyst/Visual QA rodam em Opus 5 (ou o mais próximo disponível de
  raciocínio forte); Frontend Executor/Motion-Widget Executor rodam em
  Sonnet (ou o mais próximo disponível de execução rápida). Sonnet nunca
  aprova pixel-perfect do próprio trabalho — aprovação final é sempre do
  Visual QA. Detalhe do loop, brief e formatos de saída em
  `.claude/WORKING_MODEL.md` ("Refinamento visual pixel-perfect"); papéis em
  `.claude/ORG.md`. Isto substitui a divisão plana anterior (Pixel Perfect
  Lead / Motion Lead / Widget Lead / Visual QA Lead como quatro leads
  paralelos) por uma cadeia liderada pelo UI Director. Missão associada:
  **ZARA MASTER PIXEL-PERFECT FINALIZATION** (`.claude/CURRENT_MISSION.md`),
  tasks UI-001 a UI-018 (`.claude/TASK_BOARD.md`).

- **2026-09-04 (correção do Alex) — backlog não trava por teste manual
  pendente.** Uma tarefa aguardando validação física do Alex (ex.: F1.1 voz
  Kore) não bloqueia o restante do backlog (F1.2 em diante). Se existir
  tarefa `SAFE` e independente (arquivos e resultado não dependem do teste
  pendente), ela segue em paralelo. Só trava o que depende diretamente do
  resultado ainda não confirmado.

- **`ZARA_STATE.md`/`.json` (gerado por `tools/zara_selftest.py`) é a fonte de
  estado técnico oficial.** Antes de reauditar a ZARA, comparar o commit
  registrado nele com `git rev-parse HEAD`; se bater, não rodar suíte de novo.

- **Dispatcher central confirmado é `core/ipc_handlers.py` (classe
  `IPCHandler`)**, com `core/action_registry.py` como registro de ações. Este
  documento usa esses nomes — não "ToolRouter"/"ToolRegistry" — porque são os
  nomes reais encontrados no código (`.claude/rules/path-rules/backend-core.md`).
  Se o Alex quis dizer outra coisa com "ToolRouter", isso precisa ser
  confirmado antes de virar decisão.

- **Hermes e o gate do Supercérebro foram removidos do produto** (commit
  `0e582ec`, 2026-09-04). Não reintroduzir nenhum dos dois — já registrado em
  `.claude/rules/path-rules/backend-core.md`.

## 2026-09-05 — UI se confere renderizando, não lendo

Decidido durante o turno CORUJÃO, e virou regra:

- **Nenhuma afirmação sobre a Home vale sem render.** "O código está certo"
  não é evidência de que a tela está certa. Três defeitos desta madrugada
  passariam despercebidos numa leitura de código: os anéis da plataforma
  invisíveis contra a aurora, a faixa do Sistema cobrindo o card
  Comunicações, e a resposta de texto que era descartada.
- **O harness é `node .zara-tests/ui/run-ui-checks.mjs`.** Builda, sobe um
  servidor local em 127.0.0.1 e roda os probes contra o DOM. Quem mexer na
  Home roda isso antes de dizer que está bom.
- **Os probes injetam o formato REAL dos handlers**, copiado de
  `core/ipc_handlers.py`. Um stub com formato inventado prova nada — foi
  exatamente assim que RAM e Disco ficaram meses sem aparecer.
- **Nível de evidência do harness é `RUNTIME_AUTOMATED`**, e não sobe
  sozinho. Ele prova o renderer, não o EXE que o Alex abre.

## 2026-09-05 — dado de maquete é pior que botão morto

A Home mostrava "João espera sua resposta • WhatsApp • 10 min", "Reunião às
14:00", contagens de mensagens não lidas em quatro canais sem integração, e
uma barra de progresso de projeto em 61%. Tudo herdado da maquete.

Decisão: **conteúdo de maquete não entra em tela de produto.** Um botão que
não faz nada custa um clique; um dado inventado custa o Alex ir procurar uma
mensagem que não existe, e custa a confiança em todo o resto da tela. Sem
fonte real, a tela diz que não tem — nunca preenche com exemplo.

O probe `.zara-tests/ui/probe-sem-mentira.mjs` falha se qualquer uma dessas
frases voltar.

## Separação de memória (não duplicar estado)

- `.claude/` = como o Claude trabalha (este modelo de operação).
- `.zara-tests/` = como a ZARA está de fato (estado técnico medido).

Nunca escrever estado técnico dentro de `.claude/`, nem regra de processo
dentro de `.zara-tests/`.
