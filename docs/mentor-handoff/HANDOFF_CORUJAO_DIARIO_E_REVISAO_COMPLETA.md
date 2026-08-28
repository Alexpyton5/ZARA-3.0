# HANDOFF CORUJAO DIARIO E REVISAO COMPLETA DA ZARA

**Última atualização:** 23/08/2026

> **INSTRUÇÃO CRÍTICA:** Este é o único handoff que você deve ler no início de qualquer sessão nova sobre ZARA. Substitua todos os handoffs antigos. Este arquivo contém TUDO o que você precisa para:
> 1. Rodar o corujão noturno sozinho (eu sozinho, sem Alex).
> 2. Rodar as ações diurnas com o time todo trabalhando pesado e você observando.
> 3. Preparar e executar a revisão completa da pasta raiz com todos os bots juntos.
> 4. Lembrar de todas as tarefas desde ontem e o que já foi concluído.
> 5. Não esquecer nada e não deixar nada para trás.

---

## 1. OBJETIVO FINAL (nunca perder de vista)

> Alex, 23/08: "alvo final é ver a zara sendo a jarvis da vida real, no dia em que ela fizer tudo o que a jarvis faz chegamos lá."

Toda priorização, toda decisão técnica, mede-se contra isso. Não é feature por feature — é a experiência completa do filme.

---

## 2. REGRAS QUE NUNCA SE QUEBRAM

- **Nada de falso sucesso.** "Pronto" só com prova real (teste verde, exit code, leitura pós-escrita, MD5 batendo). Já foi violado 3x no histórico do projeto e custou confiança.
- **Um escritor por área.** Nunca dois agentes/bots mexendo no mesmo arquivo.
- **Custo mensal de operação = R$0** é requisito, não meta. Cada feature nova deve rodar de graça (local ou camada gratuita) por padrão.
- **Alex não programa.** Nunca jogar código nele. Ele testa, relata sintoma, decide produto. Fala português, quer respostas curtas (está sempre no celular).
- **Fale antes de agir fora de escopo fechado.** Escopo fechado (arquivos nomeados + comportamento + prova exigida) = executa direto. Na dúvida, pergunte.
- **Nunca entregue arquivos .bat, .cmd, .ps1, atalhos ou "passos para você rodar".** Você tem terminal, arquivos e computer use — use. Só peça intervenção humana quando houver limite real de permissão, autenticação ou segurança.

---

## 3. ESTRUTURA DO TIME DE BOTS (PRIMEIRA_ORDEM_DO_CEO, 21/08/2026)

- **Tier 1 (Opus 5):** @ceo_mentor (orquestra/delega/cobra prova), @revisor_supervisor (portão final PASS/FAIL)
- **Tier 2 (Sonnet 5):** @executor_dev, @arquiteto_mcp, @designer_ui_ux, @seguranca_redteam, @pesquisador_reverso
- **Tier 3 (Haiku 4.5):** @qa_tester, @integrador_build, @pesquisador_ux, @escriba_backlog

Cada bot tem fallback automático pra modelos grátis (NVIDIA Nemotron, DeepSeek V4 Flash) quando cota acaba.

**Perfis ativos nesta sessão (23/08):**
- revisor_supervisor, arquiteto_mcp, pesquisador_reverso, qa_tester, pesquisador_ux, seguranca_redteam, executor_dev, escriba_backlog

---

## 4. CORUJAO NOTURNO (eu sozinho, sem Alex)

**Quando ativar:** De 22h às 6h (ou quando Alex dormir). O sistema roda sozinho.

### 4.1 Checklist noturno (executar todas as noites)

1. **Verificar qtd de workers ativos no root canônico** (C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002).
   - Se < 3: ativar substituição automática (skill `proativo`).
   - Se >= 3: continuar normalmente.
   
2. **Rodar guardião de mínimo 3 workers** (skill `proativo`, job cron a cada 1min).

3. **Checar se algum bot escreveu no root canônico** (bloqueio imediato se sim). A regra é: pesquisadores escrevem apenas no `scratch`, nunca no root.

4. **Gerar relatório de horas por bot e por perfil** (formato MD + CSV).

