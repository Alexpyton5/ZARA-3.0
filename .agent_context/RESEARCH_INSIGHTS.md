# Research Insights — ZARA 3.0 Reconstruction

> Coletânea de descobertas dos agentes da fábrica ZARA. Cada seção é append-only; não sobrescreva seções de outros agentes.

---

## SEÇÃO ARQUITETURA ATUAL (task-001 — PESQUISADOR_REVERSO)

> Mapeamento verificado no repo ATIVO `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002` (branch `zara-pearl-install-001`, HEAD 98d5592, 55 alterações). Fatos citando arquivos/linhas, sem opinião.

### 1. Topologia geral
- **Arquitetura sidecar Electron-Python.** Entrada do lado Python: `main.py` (128 linhas) — cria dirs, checa deps, roda `ipc_main()` de `core/ipc_handlers.py` (linha 128: `run_ipc_handler`) via `asyncio.run`. Comunicação com o frontend via IPC **stdin/stdout** UTF-8 (não HTTP). `configure_utf8_stdio()` em `main.py:31-41`.
- Frontend **Electron + React + TS + Vite** em `frontend/` (eletron "Neural Interface", título em `FINAL_GAPS_ROADMAP` P3-B). Build Electron gerado em `frontend/release/`.

### 2. core/ — despachante de voz e texto (o cérebro)
- **`core/ipc_handlers.py`** (211 KB, o maior módulo): despachante central de Voz E Texto. Classe `IPCHandler` (linha 289). Pontos-chave citados:
  - Linha 30/85/1213/1262: `_WAKE_PREFIX_RE` decide wake por TRANSCRIÇÃO (não por gate de áudio local).
  - Linha 1242 `_on_gemini_live_turn`: callback de uma fala do Gemini Live.
  - Linha 1192 `_voice_can_answer_directly`: gate p/ resposta direta.
  - Linha 3266 `handle_voice_start` → 3272 `_handle_voice_start_locked`.
  - Linha 2751: registro `'voice-start': self.handle_voice_start` (rotas de voz).
  - Linha 2219: `[VOICE_TRACE] stage=ACTION_DISPATCH` (observabilidade de latência).
  - Linha 1018 `_looks_like_own_echo` (proteção contra auto-eco — ZARA-VOICE-ECO-001).
  - Linhas 628 `_confirmar_o_que_entendeu`, 657 `_contar_a_latencia`, 70 `_corrigir_nomes_da_casa`.
  - Linha 20: importa `RESPOSTA_NAO_SEI` de `core/pc_voice_intent.py` (recusa honesta com "o que fazer a seguir").
- **`core/gemini_live_voice.py`** (1362 linhas): camada de voz nativa de baixa latência do Gemini Live (voz Kore). Docstring (linhas 1-38) documenta a MUDANÇA de arquitetura: gate Vosk local DESLIGADO por padrão → microfone transmite continuamente ao Gemini, wake decidido por transcrição. Consequências: LISTENING permanente, **barge-in real** (mic chega ao Gemini durante a fala → VAD do servidor enxerga interrupção), e proteção contra auto-audição via `_looks_like_own_echo`. Config (classe `GeminiLiveVoiceConfig`, linha 126): `vad_silencio_ms=300`, `vad_padding_ms=100`, `vad_fim_sensivel=True` (linhas 154-156). Wake local via `_ensure_wake_detector` (319) — Vosk com grammar reduzida `("zara","sara")`; reversível por `"wake_word_mode": "local"` em `api_keys.json` sem rebuild. Gate local desligado p/ preservar barge-in (linha 185).
- **`core/voice_stt.py`** (526 linhas): STT offline Vosk + Porcupine wake word. Classes: `VoiceConfig`(56), `VoskSTT`(81), `PorcupineWakeWord`(142), `AudioInput`(208), `VoicePipeline`(276). `voice_stt.py:1-3`: "Vosk offline speech recognition + Porcupine wake word."
- **`core/voice_tts.py`** (718 linhas): cascata de TTS. Docstring (1-18): ordem Kore(Gemini Live) → Edge Neural(gratuita/offline) → Kokoro ONNX(local) → Gemini HTTP → SAPI. Classes: `KokoroTTS`(97), `EdgeTTS`(297), `GeminiTTS`(521), `TTSManager`(590). "ZARA nunca fica muda nem cai da Kore direto no SAPI."
- **`core/pc_voice_intent.py`** (940 linhas): intenções de voz por regex (controle do PC). **`core/file_voice_intent.py`** (89): intents de arquivos por voz.
- **Gestão/orquestração:** `core/model_router.py` (26 KB, roteamento de providers/models — P3-A, linha 20 do AGENTS), `core/zara_orchestrator.py` (16438, orquestrador), `core/autonomy_engine.py` (26318, Autonomy Core), `core/reminder_engine.py` (15281 lembretes), `core/lab_coordinator.py` (25184, LAB/Mission Control P2-B), `core/aprovacao_remota.py` (aprov. por celular/Telegram), `core/aprendizado.py` (memória de aprendizagem), `core/memory`, `core/mcp/` (base_server, client, launcher, servers, stdio_transport).

