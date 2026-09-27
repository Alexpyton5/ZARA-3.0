# Plano da Agência ZARA 3.0

**Status:** plano de execução futura. Esta entrega não autoriza nem executa alterações no runtime, nos builds, nas memórias, nos bancos, nos testes ou nos artefatos protegidos.

**Data-base das auditorias:** 17/09/2026.  
**Coordenação:** coordenação técnica da ZARA 3.0.  
**Regra de precedência:** código e evidência recente prevalecem sobre relatórios históricos; o ponteiro `ZARA_ACTIVE_BUILD.json` prevalece sobre referências antigas de build.

## 1. Decisão executiva

A agência deve trabalhar em três trilhas separadas e não intercambiáveis:

1. **Limpeza segura:** inventário, classificação e eventual arquivamento reversível de caches, cópias, planos e saídas regeneráveis. Não altera comportamento, não promove capacidade e não apaga dados.
2. **Refatoração:** mudanças de código, contratos, testes ou pipeline. Só começa depois do mapeamento de callers, da decisão arquitetural correspondente e de uma janela exclusiva de escrita por arquivo.
3. **Decisões do proprietário:** escolhas sobre fonte de verdade, promoção de build, ativação de scheduler, providers, Lab, memória, UI, integrações, descarte e capacidade de produção. A coordenação prepara evidência e recomendação, mas não decide em nome do proprietário.

A ordem obrigatória é **congelar invariantes → reconciliar evidência → mapear callers e dependências → decidir arquitetura → limpar de modo reversível → refatorar uma superfície por vez → validar em Linux protegido → validar no Windows empacotado → decidir promoção**. Nenhuma fase posterior pode contornar uma anterior.

### Prioridade do proprietário — 17/09/2026

O proprietário definiu a ordem de produto: **não iniciar novas pesquisas externas nem novas capacidades antes de fazer o que já existe funcionar corretamente**. A agência deve priorizar, nesta sequência:

1. organizar e simplificar a documentação, os diretórios e os caminhos duplicados;
2. limpar lixo, caches, cópias e artefatos somente de forma reversível e sem tocar em dados, memória, bancos, evidências ou build ativo;
3. mapear e corrigir problemas do código existente, preservando os gates de segurança;
4. testar backend, frontend, IPC, memória, voz condicionada, ações, build e runtime empacotado, separando testes puros de testes físicos;
5. reconciliar e estabilizar o Lab V1 e o Lab legado, sem misturar os dois;
6. somente depois transformar o ZARA Lab em laboratório vivo e ativar o modo Autopilot com tarefas, supervisão, custo, auditoria, rollback e estado real.

O Autopilot não deve ser ligado durante as fases de limpeza, reconciliação ou validação. A existência de 291 definições em `.codex/agents/` e de 313 agentes exibidos pelo aplicativo não autoriza iniciar todos simultaneamente; a agência deve escalar por fases, com um escritor por arquivo e revisão por domínio.

O estado atual não é uma capacidade única e homogênea. Há um caminho ativo de Electron/React, sidecar Python, ações com gates, múltiplos stores de memória, Lab V1 e Lab legado paralelo. Há também componentes condicionais de voz, providers, navegador, Windows, plugins, automação e módulos experimentais. A presença de código, alias, relatório, plano ou adapter não prova que a capacidade está autenticada, empacotada, disponível, autorizada ou validada.

## 2. Limites imediatos e invariantes

Até que este plano seja aprovado e uma ordem de mudança seja aberta, fica proibido:

- alterar, apagar ou mover qualquer arquivo de runtime, build, teste, memória, histórico, banco, vault, snapshot ou evidência;
- criar o diretório `integrations/`; as integrações Telegram e bridges existentes permanecem nos módulos opcionais de `core/` até decisão arquitetural;
- substituir ou remover `ActionRegistry`, `ToolRegistry`, `ToolRouter`, `core/lab_coordinator.py`, `core/lab_v1/` ou qualquer banco de Lab;
- ativar providers pagos, chamadas externas, voz física, navegador live, hardware ou testes com efeitos reais; o scheduler de melhorias foi ativado em 17/09/2026, mas continua subordinado à workforce policy, orçamento, deduplicação, verificação e escopo do Lab;
- alterar `--restricted` ou o `cwd` neutro do adapter Claude CLI, os gates de capability/risco/confirmação/verificação ou a separação entre `lab/zara_lab.db` e `lab/zara_lab_v1.db`;
- promover Hermes, Supercérebro, módulos `.bak`, planos `.unlazy`, placeholders ou relatórios históricos a runtime;
- trocar o build apontado por `ZARA_ACTIVE_BUILD.json`, executar o caminho paralelo `tools/build_candidate.py` ou sobrescrever evidência histórica para fazê-la parecer atual;
- sincronizar `docs/vault/Zara-Memoria/` com o vault físico sem confirmar o caminho do Obsidian e registrar proveniência.

