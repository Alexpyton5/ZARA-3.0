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