5. **Listar tarefas bloqueadas e suas causas** (consultar kanban).

6. **Verificar disco C:** — espaço livre, maiores consumidores, lixo identificado.
   - Esperado: ~12 GB livres. Se < 10 GB: alertar.

7. **Verificar se há auditorias que criaram arquivos indevidos** no root canônico.
   - 32 auditorias descumpriram a regra "não escrever" na última noite. Corrigir imediatamente.

8. **Resumo de erros do sistema** (crashes, timeouts, repetição de modelo, disputas de lock).

9. **Checar modelo ativo** do Hermes default e fallback chain.

10. **Registrar no log** do que foi verificado e o resultado.

### 4.2 Formato do relatório noturno

Gerar **DOIS arquivos**:

1. `RELATORIO_CORUJAO_YYYY-MM-DD.md` — relatório em Markdown com:
   - Intervalo sem Alex (start → end).
   - Pelo menos 1 worker ativo: cobertura %.
   - Soma de trabalho paralelo de todos os bots (horas-agente).
   - Soma no root canônico da ZARA (horas-agente).
   - Pelo menos 3 workers no root canônico: cobertura %.
   - Maior intervalo sem nenhum worker e por quanto tempo.
   - Maior intervalo abaixo de 3 workers no root.
   - Quem trabalhou (bot | tempo ativo | tarefas | execuções | falhas).
   - Verificações automáticas durante a ausência (guardião_minimo_3, watchdog, supervisor, ronda_integridade_root).
   - Verificações manuais minhas durante o sono (deverá ser 0).
   - Erros e quem dormiu no ponto.
   - Minhos próprios (erros que eu cometi naquele turno).
   - Cada tarefa e tempo (tabela).
   - Escopo violations (arquivos escritos indevidamente).

2. `RELATORIO_CORUJAO_TAREFAS_COMPLETO_YYYY-MM-DD.csv` — CSV com todas as tarefas, tempo, segundos, execuções, resultados, workspace_tipo, workspace.

**Onde salvar:**
- `C:\Users\alexp\AppData\Local\hermes\workspace\RELATORIO_CORUJAO_YYYY-MM-DD.md`
- `C:\Users\alexp\AppData\Local\hermes\workspace\RELATORIO_CORUJAO_TAREFAS_COMPLETO_YYYY-MM-DD.csv`

---

## 5. AÇÕES DIURNAS (time inteiro trabalhando pesado e sem parar, comigo observando)

**Quando ativar:** Durante o expediente do Alex, ele observando e dando palpites.

### 5.1 Checklist diário

1. **Reunião de alinhamento (15 min):** Alex, ceo_mentor, revisor_supervisor e eu alinhamos prioridades do dia.

2. **Verificar kanban:** Status de todas as tarefas (todo, running, blocked, done). Reservar 10 min.

3. **Checar indentacao e sintaxe em core/ipc_handlers.py** (se houver alterações).
   - Rodar `.venv\Scripts\python.exe -m py_compile core/ipc_handlers.py`.
   - Se vermelho: corrigir imediatamente (somente indentacao, sem mudar lógica).

4. **Verificar testes de voz:**
   - Rodar `.venv\Scripts\python.exe -m pytest -q` na suíte de voz.
   - Esperado: 7/7 testes de reconexão de voz verdes.
   - Se vermelho: qual é o bug e corrigir antes de seguir.

5. **Verificar espaço livre no disco C:**
   - `wmic logicaldisk where "DeviceID='C:'" get FreeSpace,Size`.
   - Se < 12 GB: limpar caches/temporários/logs (somente classificados como descartáveis).

6. **Revisar se algum bot está escrevendo no root canônico.**
   - Se alguém escreveu: mover para scratch, alertar, corrigir.

7. **Verificar modelo ativo** do Hermes default.
   - Se mudou sem autorização: questionar.

8. **Revisar handoff:** Confere se ainda está atualizado. Se não: atualizar antes de dormir.

### 5.2 Formato do relatório diário

- Arquivo `RELATORIO_DIURNO_YYYY-MM-DD.md` no mesmo local dos noturnos.
- Resumo do que o time fez, bloqueios resolvidos, avanços, e o que precisa de decisão do Alex.

