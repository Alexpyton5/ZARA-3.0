# ZARA 3.0 — Arquitetura Autopilot Total

**Escopo:** somente a frente de arquitetura do Autopilot.

**Status:** desenho técnico e mapa de implementação. Este documento não declara a ativação de um novo build, não liga providers, não altera o banco, não inicia processos e não substitui a aprovação do proprietário.

**Base factual:** código-fonte, testes e documentação local observados no repositório em 17/09/2026. Relatórios históricos só são considerados quando compatíveis com o código e com evidência datada.

## 1. Veredito executivo

A visão de **Autopilot total** da ZARA deve ser implementada como um ciclo fechado, porém limitado e auditável:

```text
sinal factual
  → proposta
  → admissão idempotente
  → missão limitada
  → candidato isolado
  → teste de baseline e teste do candidato
  → revisão independente
  → aprovação explícita
  → pacote candidato
  → canário do runtime empacotado
  → ativação transacional
  → monitoramento
  → commit ou rollback
```

A ZARA já possui partes relevantes desse ciclo. Há um sidecar Python com `core/ipc_handlers.py`, registro de ações, `ToolRouter`, memória persistente e um runtime de Lab V1. O Lab também possui supervisor, orçamento, deduplicação, ledger idempotente, isolamento de candidato e uma fila de promoção com rollback. Essas partes não equivalem, isoladamente, a um Autopilot total em produção.

O limite principal é este: **o Autopilot pode observar, propor, testar e preparar um candidato; ele não deve transformar uma proposta em alteração de produção sem todos os gates e sem autorização explícita do proprietário**. O caminho de linguagem natural ainda não decompõe arbitrariamente qualquer objetivo em um plano autônomo. O `RulePlanner` aceita `explicit_steps`, e a decomposição automática geral continua não provada [1].

Portanto, a arquitetura proposta trata “total” como **cobertura integral do ciclo de decisão e evidência**, não como permissão irrestrita para modificar o computador, o código ou o build ativo.

## 2. Termos e estados de verdade

Os termos abaixo têm significado operacional. A interface, o banco e a UI devem usar esses estados sem fazer inferências otimistas.

| Termo | Significado obrigatório | O que não significa |
|---|---|---|
| **Sinal** | Observação factual, com origem, horário e identidade da evidência. | Uma opinião ou um hash sem diagnóstico não prova defeito. |
| **Proposta** | Hipótese ou objetivo registrado para avaliação. | Não é autorização para editar source ou executar ação externa. |
| **Admitida** | Proposta aceita pelo supervisor sob orçamento, deduplicação e política. | Não significa que um agente já executou trabalho. |
| **Candidato** | Alteração produzida em workspace isolado, com manifest e identidade de source. | Não é o build ativo nem uma release aprovada. |
| **Testada** | Baseline e candidato foram executados nos testes definidos, com saída e hashes registrados. | Um teste verde em fixture não prova o runtime empacotado. |
| **Revisada** | Revisor independente examinou diff, objetivo, riscos e evidências e emitiu `PASS`. | Uma resposta do agente executor não é revisão independente. |
| **Aprovada** | Proprietário autorizou o candidato específico, identificado por hashes e escopo. | “Pronto para aprovar” ou a presença de um instalador não são aprovação. |
| **Ativada** | O candidato foi colocado no caminho operacional por uma operação transacional. | Não é apenas copiar arquivos ou mudar um ponteiro. |
| **Ativa saudável** | O runtime ativo passou pelo monitoramento pós-ativação e foi consolidado no journal. | O estado não pode ser exibido antes da verificação do mesmo pacote, ASAR e backend. |
| **Bloqueada** | O sistema recusou avançar por falta de evidência, risco, drift, erro ou decisão do proprietário. | Não é falha silenciosa nem autorização implícita para tentar novamente. |

Estados são monotônicos dentro de um ciclo, exceto por transições explícitas para `ROLLED_BACK` ou `BLOCKED`. Uma reexecução com o mesmo `request_id` deve devolver o mesmo ACK durável; uma nova intenção com o mesmo ID deve ser recusada como conflito [10].

## 3. Componentes reais e responsabilidade proposta

A tabela separa o que já existe do que ainda precisa de integração ou prova. “Real” significa que há código ou teste local correspondente; não significa que todos os ambientes, providers ou dispositivos estejam disponíveis.

