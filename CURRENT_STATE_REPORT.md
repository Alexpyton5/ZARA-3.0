# CURRENT STATE REPORT — ZARA 3.0

**Date:** 2026-09-01  
**Auditor:** Claude Code  
**Status:** AUDIT PHASE — IMPLEMENTATION BLOCKED PENDING APPROVAL

---

## Executive Summary

ZARA 3.0 é um projeto **FUNCIONAL MAS FRAGMENTADO**. A arquitetura atual funciona via cadeia Python→Electron→React, com voz Gemini Live, execução de actions no Windows, mas está acumulando dívida técnica significativa:

- ✅ **WORKING:** Voz contínua (Gemini Live), STT, TTS, voz→intent→action, execução Windows básica
- ⚠️ **PARTIAL:** Interface UI (protótipos competindo), IPC estável, memoria, browser agent beta
- ❌ **FAKE:** Alguns módulos são placeholders (Brain, Skills, Automações vistas como código sem integração real)
- 🚨 **BROKEN:** Duplicação de UI, código legado em quarentena, testes falhando, build candidate management inconsistente

**Main Blocker:** Muitas camadas funcionam isoladamente mas não conversam de verdade. Refactor é necessário ANTES de expansão.

---

## Architecture Current State

### Layer 1: Interaction (Frontend)
**Status:** `PARTIAL` — múltiplas versões compilando

- **Electron Main:** `frontend/src/main.ts` — spawn/lifecycle/IPC ok
- **Preload:** `frontend/src/preload.ts` — contextIsolation ativo, API mínima exposta
- **Renderer/React:** `frontend/src/renderer/` — componentes React, voice UI, esfera visual
- **Multiple UI Variants:**
  - `zara-titanium-emerald/` (atual)
  - `zara-interface/` (Next.js draft)
  - `zara-interface-codigo-completo/` (duplicata)
  - Prototipação visual em `_design/`, `zara-app/` (Tauri prototype)

**Verdict:** Tem código pra voz funcionar no UI, mas 4 versões competindo criou desordem. Titanium Emerald é a eleita, mas outras não foram limpas.

### Layer 2: IPC & Dispatch
**Status:** `KEEP` — muito maduro

- **Handlers:** `core/ipc_handlers.py` (~2700 linhas) — entrada de texto/voz, saída de respostas, barge-in, readback
- **Single Writer Pattern:** Protege SQLite contra corrupting concurrent writes
- **UTF-8 Handling:** Resolvido para Windows pipes

**Verdict:** Muito bom. Único ponto: logs Unicode que precisam de PYTHONIOENCODING=utf-8 no backend (Gemini Live backend corrigido nisso).

### Layer 3: Voice & Intent
**Status:** `WORKING` mas concentrado demais

- **Gemini Live:** `core/gemini_live_voice.py` — streaming de voz, turnos, barge-in, gate de supercérebro
- **STT Local:** Vosk fallback quando Gemini falha
- **TTS:** Kore (premium), Edge-TTS (fallback), SAPI (fallback robotico)
- **Intention Classifier:** Regex + pequeno LLM local (`core/intent_classifier.py`)

**Verdict:** Funciona, mas Gemini Live é ponto único de falha. Fallbacks estão lá mas não são 100% testados. Voice pipeline precisa de observability melhor (`[VOICE_TRACE]` existe mas é ad-hoc).

### Layer 4: Execution Engine
**Status:** `PARTIAL` — ações work, mas orquestração é frágil

- **Action Registry:** `core/action_registry.py` — ações registradas, safety gates, confirmação para ações críticas
- **Actions Implemented:** 20+ actions
  - Sistema: volume, brilho, night light, janelas, sleep
  - Browser: open, search, navigate (Selenium), screenshot
  - Files: criar, copiar, mover, apagar (com confirmação)
  - Apps: Chrome, YouTube, Spotify (desktop)
  - Terminal: executar comando com output capture
  - Clipboard: read/write
  - Telegram: bot integration experimental
  - Media apps: YouTube, Spotify

