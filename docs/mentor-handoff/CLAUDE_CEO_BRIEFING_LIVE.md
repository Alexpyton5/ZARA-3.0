## 0. COLE ISTO NO INÍCIO DE UMA SESSÃO NOVA (texto pronto pro Alex)

Alex, copie e cole exatamente isto na primeira mensagem de uma conversa nova
comigo, sempre que quiser retomar o trabalho da ZARA sem reexplicar nada:

```
Você é o CEO/arquiteto operacional do projeto ZARA. Leia agora o arquivo
C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\docs\mentor-handoff\CLAUDE_CEO_BRIEFING_LIVE.md
inteiro antes de responder qualquer coisa. Ele tem o alvo do projeto, as
regras que nunca quebram, o estado atual, decisões já tomadas e lições
aprendidas. Depois de ler, me diga em 3 linhas onde paramos e o que sugere
como próximo passo.
```

Isso funciona mesmo se minha memória embutida falhar ou for limpa — o
arquivo é a fonte de verdade e sobrevive a qualquer reset de sessão.

---



**Este arquivo é atualizado por mim (Claude/Hermes, perfil default) a cada
sessão relevante. Leia isto no início de QUALQUER conversa nova antes de
perguntar ao Alex o que estamos fazendo — a resposta provavelmente já está
aqui.**

Última atualização: 23/08/2026.

---

## 1. Quem eu sou aqui

Sou o Hermes rodando no perfil **default**, conectado ao Telegram (DM direta
com o Alex). Alex me colocou no papel de **CEO operacional / arquiteto** do
projeto ZARA — o mesmo papel que o `AGENTS.md` do projeto descreve como
"Claude" (arquiteto, responde ao Alex, acima do Codex/executor).

Não confundir com os bots do time Hermes (`@ceo_mentor`, `@executor_dev`
etc. — esses são outros perfis/processos, Tier 1 Opus / Tier 2 Sonnet /
Tier 3 Haiku). Eu sou a entidade que fala direto com o Alex no Telegram e
que decide/coordena de cima.

## 2. O alvo final (nunca perder de vista)

> Alex, 23/08: "alvo final é ver a zara sendo a jarvis da vida real, no dia
> em que ela fizer tudo o que a jarvis faz chegamos lá."

Toda priorização, toda decisão técnica, mede-se contra isso. Não é feature
por feature — é a experiência completa do filme.

## 3. Regras que NUNCA se quebram (do projeto, herdadas por mim)

- **Nada de falso sucesso.** "Pronto" só com prova real (teste verde, exit
  code, leitura pós-escrita, MD5 batendo). Já foi violado 3x no histórico do
  projeto e custou confiança. Alex reclama forte quando isso acontece.
- **Um escritor por área.** Nunca dois agentes/bots mexendo no mesmo arquivo.
- **Custo mensal de operação = R$0** é requisito, não meta. Cada feature
  nova deve rodar de graça (local ou camada gratuita) por padrão.
- **Alex não programa.** Nunca jogar código nele. Ele testa, relata sintoma,
  decide produto. Fala português, quer respostas curtas (está sempre no
  celular).
- **Fale antes de agir fora de escopo fechado.** Escopo fechado (arquivos
  nomeados + comportamento + prova exigida) = executa direto.

## 4. Estrutura do time de bots (PRIMEIRA_ORDEM_DO_CEO, 21/08/2026)

Raiz única: `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002` (viva, git ativo).
`D:\ZARA 3.0 CLEAN 002` = snapshot morto, nunca usar.

- **Tier 1 (Opus 5):** @ceo_mentor (orquestra/delega/cobra prova),
  @revisor_supervisor (portão final PASS/FAIL)
- **Tier 2 (Sonnet 5):** @executor_dev, @arquiteto_mcp, @designer_ui_ux,
  @seguranca_redteam, @pesquisador_reverso
- **Tier 3 (Haiku 4.5):** @qa_tester, @integrador_build, @pesquisador_ux,
  @escriba_backlog

Cada bot tem fallback automático pra modelos grátis (NVIDIA Nemotron,
DeepSeek V4 Flash) quando cota acaba.

## 5. Estado do projeto na última leitura (22-23/08/2026)

Fonte: `docs/FASES-CORUJAO-STATUS.md`, `docs/ESTADO-DOS-COMANDOS.md`, kanban.

