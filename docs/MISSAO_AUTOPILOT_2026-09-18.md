# Missão Autopilot — Evolução segura da ZARA

## Comando

Liderança técnica nesta sessão: Manus AI. A missão trabalha em ciclos finitos, com decisões técnicas autônomas dentro do escopo autorizado. O resultado de cada ciclo precisa ser salvo, testado e registrado.

## Objetivo

Aumentar a capacidade da ZARA e do ZARA Lab aproximando-os de uma assistente de sistema, sem trocar o build ativo, sem apagar dados e sem ativar código não verificado.

## Prioridades de hoje

1. Corrigir e proteger o contrato Preload → Electron Main → Python → Lab V1.
2. Melhorar diagnóstico do modo residente e do sidecar.
3. Fortalecer a validação de aprovação e rollback de Skills.
4. Adicionar testes de contrato e de falha, usando dados temporários.
5. Produzir inventário e relatório objetivo para a validação física no Windows.

## Regras de execução

Cada alteração deve ser pequena, localizada e reversível. Nenhum agente pode editar o mesmo arquivo simultaneamente. Nenhuma missão pode mover ou apagar arquivo sem inventário, hash e registro na quarentena. O build ativo não será sobrescrito. A ativação de Skill exige teste aprovado e aprovação registrada. Controle do Windows e integração externa permanecem bloqueados para testes físicos até validação no computador do usuário.

## Critérios de sucesso

A missão só declara uma entrega concluída quando o arquivo existir, a sintaxe passar, o teste focal passar e o resultado estiver registrado. “Codado” significa salvo e validado localmente. “Pronto” exige teste no Windows empacotado.

## Estado inicial

A pasta `_quarentena` existe. O inventário é somente leitura. Os canais `lab-v1-research-skill` e `lab-v1-team-chat` estão conectados nas camadas principais. Os testes focados anteriores passaram, mas a validação física do Electron/Windows continua pendente.

## Encerramento honesto

A missão não roda indefinidamente nem consome créditos sem limite. Ela executa ciclos controlados enquanto houver tempo e recursos nesta sessão. Obstáculos de permissão, volume, dependência, teste ou ambiente são registrados e não contornados de forma insegura.