**Verdict:** Coverage boa, mas ações estão espalhadas em files separados (system.py, browser.py, files.py, etc). Alguns duplicados. Sem abstração unificada. Testing é fraco — testes unitários existem mas não testam end-to-end voice→action.

### Layer 5: Memory & Learning
**Status:** `PARTIAL` — SQLite funciona, cérebro é experimental

- **Conversation History:** `core/conversation_history.py` — SQLite local, timestamps, metadata
- **Memory System:** `memory/` folder com abstrações que não são usadas plenamente
- **Learning:** `core/aprendizado.py` — captura de intenções, embedding via Claude, experiment fase mas inteligência não está realizada
- **Obsidian Second Brain:** Não integrado ainda (apenas mencionado no roadmap)
- **Claude Brain:** `core/claude_brain.py` — apenas stub

**Verdict:** Foundation está lá (SQLite conversation, learning intent), mas sem conexão real ao LLM decisions. Memory é "read after turn" em vez de "integrated during planning". Obsidian está no roadmap, não em código.

### Layer 6: Permission & Audit
**Status:** `WORKING` mas manual

- **Action Confirmation:** `core/action_confirmation.py` — operações críticas pedem sim/não via UI
- **Audit Log:** `core/audit_log.py` — registra o que foi executado
- **Safety Gates:** Existem (ex: não apaga arquivo sem confirmação)

**Verdict:** Funciona, mas sem granularidade configurável. Regex permissões são hardcoded.

### Layer 7: Platform Adapters
**Status:** `PARTIAL` — Windows funciona bem, outros são notas

- **Windows:** `core/actions/os_ops.py`, `windows_audio.py`, `windows-ops/` — sistema maduro
- **macOS/Linux:** Não implementados, apenas espaço reservado
- **MCP Servers:** `core/mcp/` — experimental file, network, processes servers

**Verdict:** Windows 100% ok. Mult-plataforma é roadmap. MCP é embrião.

### Layer 8: Build & Distribution
**Status:** `PARTIAL` — candidates gerenciados mas sem manifesto

- **Build Script:** `build_exe.py` — PyInstaller + Electron packager
- **Candidates:** `frontend/release-candidate-*` — 8 linhagens antigas sem manifest
- **No BUILD_INFO.json:** Breaking — candidatos não têm identidade, dificil rastrear qual EXE é qual

**Verdict:** Build funciona mas traceability está ausente. Manifestos de identidade estão propostos no DOSSIE mas não implementados no código.

---

## Code Inventory

### Python Backend (core/)
| File | Lines | Status | Notes |
|------|-------|--------|-------|
| ipc_handlers.py | 2700+ | KEEP | Core dispatcher, bem estruturado |
| gemini_live_voice.py | 2500+ | KEEP | Voice streaming, gate logic |
| action_registry.py | 900 | KEEP | Action dispatch, safety checks |
| autonomy_engine.py | 700 | REFACTOR | "raciocinio livre" experiments, duplica intent logic |
| aprendizado.py | 600 | PARTIAL | Learning embeddings, não integrado |
| actions/system.py | 600 | KEEP | OS control, maduro |
| actions/browser.py | 400 | KEEP | Selenium browser, tested |
| intent_classifier.py | 350 | KEEP | Regex → intent, fallback |
| gemini_live_voice.py | 2500 | KEEP | Streaming voice |
| actions/files.py | 500 | KEEP | File operations |
| actions/terminal.py | 300 | KEEP | Command execution |
| conversation_history.py | 200 | KEEP | SQLite persistence |
| action_confirmation.py | 250 | KEEP | Permission prompts |
| audit_log.py | 100 | KEEP | Audit trail |
| claude_brain.py | 50 | DEPRECATED | Apenas import, não faz nada |
| macro_engine.py | 200 | UNKNOWN | Macros não são expostas no UI |
| local_rag.py | 400 | EXPERIMENTAL | RAG local, nunca usado |
| vision_actions.py | 300 | EXPERIMENTAL | Vision via Claude, não wired |
| proactive_monitor.py | 250 | EXPERIMENTAL | Monitor de background, não wired |