- **Fases 1-2 (fundação, cérebro, roteamento): PRONTO.** 1293 testes verdes,
  telemetria de roteador, capability registry (só 23 ações essenciais no
  boot, resto sob demanda).
- **Fase 3 (percepção/memória humana): quase pronta**, faltava revisão
  formal (`docs/REVISAO-FASE-1-2.md`) e validar interface premium na build.
- **Fase 4 (proatividade/Jarvis): EM ANDAMENTO.** Duas tarefas rodando no
  kanban nesta data: `t_c5f2d114` (engenheiro — endurecer pipeline de voz:
  reconexão, barge-in, falha de microfone) e `t_012eee3c` (executor_dev —
  ligar aprovação pelo celular ao Telegram e ao executor real). Essa segunda
  é a peça que falta pro Alex aprovar ações remotamente de verdade.
- **Fase 5 (distribuível): parcial.** Comando único de build+instalador
  ainda não validado do zero.
- **Comandos de voz:** 60 mapeados, 54 com teste provado, 6 "só existem no
  papel" (browser_read_page, window_move, window_resize_larger,
  window_close, os_clipboard_read, aprendizado_resumo).
- **Risco registrado:** hardware do Alex = 16GB RAM / 4GB VRAM, limita
  modelos locais grandes.

**Isso é uma FOTO de 22-23/08 — sempre confira o kanban ao vivo
(`hermes kanban list`) antes de assumir que continua assim.**

## 6. Decisões tomadas nesta sessão (23/08/2026)

- Modelo do Hermes default: testado haiku → qwen3:4b (quebrou vision
  auxiliar, confirmando troca real) → **fixado em opus** por pedido do Alex.
- Cota Anthropic verificada: 2 de 3 credenciais OAuth exauridas no momento
  (`dashboard_pkce`, `hermes_pkce`), `claude_code` ativa. Fallback chain do
  perfil default: sonnet-5 → nemotron-120b (NIM grátis) → nemotron-30b (NIM)
  → qwen3:8b local.
- **Provider de memória externa `holographic` ativado** (`hermes memory
  setup holographic`) com `auto_extract: true`. SQLite local, zero custo,
  FTS5 + trust scoring + HRR. Resolve a perda de contexto entre sessões —
  ferramenta `fact_store`/`fact_feedback` fica disponível em sessões novas
  (não estava carregada nesta, que já rodava antes da ativação).
- **NÃO AINDA VERIFICADO:** se o `fact_store` está de fato gravando e
  recuperando fatos entre sessões. Testar na próxima conversa nova: pedir
  pra eu buscar algo, ou gravar algo e confirmar persistência depois.

## 7. O que o Alex pediu que eu faça como CEO da ZARA

1. Assumir posse do conhecimento do projeto (feito — li os MDs principais:
   IDENTITY, IDEIAS-DO-ALEX, PRIMEIRA_ORDEM_DO_CEO, ROADMAP,
   SPEC_ZARA_VISAO_ALEX, OPERATIONS, QUADRO-ZARA, CADERNO-DE-TAREFAS,
   O-QUE-MUDOU-22-08, FRONTEIRA/core_boundary, MENTOR_BRAIN_TRANSFER — esse
   último truncado em 1997 linhas, só li as primeiras 500, **vale reler o
   resto se precisar de mais profundidade técnica**).
2. Regular o time de 16 agentes no kanban: delegar, monitorar, decidir
   motor de IA por tarefa (Opus/Sonnet/NIM/Qwen local), autorreparar bot
   travado, reportar só via Telegram — sem exigir que Alex fique no PC.
3. Nunca inventar sucesso, nunca alucinar, nunca deixar ele na mão longe do
   PC — isso é regra da casa e do projeto, reforçada explicitamente.

## 8. Próximos passos sugeridos (ainda não executados, pendente confirmação)

- Verificar as 2 tarefas rodando no kanban (`t_c5f2d114`, `t_012eee3c`) —
  vivas ou travadas?
- Configurar daemon do kanban (`hermes kanban daemon`/`watch`) rodando
  contínuo em background, não dependente desta conversa.
- Cron job de relatório periódico pro Telegram (silencioso quando não há
  nada novo) — ainda não criado.
- Confirmar `fact_store` gravando de verdade numa sessão nova.
- Ajustar fallback chain específico de cada bot do time (ainda não auditado
  bot a bot nesta sessão).

## 9. Handoff do OpenClaw (`HERMES_BOT_HANDOFF.md`) — o que aproveitei e o que corrigi

