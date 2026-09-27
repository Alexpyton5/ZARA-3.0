# Missão Noturna — 5.000 ideias para a ZARA

## Objetivo

Criar um backlog de 5.000 candidatos de melhoria nas áreas de controle Windows, voz, navegador, visão computacional, memória, desempenho, fluidez, ZARA Lab, segurança e qualidade de código.

## Interpretação segura

Os 5.000 itens são **candidatos para análise**, não 5.000 mudanças automáticas. Ideias repetidas, inviáveis, inseguras ou sem benefício mensurável serão descartadas. Apenas itens priorizados, implementados e testados entram no produto.

## Frentes

1. Controle Windows, voz e navegador.
2. Visão computacional e OCR.
3. Memória, contexto, Obsidian e proveniência.
4. ZARA Lab, agentes, handoffs e autopilot.
5. Desempenho, fluidez, inicialização e resiliência.
6. Revisão, limpeza estrutural e redução de duplicidade.
7. Segurança, permissões, confirmação e rollback.
8. Testes, telemetria honesta e validação física Windows.

## Regras

- Windows é o alvo; o ambiente Linux desta sessão serve apenas para validação estática e testes simulados.
- Nenhum agente edita o mesmo arquivo simultaneamente.
- Nada é apagado sem inventário, hash e quarentena.
- Nenhum código pesquisado é ativado sem teste e aprovação.
- Cada alteração precisa de teste focal e regressão.
- Não declarar “controle total” sem prova física no Windows.
- Não executar uma missão infinita: o estado, resultados e próxima fila devem ser salvos.

## Critério de progresso

Uma ideia só vira melhoria quando tem objetivo, risco, arquivo-alvo, teste, evidência e rollback. A missão prioriza qualidade e funcionamento real, não quantidade de linhas codadas.
