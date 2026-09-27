# Missão de 50 tarefas grandes — ZARA

Cada tarefa só é concluída com código salvo, teste focal, regressão e registro. As tarefas abaixo são uma fila priorizada; não serão executadas todas simultaneamente no mesmo arquivo.

## Qualidade e dependências

1. Restaurar dependências frontend sem symlink quebrado no volume montado.
2. Transformar `npm test` em gate real.
3. Corrigir bootstrap dos testes CommonJS.
4. Criar teste que falha quando o gate é falsamente verde.
5. Fazer typecheck falhar de forma legível quando binário estiver ausente.
6. Fazer lint falhar de forma legível quando binário estiver ausente.
7. Criar manifesto de versão e hash do build.
8. Detectar documentação stale contra o build ativo.
9. Separar testes mockados, simulados e live Windows.
10. Criar relatório único de qualidade por ciclo.

## Lab, Electron e Autopilot

11. Encaminhar evento terminal do Lab até o renderer.
12. Expor listener terminal no preload.
13. Deduplicar eventos por `event_id` na interface.
14. Unificar rotas de submissão do Lab no ledger durável.
15. Conectar ativação do modo contínuo ao Main.
16. Expor ativação contínua no preload.
17. Adicionar botão de ativação com estado real no Lab.
18. Separar residente ativo de scheduler de melhorias.
19. Tornar health agregado operacional.
20. Testar restart com operação pendente e resultado terminal.
21. Eliminar corrida entre drains do outbox.
22. Criar política para ações agendadas de alto risco.
23. Corrigir cron simplificado ou rejeitar expressões não suportadas.
24. Criar heartbeat verificável do sidecar.
25. Criar recuperação após falha do consumidor.

## Windows, voz e navegador

26. Escolher rota canônica entre `os_ops` e fundação Windows.
27. Unificar allow-list e política de risco Windows.
28. Criar camada de mouse com simulação e readback.
29. Criar camada de teclado com confirmação e readback.
30. Conectar OCR nativo Windows real.
31. Criar teste live de OCR Windows.
32. Criar teste live de abrir/focar/fechar janela.
33. Criar controle seguro de arquivos e pastas.
34. Tornar navegação verificável por título/URL final.
35. Escolher navegador padrão ou Playwright como rota oficial.
36. Consolidar stack de voz canônica.
37. Corrigir lifecycle do engine local de voz.
38. Criar teste live de microfone/STT.
39. Criar teste live de TTS e interrupção.
40. Criar comando de voz com confirmação e cancelamento.

## Memória, Lab e interface

41. Tornar contexto por projeto end-to-end.
42. Expor ativação e seleção de projeto no IPC/UI.
43. Tornar TeamChat idempotente e legível.
44. Persistir TeamChat no índice transacional.
45. Unificar projeções Obsidian.
46. Expor idade, origem e degradação da memória.
47. Consolidar CSS duplicado do Lab.
48. Corrigir foco, Escape e semântica dos modais.
49. Reduzir polling e renders completos do Lab.
50. Criar painel executivo de evidências, riscos e rollback.

## Regra de execução

As tarefas 1–10 são bloqueadoras do gate. As tarefas 11–25 fecham a última milha do Autopilot. As tarefas 26–40 dependem de validação física Windows. As tarefas 41–50 fecham memória e experiência. Nova fila só será aberta depois de registrar os resultados desta missão.