### 3. core/actions/ — ações executáveis (o corpo)
Pasta `core/actions/` (não há `actions/` na raiz):
`browser.py`, `code.py`, `files.py`, `media_apps.py`, `os_ops.py`, `ponte_claude.py`, `scheduler.py`, `system.py`, `terminal.py`, `vision.py`, `web.py`, `windows_radios.py`, `aprendizado_acoes.py`. 
- `os_ops.py`: volume/brilho/luz noturna/janelas (controla PC via win32, readback Win32 real, P1-A/B/C).
- `vision.py`: captura de tela por HWND (P1-F; interpretação geral bloqueada — sem backend local).
- Pasta `tools/` na raiz é utilitários de dev: `probe_voice.py`, `testar_intents.py`, `auditar_compreensao.py`, `guardar_chave_telegram.py`, entre outros — NÃO são ações de runtime.

### 4. Pipeline de VOZ (fluxo de ponta a ponta)
1. **Captura no RENDERER Electron** (Chromium faz canc. de eco — AGENTS.md) → IPC `handle_voice_mic_chunk` (ipc_handlers:954, `push_mic_pcm` → gemini_live_voice:394).
2. **Gemini Live** transmite continuamente; **wake por transcrição** (`_WAKE_PREFIX_RE`) no `_on_gemini_live_turn`.
3. **Barge-in real** (VAD servidor) + **auto-eco** filtrado por conteúdo em `_looks_like_own_echo`.
4. **Intent → Ação**: `core/pc_voice_intent.py` + dispatch no `ipc_handlers` → executor em `core/actions/`.
5. **Resposta → TTS** via cascata `core/voice_tts.py` (`TTSManager`).
6. **Observabilidade:** `core/cronometro.py` mede latência NO DISCO; `[VOICE_TRACE]` em ipc_handlers:2219; mediana limpa de descartes 0ms (CADERNO-DE-TAREFAS linha 168).
- **Latência:** pipeline paralelo à voz do Hermes, roteamento, health cache (<15s) — ver skills `zara-development` → `references/hermes-brain-voice.md`.

### 5. Frontend Electron (`frontend/src/`)
- Renderer React: `src/renderer/components/zara/` (UI da ZARA), `lib/` (`aecAudio.ts` = áudio/AEC, `aparencia.ts`, `chatHistory.ts`), `styles/` (`tokens.css`, `padroes.css`, `pearl.css`, `instrumento.css`, `pele-instrumento.css`, `aparencia.css` — 13 peles, tokens), `types/`.
- **`ConversaInstrumento.tsx`** (componente novo, ligável/desligável — CADERNO-DE-TAREFAS 15/08): medidor de nível, painel do último valor, registro de turnos com selo.
- `src/main.ts`, `preload.ts`, `reminderEvents.ts`.

### 6. Build system
- **`build_exe.py`** (PyInstaller): constrói SÓ o sidecar Python `zara-backend.exe` (`build-sidecar/` `dist-sidecar/`), `console=True` (comunica via stdin/stdout — linhas 20-41). `main.py` é o entry point. Não toca artefatos Electron.
- Frontend: `frontend/` tem `npm run typecheck/lint/build/build:electron` (AGENTS.md). Builds candidatas em `frontend/release/` + `release-candidate-*/`.
- Regra AGENTS.md: build sempre com `.venv\Scripts\python.exe`, nunca `python` solto (contaminação PATH Hermes). Usar npm, nunca pnpm.

