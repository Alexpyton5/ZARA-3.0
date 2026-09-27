# Status do Autopilot Seguro — ZARA

**Data de referência:** 2026-09-18  
**Escopo desta nota:** documentação do que já existe, limites reais de execução contínua, gates, memória e ordem de integração.  
**Regra de alteração:** esta tarefa altera somente este arquivo e `docs/PLANO_EXECUCAO_AUTOPILOT_SEGURO.md`; não altera código, build ativo, banco, memória do usuário ou arquivos de outros agentes.

## Status executivo

**Estado:** `PARCIAL — AUTOPILOT GOVERNADO EM IMPLEMENTAÇÃO INCREMENTAL`.

A ZARA já possui código real para sidecar Python, IPC Electron, registro e roteamento de ações, Lab V1, supervisor persistente, scheduler, orçamento, deduplicação, backoff, ledger idempotente, memória de projeto, snapshot de candidato e fila de release. Isso é base de um ciclo governado; não é evidência de autonomia total irrestrita, de decomposição geral de objetivos ou de um Windows empacotado operando 24/7 sem a aplicação aberta.

## O que já existe

| Área | Evidência local | Estado factual |
|---|---|---|
| Execução desktop | `main.py`, `frontend/src/main.ts`, `frontend/src/preload.ts`, `core/ipc_handlers.py` | Sidecar e ponte IPC existem; execução bem-sucedida depende do runtime correspondente. |
| Ações | `core/action_registry.py`, `core/actions/`, `core/tool_router.py` | Há caminho determinístico de validação → permissão → execução → verificação → auditoria. Não criar executor paralelo. |
| Lab | `core/lab_v1/` | Há sessões, agentes, tarefas, eventos, handoffs e runtime V1. O Lab legado não é a fonte do Lab V1. |
| Supervisão | `core/lab_v1/supervisor.py` | Policy persistida, gate entre processos, orçamento diário, prioridade do owner, dedup, backoff e tick local. |
| Scheduler | `core/lab_v1/service.py` | `ImprovementScheduler` persiste seu estado em SQLite, evita spin, aplica cadência/backoff e não chama provider para decidir se há trabalho. |
| Admissão | `core/lab_v1/operation_ledger.py` | `request_id` tem ACK durável; replay igual é idempotente; payload diferente gera `IDEMPOTENCY_CONFLICT`. |
| Memória | `memory/project_memory.py`, `memory/`, `LabStore` | SQLite/Markdown, contexto por projeto e espelho Obsidian best-effort; contexto é limitado e seletivo. |
| Release | `core/lab_v1/candidate_source.py`, `core/lab_v1/release.py`, `tools/build_current.py` | Há isolamento, manifest, baseline/candidato, pacote, canário, approval gate, journal e rollback previstos. |

## Limite real de 24/7

O processo implementado é **contínuo enquanto a ZARA está aberta e o sidecar está vivo**. `LabV1Service.start_background()` cria tarefas `asyncio` para consumidor de operações e supervisor; `start_scheduler()` cria a tarefa do scheduler. `activate_autopilot()` persiste a política e informa `CONTINUOUS_WHILE_ZARA_OPEN`.

Isso não prova 24/7 independente do aplicativo. Fechar a ZARA, terminar o sidecar, crash, logout, suspensão/hibernação, reinício do Windows, falha de volume, falta de memória ou indisponibilidade de rede interrompem o processo em memória. Há recuperação de operações duráveis no próximo boot, mas não foi demonstrado nesta tarefa um Windows Service, Task Scheduler, watchdog externo, restart automático, máquina ligada ou heartbeat observado por 24 horas. A frase operacional correta é:

> **Background contínuo enquanto a ZARA está aberta; recuperação durável após reinício quando o processo volta.**

Cadências observadas não são SLA: policy de supervisor com `cadence_seconds` padrão de 60 s; scheduler com piso de polling de 30 s; intervalo base de ciclo de 900 s; backoff máximo de 21.600 s. Budget, dedup, prioridade do owner e pausa podem bloquear nova missão mesmo com o processo vivo. `SCHEDULER_ENABLED = True` permite o recurso no source atual, mas não prova que a tarefa foi iniciada ou está `RUNNING`.

## Gates de aceitação

A transição deve ser monotônica, salvo `ROLLED_BACK` ou `BLOCKED`, e sempre derivada de evidência. O ACK `QUEUED`/`ADMITTED` é persistência, não conclusão.