| Camada | Componente real | Responsabilidade no Autopilot | Estado factual e limite |
|---|---|---|---|
| Entrada desktop | `frontend/src/main.ts` | Criar janela, iniciar/encaminhar o sidecar, expor IPC do Electron. | É transporte e lifecycle. Não deve ser a autoridade de autorização do Autopilot. |
| Ponte segura | `frontend/src/preload.ts` | Expor uma API mínima ao renderer. | O contrato observado mantém `contextIsolation=true` e `nodeIntegration=false`; não colocar credenciais ou decisões de promoção no renderer [1]. |
| Orquestração IPC | `core/ipc_handlers.py` | Receber comando, encaminhar estado, Lab, memória, voz e ações. | Existe caminho real, mas a presença de um canal IPC não prova execução bem-sucedida de uma missão. |
| Registro de ações | `core/action_registry.py` e `core/actions/` | Declarar ações disponíveis e parâmetros. | Há ações Windows, arquivos, terminal, navegador e voz; disponibilidade é condicionada ao ambiente e ao gate da ação. |
| Ferramentas | `core/tool_registry.py` e `core/tool_router.py` | Validar schema, verificar permissão, executar, normalizar resultado, verificar e auditar. | O fluxo determinístico é `VALIDATE → LOOKUP → SCHEMA → PERMISSION → EXECUTE → NORMALIZE → VERIFY → AUDIT → RESULT`. A cobertura de verifiers varia por ferramenta [8]. |
| Roteamento de modelos | `core/model_router.py` | Escolher modelo conforme tarefa, política, saúde, custo e fallback configurado. | Registry e política não provam chave, quota, conectividade, latência ou qualidade desta instalação. Nenhum provider é ativado por este documento. |
| Lab V1 | `core/lab_v1/` | Persistir equipes, agentes, sessões, tarefas, eventos, handoffs e operações. | O V1 separa provider, model, agent, role, team e session. Não é uma fábrica irrestrita de agentes nem um council completo [1]. |
| Serviço do Lab | `core/lab_v1/service.py` | Fachada JSON-safe para IPC, snapshots, scheduler e operações de background. | Há scheduler persistente, backoff e deduplicação no código. Isso não prova que um processo Windows esteja executando continuamente. A política efetiva e o heartbeat devem ser verificados em runtime [6]. |
| Supervisor | `core/lab_v1/supervisor.py` | Ser a única porta de admissão para autonomia diária: orçamento, prioridade, pausa, heartbeat, gate entre missões e recuperação. | O supervisor persiste policy, operações e lease entre processos. Não deve iniciar provider, rede ou ação externa apenas por observar um sinal [7]. |
| Ledger | `core/lab_v1/operation_ledger.py` | Reservar `request_id`, criar `operation_id`, garantir replay e rejeitar conflito. | Há testes de concorrência, restart e rollback transacional do ACK [10]. |
| Motor de evolução | `core/lab_v1/evolution.py` | Observar source e lacunas factuais, gerar proposta e despachar missão limitada. | O motor observa e planeja; a própria documentação do módulo separa observação de reparo. Ele não deve promover source por conta própria [1]. |
| Missão | `core/lab_v1/mission_controller.py` | Validar plano, aplicar limites de turnos/delegações/retries/ações/deadline, usar leases e persistir checkpoints. | Uma missão possui limites finitos e execução sequencial; não é loop infinito. |
| Autopilot de missão | `core/lab_v1/autopilot.py` | Coordenar a missão governada pelo Lab e seus agentes/ports. | Delegação, rodadas e providers estão limitados por policy. Não presumir formação automática de equipes, learned routing ou autonomia geral. |
| Fonte do candidato | `core/lab_v1/candidate_source.py` | Copiar arquivos explicitamente autorizados para sandbox, criar baseline/manifest, aplicar edição limitada e gerar diff. | Há proteção contra path fora do workspace, symlink, arquivos proibidos, drift e edição apenas de teste. A política de rede declarada para o candidato é `ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED` [4]. |
| Testes | `tests/`, `pytest`, typecheck/build conforme política | Provar baseline, mudança, regressão, contratos de segurança e integração. | Teste puro em Linux ou fixture não substitui teste Windows/Electron/microfone/browser. Números históricos não devem ser reciclados como estado atual [1]. |
| Release queue | `core/lab_v1/release.py` | Manter fila durável: package, canary, readiness, promoção, monitoramento, commit e rollback. | Já recusa candidato não verificado, sem review, de risco não baixo, com artefato alterado ou sem alvo conhecido de rollback [5]. |
| Empacotamento | `tools/build_current.py` e scripts canônicos | Construir candidato com identidade, `SOURCE_MANIFEST.json`, `BUILD_INFO.json`, ASAR e backend identificados. | O build ativo não deve ser sobrescrito. Preflight e staging são allow-listed; a existência de instalador não autoriza ativação [2]. |
| Ponteiro operacional | `ZARA_ACTIVE_BUILD.json` e launcher | Identificar o pacote que será aberto e validar hashes antes do lançamento. | O ponteiro observado aponta para `release-candidate-fix-9router-v2-20260917-0020`, com `GIT_DIRTY=true`. Esse fato não é uma nova validação feita por esta tarefa. |
| Memória | `memory/`, histórico SQLite e `LabStore` | Persistir fatos, eventos, decisões, proveniência e resultados necessários ao ciclo. | Memória estruturada possui escrita atômica/redaction; isso não transforma o vault em contexto global automático nem autoriza reter segredos. |

### 3.1 Fronteira de autoridade

A autoridade deve permanecer concentrada no backend e ser dividida em três decisões distintas:

1. **Supervisor:** decide se uma proposta pode consumir orçamento e virar missão.
2. **Executor de candidato:** decide se uma edição bounded pode ser escrita no sandbox e se os testes foram executados.
3. **Release owner:** decide se o candidato específico pode sair do sandbox e ser promovido ao runtime.

O renderer, a resposta textual do modelo e o fato de um agente ter terminado uma tarefa não podem substituir nenhuma dessas três decisões.

## 4. Topologia alvo, preservando os caminhos existentes

A topologia alvo não cria um terceiro executor de ações. Ela conecta o Autopilot aos caminhos já existentes e deixa claros os limites.

