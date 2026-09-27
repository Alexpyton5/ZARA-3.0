# Plano de execução seguro — ZARA Autopilot

## Regra de volume

Cada etapa deve seguir esta ordem: editar poucos arquivos → salvar → reler os arquivos alterados → validar sintaxe/teste → registrar resultado. Se o volume desconectar, parar imediatamente e não declarar sucesso.

## Etapas

1. **Checkpoint inicial**: confirmar montagem, registrar data, arquivos-alvo e estado atual. Não alterar build ativo.
2. **Autopilot contínuo**: fechar o ciclo observar → planejar → executar pela política → verificar → registrar aprendizado → criar proposta. Limitar retry e pausar em erro.
3. **Memória central**: confirmar vault real, indexar notas, separar fatos/decisões/missões/skills/pesquisas e manter cache como derivado.
4. **Controle Windows**: reutilizar ActionRegistry/ToolRouter; adicionar somente ações com risco, confirmação e verificação pós-ação.
5. **Pesquisa e ingestão**: capturar fontes, transcrever quando possível, resumir com URL/data/evidência e gravar no Obsidian sem segredos.
6. **Skills**: usar DRAFT → TESTING → READY → ACTIVE → RETIRED, com teste, aprovação, permissões e rollback.
7. **9 Router**: validar no Windows executável, autenticação, modelos e chamada real. Registro de modelo não conta como prova.
8. **Build**: gerar candidato separado, verificar cinco artefatos, instalar somente depois da validação e executar teste físico.

## Estados de entrega

- **Codado**: arquivo salvo e relido.
- **Validado**: teste executado com resultado registrado.
- **Pronto**: validado no Windows real e, quando aplicável, dentro do instalador.

## Proibições

Não apagar dados, não sobrescrever build ativo, não afirmar que o Lab é 24/7 com o app fechado, não afirmar que um provider funciona apenas porque está configurado e não continuar editando durante falha de volume.

## Estado factual consolidado em 2026-09-18

Este plano descreve o **Autopilot governado em implementação incremental**. O repositório já contém peças reais para admissão, supervisão, memória, missão limitada, candidato isolado, testes e fila de release; a presença dessas peças não certifica um ciclo completo em Windows empacotado nem autoriza ativação automática.

| Área | Existe no código/documentação local | Limite que deve permanecer explícito |
|---|---|---|
| Desktop e IPC | Electron, `preload` com ponte segura, `core/ipc_handlers.py` e sidecar Python | Canal IPC, ACK ou resposta textual não provam execução concluída nem health do runtime empacotado. |
| Ações | `ActionRegistry`, `core/actions/` e `ToolRouter` com validação, permissão, execução, verificação e auditoria | Ações Windows, browser, voz, hardware e verifiers dependem do ambiente e de teste físico; não criar um segundo executor. |
| Lab V1 | `LabRuntime`, sessões, agentes, tarefas, eventos, handoffs, `OperationLedger`, supervisor e `MissionController` | Não é fábrica irrestrita de agentes, council completo, learned routing ou decomposição geral de qualquer objetivo em linguagem natural. |
| Autonomia recorrente | `AutonomySupervisor.tick`, orçamento persistido, deduplicação, backoff, prioridade do owner e `ImprovementScheduler` | Scheduler permitido no source não significa processo vivo, boot automático, watchdog ou disponibilidade 24/7. |
| Candidato e release | `CandidateSource`, baseline/candidato, fila de release, pacote, canário, journal e rollback previstos | O build ativo, o ponteiro, o ASAR e o backend não podem ser tratados como validados só pela existência de um instalador. |
| Modelos/providers | Registry e `model_router.py` | Registro/configuração não prova autenticação, quota, conectividade, custo, latência ou qualidade no Windows real. |

### Limite real de 24/7

O comportamento implementado é **contínuo enquanto o processo da ZARA estiver vivo**. `LabV1Service.start_background()` cria tarefas `asyncio` para o consumidor de operações e para o loop do supervisor; `start_scheduler()` cria outra tarefa para o agendador. `activate_autopilot()` persiste a política e retorna o modo `CONTINUOUS_WHILE_ZARA_OPEN`. O sidecar é iniciado pelo `main.py` como processo IPC quando o aplicativo é executado.

