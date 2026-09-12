# Foundation Baseline — ZARA 3.0

**Date:** 2026-09-02 00:20 GMT-3  
**Status:** COMPLETE  
**Milestone:** M1

---

## Git State

| Field | Value |
|---|---|
| **Branch** | `backup/estado-20260820-1143` |
| **HEAD Commit (short)** | `78080c4` |
| **HEAD Commit (full)** | `78080c4f5fe8bdad69bc5a445b10d7103cb142a3` |
| **Dirty Status** | Clean (after CLAUDE.md update commit) |

---

## Environment Versions

| Tool | Version |
|---|---|
| **Node.js** | v24.18.0 |
| **npm** | 12.0.2 |
| **Python** (.venv) | 3.11.15 |

---

## Project Structure

**Root:** `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`

### Main Directories

```
frontend/               # Electron + React
  src/                  # React & Electron source
  public/               # Static assets, UI builds
  release/              # Built app (release/win-unpacked/)
  package.json          # npm config
  package-lock.json     # npm lock ✓
  pnpm-lock.yaml        # pnpm lock (CONFLICT)
  pnpm-workspace.yaml   # pnpm workspace
  dist-electron/        # Electron build output
  dist-frontend/        # Frontend build output

core/                   # Python backend (sidecar)
  *.py                  # ~30 modules, ~18K lines

tests/                  # Test suite
  ~40 test files        # ~1594 tests total

config/                 # Configuration
  api_keys.json         # Secrets (DO NOT COMMIT)
  telegram_lido.json    # Config

.venv/                  # Python virtual environment
build-sidecar/          # PyInstaller build directory
dist-sidecar/           # PyInstaller output (zara-backend.exe)

.zara-dev/              # Development state
  LAB_TODAY_ROADMAP.md
  ROADMAP-CONTROLE-DO-PC.md

_quarentena/            # Legacy code (not in build)
_design/                # Design artifacts
```

---

## Entrypoints

### Electron (Frontend)

| File | Role |
|---|---|
| `frontend/src/main.ts` | Main process, spawn Python sidecar, IPC routing |
| `frontend/src/preload.ts` | Context isolation, API bridge |
| `frontend/src/renderer/App.tsx` | React root, loads iframe |
| `frontend/public/zara-titanium-emerald/` | UI build output (elected) |

### Python (Backend)

| File | Role |
|---|---|
| `main.py` | Entry point, calls ipc_handlers.main() |
| `core/ipc_handlers.py` | Core dispatcher, 34 IPC channels, voice/text input |
| `core/gemini_live_voice.py` | Gemini Live streaming, voice engine |

### Build

| File | Role |
|---|---|
| `build_exe.py` | PyInstaller + Electron packaging (501 lines) |
| `package.json` (frontend) | npm scripts, build/run commands |

---

## Package Manager Status

**Conflict detected:** both npm and pnpm locks exist.

| Manager | Lock File | Status |
|---|---|---|
| **npm** | `package-lock.json` | ✓ Present |
| **pnpm** | `pnpm-lock.yaml` | ✓ Present (conflict) |

**Current canonical:** npm (used in CI/build scripts)  
**Recommendation:** remove pnpm locks in M3

---

## Test Suite

**Total Tests Collected:** 1594

| Category | Count |
|---|---|
| Accessibility auditor | 7 |
| Action confirmation | 9 |
| Action metadata safety | 2 |
| Action registry safety | 1+ |
| ... (many more) | |

**Test Locations:** `tests/test_*.py`

**Framework:** pytest

**Configuration:** `pyproject.toml` (pytest section)

---

## Database

**Type:** SQLite  
**Location:** `~/.zara/conversation.db` (user data dir)  
**Module:** `core/conversation_history.py`

**Tables (inferred from code):**
- `conversations` (turns, timestamps, metadata)
- `audit_log` (actions executed)

---

## Configuration

**Secrets:** `config/api_keys.json` (not in repo)  
**Environment:** `.env` (if exists, not committed)  
**Env vars required:**

- `GEMINI_API_KEY` (for Gemini Live)
- `CLAUDE_API_KEY` (optional, fallback)
- `PYTHONIOENCODING=utf-8` (for Windows console)

---

## Build Scripts

**npm (frontend):**

```bash
npm install                 # Install deps
npm run build               # Build frontend
npm run electron:build      # Build Electron installer
npm test                    # Run tests
npm run typecheck           # TypeScript check
npm run lint                # ESLint
```

**python (backend):**

```bash
.venv\Scripts\python.exe -m pytest tests/   # Run tests
python build_exe.py                         # Build sidecar
python build_exe.py --full                  # Full build (Python + Electron)
```

---

## Known Issues / Observations

1. **Package manager conflict:** pnpm vs npm locks, not both needed
2. **No BUILD_INFO.json:** Builds not identified (M2 will add)
3. **8 old release-candidate folders:** No manifests, unclear what's inside
4. **Voice latency:** Documented in memory as area for optimization
5. **Learning engine isolated:** `aprendizado.py` exists but not integrated
6. **Duplicate intent routing:** `intent_classifier.py` + `autonomy_engine.py` (M6 will map)
7. **No comprehensive smoke tests:** Will add in M7

---

## Test Baseline (M1)

**Running pytest collection:** 1594 tests found  
**Next step (M2):** Run full test suite to establish pass/fail baseline

---

## Files Referenced

- `CLAUDE.md` — Project communication rules
- `TRANSFORMATION_PLAN.md` — 16-week roadmap
- `ARCHITECTURE_MAP.md` — Current architecture
- `KEEP_CONNECT_REFACTOR_REPLACE.md` — Component classification

---

## Next Milestone

**M2: BUILD_IDENTITY** — Add BUILD_INFO.json manifest

