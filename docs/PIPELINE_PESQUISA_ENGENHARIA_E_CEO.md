# Pipeline de pesquisa, engenharia, testes e CEO

## Pendências para fechar o ciclo

| Etapa | Falta fechar | Critério de conclusão |
|---|---|---|
| Pesquisa | Coleta de fontes oficiais, limite de tamanho, hash e separação entre fato e opinião | Cada descoberta tem URL, trecho, data e SHA-256 |
| Engenharia reversa | Transformar a descoberta em requisitos, riscos, compatibilidade e experimento reproduzível | Existe um plano técnico sem código executável recebido diretamente da web |
| Codificação | Criar uma implementação isolada, com permissões mínimas e versão SemVer | Candidato registrado como `DRAFT`, com checksum e referências |
| Testes de falha | Testar entradas inválidas, fonte indisponível, conteúdo sensível, timeout, regressão e rollback | Recibos de teste persistidos; nenhum teste aprovado sem evidência |
| Revisão | Revisor independente verifica fatos, diff, permissões e cobertura | Revisão independente aprovada |
| CEO/Arquiteto | Decide benefício, risco, custo, compatibilidade e autorização de ativação | Aprovação explícita do owner/CEO registrada |
| Ativação | Ativar somente a versão aprovada e manter a anterior | Ponteiro ativo atualizado atomicamente |
| Rollback | Restaurar versão anterior conhecida sem apagar histórico | Rollback testado e ponteiro anterior recuperado |

## Chat de equipe usando a memória do Obsidian

O Lab deve tratar cada missão como uma sala com papéis fixos, não como uma conversa sem dono. A ordem recomendada é:

`PESQUISADOR → ARQUITETO → ENGENHEIRO → CODADOR → TESTER/RED TEAM → REVISOR → CEO`

Cada mensagem deve conter `mission_id`, `role`, `reply_to`, `state`, `summary`, `evidence_refs` e `next_action`. O conteúdo bruto de fontes não deve ser despejado na memória central; deve ficar em artefato limitado, enquanto o Obsidian recebe resumo, fonte, hash, decisão e links opacos.

O Obsidian funciona como cérebro compartilhado em quatro camadas. A camada de fatos guarda somente observações com fonte. A camada de decisões registra alternativas rejeitadas e motivo. A camada de execução registra tarefas, responsáveis, testes e falhas. A camada de memória de skills registra manifestos, permissões, versões ativas e histórico de rollback. ZARA e os agentes consultam as mesmas notas, mas nenhum agente pode transformar uma nota em código executável sem passar pelo registro e pelos portões de teste.

Estados de uma mensagem: `OBSERVED`, `ANALYZING`, `PLANNED`, `IMPLEMENTING`, `TESTING`, `REVIEWING`, `WAITING_CEO`, `APPROVED`, `REJECTED`, `ROLLED_BACK`. Um agente só pode avançar o estado que lhe pertence. O CEO não escreve código; ele decide promoção e rollback.

## O que já foi codificado nesta etapa

Foi criado `core/lab_v1/research_skill_autopilot.py`. Ele pesquisa fontes HTTP(S) com limite de 256 KiB, rejeita padrões sensíveis, guarda excerpt e SHA-256, cria candidatos metadata-only no registro versionado, grava recibos de teste, exige aprovação explícita do owner, atualiza o ponteiro ativo com escrita atômica e mantém versões anteriores para rollback.

O módulo não importa, carrega ou executa código descoberto na internet. Essa separação é intencional: pesquisa pode ser autônoma; ativação de uma capacidade que altera o computador continua dependente dos gates de teste e aprovação.

## Próxima integração no Lab

O próximo passo técnico é instanciar esse pipeline no `LabV1Service`, expor operações IPC para `research`, `candidate`, `test`, `activate` e `rollback`, e publicar cada mudança como evento na sala visual. Depois disso, o ciclo poderá ser acionado pelo scheduler, ainda respeitando orçamento, limites e a fila de aprovação.