Isso não equivale a 24/7 independente do aplicativo. Fechar a ZARA, encerrar o sidecar, crash, logout, suspensão/hibernação, reinício do Windows, falha de volume ou falta de recursos interrompem as tarefas em memória. Há recuperação de operações duráveis no próximo boot, mas não há, nesta documentação, prova de serviço Windows, tarefa agendada, watchdog externo, restart automático, máquina ligada, rede disponível ou heartbeat observado durante toda a noite. Portanto, a redação correta é **“background contínuo enquanto a ZARA está aberta; recuperação durável após reinício quando o processo volta”**, nunca “24/7 com o app fechado”.

Cadências observadas no código devem ser tratadas como política, não como SLA: o supervisor usa `cadence_seconds` (padrão persistido de 60 s), o scheduler consulta com piso de 30 s, inicia ciclos com intervalo de 900 s e pode aplicar backoff até 21.600 s. Orçamento diário, deduplicação, prioridade de missões do owner e pausa podem impedir uma nova missão mesmo quando o processo está vivo. `SCHEDULER_ENABLED = True` significa que o recurso está permitido por padrão no source atual; não prova que `start_scheduler()` foi chamado nem que a tarefa está `RUNNING`.

### Memória e contexto

As fontes reais devem permanecer separadas e com proveniência:

1. **Memória operacional do Lab:** SQLite/`LabStore` para sessões, tarefas, eventos, operações, ACKs, resultados, leases, política e journals. O `OperationLedger` torna o `request_id` idempotente: replay do mesmo payload devolve o ACK durável; o mesmo ID com payload diferente é conflito.
2. **Memória do projeto:** `%LOCALAPPDATA%\\ZARA3\\data\\project-memory\\project_memory.db`, Markdown interno e `mentor_context_latest.md`. `ProjectMemory` também mantém documentos por projeto em `vault/projects/<project_id>/`.
3. **Espelho Obsidian:** é best-effort, detectado pelo `obsidian.json` real e escrito na subpasta `Zara-Memoria`; vault inexistente, removido ou desconectado não pode quebrar a memória interna nem ser declarado sincronizado.
4. **Memórias de usuário e episódicas:** continuam nos módulos existentes (`UserMemoryCore`, `MemoryManager`/episódica e histórico), sem duplicar a mesma decisão em outra fonte de verdade.

O contexto é seletivo, não um despejo global do vault: `build_project_context()` exige projeto ativo ou explícito, rejeita documentos/chaves ausentes, inclui `project_id` como item obrigatório e aplica orçamento padrão de 4096 bytes, marcando degradação e itens omitidos quando necessário. Nunca gravar segredo, token, `.env`, raciocínio privado ou conteúdo externo como permissão. Uma memória persistida prova armazenamento; não prova recuperação perfeita, relevância automática ou injeção em todos os prompts.

### Gates obrigatórios e estados de bloqueio

Nenhuma etapa pode pular gate. O estado deve ser derivado de executor, verifier, receipt e journal, nunca da prosa do agente.

| Gate | Verificação mínima | Falha/saída honesta |
|---|---|---|
| G0 autoridade | Policy, ledger e promoções pendentes sem conflito | `BLOCKED` |
| G1 sinal | Evidência factual com origem, horário, hash e escopo | `PROPOSAL_ONLY_UNSUPPORTED` |
| G2 admissão | `request_id`, dedup, orçamento e ACK durável | `DUPLICATE`, `PAUSED` ou `BUDGET_EXHAUSTED` |
| G3 missão | Plano versionado finito, limites, lease, deadline e aceite | `MISSION_REJECTED` |
| G4 isolamento | Snapshot allow-listed fora da produção; sem path externo, symlink ou segredo | `CANDIDATE_SANDBOX_REJECTED` |
| G5 baseline | Teste focal da baseline com comando e exit code registrados | `BASELINE_FAILED` |
| G6 patch | Diff bounded, sintático, com alteração de source autorizada | `PATCH_DRAFT_REJECTED` |
| G7 candidato | Regressões, invariantes e artefatos do candidato | `CANDIDATE_TEST_FAILED` |
| G8 revisão | Revisor independente, `reviewer_run_id` e `PASS` | `INDEPENDENT_REVIEW_BLOCKED` |
| G9 pacote | Instalador, EXE, `BUILD_INFO.json`, `SOURCE_MANIFEST.json` e backend coerentes | `CANDIDATE_ARTIFACT_DRIFT` |
| G10 canário | Mesmo ASAR e backend do pacote, não fixture ou outro build | `PACKAGED_CANARY_NOT_PASSED` |
| G11 owner | Aprovação explícita vinculada ao candidato, source, build, ASAR e backend | `AWAITING_OWNER_APPROVAL` |
| G12 ativação | Journal, known-good, backup, ponteiros e promoção transacional | `BLOCKED` com restauração |
| G13 saúde | Smoke do runtime exato: startup, preload/IPC, sidecar, memória quando aplicável | `ROLLED_BACK` |
| G14 commit | Journal `COMMITTED`, ponteiro e hashes coerentes | `RECONCILIATION_NEEDS_OWNER` |

