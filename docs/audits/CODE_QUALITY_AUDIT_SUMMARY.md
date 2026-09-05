# Code Quality and Release-Readiness Audit — ZARA 3.0 CLEAN 002

## Phase 1 — Explore the terrain

### Source file enumeration (excluding .venv, node_modules, build, .git, .zara_recovery, lixo/trash):
- **Total Python files found**: 387+ (including scripts, tools, utilities)
- **Core architecture files**: 
  - `core/ipc_handlers.py` — 4688 lines (IPC bridge frontend↔backend)
  - `core/model_router.py` — 823 lines (model routing + health)
  - `core/gemini_live_voice.py` — 1227 lines (Gemini Live voice pipeline)
  - `core/actions/os_ops.py` — varies (OS operations)
  - `core/actions/` — 13 action modules
- **Architectural boundaries**: `core/`, `actions/`, `integrations/`, `tests/`
- **Tests**: 110 test files in `tests/`

### Biggest files (sorted by line count):
1. `core/ipc_handlers.py` — 4688 lines
2. `core/actions/os_ops.py` — large (OS operations)
3. `core/model_router.py` — 823 lines
4. `core/gemini_live_voice.py` — 1227 lines
5. `core/ipc_handlers.py` dominates as a monolithic bridge

## Phase 2 — Find duplication (DRY violations)

### Hardcoded system prompts / constants duplicated:
- **`api_keys.json` path** read in multiple locations:
  - `core/model_router.py:443` — `config_dir() / "api_keys.json"`
  - `core/ipc_handlers.py:748,763,916,934,953,3503,3520` — same path
  - `core/lab_worker_runtime.py:65` — same path
  - `core/zara_orchestrator.py:278` — references bridge key `zara-hermes-bridge-key-2026`

- **`config_dir()` import pattern** repeated across 7+ files
- **Model registry** hardcoded in `model_router.py:84-384` with 30+ ModelConfig entries — each has `api_key_env`, `base_url`, `task_types` repeated structurally

### Provider config reading logic:
- `model_router.py:_load_api_keys()` (lines 440-463) loads from `api_keys.json` and also from `os.environ`
- `ipc_handlers.py` reads config at lines 747-763, 903-982, 3503-3520
- **Duplication count**: 7+ files independently read the same config file from disk

## Phase 3 — Find god classes / monoliths

### `core/ipc_handlers.py` — 4688 lines
**Responsibilities touched**:
- Wake word detection (`_WAKE_PREFIX_RE`, `_NOMES_DA_CASA`)
- Name correction (`_corrigir_nomes_da_casa`)
- Action intent classification (`_looks_like_unhandled_local_action`)
- TTS voice name extraction (`_tts_voice_name`)
- Failure observation (`_observe_failure`)
- Windows SAPI speaker (`_speak_windows_sapi`)
- Volume reading (`_read_windows_volume`)
- IPC message routing (main handler function)
- Telegram bridge integration
- Multiple regex-based intent parsers

**Problem**: Single file of ~4700 lines handles voice intent, name correction, TTS, failure observation, Windows integration, AND IPC message routing. This is a classic god object — any change risks cascading breakage.

### `core/model_router.py` — 823 lines
**Responsibilities touched**:
- Model registry (30+ ModelConfig entries)
- Health tracking (provider + model level, credit states)
- Intent classification (`classify_intent`)
- Model ranking and scoring (`_score`, `rank_models`, `get_best_model`)
- Fallback chain logic
- Usage recording (`record_usage`)
- Available model listing (`get_available_models`)
- Configured status reporting (`configured_model_status`)

**Problem**: 823 lines of core routing logic with mixed concerns: data models (dataclasses), registry, health tracking, scoring algorithm, and routing decisions all in one file.

## Phase 4 — Find security anti-patterns

### Credential storage:
- **`api_keys.json` stored in plain text** at `%LOCALAPPDATA%\ZARA3\config\api_keys.json`
- **7+ files read this config directly** from disk on every call (I/O anti-pattern):
  - `model_router.py:443`
  - `ipc_handlers.py:748,763,916,934,953,3503,3520`
  - `lab_worker_runtime.py:65`
- **No central config manager** — each module reads the file independently
- **Environment variables populated with secrets** (line 461 in model_router.py: `os.environ[env_key] = value`)

### Synchronous HTTP in async project:
- `model_router.py:731` — `urllib.request.urlopen()` in `get_available_models()` (line 729-735)
  - This is a blocking synchronous HTTP call in what appears to be an async project
  - Uses `urllib.request` not `aiohttp` or `httpx`
  - Has timeout=2 but still synchronous

### Credential exposure risk:
- API keys in `api_keys.json` are **plain text, no encryption**
- No `.gitignore` protection since this is runtime config (not in repo)
- Build artifacts may embed config (PyInstaller packages)

## Phase 5 — Audit what tests actually prove

### Test collection:
- 110 test files in `tests/`
- Two router-related tests found:
  - `tests/test_router_circuit_breaker.py`
  - `tests/test_router_integrity.py`