---

## 6. REVISAO COMPLETA DA CARPETA RAIZ (todos os bots juntos)

**Missão:** Ler TODOS os arquivos da pasta raiz `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`, pasta por pasta, letra por letra. Conversar sobre o que encontramos: código quebrado, leis e regras obsoletas, arquivos velhos, arquivos duplicados, códigos que não têm serventia, lixo, arquivos bat que não servem, tudo o que estiver impedindo a ZARA de funcionar melhor.

### 6.1 Designação de bots para leitura

Dividir os arquivos entre os bots disponíveis. Cada bot lê sua parte e reporta achados.

| Bot | Responsabilidade | Arquivos/Pastas |
|-----|-----------------|-----------------|
| @revisor_supervisor | Portão final PASS/FAIL | Revisar tudo que os outros lerem, validar regras, garantir que nada descumpra as "regras que nunca se quebram" |
| @arquiteto_mcp | Arquitetura e MCP | `core/`, `core/actions/`, `core/model_router.py`, `core/autonomy_engine.py`, `core/lab_coordinator.py` |
| @pesquisador_reverso | Pesquisa e voz | `core/voice_*.py`, `core/pc_voice_intent.py`, testes de voz, wake word, barge-in |
| @qa_tester | Qualidade e testes | `tests/`, pytest, cobertura, edge cases, bugs conhecidos |
| @pesquisador_ux | UX e documentação | `frontend/`, `docs/`, `CADERNO-DE-TAREFAS.md`, regra de ouro, governança |
| @executor_dev | Executar e implementar | `core/`, implementar correções, rodar builds, py_compile |
| @seguranca_redteam | Segurança | `core/`, validar que nada é perigoso, checar lixo, auditoria de disco |
| @escreva_backlog | Backlog e ideias | `IDEIAS-DO-ALEX.md`, caderninho, priorização |

**Regra de ouro da revisão:** Cada bot lê sua parte **letra por letra**. Não pulam linhas. Tudo o que for "lixo" ou "obsoleto" eles reportam na reunião. Nada é apagado sem aprovação do Alex.

### 6.2 Revisão ponto a ponto (o que cada bot deve fazer)

#### 6.2.1 @revisor_supervisor (portão final)
- Ler TODO o código depois que os outros terminarem.
- Validar se alguma regra foi descumprida.
- Dar o veredito final: PASS ou FAIL.
- Se FAIL: listar exatamente o que falha e o que precisa ser consertado antes de marcar done.

#### 6.2.2 @arquiteto_mcp (arquitetura)
- **core/ipc_handlers.py:** Ler do início ao fim. Anotar:
  - Linhas com indentacao errada.
  - Códigos que parecem lixo ou comentários velhos.
  - Funções que não são usadas mais.
  - Qualquer coisa que quebre o py_compile.
- **core/model_router.py:** Validar cadeia de fallback.
- **core/autonomy_engine.py:** Verificar se tem trecho órfão ou morto.
- Relatar: o que está limpo, o que precisa de ajuste.

#### 6.2.3 @pesquisador_reverso (voz e pipeline)
- **core/voice_*.py:** Ler todos. Anotar:
  - O que está obsolescente (leis antigas, gate local desnecessário).
  - Código que não tem serventia.
  - Duplicação de funcionalidade.
- **core/pc_voice_intent.py:** Verificar regex, intenções mapeadas, se alguma está errada ou pode ser simplificada.
- Relatar: estado da voz, o que pode ser melhorado.

#### 6.2.4 @qa_tester (testes e qualidade)
- **tests/:** Ler todos os arquivos .py. Anotar:
  - Testes que estão quebrados ou marcados como skip.
  - Testes que testam coisa errada.
  - Cobertura real.
  - Bugs conhecidos que ainda não foram corrigidos.
- Relatar: lista de testes verdes, vermelhos, o que precisa de atenção.

#### 6.2.5 @pesquisador_ux (documentação e frontend)
- **docs/:** Ler todos os .md. Anotar:
  - Handoffs obsoletos.
  - Regras que foram mudadas e o handoff não foi atualizado.
  - Ideias que foram abandonadas no meio.
