# ZARA 3.0 — Contexto Mestre Canônico

**Data da consolidação:** 2026-09-05 20:00–20:10 (UTC−03)  
**Repositório:** `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
**Branch observada:** `backup/estado-20260820-1143`  
**HEAD observado:** `4f415e6a4f4b687b043aa4b8d18962b7f15653f7`  
**Status desta consolidação:** documento canônico criado; nenhum código de runtime alterado.

> Este arquivo é a fonte única de contexto operacional da ZARA. Relatórios antigos foram preservados em `_quarentena/docs-legacy/2026-09-05/` para auditoria histórica, mas não devem ser usados como descrição atual sem reconciliação com o código e os artefatos de teste mais recentes.

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
