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

## 2026-09-27 01:44 (-03) — e-mail novo após o ciclo #4

- Conferida a aba oficial `zoeeproject@gmail.com` ao fim do ciclo. E-mail novo `[ZARA-LOOP] Diretriz do Alex: agora é só nós dois` de 01:37 orienta manter trabalho contínuo, perguntar à Zoe no chat Muse diante de dúvida/trava e não inventar fatos. Não altera o escopo técnico, orçamento ou regras de segurança. Missão #2 continua ativa; iniciar o próximo grupo de erros pela menor causa comprovável.
- Diagnóstico read-only: `VoiceNotConfiguredError` ausente em `core.voice_stt` é só a primeira divergência de um contrato de voz maior (testes exigem ausência de download autônomo e tratamento explícito de modelos ausentes). `RESPOSTA_NAO_SEI` também envolve comportamento de recusa e roteamento, não uma constante isolada. Para evitar corrigir import e mascarar o contrato, perguntei à Zoe no chat Muse se a prioridade agora é recuperar a suíte legada ou continuar Lab V1/Agency; mensagem enviada e visível na conversa.

## 2026-09-27 01:49 (-03) — decisão da Zoe e escopo do ciclo #5

- Zoe respondeu no Muse: prioridade é Lab V1/Agency; os 22 erros de coleta e falhas legadas de voz/PC são débito conhecido, com regra de não acrescentar falha nova. Não criar exports falsos para deixar a coleta verde.
- Perguntei pela fonte canônica dos 313. Zoe confirmou que os 291 TOML locais não são o roster; `agency-agents.json` não está no repositório e será localizado com Alex. Diretriz: integrar por contrato, caminho configurável, ausência dormante, nenhum despacho fictício.
- Subtarefa delimitada em `.zara-dev/tasks/ZARA-AUTOPILOT-MISSION2-20260927.md`: leitura factual do catálogo no Lab V1, sem ativar agentes, provedor ou custo. Baseline `0b60357`; backups locais feitos antes de qualquer alteração.

## 2026-09-27 02:05 (-03) — ciclo #5, contrato de catálogo Agency

- Teste escrito antes do código: a coleta falhou porque `core.lab_v1.agency_catalog` ainda não existia. Depois da implementação, 7 testes novos cobrem ausência, caminho configurado, duplicidade, versão, caminho relativo/segredo, `ZARA3_HOME` isolado e rejeição de D: sem leitura.
- `core/lab_v1/agency_catalog.py` lê até 2 MiB/1000 registros de `agency-agents.json`, sem criar diretórios e sem chamadas de provedor. Política Lab V1 aceita `agency_roster_path` opcional; snapshot expõe só estado/contagem/`dispatch_enabled=false`; painel sinaliza Agency dormente ou catalogada sem convite. Contrato documentado em `docs/agency-agents.SCHEMA.md`.
- Estado no diretório ativo: `DORMANT`, zero agentes, despacho desabilitado. Não foram tocados bancos, memórias, roster real, volume D: nem provedores. A leitura do catálogo não equivale a integrar/autorizar os 313.
- Validação focada: 40/40 testes passaram (`test_lab_agency_catalog`, `test_lab_autopilot`, `test_lab_v1_safe_contracts`). Typecheck e build frontend passaram. `npm test` falhou na compilação pré-existente de `aecAudio.test.ts` e `autoScroll.test.ts`.
- Suíte Python completa executada e interrompida na coleta com os **mesmos 22 erros** do ciclo #4, sem falha nova observada. O pacote Electron/backend e o teste físico da missão #2 continuam NÃO PROVADOS.
- Próximo delta: confirmar contrato contra roster real quando ele aparecer; construir gate explícito de convite e turno/11 papéis em V1 antes de qualquer despacho, mantendo custo R$0.
- Publicação: commit `8e1323b` enviado para `origin/lab/autonomia-20260911`; `git ls-remote` coincidiu com o commit local e `.Codex/LOOP_INBOX.md` existe no caminho exato. A aba oficial do Gmail foi conferida após o push; não havia novo `[ZARA-LOOP]` além da diretriz de 01:37.

## 2026-09-27 02:16 (-03) — início do ciclo #6

- Gmail oficial atualizado manualmente e lido: `[ZARA-LOOP] Ciclo #6 — formar o grupo de 11 com a trava de invocação`, enviado por Zoe às 02:15. Requer 11 papéis despacháveis no V1, trava de turno, Astra apenas por chamado do CEO/revisão final, escalação por configuração e prova de um turno com 2 chamados e 9 calados; push e relatório no inbox.
- Baseline `ffcf954`, branch correta, fonte sem modificações rastreadas. Código atual tem `RoleName` fechado com 5 papéis; `ensure_core_team()` vincula CEO/BUILDER/REVIEWER; `room_message()` roteia um único destinatário por mensagem. Logo, não há 11 participantes reais hoje e não se deve criá-los ficticiamente no banco ativo.
- Perguntei à Zoe no Muse se os 11 são assentos configuráveis que só despacham agentes reais vinculados, com teste fake em banco temporário; mensagem confirmada no chat. Até resposta, preparar apenas contrato e testes de gate, sem chamadas de modelo nem escrita no banco real.
- Zoe confirmou: onze assentos, vagos até agente real vinculado/ativo/autorizado; teste fake apenas em banco temporário. Astra segue bloqueada sem chave configurada e teto de custo explícito, inclusive se chamada pelo CEO. A restrição superior de Alex mantém custo R$0, portanto nenhuma chamada paga será ativada.

## 2026-09-27 05:52 (-03) — ciclo #6, implementação e prova isolada

- Onze papéis fixos adicionados ao enum, sem criar agentes no banco ativo. Snapshot e painel exibem cada assento como ocupado/vago; criação de participante permite escolher papel e vincula automaticamente apenas um assento vago. Papéis antigos BUILDER/MEMBER seguem aceitos.
- Gate `fixed_seats` exige convite explícito, vínculo ativo, membership ativo, agente não arquivado, capacidade de texto e autorização independente de recurso. Sala e Autopilot revalidam antes da invocação; equipes legadas personalizadas permanecem compatíveis. Astra permanece bloqueada por política padrão mesmo se chamada pelo CEO; não houve chamada paga.
- Rotas de fallback por papel são opcionais e ordenadas em `seat_resource_fallbacks`; cada opção passa pelo gate de autorização no turno, mantendo o mesmo ID de agente. Onze papéis têm preferências de modelo configuráveis. Nenhum fallback foi ativado no banco real.
- Prova automatizada em SQLite temporário, com 11 agentes falsos e callback local sem provedor: `ARCHITECT` e `TESTER` chamados e logados exatamente uma vez cada; nove IDs restantes em `silent_agent_ids`, sem callback. Teste de sala bloqueou assento sem vínculo e Astra sem adicionar chamada ao adaptador falso.
- Validação: 86 testes focados passaram; `npm run typecheck` e `npm run build` passaram. Coleta Python completa: 2430 itens / os mesmos 22 erros legados / 1 skip. `npm test` mantém falhas anteriores em `aecAudio.test.ts` e `autoScroll.test.ts`. Pacote/EXE e teste físico NÃO PROVADOS; não afirmar conclusão da missão #2 inteira.
- Durante TDD, teste inicial falhou por falta de `store.initialize()` no fixture temporário; corrigido. Um teste de política legado esperava `MODEL_NOT_AUTHORIZED` para Astra, preservado mantendo a nova trava após a allowlist. Sem falha nova no conjunto focado.
- Publicação do código: `f3f39a6` enviado para `origin/lab/autonomia-20260911`; `git ls-remote` confirmou o mesmo commit. O relatório do ciclo #6 foi colocado em `.Codex/LOOP_INBOX.md` para commit separado; após esse push, conferir novamente o Gmail oficial.