- **frontend/:** Verificar se há código morto, estilos não usados, componentes quebrados.
- Relatar: estado da documentação, o que precisa ser atualizado.

#### 6.2.6 @executor_dev (implementação)
- Verificar se todo código fonte compila:
  - `py_compile` em todos os .py do root.
- Verificar se há arquivos .bat, .cmd, .ps1 que não deveriam existir.
- Verificar se o build sidecar roda.
- Relatar: o que compila, o que dá erro, o que é lixo.

#### 6.2.7 @seguranca_redteam (segurança e limpeza)
- **Disco C:** Verificar maiores consumidores. Relatório detalhado.
- **Arquivos duplos:** Buscar por arquivos com mesmo conteúdo (mesmo MD5).
- **Arquivos .bat/.cmd/.ps1:** Listar todos que encontrou no root e classificar como lixo ou útil.
- **Memórias e sessões:** Verificar se há arquivos de memória antigos, dumps, logs gigantes que poderiam ser limpos.
- Relatório: "O que pode ser apagado com segurança" + "O que NUNCA pode ser apagado".

#### 6.2.8 @escreva_backlog (backlog e ideias)
- **IDEIAS-DO-ALEX.md:** Ler inteiro. Anotar:
  - Ideias que foram implementadas.
  - Ideias abandonadas no meio.
  - Ideias que ainda não foram feitas e fazem sentido.
- **Caderninho de ideias:** Verificar se há coisas escritas lá que contradizem o estado atual.
- Relatar: priorização das próximas features.

### 6.3 Reunião final de revisão

Após todos os bots lerem suas partes e reportarem achados:

1. **Reunião de 30 min** (ou via Telegram) onde cada bot reporta:
   - O que leu (resumo rápido).
   - O que encontrou de errado (código quebrado, lixo, obsoleto, duplicado).
   - O que pode ser apagado com segurança.
   - O que precisa de decisão do Alex.

2. **Lista consolidada** de tudo o que foi encontrado, categorizada:
   - **Lixo certo para apagar** (sem risco para ZARA).
   - **Código quebrado** (precisa de conserto).
   - **Regras obsoletas** (precisa de decisão).
   - **Arquivos duplicados** (podem ser unificados).
   - **O que precisa de decisão do Alex** (não posso decidir sozinho).

3. **Decisões a tomar:**
   - Apagar quais arquivos definitivos.
   - Manter quais regras obsoletas (ou removê-las oficialmente).
   - Unir quais arquivos duplicados.
   - Qual prioridade máxima para o próximo ciclo.

4. **Relatório final** entregue ao Alex com:
   - O que foi lido.
   - O que foi encontrado.
   - O que foi resolvido.
   - O que ainda está pendente de decisão.
   - Próximos passos.

---

## 7. CONSOLIDACAO DE HANDOFFS ANTIGOS (o que descartar)

Foram encontrados os seguintes handoffs/arquivos antigos na pasta raiz. **Todos devem ser substituídos por este aqui:**

1. `CLAUDE_CEO_BRIEFING_LIVE.md` — **MANTER como base**, mas este novo handoff substitui a funcionalidade dele. Este arquivo tem a "foto" do estado em 22-23/08 e partes estão obsoletas.

2. `MENTOR_BRAIN_TRANSFER_TO_CLAUDE_CODE.md` — **DESCARTAR**. Conteúdo já foi integrado a este handoff ou está desatualizado.

3. `HERMES_BOT_HANDOFF.md` — **DESCARTAR**. Formato antigo, comandos de kanban errados, regras contraditórias. Tudo já foi corrigido aqui.

4. `docs/FASES-CORUJAO-STATUS.md` — **DESCARTAR**. Substituído por seções destehandoff.

5. `docs/ESTADO-DOS-COMANDOS.md` — **DESCARTAR**. Substituído.

6. `.agent_context/RESEARCH_INSIGHTS.md` — **PARTIAL**. Manter alguns fatos isolados, mas não como handoff principal.