Alex também tinha um handoff escrito por outro agente (OpenClaw/"Claw") pra
outro bot chamado "Hermes". Li inteiro e cruzei com a realidade do projeto
antes de aceitar qualquer coisa dele.

**Aproveitado (bate com a realidade e com as regras do projeto):**
- Formato de relatório pro Alex: *"Alex, a Zara agora [faz X]. Testei: [Y]."*
  Sem hash, PID, exit code, nome de teste.
- "Done" no kanban ≠ validado — sempre testar antes de reportar.
- Não confundir identidade: eu não sou a ZARA, sou quem coordena o time que
  a constrói.
- Um escritor por área, escalar decisão de produto pro Alex, não adivinhar.

**Corrigido (divergia da realidade ou já foi superado):**
- ❌ "Voz 100% local (faster-whisper/Kokoro/Pipecat)" como estado atual —
  **falso**. Produção usa Gemini Live + voz Kore (confirmado em `AGENTS.md`
  e na tarefa `t_c5f2d114`, que fala em reconexão da sessão Gemini Live).
  Pipeline local foi só exploração no kanban antigo, nunca virou produção.
- ❌ "HUD PyQt6 completo" — não existe nenhum arquivo PyQt6/HUD no projeto.
  Frontend real é Electron + React. Contaminação de referência ao Mark-LI
  (projeto usado só como fonte de engenharia reversa).
- ❌ `GESTAO-DE-MODELOS.md` — arquivo citado não existe nesta pasta.
- ❌ Comandos do kanban errados no handoff (`add/start/done`). Reais:
  `hermes kanban create / claim / complete` (verificar sempre com
  `hermes kanban --help` antes de rodar às cegas).
- ❌ **Regra de ouro nº5 do handoff — "nunca crie cron que só monitora,
  queima cota sem entregar" — CONTRADIZ o que eu tinha proposto ao Alex**
  (daemon/cron de vigilância do kanban). Essa lição é real e mais forte:
  abandonei a ideia de cron de monitoramento. Checagem de status é sob
  demanda, não recorrente.
- ⚠️ "Modelo local/grátis sempre por padrão" está desatualizado — a ordem
  mais recente e válida é a `PRIMEIRA_ORDEM_DO_CEO` (21/08), que define
  Sonnet 5 pago para Tier 2 (engenheiro, executor_dev) por design. Essa
  ordem é posterior ao handoff do OpenClaw e prevalece.

## 10. Incidente de RAM — causa raiz encontrada e resolvida (23/08)

**Sintoma:** 89 MB livres de 16 GB total, com só 2 tarefas do kanban
"rodando" oficialmente.

**Causa raiz real (achada, não presumida):** um `pytest` **órfão**
(PID 13096, `ZARA3\toolchain\python\python.exe -m pytest`) sozinho segurava
**5,7 GB de RAM**. Diagnóstico que provou que era lixo, não trabalho ativo:
rodava há 2h23min mas tinha consumido só 132s de CPU total nesse tempo —
processo parado, não trabalhando. Nasceu no mesmo minuto (20:30) em que a
run #138 de `t_c5f2d114` foi `manual_reclaim`ada por estouro de RAM (log do
próprio kanban: "RAM em 0,67 GB livres com 8 workers simultâneos; o
despachante ignorou o limite de 3"). Quando o kanban matou a run, o
subprocesso `pytest` que ela tinha disparado ficou órfão e nunca foi limpo.

**Como diagnosticar isso rápido numa próxima vez (comandos que funcionam):**
```powershell
# Top processos por RAM (bash + wmic dá lixo UTF-16; usar powershell -File)
Get-Process | Sort-Object WS -Descending | Select-Object -First 30 Name,Id,@{N='RAM_MB';E={[math]::Round($_.WS/1MB,1)}}
# RAM livre total do sistema
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
# Linha de comando completa de um PID suspeito (identifica origem)
Get-CimInstance Win32_Process -Filter "ProcessId=<PID>" | Select-Object CommandLine,CreationDate
# Teste "travado vs trabalhando": CPU baixo + tempo de vida alto = zumbi
$p = Get-Process -Id <PID>; ($p.CPU, ((Get-Date)-$p.StartTime).TotalMinutes)
```
Nota: rodar PowerShell via `terminal()` (bash) quebra se usar `$_`/`${...}`
inline — o bash expande antes de chegar no PowerShell. Escrever o script
num `.ps1` com `write_file` e rodar `powershell -File caminho.ps1` evita
isso.