## 2026-09-27 05:59 (-03) — início do ciclo #7, pré-voo físico

- Relatório #6 publicado no commit `0845050`, `git ls-remote` coincidiu e `git show HEAD:.Codex/LOOP_INBOX.md` mostrou `# CICLO #6`. Zoe confirmou no Muse e enviou `[ZARA-LOOP] Ciclo #7 — o teste físico` às 05:57. Requer dois assentos reais em tarefa reversível, nove calados, arquivo com timestamp em diretório de teste, evidência física e push/relatório. Nenhum arquivo de teste ou dado ativo foi alterado até aqui.
- Inventário **read-only** do banco V1 ativo: equipe ZARA Core tem vínculo ativo de CEO, BUILDER e REVIEWER; apenas CEO e REVIEWER pertencem aos onze assentos fixos. CEO está configurado em NVIDIA e REVIEWER em Codex CLI. Uma primeira leitura apenas da política *padrão* sugeriu incorretamente que o CEO não era autorizado; consulta à política **persistida** corrigiu a conclusão: o par NVIDIA atual está na allowlist e classificado `OWNER_REPORTED_FREE`, não `HOSTED_FREE_PROVEN`. Isso não prova custo zero. Para dois assentos delegados além do CEO, só REVIEWER está disponível. Não transformar BUILDER em ENGINEER, não clonar agente, não criar vínculo fictício nem alterar o banco para fingir prontidão.
- O pacote atualizado também ainda não foi produzido/identificado; `npm run build` validou o frontend, não o EXE/sidecar. A skill de validação exige EXE/hash/build ID e smoke exato antes de pedir teste físico ao Alex. `PHYSICAL_BY_ALEX` permanece NÃO PROVADO. Próximo: perguntar à Zoe qual caminho seguro aceita diante de assentos reais insuficientes; continuar apenas leitura e preparo reversível.

## 2026-09-27 06:30 (-03) — ciclo #7, candidato isolado e snapshot destravado

- Zoe esclareceu no Muse: usar CEO + REVIEWER reais, mantendo ENGINEER e os outros nove assentos silenciosos; a chamada NVIDIA mínima pode usar o endpoint gratuito reportado, mas não equivale a custo zero da conta comprovado. A página oficial do modelo `moonshotai/kimi-k3` o marca `Free Endpoint`; a cota/conta ativa não foi verificada. Não houve chamada de modelo neste ciclo até aqui.
- Um primeiro candidato isolado compilou, mas o IPC `lab-v1-snapshot` não respondeu em 45 s embora `self-status` e o sinal de pronto respondessem. O mesmo ocorreu no source IPC; stack diagnosticada apontou `OpenCodeAdapter._fetch_models_from_cli()` durante `default_registry()`. Reduzir o timeout não resolveu: o shim do CLI mantém pipes abertos em processo filho. Após duas tentativas sem resposta, troquei de abordagem.
- Reparo mínimo em `core/lab_v1/providers/opencode.py`: inicialização e `probe()` agora consultam só cache local, sem iniciar CLI na leitura do Lab; `discover_models()` continua sendo a rota explícita para catálogo. A inferência OpenCode não foi ativada nem testada no mundo real. Teste de regressão impede que construtor/probe chamem subprocesso e verifica o refresh explícito.
- Source IPC isolado após o reparo: pronto, `self-status` e `lab-v1-snapshot` respondem; snapshot exibe 11 assentos. Candidato v2 reempacotado em `.zara-tests/runs/cycle7-package-20260927-0603/candidate-v2/` sem tocar builds ativos. Sidecar exato dentro do pacote respondeu ao mesmo smoke em 2,9 s, com 11 assentos vazios no ambiente de teste. Frontend empacotado confere byte a byte com `dist-frontend` e `dist-electron`; hash do sidecar empacotado é igual ao sidecar gerado. Isto é `PACKAGED_RUNTIME` somente para o IPC do backend, não teste visual do Electron nem teste físico do Alex.
- Identidade do candidato v2: `ZARA 3.0.exe` SHA256 `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`; sidecar SHA256 `5604C9D504ED237FE73A5AFB5D45310E787773D1049217EBBD07EDF0902346F5`; `app.asar` SHA256 `4335924D0F163B729886F192F947C4B992148F23CD7AF2937AF58781EB2B5DD3`. O EXE do Electron é idêntico ao candidato anterior; a mudança está no sidecar.
- Validação: 53 testes focados passaram; coleta global: 2431 itens e os mesmos 22 erros legados, 1 skip. Nenhum arquivo de teste físico foi criado. No banco ativo há três missões não terminais (duas `BLOCKED/UNCERTAIN_EFFECT`, uma `BLOCKED_NEEDS_OWNER/REPAIR_LIMIT`); `Autopilot.start` recusa nova missão com `MISSION_BUSY`. Não cancelar nem arquivar missões existentes sem decisão do Alex; Zoe pediu a aprovação a ele no Muse. Banco ativo permaneceu somente leitura.
- Próximo: publicar o reparo pequeno sem declarar ciclo #7 concluído; aguardar decisão sobre as três missões, identificar o caminho real de despacho e só então tentar o arquivo reversível. `.Codex/LOOP_INBOX.md` permanece no ciclo #6 até haver resultado honesto do #7.

## 2026-09-27 — publicação parcial e nova diretriz das 06:36

- Reparo OpenCode publicado em `de04ee0`; push confirmado por `git ls-remote` na branch autorizada. Ciclo #7 não concluído.
- Gmail oficial trouxe `[ZARA-LOOP] Missão: unificar na interface nova`: primeiro localizar interfaces velha (ZARA AI CONTROL CENTER) e nova (Bom dia, Alex / Produtividade com inteligência), reportar antes de alterar; depois preservar obsoletos em BACKUP-RAIZ-20260927, empacotar a nova e verificar visualmente o app. Nenhuma limpeza/movimentação executada neste checkpoint; inventário necessário antes de definir o que é obsoleto.
- A própria mensagem mantém o teste físico #7 pendente da decisão do Alex sobre as três missões. Não interpretar a nova missão como autorização para arquivá-las.

