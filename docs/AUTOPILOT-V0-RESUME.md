# ZARA Autopilot V0 — handoff antes do limite de uso

> Histórico V0.1. Foi sucedido pela missão one-shot autorizada por Alex.
> Retomada atual: `artifacts/autonomy-one-shot/RESUME.md`.
> As restrições de fase e os 73 testes abaixo descrevem a entrega anterior.

Data: 2026-09-06. Workspace: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002.

## Autorização e ponto de parada

Alex autorizou iniciar somente V0.1 (Mission Controller) após o contrato Autopilot.
Pediu parar antes de 3% de saldo, com registro para retomada. Última consulta
durante implementação: 8% na janela de cinco horas. Não usar reset de quota.
V0.2/Hermes NÃO foi iniciado. Não continuar automaticamente para outra fase.

## Estado entregue

Implementação offline funcional e testes verdes; V0.1 ainda deve ser fechada
quanto às limitações abaixo antes de qualquer integração externa.

- Novo core/lab_v1/mission_controller.py: Mission reutiliza o ID da Session;
  plano sequencial versionado, limites persistidos, checkpoints, lease SQLite
  com token de fencing, execute/verify separados, cancelamento e reconciliação.
- Novas tabelas mission_controls e mission_plans no MESMO banco do Lab.
  Migration aditiva somente ao construir explicitamente MissionController.
  Startup V1 não instancia controller nem aplica esta extensão.
- Ação interrompida passa a UNCERTAIN_EFFECT. Nunca repete automaticamente.
  APPLIED exige receipt e verificação posterior; NOT_APPLIED exige evidência
  e consome retry global; UNKNOWN fica bloqueado.
- Só Verification PASS com referência de evidência permite concluir a Task.
- core/lab_v1/store.py: mission_snapshot consulta extensão sem ativá-la.
- core/lab_v1/runtime.py: submit V1 rejeita Session já controlada
  (MISSION_CONTROLLED); snapshot apresenta extensão quando existente.
- Portas execute/verify injetadas; nenhum executor/modelo concreto integrado.
- Nenhum Run real ou evento de chamada externa foi inventado pelo controller.

## Testes

Novo tests/test_lab_mission_controller.py: 22 casos; relógio controlado,
storage temporário e portas falsas. Inclui restart, concorrência entre duas
instâncias, fencing, cancelamento, budgets, dependências, revisão de plano,
reconciliação, verificação e migration sobre fixture V1.

Corrigido teste instável test_concurrent_submit_invokes_provider_once em
tests/test_lab_v2_seam.py: substituído busy loop por threading.Event para
assegurar que a primeira chamada está dentro do adapter antes da segunda.
Uma regressão inicial deu 72 PASS/1 FAIL por esta corrida. Após correção:

    .venv\Scripts\python.exe -m pytest tests/test_lab_mission_controller.py tests/test_lab_v1_units.py tests/test_lab_v2_seam.py tests/test_lab_v2_nvidia.py tests/test_lab_v2_nvidia_agents.py tests/test_home_ipc_contracts.py -q

Resultado final: 73 PASS / 0 FAIL. Não houve chamadas externas reais.
Nenhuma mudança TypeScript nesta etapa; typecheck não foi repetido.

## Limitações abertas — não ocultar na retomada

1. Portas são somente contratos offline: devem cumprir deadline e realizar uma
   operação limitada. Ainda não há encerramento físico de processo, heartbeat
   automático nem scheduler em background (integração futura).
2. Deadline da missão é verificado antes do despacho. Revisar também o commit
   de execução/verificação que termine após deadline mas antes de expirar lease:
   resultado tardio não pode produzir COMPLETED indevidamente.
3. Orçamento atual contabiliza invocações, delegações, ações, retries e tempo;
   tokens e custo monetário não estão contabilizados. Não prometer teto em USD.
4. Planos podem ser revisados somente antes de executar qualquer etapa.
   Falhas de verificação ficam BLOCKED: ainda não há reparo/replanejamento
   integrado ou OwnerDecision persistente para desbloqueios gerais.
5. Escopo de recursos/autorização não é ainda um contrato executável:
   ContextPacket contém objetivo, Task e aceite. Antes do executor real,
   precisa de workspace/recursos permitidos explícitos e política de ação.
6. Não há endpoint IPC, UI nem execução automática de tick. Isso não é ainda
   um Autopilot utilizável via voz/chat. V0.1 entrega núcleo offline.
7. Guard submit V1 evita bypass de Session já controlada. A adoção simultânea
   de uma Session por controller e um submit V1 ainda não tem transação única
   compartilhada; não habilitar os dois fluxos concorrentes sem fechar isso.
8. Reavaliar restrição de uma missão ativa: lease global impede duas operações
   em andamento e estados incertos bloqueiam outras missões, mas a API ainda
   permite cadastrar múltiplos planos e alternar ticks entre eles.

## Preservado

Não executei providers, Hermes, install, UI, package, launchers ou ativação.
Não instanciei controller sobre banco de produção; fixtures usaram tmp_path.
Não editei credentials, memória pessoal ou evidências históricas A/B/C/G13.
Baseline 055925 e staging Claude 083543 não foram alvo de nenhuma operação.
Não houve nova verificação de hashes de pacotes nesta etapa.

O worktree já era muito dirty: não reverter mudanças globais ou atribuí-las
a V0.1. Arquivos Lab não rastreados pelo Git já existiam antes desta etapa.

## Próximo passo exato

Retomar V0.1 do controller e dos 73 testes verdes, fechar primeiro deadline
no commit e as lacunas necessárias ao aceite offline, com testes focados,
antes de declarar V0.1 completa; não iniciar Hermes/V0.2 sem nova autorização.