**Resolvido:** processo zumbi encerrado, RAM voltou a 11,1 GB livres
(confirmado, não presumido).

**Regra adotada:** RAM baixa no kanban não significa "preciso de mais
workers cabendo" — primeiro suspeitar de subprocesso órfão de uma run já
`reclaimed`, antes de mexer no dispatcher ou reduzir paralelismo. Checar
RAM livre antes de `hermes kanban claim`/disparar tarefa nova continua
válido, mas o primeiro diagnóstico é caçar zumbi, não limitar workers.

---

## 11. Roteamento de modelos e retomada do time (23/08/2026)

- Alex alterou manualmente os modelos no Kanban e o chat default para testar a retomada. A direção estava correta, mas `set-model` só vale no próximo dispatch; não troca o runtime de worker já iniciado.
- Prova de runtime deve vir do `state.db` do perfil: `sessions.model` + `sessions.billing_provider`, nunca apenas da tela/configuração.
- Estratégia econômica atualizada por ordem do Alex: operação **Codex-only**. GPT-5.6 Sol para arquitetura crítica, consolidação, integração/build e portão final; Terra para auditoria técnica e correções equilibradas; Luna para inventário, documentação e testes mecânicos. Anthropic e NVIDIA ficam fora enquanto esta ordem estiver ativa.
- Em 23/08 11:26, `arquiteto_mcp` iniciou `t_04c0e6eb` comprovadamente com `gpt-5.6-sol` e `billing_provider=openai-codex`. Os três workers já em execução continuaram no modelo NVIDIA com que haviam nascido; não foram interrompidos.
- O YAML de `profiles/arquiteto_mcp/config.yaml`, corrompido por edição manual anterior, foi restaurado para sintaxe válida e ficou em GPT-5.6-sol/OpenAI Codex. Backup: `config.yaml.bak-20260823-model-fix`.
- Cinco cartões artificiais de teste de modelo foram arquivados para não gastar cota. O portão final `t_00973670` e o build `t_2eadf0a1` ficaram presos ao Codex no próximo dispatch.

## 12. Super varredura raiz autônoma (23/08/2026)

- Sete frentes A-G cobrem core/actions, voz/memória/integrações, frontend/IPC, testes, raiz/docs/scripts, builds/caches/vendors e segurança. Cada frente grava manifesto fora do root em `%LOCALAPPDATA%\hermes\workspace\zara_root_sweep\`.
- Encadeamento: A-G -> consolidação Sol (`t_0c99e779`) -> limpeza segura Terra (`t_46ab3931`) -> portão final Sol (`t_00973670`). Exclusão automática fica limitada a itens comprovadamente regeneráveis; código, configs, memória, chaves, bancos e baseline de release são preservados.
- Limite seguro fixado em quatro workers globais e um por perfil (`kanban.max_in_progress=4`, `max_in_progress_per_profile=1`) por causa dos 16 GB de RAM. O guardião Codex-only mantém no mínimo três e cria Terra/Luna conforme a natureza da auditoria.
- Modelos disponíveis confirmados no catálogo do provider OpenAI Codex: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`. Prova de execução continua sendo `state.db` do perfil.

## 13. Corte de desperdício e estado ao vivo (23/08/2026, 17:29)

- Cota Codex medida diretamente: 94% usada, 6% restante.
- A super varredura A-G e a consolidação terminaram. A limpeza segura removeu 626 caches, liberou 42.847.145 bytes e preservou código, memória, configurações, ambientes e releases.
- Três workers estavam ativos: `executor_dev` restaurando os contratos/testes Telegram (Terra), `pesquisador_ux` auditando voz (Terra) e `qa_tester` auditando proatividade/memória (Luna), todos comprovados em runtime no OpenAI Codex.
- O guardião automático havia criado centenas de auditorias repetitivas (`continuidade 226`) e estava consumindo cota sem ganho proporcional. Foram pausados: mínimo de 3 workers, ronda de integridade, supervisor da varredura, os dois pesquisadores web permanentes e o conselho de pesquisa. Nenhum worker em execução foi morto.
- Build final e portão final continuam parados por dependências técnicas abertas; não declarar release pronta.

*Regra de manutenção deste arquivo: eu atualizo as seções 6, 8, 9 e 10 a
cada sessão relevante. Não deixo esse arquivo dessincronizar do que
realmente aconteceu — se uma decisão mudou, edito aqui, não crio um segundo
arquivo.*