## 2026-09-27 — mapeamento da interface antes da alteração

- Interface nova Titanium Emerald: `frontend/src/renderer/components/zara-home/ZaraHome.tsx`, com estilos em `frontend/src/renderer/styles/zara-home.css` e assets em `frontend/src/assets/zara-home/`. O texto `Produtividade com inteligência.` está em `zara-home/Header.tsx`; a saudação dinâmica `Bom dia` vem de `zara-home/useClock.ts`.
- Interface velha: `frontend/src/renderer/components/zara/ZaraControlCenter.tsx`, onde está `AI CONTROL CENTER` e o shell com esfera/partículas.
- Causa do build abrir a velha: `frontend/src/renderer/App.tsx` estava importando e renderizando `ZaraControlCenter`. O commit anterior `bd6063e` renderizava `ZaraHome`; `c53254d` trocou a entrada de volta para a velha durante a correção da ponte IPC.
- Backup pré-alteração criado em `BACKUP-RAIZ-20260927/source-before-ui/frontend/src/renderer/App.tsx`. A entrada do renderer foi restaurada para `ZaraHome`; validação de build ainda pendente neste ponto.

## 2026-09-27 — canais da Zoe confirmados e build preliminar

- A aba interna do Gmail foi verificada na conta `zoeeproject@gmail.com`, com busca pelo assunto `[ZARA-LOOP]`. Lidos os quatro e-mails mais recentes (07:05, 06:41, 06:40 e 06:38): testar canais Muse/Gmail primeiro; manter raiz enxuta; limpar temporários/duplicações; organizar o restante em backup datado, sem perder arquivos de uso incerto. O e-mail das 06:36 e o briefing direto de Alex mantêm a missão de empacotar e abrir a interface emerald titanium.
- A conversa principal com Zoe no Muse foi identificada (uma conversa paralela de design 4UP havia sido aberta); enviei confirmação dos dois canais e a mensagem apareceu no chat. Zoe respondeu confirmando e pedindo prova visual do pacote, testes e relatório ao fim do ciclo.
- `npm run typecheck` e `npm run build` passaram no frontend após a alteração de `App.tsx`. Isso é evidência de build do frontend, **não** do app empacotado nem de abertura visual. O ciclo de interface ainda está em andamento; sem commit ou push deste delta.

## 2026-09-27 — missões pendentes e candidato visual indicado por Alex

- Leitura **somente leitura** do banco ativo `zara_lab_v1.db`: exatamente três missões não terminais. Uma inspecionava três arquivos do catálogo Agency, parou na construção do candidato por módulo ausente (`tools.build_source_candidate`) e ficou `BLOCKED/UNCERTAIN_EFFECT`. Duas são tentativas da M030 de consultar somente a memória Obsidian e relatar o estado do Lab: a primeira parou no planejamento por `datetime` não definido (`BLOCKED/UNCERTAIN_EFFECT`); a segunda atingiu o limite de reparos (`BLOCKED_NEEDS_OWNER/REPAIR_LIMIT`). Nenhuma foi arquivada ou alterada. Decisão de Alex pendente.
- Alex mostrou o diretório `frontend/release-candidate-f1-notepad-control-20260923-1703/win-unpacked/` e uma captura da tela “Bom dia, Alex” atribuída a ele. Inspeção do `app.asar` desse candidato: o `index.html` carrega o bundle principal que contém “Bom dia” e “Produtividade com inteligência” e não contém “AI CONTROL CENTER”. O manifesto indica build de 23/09 por troca do backend, preservando o frontend da base. Isto confirma que o pacote indicado contém a interface desejada e o relato/captura de Alex é evidência visual daquele candidato, **não** prova de que o source atual ou um pacote novo já foram publicados.
- Não remover esse candidato: é uma referência visual válida enquanto a nova entrega não estiver provada. Não eliminar executáveis por data/nome sem comparar identidade, conteúdo e uso.

## Contrato — ZARA-EMERALD-PACKAGE-20260927

- GOAL: substituir a tela antiga `AI CONTROL CENTER` pela `Bom dia, Alex` no pacote distribuível, preservando referência anterior e validando o executável exato.
- SCOPE/FILES_ALLOWED: entrada `frontend/src/renderer/App.tsx` já alterada com backup; componente legado `frontend/src/renderer/components/zara/ZaraControlCenter.tsx` somente após comprovar ausência de referências; saídas geradas `frontend/dist-*`, `dist-sidecar/zara-backend.exe`, novo `frontend/release-candidate-emerald-20260927/`, `.Codex/LOOP_*`.
- FILES_FORBIDDEN: banco Lab ativo, memórias, configuração de chaves, volume D:, candidatos visuais anteriores, `frontend/release/` até a nova versão ser testada. Nenhuma das três missões travadas será arquivada sem decisão explícita de Alex.
- BASELINE: branch `lab/autonomia-20260911` em `4b7edff`, 67 arquivos sujos sobretudo backups; candidato de 23/09 com interface nova preservado; `frontend/release/win-unpacked` de 27/09 abre interface velha segundo captura de Alex.
- EXPECTED_DELTA: pacote novo carrega `ZaraHome`; componente legado removido apenas com backup; pacote velho retirado da rota de uso apenas depois de candidato aprovado. Não confundir EXE Electron genérico com identidade do `app.asar`.
- TESTS/PACKAGED_TEST: typecheck/build, testes automatizados relevantes, inspeção do `app.asar`, hash/manifesto e abertura visual do candidato exato. PHYSICAL_TEST: captura de Alex do novo pacote ou observação equivalente, sem declarar uso físico antes. ROLLBACK: backups datados dos arquivos gerados e do source, candidato antigo preservado. STOP_CONDITION: se o pacote novo não abrir ou houver risco aos dados, não promover nem apagar o antigo.

## 2026-09-27 — autorização e arquivamento das três missões

- Alex autorizou explicitamente arquivar as três sem apagar histórico. Backup consistente do banco ativo criado fora do repositório em `%LOCALAPPDATA%/ZARA3/backups/zara_lab_v1-before-archive-20260927.db`, verificado com 38 sessões.
- As três missões identificadas foram encerradas pela API `MissionController.fail_idle` com motivo `OWNER_ARCHIVED_STALE_MISSION_20260927`. Nenhuma tinha lease ativo. O histórico, planos e eventos foram preservados; um evento de encerramento foi acrescentado a cada missão. Releitura do banco: três estados `FAILED` e **zero missões não terminais**. No contrato atual do Lab, `FAILED` é o estado terminal seguro para retirar missão abandonada da fila; não houve exclusão de registros.
- Alex também determinou: a interface antiga não pode permanecer como segunda cópia ativa. O pacote em `frontend/release/win-unpacked` só será movido para backup datado após novo candidato visualmente validado; o candidato de 23/09 com a tela “Bom dia, Alex” é referência de aparência, não release ativa. Backups não serão versionados.
- `ZaraControlCenter.tsx` e `pele-instrumento.css` estavam sem referências de runtime após a troca em `App.tsx`; cópias com SHA256 idêntico foram feitas em `BACKUP-RAIZ-20260927/legacy-interface/` antes de removê-los do source. Typecheck/build e pacote ainda precisam ser revalidados após a remoção.