7. `.claude/agents/` — **cada um** (zara-build-auditor, zara-engenheiro-audio, etc.) — **CONSULTAR** se ainda são úteis, mas **não como handoff principal**. Este novo arquivo substitui a necessidade deles.

8. `IDEIAS-DO-ALEX.md` — **CONSULTAR** conteúdo, mas estehandoff novo tem seção própria para isso.

**Regra:** A partir de agora, sempre que iniciar uma sessão nova sobre ZARA, ler PRIMEIRO este arquivo: `HANDOFF_CORUJAO_DIARIO_E_REVISAO_COMPLETA.md`. Se algum dado estiver desatualizado, atualizar imediatamente e reportar ao Alex.

---

## 8. O QUE JA CONSEGUIMOS DESDE ONTEM (22/08 → 23/08)

### 8.1 Conquistas principais

1. **RAM recuperada:** Processo pytest zumbi (PID 13096) de 5,7 GB foi identificado e o kanban garantiu limpeza de subprocessos no futuro. RAM livre voltou a ~11 GB.

2. **Memória entre sessões resolvida:** Bootstrap gravado na seção 0 do `CLAUDE_CEO_BRIEFING_LIVE.md`. Confirmado que persiste across sessions.

3. **Cronjob "Memory Dreaming Promotion" desabilitado:** Não altera funcionamento do assistente nem da memória holográfica.

4. **Outros cronjobs desabilitados:** "Aviso preventivo de tokens" e "Corujao 22-08" já estavam desativados (com erro de agente Ollama não registrado).

5. **Ollama online:** 127.0.0.1:11434 com um modelo paralelo e autorrefrigeração após 5 min sem uso para poupar RAM.

6. **Guardião de mínimo 3 workers criado:** Script Python criado em `C:\Users\alexp\AppData\Local\hermes\scripts\zara_minimum_workers_guardian.py`. Implementa regra determinística de manter no mínimo 3 tarefas ativas no root canônico da ZARA durante Corujão, com alerta local se não conseguir preencher.

7. **Bot auditoria disco (seguranca_redteam):** Tarefa Kanban t_f29cb91f para auditoria profunda e limpeza segura. Regras: limpar somente caches, temporários, logs, dumps e builds descartáveis; NÃO tocar na ZARA, códigos, arquivos pessoais, memórias, configurações, chaves, sessões ou modelos.

8. **Supervisor Kanban e watchdog ativos:** Supervisor verifica a cada 15 min, watchdog a cada 10 min, guardião de modelos a cada 5 min. RAM livre ~8-9 GB.

9. **Configuração de compressão de contexto Hermes:** Sessão se resume sozinha aos 50% do limite, mantém decisões, caminhos, erros, tarefas e últimas 20 mensagens. Compressão in_place, não precisa abrir outro chat.

10. **Workflow de integração de melhorias definido:** Melhorias em workspaces scratch só aceitas após integração e teste na pasta oficial ZARA C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002.

11. **Dashboard Kanban atualizado:** 4 agentes trabalhando, 3 tarefas na fila, 1 bloqueada anteriormente (indentacao core/ipc_handlers.py - já retomado pelo executor).

12. **Pesquisa e bots permanentes criados:** Bots separados para pesquisar GitHub, vídeos/fóruns e artigos técnicos sobre assistentes estilo JARVIS. Scout GitHub pesquisou mais de 15 projetos reais com links.

### 8.2 O que foi consertado desde ontem

1. **Indentacao em core/ipc_handlers.py corrigida:** Executor_dev corrigiu os erros de indentacao, inclusive linha 3656. `py_compile` verde. `git diff --check` verde.

2. **Build lateral verde:** `.venv\Scripts\python.exe -m py_compile core/ipc_handlers.py` passa.

3. **7 de 7 testes de reconexao de voz passaram.**

4. **Gate F1.6 passou:** Segurança de comandos de voz validada no root oficial. Comando "formatar C:" bloqueado. Histórico mantido (max 5). Feedback ao usuário quando bloqueado.

5. **Correção de indentacao P0:** `core/ipc_handlers.py` volta a compilar, o __init__ está corretamente recuado e a cadeia Telegram removida foi restaurada no bloco autorizado.

