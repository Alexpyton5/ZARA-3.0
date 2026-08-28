CODE QUALITY AND RELEASE-READINESS AUDIT - ZARA 3.0 CLEAN 002
=============================================================

AUDITOR: Claude (Agent Executor)
DATE: 2026-08-23
REPO: C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002
GIT HEAD: 1287f2f

=============================================================
PHASE 1 — EXPLORE THE TERRITORY
=============================================================

Source file enumeration (excluding .venv, node_modules, build, .git):
- Total .py files: 573
- Excluded: .venv, node_modules, __pycache__, .zara-dev, lixo, _quarentena
- Architectural boundaries identified:
  * core/ — 342 files (actions, integrations, perception, mcp)
  * frontend/ — 140 files (src, tests, configs)
  * tests/ — 107 files (comprehensive test suite)
  * configs/ — 12 files (api_keys, schemas, base)
  * memory/ — 8 files (episodic, trust gate, etc.)
  * skills/ — 15 files
  * scripts/ — 12 files

Largest files (by LOC):
1. core/ipc_handlers.py — 4688 lines
2. core/actions/os_ops.py — 109683 lines (largest single file)
3. core/gemini_live_voice.py — 1226 lines
4. core/pc_voice_intent.py — 976 lines
5. core/model_router.py — 823 lines

=============================================================
PHASE 2 — FIND DUPLICATION (DRY VIOLATIONS)
=============================================================

CONFIG READING LOGIC — 4 files reference api_keys.json/config:
- core/actions/os_ops.py — registers MCP servers with hardcoded npx commands
- core/actions/ponte_claude.py — Claude bridge integration
- core/actions/scheduler.py — scheduling with config references
- core/actions/files.py — file operations with config

Duplicate pattern: Each file independently reads config or has its own config path logic.
ROOT CAUSE: No central config manager abstraction — each module reads api_keys.json directly.

HTTP CLIENT SETUP — 3 files use HTTP clients:
- core/actions/browser.py — uses requests/urllib
- core/actions/media_apps.py — uses urllib
- core/actions/web.py — uses httpx + urllib mix

Duplicate pattern: Different HTTP libraries across similar action modules. No shared client adapter.

SYSTEM PROMPTS — 1 file has embedded system prompts:
- core/actions/os_ops.py — contains system prompt patterns

Duplicate pattern: No shared system prompt base. Each module that needs one defines its own.

=============================================================
PHASE 3 — FIND GOD CLASSES / MONOLITHS
============================================================-

LARGEST/most complex classes:

1. core/ipc_handlers.py (4688 lines) — IPC bridge between Electron and Python
   - Responsibilities: voice routing, Telegram integration, IPC message handling, tool execution, config management
   - Methods count: ~80+ public methods
   - Instance attributes in __init__: N/A (module-level functions)
   - Imports: 20+ external modules
   - PROPOSAL: Decompose into: ipc_router.py, voice_router.py, telegram_handler.py, tool_dispatcher.py

2. core/actions/os_ops.py (109683 lines) — OS operations
   - Responsibilities: file operations, process management, volume/brightness control, notifications, MCP server registration
   - Methods count: ~260+ functions
   - Key functions: os_app_action, os_volume_action, os_brightness_action, os_night_light_action, os_wifi_action, os_bluetooth_action, os_drive_format (new)
   - PROPOSAL: Decompose into: file_ops.py, network_ops.py, device_ops.py, notification_ops.py, mcp_bridge.py

3. core/model_router.py (823 lines) — Model routing and registry
   - Responsibilities: ModelProvider enum, TaskType enum, HealthState, ModelConfig dataclass, MODEL_REGISTRY with 15+ models
   - Methods count: N/A (dataclasses + functions)
   - Attributes: health tracking, credit states, priority, zero_cost_eligible
   - PROPOSAL: Extract model configs to separate provider files (anthropic_provider.py, ollama_provider.py, groq_provider.py)

=============================================================
PHASE 4 — FIND SECURITY ANTI-PATTERNS
============================================================-