```text
[Texto / voz / evento local]
          |
          v
[IPC seguro + handler]
          |
          +--> [Fast path determinístico]
          |          |
          |          +--> ActionRegistry / ToolRouter
          |          +--> confirmação / permissão / verifier / auditoria
          |
          +--> [Autopilot admission]
                     |
                     +--> OperationLedger: ACK idempotente
                     +--> AutonomySupervisor: policy, orçamento, dedup, lease
                     +--> MissionController: plano e limites
                     +--> Lab V1: sessão, agentes, tarefas, eventos
                     +--> CandidateSource: snapshot e sandbox
                     +--> testes de baseline e candidato
                     +--> revisão independente
                     +--> ReleaseQueue: package → canary → approval
                     +--> SourcePromotion/build_current: ativação transacional
                     +--> health monitor → commit ou rollback
```

O fast path continua obrigatório para comandos simples. Uma solicitação não deve ser enviada ao ciclo de autopilot apenas porque contém linguagem natural. O roteador deve escolher entre ação determinística, resposta sem efeito externo, proposta de missão ou bloqueio explícito.

A sequência de execução de uma ferramenta continua sendo determinística. Um agente pode produzir uma intenção estruturada, mas não pode chamar subprocesso, rede, hardware ou uma ação diretamente. A intenção deve voltar ao `ToolRouter`, que reavalia schema, capacidade, risco, permissão, confirmação e verificação [1] [8].

## 5. Contratos mínimos testáveis

Os contratos abaixo são formas de referência para implementação e testes. Os nomes podem ser adaptados ao código existente, mas a semântica não deve ser relaxada.

### 5.1 Envelope de proposta

```json
{
  "proposal_id": "proposal:sha256:...",
  "request_id": "request:...",
  "kind": "SELF_IMPROVEMENT",
  "objective": "Investigar uma falha factual no executor",
  "source_refs": ["core/actions/browser.py"],
  "evidence": {
    "observation_kind": "RUNTIME_CAPABILITY_FAILURE",
    "observed_at": "2026-09-17T00:00:00Z",
    "evidence_sha256": "..."
  },
  "risk": "LOW",
  "production_activation": "OWNER_APPROVAL_REQUIRED",
  "state": "PROPOSED"
}
```

Invariantes:

- `proposal_id` é derivado da evidência e do escopo, ou é univocamente persistido.
- `source_refs` aponta apenas para caminhos permitidos; não inclui segredo, build, release ou dados pessoais.
- `risk` não pode ser rebaixado pelo agente.
- `production_activation` começa sempre como `OWNER_APPROVAL_REQUIRED`.
- Proposta sem evidência suficiente pode ser registrada como `PROPOSAL_ONLY_UNSUPPORTED`, mas não pode produzir edição.

### 5.2 Envelope de candidato

```json
{
  "candidate_id": "candidate:...",
  "proposal_id": "proposal:...",
  "workspace": "sandbox/desktop-workspace",
  "manifest_sha256": "...",
  "source_before_sha256": "...",
  "source_after_sha256": "...",
  "overlay": [
    {"path": "core/example.py", "sha256": "...", "editable": true}
  ],
  "baseline": {"status": "PASSED", "receipt_id": "test:baseline:..."},
  "candidate_tests": {"status": "PASSED", "receipt_id": "test:candidate:..."},
  "review": {"verdict": "PASS", "reviewer_run_id": "run:..."},
  "candidate_status": "VERIFIED_AWAITING_APPROVAL"
}
```

Invariantes:

- O workspace do candidato está fora do workspace de produção.
- Cada arquivo editável foi explicitamente autorizado e existe no manifest.
- O source de produção permanece byte-a-byte inalterado durante a edição e os testes do candidato.
- O candidato precisa alterar ao menos um arquivo de source; apenas modificar testes não é uma correção válida.
- O relatório de teste inclui comando, exit code, stdout/stderr limitado, hashes de testes e indicação de baseline ou candidato.
- Qualquer drift em source, overlay, package, ASAR ou backend invalida o candidato e exige reconstrução.

### 5.3 Envelope de aprovação

```json
{
  "approval_id": "approval:...",
  "candidate_id": "candidate:...",
  "owner": "owner-id",
  "decision": "APPROVE_ACTIVATION",
  "scope": {
    "build_id": "zara-current-...",
    "source_sha256": "...",
    "asar_sha256": "...",
    "backend_sha256": "..."
  },
  "approved_at": "2026-09-17T00:00:00Z",
  "expires_at": null,
  "reason": "Candidato revisado e canário aprovado"
}
```

A aprovação deve ser vinculada ao `candidate_id` e aos quatro elementos de identidade relevantes: source, build, ASAR e backend. Aprovação genérica para “qualquer próximo build” é inválida. Mensagens como “pode preparar”, “parece bom” ou “faça a atualização” não devem ser convertidas em aprovação silenciosa quando o fluxo exige decisão explícita.

### 5.4 Journal de ativação

```json
{
  "state": "MONITORING",
  "candidate_build_id": "zara-current-...",
  "known_good_build_id": "zara-current-previous-...",
  "before_source_sha256": "...",
  "candidate_source_sha256": "...",
  "build_journal": "artifacts/releases/...json",
  "source_promotion_journal": "artifacts/releases/source-.../SOURCE_PROMOTION.json",
  "health": {"status": "PENDING", "checks": []},
  "rollback_target": "retained-known-good"
}
```

