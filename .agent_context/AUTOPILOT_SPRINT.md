# Sprint de implementação — ZARA Lab Autopilot

**Data:** 17/09/2026  
**Prioridade:** fazer o Lab trabalhar sozinho enquanto a ZARA estiver aberta.  
**Estado:** quadro preparado durante o empacotamento do build; não iniciar tarefas que alterem arquivos atualmente lidos pelo build até o pacote terminar.

## Objetivo do sprint

Fazer o ZARA Lab iniciar, executar, verificar, registrar e retomar missões de melhoria de forma controlada. O Autopilot deve trabalhar sem o proprietário ficar diante do computador, mas não deve ganhar shell irrestrito, apagar dados, promover build sem verificação ou ultrapassar orçamento e política.

## Regras para todos os agentes

1. Ler `ZARA_AGENT_START_HERE.md`, `ZARA_MASTER_CONTEXT.md` e `docs/PLANO_DA_AGENCIA_ZARA.md` antes de editar.
2. Um agente por arquivo durante cada change set.
3. Não editar `ZARA_ACTIVE_BUILD.json`, o diretório do build ativo, bancos de memória ou bancos de Lab sem uma tarefa específica.
4. Não remover `--restricted`, `ExecutionScope`, `WorkforcePolicy`, confirmação, deduplicação, verificação ou rollback.
5. Não iniciar provider pago, navegador live, hardware live ou teste destrutivo.
6. Cada mudança deve ter rollback simples, descrição curta e comando de validação.
7. O resultado deve distinguir `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `BLOCKED` e `UNVERIFIED`; nunca declarar sucesso por inferência.

## Onda 1 — estado, retomada e supervisor

| Agente | Missão | Arquivos principais | Entrega | Pronto quando |
|---|---|---|---|---|
| `lab-boot-owner` | Garantir que o serviço Lab inicie o supervisor e o scheduler no primeiro caminho real de uso | `core/lab_v1/service.py`, `core/ipc_handlers.py` | Change set pequeno e reversível | O estado do Lab informa se o background está `RUNNING`, `PAUSED` ou `BLOCKED` |
| `mission-resume-owner` | Garantir retomada após fechar e reabrir a ZARA | `core/lab_v1/operation_ledger.py`, `core/lab_v1/mission_controller.py`, `core/lab_v1/service.py` | Matriz de estados de restart e correção necessária | Operação interrompida não é perdida nem marcada como concluída sem evidência |
| `supervisor-owner` | Fazer o supervisor avançar uma etapa por ciclo, com lease e orçamento | `core/lab_v1/supervisor.py`, `core/lab_v1/autopilot.py` | Correções de ciclo e backoff | Uma missão ativa não bloqueia o IPC e não cria duplicatas |
| `workforce-owner` | Garantir escolha de agentes e providers autorizados | `core/lab_v1/workforce_policy.py`, `core/lab_v1/providers/` | Relatório de disponibilidade e fallback | Provider indisponível gera `BLOCKED`/fallback honesto, não falso sucesso |

## Onda 2 — trabalho de melhoria do código

| Agente | Missão | Arquivos principais | Entrega | Pronto quando |
|---|---|---|---|---|
| `source-mission-owner` | Garantir snapshot isolado, proposta, aplicação limitada e rollback | `core/lab_v1/source_mission.py`, `core/lab_v1/candidate_source.py`, `core/lab_v1/sandbox_actions.py` | Fluxo de candidata isolada | Nenhuma edição ocorre fora do workspace autorizado |
| `artifact-verifier-owner` | Fortalecer verificação de artefato, diff e critérios de aceitação | `core/lab_v1/artifact_verifier.py`, `core/lab_v1/mission_controller.py` | Evidência vinculada a cada etapa | Só uma evidência verificável pode avançar a missão |
| `release-gate-owner` | Impedir autopromoção de build sem gate e rollback | `tools/build_current.py`, `tools/quality_gate.py`, `build_exe.py` | Proposta de promoção controlada | O Lab pode preparar candidata, mas só ativa build validado |
| `security-owner` | Revisar escopo, permissões, segredos e prompt injection | `core/lab_v1/execution_scope.py`, `core/lab_v1/workforce_policy.py`, ações | Lista de bloqueios e correções | Nenhuma tarefa do Lab obtém shell arbitrário ou acesso fora do escopo |

## Onda 3 — comunicação e experiência

| Agente | Missão | Arquivos principais | Entrega | Pronto quando |
|---|---|---|---|---|
| `lab-ui-owner` | Mostrar estado real do time e das missões | `frontend/src/renderer/components/zara-lab-v2/` | Estados `idle/queued/running/blocked/completed/failed` | A UI não confunde admissão com conclusão |
| `lab-ipc-owner` | Manter paridade entre preload, tipos e handlers Lab V1 | `frontend/src/preload.ts`, `frontend/src/renderer/types/global.d.ts`, `core/ipc_handlers.py` | Contrato IPC documentado | Toda operação tem request id, estado e resultado persistente |
| `memory-owner` | Registrar lições verificadas do Lab sem duplicar memórias | `memory/`, `core/lab_v1/agent_continuity.py`, `memory/shared_second_brain.py` | Política de lições e proveniência | Só resultados aceitos entram na memória compartilhada |

## Onda 4 — operação real

| Agente | Missão | Entrega |
|---|---|---|
| `packaging-owner` | Reempacotar após os change sets e conferir ponteiro/hashes | Build validado, manifestos e rollback |
| `windows-live-owner` | Executar teste físico no Windows com missão de baixo risco | Evidência de boot, missão, agente, resultado e retomada |
| `coordinator` | Consolidar resultados e liberar a próxima onda | Relatório final e ordem de merge |

## Ordem obrigatória de execução

```text
Build atual terminar
  → Onda 1: boot, retomada, supervisor, workforce
  → Onda 2: candidata, verificação, release, segurança
  → Onda 3: UI, IPC, memória
  → novo empacotamento
  → teste físico controlado no Windows
  → somente então liberar Autopilot contínuo
```

## Missão física inicial recomendada

Usar uma tarefa reversível e sem impacto no sistema, por exemplo:

> “ZARA, faça uma autoatualização controlada do próprio projeto: apenas analise um arquivo de documentação dentro do workspace isolado, proponha uma melhoria pequena, gere a evidência e não promova nem instale o build.”

O teste deve confirmar:

- o Lab iniciou;
- o time foi selecionado por política;
- a missão ficou persistida;
- o agente produziu um artefato;
- o verificador aceitou ou recusou com motivo;
- o resultado apareceu no Lab;
- reiniciar a ZARA não apagou o estado;
- nenhuma alteração fora do workspace ocorreu.

## Proibições do sprint

- Não mandar os 313 agentes trabalharem simultaneamente.
- Não permitir que agentes editem `core/ipc_handlers.py`, `service.py` ou o build ao mesmo tempo.
- Não ligar autopromoção automática de release.
- Não apagar quarentena, memória, bancos ou evidências.
- Não tratar a contagem de agentes instalados como prova de que todos estão disponíveis ou autenticados.