### 7. Testes e dependências
- 80 arquivos `tests/test_*.py`. Testes de voz: `test_gemini_live_voice_responsiveness.py`, `test_voice_latency_vad.py`, `test_voice_conversation_fluidity.py`, `test_voice_tts_cascade.py`, `test_voice_pipeline_safety.py`, `test_system_voice_intents.py`, `test_file_voice_intent.py`, `test_clipboard_voice.py`. CADERNO-DE-TAREFAS reporta 1075 testes verdes (15/08).
- `requirements.txt` (61 linhas) inclui: `vosk`, `pvporcupine`, `kokoro-onnx`, `edge-tts`, `miniaudio`, `sounddevice`, `pycaw`, `mss`, `pytesseract` (verificado por grep).
- Rutas executáveis via `.venv\Scripts\python.exe -m pytest -q` e `ruff check core memory integrations tests`.

### 8. Estado documentado (FINAL_GAPS_ROADMAP + CADERNO-DE-TAREFAS)
- **P0 voz física**: AUTONOMOUS_DONE/AWAITING_ALEX_PHYSICAL. Wake gate, mic→intent→action, barge-in, self-listening prontos no código; microfone real + modelos presentes; física não provada. `FINAL_GAPS_ROADMAP.md` linhas 7-18.
- **`FINAL_GAPS_ROADMAP.md`** (169 linhas): P0-A voz física (DONE/AWAITING), P0-B reminder UTF-8 (DONE), P1-A janelas (DONE), P1-B browser (DONE), P1-C input (DONE), P1-D áudio global (DONE/AWAITING), P1-E info PC (DONE), P1-F visão (DONE)/BLOCKED, P2-A Jarvis 5/5 (DONE), P2-B LAB (DONE), P3-A smart router (DONE), P3-B soak (DONE). Fora fila: paint/calculadora/Edge/Spotify/power deletado = SKIPPED/BLOCKED por escopo/segurança.
- **`CADERNO-DE-TAREFAS.md`** (197 linhas): histórico de delegação Claude/Codex; instrumentações de latência, honestidade (`ActionResult.verificado`), aprovação remota, etc.
- **Regra nº 1 do repo (AGENTS.md)**: nada de falso sucesso — toda ação confirma pós-condição real (`result.success`); manter honestidade integral.

---

## SEÇÃO SKILLS HERMES (task-002 — PESQUISADOR_REVERSO)

> Skills Hermes já existentes/disponíveis que aceleram o trabalho da fábrica ZARA. Cada skill nomeada é REAL (verificada no catálogo deste perfil). Recomendações de uso por task.

### Skills diretas da ZARA (já carregadas e usadas)
- **`zara-development`** (software-development): o manual operacional do repo `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`. Regras: PYTHONPATH vazio p/ não poluir o venv, `.venv\Scripts\python.exe` sempre, pitfalls Flet/Electron (window.width, Dialog dual, índices mágicos), build sidecar, patches de latência de voz, gambiarras de integração com Codex/Claude. **Obrigatória p/ @executor_dev e @qa_tester** antes de tocar em código.
- **`zara-canonical-root-audit`** (zara): achar a raiz canônica da ZARA entre múltiplas pastas (`CLEAN 002`, `ZARA_SuperCerebro`, `Mark-L`) + auditoria local-vs-GitHub SEM tocar worktree. Regra de ouro: READ-ONLY, nunca alterar/abrir/launchar ZARA, nunca matar processos. **Já aplicada: raiz = CLEAN 002 (github HEAD 98d5592), SEM FIFOtos.**