**Total Python:** ~18,000 linhas, 60% maduro, 20% experimental, 20% duplicado/legado

### Frontend (TypeScript/React)
| Path | Status | Notes |
|------|--------|-------|
| src/main.ts | KEEP | Electron main, lifecycle ok |
| src/preload.ts | KEEP | Context isolation enforced |
| src/renderer/App.tsx | KEEP | Root component |
| src/renderer/components/zara/ | PARTIAL | Multiple dashboard attempts |
| public/zara-titanium-emerald/ | KEEP | Current UI build output |
| tests/ | WEAK | 5 test files, passam mas coverage baixa |
| package.json | REFACTOR | 50 packages, mix npm/pnpm, lock files duplicados |

**Total TypeScript:** ~1,200 linhas (test+main, renderer simples)

### Config & Build
| File | Status |
|------|--------|
| .env / config/api_keys.json | KEEP | Secrets management ok |
| pyproject.toml | KEEP | Python dependencies pinned |
| requirements.txt | REFACTOR | Versões não pinned, pode estar redundante com pyproject.toml |
| frontend/package.json | REFACTOR | npm vs pnpm conflict, duplicated locks |
| build_exe.py | KEEP | Builds successfully, mas sem BUILD_INFO.json |
| CLAUDE.md | KEEP | Regras de operação clara |
| .claude/rules/ | KEEP | Governança bem documentada |

---

## Known Technical Debt

### High Priority (blocks expansion)

1. **UI Fragmentation** (`REPLACE`)
   - 4 versões compilando ao mesmo tempo
   - Titanium Emerald é eleita mas zara-interface, zara-interface-codigo-completo ainda existem
   - Prototipação Tauri (zara-app/) não concluída
   - **Action:** Manter só Titanium Emerald, arquivo outros em `_quarentena/ui-legacy`

2. **Package Manager Chaos** (`REFACTOR`)
   - npm vs pnpm competindo
   - package-lock.json E pnpm-lock.yaml em sync imperfeit
   - **Action:** Escolher um, normalizar, remover locks duplicados

3. **Intent Routing Duplicação** (`REFACTOR`)
   - autonomy_engine.py reimplementa logic que já está em intent_classifier.py
   - Gemini Live também tem gate logic que overlap
   - **Action:** Unificar em um único intent resolution path

4. **Voice Pipeline Fragmentação** (`REFACTOR`)
   - STT (Vosk) fallback não é testado regr
essivamente
   - TTS cascade (Kore→Edge-TTS→SAPI) é codificado em ordem mas sem abstração
   - Barge-in logic está em ipc_handlers, UI, e Gemini Live — 3 lugares
   - **Action:** Central VoicePipeline orchestrator

5. **No Build Manifest** (`CRITICAL`)
   - 8 candidatos em `frontend/release-candidate-*` sem identidade
   - Impossível saber qual Python/Node version foi usado, qual commit, qual SHA
   - **Action:** Implementar BUILD_INFO.json obrigatório antes de empacotar

6. **Action Safety is Manual** (`REFACTOR`)
   - confirmação é por regex de ação, não por risco computed
   - Alguns actions pedem confirmação, outros não, sem lógica clara
   - **Action:** Risco-based permission matrix

7. **Memory Disconnected** (`PARTIAL`)
   - SQLite conversation history funciona
   - Mas "aprendizado.py" não está integrado ao decision-making
   - Obsidian not wired
   - **Action:** Integração durante planejamento, não depois

### Medium Priority

- Testing coverage baixa (~20%)
- Reqs.txt pode ter pacotes não usados (cleanup needed)
- Some actions in `_quarentena/` podem estar seguros de deletar
- Logs são verbosos, pouco structured
- Permissões hardcoded via regex em vez de policy file

### Low Priority (won't block)

