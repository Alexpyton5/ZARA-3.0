# Checkpoint — pesquisa autônoma e Skills com rollback

## Integração concluída

O módulo `core/lab_v1/research_skill_autopilot.py` agora está conectado ao `LabV1Service` e pode ser chamado pelo IPC usando o tipo `lab-v1-research-skill`.

Operações disponíveis no payload:

- `snapshot`: mostra candidatos e Skills ativas;
- `research`: lê fontes HTTP(S) limitadas e gera evidências com hash;
- `candidate`: cria uma Skill metadata-only em `DRAFT`;
- `test`: grava recibo de teste;
- `activate`: exige teste aprovado e `owner_approved: true`;
- `rollback`: restaura uma versão anterior conhecida.

## Segurança aplicada

O pipeline não importa nem executa código descoberto na internet. Fontes são limitadas a 256 KiB, conteúdo com padrões sensíveis é recusado, arquivos são gravados atomicamente e a ativação exige aprovação explícita. A versão anterior é preservada antes da troca do ponteiro ativo.

## Validação real

A compilação sintática de `research_skill_autopilot.py`, `service.py` e `ipc_handlers.py` terminou com `PYTHON_OK`. Os três testes do pipeline passaram: `3 passed`.

O aviso do pytest sobre `.pytest_cache` foi apenas uma limitação de escrita do volume montado, não uma falha dos testes.

## Ainda pendente

A interface visual ainda precisa de botões/telas para essas operações e o scheduler ainda precisa criar automaticamente uma missão de pesquisa com orçamento. Também falta o teste físico no instalador Windows. Até essas etapas, o pipeline está codificado e protegido, mas não deve ser descrito como ciclo 100% autônomo.
