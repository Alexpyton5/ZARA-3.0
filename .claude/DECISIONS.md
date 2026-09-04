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
  (`ZARA_ACTIVE_BUILD.json`/`.txt`), não "candidatos" — já formalizado em
  `.claude/rules/build-release.md` desde 2026-09-04.

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

## Separação de memória (não duplicar estado)

- `.claude/` = como o Claude trabalha (este modelo de operação).
- `.zara-tests/` = como a ZARA está de fato (estado técnico medido).

Nunca escrever estado técnico dentro de `.claude/`, nem regra de processo
dentro de `.zara-tests/`.