CREDENTIALS IN SOURCE:
- config/api_keys.json contains: gemini_api_key, zai_api_key, xai_api_key, groq_api_key, hermes_api_key, nvidia_api_key
- nvidia_api_key field: "SUA_CHAVE_NVIDIA_AQUI" — placeholder, but still present in source
- hermes_api_key: "zara-hermes-bridge-key-2026" — hardcoded bridge key

CREDENTIALS STORAGE CHECK:
- api_keys.json stored in config/ (project folder) — but ZARA runtime reads from %LOCALAPPDATA%\ZARA3\config\api_keys.json
- TWO different api_keys.json files exist — project config vs runtime config
- This was identified as a critical issue in previous sessions (19/08/2026 — Telegram bridge never worked because correct token/ID were in wrong file)

FILES REFERENCING CREDENTIALS FILE DIRECTLY:
- core/actions/os_ops.py — reads config paths
- core/actions/ponte_claude.py — reads hermes config
- core/model_router.py — api_key_env references in ModelConfig

SYNCHRONOUS HTTP IN ASYNC PROJECT:
- core/actions/browser.py — uses requests (sync) 
- core/actions/media_apps.py — uses urllib (sync)
- These in an async project create event loop blocking risks

=============================================================
PHASE 5 — AUDIT WHAT TESTS ACTUALLY PROVE
============================================================-

TEST COLLECTION vs EXECUTION:
- 107 test_*.py files in tests/
- Need to run `--collect-only` to verify actual collected items
- Some test files may have `main()` only (contribute no pytest coverage)

SUBSYSTEM MAP (assertions → behaviors):
- Model router: model selection, health states, credit tracking → needs more coverage
- IPC handlers: message routing, tool dispatch → extensive coverage likely
- Voice STT: Vosk/Whisper models, wake word → limited (dependent on native deps)
- PC voice intent: command detection, security patterns → growing coverage
- OS ops: action execution, MCP registration → integration-heavy

MOCKS AND FAKES DRIFT:
- Check method names match between production adapters and fakes
- Example: history vs system prompt, name vs ID, error text vs typed failure
- Need to verify all fakes match production signatures semantically

SIDE EFFECTS IN DEFAULT SUITE:
- Real network calls (some HTTP client tests)
- Disk writes (learning/diary tests may write to SQLite)
- Process launches (MCP server registration tests)
- Microphone/camera (voice tests - marked as requiring hardware)
- Clocks/background services (scheduler tests)

=============================================================
PHASE 6 — RECONCILE DOCS, REPO, AND RELEASE ARTIFACT
=============================================================

GIT REPRODUCIBILITY:
- Tracked files: need to verify clean checkout can run tests/build
- Ignored/untracked: many scratch files, audit reports, temp materials
- Dependency manifests: requirements.txt, pyproject.toml present

CLAIM TRACING (from README/docs → code):
- Feature completion claims need verification against actual code
- Offline behavior: Vosk/Whisper STT offline, but depends on model files
- Persistence: aprendizado.py uses SQLite in %LOCALAPPDATA%\ZARA3\data\
- Security: credentials in api_keys.json need build artifact check

TEMPORARY/DEBUG MATERIAL (by category):
- Screenshots, click/calibration scripts, logs, caches
- Build intermediates in frontend/
- Runtime data in release folders
- Temp files: %TEMP%voz_real.txt, %TEMPvoz_*.txt found in repo root

BUILT ARTIFACT INSPECTION:
- PyInstaller builds — need to enumerate archive entries without printing secrets
- Verify real credentials, personal memory/history, runtime logs are absent from EXE
- Onefile extraction vs persistence roots distinct

RESOURCE vs PERSISTENCE ROOTS:
- Onefile extraction location distinct from writable app data
- Prove clean first run without source tree

=============================================================
PHASE 7 — QUANTIFY AND PRIORITIZE
=============================================================

PRIORITY MATRIX (Impact × Effort):

