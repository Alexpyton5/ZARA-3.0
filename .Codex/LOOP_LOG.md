# ZARA 3.0 — histórico do loop

## 2026-09-27 — recuperação após desligamento

- Evidência: `LOOP_LOG.md` não existia; `LOOP_STATE.md` e `LOOP_INBOX.md` registravam apenas o ciclo #2 (religação do Lab V1).
- Fase 1 já publicada: `HEAD` e `origin/lab/autonomia-20260911` apontam para `c98983be1a904e87e37439109e5f9b73c1125f6e`.
- Git após reinício: somente oito backups locais não rastreados; nenhum arquivo-fonte modificado. Não há implementação parcial da missão #2 para recuperar.
- Diretriz recebida antes do desligamento: e-mail `[ZARA-LOOP] Missão #2 — Autopilot: Lab unificado, grupo de 11, 313 plugados`, com o anexo `FASE2-AUTOPILOT-ANALISE.md`. O anexo foi lido; nenhum patch havia começado.
- Estado perdido: somente o registro de progresso que ainda não tinha sido criado. Esta entrada recompõe o ponto de retomada a partir do Git, dos arquivos do loop e da diretriz já lida.
- Próximo trabalho: delimitar a missão #2, verificar o Lab V1, o roster Agency e o sprint físico; implementar em deltas pequenos com testes e sem escrever no volume D:.

## 2026-09-27 — missão #2, primeiro delta após a recuperação

- Fontes verificadas: `.codex/agents/` contém 291 perfis TOML; não foi encontrado `agency-agents.json` no diretório de dados da ZARA. A contagem de 313 da diretriz ainda é **NÃO PROVADA** e não foi usada como valor de runtime.
- Banco Lab V1 consultado em modo somente leitura: 15 agentes, 2 equipes (`ZARA Conversa`, `ZARA Core`), 11 vínculos ativos e 38 sessões. Os 11 vínculos não correspondem aos 11 papéis solicitados; existe missão não terminal bloqueada. Nenhuma missão física nova foi disparada.
- Teste de referência antes do patch: `test_lab_autopilot.py` e `test_lab_v1_safe_contracts.py` tiveram 18 falhas/15 passes; a trava de teste revelou que `core.paths.user_data_dir()` ignorava `ZARA3_HOME` e tentava abrir a memória real. A trava impediu o acesso.
- Correção limitada: `core/paths.py` agora respeita `ZARA3_HOME`, mantendo `LOCALAPPDATA/ZARA3` quando não configurado. `core/ipc_handlers.py` recusa `lab-v1-autopilot` em smoke mode, exceto canary de entrada explícito. Ambos os arquivos receberam backup local antes da alteração.
- Repetição focada: 37/37 testes passaram (`test_isolamento_dados_reais.py`, `test_lab_autopilot.py`, `test_lab_v1_safe_contracts.py`). Isso é evidência de TESTE, não prova física.
- Suíte Python completa foi executada: 2335 itens coletados, mas a coleta parou com 25 erros de importação/contrato em outras áreas. Portanto a validação completa está **BLOQUEADA**; não afirmar que a suíte passou. Nenhum push da missão #2 foi feito neste ponto.
- Próximo: classificar os 25 erros de coleta contra a base, sem misturar correções alheias ao delta; depois validar o Lab relevante, empacotamento e o fluxo físico isolado. Integrar o roster somente após confirmar a fonte canônica.
- Ampliação de validação: 780 testes Lab coletados; a execução foi interrompida após vários grupos falharem e um teste ficar sem progresso por mais de 90 segundos, portanto não há resultado completo desse subconjunto. Amostras isoladas mostram falha funcional em `test_lab_autonomy.py` e outra tentativa de abrir banco real em `test_lab_message_order_133.py`, barrada pela fixture de segurança. Não extrapolar os 37 passes focados para todo o Lab.
- Frontend: `npm run typecheck` e `npm run build` passaram; `npm test` falhou na compilação dos testes (`autoScroll.test.ts` sem imports e configuração incompatível com extensão `.ts`). Nenhum arquivo de frontend foi modificado neste delta.
- Decisão conservadora: publicar apenas o reparo de isolamento de dados e a trava de smoke com falhas globais explicitadas; não iniciar missão física, não importar catálogo incerto e não marcar a missão #2 como concluída.
- Publicação verificada: commit `ef7a36d08ec4d5fe9d1ae3a283b8698147d24122` em `lab/autonomia-20260911`; `git ls-remote` confirmou o mesmo commit no origin. Apenas cinco arquivos deliberados entraram no commit; backups permaneceram locais e não rastreados.
- Após o push, a conexão Gmail disponível apontou para `alexlowperfil@gmail.com`, não para a caixa `zoeeproject@gmail.com` indicada para o loop; a busca `[ZARA-LOOP]` nessa conta retornou vazia. Não interpretar isso como ausência de resposta da Zoe na conta correta. A missão #2 já recebida segue como tarefa ativa.

## 2026-09-27 — ciclo #4, canal oficial e primeira causa raiz da coleta

- Alex confirmou que a aba do Gmail no navegador, conectada a `zoeeproject@gmail.com`, é o canal oficial. A mensagem `[ZARA-LOOP] Pulso + regra anti-travamento nos erros da suite` orienta agrupar as 25 falhas de coleta por causa e usar `.Codex/LOOP_INBOX.md` no Git. A conexão automática de Gmail de outra conta deixa de ser referência; a automação foi atualizada para conferir a aba correta.
- O Git tinha somente `.codex/LOOP_*.md` (minúsculo); em um repositório remoto sensível a maiúsculas isso não satisfaz `.Codex/LOOP_INBOX.md`. Os três arquivos de loop foram renomeados no índice para `.Codex/`, com backups locais prévios, sem mover os 291 perfis em `.codex/agents/`.
- Coleta inicial da suíte Python: 25 erros = 3 registros com capacidade legada `LOCAL_PC_CONTROL`, 21 imports de símbolos ausentes e 1 módulo `voice` ausente. Agrupamento feito por mensagem de erro, sem presumir que todos os imports tenham a mesma correção.
- A tentativa de substituir o nome da capacidade apenas em `ponte_claude.py` revelou a mesma falha em `windows_radios.py` e foi revertida. O delta correto normaliza `LOCAL_PC_CONTROL` para a capacidade existente `PC_CONTROL` em `core/action_registry.py`; o gate de Supercérebro continua bloqueando execução sem autorização. Teste de regressão foi escrito e falhou antes da correção, depois passou.
- Validação: 17 testes do registry passaram; os três módulos antes bloqueados agora coletam (96 testes no conjunto focado). A execução desse conjunto ainda tem 52 falhas funcionais de intents/ponte/radios e 44 passes, não atribuídas ao alias de registro. A suíte geral continua bloqueada na coleta, agora com 22 erros e 2415 testes coletados; antes eram 25 erros e 2335 testes coletados.
- Frontend: typecheck e build passaram; `npm test` continua falhando na compilação dos testes. Não houve edição do frontend neste ciclo. Pacote atualizado e teste físico continuam NÃO PROVADOS.
- Próximo grupo: exports legados ausentes (sobretudo `core.ipc_handlers`, `core.pc_voice_intent`, `core.voice_stt`); comparar contratos e histórico antes de adicionar compatibilidade, sem mascarar comportamento que deixou de existir.
