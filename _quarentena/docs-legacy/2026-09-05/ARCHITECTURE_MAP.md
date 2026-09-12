# ARCHITECTURE MAP — ZARA 3.0 Current

## Directory Tree (Simplified)

```
ZARA 3.0 CLEAN 002/
│
├── .claude/                           # Claude Code configuration
│   ├── rules/                         # Governance rules (time-zara.md, evidence.md, etc)
│   └── copyback/                      # Session artifacts
│
├── .zara-dev/                         # Development state
│   ├── continuity/                    # Continuity engine (experimental)
│   ├── tasks/                         # Task tracking
│   └── reports/                       # Audit reports
│
├── frontend/                          # Electron + React
│   ├── src/
│   │   ├── main.ts                    # Electron main process
│   │   ├── preload.ts                 # Context isolation bridge
│   │   ├── renderer/
│   │   │   ├── App.tsx                # Root component
│   │   │   ├── components/zara/       # ZARA-specific components
│   │   │   │   ├── ZaraControlCenter.tsx
│   │   │   │   ├── VoiceParticleSphere.tsx
│   │   │   │   ├── Dashboard.tsx      # Prototypes
│   │   │   │   ├── interface/         # UI components (experimental)
│   │   │   │   └── (multiple versions)
│   │   │   └── lib/aecAudio.ts        # Audio echo cancellation
│   │   └── types/global.d.ts          # IPC contract
│   │
│   ├── public/
│   │   ├── zara-titanium-emerald/     # ← CURRENT BUILD OUTPUT
│   │   │   ├── index.html
│   │   │   ├── assets/                # JS, CSS bundles
│   │   │   └── references/MASTER_UI.png
│   │   ├── zara-interface/            # (deprecated)
│   │   └── zara_interface/            # (deprecated)
│   │
│   ├── dist-electron/                 # Electron app package (post-build)
│   ├── dist-frontend/                 # Frontend app build (post-build)
│   ├── release/                       # ← BASELINE UI, preserve
│   ├── release-candidate-*            # Old builds (8 linhagens, no manifest)
│   └── package.json                   # npm/pnpm (mixed, conflict)
│
├── core/                              # Python sidecar (BRAIN)
│   ├── __init__.py
│   │
│   ├── ipc_handlers.py                # ← CORE DISPATCHER (~2700 lines)
│   │   ├─ handle_send_message()
│   │   ├─ _process_voice_message()
│   │   ├─ _speak_response()
│   │   ├─ handle_interrupt()
│   │   └─ 34+ IPC channels
│   │
│   ├── gemini_live_voice.py           # ← VOICE ENGINE (~2500 lines)
│   │   ├─ Gemini Live streaming
│   │   ├─ Turn management
│   │   ├─ Barge-in logic
│   │   └─ Gate (supercérebro on/off)
│   │
│   ├── intent_classifier.py           # ← INTENT RESOLUTION (~350 lines)
│   │   ├─ Regex patterns → intent name
│   │   ├─ Fallback to small LLM
│   │   └─ Lists local-deterministic actions
│   │
│   ├── action_registry.py             # ← ACTION DISPATCH (~900 lines)
│   │   ├─ Registry of 20+ actions
│   │   ├─ Safety gates + confirmation
│   │   ├─ Result extraction
│   │   └─ Readback generation
│   │
│   ├── actions/                       # Action implementations
│   │   ├── system.py                  # Volume, brightness, night light, etc.
│   │   ├── browser.py                 # Selenium-based browser control
│   │   ├── files.py                   # File operations (create, copy, delete, etc)
│   │   ├── os_ops.py                  # Windows-specific system ops
│   │   ├── terminal.py                # Command execution
│   │   ├── media_apps.py              # YouTube, Spotify, etc.
│   │   ├── web.py                     # Web requests, search
│   │   ├── scheduler.py               # Cron-like scheduling (experimental)
│   │   ├── ponte_claude.py            # Relay to Claude via IPC
│   │   ├── code.py                    # Code execution, linting
│   │   ├── vision_actions.py          # Vision via Claude API (not wired)
│   │   ├── system_advanced.py         # Advanced system ops (experimental)
│   │   ├── macro_actions.py           # Macro recording/playback (not exposed)
│   │   ├── aprendizado_acoes.py       # Learning from actions (experimental)
│   │   └── __init__.py                # Action enum, dispatcher
│   │
│   ├── autonomy_engine.py             # "Raciocinio livre" experiments (~700 lines)
│   │   ├─ Alternative intent routing (duplicates intent_classifier)
│   │   ├─ Flag-gated reasoning
│   │   └─ [KNOWN DUPLICATION]
│   │
│   ├── conversation_history.py        # ← MEMORY PERSISTENCE
│   │   └─ SQLite conversation log
│   │
│   ├── aprendizado.py                 # Learning + embeddings (~600 lines)
│   │   ├─ Captures intent patterns
│   │   ├─ Generates embeddings via Claude
│   │   └─ [NOT INTEGRATED TO DECISIONS]
│   │
│   ├── action_confirmation.py         # Permission prompts
│   │
│   ├── audit_log.py                   # Audit trail
│   │
│   ├── intent_classifier.py           # Backup intent routing
│   │
│   ├── model_router.py                # Local/remote model selection (experimental)
│   │
│   ├── claude_brain.py                # [DEPRECATED] 50-line stub
│   │
│   ├── local_rag.py                   # Local RAG engine (~400 lines, not used)
│   │
│   ├── macro_engine.py                # Macro execution (~200 lines, not exposed)
│   │
│   ├── voice_stt.py / voice_tts.py    # Voice I/O wrappers
│   │
│   ├── mcp/                           # MCP server implementations (experimental)
│   │   ├── servers/file_ops.py
│   │   ├── servers/network.py
│   │   ├── servers/processes.py
│   │   └── servers/registry.py
│   │
│   ├── memory/                        # Memory schemas (experimental)
│   │   ├── contextual_memory.py
│   │   └── conversation_memory.py
│   │
│   ├── obsidian_memory.py             # Obsidian integration [NOT IN CODE YET]
│   │
│   ├── proactive_monitor.py           # Background monitoring (experimental)
│   │
│   ├── screen_understanding.py        # Vision pipeline (experimental)
│   │
│   ├── vibe_guardrails.py             # Personality constraints (experimental)
│   │
│   ├── paths.py                       # Config directory management
│   │
│   ├── single_writer.py               # SQLite concurrency guard
│   │
│   └── ... 30+ other support files
│
├── memory/                            # Memory schema definitions
│   └── (structured storage, experimental)
│
├── integrations/                      # External integrations
│   ├── telegram_bot.py                # Telegram relay
│   └── ...
│
├── tests/                             # Test suite
│   ├── test_action_registry_safety.py
│   ├── test_brightness_control.py
│   ├── test_file_actions.py
│   ├── test_provider_failover.py
│   ├── test_volume_context.py
│   ├── ... (~5 test files, ~20% coverage)
│   └── regression_suite.py
│
├── tools/                             # Utility scripts
│   ├── boilerplate_gen.py
│   ├── file_organizer.py
│   ├── git_assistant.py
│   ├── media_downloader.py
│   ├── meeting_transcriber.py
│   ├── mock_data_gen.py
│   ├── price_watch.py
│   ├── smart_clipboard.py
│   ├── snippet_finder.py
│   ├── syntax_watcher.py
│   ├── system_stats.py
│   ├── zara_claude_bridge.py
│   └── zara_telegram_bot.py
│
├── skills/                            # Skill system (not implemented)
│   └── (empty or templates)
│
├── docs/                              # Documentation
│   ├── mentor-handoff/
│   │   └── MENTOR_BRAIN_TRANSFER_TO_CLAUDE_CODE.md
│   └── ...
│
├── config/                            # Configuration
│   ├── api_keys.json                  # Secrets (DO NOT COMMIT)
│   ├── telegram_lido.json
│   └── ...
│
├── _quarentena/                       # Quarantine (old, probably deletable)
│   └── scripts_debug_20260827/
│
├── _design/                           # Design artifacts
│   └── (mockups, PNGs, etc.)
│
├── zara-app/                          # Tauri prototype (abandoned)
│   └── src-tauri/
│
├── zara-interface*/                   # Old UI drafts (deprecated)
│   └── (multiple versions, not maintained)
│
├── plugins/                           # Plugin system (experimental)
│
├── profiles/                          # User profiles (old data)
│
├── wiki/                              # Wiki docs (archived, not authoritative)
│
├── main.py                            # ← ENTRY POINT
│   └─ Starts Python sidecar, calls ipc_handlers.main()
│
├── build_exe.py                       # ← BUILD SCRIPT
│   └─ PyInstaller + electron-builder
│
├── requirements.txt                   # Python dependencies (not pinned)
│
├── pyproject.toml                     # Python project config (pinned)
│
├── CLAUDE.md                          # Governance rules
│
├── README.md                          # Project overview
│
├── CADERNO-DE-TAREFAS.md              # Task log
│
└── ABRIR-A-ZARA.bat                   # Windows launcher
```