O único arquivo produzido por esta missão é este plano. Não houve execução de testes, build, launcher, provider, hardware, rede, Electron, limpeza ou migração.

## 3. Papéis, autoridade e regra de um escritor por arquivo

A coordenação técnica mantém a ordem, o registro de decisões, a matriz de dependências e os gates. O proprietário aprova decisões irreversíveis, promoção de capacidade, mudança de política, descarte, ativação de custo ou exposição externa. Cada domínio possui um responsável técnico; isso não concede autorização para alterar arquivos protegidos sem uma ordem aprovada.

A regra operacional é **um escritor por arquivo em cada janela de mudança**. Um responsável pode escrever vários arquivos somente quando estiverem explicitamente no mesmo change set e nenhum outro responsável estiver escrevendo um arquivo do conjunto. Arquivos gerados devem ter um único produtor automatizado; não recebem edição manual concorrente. Revisores não escrevem durante a mesma janela.

| Arquivo ou conjunto | Escritor responsável padrão | Condição de escrita | Revisão obrigatória |
|---|---|---|---|
| `docs/PLANO_DA_AGENCIA_ZARA.md` | Coordenação técnica | Atualização coordenada deste plano | Proprietário se mudar ordem, escopo ou decisão |
| `main.py`, `core/ipc_handlers.py` | Responsável Backend/IPC | Janela exclusiva; callers mapeados | Segurança, testes IPC e proprietário se houver mudança de gate |
| `core/action_registry.py`, `core/tool_registry.py`, `core/tool_router.py`, `core/actions/**` | Responsável Execução Segura | Não criar terceiro caminho; fallback preservado | Backend/IPC, segurança e testes puros |
| `core/lab_v1/**` | Responsável Lab V1 | Não misturar com Lab legado; contratos preservados | Coordenação, segurança, build e Windows |
| `core/lab_coordinator.py`, banco legado | Responsável Compatibilidade Lab | Só após mapa de callers e decisão explícita | Proprietário e Lab V1 |
| `memory/**`, `core/obsidian_bridge.py`, `docs/vault/Zara-Memoria/**` | Responsável Memória/Dados | Autoridade, redaction e migração definidos | Segurança, privacidade e Windows/Obsidian |
| `frontend/src/**`, `frontend/package.json` | Responsável Frontend/Electron | Uma superfície por vez; Home ativa preservada | Backend IPC, QA visual, build e Windows |
| `tests/**`, `tests/conftest.py`, `.zara-tests/**` | Responsável Testes/Qualidade | Guards e evidência preservados | Coordenação e domínio afetado |
| `tools/**`, `build_exe.py` | Responsável Build/Release | Pipeline canônico; sem atalho paralelo | Testes, hashes, segurança e proprietário |
| `ZARA_ACTIVE_BUILD.json`, `BUILD_INFO.json`, manifests e release | Pipeline de Release | Só na ativação atômica de build validado | Hashes, launcher, rollback e proprietário |
| `ZARA_AGENT_START_HERE.md`, `ZARA_MASTER_CONTEXT.md` | Curadoria Documental | Atualizar apenas após evidência comprovada | Coordenação e proprietário |
| `_quarentena/**`, `.unlazy/**`, `artifacts/**` | Curadoria de Evidência | Não executar; movimento reversível autorizado | Coordenação, QA e proprietário |

Antes de cada mudança, a ordem deve registrar caminhos exatos, escritor, revisor, dependências, comandos de validação, backup/rollback, janela de escrita e critério de abortar. Change sets que toquem o mesmo arquivo são serializados; não haverá merge informal de edições concorrentes.

## 4. Ordem macro de execução

| Ordem | Fase | Trilha | Dono | Saída obrigatória | Gate de passagem |
|---:|---|---|---|---|---|
| 0 | Congelamento e autoridade | Decisão do proprietário | Proprietário + coordenação | Invariantes, responsáveis e escopo protegido | Nenhum runtime/build alterado |
| 1 | Reconciliação somente leitura | Preparação | Coordenação + domínios | Baseline datada de callers, build, testes, dados e evidências | Divergências registradas |
| 2 | Reachability e dependências | Preparação | Backend, Frontend, Lab, Memória e QA | Caller → arquivo → contrato → teste → ambiente | Nada ativo apenas por existir |
| 3 | Limpeza reversível | Limpeza segura | Evidência + proprietário | Manifestos, backups e quarentena reversível | Referências, processos e rollback verificados |
| 4 | Decisões arquiteturais | Proprietário | Proprietário apoiado pela coordenação | ADRs sobre ações, Lab, memória, UI, providers e scheduler | Decisão explícita por tema |
| 5 | Refatoração por domínio | Refatoração | Um dono de cada domínio, em série | Patches pequenos e compatibilidade | Gates estáticos e contratuais passam |
| 6 | Validação protegida | Validação | QA/Build + domínios | Relatórios datados Linux/Windows, hashes e limitações | Evidência ligada ao build exato |
| 7 | Promoção ou rollback | Decisão do proprietário | Proprietário + Release | Ponteiro, contexto e rollback registrados | Hashes, launcher, runtime e evidência coincidem |