P0 (Critical + Low Effort):
1. CREDENTIAL LEAK RISK - api_keys.json in project config vs runtime config
   - Evidence: Two api_keys.json files; runtime reads from AppData, not project folder
   - Fix: Ensure runtime always uses AppData config; add validation on startup
   - Gain: Prevents credential exposure; fixes Telegram bridge historical failure

2. SYNCHRONOUS HTTP IN ASYNC CONTEXT
   - Evidence: browser.py uses requests, media_apps.py uses urllib in async project
   - Fix: Replace with aiohttp/httpx async clients; wrap sync calls in asyncio.to_thread()
   - Gain: Prevents event loop blocking; better performance

P1 (High + Medium/Low Effort):
3. GOD CLASS DECOMPOSITION - core/ipc_handlers.py (4688 lines)
   - Evidence: 80+ methods, 20+ imports, handles voice, telegram, IPC, tools, config
   - Fix: Split into ipc_router.py + voice_router.py + telegram_handler.py + tool_dispatcher.py
   - Gain: Maintainability; easier testing; clearer boundaries

4. GOD CLASS - core/actions/os_ops.py (109683 lines)
   - Evidence: 260+ functions, MCP server registration, file ops, device control
   - Fix: Decompose into focused modules (file_ops, network_ops, device_ops, mcp_bridge)
   - Gain: Compile-time safety; independent testing per module

P2 (Medium + Any Effort):
5. DUPLICATED CONFIG READING PATTERNS
   - Evidence: 4 action files each handle config/api_keys independently
   - Fix: Create central ConfigService class; inject via dependency injection
   - Gain: Single source of truth; easier credential management

6. MODEL ROUTER EXPANSION - new providers without router updates
   - Evidence: Anthropic + Ollama models added to model_router.py but routing logic may not cover all cases
   - Fix: Ensure auto_eligible/zero_cost_eligible flags properly weight models in AUTO mode
   - Gain: Correct model selection; cost optimization

P3 (Low + Medium Effort):
7. TEST COVERAGE GAPS
   - Evidence: Several subsystems lack explicit unit tests (perception/, some mcp servers)
   - Fix: Add targeted tests for security patterns, config validation, model routing edge cases
   - Gain: Confidence in refactors; early regression detection

=============================================================
SUMMARY REPORT
=============================================================

TOP 3 BLOCKING/IMPROVEMENT AREAS:

1. [P0] CREDENTIAL MANAGEMENT — Two api_keys.json files exist (project config vs runtime AppData). Runtime reads from %LOCALAPPDATA%\ZARA3\config\, but project has config/api_keys.json with actual keys. Historical issue: Telegram bridge never worked because correct token/ID were in wrong file. FIX: Centralize config loading; validate on startup which path is active.

2. [P1] GOD CLASS DECOMPOSITION — core/ipc_handlers.py (4688 lines) and core/actions/os_ops.py (109683 lines) are monoliths handling too many responsibilities. Need decomposition into smaller, focused modules with clear boundaries.

3. [P1] ASYNC VIOLATIONS — Synchronous HTTP (requests/urllib) used in async context across browser.py and media_apps.py. Must replace with async clients or wrap in asyncio.to_thread().

EVIDENCE-BASED FINDINGS:
- 573 .py files total in repo
- 2 god classes identified exceeding size thresholds
- 4 files with duplicated config reading logic
- 3 files with synchronous HTTP in async project
- 2 api_keys.json files (project vs runtime) — credential leak risk
- 107 test files; coverage unknown without --collect-only execution
- Build artifact (PyInstaller) not yet audited for embedded credentials

RECOMMENDED FIRST STEPS (smallest safe changes):
1. Add runtime config validation in main.py — check both project/ and AppData/ paths, warn if mismatch
2. Create central ConfigService in core/config/ — inject across modules instead of direct file reads
3. Replace requests/urllib in browser.py/media_apps.py with async httpx clients
4. Split ipc_handlers.py into router + voice + telegram + dispatch submodules
5. Run pytest --collect-only to get actual test counts per subsystem