O journal é a fonte de recuperação do ciclo, não um log decorativo. Após restart, o reconciliador deve classificar source, sidecar, pacote e ponteiro como `KNOWN_GOOD`, `CANDIDATE` ou `UNKNOWN`. `UNKNOWN` não pode ser promovido nem descartado automaticamente; deve resultar em rollback comprovado ou `RECONCILIATION_NEEDS_OWNER` [5].

## 6. Fluxo proposto: candidato → teste → aprovação → ativação

### Passo 0 — Preparar o ciclo

O supervisor lê a policy persistida, verifica se não há missão não terminal de prioridade maior, confirma orçamento e consulta journals de promoção pendentes. Se houver promoção não resolvida, o ciclo fica bloqueado. O sistema não inicia uma segunda promoção sobre estado híbrido.

**Saída:** `CYCLE_ADMITTED` ou `BLOCKED` com razão persistida.

### Passo 1 — Registrar sinal e gerar proposta

Um sinal deve ser factual: falha de runtime capturada, feedback com identidade, contraexemplo reproduzível ou inspeção local sem provider. O motor registra origem, hash, timestamp e caminho relacionado. Se não houver evidência suficiente, grava uma proposta somente para avaliação e encerra sem edição.

**Saída:** `PROPOSED` com `proposal_id` estável.

### Passo 2 — Admitir com ledger e orçamento

O supervisor passa a proposta pelo `OperationLedger`. O mesmo `request_id` reapresentado devolve o ACK original. Uma intenção diferente com esse ID falha como conflito. Deduplicação por evidência e orçamento diário são aplicados antes de chamar agente ou provider.

**Saída:** `ADMITTED`, `DUPLICATE`, `BACKOFF`, `PAUSED`, `BUDGET_EXHAUSTED` ou `BLOCKED_NEEDS_OWNER`.

### Passo 3 — Criar sessão e plano limitado

O Lab cria ou reutiliza uma sessão sem duplicar time, missão, mensagens ou decisões. O plano deve declarar `MissionLimits`: máximo de turnos, delegações, retries, ações e deadline. Cada passo precisa de tarefa, critério de aceitação, membro ativo, dependências válidas e `ExecutionScope`.

O objetivo em linguagem natural não pode pular essa etapa. Se não houver passos explícitos válidos, a ZARA deve responder que a missão não foi admitida, em vez de improvisar uma sequência de ações.

**Saída:** `MISSION_QUEUED` com plano versionado, limites e escopo.

### Passo 4 — Criar snapshot bounded

`CandidateSource` copia somente os arquivos autorizados para um workspace descartável. O manifest registra existência, caminho original, hash anterior e editabilidade. Suportes são somente leitura. Paths absolutos, `..`, symlink, segredos, builds, releases, caches e arquivos fora do escopo são recusados.

**Saída:** `CANDIDATE_SANDBOXED` com `manifest_path`, `baseline_root` e identidade da fonte.

### Passo 5 — Executar baseline

Antes da mudança, executar os testes focados contra a baseline. Se a baseline já falhar, a missão não pode atribuir a falha ao candidato. O relatório deve separar `baseline=true` de `baseline=false` e conservar o comando exato.

**Saída:** `BASELINE_PASSED` ou `BASELINE_FAILED`. Baseline falha bloqueia promoção e exige diagnóstico ou replanejamento.

### Passo 6 — Aplicar patch limitado no sandbox

O agente retorna edição estruturada. O executor valida todas as edições antes da primeira escrita. Edição apenas de teste, no-op, duplicada, acima do limite, fora de arquivo autorizado ou incompatível com a sintaxe deve ser recusada sem tocar na produção. Ao final, o executor produz diff factual, contagem de arquivos, linhas e hashes antes/depois.

**Saída:** `PATCH_APPLIED` ou `PATCH_DRAFT_REJECTED`.

### Passo 7 — Executar teste do candidato

Os mesmos testes da baseline, mais regressões específicas e testes dos invariantes de segurança, rodam sobre o sandbox. Uma missão só pode marcar sucesso se tiver exit code esperado, resultados coerentes e evidência de artefato. Uma resposta de modelo ou um ACK de fila nunca substitui essa prova.

**Saída:** `CANDIDATE_TESTED` ou `CANDIDATE_TEST_FAILED`.

### Passo 8 — Revisão independente

Um revisor diferente do executor verifica objetivo, diff, source permitido, risco, testes, evidência e ausência de alteração fora do workspace. O review retorna `PASS`, `FAIL` ou `INCONCLUSIVE`, com `reviewer_run_id` e referências a artefatos. `INCONCLUSIVE` é bloqueio, não aprovação.

**Saída:** `CANDIDATE_VERIFIED` ou `INDEPENDENT_REVIEW_BLOCKED`.

### Passo 9 — Empacotar sem ativar

Somente um candidato verificado pode entrar em `ReleaseQueue`. A fila exige workspace canônico, candidato de risco baixo, review aprovado, source identity, baseline conhecido e ausência de promoção pendente. O pacote deve conter, no mesmo staging, o instalador, `win-unpacked/ZARA 3.0.exe`, `BUILD_INFO.json`, `SOURCE_MANIFEST.json` e o backend empacotado [2].

**Saída:** `PACKAGE_PENDING` → `CANARY_PENDING`.

### Passo 10 — Canário exato do pacote