## 5. Fase 0 — congelamento e autoridade

**Objetivo.** Impedir que uma limpeza, build antigo, script one-shot ou scheduler altere o estado durante a reconciliação.

**Dono.** Proprietário para autorizar; coordenação técnica para registrar.

**Arquivos e superfícies.** `ZARA_ACTIVE_BUILD.json`, `ZARA_MASTER_CONTEXT.md`, `ZARA_AGENT_START_HERE.md`, `frontend/release-candidate-fix-9router-v2-20260917-0020`, `main.py`, `core/ipc_handlers.py`, `core/lab_v1/**`, `core/lab_coordinator.py`, bancos de Lab, `memory/**`, `frontend/src/**`, `tests/**`, `.zara-tests/**`, `tools/**` e `_quarentena/**`.

**Dependências.** Nenhuma alteração de código. É necessário nomear responsáveis e reconhecer o ponteiro de build e as proteções existentes.

**Riscos.** O build ativo registra `GIT_DIRTY=true`; a última evidência agregada disponível é de 05/09 e não comprova o candidato de 17/09. Há risco de iniciar uma refatoração contra uma árvore ou release diferente da usada pelo launcher.

**Validação.** Confirmar, somente por leitura, `BUILD_ID`, commit, branch, método de ativação, diretório apontado e hashes registrados. Confirmar `SCHEDULER_ENABLED=False`, que o launcher lê o ponteiro e que os bancos de Lab continuam separados. Registrar processos de staging e locks antes de qualquer janela futura.

**Saída.** Termo de congelamento no registro de trabalho, sem alterar o repositório. Divergência entre ponteiro, `BUILD_INFO.json`, hashes ou contexto devolve o trabalho à Fase 1.

## 6. Fase 1 — baseline e reconciliação somente leitura

**Objetivo.** Produzir visão única, datada e honesta do que existe, do que é chamado e do que foi validado.

**Dono.** Coordenação técnica, com parecer de cada domínio.

**Arquivos principais.**

- **Backend:** `main.py`, `core/ipc_handlers.py`, registries, `core/actions/**`, `core/zara_orchestrator.py`, `core/model_router.py`, `core/planner/**`, voz e integrações opcionais em `core/`.
- **Frontend:** `frontend/package.json`, `frontend/src/main.ts`, `preload.ts`, `App.tsx`, `main.tsx`, `zara-home/**`, `zara-lab-v2/**`, `renderer/types/global.d.ts` e estilos carregados.
- **Lab:** `core/lab_v1/**`, `core/lab_coordinator.py`, `lab/zara_lab_v1.db`, `lab/zara_lab.db`, `.unlazy/**`, `artifacts/**`.
- **Memória:** `memory/**`, `core/obsidian_bridge.py`, `docs/vault/Zara-Memoria/**` e caminhos persistentes identificados, sem migrar conteúdo sensível.
- **Build/testes:** `ZARA_ACTIVE_BUILD.json`, `BUILD_INFO.json`, launcher, `tools/build_current.py`, `build_exe.py`, validadores, `tests/conftest.py`, `.zara-tests/**`.
- **Documentação/quarentena:** `README.md`, guias de boot, `docs/**`, `_quarentena/**`, scripts e manifestos históricos.

**Dependências.** Fase 0 congelada. Cada domínio entrega callers reais, imports, entry points, testes e requisitos de ambiente. O inventário distingue fonte, adapter, cache, evidência, backup, especificação e runtime.

**Riscos.** A ausência de `integrations/`, a coexistência de dois caminhos de ações, duas famílias de UI, dois Labs e vários stores de memória podem gerar falsa consolidação. Evidência ausente ou diretórios com erro de I/O não devem ser preenchidos por inferência.

**Validação.** Cada item recebe estado **ativo**, **condicional**, **experimental**, **legado**, **artefato** ou **não comprovado**. Cada capacidade liga-se a caller, configuração, teste e data. A divergência entre `.zara-tests/latest.json` e `.zara-tests/latest/ZARA_TEST_REPORT.json` permanece aberta até decisão sobre formato canônico. A contagem histórica de `1139 passed, 8 failed, 27 skipped` não valida o build de 17/09.