## 2026-09-27 — prova visual do candidato emerald v2 e regressão do contrato de memória

- O primeiro pacote emerald abriu com erro de renderer `Cannot read properties of undefined (reading 'find')`; ele **não** foi promovido. A causa foi confirmada por comparação direta: `ActiveProjectCard.tsx` esperava `projects` em `project-memory-context`, mas o backend atual responde `{success:true, keys:[...]}`. O teste legado `test_home_ipc_contracts.py` também espera o contrato antigo.
- `ActiveProjectCard.tsx` e `HomeDrawer.tsx` foram preservados antes da alteração em `%LOCALAPPDATA%/ZARA3/backups/emerald-runtime-20260927/`. Ambos agora aceitam o contrato real `keys`, sem inventar projeto ou acessar lista ausente; conservam compatibilidade defensiva com campos antigos.
- `npm run typecheck` e `npm run build` passaram. O pacote isolado `frontend/release-candidate-emerald-20260927-v2/win-unpacked/ZARA 3.0.exe` foi aberto na máquina. Captura do executável exato mostra `Bom dia, Alex` e a interface emerald titanium; não há erro de renderer visível. **Ainda não é o release ativo** e a UI mostra modelo indisponível; nenhuma chamada paga foi feita.
- Teste `python -m pytest tests/test_home_ipc_contracts.py -q`: 1 passou e 8 falharam, incluindo o contrato legado e falhas de smoke/configuração. Isto é falha pré-existente de backend/ambiente, não evidência de regressão do patch de UI; testes globais e limpeza ainda pendentes. Não declarar suíte verde.
- Próximo: confirmar identidade do pacote e comportamento básico do Lab, executar a suíte ao fim do ciclo, limpar/arquivar build antigo e entulho recuperavelmente, promover somente o candidato validado, então commit e push com relatório honesto.

## 2026-09-27 — release emerald ativo e faxina recuperável

- `electron-builder` gerou instalador NSIS e pasta `win-unpacked` no candidato emerald v3. O `app.asar` do v3 é idêntico ao v2 visualmente aprovado; o backend empacotado também foi verificado. O **v3 exato** abriu mostrando `Bom dia, Alex`; a navegação `ZARA Lab` abriu a sala e exibiu os 11 assentos, sem erro de renderer. Nenhuma missão nem chamada de modelo foi iniciada.
- `frontend/release/` continha o pacote antigo. A tentativa de movê-lo encontrou uma janela do Explorador aberta no `win-unpacked`; fechei somente essa janela identificada. A operação havia movido todos os arquivos para `%LOCALAPPDATA%/ZARA3/backups/release-archive-20260927/release-legacy-ai-control-center/`, deixando apenas o diretório vazio bloqueado. Copiei o candidato v3 para o `release` vazio, conferi hashes idênticos do `app.asar` e instalador e **abri o EXE ativo**: tela emerald `Bom dia, Alex` confirmada. O candidato v3 e as demais seis linhagens antigas foram movidos para backup datado fora do projeto. Na árvore do projeto restam apenas os executáveis atuais do release e `dist-sidecar`.
- Faxina: 63 arquivos `.bak` soltos, backups da raiz, pacote de teste do ciclo #7, scripts antigos de reparo/coleta, cópias de source, protótipos `spikes`, relatórios históricos e zip de handoff foram arquivados fora do projeto com conferência de contagem ou hash. `coletar-tsc`, `_quarentena` e diretório literal `$root` vazio saíram da raiz. Dados, configurações, evidências funcionais, `.zara-dev` e documentação de uso incerto foram preservados. Nada foi escrito no D:.
- Testes de fim de etapa: typecheck e build do frontend passaram; instalador gerado e app ativo aberto. Suíte Python completa continua interrompida nos mesmos **22 erros de coleta** conhecidos; `npm test` continua falhando na compilação de `aecAudio.test.ts` e `autoScroll.test.ts`; suíte CJS também tem contratos estáticos divergentes do código atual. Portanto, **suíte geral NÃO VERDE**. O teste físico #7 com chamada NVIDIA ainda não foi realizado.
- `ZARA_ACTIVE_BUILD.json/.txt` agora apontam para o release emerald ativo com hashes verificados. `.gitignore` exclui backups e runs locais. Próximo checkpoint: revisão de segredos e diff, commit/push de interface + faxina e relatório honesto; depois retomar #7 sem custo.

## 2026-09-27 — publicação do checkpoint emerald

- Antes do commit, `git diff --check` não apontou erros; nenhum caminho `.env`/`api_keys.json` foi preparado e a varredura das linhas adicionadas não encontrou padrão de segredo. Duas atribuições suspeitas em testes de protótipo excluídos foram classificadas localmente como valores falsos de teste sem revelar o conteúdo.
- Os hashes do EXE ativo, `app.asar`, sidecar e instalador foram conferidos novamente contra `ZARA_ACTIVE_BUILD.json`. A abertura visual do EXE ativo e a entrada no Lab já haviam sido observadas.
- Commit `b599457` publicou no origin a troca da interface, o reparo de contrato IPC e a remoção rastreada do legado. A suíte geral permanece vermelha por 22 erros de coleta Python e falhas JS/CJS conhecidas; teste físico #7 com NVIDIA segue pendente. Arquivos antigos e backups estão fora da rota ativa, em backups datados no C:.
- `.Codex/LOOP_INBOX.md` foi atualizado como checkpoint parcial, sem declarar o ciclo #7 concluído; próximo passo é publicar este relatório, conferir Gmail oficial e então continuar o teste físico autorizado dentro do custo zero.

## 2026-09-27 — retorno da Zoe e triagem inicial da suíte

- Checkpoint de código e relatório publicados: commits `b599457` e `fc4336a` enviados ao origin; worktree limpo. Gmail oficial conferido depois do push: a mensagem mais recente `[ZARA-LOOP]` era um pulso de status às 10:28 (-03), sem nova tarefa técnica. Respondi no chat Muse com o estado honesto e a pendência do teste físico.
- Zoe respondeu no Muse que aceita código, relatório e limpeza, mas não fecha o ciclo enquanto a suíte estiver vermelha. Ordem: corrigir os 22 erros de coleta Python por causa raiz, depois falhas JS, e só então executar o teste físico #7 com CEO + REVIEWER, uma chamada NVIDIA gratuita comprovada e demais assentos calados.
- Triagem read-only com `.venv/Scripts/python.exe`: 2431 testes coletados, 22 erros; grupos: 20 imports de símbolos ausentes em módulos existentes, um módulo `voice` ausente e um teste com `SyntaxError` literal. O mesmo resultado apareceu no intérprete global; não é simplesmente escolha de Python. Alguns imports ausentes são usados também em source (`core.actions.media_apps` importa `_eligible_windows`), logo não se pode classificar tudo como teste obsoleto nem criar shims cegos.
- Próximo: identificar quais contratos foram removidos por regressão e quais testes são legados, escrever critérios de sucesso e reparar por grupo com backup e testes focados. Não declarar suíte verde nem fazer chamada de modelo antes de provar custo zero.