A validação do canário deve apontar para o mesmo `ASAR_SHA256` e `BACKEND_SHA256` registrados no pacote. O relatório precisa identificar o executável/ASAR/backend observados, comandos, status e limitações. Canário de fixture ou de outro build não satisfaz esse gate.

**Saída:** `READY_TO_ACTIVATE` ou `PACKAGED_CANARY_NOT_PASSED`.

### Passo 11 — Aprovação explícita

Antes de sair do sandbox, a ZARA apresenta ao proprietário: objetivo, diff, riscos, testes da baseline e do candidato, review independente, hashes, build ID, canário, plano de rollback e efeitos esperados. O proprietário aprova esse candidato específico. Sem decisão explícita, o ciclo permanece pronto para aprovação.

**Saída:** `OWNER_APPROVED` ou `AWAITING_OWNER_APPROVAL`.

### Passo 12 — Ativação transacional

`SourcePromotion` registra journal, preserva source e pacote conhecido-bom, aplica a fonte do candidato, confere `source_sha256`, copia o backend, prepara staging de promoção e só então usa o pipeline de ativação. Qualquer exceção restaura source, sidecar, pacote e pointers conforme o journal. O build ativo não deve ser editado no lugar.

**Saída:** `ACTIVATING` → `MONITORING` ou `BLOCKED`.

### Passo 13 — Health check, commit ou rollback

O monitoramento verifica que o pacote ativo, o ponteiro, o source e o sidecar correspondem ao candidato. O health check deve incluir startup, preload/IPC, spawn do sidecar, resposta textual, memória/histórico quando aplicável e a ação segura prevista no escopo. Voz, microfone, browser, hardware e Electron empacotado devem ser marcados como não provados se não forem executados no ambiente exigido.

Se o monitoramento falhar, a fila chama rollback para o known-good retido. Se passar, `SourcePromotion.commit()` fecha o journal. Um erro durante o commit não autoriza repetir a promoção às cegas; o reconciliador deve primeiro classificar a evidência.

**Saída:** `ACTIVE` com `PROMOTION_MONITORED_PASS`, `ROLLED_BACK` ou `RECONCILIATION_NEEDS_OWNER`.

## 7. Fases de implantação da arquitetura

As fases abaixo são incrementais. Nenhuma fase posterior deve ser considerada concluída porque um módulo foi criado; cada fase exige os gates da seção seguinte.

### Fase A — Governança e inventário

**Objetivo:** consolidar as fontes de verdade e impedir que o Autopilot toque no build ativo.

**Trabalho:** manter uma única policy do supervisor, um único ledger de operações, um único caminho de execução (`ToolRouter`) e um único caminho de release (`ReleaseQueue` + pipeline canônico). Inventariar callers antes de ligar módulos experimentais.

**Definition of Done:** toda proposta identifica source, risco, owner gate e destino; toda promoção pendente é detectável; o build ativo e os bancos permanecem intocados durante testes de sandbox.

### Fase B — Proposta e admissão idempotente

**Objetivo:** transformar sinais factuais em propostas rastreáveis sem execução implícita.

**Trabalho:** formalizar `ProposalEnvelope`, `request_id`, `evidence_sha256`, deduplicação, pause, backoff e limites diários. Separar `PROPOSAL_ONLY_UNSUPPORTED` de falha de execução.

**Definition of Done:** duplicata gera uma operação lógica; restart preserva orçamento e estado; proposta não gera patch sem admissão.

### Fase C — Missão bounded e candidato isolado

**Objetivo:** tornar o trabalho do agente executável, reversível e restrito a um workspace descartável.

**Trabalho:** conectar plano versionado e `ExecutionScope` ao `CandidateSource`; persistir leases; rejeitar path proibido, symlink, source drift, edição de teste isolada e patches acima dos limites.

**Definition of Done:** o source de produção não muda durante a missão; baseline e candidato têm receipts separados; qualquer rejeição ocorre antes da primeira escrita.

### Fase D — Testes e revisão verificáveis

**Objetivo:** eliminar o falso sucesso.

**Trabalho:** exigir baseline, candidato, regressões, evidência de artefatos e revisão independente. O estado da missão só avança com receipts válidos.

**Definition of Done:** uma falha não recebe `COMPLETED`; um resultado sem verifier é explicitamente `UNVERIFIED`; review `FAIL` ou `INCONCLUSIVE` impede release.

### Fase E — Pacote candidato e canário

**Objetivo:** provar o runtime empacotado sem tocar no pointer ativo.

**Trabalho:** gerar staging allow-listed, `BUILD_INFO.json`, `SOURCE_MANIFEST.json`, hashes de EXE/ASAR/backend e relatório de canário do mesmo pacote.

**Definition of Done:** `promotion_readiness()` retorna `eligible=true` para um fixture completo e retorna uma razão específica para cada violação; o build ativo continua com a mesma identidade.

### Fase F — Aprovação e ativação transacional

**Objetivo:** fazer uma promoção real somente com aprovação específica e rollback disponível.

**Trabalho:** vincular aprovação a candidate/build/source/ASAR/backend; executar `SourcePromotion`; monitorar; consolidar ou restaurar.

**Definition of Done:** promoção saudável termina em `COMMITTED` e mantém backup; health failure termina em `ROLLED_BACK`; drift, falha de pointer ou journal ambíguo não produzem estado híbrido silencioso.