**Saída.** `MATRIZ_REACHABILITY_EVIDENCIA_<data>.md` e lista de divergências, sem alterar arquivos auditados. A matriz é pré-requisito para limpeza ou refatoração.

## 7. Fase 2 — limpeza segura, reversível e sem mudança de comportamento

Esta fase não é uma autorização para apagar. “Limpeza segura” significa reduzir ambiguidade sem destruir reversibilidade, dados ou compatibilidade.

### 7.1 Preparação obrigatória

**Dono.** Curadoria de Evidência, com revisão da coordenação e autorização do proprietário para cada movimento.

**Candidatos.** `__pycache__/**`, caches regeneráveis, cópias `.bak`, locks expirados, scripts one-shot, relatórios históricos, saídas geradas, planos `.unlazy/**`, diretórios de artefatos e itens já isolados em `_quarentena/**`. Não são candidatos automáticos: memórias, bancos, histórico, snapshots, vaults, builds apontados, evidências de teste, manifests de baseline e código de runtime.

**Dependências.** Fases 0 e 1 concluídas; busca de referências vivas, atalhos, imports, pipelines, processos e ponteiros; backup ou manifesto de cada item; destino de rollback definido.

**Riscos.** Um `.bak` pode ser importado por script; um artefato pode ser necessário para auditoria; um lock pode representar execução ativa; uma saída antiga pode estar referenciada por documentação ou release. Movimento por idade, tamanho ou nome é proibido.

**Validação.** Antes de mover qualquer item, registrar caminho original, hash, tamanho, origem, referências, motivo e destino. Fechar staging e processos relacionados. Depois de um movimento autorizado, executar busca de imports, checagem do launcher, verificação do ponteiro e teste de restauração em diretório isolado. O relatório deve provar que nenhum arquivo de runtime ou dado persistente foi alterado.

### 7.2 Ações permitidas após autorização

1. **Classificar sem mover.** É a opção padrão para itens ambíguos.
2. **Criar manifesto de quarentena.** O manifesto é escrito pelo responsável de Evidência; não altera o item.
3. **Mover de forma reversível.** Somente para destino versionado, com `MOVIMENTACOES.txt`, hash e procedimento de retorno.
4. **Remover caches regeneráveis.** Apenas depois de confirmar que não são evidência, não estão em uso e que o proprietário autorizou.

Não é limpeza segura promover um caminho legado, atualizar o ponteiro, reconstruir um build, alterar `package.json`, mudar política de provider ou ligar integração. Essas ações pertencem à refatoração ou à decisão do proprietário.

## 8. Fase 3 — decisões que pertencem ao proprietário

A coordenação deve transformar cada item abaixo em um ADR curto, com alternativas, custo, impacto, rollback e decisão. Sem aprovação, o estado atual é preservado.

| Decisão | Pergunta | Opção conservadora recomendada | Arquivos afetados depois da decisão |
|---|---|---|---|
| Execução de ações | `ActionRegistry` ou `ToolRouter` será canônico? | Escolher um caminho; manter o outro como adapter temporário, sem terceiro caminho | `core/ipc_handlers.py`, registries, `core/actions/**`, planner e testes |
| Fonte de verdade de memória | Qual store é autoritativo por domínio? | Declarar autoridade e tratar mirrors como derivados | `memory/**`, `core/obsidian_bridge.py`, docs e migrações |
| Redaction | A política vale para JSON, SQLite, prompts, Markdown, exports e mirrors? | Política única fail-closed com testes em português e inglês | `memory/**`, bridge, exports e testes |
| Lab | O Lab V1 será promovido? Como o legado será mantido? | Preservar os dois bancos até callers e validação empacotada | `core/lab_v1/**`, `core/lab_coordinator.py`, frontend Lab |
| Scheduler | Melhorias em background serão permitidas? | Manter desligado até orçamento, idempotência e observabilidade | `core/lab_v1/service.py`, config e docs |
| Providers | Qual provider está autorizado e disponível? | Exigir probe datado, autenticação, quota, custo e provenance | registry, policy, build e evidência |
| UI | Home/Titanium Emerald e `zara-lab-v2` são canônicas? | Manter superfície ativa; UI antiga isolada até callers comprovados | `frontend/src/**`, estilos e docs |
| Testes | Qual formato de resultado é canônico? | Gerar evidência nova sem sobrescrever histórico | `.zara-tests/**`, tools e docs |
| Build | `tools/build_current.py` é o único caminho de ativação? | Sim, até decisão contrária; não usar `build_candidate.py` operacionalmente | `tools/**`, `ZARA_ACTIVE_BUILD.json` |
| Quarentena | O que pode ser arquivado ou descartado? | Arquivamento reversível, item a item, com autorização | `_quarentena/**`, `.unlazy/**`, `artifacts/**` |
| Obsidian | Qual é o vault físico e o que pode sincronizar? | Confirmar caminho, registrar origem e sincronizar seletivamente | `memory/project_memory.py`, bridge e docs |

