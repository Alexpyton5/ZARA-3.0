# ZARA 3.0 — Contexto Mestre Canônico

**Data da consolidação:** 2026-09-05 20:00–20:10 (UTC−03)  
**Repositório:** `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
**Branch observada:** `backup/estado-20260820-1143`  
**HEAD observado:** `4f415e6a4f4b687b043aa4b8d18962b7f15653f7`  
**Status desta consolidação:** documento canônico criado; nenhum código de runtime alterado.

> Este arquivo é a fonte única de contexto operacional da ZARA. Relatórios antigos foram preservados em `_quarentena/docs-legacy/2026-09-05/` para auditoria histórica, mas não devem ser usados como descrição atual sem reconciliação com o código e os artefatos de teste mais recentes.

## Atualização de organização — 2026-09-17

Para qualquer nova IA, o ponto de entrada obrigatório agora é
[`ZARA_AGENT_START_HERE.md`](./ZARA_AGENT_START_HERE.md). Ele resume arquitetura,
fontes de verdade, regras de edição, validação, capacidades e limitações.

O ponteiro operacional atual em `ZARA_ACTIVE_BUILD.json` prevalece sobre os
registros históricos abaixo. Ele aponta para
`frontend/release-candidate-fix-9router-v2-20260917-0020`.

Artefatos, rascunhos, scripts one-shot e relatórios duplicados foram movidos de
forma reversível para `_quarentena/organizacao-2026-09-17/`; o inventário está em
`_quarentena/organizacao-2026-09-17/MOVIMENTACOES.txt`. Nenhum código-fonte ativo,
memória, banco ou build apontado pelo ponteiro foi apagado.

## 0. Atualização 2026-09-06 — ZARA CURRENT BUILD ativada (transferência Astra → Claude)

**HEAD atual:** `7e3624c44cdbce5a4f1114229884cc7deb41d346` (branch inalterada, dirty=true).
**Build ativo:** `zara-current-20260906-055925`, `frontend\ZARA CURRENT BUILD\win-unpacked\ZARA 3.0.exe`.
Identidade em `ZARA_ACTIVE_BUILD.json` (STATUS `active-validated`), validação real em
`artifacts/visual-qa/packaged-validation.json`, ledger de verificação em `GATES.md`.

Nesta sessão a Home foi reconstruída/consolidada (`zara-home.css`, ~2.580 linhas de overrides
eliminadas), o Core recebeu logo vetorial novo, o card "Ferramentas" foi substituído por
**LabHomeCard** (mostra propostas/tarefas reais persistidas do ZARA Lab, nunca fabricadas) e o
controle de voz central foi reduzido para não invadir a faixa Sistema. `HomeDrawer.tsx` liga a
sidebar/Dock a paineis reais (Conversas, Projetos, Arquivos, Aplicativos, Automações, Memórias,
Lab, Sistema, Configurações), com Escape e restauração de foco confirmados neste build.

Isso corrige/atualiza as seguintes linhas da tabela da Seção 4, que estavam desatualizadas:
- "Para você/Comunicações — placeholder" → o card "Para você" e "Comunicações" seguem mostrando
  `—` quando não há dado real (correto, não é regressão), mas a navegação por trás deles
  (`Conversas`) agora abre histórico real do backend.
- "ZARA Lab" (não existia como linha própria): real, mas **não** é multiagente completo — é
  leitura+fila (`lab.send` com ACK `QUEUED`, nunca "concluído") sobre o backend existente.

Validado nesta sessão via Electron empacotado real (CDP/Playwright contra o processo
empacotado, não o dev server): preload (`window.zaraIPC`) presente com o canal completo,
`system.metrics()` retornando CPU/RAM/disco reais da máquina, Home carregando com saudação e
dados reais, navegação "Conversas" abrindo histórico real (inclusive uma resposta honesta de
falha, "Não consegui confirmar" — não um sucesso fabricado), sem erros de console, testado em
1671×941 / 1366×768 / 1280×720 sem clipping. Voz **não** foi testada fisicamente nesta sessão
(NOT_LIVE_VERIFIED — mic/STT/TTS/latência continuam sem prova física).

A instalação antiga (NSIS per-user) em `%LOCALAPPDATA%\Programs\zara-frontend` foi **desinstalada**
a pedido do Alex ("não quero cópia antiga no sistema... um só build"), não apenas deixada
desatualizada — era instalação por usuário, sem UAC, então o uninstaller registrado rodou normal.
Os atalhos reais (Desktop, Menu Iniciar, `ABRIR-A-ZARA.bat`, `ZARA_INICIAR.bat`) apontam para
`tools/launch_current.ps1`, que resolve `ZARA_ACTIVE_BUILD.json` e confere hashes antes de abrir —
esse é hoje o único caminho de entrada da ZARA no sistema.

## 0.1 Atualização 2026-09-06 — ZARA LAB REAL V1 (runtime multiagente real)

Existe agora um runtime multiagente real em `core/lab_v1/`, separado e sem tocar no
`core/lab_coordinator.py` legado (que continua funcionando e dono do `lab/zara_lab.db`).
V1 é dono de `lab/zara_lab_v1.db`.

**A invariante do desenho:** PROVIDER ≠ MODEL ≠ AGENT ≠ ROLE ≠ TEAM ≠ SESSION. Um
handoff só re-vincula o *cargo* a outro agente; time, missão, mensagens, tarefas e
decisões não são recriados. É isso que faz o retorno do Astra ser uma troca de binding,
não uma reconstrução.

**Provider real:** `claude_cli`, o Claude Code CLI oficial em modo não-interativo
(`-p --output-format json --model … --restricted`). `--restricted` é obrigatório e
remove Bash/PowerShell/execução de código: agentes do Lab conversam e raciocinam, mas
não controlam o PC — o executor continua sendo o ToolRouter existente da ZARA. Os
agentes rodam com cwd num diretório neutro (`data/lab/agent-workspace`), senão o CLI
carrega o CLAUDE.md do projeto e o custo por chamada sobe ~4x.

**Matriz de provedores (honesta, sondada de verdade):** `claude_cli` AVAILABLE;
`codex_cli` OFFLINE (CLI não instalado — é por aqui que Astra entra no futuro, sem
mudar o domínio); `anthropic_api` AUTH_REQUIRED (sem chave configurada).

**Time ZARA Core:** Artemis (Opus, CEO, designação ACTING enquanto Astra está sem cota)
e Vulcan (Sonnet, BUILDER, fallback do CEO).

**Provado por execução real** (`tools/lab_v1_acceptance.py`, evidência em
`artifacts/lab-v1/acceptance.json`, 14/15 portões em `GATES.md`): mensagem do Alex
persistida; CEO real (`claude-opus-5`, custo real, `cost_basis=KNOWN`) delegando tarefa
a um agente distinto; Builder real (`claude-sonnet-5`) executando a própria chamada;
resultado voltando à mesma sessão; 21 eventos observados; zero campos de
chain-of-thought armazenados; promoção idempotente de um fato para a memória existente
(`UserMemoryCore`, com `ref` rastreável); restart em processo novo recuperando tudo;
e failover — CEO marcado indisponível, Handoff gravado, cargo re-vinculado ao fallback,
**mesma sessão**, zero mensagens/tarefas perdidas.

**IPC/UI:** sete canais `lab-v1-*` ligados nos quatro pontos (main/preload/global.d.ts/
consumidor). O painel ZARA Lab mostra equipe, provedores com estado textual, objetivo,
conversa, tarefas, handoffs e custo (`—` quando desconhecido, nunca "grátis").
`lab-v1-submit` responde `QUEUED` — recebido e persistido, nunca "concluído".

**O que o Lab V1 NÃO é:** não há scheduler novo, Intelligent Router adaptativo, executor
autônomo, learned routing, council completo nem formação automática de equipes. Delegação
é limitada por `max_delegations` e uma única rodada de consolidação.

**Isolamento de teste (obrigatório).** O acceptance runner NUNCA toca a base de
produção. Ele cria banco e memória próprios sob `ZARA3_LAB_SANDBOX`; o failover, os
handoffs e o restart acontecem só nesse mundo de teste. O relatório grava a impressão
digital da produção antes e depois (time, bindings, designação, sessões, tarefas,
mensagens e SHA-256 do arquivo) e o portão G14 falha se qualquer dimensão mudar. Não
depende de "o teste normalmente chega ao fim": não existe caminho do runner para a
produção, então uma exceção ou um Ctrl-C também não contamina.

**Self-delegation é recusada.** Se o delegador e o alvo resolverem para o mesmo
AgentInstance (uma pessoa ocupando dois cargos é legítimo), o runtime NÃO faz uma
segunda chamada paga fingindo delegação. Retorna `delegation_refusal="SELF_DELEGATION"`
com `delegation_candidate_agent_ids` para o chamador escolher outro membro, registra o
CapabilityGap e avisa o Alex por mensagem. Isso importa porque uma segunda chamada ao
mesmo agente produziria um Run com custo real e modelo real — exatamente a forma que os
portões multiagente procuram — e passaria por prova de dois agentes sem ser.

**Não promovido a build.** `zara-current-20260906-055925` continua sendo a CURRENT BUILD
e é o que o atalho do Alex abre. O Lab V1 foi validado em Electron real com preload e IPC
reais, mas **não** empacotado: faltou espaço em disco (2,86 GB livres). Ver G13 em
`GATES.md`.

## 1. Veredito executivo

A ZARA 3.0 é um aplicativo desktop Windows baseado em **Electron + React/TypeScript** no frontend e um **sidecar Python** no backend. O processo Electron cria a janela, expõe uma ponte IPC mínima via preload, inicia o sidecar e encaminha mensagens, voz, ações, confirmação e estado. O Python mantém o registro de ações, intenção determinística, roteamento de ferramentas, gates de risco/permissão, persistência de memória e integrações de voz/modelos.

O caminho confiável hoje é **comando simples → resolução determinística → ActionRegistry/ToolRouter → gate de segurança → execução → resultado/auditoria/verificação quando configurada**. Existe um domínio de Planner com modelos, validação topológica e execução via ToolRouter, mas ele é uma infraestrutura preparada: o `RulePlanner` aceita apenas `explicit_steps`; não há `LLMPlanner`/`HybridPlanner` e o Planner não está conectado automaticamente ao caminho geral de linguagem natural.

A UI eleita é **Titanium Emerald**. A Home atual é React real (`ZaraHome`) e não mais um iframe; texto, voz, estado do Core, métricas do sistema e bateria têm conexões reais. Wi‑Fi, nuvem, segurança, energia, contagens de comunicação, projeto ativo e identidade real do usuário continuam placeholders explícitos ou canais ainda não ligados.

## 2. Topologia operacional

```text
Electron main (frontend/src/main.ts)
  ├─ BrowserWindow frameless + lifecycle
  ├─ spawn do sidecar Python / zara-backend
  ├─ ipcMain: janela, texto, voz, sistema, histórico, config e eventos
  └─ encaminhamento para o renderer via preload