### Fase G — Autonomia recorrente limitada

**Objetivo:** permitir ciclos recorrentes sem perder controle.

**Trabalho:** scheduler com heartbeat, backoff, prioridade de missões do owner, orçamento, dedup e pausa; nenhum ciclo pode criar uma autorização permanente. A fila pode continuar propondo, testando e aguardando aprovação.

**Definition of Done:** restart retoma o estado durável; ciclo vazio gasta zero chamadas; backlog não cresce por duplicata; owner pode pausar novas admissões; não há alegação de 24/7 sem evidência de processo e heartbeat no ambiente real.

## 8. Gates de aceitação

| Gate | Pergunta de bloqueio | Evidência mínima | Estado se falhar |
|---|---|---|---|
| **G0 — autoridade** | Há um ciclo pendente, conflito de owner ou promoção não reconciliada? | Snapshot da policy, ledger e `pending_promotions()` | `BLOCKED` |
| **G1 — sinal** | O objetivo é baseado em observação factual? | `proposal_id`, origem, timestamp, hash e escopo | `PROPOSAL_ONLY_UNSUPPORTED` |
| **G2 — admissão** | O request é novo, permitido e está dentro do orçamento? | ACK durável, `operation_id`, budget e dedup result | `DUPLICATE`, `PAUSED` ou `BUDGET_EXHAUSTED` |
| **G3 — missão** | O plano é finito, válido e tem acceptance criteria? | Plano versionado, limits, lease e execution scope | `MISSION_REJECTED` |
| **G4 — isolamento** | O candidato pode ser editado sem tocar produção? | Snapshot, manifest, paths allow-listed e sandbox externo | `CANDIDATE_SANDBOX_REJECTED` |
| **G5 — baseline** | A baseline conhecida passa os testes focados? | Receipt com `baseline=true`, comando e exit code | `BASELINE_FAILED` |
| **G6 — patch** | A mudança é de source, bounded, sintática e não altera arquivo proibido? | Diff factual, hashes e `source_files_changed > 0` | `PATCH_DRAFT_REJECTED` |
| **G7 — candidato** | O candidato passa testes e verifier? | Receipt candidato, testes e artefatos | `CANDIDATE_TEST_FAILED` |
| **G8 — revisão** | Um revisor independente aprovou este diff? | `reviewer_run_id`, verdict `PASS`, rationale e refs | `INDEPENDENT_REVIEW_BLOCKED` |
| **G9 — pacote** | O pacote é íntegro e corresponde ao source? | `BUILD_INFO.json`, `SOURCE_MANIFEST.json`, EXE/ASAR/backend hashes | `CANDIDATE_ARTIFACT_DRIFT` |
| **G10 — canário** | O canário executou o mesmo ASAR e backend? | Relatório `passed` com os dois hashes | `PACKAGED_CANARY_NOT_PASSED` |
| **G11 — owner** | O proprietário aprovou o candidato específico? | Approval vinculada a IDs e hashes | `AWAITING_OWNER_APPROVAL` |
| **G12 — ativação** | A transação preserva known-good e journal? | Journal, backup, pointers e source identity | `BLOCKED` + restauração |
| **G13 — saúde** | O runtime ativo é coerente e atende o smoke definido? | Health report do candidato exato | `ROLLED_BACK` |
| **G14 — commit** | A promoção foi concluída sem ambiguidade? | Journal `COMMITTED`, pointer e hashes coerentes | `RECONCILIATION_NEEDS_OWNER` |

Os gates G9–G14 seguem a lógica já expressa pela fila de release: candidato verificado, review aprovado, risco baixo, canário compatível, known-good disponível e rollback preservado [5].

## 9. Matriz de riscos e contenções

| Risco | Falha que a arquitetura deve evitar | Contenção obrigatória |
|---|---|---|
| Falso sucesso | Modelo diz “concluído”, mas nenhuma ação ou teste produziu evidência. | Estado deriva de executor, verifier, receipt e journal; nunca da prosa do agente. |
| Self-modification irrestrita | Agente altera o próprio runtime, build, policy ou banco de produção. | CandidateSource bounded, paths proibidos, source separado, owner gate e pipeline de release. |
| Repetição paga | Restart ou retry cria chamadas duplicadas. | Ledger idempotente, dedup por evidência, max retries e budget persistido. |
| Ação externa sem autorização | Plano chama terminal, browser, arquivos ou sistema sem gate. | Planner sem subprocess/rede/hardware; toda ação passa pelo ToolRouter. |
| Drift | Source muda depois do teste ou pacote é adulterado antes da ativação. | Hashes antes/depois, manifest, package verify e recusa de `CANDIDATE_ARTIFACT_DRIFT`. |
| Estado híbrido | Source, sidecar, pacote e pointer pertencem a builds diferentes. | Journal transacional, known-good retido, classificação de evidência e rollback. |
| Provider indisponível | Registry ou binário presente é tratado como provider disponível. | Estados `AVAILABLE`, `LIMITED`, `AUTH_INVALID`, `ERROR` e `UNKNOWN_COST`; disponibilidade exige sondagem no ambiente. |
| Loop infinito | Scheduler cria missões continuamente ou reprocessa a mesma evidência. | Cadência, backoff, dedup, limite diário, prioridade do owner e pausa. |
| Vazamento | Segredo aparece em prompt, memória, histórico, receipt ou auditoria. | Redaction, allowlist de contexto, não copiar `.env`/chaves e revisar payloads. |
| Teste inadequado | Fixture verde é apresentada como prova de Electron, Windows ou hardware. | Separar `PURE`, `PACKAGED`, `WINDOWS_LIVE` e `HARDWARE_LIVE`; declarar `NOT_LIVE_VERIFIED` quando necessário. |