`QUEUED`/`ADMITTED` significa recebido e persistido; não significa executado. `MONITORING` não significa sucesso final. `ACTIVE` só pode aparecer depois do health check do mesmo pacote. `UNKNOWN` ou journal ambíguo não pode ser descartado por retry cego.

### Ordem de integração sem inverter

1. **Governança e inventário:** congelar fontes de verdade, confirmar build ativo/known-good, uma policy, um ledger, um `ToolRouter` e uma `ReleaseQueue`; nenhum teste toca produção.
2. **Admissão idempotente:** registrar sinal/proposta, `request_id`, hash de evidência, dedup, orçamento, pause e backoff; não chamar provider antes de admissão.
3. **Missão bounded:** criar sessão e plano explícito com `MissionLimits`, `ExecutionScope`, lease e deadline; linguagem natural sem passos válidos fica bloqueada.
4. **Snapshot e baseline:** copiar somente arquivos autorizados para sandbox externo, gerar manifest e executar baseline separado do candidato.
5. **Patch e verificação:** aplicar edição estruturada somente no sandbox, rejeitar no-op/patch fora do escopo e executar testes, regressões e verifiers.
6. **Revisão independente:** revisor diferente do executor confere diff, risco, hashes, receipts e ausência de drift.
7. **Pacote e canário:** gerar staging allow-listed e provar o runtime empacotado pelo mesmo ASAR/backend; não mover ponteiro.
8. **Aprovação e ativação:** apresentar diff, riscos, evidências e rollback; exigir aprovação específica; executar promoção transacional com journal.
9. **Health, commit ou rollback:** verificar Windows/Electron/sidecar e capacidades autorizadas; consolidar somente com evidência, ou restaurar known-good.
10. **Recorrência limitada:** apenas depois dos gates anteriores, habilitar supervisor/scheduler com orçamento, dedup, backoff, prioridade do owner e pausa; reinício retoma registros duráveis, não concede autorização permanente.

### Validação mínima por ambiente

Manter a taxonomia `SOURCE → TEST → RUNTIME_AUTOMATED → PACKAGED_RUNTIME → PHYSICAL_BY_ALEX → VOICE_PHYSICAL`. Testes Python/Linux ou fixtures cobrem apenas a camada correspondente. Para declarar pronto no Windows, ainda é necessário executar o build candidato correto, validar os cinco artefatos, abrir o Electron empacotado, confirmar preload/IPC/sidecar, testar texto, histórico e uma ação com confirmação; voz, microfone, browser e hardware exigem autorização e teste físico específico. Sem essa camada, registrar `NOT_LIVE_VERIFIED`.

## Referências locais de conferência

- `docs/ARQUITETURA_AUTOPILOT_TOTAL.md`: contratos, gates G0–G14, release e limites.
- `docs/AUTOPILOT_BUILD_E_TESTE.md`: artefatos obrigatórios, preflight de espaço e teste físico pendente.
- `docs/ZARA_DOCUMENTACAO_UNICA.md`: estado consolidado, memória, build e regras de segurança.
- `core/lab_v1/service.py`: tarefas em processo, consumidor, scheduler e modo `CONTINUOUS_WHILE_ZARA_OPEN`.
- `core/lab_v1/supervisor.py`: policy, orçamento, dedup, backoff, prioridade e tick.
- `memory/project_memory.py`: SQLite, vault, Obsidian best-effort e orçamento de contexto.
