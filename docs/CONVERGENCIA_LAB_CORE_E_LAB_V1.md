# Convergência do ZARA Lab

## Decisão

O **Lab V1** é o caminho oficial para novas missões, pesquisa, Skills, memória central e scheduler. O **Lab Core legado** permanece como compatibilidade para propostas e integrações antigas, mas não deve receber novas regras de autonomia.

## Divisão

| Área | Caminho oficial | Estado do caminho legado |
|---|---|---|
| Missões e execução verificada | `core/lab_v1/service.py` | Compatibilidade |
| Pesquisa e Skills | `core/lab_v1/research_skill_autopilot.py` | Não duplicar |
| Chat estruturado | `core/lab_v1/team_chat_memory.py` | Não duplicar |
| Memória central | `LabV1Service.snapshot()` | Apenas leitura/ponte |
| Scheduler | `ImprovementScheduler` | Não criar segundo loop |
| Aprovação/rollback | pipeline de Skills V1 | Bloqueado fora da política |
| Estado visual | canais `lab-v1-*` | Legacy somente quando necessário |

## Regras para futuras alterações

Uma melhoria nova deve entrar no Lab V1. Se uma tela antiga precisar da função, criar um adaptador fino que encaminhe para o serviço V1; não copiar a regra de negócio. Toda operação deve conservar o mesmo gate de owner, orçamento, lock, evidência e pós-verificação.

O Lab Core legado não pode ativar código descoberto na internet, executar comandos sem ActionRegistry, nem criar um scheduler paralelo. A migração de dados deve ser idempotente e registrada.

## Critério de retirada do legado

O Lab Core só poderá ser removido depois de o teste empacotado no Windows confirmar que as telas e integrações antigas usam os canais V1, que não há escrita exclusiva no banco legado e que o rollback do build funciona.