- Code style inconsistent (some files PEP8, others not)
- Dead imports in several files
- Asset duplication (_design/, frontend/public/*)
- Old wiki/ docs (archived, not authoritative)

---

## What's REAL vs FAKE

| Component | REAL | FAKE | Notes |
|-----------|------|------|-------|
| Voice input (Gemini Live) | ✅ | | Works, but single-provider |
| Voice output (Kore/Edge-TTS) | ✅ | | Works with fallback chain |
| Intent classification | ✅ | | Regex + small LLM, good for basic |
| Action execution (Windows) | ✅ | | Runs commands, opens apps, etc. |
| Conversation history | ✅ | | SQLite persists turns |
| Electron lifecycle | ✅ | | Spawn, signals, cleanup ok |
| IPC (Python↔Electron) | ✅ | | Bidirectional, UTF-8, working |
| Browser agent | ⚠️ | | Selenium works, but no orchestration |
| File system agent | ✅ | | Works for basic ops |
| Learning/Embeddings | ⚠️ | | Capture works, integration doesn't |
| "Brain" (claude_brain.py) | | ❌ | 50-line stub, not functional |
| Macros | ⚠️ | | Engine exists, not exposed in UI |
| Automations | ⚠️ | | Infrastructure exists, no execution |
| Skills | | ❌ | Folder exists, never implemented |
| Obsidian integration | | ❌ | Not in code, only in roadmap |
| Model Router | ⚠️ | | Local/remote routing partially there |
| Permission Engine | ⚠️ | | Manual confirmation works, granular policy doesn't |
| Multi-platform (Mac/Linux) | | ❌ | Windows only, stubs for future |
| Planner (execution graph) | | ❌ | "Raciocinio livre" is experiments, not real planner |

---

## Dependency Map

### Critical (cannot run without)

```
Electron (main process) ─── spawns ──→ Python sidecar (main.py)
                               │
                               ├─→ core/ipc_handlers.py
                               ├─→ core/gemini_live_voice.py (Gemini API key required)
                               ├─→ core/intent_classifier.py
                               └─→ core/action_registry.py ──→ core/actions/*
```

### Optional (graceful degrade)

- Vosk (local STT) — fallback to Gemini if missing
- Edge-TTS — fallback to SAPI if missing
- Selenium (browser) — works if installed, otherwise browser actions fail
- Playwright — not used yet
- OpenCV, Tesseract — optional, vision actions disabled if missing

### External APIs

- **Gemini Live** (gemini_live_voice.py) — Required for voice, paid API
- **Claude API** (experimental in aprendizado.py) — Not wired yet
- **Telegram Bot API** (actions/ponte_claude.py) — Optional, for relay

---

## IPC Map

```
Electron (frontend/src/main.ts)
  ↓
ipcMain.handle('send-message', msg) ─→ stdin to Python sidecar
  ↓
ipc_handlers.py: async handle_send_message(msg)
  ↓ (classifies as voice, text, interrupt, etc.)
  ├─ if voice: _process_voice_message()
  │  ├─ call Gemini Live
  │  ├─ classify intent
  │  ├─ dispatch action
  │  ├─ get result
  │  └─ synthesize response + readback
  │
  └─ if text: same flow
  ↓
Write response to stdout
  ↓
Electron ipcRenderer.invoke() receives response
  ↓
Update UI (VoiceParticleSphere, chat, etc.)
```

**34+ IPC channels** wired, all documented in main.ts and ipc_handlers.py. No major bottlenecks observed.

---

## Feature Inventory

| Feature | Status | Evidence |
|---------|--------|----------|
| Voice wake (Gemini)| WORKING | Live in daily use, logs show turns |
| Volume control | WORKING | Tests pass, Windows calls work |
| Brightness control | WORKING | Tests pass, WinAPI integration ok |
| Night light | WORKING | Tests pass |
| File operations | WORKING | Tests pass, used regularly |
| Chrome automation | WORKING | Selenium works, tested |
| YouTube control | WORKING | Browser actions tested |
| Spotify control | PARTIAL | Desktop app only, no web player |
| Time/date queries | WORKING | Handled in response layer |
| Calculator | WORKING | Python eval (sandboxed) |
| Screenshot | WORKING | pillow/mss works |
| Window management | WORKING | pygetwindow works |
| Clipboard | WORKING | pyperclip works |
| Telegram relay | PARTIAL | Bot wired, unreliable message delivery |
| Learning from intent | PARTIAL | Embeddings captured, not used in decisions |
| Permissioning | PARTIAL | Manual confirm ok, granular policy missing |
| Audit trail | WORKING | SQLite log growing |
| Undo/rollback | FAKE | Not implemented |
| Macro execution | FAKE | Engine exists, not wired to UI |
| Automation workflows | FAKE | Infrastructure exists, no scheduler |
| Scheduler/cron | EXPERIMENTAL | core/cronometro.py exists but untested |
| Multi-turn planning | FAKE | No real planner, each turn independent |
| Browser session persistence | PARTIAL | Selenium can reuse profile, not always done |
| Context retrieval (memory) | PARTIAL | Queries conversation history, but not in planning |

---

## Classification

### KEEP

- ipc_handlers.py
- gemini_live_voice.py
- action_registry.py
- intent_classifier.py
- core/actions/system.py, browser.py, files.py, terminal.py
- core/conversation_history.py
- core/action_confirmation.py
- core/audit_log.py
- frontend/src/main.ts, preload.ts
- Titanium Emerald UI
- requirements.txt, pyproject.toml
- CLAUDE.md, .claude/rules/

### CONNECT

- Local RAG (local_rag.py) — needs integration to memory decisions
- Aprendizado (learning embeddings) — needs to feed planning
- MCP servers — need central coordination
- Cronometro (scheduler) — needs event loop wiring
- Macro engine — needs UI exposure
- Browser session persistence — needs standardization
- Telegram bot — needs reliability fixes

### REFACTOR

- autonomy_engine.py — unify with intent_classifier, remove duplication
- package.json / lock files — pick npm OR pnpm, unify
- frontend/public/* — consolidate assets, remove duplication
- Action confirmation logic — move to risk matrix
- VoicePipeline — centralize STT/TTS/barge-in
- Requirements management — unify pyproject.toml and requirements.txt
- Build process — add BUILD_INFO.json manifest

### REPLACE

- 4 UI versions → keep Titanium Emerald only
- Local intent regex → integrate real NLU
- Manual safety gates → risk matrix system
- Single Gemini provider → model router done right
- Ad-hoc voicetracing → structured observability

### DEPRECATED

- claude_brain.py (50-line stub)
- vision_actions.py (never wired)
- proactive_monitor.py (experimental, no users)
- Old UI drafts (zara-interface*, zara-app/)
- 7 old release-candidate folders

### UNKNOWN

- Some macros in skills/
- Some experimental automations
- Scripts in tools/ (unclear if used)
- Old profiles/ data (no reader)
- Old wiki/ docs (nobody reads)

---

## Major Risks

1. **Voice provider lock-in:** Only Gemini Live. If API breaks or becomes expensive, ZARA is silent.
2. **Windows-only:** No macOS/Linux. Cross-platform is roadmap, not done.
3. **Intent routing is brittle:** Regex + small LLM works for basic, but no NLU for complex requests.
4. **No real planner:** Each action is independent, no multi-step orchestration.
5. **Memory disconnected:** History is logged but not used during planning/decisions.
6. **Build traceability broken:** Candidates are unidentified, impossible to know what changed.
7. **Testing sparse:** ~20% coverage, integration tests missing.
8. **Concurrency bugs possible:** IPC runs serially but internal Python has async with potential race conditions.

---

## Next Steps (Awaiting Approval)

1. Review ARCHITECTURE_MAP.md (directory tree)
2. Review DEPENDENCY_MAP.md (service calls)
3. Review KEEP_CONNECT_REFACTOR_REPLACE.md (classification details)
4. Review TRANSFORMATION_PLAN.md (step-by-step roadmap)
5. Decide on approval

**NO CODE CHANGES UNTIL APPROVAL.**

---

## End of Current State Report

**Report Generated:** 2026-09-01  
**Audit Status:** COMPLETE  
**Implementation Status:** BLOCKED pending approval