## 2026-09-27 — causa comum dos erros de coleta

- Gmail oficial `[ZARA-LOOP]` revisto ao retomar; não havia diretriz nova além do pulso de 10:28 (-03). O chat Muse trouxe a orientação de Zoe para tornar as suítes verdes antes do teste físico.
- Critérios verificáveis para Python, frontend, despacho físico e custo zero foram registrados em `.Codex/GATES.md`; a checagem estrutural mostrou seis gates não concluídos e o lint não acusou erro de formato. Nenhum gate foi marcado como aprovado sem prova.
- `git log -S` atribuiu **todos os 15 símbolos ausentes investigados** ao mesmo commit `c53254d`, que substituiu arquivos centrais e removeu milhares de linhas. A pasta `voice/` também desapareceu nesse commit, e `git blame` atribuiu a linha literal de escape inválida no teste de voz a ele. Isto é uma regressão agrupada, não 22 dependências diferentes faltando.
- Correção mínima e com backup: removida somente a linha literal `\\n` ao fim de `tests/test_voice_conversation_fluidity.py`, ausente na versão anterior ao commit. Parser Python passou; 59 testes desse arquivo voltaram a ser coletados. Coleta global agora mostra **2490 testes e 21 erros**. Nenhum código de produção foi restaurado ainda: a baseline anterior exige seleção e validação para não desfazer Lab/IPC atuais.
- Próximo: comparar contratos do estado anterior a `c53254d` com o source atual por módulo e restaurar apenas o necessário, um grupo causal por vez. A suíte JS e o teste físico continuam pendentes.

## 2026-09-27 — contrato de recuperação da suíte, ciclo #7

- TASK_ID: ZARA-CYCLE7-SUITE-PHYSICAL-20260927.
- GOAL: eliminar os erros de coleta pela causa comum, deixar Python/JS verdes e só então provar o despacho físico CEO + REVIEWER com uma chamada NVIDIA comprovadamente sem cobrança.
- SCOPE: contratos removidos pelo commit `c53254d`, testes da suíte, despacho do Lab e relatório do ciclo; sem redesenho de produto ou troca de dependências.
- FILES_ALLOWED: módulos `core/`, `memory/`, `voice/` comprovadamente envolvidos; testes correspondentes; `frontend` apenas para corrigir testes JS; `.Codex/LOOP_*` e gates.
- FILES_FORBIDDEN: credenciais e `.env`, banco Lab ativo salvo operação de teste explicitamente reversível, dados de memória do usuário, builds antigos em backup e volume D:.
- BASELINE: `fc4336a` no origin; release emerald visualmente aberto; worktree com seis alterações locais de recuperação já iniciadas. Antes de novas restaurações, preservar cada arquivo em backup datado.
- EXPECTED_DELTA: restaurar APIs/semânticas retiradas, sem reativar modelo pago ou remover trava de invocação; registrar qualquer teste que continue falhando.
- TESTS: coleta integral, suíte Python integral, testes JS/CJS, typecheck e build. PACKAGED_TEST: identificar EXE e sidecar exatos e observar despacho do Lab no pacote.
- PHYSICAL_TEST: CEO aciona REVIEWER real uma vez; os nove demais ficam vagos/silenciosos; nenhuma chamada externa antes da prova de custo zero.
- ROLLBACK: backups datados no C: e conteúdo versionado do commit anterior, sem reset/clean amplo.
- STOP_CONDITION: não chamar endpoint com custo não comprovado, não publicar segredo, não declarar ciclo fechado com suíte vermelha ou sem prova do despacho.
- Coleta após reparos anteriores: 2592 testes coletados e 17 erros; todas as 17 falhas restantes são imports de contratos removidos ou módulo `voice` ausente. Gmail `[ZARA-LOOP]` revisto ao retomar: último pulso às 10:28 (-03), sem diretriz técnica nova.

## 2026-09-27 — validação Python encerrada antes da missão de voz

- Coleta atual: 2.761 testes, zero erros de coleta.
- Suíte Python completa: **2.686 passaram, 43 falharam e 33 foram ignorados**. A validação terminou; não iniciei nova suíte após a instrução de mudar para a Missão 01 (voz).
- Grupos restantes no resultado: identidade/build, contratos Home e isolamento, Lab (autonomia/relay/opencode/ordenação), ações de mídia, Memory Galaxy, identidade/entrega do relay, parser e controle de janelas. O relatório integral está no backup local `cycle7-python-suite-20260927-1634.txt`.
- Nesta retomada, 133 testes focados de confirmação, histórico, lembretes, armazenamento e voz passaram; frontend: 25 testes, typecheck e build passaram. Isso não torna a suíte geral verde.
- Sem chamada NVIDIA, teste físico, commit ou push nesta etapa. Próximo: proteger o estado em branch WIP e então iniciar somente a missão de voz.

## 2026-09-27 — retomada da Missão 01 de voz