## 10. Limites atuais que permanecem explícitos

1. **Planejamento autônomo geral não está provado.** O Planner validado executa planos explícitos; não existe evidência de decomposição automática geral de linguagem natural integrada ao caminho principal [1].
2. **Autonomia recorrente não equivale a autonomia irrestrita.** Scheduler, supervisor, orçamento e deduplicação existem como código e testes, mas o processo, o boot e o heartbeat do ambiente de produção precisam ser validados no runtime. A presença de `SCHEDULER_ENABLED` no source não prova que um build ativo esteja executando o loop.
3. **O Lab V1 é limitado.** Há sessões, agentes, delegação limitada, handoffs e failover, mas não há prova de council completo, formação automática de equipes, learned routing ou fábrica autônoma de agentes [1].
4. **Verificação é parcial.** `ToolRouter` suporta verifiers, mas cada ferramenta pode não possuir verifier ou pós-condição suficiente. Resultado sem verificação deve permanecer não verificado [8].
5. **Providers são condicionais.** A configuração de um provider, seu registro ou seu CLI não comprova autenticação, quota, disponibilidade, custo, latência ou qualidade. Este documento não usa rede nem ativa provider.
6. **Voz, microfone, browser, hardware e Electron empacotado exigem prova do ambiente correspondente.** Testes Linux de inspeção e fixtures não substituem teste Windows live [1] [2].
7. **Memória não é contexto global automático.** JSON, SQLite e bridge local provam persistência de dados, não recuperação perfeita ou injeção automática de todo o vault em cada decisão [1].
8. **Ativação não é consequência automática do teste.** Um candidato pode ser aprovado nos testes e ainda permanecer aguardando owner, canário ou espaço/condições do build.
9. **Build ativo e bancos estão fora do escopo desta frente.** O documento descreve interfaces de proteção; não muda `ZARA_ACTIVE_BUILD.json`, não move release, não altera `data/`, `memory/` ou frontend.
10. **“Infinito” é uma propriedade de fila, não um efeito garantido.** Uma fila futura pode ser gerada somente quando os gates anteriores forem concluídos e a policy permitir. Sempre deve existir pausa, orçamento e decisão humana para promoção.

## 11. Estados de UI e API

A UI deve mostrar o estado persistido, não uma interpretação visual otimista. O mínimo recomendado é:

| Estado backend | Rótulo de UI | Ação permitida |
|---|---|---|
| `PROPOSED` | Proposta registrada | Ver evidência; admitir ou descartar. |
| `QUEUED` / `ADMITTED` | Na fila | Cancelar ou aguardar; não anunciar execução concluída. |
| `RUNNING` | Em execução | Ver objetivo, lease, limites e cancelar quando suportado. |
| `CANDIDATE_TESTED` | Candidato testado | Abrir diff e receipts; ainda não ativar. |
| `READY_TO_ACTIVATE` | Aguardando aprovação | Exibir hashes, riscos e rollback; solicitar decisão explícita. |
| `ACTIVATING` | Ativando | Bloquear segunda promoção e mostrar journal. |
| `MONITORING` | Monitorando | Não mostrar sucesso final antes do health check. |
| `ACTIVE` | Ativo e monitorado | Mostrar build ID e evidência do monitoramento. |
| `ROLLED_BACK` | Revertido | Mostrar causa, known-good restaurado e próximo passo. |
| `BLOCKED` / `RECONCILIATION_NEEDS_OWNER` | Bloqueado | Mostrar razão e exigir ação compatível; não retry automático. |

O ACK `QUEUED` significa “recebido e persistido”. Ele não significa “executado” ou “concluído”. A regra vale para Lab, release, ferramentas, voz e qualquer integração futura.

## 12. Plano de validação testável

A validação deve ser executada em camadas, com cada camada produzindo evidência própria.

### 12.1 Testes puros e isolados

Executar no workspace de candidato ou em fixtures descartáveis:

```text
pytest tests/test_lab_candidate_source.py -q
pytest tests/test_lab_operation_ledger.py -q
pytest tests/test_lab_daily_autonomy.py -q
pytest tests/test_lab_supervisor.py -q
pytest tests/test_lab_source_promotion.py -q
```

Esses testes devem demonstrar, no mínimo:

- snapshot e manifest de arquivos reais;
- contexto limitado ao snapshot;
- rejeição de path externo, symlink, segredo e suporte somente leitura;
- recusa de patch sem mudança de source;
- baseline e candidato separados;
- ACK idempotente, conflito e concorrência;
- orçamento persistido e deduplicação após restart;
- pausa, backoff e prioridade de missão do owner;
- readiness recusando review ausente, risco não baixo, canário incompatível e artifact drift;
- promoção saudável transacional;
- rollback após health failure;
- restauração após falha de pointer e drift antes da ativação.

Os caminhos exatos de teste devem ser conferidos no checkout antes de executar. Este documento não converte uma lista de comandos em resultado de teste.