### Skills de AUTOMAÇÃO/desenvolvimento avião (acceleração paralela)
- **`claude-code`** (autonomous-ai-agents): delegar código ao Claude Code CLI (features, PRs) — encaixa na ponte ZARA↔Claude já existente (`core/actions/ponte_claude.py`, `CADERNO-DE-TAREFAS`).
- **`codex`** (autonomous-ai-agents): delegar ao OpenAI Codex CLI — espelha a ponte `core/ponte_codex_cli.py`. Útil p/ o @executor_dev rodar códigos de UI no app.
- **`computer-use`** (autonomous-ai-agents): dirigir o desktop Windows em background SEM roubar o cursor/foco. **Chave p/ testar a ZARA real** (P0 voz física, P1 janelas) — ver skill `zara-development` → `references/zara-lab-mentor-relay.md` p/ pitfalls do Electron (AX tree morre após minimize, `cua_browser_*` recusa Electron, type exige foreground).
- **`systematic-debugging`** (software-development): 4 fases de root cause antes de consertar — alinhado à regra "sem falso sucesso" da ZARA.

### Skills de MCP / infra (apoio ao @arquiteto_mcp TASK-005)
- **`hermes-gateway-integration`** (software-development): chamar o gateway Hermes de agentes externos (127.0.0.1:8642) + pool de IAs gratuitas (Ollama/OpenRouter :free/NVIDIA NIM) via `references/moa-free-model-pool.md`. Base para automação MCP Windows da ZARA.
- **`hermes-provider-setup`** (hermes): adicionar/trocar provedores LLM no Hermes — útil p/ o router da ZARA (`core/model_router.py`).
- **`airtable`, `notion`, `powerpoint`, `xlsx`, `docx`, `pdf`** (productivity): extensões de conteúdo se algum agente precisar gerar/ler esses formatos.
- **`huggingface-hub`** (mlops): baixar modelos (ex.: pesos do Kokoro ONNX p/ TTS local offline) via hf CLI.

### Skills de qualidade/revisão (apoio ao @revisor_supervisor e @qa_tester)
- **`requesting-code-review`** (software-development): revisão pré-commit com securrscan e auto-fix. **`github-code-review`** (github): comentar PRs via gh. **`systematic-debugging`** acima.

### Skills cross-ZARA (runtime próprio)
- **`zara-autonomous-execution`** (software-development): executar batches autônomos da ZARA via GitHub bus do Mentor. **`zara-autonomous-ops`** (zara): tarefas batched 031-080 com safety rails. **`zara-room-operations`** (zara): alcançar o Mentor do Hermes em activate/talk. **`caderninho-de-ideias`** (zara), **`zara-corujao`** (zara): runs overnight com kanban+watchdog.

### Recomendações de aceleração por task
| Task | Skill prioritária |
|---|---|
| @arquiteto_mcp (TASK-005 MCP Windows) | `hermes-gateway-integration` + `computer-use` + `zara-development`(refs) |
| @pesquisador_ux (TASK-006 voice) | `zara-development` → refs `hermes-brain-voice.md`, `zara-model-router-diagnosis.md` | 
| @seguranca_redteam (TASK-007) | `requesting-code-review` + `systematic-debugging` |
| @qa_tester (TASK-003) | `zara-development` (pytest com PYTHONPATH vazio) + `systematic-debugging` |
| @executor_dev (TASK-008-PREP) | `zara-development` + `claude-code` + `codex` |
| @designer_ui_ux (TASK-004) | `popular-web-designs` + `sketch`/`claude-design` (mockups) — ver seções de tokens em `frontend/src/renderer/styles/` |

> Nota de honestidade: as skills acima estão listadas no catálogo deste perfil (`skills_list`). Cada agente deve confirmar via `skills_list`/`skill_view` se possui/quer carregar cada uma; os limites de sessão/cache descritos em `hermes-agent-skill-authoring` (loader cacheado por sessão) se aplicam.

---

## SEÇÃO BUGS CONHECIDOS (task-003 — QA_TESTER)

*Aguardando entrega do qa_tester*

---

## SEÇÃO UI MODERNA (task-004 — DESIGNER_UI_UX)

*Aguardando entrega do designer_ui_ux*

---

## SEÇÃO MCP ARCH (task-005 — ARQUITETO_MCP)

*Aguardando entrega do arquiteto_mcp*

---

## SEÇÃO VOICE PIPELINE (task-006 — PESQUISADOR_UX)

*Aguardando entrega do pesquisador_ux*

---

## SEÇÃO SECURITY AUDIT (task-007 — SEGURANCA_REDTEAM)

*Aguardando entrega do seguranca_redteam*