## 9. Fase 4 — refatoração em ordem e por domínio

A refatoração só começa quando a decisão correspondente estiver registrada. Cada subfase deve terminar com validação antes da seguinte. Não haverá mudanças simultâneas em `ipc_handlers.py`, `preload.ts`, memória ou pipeline de release.

### 9.1 Execução segura e ações

**Dono.** Responsável de Execução Segura.  
**Arquivos.** `core/ipc_handlers.py`, `core/action_registry.py`, `core/tool_registry.py`, `core/tool_router.py`, `core/actions/**`, `core/planner/**`, contratos e testes de ações.

**Ordem.** Mapear callers. Declarar o caminho canônico. Adaptar o caminho secundário ao canônico sem retirar fallback. Migrar callers em lotes pequenos. Remover compatibilidade somente por decisão.

**Conteúdo mínimo.** Inventariar cada ação com capability, risco, confirmação, fingerprint, auditoria e verifier. Priorizar readback para `terminal_bg`, arquivos, browser, janelas, visão, energia, tarefas, macros e solicitações externas. Manter chamadas diretas fora do registro proibidas. Não transformar `RulePlanner` em planejador autônomo.

**Riscos.** Bypass de permission checker, verifier ou auditoria; confirmação MEDIUM/HIGH inconsistente; retorno `success` sem readback; execução Windows não comprovada em Linux; lock advisory fail-open permitindo dois writers.

**Validação.** Testes puros em `ZARA3_HOME` temporário, sem hardware, rede, provider ou subprocesso real; testes de schema, capability, confirmação, fingerprint, auditoria redigida, fallback e estado verificado/incerto. Depois, Windows live autorizado para uma golden path, uma ação confirmada e readback.

### 9.2 Contrato Electron/React e superfície Lab

**Dono.** Responsável Frontend/Electron.  
**Arquivos.** `frontend/src/main.ts`, `frontend/src/preload.ts`, `frontend/src/renderer/types/global.d.ts`, `frontend/src/renderer/App.tsx`, `frontend/src/renderer/main.tsx`, `frontend/src/renderer/components/zara-home/**`, `frontend/src/renderer/components/zara-lab-v2/**`, `frontend/src/renderer/lib/labDurableOperation.ts`, `useLabRoom.ts`, CSS ativo e `frontend/package.json`.

**Ordem.** Construir a matriz App → ZaraHome → preload → IPC → sidecar. Comparar `preload.ts` com `global.d.ts`. Decidir a nomenclatura `zara-lab-v2` versus backend Lab V1. Consolidar tipos, adicionar checagem de paridade e só então alterar CSS. Corrigir o comentário de timeout de 45 s para 75 s em change set separado de qualquer mudança de runtime.

**Conteúdo mínimo.** Preservar `contextIsolation`, `nodeIntegration`, canais mínimos, confirmação, proveniência, histórico, journal/replay e fallback legado enquanto houver caller comprovado. Substituir o stub de `npm test` por runner real ou declarar formalmente ausência de cobertura; ele não pode continuar sendo tratado como evidência.

**Riscos.** Drift entre tipos e ponte real; reativação acidental da família `zara/**`; regressão global de CSS; confusão entre admissão `QUEUED` e conclusão; placeholders de identidade, nuvem, segurança e progresso anunciados como dados reais.

**Validação.** `npm run typecheck`, `npm run lint`, `npm run build`, smoke da Home e do Lab, paridade de API, testes de histórico/proveniência/confirmação e replay após restart. Depois, Electron empacotado no Windows com sidecar, janela, texto, confirmação, interrupt, voz condicionada e operações Lab persistentes.

### 9.3 Memória, privacidade e Obsidian

**Dono.** Responsável Memória/Dados, com revisão de segurança e do proprietário.  
**Arquivos.** `memory/memory_manager.py`, `episodic_memory.py`, `user_memory.py`, `project_memory.py`, `shared_second_brain.py`, `second_brain_composition.py`, `memory_context.py`, `core/obsidian_bridge.py`, documentação e testes de memória.

