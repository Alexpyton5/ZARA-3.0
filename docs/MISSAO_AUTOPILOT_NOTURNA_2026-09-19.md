# Missão Autopilot Noturna — Evolução contínua da ZARA

## Comando

Executar ciclos sucessivos de melhoria enquanto esta sessão permanecer ativa, sem apagar dados, sem sobrescrever o build ativo e sem ativar código não verificado.

## Objetivo

Tornar a ZARA mais autossuficiente, limpa, inteligente e autopilot, priorizando confiabilidade real em vez de promessas de autonomia.

## Fila de implementação

1. Visão/OCR somente leitura, com simulação antes de qualquer ação.
2. Contrato de confirmação, cancelamento e expiração para ações sensíveis.
3. Memória por projeto, com contexto mínimo e proveniência.
4. Pesquisa segura com evidências, limites e rollback.
5. Pipeline do Lab com handoffs entre pesquisa, arquitetura, código, testes e CEO.
6. Observabilidade do residente, sidecar e scheduler.
7. Limpeza documental e inventário sem remoção automática.
8. Preparação do build candidato e checklist Windows.

## Regra de cada ciclo

Código pequeno → sintaxe → teste focal → teste de regressão → documentação → próximo ciclo.

Se um teste falhar, a próxima tarefa é corrigir a falha. Não avançar sobre regressão.

## Limites

A ZARA não executará comandos arbitrários, não clicará em telas sem gate, não excluirá arquivos automaticamente, não instalará código pesquisado sem aprovação e não declarará validação física Windows a partir do Linux.

A missão não é um processo eterno nem garante trabalho fora desta sessão. Quando a sessão não puder continuar, o estado e a próxima tarefa ficam registrados neste arquivo e na fila do projeto.

## Critério de pronto

“Codado” = arquivo salvo e testes locais aprovados. “Pronto para uso” = build Windows empacotado, instalado e testado fisicamente.

## Estado inicial

A fundação de segurança, Skills, memória, scheduler, saúde residente e controle Windows está codada e validada por testes focados. A validação física do Electron, Nine Router e Windows continua pendente.