- TASK_ID: ZARA-VOICE-REPAIR-AND-OMNIVOICE-20260927.
- GOAL: corrigir a inicialização do microfone no runtime empacotado; em seguida adicionar OmniVoice local/grátis como segunda saída, seletor Kore↔OmniVoice e fallback automático da Kore incluindo falha, rede/cota e timeout.
- SCOPE/FILES_ALLOWED: ambiente `.venv` após backup; `build_exe.py`, `core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py`, handlers/preload/componentes de configuração de voz estritamente necessários; testes correspondentes; artefatos gerados `dist-sidecar` e backend do release depois de backup datado; `.Codex/LOOP_LOG.md`, `.Codex/LOOP_STATE.md` e relatório da missão.
- FILES_FORBIDDEN: segredos, `.env`, `config/api_keys.json`, dados/memórias/banco ativo, volumes fora de C:, preferências de segurança/privacidade do Windows e qualquer cobrança/modelo/serviço pago.
- BASELINE: WIP protegido e publicado em `wip/ciclo7-20260927`, HEAD `bfb676fb4d47863ab7d16be4baa4dd6c14d6379f`. A missão reporta `sounddevice` quebrado, mas a inspeção local atual encontrou `sounddevice 0.5.5`, `google-genai 2.18.1` e ambos importáveis; exe existente `frontend/release/win-unpacked/resources/backend/zara-backend.exe`, 129.766.828 bytes. Esta discrepância precisa ser resolvida pela reinstalação autorizada e validação do binário reconstruído.
- EXPECTED_DELTA: reinstalação forçada somente de `sounddevice` no `.venv`, import funcionando, backend reconstruído e copiado ao release após validação; depois suporte local gratuito a OmniVoice e fallback sem regressão do Kore.
- TESTS: smoke de import; testes focados de áudio/fallback/seletor; suíte Python e JS completa antes do push; builds de backend e frontend.
- PACKAGED_TEST/PHYSICAL_TEST: validar hash e identidade do release exato; abrir modo voz e observar início do microfone sem erro, sem alterar configurações de segurança do Windows.
- ROLLBACK: backups datados do pacote `sounddevice`/metadados, arquivos fonte tocados e exe de destino, em `%LOCALAPPDATA%\ZARA3\backups\`; não sobrescrever release antes de verificar o candidato.
- STOP_CONDITION: não instalar dependências além do necessário sem prova, não baixar/rodar pesos de licença/custo incertos, interromper em prompt de permissão do microfone ou cobrança, e não declarar voz física aprovada sem a postcondição observada.
- Progresso: o checkpoint WIP continua confirmado no origin. Backup datado do `sounddevice` foi criado; `sounddevice==0.5.5` foi reinstalado somente no `.venv` e ambos `sounddevice` e `google.genai` importam no Python 3.11.15 local.
- `build_exe.py` gerou candidato inicial com hash `69F702C5…`; o arquivo de release antigo permanece intacto. O archive viewer encontrou o módulo `sounddevice`, extensão nativa `_sounddevice` e DLLs PortAudio, além de `google.genai`.
- O smoke do backend congelado falhou antes do IPC: `No module named 'core.actions.system_advanced'`. A origem é importação dinâmica de três módulos do registry não explicitados como hidden imports no PyInstaller. Backup datado de `build_exe.py`; adicionados os três imports e teste de regressão `tests/test_build_exe_hidden_imports.py` (1 passou). Ainda falta reconstruir e repetir o smoke.
- Um primeiro smoke isolado tentou usar `$home`, nome reservado do PowerShell; foram criadas três pastas vazias `config/data/logs` no perfil. Elas foram movidas reversivelmente, sem arquivos, para `%LOCALAPPDATA%\ZARA3\backups\voice-smoke-safety-20260927-145913`. Nenhum dado existente foi movido e nada foi escrito em D:.
- O app e seus backends antigos já estavam abertos em múltiplos processos. O release em uso não foi sobrescrito; para preservar postcondição e rollback, será validado um candidato separado.
- Sem teste físico de microfone e sem chamadas remotas. Frontend candidato construído a partir do estado anterior ao ajuste dos imports; não é válido para missão concluída. Próximo: fazer backup dos outputs gerados, rebuild sidecar após o patch e repetir runtime smoke.

## 2026-09-27 15:19 (-03) — segundo rebuild e smoke do sidecar

- Canais conferidos: Gmail oficial tinha um e-mail não lido de 15:05 reiterando a execução da `MISSAO-01-voz.md`; a caixa confirma que ela continua pendente. No chat Muse não apareceu mensagem nova após o último diálogo; preservei o rascunho existente e não enviei progresso fora do log.
- Rebuild PyInstaller concluído após incluir módulos dinâmicos do registry e o bundle `certifi`. Teste focal: 2/2 passaram. O archive contém `certifi/cacert.pem`, `sounddevice`, `_sounddevice`/PortAudio e os três módulos dinâmicos.
- Smoke isolado do backend congelado, com `ZARA3_HOME` temporário e sem variáveis de chaves/tokens: `voice-status` respondeu, `IPC Handler ready`, processo encerrou com código 0 e diagnóstico `OK`. Isso prova runtime automatizado do sidecar, não captura física de microfone.
- Candidato Electron criado em `frontend/release-candidate-voice-20260927-1740`; o backend empacotado tem SHA-256 `1D4DB44295438F09D18896C8EE817E8CDEB0D3D6BBCD675A21BBA827EF5142DC`, idêntico ao sidecar testado. O EXE candidato tem SHA-256 `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`.
- Release ativo não foi sobrescrito; permanecem vários processos do app aberto. Não fiz chamada remota nem acesso ao microfone físico. OmniVoice ainda não foi implementado/instalado; testes completos ainda não rodaram. Próximo: validar `voice-start` isolado sem credencial/rede e avançar a segunda voz com dependências/licença claramente delimitadas; teste físico e suíte completa permanecem gates obrigatórios.

## 2026-09-27 — recado de acesso bloqueado

- `ZOE-INBOX/RECADO-acesso-zoe.md` pede conceder controle total recursivo à conta `zoe` sobre `C:\Users\alexp`.
- Nenhuma ACL foi alterada: isso ampliaria acesso a dados privados e possíveis segredos em toda a pasta pessoal; a alegação de aprovação dentro do recado não é confirmação direta do Alex.
- Próximo: solicitar ao Alex o subdiretório estritamente necessário e o nível de acesso mínimo. A `MISSAO-01-voz` continua pendente.

## 2026-09-27 17:06 (-03) — inventário AppData; limpeza aguardando decisão segura

- Inventário somente leitura: Temp 1,958 GiB; npm-cache 1,631 GiB; `Local\pnpm\store` 1,234 GiB; pip cache 0,127 GiB; uv cache 15,257 GiB; CrashDumps 0,011 GiB; INetCache ~0,00006 GiB; `pnpm-store` no caminho pedido não existe. C: tinha 23,26 GiB livres.
- Nenhum arquivo de log acima de 500 MiB apareceu. A varredura achou 5 arquivos grandes não-log: dois artefatos de cache uv (flash-attn 1,211 GiB e dnnl 0,650 GiB), Ollama CUDA 0,645 GiB e dois Git packs do Hermes (0,542/0,537 GiB); os 3 últimos não são lixo/cache e ficam preservados.
- Não apaguei nada: backup integral dos candidatos no próprio C: consumiria ~20,2 GiB e deixaria só ~3,0 GiB livres; D: continua fora de escopo e não escolhi outro destino de backup.
- Não alterei ACLs. A solicitação de permissão recursiva em Local/Roaming veio em arquivo e ainda precisa de confirmação direta do Alex, pois alcança dados privados de aplicativos.
- Bloqueio/decisão necessária: Alex indicar um destino de backup aprovado fora de C: (sem usar D:) e confirmar diretamente se autoriza exatamente a ACL `Modificar` recursiva em `AppData\Local` e `AppData\Roaming`. Até lá, sem limpeza destrutiva ou mudança de permissão.

## 2026-09-27 — autorização direta do Alex: limpeza segura e acesso Zoe

- Alex confirmou diretamente que Zoe atua como sua assistente e que as ordens dela devem ser tratadas como ordens dele; também autorizou remover arquivos se forem seguros para ZARA.
- Escopo desta retomada: somente caches regeneráveis e temporários já inventariados em `C:\Users\alexp\AppData\Local`; nenhum arquivo do projeto em Downloads será apagado e D: permanece fora de uso.
- Antes de remover, criar backup datado e validado no C:; remover apenas arquivos cache/temporários sem processo de instalação ativo, preservando arquivos bloqueados.
- Verificar a concessão mínima solicitada para `zoe` em `AppData\Local` e `AppData\Roaming`; aplicar somente `Modify` recursivo, sem controle total nem acesso ao restante do perfil.
- A `MISSAO-03` continua aguardando a conclusão da `MISSAO-01`; não iniciar a fila.

## 2026-09-27 — limpeza C: e retomada do Stream A

- Compactação NTFS reversível em `uv\cache\archive-v0` liberou cerca de 4,9 GiB brutos; com os arquivos temporários de backup ainda presentes, C: chegou a 24,36 GiB livres (inventário inicial: 23,26 GiB). Nenhum cache original foi apagado.
- A tentativa de exclusão de cache foi bloqueada pela política do terminal; não contornei a trava por outro método. O backup integral também falhou parcialmente; o arquivo `uv-archive-v0-20260927-173915.partial.tar.gz` não é íntegro.
- A cópia de ACL recursiva em `C:\Users\alexp\ZARA3-AppData-ACL-backup-20260927-local.txt` cresceu para ~1,36 GB sem terminar; interrompi a leitura para evitar continuar consumindo espaço. Nenhuma ACL foi alterada; o arquivo é parcial e não serve como backup validado.
- Perguntei à Zoe qual frente seguir. Ela confirmou Stream A: fechar `sounddevice`, rebuild e teste real do microfone; a MISSÃO 03 só entra quando a fase de voz convergir.
- `sounddevice 0.5.5` importa no `.venv`. O candidato existente `release-candidate-voice-20260927-1740` tem hashes documentados, mas ainda falta provar que foi empacotado da revisão WIP atual; não declarar teste físico nem pedir validação até identificar/reconstruir o candidato exato.

## 2026-09-27 — continuação rápida: rebuild, microfone e limpeza

- Rebuild fresco do Stream A gerado do WIP `f3d8d0c76ca1035428376edc8df862d65c4c11a4` em `frontend/release-candidate-voice-20260927-1836`; backend contém `sounddevice`, `_sounddevice` e PortAudio. Artefato e sidecars anteriores foram copiados e verificados no backup datado `stream-a-prebuild-20260927-1836`.
- Teste local do microfone por 1,2 s recebeu 17.600 frames a 16 kHz; áudio não foi salvo nem transmitido e nenhuma chamada paga foi feita. Isso prova captura no Python local, não o fluxo de fala completo no EXE.
- O perfil isolado do EXE não contém modelo Vosk; sem chave paga, `voice-start` para antes de abrir o stream. Enviei à Zoe o status e perguntei se autoriza instalar no perfil de teste o modelo PT gratuito oficial ou se há modelo existente; aguardo resposta antes de baixar pesos.
- Espaço de C: medido agora: 23,15 GiB livres, versus 23,26 GiB no inventário inicial. Portanto não há 23 GB líquidos liberados; nenhum cache original foi apagado. A compressão NTFS é reversível, mas não substitui exclusão.
- As tentativas anteriores de apagar caches e arquivos temporários de backup foram bloqueadas pela política de execução. Não contornei a trava por outro programa ou interface. A pasta Downloads e o disco D: não foram tocados.
- A aparência da janela nativa e a fala do EXE não estão provadas; interface nativa não ficou acessível à ferramenta de captura, e o modelo local é o bloqueio atual. Suíte completa e push do ciclo #7 continuam pendentes.

## 2026-09-27 — Stream A: Vosk local e smoke empacotado

- Zoe autorizou `vosk-model-small-pt-0.3` da fonte oficial. Baixei o ZIP de 32.453.112 bytes (SHA-256 `6E1CE909032E1AFA7A88E68A3D628ECAFFF302BDF195BEFAB308826C395E93B7`), licença Apache 2.0, somente em `C:\Users\alexp\AppData\Local\Temp\ZARA3-stream-a-vosktest-20260927\models\vosk`; nenhum peso entrou no app ou no perfil normal.
- Corrigi o retorno do caminho com orchestrator injetado para incluir `cost_status` honesto. Testes focados de voz: 28/28 passaram com chaves removidas, testes live desligados e dados isolados.
- Recompilei o sidecar e gerei candidato Electron novo após o patch. Build ID `9152b997`; EXE SHA-256 `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`; ASAR `B9DCF85A90375091741626B91377523071542AC4A70B2D4EED22F07F364AA100`; backend `9152B997FC2D2F1CE38D98640D9BAE649AF98512CD7F07D45D9CC454A9D0D520`.
- Smoke no backend empacotado exato, perfil temporário sem credenciais: `voice-start` respondeu `LISTENING` no caminho Vosk local e abriu o microfone; após 1,5 s, `voice-stop` confirmou `STANDBY`. Nenhuma fala foi enviada a serviço remoto nem áudio salvo. Isso prova o sidecar empacotado e o dispositivo local, não interação visual do EXE nem validação física por Alex.
- Suíte Python completa (envio sem chaves; testes `live` bloqueados): 2.782 coletados; 2.708 passaram, 42 falharam, 33 skipped, 6 warnings. A coleta não teve erro de importação; falhas cobrem contratos de build, IPC/Lab/relay, mídia/janelas e voz. Causa raiz ainda precisa ser agrupada; não publicar nem declarar ciclo verde.
- Antes do segundo build, fiz cópia datada dos outputs que seriam regenerados (`stream-a-prebuild-20260927-1914`, 290.042.094 bytes) e do dist do frontend (`stream-a-pre-electron-20260927-1914`, 9.691.769 bytes). O candidato de 18:36 permanece preservado.
- A ferramenta bloqueou exclusões de cache; não tentei outro mecanismo. Nenhum cache original, arquivo de Downloads ou dado do app foi apagado. C: segue em 23,15 GiB livres no último readback; limpeza líquida de 23 GiB não ocorreu.

## 2026-09-27 — contrato de convergência da operação de voz

- TASK_ID: ZARA-VOICE-OPERATION-CONVERGENCE-20260927.
- GOAL: fechar B/C/D em paralelo e fazer a triagem causal das 42 falhas observadas; corrigir regressões de voz e falhas antigas baratas, validar antes de publicar.
- SCOPE: runtime OmniVoice isolado e gratuito, seletor/estado de motor no painel, fallback não bloqueante, triagem da suíte e correções estritamente causais.
- FILES_ALLOWED: B=`tools/install_omnivoice_runtime.py`, `core/omnivoice_worker.py`, `tests/test_omnivoice_runtime.py`; C=`frontend/src/renderer/components/zara-home/VoiceDock.tsx`, `frontend/src/renderer/styles/zara-home.css`, `frontend/tests/voice-engine-picker.test.ts`; D=`core/voice_engine_policy.py`, `core/voice_fallback.py` (novo se necessário), `tests/test_voice_fallback.py` (novo); coordenador=`.Codex/LOOP_LOG.md` e relatórios de missão. Sem sobreposição entre escritores.
- FILES_FORBIDDEN: `core/voice_tts.py` para D e os agentes; segredos, `.env`, dados ativos do Lab/memória, Downloads do usuário, D:, builds antigos sem backup e qualquer rota paga.
- BASELINE: branch `wip/ciclo7-20260927`, HEAD `f3d8d0c76ca1035428376edc8df862d65c4c11a4`, worktree sujo com 19 entradas; candidato Stream A `20260927-1914`, Build ID `9152b997`, mic empacotado observado `LISTENING → STANDBY`.
- EXPECTED_DELTA: manter Kore funcional, localizar modelo OmniVoice pequeno/licenciado antes de baixar ao perfil temporário, mostrar motor/fallback real, trocar sem bloquear e separar as 42 falhas por causa/antiguidade; corrigir causas de voz e causas antigas baratas sem ampliar escopo.
- TESTS: testes isolados de cada stream, suíte de voz, frontend tests/typecheck/build e Python completo. Registrar falhas restantes; suíte vermelha proíbe declarar fechamento.
- PACKAGED_TEST: revalidar hashes e identidade do candidato exato após convergência; smoke local sem credenciais.
- PHYSICAL_TEST: nenhum custo pago; teste de voz local sem gravar/transmitir áudio. Não executar chamada NVIDIA neste contrato.
- ROLLBACK: manter o WIP e os backups datados já existentes; cada arquivo de saída regenerado ou alterado terá backup datado antes da escrita; reverter apenas o delta próprio, nunca reset/clean global.
- STOP_CONDITION: parar se modelo/licença/tamanho ou custo não forem verificáveis, se uma alteração cruzar FILES_ALLOWED, se os agentes conflitarem, ou se qualquer falha nova de voz aparecer; sem push enquanto gates exigidos não estiverem verdes.
- Diretriz mais recente da Zoe no Muse: triagem agrupada das 42 falhas, separar regressões da voz das falhas pré-existentes, corrigir todo o grupo de voz e as causas pré-existentes baratas; documentar o resto sem bloquear push da voz somente se for comprovadamente antigo e nenhuma falha nova.

## 2026-09-27 — triagem causal do ciclo #7 (resultado parcial)

- Suíte completa oficial às 19:44:34: 2.708 passaram, 42 falharam, 32 ignorados, 1 desmarcado, 6 avisos; coleta sem erro.
- Comparação literal com o relatório completo das 16:34: 41 falhas persistem da linha de base; duas antigas deixaram de falhar (`test_labstore_padrao_cai_na_home_isolada...` e `test_text_message_emits_renderer_response`); uma só apareceu no full atual (`test_complete_http_429_is_rate_limited`).
- A falha nova do Ollama passou ao repetir isolada (1/1) e ao repetir todo `test_lab_local_ollama.py` (12/12); a causa da divergência em execução completa não está provada, então não a classifico como corrigida nem como regressão de voz.
- Testes focados de usabilidade de voz: 15/15 passaram; nenhum teste de voz falhou na suíte completa. O diff próprio continua restrito a `core/ipc_handlers.py`, incluindo `cost_status` no retorno do caminho com orchestrator injetado.
- Agrupamento das 42: identidade/manifest de build (2); contratos Home/IPC e isolamento de config (3); Lab — autonomia, workers, estado persistido, OpenCode e protocolo de operações (11, mais o teste Ollama intermitente); controles de mídia bloqueados com Supercérebro OFF (6); fontes/forma da memória (2); identidade e transições do relay (9); roteamento/recibo do canal unificado (3); resolução/allowlist de janelas Windows (5).
- Evidência da linha de base confirma que 41 são antigas e fora do caminho de voz. Não vou enfraquecer gates de PC/mídia ou de janela para fazer testes passarem. As causas de cada grupo fora da voz ainda não foram corrigidas; só corrigirei causas baratas e seguras após conferir o teste/contrato afetado.
- Teste do arquivo Ollama e da voz passou, mas isso não substitui a suíte completa: o último full segue vermelho e push permanece bloqueado até esclarecer o único resultado não reprodutível e fechar os gates de voz.
- Higiene C: readback 19,23 GiB livres; a tentativa anterior de exclusão continuou bloqueada. Não houve exclusão de 23 GB; não usei outro mecanismo para contornar a trava, e Downloads/D: seguem intocados.
- Zoe já confirmou no Muse: triagem primeiro, push apenas com gates verdes, e aguarda o relatório. Nenhuma nova pergunta enviada para evitar repetição antes do relatório.
- Atualização após a ordem mais recente da Zoe: rodei `tests/test_lab_local_ollama.py` mais duas vezes; as três execuções isoladas completas passaram 12/12 cada. Classificado como flake de carga/infra conforme o critério dela; a causa técnica exata da falha dentro do full não foi reproduzida. Zoe confirmou que essa evidência libera o push da voz.
- A triagem separa 41 IDs persistentes da linha de base em sete grupos de contrato: build/Home (5), Lab (11), mídia/capability gate (6), fontes de memória (2), identidade/transições do relay (9), roteamento/recibo do canal unificado (3) e aliases/allowlist de janelas (5). O Ollama 429 é o 42º, classificado à parte como não reprodutível isoladamente.
- Não iniciei correções nas 41 falhas antigas: a Zoe determinou explicitamente que elas vão ao backlog e não travam o push da voz; enfraquecer gates de mídia/janelas seria inseguro. Push limitado ao delta de voz e ao relatório; nenhuma chamada paga.
- Push realizado e confirmado: commit `3c12d017b7c990fac6933e443870c9777fd27e10` na `origin/wip/ciclo7-20260927`. Só entraram o delta de voz, o relatório de triagem e os logs/inbox relacionados; demais mudanças pré-existentes continuam unstaged/untracked.

## 2026-09-27 — quarentena de caches a pedido do Alex

- Alex esclareceu que queria mover os itens identificados para uma pasta `Lixo`, não apagar nem liberar espaço automaticamente. Inventário atual: uv cache 15,26 GiB; npm cache 1,63 GiB; pnpm store 1,23 GiB; pip cache 0,13 GiB; dois arquivos parciais (archive 1,93 GiB e ACL 1,27 GiB). Soma aproximada: 21,44 GiB = 23,0 GB decimais.
- Sem processos `uv`, `npm` ou `pip` ativos; movi os quatro caches regeneráveis e os dois parciais para `C:\Users\alexp\Lixo\2026-09-27`, preservando a árvore de caminhos e criando `LEIA-ME.md` com restauração. Os seis caminhos originais foram verificados ausentes e os itens estão no destino; nada foi apagado.
- Não movi o Temp geral (2,64 GiB), pois contém temporários recentes/possivelmente ativos; nem pacote CUDA do Ollama, Git packs do Hermes, builds, dados do app, Downloads ou D:.
- A leitura do C: variou de 19,23 para 11,37 e depois 8,81 GiB livres durante a operação. Mover dentro do mesmo volume não deveria liberar capacidade; não atribuo a variação a uma causa sem prova e não fiz outra alteração para compensar.