**Ordem.** Decidir autoridade e retenção. Definir redaction única. Endurecer bridge e mirrors. Só depois planejar migração ou reindexação. Limpeza de banco ou vault fica fora desta fase até backup e decisão separada.

**Conteúdo mínimo.** Definir precedência entre `long_term.json`, episódios, fatos de usuário, projeto, histórico, stores paralelos, Lab, Obsidian e índices derivados. Validar traversal, `category`, `title`, frontmatter, escrita atômica, recuperação de índice corrompido, links, deduplicação e sinalização de mirror atrasado. Documentar `nomic-embed-text`, dimensão 768, fallback offline, timeout e comportamento sem Ollama. Revisar `mark_used`, que não deve afirmar uso pelo modelo sem evidência.

**Riscos.** Divergência entre stores; conteúdo sensível chegando a Markdown; vault físico não confirmado; filtro de segredos inconsistente; contexto parcial tratado como completo; vetor incompatível; busca lexical com baixa recuperação.

**Validação.** Testes de redaction em português e inglês, traversal, crash entre arquivo e índice, corrupção de índice, links, deduplicação, migração, retenção, fallback sem Ollama e envelopes com orçamento/degraded. No Windows, confirmar vault físico, espelhamento seletivo e proveniência. Nenhuma nota ou banco real deve ser apagado durante a validação.

### 9.4 Lab V1, Lab legado e módulos experimentais

**Dono.** Responsável Lab V1.  
**Arquivos.** `core/lab_v1/domain.py`, `store.py`, `runtime.py`, `service.py`, `providers/**`, `execution_scope.py`, `workforce_policy.py`, `artifact_verifier.py`, `audit_contract.py`, `sandbox_actions.py`, `autopilot.py`, `mission_controller.py`, `supervisor.py`, `core/lab_coordinator.py`, bancos e UI correspondente.

**Ordem.** Reconciliar evidência referenciada com `artifacts/`. Mapear IPC/build. Provar separação dos bancos. Sondar adapters sem considerar catálogo como disponibilidade. Executar prova atual com provider real somente com autorização. Só depois discutir promoção ou consolidação.

**Conteúdo mínimo.** Preservar `PROVIDER != MODEL != AGENT != ROLE != TEAM != SESSION`, handoff sem recriar sessão, não armazenamento de chain-of-thought, leases, receipts, verificação, idempotência, failover, self-delegation guard e `--restricted`. `submit()` e `QUEUED` significam admissão/estado persistido, não conclusão fabricada. `core/lab_coordinator.py` e `lab/zara_lab.db` permanecem compatibilidade até mapa de callers.

**Riscos.** Mistura dos dois bancos; promoção por relatório histórico; probe de CLI confundido com autenticação/quota; autopilot e scheduler confundidos com autonomia 24/7; Hermes ou `.bak` importados acidentalmente; evidência ausente em `artifacts/`.

**Validação.** Windows/live autorizado com provider, persistência, restart, failover, self-delegation, handoff, confirmação de banco legado intacto e prova de que agentes não obtêm shell arbitrário. O scheduler permanece desligado, salvo sandbox isolado expressamente autorizado.

### 9.5 Pipeline de teste e release

**Dono.** Responsável Testes/Qualidade para evidência; Responsável Build/Release para empacotamento; proprietário para ativação.

**Arquivos.** `build_exe.py`, `tools/build_current.py`, `tools/launch_current.ps1`, `tools/build_manifest.py`, `tools/zara_validate.py`, `tools/zara_selftest.py`, `tools/quality_gate.py`, `tests/conftest.py`, `tests/**`, `.zara-tests/**`, `ZARA_ACTIVE_BUILD.json`, `BUILD_INFO.json` e release.

**Ordem.** Classificar testes por ambiente. Reproduzir as oito falhas conhecidas isoladamente. Escolher formato canônico. Executar validação Linux protegida. Construir em staging pelo pipeline canônico. Validar hashes e launcher. Executar Windows empacotado. Solicitar promoção somente depois.

**Conteúdo mínimo.** Preservar guards de `ZARA_TEST_MODE`, `ZARA3_HOME`, lock, SQLite e `ALLOW_LIVE_TESTS`. Tratar como conhecidas, até nova prova, as quatro falhas de `test_remote_approval_e2e.py`, duas de `test_system_env_and_files_list_safety.py` e duas de `test_voice_usability.py`. Não editar baseline para mascarar falhas. Não usar `tools/build_candidate.py` para ativar.

**Riscos.** Evidência velha; dirty tree; divergência source-versus-packaged; testes live no Linux; scripts com efeitos fora do staging; sobrescrita de latest/histórico; hardcode de caminho Windows no teste de microfone.