---

## Data Flow Diagram

```
[ZARA User]
    │ (speaks)
    ▼
[Electron Main] ─ Frontend (React/TypeScript)
    │
    ├─ Microphone input
    │   ▼
    ├─ ipcMain.handle('send_message') 
    │   ▼
    ├─ Writes to stdin
    │
    ├─ [Python Sidecar Process] ─ ipc_handlers.py
    │   ├─ _process_voice_message(audio)
    │   │   ▼
    │   ├─ Gemini Live streaming (turn-based)
    │   │   ▼
    │   ├─ Extract text from response
    │   │   ▼
    │   ├─ intent_classifier.py:  text → intent name
    │   │   ▼
    │   ├─ action_registry.dispatch(intent)
    │   │   ├─ Safety check (confirm if needed)
    │   │   ├─ Call action executor
    │   │   └─ Extract result.success + output
    │   │   ▼
    │   ├─ conversation_history.log()
    │   │   ▼
    │   ├─ Generate response text (from result OR fallback LLM)
    │   │   ▼
    │   ├─ _speak_response(text)
    │   │   ├─ TTS (Kore → Edge-TTS → SAPI cascade)
    │   │   └─ Play audio back to user
    │   │
    │   └─ Writes response to stdout (JSON)
    │
    ▼
[Electron ipcRenderer] receives response
    │
    ▼
[React Components] update UI
    ├─ VoiceParticleSphere (visualize voice level)
    ├─ ChatHistory (log turn)
    └─ Status panels (show action result)
    
    ▼
[Audio Output] to user's speakers
```