Preload (frontend/src/preload.ts)
  └─ contextIsolation=true, nodeIntegration=false, API window.zaraIPC mínima

React renderer (frontend/src/renderer/)
  ├─ App.tsx → ZaraHome (UI eleita)
  ├─ Home Titanium Emerald: Core, texto, voz, cards e métricas
  └─ canais legados Lab/Memory/HUD ainda coexistem no código

Python sidecar (main.py → core/ipc_handlers.py)
  ├─ intent/PC voice deterministic path
  ├─ ActionRegistry + ToolRegistry + ToolRouter
  ├─ gates de capability/risco/permissão/confirmation/audit
  ├─ planner opcional (não automático)
  ├─ modelos: ModelRouter para texto; Gemini Live para voz quando configurado
  ├─ memória estruturada, episódica, histórico SQLite e bridge Obsidian
  └─ TTS/STT com cascata e interrupção
```

### Entry points e build

| Área | Arquivo/caminho | Papel real |
|---|---|---|
| Python | `main.py` | inicia `core.ipc_handlers.main()` |
| IPC Python | `core/ipc_handlers.py` | loop de mensagens, handlers de texto/voz/estado |
| Electron | `frontend/src/main.ts` | janela, sidecar, IPC e lifecycle |
| Segurança IPC | `frontend/src/preload.ts` | ponte exposta ao renderer |
| React | `frontend/src/renderer/App.tsx` | raiz visual; deve renderizar `ZaraHome` |
| Home | `frontend/src/renderer/components/zara-home/` | UI Titanium Emerald conectada |
| Build Python | `build_exe.py` | PyInstaller e, conforme flags, pipeline completo |
| Build frontend | `frontend/package.json` | Vite/Electron/package scripts |
| Artefatos | `dist-sidecar/`, `frontend/dist-frontend/`, `frontend/release/` | outputs; não são source of truth |

## 3. Fluxos reais

### 3.1 Texto

`TextCommandInput` usa `window.zaraIPC.message.send({ message, engine, history: [] })`. A Home não mantém uma thread própria; o backend recebe a mensagem e segue o fluxo existente de intenção/ação ou chamada de modelo. O `ZaraOrchestrator` comprime histórico, aplica modo manual ou políticas `auto_smart`, `auto_economy` e `auto_fast`, escolhe modelo e faz fallback entre modelos configurados. Resposta vazia ou prefixada por erro é tratada como falha, não sucesso.

### 3.2 Ação e ferramenta

O `ActionRegistry` importa módulos de `core/actions/` e registra funções com decorator. O `ToolRegistry` adapta especificações do ActionRegistry para `ToolDefinition`, incluindo executor delegado e perfil de risco. O `ToolRouter` segue a sequência:

`VALIDATE → LOOKUP → SCHEMA → PERMISSION → EXECUTE → NORMALIZE → VERIFY → AUDIT → RESULT`.

O fallback para o ActionRegistry existe quando a ferramenta não está no ToolRegistry. O resultado estruturado carrega sucesso, erro, duração, categoria, verificação e dados. A existência do caminho não significa que todos os módulos avançados estão expostos ou que toda ação possui verifier.

### 3.3 Planner

`core/planner/models.py`, `planner.py`, `validation.py` e `execution.py` formam um subsistema válido e isolado. `validate_plan` detecta plano vazio, IDs duplicados, ferramentas desconhecidas/bloqueadas, argumentos inválidos, dependências inválidas, auto-dependência e ciclos. `execute_plan` só aceita planos validados, executa em ordem topológica, bloqueia dependentes de falhas e usa o ToolRouter sem ganhar privilégios novos.

O limite atual é deliberado: `RulePlanner.plan()` recusa ausência de `explicit_steps`; o objetivo em linguagem natural não é decomposto automaticamente. Portanto, não declarar que a ZARA já possui planejamento autônomo multi-etapas integrado.

### 3.4 Voz

A Home usa os canais existentes `voice.start`, `voice.stop`, `voice.sendMicChunk` e `message.interrupt`. Para modo não local, o renderer inicia captura AEC e envia chunks; Vosk pode manter o microfone no Python. O `VoiceDock` assina áudio de saída, toca PCM via `tocarKore`, interrompe Kore e chama o interrupt IPC durante fala.

No TTS, a implementação observada é: **Kore/Gemini Live acima do gerenciador quando selecionado; dentro do TTSManager: Edge neural → Kokoro local → Gemini HTTP**, com streaming Edge quando `miniaudio + sounddevice + numpy` estão disponíveis e caminho de arquivo/MCI como fallback do Edge. `TTSManager.interrupt()` para Edge via MCI e `sounddevice`, cobrindo o problema de barge-in documentado. A documentação histórica que disser SAPI como fallback canônico está desatualizada frente ao código atual.

### 3.5 Memória

`memory/memory_manager.py` persiste `long_term.json` no diretório de usuário obtido por `core.paths`, com backup `long_term.backup.json`, escrita atômica, limite de tamanho, truncamento e filtragem de chaves/padrões sensíveis. Há categorias estruturadas (identity, preferences, projects, relationships, wishes, notes), sessões limitadas e integração com memória episódica. Exportação redige valores sensíveis; limpeza tenta remover também episódios.

`core/conversation_history.py` mantém histórico SQLite no diretório de dados do usuário. `core/obsidian_bridge.py` cria vault local em `safe_user_path("vault")`, com `memories/`, `knowledge/`, `projects/` e `.zara_index.json`, além de `galaxy()`, `add_memory()` e `link_memories()`. Isso prova uma bridge local mínima; não prova que o grafo Obsidian seja a fonte de contexto do Planner ou esteja integrado a cada decisão.

## 4. Capacidades: estado factual

| Domínio | Estado | Evidência / limite |
|---|---|---|
| Controle de janelas | real | main/preload e handlers Electron |
| Texto | real | `TextCommandInput` → `message.send` |
| Voz start/stop | real condicionado | canais existentes; depende do backend/dispositivo/configuração |
| STT local | disponível | caminho Vosk no backend quando selecionado |
| Voz Gemini Live | disponível condicionado | requer chave/rede e caminho configurado |
| TTS Edge | disponível condicionado | requer pacote/rede; streaming ou MCI |
| TTS Kokoro | disponível condicionado | local, depende de instalação/modelo |
| Interrupção/barge-in | implementado | Kore + Edge + sounddevice; exige teste Windows live |
| Ações Windows | real | módulos em `core/actions/`, gates aplicados |
| Browser/Selenium | real condicionado | integração existente; precisa browser/driver/configuração |
| Arquivos | real com gate | validação de path e confirmação para operações de risco |
| Terminal | real com gate | executor existente; segurança depende do allowlist/política vigente |
| Model routing texto | real | `ModelRouter` + fallback conforme configuração |
| Planner multi-etapas | parcial | domínio e executor existem; geração automática não existe |
| Verificação de resultado | parcial | ToolRouter suporta verifier; cobertura varia por ferramenta |
| Memória estruturada | real | JSON atômico + backup + redaction |
| Memória episódica | existente | chamada pela camada de memória; validar cobertura por teste |
| Conversa | real | SQLite |
| Obsidian/Galaxy | bridge mínima real | índice local e operações básicas; não é contexto automático global |
| Plugins | carregamento presente | `core/actions/__init__.py` carrega `plugins/*.py`; erro de plugin não derruba os demais |
| Wi‑Fi na Home | não conectado | action existe, Home não consulta o canal |
| Energia na Home | não conectado | actions existem, Home não liga list/set |
| Segurança na Home | placeholder | nenhuma action correspondente ligada à tela |
| Para você/Comunicações | placeholder | sem fonte real de contagens |
| Projeto ativo/progresso | placeholder | sem conceito backend consumido pela Home |
| Perfil real | fallback | nome fixo `Alex Silva`, iniciais; autenticação está fora de escopo |

## 5. UI ativa e contratos visuais

A Home `ZaraHome.tsx` compõe sidebar, status row, header, comando, cards, Core, dock de voz e faixa System. O CSS `zara-home.css` usa namespace `zh-`, paleta Titanium Emerald, aurora de fundo, vidro translúcido, layout central de três colunas e breakpoints/responsividade existentes. A Home não depende do CSS legado de Lab/Memory Galaxy.

Conexões comprovadas na Home:

- texto: `window.zaraIPC.message.send`;
- Core: `window.zaraIPC.on.stateChange`, mapeado para `idle`, `listening`, `understanding`, `thinking`, `planning`, `executing`, `awaiting_authorization`, `speaking`, `success`, `error`, `offline`;
- voz: start/stop/send chunks/interrupt e áudio PCM;
- CPU/RAM/disco: `window.zaraIPC.system.metrics()`;
- bateria/carregamento: `navigator.getBattery()`;
- relógio: hook local.

Os ícones de nuvem, segurança e conectividade ficam explicitamente marcados como não conectados; isso é comportamento correto, não bug visual. O frontend preview fora do Electron deve mostrar offline/desabilitado em vez de simular sucesso.

## 6. Segurança e invariantes

1. Não executar ação externa sem passar pelo caminho de capability/risco/permissão/confirmation aplicável.
2. Não tratar texto de UI como confirmação implícita.
3. Não expor segredos no renderer, histórico, memória, export ou auditoria; redigir chaves e tokens.
4. Não chamar subprocess, hardware ou rede a partir de modelos puros do Planner.
5. Não permitir que Planner bypass ToolRouter.
6. Manter `contextIsolation=true` e `nodeIntegration=false`.
7. Não declarar disponibilidade com base apenas em presença visual; usar estado real ou marcar `NOT_CONNECTED_YET`.
8. Mudanças de build/runtime devem preservar a separação source → build → runtime e atualizar identidade do build.
9. Testes que tocam Windows, microfone, navegador, Electron empacotado ou hardware devem rodar no Windows live conforme `TEST_RUN_POLICY.md`; Linux/mount serve para inspeção e testes puros.
10. Não apagar histórico sem backup/decisão explícita; arquivamento reversível é preferível à remoção.

## 7. Estado de testes e evidência

A baseline versionada e os relatórios mais recentes em `.zara-tests/` são a evidência preferencial, não os números de relatórios antigos. O estado registrado indica uma suíte Python ampla, smoke tests históricos com falhas conhecidas e frontend com typecheck/build verificados em uma sessão anterior. O relatório de integração da Home confirma `npm run typecheck` limpo, `npm run build` bem-sucedido e preview Vite sem erros de console, mas declara que o Electron empacotado ainda não foi provado nessa sessão.

Antes de qualquer afirmação de release, executar no Windows live, na ordem segura:

1. `npm run typecheck` em `frontend/`;
2. `npm run build` em `frontend/`;
3. pytest conforme política vigente, primeiro testes puros e depois os marcados Windows/live;
4. `npm run electron:dev` ou candidato empacotado, confirmando preload, spawn do sidecar e canais IPC;
5. smoke manual de texto, start/stop voz, interrupt durante fala, estado do Core, memória e uma ação com confirmação;
6. registrar commit, branch, timestamp, artefatos e qualquer falha em relatório novo.

Não usar números históricos (por exemplo, contagens de 2026-09-02) como estado atual sem nova execução.

## 8. Organização canônica do repositório

### Deve permanecer como fonte operacional

- `README.md` — ponte curta para este documento;
- `CLAUDE.md` e `.claude/rules/` — governança/instruções, não substituir por relatório;
- `ZARA_MASTER_CONTEXT.md` — este contexto único;
- `main.py`, `build_exe.py`, `pyproject.toml`, `requirements.txt` até decisão explícita de remoção;
- `core/`, `frontend/src/`, `tests/`, `.zara-tests/`, `.zara-dev/`, `config/` conforme regras de segredo;
- `frontend/package.json` e `package-lock.json` como cadeia Node observada; lockfiles alternativos só podem ser removidos após validação e decisão.

### Deve ser tratado como histórico, não como contexto ativo

Os relatórios de baseline, mapas, boards noturnos, planos antigos, handoffs, classificações e investigações que estavam soltos na raiz foram movidos para `_quarentena/docs-legacy/2026-09-05/`. Eles permanecem versionados e pesquisáveis, mas não competem com este arquivo.

### Não confundir com source

`frontend/dist-*`, `frontend/release/`, `dist-sidecar/`, `build-sidecar/`, caches, `__pycache__` e candidatos antigos são outputs/artefatos. Só um build com identidade, commit e testes correspondentes deve ser chamado de candidato operacional.

## 9. Backlog priorizado após a consolidação

### P0 — prova de runtime

- **Feito em 2026-09-05 (Missão Jarvis, sessão Chief of Staff):** Electron empacotado
  (`ZARA_ACTIVE_BUILD` → `AppData\Local\Programs\zara-frontend\ZARA 3.0.exe`, atalho do
  Windows atualizado para o mesmo binário) confirmado vivo com o golden path de texto:
  "Oi Zara" → resposta real; "Abra o Chrome" → abre e verifica; "Quanto de RAM estou
  usando?" → métrica real na resposta; "Minimize o Chrome" → minimiza e verifica.
  Evidência: `core/conversation_history.py` (histórico real) + `IsIconic` via Win32 no
  Chrome depois do comando. Dois bugs reais corrigidos no caminho:
  - `core/ipc_handlers.py::handle_send_message` tratava "Oi Zara" sozinho (só
    saudação+nome, sem comando) como texto vazio e recusava com "No text provided".
  - `window_minimize`/`window_maximize`/`window_restore` só suportavam a janela
    ativa/contextual; "Minimize o Chrome" (janela por NOME, não em foco) caía em
    "ainda não sei fazer". Agora reaproveitam a mesma resolução por nome de
    `window_focus_named` (`core/actions/os_ops.py`, `core/pc_voice_intent.py`).
  "Abra a Calculadora" continua fora de propósito — Alex removeu a calculadora da
  lista de apps em 2026-08-27 (`ZARA-APPS-REAIS-2026-08-27`, `core/actions/os_ops.py`);
  não reintroduzir sem ele pedir de novo.
- Reconciliar e atualizar baseline de testes com um relatório datado.
- Exercitar interrupção/barge-in real e registrar latência/resultado.
- Verificar que nenhum artefato antigo está sendo usado pelo script de build ou atalho ativo.

### P1 — reduzir risco estrutural

- Integrar ToolRegistry/ToolRouter ao ponto de entrada escolhido sem duplicar gates.
- Definir cobertura e contrato dos verifiers; adicionar testes para ações de alto impacto.
- Escolher política explícita para npm versus pnpm e pyproject versus requirements; não apagar por suposição.
- Consolidar logs estruturados sem vazar parâmetros sensíveis.
- Auditar módulos experimentais (`autonomy_engine`, `proactive_monitor`, `macro_engine`, MCP e visão) por callers reais antes de conectar ou arquivar.

### P2 — capacidades de produto

- Criar decisão explícita para quando o Planner entra; manter fast path determinístico para comandos simples.
- Implementar output estruturado confiável para `LLMPlanner`/`HybridPlanner` com validação e confirmação.
- Integrar recuperação de memória relevante ao contexto de planejamento, com limites e redaction.
- Ligar Wi‑Fi/energia apenas com contratos reais e estados de indisponibilidade.
- Definir fonte real para projeto ativo, comunicações e identidade do usuário antes de remover placeholders.

## 10. Regra de atualização deste documento

Toda mudança de arquitetura, integração, build, segurança ou capacidade deve atualizar esta página ou criar um relatório datado apontado por ela. Se um relatório histórico divergir do código, vence o código verificado mais recente, seguido pelo artefato de teste datado; a divergência deve ser registrada aqui. Não criar outro “estado atual” paralelo na raiz.