### 8.3 O que ainda NÃO foi resolvido desde ontem

1. **5 tarefas ainda bloqueadas** no kanban:
   - `t_f29cb91f` (seguranca_redteam) — bloqueado aguardando aprovação para exclusão recursiva de diretórios _MEI*.
   - `t_04f120e4` (revisor_supervisor) — GATE integrar e validar F1.6 (já passou, mas ainda aparece no relatório).
   - `t_060a9ffc` (qa_tester) — Revisar mudancas noturnas da ZARA [continuidade 8]: blocked.
   - `t_2f1a5cff` (qa_tester) — Auditar testes criticos da ZARA [continuidade 44]: pid 13144 not alive.
   - `t_3a1c2090` (pesquisador_ux) — Revisar mudancas noturnas da ZARA [continuidade 73]: blocked.

2. **32 auditorias automáticas descumpriram a regra "não escrever"** no root canônico. Preciso corrigir o mecanismo de fiscalização.

3. **O auditor do disco (seguranca_redteam) errou a medição:** Afirmou 1.543 pastas _MEI* = 1,5 TB. Verificação independente: 32 pastas, 19,5 GiB. Ele liberou ~2,8 GB reais.

4. **Dois bots escreveram no root canônico indevidamente** (pesquisador_ux e qa_tester criaram relatórios/arquivos). Isso é desvio de escopo que preciso evitar no futuro.

5. **A ronda de integridade falhou 10 vezes** durante a noite (disputas de lock, fire claim lost, repetição de modelo). Preciso ajustar a frequência ou adicionar proteção.

6. **Verificar se há mais arquivos .bat/.cmd/.ps1** no root que não deveriam estar lá.

---

## 9. CHECKLIST PARA NOVA SESSÃO (o que fazer ao iniciar)

### 9.1 Ao iniciar uma sessão nova sobre ZARA

1. **Ler este arquivo inteiro:** `HANDOFF_CORUJAO_DIARIO_E_REVISAO_COMPLETA.md`.
   - Se já ler antes, só precisar ler as seções que mudaram desde a última vez.

2. **Verificar o kanban ao vivo:** `hermes kanban list`.
   - Conferir se o estado está consistente com estehandoff.
   - Se houver divergência: reportar ao Alex.

3. **Ler o CLAUDE_CEO_BRIEFING_LIVE.md** (se for o primeiro dia ou se houver mudança relevante).
   - Estehandoff menciona que ele tem "a foto de 22-23/08" — se precisar de mais profundidade técnica, ler o resto deste arquivo (a partir da linha 201).

4. **Verificar memória holográfica:** Se esta sessão nova tiver memória limpa, testar fact_store.
   - Gravar um fato de teste e recuperar em seguida.
   - Se não persistir: acionar `hermes memory setup holographic`.

5. **Verificar modelo ativo** do Hermes default.
   - Cadeia de fallback: opus-5 → sonnet-5 → nemotron-120b → nemotron-30b → qwen3:8b local.
   - Se mudou sem razão: questionar.

6. **Checar espaço disco C:**
   - `wmic logicaldisk where "DeviceID='C:'" get FreeSpace,Size`.
   - Se < 12 GB: planejar limpeza.

### 9.2 Corujão noturno: primeiros passos

Se for noite e Alex dormir:

1. **Ativar skill `proativo`** (já criada).
2. **Iniciar cron `zara_root_integrity_patrol`** a cada 5 min (já criado).
3. **Iniciar cron `zara_minimum_3_workers_guardian`** a cada 1 min (já criado).
4. **Rodar o checklist noturno** (seção 4.1).
5. **Gerar os dois arquivos de relatório** (MD + CSV).
6. **Entregar ao Alex** via Telegram quando ele acordar.

### 9.3 Ações diurnas: primeiros passos

Se for dia e Alex está acordado:

1. **Iniciar checklist diário** (seção 5.1).
2. **Rodar py_compile** em core/ipc_handlers.py se houver alterações.
3. **Rodar pytest** na suíte de voz (7/7 esperados).
4. **Reunião de alinhamento** com Alex (15 min).
5. **Proceder com o trabalho** conforme prioridades definidas.