| Gate | Evidência mínima | Saída se falhar |
|---|---|---|
| G0 autoridade | Policy, ledger e promoções pendentes coerentes | `BLOCKED` |
| G1 sinal | Origem, timestamp, hash e escopo factual | `PROPOSAL_ONLY_UNSUPPORTED` |
| G2 admissão | ACK, `operation_id`, dedup e orçamento | `DUPLICATE` / `PAUSED` / `BUDGET_EXHAUSTED` |
| G3 missão | Plano finito, limites, lease, deadline e aceite | `MISSION_REJECTED` |
| G4 isolamento | Snapshot/manifest allow-listed fora da produção | `CANDIDATE_SANDBOX_REJECTED` |
| G5 baseline | Receipt separado com comando e exit code | `BASELINE_FAILED` |
| G6 patch | Diff bounded com alteração de source autorizada | `PATCH_DRAFT_REJECTED` |
| G7 candidato | Testes, regressões, verifiers e artefatos | `CANDIDATE_TEST_FAILED` |
| G8 revisão | Revisor independente e `PASS` | `INDEPENDENT_REVIEW_BLOCKED` |
| G9 pacote | Instalador, EXE, `BUILD_INFO`, `SOURCE_MANIFEST`, backend e hashes | `CANDIDATE_ARTIFACT_DRIFT` |
| G10 canário | Mesmo ASAR e backend do pacote | `PACKAGED_CANARY_NOT_PASSED` |
| G11 owner | Aprovação específica por candidato e hashes | `AWAITING_OWNER_APPROVAL` |
| G12 ativação | Journal, known-good, backup e promoção transacional | `BLOCKED` + restauração |
| G13 saúde | Health do pacote exato no ambiente exigido | `ROLLED_BACK` |
| G14 commit | Journal `COMMITTED`, pointer e hashes coerentes | `RECONCILIATION_NEEDS_OWNER` |

Voz, microfone, browser, hardware e Electron empacotado devem permanecer `NOT_LIVE_VERIFIED` quando não executados no Windows real e no candidato exato.

## Memória e limites de contexto

A memória operacional do Lab fica no SQLite/`LabStore`, incluindo operações, ACKs, tarefas, eventos, leases, policy e journals. A memória do projeto fica em `%LOCALAPPDATA%\\ZARA3\\data\\project-memory\\project_memory.db`, Markdown interno, `mentor_context_latest.md` e `vault/projects/<project_id>/`. O espelho do Obsidian é opcional/best-effort: o caminho é descoberto pelo `obsidian.json` real e a escrita ocorre em `Zara-Memoria`; vault ausente ou desconectado não invalida a memória interna.

`ProjectMemory.build_project_context()` seleciona projeto ativo ou explícito, rejeita chaves ausentes e aplica orçamento padrão de 4096 bytes. `project_id` é obrigatório no envelope; itens menos prioritários podem ser omitidos e o envelope fica marcado como degradado. O vault não deve ser despejado inteiro em prompts. Não registrar segredos, tokens, `.env`, raciocínio privado ou texto externo como autorização. Persistência não prova recuperação perfeita, relevância automática nem injeção global em cada decisão.

## Ordem de integração

1. Governança: uma policy, um ledger, um `ToolRouter`, uma fila de release; inventariar antes de ligar módulos.
2. Admissão: evidência factual, `request_id`, hash, dedup, orçamento, pause e backoff.
3. Missão bounded: plano explícito, limites, `ExecutionScope`, lease e deadline.
4. Sandbox e baseline: snapshot allow-listed fora da produção; baseline separada.
5. Patch e testes: mudança de source limitada, regressões, invariantes e verifiers.
6. Revisão independente: diff, risco, receipts e drift.
7. Pacote e canário: artefatos completos e mesmo ASAR/backend, sem mover pointer.
8. Owner e ativação: aprovação específica, journal, known-good e promoção transacional.
9. Health: commit somente após verificação; rollback em falha; owner resolve journal ambíguo.
10. Recorrência: somente depois dos gates; scheduler com orçamento, dedup, backoff, prioridade e pausa.

A taxonomia de evidência permanece `SOURCE → TEST → RUNTIME_AUTOMATED → PACKAGED_RUNTIME → PHYSICAL_BY_ALEX → VOICE_PHYSICAL`.

## Validação desta documentação

Foram consultados o plano existente, a arquitetura Autopilot, o procedimento de build/teste, a documentação única, o roadmap, o contrato do Lab, o supervisor, o serviço Lab V1, o ledger e a memória de projeto. Este trabalho não executou providers, não iniciou o Windows/Electron, não alterou o build ativo e não alegou teste físico. Após salvar, os dois arquivos devem ser relidos e sua existência conferida no filesystem.

## Limitações abertas

- Planejamento autônomo geral de linguagem natural permanece não provado; o caminho seguro exige passos explícitos válidos.
- Scheduler e supervisor são tarefas no processo; não há prova de 24/7 com o app fechado.
- Providers, voz, browser, hardware, microfone e runtime empacotado dependem de configuração e teste no ambiente correto.
- Configuração ou registro de provider não prova autenticação, quota, custo, latência ou qualidade.
- Memória persistida e espelho Obsidian não significam contexto global automático.
- Um instalador existente não autoriza ativação; source, ASAR, backend, canário, owner approval, health e rollback continuam obrigatórios.