**Validação.** Em Linux, executar apenas testes puros ou protegidos, além de `compileall`, `ruff`, `pytest`, typecheck, lint e build conforme scripts canônicos. Em Windows, conferir `BUILD_ID`, commit, `BUILD_INFO`, SHA-256 de EXE/ASAR/backend, sidecar, preload, IPC, ação confirmada, voz, interrupt, Lab e rollback. A evidência nova deve conter timestamp, branch, commit, dirty state, modo, ambiente, nodeids, falhas, skips, hashes e limitações.

## 10. Registro de riscos e controles obrigatórios

| Risco | Controle antes da mudança | Critério de bloqueio |
|---|---|---|
| Dois writers em SQLite/WAL ou JSON | Lock de processo, `ZARA3_HOME` temporário e teste de concorrência isolado | Colisão, corrupção ou lock fail-open sem mitigação |
| Dois caminhos de ações | Mapa de callers e decisão de caminho canônico | Caller sem gate, schema, verifier ou auditoria |
| Alto impacto em terminal, browser, energia, macros e tarefas | Capability, risco, confirmação, fingerprint, readback e auditoria | `success` sem verificação ou chamada fora do registry |
| Provider declarado mas indisponível | Probe datado, auth, quota, custo, modelo reportado e fallback | Catálogo ou alias usado como prova |
| Scheduler ou background com custo real | Off por padrão, orçamento, idempotência, backoff e observabilidade | Ativação implícita ou sem rollback |
| Mistura Lab V1/legado | Bancos separados, callers mapeados e smoke de persistência | Consulta/escrita no banco errado ou conclusão fabricada |
| Segredo em memória, prompt ou vault | Redaction única, testes bilíngues, exports e mirrors cobertos | Divergência de política entre stores |
| Regressão de UI/IPC | Contrato único/paridade, smoke Home/Lab e build empacotado | `preload.ts` e `global.d.ts` divergentes |
| Limpeza destrutiva | Manifesto, hash, referência, backup, movimento reversível e restauração | Item sem proveniência, processo ativo ou rollback |
| Build não reprodutível | Staging confinado, manifesto, hashes, launcher e ponteiro atômico | Hash/BUILD_ID divergente ou dirty state omitido |
| Evidência histórica confundida com atual | Relatório datado ligado ao build exato | Contagens antigas usadas como aprovação |
| Reintrodução de Hermes/Supercérebro | Allowlist de imports e revisão de quarentena | Promoção de `.bak`, Hermes ou conceito removido |

## 11. Pacote mínimo de validação e evidência

Cada change set aprovado deve responder: **qual código foi testado, em qual build, em qual ambiente, com quais efeitos e com qual resultado**.

### 11.1 Validação estática e isolada

- `compileall` para o backend, sem importar integrações externas que iniciem processos;
- `ruff` e `pytest` com guards existentes, usando `ZARA3_HOME` temporário e sem hardware/live;
- `npm run typecheck`, `npm run lint` e `npm run build` quando o change set tocar frontend;
- testes de contrato para IPC, registries, gates de confirmação, provenance, redaction, memória, Lab, manifest e higiene;
- `tools/zara_validate.py` somente no modo coerente com o ambiente e sem sobrescrever evidência anterior;
- verificação de que scheduler, integrações externas, provider pago, navegador live, microfone e writes de hardware continuam desligados.

### 11.2 Validação empacotada no Windows

Para o `BUILD_ID` exato de `ZARA_ACTIVE_BUILD.json`:

1. conferir `BUILD_INFO.json`, commit, branch, dirty state e SHA-256 de EXE, ASAR e backend;
2. iniciar exclusivamente por `tools/launch_current.ps1`;
3. provar spawn e prontidão do sidecar, preload e canais permitidos;
4. testar texto, histórico, proveniência, confirmação e uma ação de baixo risco com readback;
5. testar Lab V1 com persistência, restart, handoff, failover e separação do banco legado, usando provider autorizado;
6. testar voz, interrupt, AEC, STT/TTS e barge-in somente se dispositivo, pacotes, pesos, rede e autorização estiverem presentes;
7. testar rollback ou a capacidade de restaurar o build anterior sem tocar nos dados do usuário;
8. registrar todos os caminhos não testados.

Nenhum teste live pode ser marcado como aprovado por ausência de erro sem readback ou evidência observável. `QUEUED`, `available` de probe ou `verifier=False` mantêm o estado correspondente no relatório.

### 11.3 Critério de promoção

Um build ou refatoração só pode ser promovido se:

