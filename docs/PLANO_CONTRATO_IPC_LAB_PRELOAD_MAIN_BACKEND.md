# Contrato IPC do ZARA Lab

## Objetivo

Garantir que cada recurso do Lab atravesse as quatro camadas na mesma ordem:

```text
React/renderer
    ↓ window.zaraIPC
Preload seguro
    ↓ ipcRenderer.invoke
Electron Main
    ↓ sendToPython
Python IPC dispatcher
    ↓ handler do Lab V1
LabV1Service
```

O Main não executa regras de negócio. O Preload não escolhe permissões. O renderer não fabrica aprovação. O backend valida a operação, grava o resultado e devolve uma resposta JSON segura.

## Canais atuais

| Recurso | Renderer | Preload | Main | Python | Serviço |
|---|---|---|---|---|---|
| Pesquisa/Skill | `window.zaraIPC.labV1.researchSkill(payload)` | `lab-v1-research-skill` | `sendToPython(...)` | `handle_lab_v1_research_skill` | `research_skill_pipeline` |
| Chat do Lab | `window.zaraIPC.labV1.teamChat(payload)` | `lab-v1-team-chat` | `sendToPython(...)` | `handle_lab_v1_team_chat` | `append_team_chat` |

A pesquisa aceita `snapshot`, `research`, `candidate`, `test`, `activate` e `rollback`. O chat aceita `mission_id`, `role`, `state`, `summary`, referências de evidência e próxima ação.

## Regras do payload

O payload deve ser um objeto JSON. Valores desconhecidos devem ser ignorados ou rejeitados pelo backend, conforme a operação. Nunca enviar funções, objetos Electron, caminhos não autorizados, tokens ou conteúdo de segredo.

A operação de pesquisa deve validar o nome da operação antes de chamar o serviço. O serviço executa em thread porque pesquisa e acesso ao armazenamento podem bloquear o loop principal.

A ativação de Skill deve conter a aprovação exigida pelo backend e a versão exata do candidato. O renderer pode solicitar a operação, mas não prova a identidade do aprovador. A próxima etapa deverá adicionar `actor`, `approval_id`, `candidate_hash` e timestamp emitidos pela autoridade do backend.

O chat deve aceitar somente papéis e estados definidos pelo serviço. Mensagens inválidas, vazias ou potencialmente sensíveis devem retornar erro sem escrever no Obsidian.

## Formato de resposta

Toda rota deve retornar uma destas formas:

```json
{"success": true, "result": {}}
```

ou:

```json
{"success": false, "error": "mensagem curta", "code": "TIPO_DO_ERRO"}
```

O renderer deve tratar `success: false` e `error` como falha. Um ACK de transporte não é prova de que a ação foi executada. A pesquisa deverá apresentar evidências retornadas pelo serviço; o chat deverá apresentar `SAVED`, `MEMORY_UNAVAILABLE` ou `REJECTED`.

## Plano de implementação

### Etapa 1 — Contrato declarado

Manter um único inventário de canais com nome, direção, payload, resposta e risco. O inventário deve ser revisado sempre que um canal for criado ou removido.

**Critério de pronto:** não existe canal exposto no Preload sem handler Main correspondente.

### Etapa 2 — Ponte segura

O Preload expõe apenas funções pequenas e tipadas. Ele não expõe `ipcRenderer` inteiro, `sendToPython`, filesystem ou shell. O Main registra cada handler uma vez dentro de `setupIPC`.

**Critério de pronto:** `contextIsolation: true`, `nodeIntegration: false` e nenhuma API privilegiada aparece no objeto exposto ao renderer.

### Etapa 3 — Dispatch Python

O dispatcher mapeia o nome do canal para um método `handle_*`. O handler verifica a disponibilidade do Lab V1, valida que o payload é um dicionário e transforma exceções em resposta controlada.

**Critério de pronto:** canal desconhecido não derruba o sidecar; payload inválido retorna erro; exceção do serviço retorna erro estruturado.

### Etapa 4 — Serviço de domínio

O `LabV1Service` concentra a regra de pesquisa e chat. O IPC não deve duplicar lógica de Skills nem de Obsidian. Operações potencialmente bloqueantes devem usar `asyncio.to_thread`.

**Critério de pronto:** o serviço pode ser testado sem Electron usando um cofre temporário e um diretório de Skills temporário.

### Etapa 5 — Consumidor visual

O LabRoom chama apenas `window.zaraIPC.labV1`. O estado de carregamento deve bloquear duplo clique. A mensagem de erro deve ser curta e compreensível. A UI não deve apresentar “ativado” antes da resposta do backend.

**Critério de pronto:** pesquisar uma fonte controlada atualiza a mensagem de pesquisa; um chat válido aparece no histórico; uma falha é visível sem quebrar a sala.

### Etapa 6 — Testes estáticos

Criar um teste que leia `preload.ts`, `main.ts`, `ipc_handlers.py` e `global.d.ts`, verificando a presença dos dois nomes em todas as camadas. O teste deve falhar quando um canal for removido de uma camada sem atualização das demais.

### Etapa 7 — Testes de contrato

Executar, em dados temporários:

1. `snapshot` de Skills;
2. pesquisa com fetcher controlado;
3. chat válido gravado no cofre temporário;
4. payload inválido rejeitado;
5. mensagem sensível rejeitada;
6. operação desconhecida rejeitada;
7. resposta de erro sem exceção escapar.

### Etapa 8 — Teste Electron

No build de desenvolvimento, abrir a sala, executar uma pesquisa e observar a resposta no renderer. Depois enviar uma mensagem de chat. O teste deve confirmar que o processo Python continua vivo e que o fechamento da janela não deixa backend órfão.

### Etapa 9 — Teste empacotado no Windows

Executar o mesmo fluxo no candidato do instalador. Confirmar `preload`, IPC, backend, memória e logs. Usar o mesmo ASAR e o mesmo backend que serão entregues. Não trocar o build ativo antes do canário passar.

### Etapa 10 — Governança da aprovação

Antes de liberar ativação real, mover a prova de aprovação para o backend. A resposta deverá registrar ator, candidato, hash, versão, data, motivo e política aplicada. O botão visual apenas inicia o pedido.

## Critérios de aceite

O contrato será considerado implementado quando:

- pesquisa e chat existirem em Preload, Main, dispatcher, handler e serviço;
- TypeScript reconhecer as APIs;
- o backend validar payloads;
- testes de contrato passarem;
- o renderer mostrar sucesso e falha corretamente;
- o teste empacotado no Windows passar;
- a aprovação de Skill estiver vinculada a um registro de owner;
- nenhum canal novo contornar o executor ou a política de segurança.

## Rollback

A ponte é reversível por commit. Se o Main não conseguir falar com o backend, o botão de pesquisa deve ser desabilitado ou mostrar “canal indisponível”; não deve simular resultado. A remoção dos dois handlers e dos dois tipos retorna ao estado anterior sem alterar o banco ou o build ativo.

## Estado desta implementação

Nesta etapa, os handlers `lab-v1-research-skill` e `lab-v1-team-chat` foram adicionados ao Electron Main. Os tipos correspondentes foram adicionados ao `global.d.ts`. O Preload e os handlers Python já existiam. Nenhum build foi substituído e nenhuma Skill foi ativada.