---

## Service Call Hierarchy

```
ZARA User Request (voice or text)
│
├─ ipc_handlers.main()
│   ├─ Normalize input (text or audio)
│   ├─ Route to voice or text handler
│   │
│   ├─ Voice Handler:
│   │   ├─ gemini_live_voice.Gemini(api_key).stream_turn(audio)
│   │   │   ├─ WebSocket to Gemini API
│   │   │   ├─ Bidirectional streaming
│   │   │   ├─ Barge-in support (interrupt if user speaks)
│   │   │   └─ Returns turn response
│   │   │
│   │   └─ Extract text from response
│   │
│   ├─ intent_classifier.classify(text)
│   │   ├─ Try regex patterns first
│   │   ├─ Fallback to small LLM if no match
│   │   └─ Return intent name
│   │
│   ├─ action_registry.dispatch(intent, context)
│   │   ├─ Look up action executor by intent name
│   │   ├─ Check safety gate (require confirmation for risky actions)
│   │   ├─ Call executor function
│   │   │   ├─ System actions: pygetwindow, pycaw, etc.
│   │   │   ├─ Browser actions: Selenium
│   │   │   ├─ File actions: pathlib, os
│   │   │   ├─ App control: subprocess
│   │   │   └─ Terminal: subprocess.run()
│   │   │
│   │   ├─ Extract result = ActionResult(success=bool, output=str, ...)
│   │   └─ conversation_history.log(turn, action, result)
│   │
│   ├─ Generate response (from result OR fallback LLM)
│   │   ├─ If result.success: "Pronto, completei X"
│   │   ├─ If result.success=False: "Não consegui porque..."
│   │   └─ OR call Gemini for longer response
│   │
│   ├─ voice_tts.speak(response_text)
│   │   ├─ Try Kore API (premium)
│   │   │   └─ If fail: fallback to Edge-TTS
│   │   │       └─ If fail: fallback to Windows SAPI
│   │   │
│   │   └─ Play audio via pydub/pyaudio
│   │
│   └─ Send JSON response to stdout (back to Electron)
│
└─ Electron receives response and updates UI
```

---

## State Management

### Frontend (React)
- Local component state (voice level, UI toggles)
- No global state manager (Redux/Zustand)
- Direct IPC communication to backend (no middleware)

### Backend (Python)
- Conversation history → SQLite (core/conversation_history.py)
- Action results → SQLite audit log (core/audit_log.py)
- Voice session state → in-memory (Gemini Live turn state)
- Config → environment variables + config/api_keys.json
- Learning/embeddings → attempted in aprendizado.py but NOT integrated

---

## IPC Contract

### Electron → Python (stdin)

```json
{
  "type": "voice" | "text",
  "data": "audio bytes or text string",
  "sessionId": "uuid",
  "userId": "alex",
  "metadata": { "timestamp": "2026-09-01T15:30:00Z" }
}
```

### Python → Electron (stdout)

```json
{
  "type": "response",
  "text": "Response to user",
  "action": "volume",
  "actionResult": { "success": true, "output": "Volume set to 80%" },
  "audioUrl": "file:///path/to/response.mp3",
  "sessionId": "uuid",
  "timestamp": "2026-09-01T15:30:02Z"
}
```

---

## End of Architecture Map