- código, hashes, `BUILD_ID`, launcher e relatório apontarem para o mesmo artefato;
- testes relevantes tiverem ambiente e escopo classificados;
- falhas conhecidas estiverem reproduzidas ou explicadas, sem serem apagadas da baseline;
- invariantes de segurança e separação de dados estiverem preservadas;
- scheduler, provider, integração ou capacidade nova não estiverem ativados sem decisão;
- o proprietário aprovar a promoção e o rollback estiver documentado;
- `ZARA_MASTER_CONTEXT.md`, `ZARA_AGENT_START_HERE.md` e documentação de produto forem atualizados somente depois da evidência nova.

## 12. Checklist de encerramento por fase

O responsável deve entregar uma resposta curta e verificável:

- **Escopo:** caminhos lidos ou alterados;
- **Escritor:** responsável único por cada arquivo;
- **Dependências:** decisões, fases e ambientes necessários;
- **Mudança:** nenhuma, reversível ou comportamental;
- **Evidência:** comandos, timestamp, commit, hashes, ambiente e resultado;
- **Riscos residuais:** limitações não resolvidas;
- **Rollback:** procedimento e localização de backup/manifesto;
- **Próximo gate:** condição objetiva de passagem ou motivo do bloqueio.

A coordenação rejeita entregas que apresentem apenas “build verde”, “provider disponível”, “Lab aceito”, “memória sincronizada” ou “teste passou” sem informar o artefato exato, o ambiente e a observação que sustenta a afirmação.

## 13. Resultado esperado da agência

Ao final de um ciclo aprovado, a ZARA 3.0 deverá ter uma cadeia explícita **fonte → build → launcher → runtime → evidência**, um caminho canônico de execução de ações, uma superfície canônica de Lab, uma política documentada de memória e redaction, uma ponte IPC tipada e verificada, e um inventário de módulos experimentais que não confunda presença com produção.

Até que esses resultados sejam comprovados, a agência deve preferir **preservar e marcar como condicionado** a remover, promover ou reescrever. A ausência de uma decisão é uma decisão de conservação: scheduler desligado, bancos separados, gates ativos, build apontado intacto, dados protegidos e artefatos históricos reversíveis.

## Referências

[1]: ../ZARA_MASTER_CONTEXT.md "Contexto mestre consolidado da ZARA 3.0"

[2]: ../ZARA_AGENT_START_HERE.md "Ponto de entrada operacional e ordem das fontes de verdade"

[3]: ../ZARA_ACTIVE_BUILD.json "Ponteiro operacional do build ativo"

[4]: ../tools/build_current.py "Pipeline canônico de build, staging, ativação e rollback"

[5]: ../tools/launch_current.ps1 "Launcher que confere BUILD_ID e hashes antes de iniciar"

[6]: ../tests/conftest.py "Guards da suíte de testes para ambiente, hardware, lock e dados"

[7]: ./ZARA_DOCUMENTACAO_UNICA.md "Resumo técnico e humano da arquitetura ativa"

[8]: ./ORGANIZACAO_REPOSITORIO_2026-09-17.md "Registro de organização reversível e itens preservados"

[9]: ./ZARA-LAB-PRODUCT-CONTRACT.md "Contrato de produto do Lab, tratado como especificação proposta"

[10]: ./ZARA-OFFICIAL-AI-FEASIBILITY.md "Pesquisa e proposta de viabilidade de providers, MCP e voz"

[11]: ./roadmap-perpetuo.md "Roadmap aspiracional, não evidência de runtime ou release"

[12]: ./vault/Zara-Memoria/04-MEMORIA-E-OBSIDIAN.md "Regras documentais de memória e sincronização com Obsidian"

[13]: ../tools/zara_validate.py "Validação técnica determinística e produção de evidência"

[14]: ../tools/zara_selftest.py "Autoteste condicionado a ambiente, build e hardware apropriados"

[15]: ../core/lab_v1/providers/claude_cli.py "Adapter Claude CLI com escopo restrito e cwd neutro"

[16]: ../core/obsidian_bridge.py "Bridge local mínima para projeção compatível com Obsidian"

[17]: ../memory/memory_manager.py "Fachada de memória de longo prazo e exportação redigida"

[18]: ../frontend/src/preload.ts "Ponte contextBridge do Electron"

[19]: ../frontend/src/renderer/App.tsx "Entry point da shell React ativa"

[20]: ../core/action_registry.py "Registro e execução protegida de ações"

[21]: ../core/tool_router.py "Roteamento unificado de ferramentas com fallback de compatibilidade"

[22]: ../core/lab_v1/service.py "Fachada assíncrona, operações duráveis e scheduler subordinado a opt-in"

[23]: ../.zara-tests/latest.json "Última evidência agregada registrada, anterior ao build de 17/09/2026"

[24]: ../frontend/package.json "Scripts oficiais, dependências e empacotamento Electron"