### 12.2 Testes de contrato

Para cada envelope e transição, adicionar testes que afirmem:

```text
assert proposal_without_evidence != CANDIDATE
assert duplicate_request.replay == first_ack
assert conflicting_request raises IdempotencyConflict
assert production_source_hash_after_candidate == production_source_hash_before_candidate
assert review_fail != READY_TO_ACTIVATE
assert canary.asar_sha256 == package.asar_sha256
assert canary.backend_sha256 == package.backend_sha256
assert approval.scope == candidate.identity
assert failed_health == ROLLED_BACK
assert unresolved_journal == RECONCILIATION_NEEDS_OWNER
```

Essas asserções devem operar sobre dados temporários e não sobre o build, banco ou memória do proprietário.

### 12.3 Testes de frontend/Electron e Windows live

Somente no ambiente autorizado e com o build candidato correto:

1. executar `npm run typecheck` em `frontend/`;
2. executar `npm run build` em `frontend/`;
3. executar os testes Python conforme `TEST_RUN_POLICY.md`, primeiro puros e depois os marcados live;
4. abrir dev/Electron ou candidato empacotado e confirmar preload, sidecar e canais IPC;
5. testar texto, histórico, uma ação com confirmação, estado do Core e interrupção segura;
6. testar voz, microfone, browser e hardware somente quando o teste físico estiver autorizado;
7. registrar commit/branch, build ID, timestamps, hashes, comandos e falhas.

Sem essa camada, o resultado deve ser marcado como `NOT_LIVE_VERIFIED`. A existência de um arquivo `VALIDATION.json` ou de um instalador sem correspondência de ASAR/backend não satisfaz o gate.

## 13. Fluxo de decisão resumido

```text
se não há sinal factual:
    registrar ausência de evidência
    não criar candidato

se há sinal, mas policy/owner/ orçamento bloqueiam:
    persistir PROPOSAL_ONLY ou BLOCKED
    não chamar executor

se admitido:
    reservar request_id
    criar missão limitada
    snapshot bounded
    rodar baseline

se baseline falha:
    encerrar como BASELINE_FAILED
    não promover

se patch é inválido ou só altera testes:
    rejeitar antes da escrita
    não promover

se candidato não passa teste ou review:
    registrar evidência
    não empacotar para ativação

se package/canary/hashes falham:
    bloquear candidato
    manter build ativo

se owner não aprovou:
    permanecer READY_TO_ACTIVATE

se owner aprovou o mesmo candidato:
    ativar transacionalmente
    monitorar
    commit se coerente
    rollback se health falhar
    owner resolve se a evidência ficar ambígua
```

## 14. Critério final de “Autopilot Total”

A arquitetura só pode ser considerada completa quando o ciclo inteiro for provado, com evidência datada, em vez de apenas por presença de módulos:

- um sinal factual produz uma proposta rastreável;
- a admissão é idempotente e limitada por policy;
- a missão tem plano, escopo, lease, deadline e orçamento;
- o candidato é criado fora da produção e a baseline é preservada;
- o patch é verificável e os testes distinguem baseline de candidato;
- uma revisão independente pode bloquear a mudança;
- o pacote e o canário identificam os mesmos artefatos;
- a aprovação do owner é vinculada ao candidato exato;
- a ativação preserva known-good e journal;
- o monitoramento decide entre commit e rollback;
- restart, timeout, crash, drift, quota, provider ausente e falha de verifier têm estados honestos;
- nenhuma resposta anuncia capacidade, provider, sucesso ou build ativo sem evidência correspondente.

Até que todos esses pontos tenham prova no ambiente relevante, a descrição correta é **Autopilot governado em implementação incremental**, e não autonomia total irrestrita.

## Referências

[1]: ../ZARA_MASTER_CONTEXT.md "ZARA 3.0 — Contexto Mestre Canônico"

[2]: ./AUTOPILOT_BUILD_E_TESTE.md "ZARA 3.0 — Build e teste físico do Autopilot"

[3]: ../GATES.md "Gates: ZARA low-cost workforce and release readiness"

[4]: ../core/lab_v1/candidate_source.py "Bounded real-source snapshots for ZARA Lab repair candidates"

[5]: ../core/lab_v1/release.py "Durable gates for candidate package, canary, activation, monitor and rollback"

[6]: ../core/lab_v1/service.py "ZARA LAB REAL V1 — service and improvement scheduler"

[7]: ../core/lab_v1/supervisor.py "Persistent opt-in supervisor"

[8]: ../core/tool_router.py "Tool Router — Deterministic routing of tool requests to execution"

[9]: ../tests/test_lab_daily_autonomy.py "Tests for daily autonomy loop, deduplication and budget"

[10]: ../tests/test_lab_operation_ledger.py "Tests for durable idempotent operation admission"

[11]: ../tests/test_lab_source_promotion.py "Tests for transactional source promotion and rollback"

[12]: ../tests/test_lab_candidate_source.py "Tests for bounded candidate source snapshots and edits"

## Validação deste documento

Este arquivo foi criado como documentação nova, sem uso de rede ou providers. Não foram alterados build ativo, banco, memória, frontend ou arquivos existentes. A validação realizada deve limitar-se a conferir a presença do arquivo, a estrutura Markdown e o diff da própria documentação; testes de runtime não são necessários nem foram alegados para esta tarefa.