- **No test files found** directly testing `model_router.py` or `ipc_handlers.py` import/function coverage

### Test semantics gap:
- Model router has **zero unit tests** in the default suite while being the central routing decisions layer
- IPC handlers has **zero unit tests** despite 4688 lines of critical bridge logic
- `test_router_circuit_breaker.py` and `test_router_integrity.py` likely test integration scenarios

### Side effects in default suite:
- Real network calls (Gemini Live, model APIs) would occur if API keys present
- Disk writes: `model_usage_stats.json`, `model_catalog_snapshot.json` in user_data_dir
- Process launches: Windows SAPI TTS
- Clocks: `time.time()` used throughout health tracking

## Phase 6 — Reconcile docs, repository, and release artifact

### Claims traceability:
- README/docs claims about "105 ações reais" and "~63 alcançáveis por voz" — need to trace to actual action handlers in `core/actions/os_ops.py` and `core/actions/terminal.py`
- "Gemini Live com a voz Kore" — referenced in `core/gemini_live_voice.py` and `voice/gemini_live_engine.py`
- "Hermes Gateway (Supercérebro)" — referenced in `model_router.py:369-383` as `hermes_gateway` model config

### Git reproducibility:
- repo has `.git` tracked files but many generated/debug files exist
- `.quality_gate_baseline.json`, `CODE_QUALITY_AUDIT_SUMMARY.md`, `AUDIT_REPORT.md`, `AUDIT_SUMMARY.md` are untracked artifacts
- Many `fix_*.py`, `do_*.py`, `update_*.py` scripts suggest active refactoring state

### Temporary/debug material inventory (selected):
- `_quarentena/` — contains debug scripts and snapshots (potentially large)
- `tools/` — utility scripts
- `scripts/` — build/deploy scripts
- `temp_*.py`, `tmp_*.py` — temporary audit scripts
- `.coverage` — test coverage data

## Phase 7 — Quantify and prioritize

### Priority Matrix (P0 = Critical+LowEffort first):

| # | Finding | Impact | Effort | Gain | Affected Files |
|---|---------|--------|--------|------|----------------|
| P0 | **IPC handlers god object** — 4688 lines handling voice intent, name correction, TTS, failure observation, IPC routing | Critical | Medium | High | `core/ipc_handlers.py` |
| P1 | **Duplicate api_keys.json reads** — 7+ files read same config independently | High | Low | Medium | `model_router.py`, `ipc_handlers.py`, `lab_worker_runtime.py`, `zara_orchestrator.py` |
| P2 | **Synchronous urllib in async project** — blocking HTTP call at line 731 | High | Medium | High | `core/model_router.py:731` |
| P3 | **Plain-text api_keys.json** — no encryption, read by multiple modules | High | Medium | Medium | `core/api_keys.json` (runtime) |
| P4 | **Model router zero test coverage** — core routing logic untested | Medium | High | Medium | `core/model_router.py` |
| P5 | **Large monolithic files** — ipc_handlers (4688 lines), os_ops (large) | Medium | High | Medium | `core/ipc_handlers.py`, `core/actions/os_ops.py` |

### Concrete first steps (smallest safe changes):

1. **Extract central config manager** (P1 — Low effort):
   - Create `core/config_manager.py` with `get_api_keys()` that reads `api_keys.json` once and caches it
   - Replace all 7+ direct file reads with calls to `get_api_keys()`
   - **Evidence**: Count of 7+ files reading same path; fix by centralizing

2. **Replace urllib with async HTTP client** (P2 — Medium effort):
   - Change `urllib.request.urlopen()` to `httpx.AsyncClient()` or `aiohttp.ClientSession()`
   - Or make the call run in threadpool via `asyncio.to_thread()`
   - **Evidence**: Line 731 has blocking `urllib.request.urlopen(timeout=2)` in async context

3. **Split ipc_handlers.py into modules** (P0 — Medium effort, but start small):
   - Extract name correction logic → `core/name_correction.py`
   - Extract TTS helpers → `core/tts_helpers.py`
   - Extract wake word patterns → `core/wake_patterns.py`
   - Keep IPC routing in main file
   - **Evidence**: 4688 lines is unmaintainable as single file

4. **Add model router unit tests** (P4 — High effort first step):
   - Test `classify_intent()` with known patterns
   - Test `_routable()` with model configs
   - Test scoring `_score()` with small model sets
   - **Evidence**: Zero tests for 823-line core routing file

---

## Summary

**Top 3 blocking areas**:
1. `core/ipc_handlers.py` at 4688 lines — god object handling too many concerns
2. Duplicate `api_keys.json` reads across 7+ files with no central config manager
3. Synchronous `urllib.request` call blocking in what is otherwise an async/model-routing project

**Recommended P0 action**: Extract a `core/config_manager.py` to centralize api_keys.json access, and begin splitting `ipc_handlers.py` into focused modules. These two changes address 2 of 3 critical findings with low-medium effort.