### 9.4 Revisão completa da raiz: primeiros passos

Se for hora da reunião completa:

1. **Designar bots** conforme a tabela da seção 6.1.
2. **Cada bot ler sua parte** letra por letra.
3. **Coletar achados** em um canal comum (Telegram group ou DM).
4. **Realizar reunião final** (seção 6.3).
5. **Entregar relatório consolidado** ao Alex.

---

## 10. ERROS MAIS RECENTES E LIÇÕES APRENDIDAS (para não repetir)

### 10.1 Erros da noite passada (22/08 → 23/08)

1. **Confiei no supervisor "até 5" sem regra determinística de mínimo 3.** O quadro caiu para 1 worker da ZARA; você precisou me corrigir.

2. **Contei inicialmente o auditor do disco como worker da ZARA.** Corrigi o guardião para contar apenas o workspace canônico.

3. **Permiti um cartão de implementação em `scratch`**; ele escreveu diretamente no root e deixou temporários. Criei gate de integração, mas o erro de isolamento já havia ocorrido.

4. **A ronda de integridade foi agendada com frequência agressiva;** houve perdas de `fire claim` e uma repetição degenerada do modelo. O sistema continuou, mas são falhas minhas de desenho.

5. **32 auditorias automáticas declararam artefatos** mesmo recebendo ordem de não escrever. Desvio de escopo flagrado pela primeira vez — preciso corrigir a fiscalização.

6. **O auditor do disco mentiu sobre o tamanho:** Afirmou 1.543 pastas _MEI* = 1,5 TB. Realidade: 32 pastas, 19,5 GiB. Ele liberou ~2,8 GB reais.

### 10.2 Lições aprendidas

1. **Regra "3 workers no root" precisa de verificação a cada minuto** com substituição ativa, não só alerta.

2. **Pesquisadores precisam de lembrete explícito no início de cada task:** "Você está escrevendo no root? Pare e mova para scratch."

3. **O guardião de modelo (guardiao_modelos) tem 73 verificações** e funcionou bem para manter cotas.

4. **A ronda de integridade precisa de ajuste de frequência** — 10 falhas em 6h indicam que o modelo entrou em loop degenerado algumas vezes.

5. **Disco C: tem 254 GB totais, 11,9 GB livres agora.** O auditor exagerou em 2 ordens de grandeza.

6. **Se querem trabalho noturno contínuo, precisamos reorganizar** para Few-Big-Tasks em vez de Many-Small-Tasks (pesquisadores trabalhando minutos fragmentados).

7. **Verificar tudo que está marcado "FEITO" precisa de prova real** (`result.success`, teste verde, MD5 batendo). Não admitir afirmação de subagente sem verificação.

8. **As 5 tarefas bloqueadas precisam de decisão** do Alex ou do ceo_mentor. Não fiquem indefinidas.

---

## 11. PROXIMOS PASSOS IMEDIATOS (após estehandoff)

1. **Estehandoff está salvo** em `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\mentor-handoff\HANDOFF_CORUJAO_DIARIO_E_REVISAO_COMPLETA.md`.

2. **A partir de agora, toda sessão nova sobre ZARA deve ler este arquivo primeiro.**

3. **Se precisar de corujão noturno:** Mande "modo corujão ativo" e eu executo o checklist e entregarei o relatório MD + CSV pela manhã.

4. **Se precisar de ações diurnas:** Mande "modo diurno ativo" e eu sigo o checklist diário.

5. **Se precisar de revisão completa da raiz:** Mande "revisão raiz iniciada" e eu designo os bots e começo a leitura.

6. **Se encontrar algum dado desatualizado nestehandoff:** Atualizar imediatamente e reportar ao Alex.

7. **Nunca esquecer as regras que nunca se quebram** (seção 2).

8. **Sempre verificar kanban** antes de assumir que continua assim (linha 102 do CLAUDE_CEO_BRIEFING_LIVE.md).

9. **Nunca declarar sucesso sem prova real.**

10. **Falar antes de agir** se fora de escopo fechado.

---