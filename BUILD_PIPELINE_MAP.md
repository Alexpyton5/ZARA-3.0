# Build Pipeline Map — ZARA 3.0

**Date:** 2026-09-02  
**Milestone:** M3

---

## Pipeline Overview

```
SOURCE CODE
  ├── Python backend (core/*)
  ├── Electron/React (frontend/src/*)
  └── Assets (frontend/public/*)
    │
    ▼
DEPENDENCY RESOLUTION
  ├── npm install (frontend/node_modules)
  └── .venv/Scripts/pip (core dependencies)
    │
    ▼
PYTHON BUILD (PyInstaller)
  ├── build_exe.py
  ├── PyInstaller spec generation
  ├── Compile Python → zara-backend.exe
  └── Output: dist-sidecar/zara-backend.exe
    │
    ▼
FRONTEND BUILD (Vite + Electron)
  ├── npm run build
  ├── Vite compiles React/TS
  ├── Electron Builder packages
  └── Output: frontend/release/
    │
    ├── win-unpacked/ (uncompressed app)
    ├── ZARA 3.0 Setup *.exe (installer)
    └── BUILD_INFO.json
    │
    ▼
FINAL ARTIFACT
  └── ZARA 3.0 Setup *.exe (portable installer)
```

---

## Step 1: Python Backend Build

**Entry:** `build_exe.py`

**Invocation:**
```bash
python build_exe.py              # Sidecar only
python build_exe.py --full       # Full build (Python + Electron)
```

**Process:**

1. Validate `main.py` exists
2. Check `.venv/Scripts/python.exe` exists
3. Create PyInstaller spec
4. Run PyInstaller → dist-sidecar/zara-backend.exe
5. Verify EXE exists
6. Update manifests (CLEAN_BUILD_ID.txt, SHA256_MANIFEST.txt)
7. Generate BUILD_INFO.json → frontend/release/win-unpacked/

**Output:**
- `dist-sidecar/zara-backend.exe` (~50-70 MB)
- `CLEAN_BUILD_ID.txt`
- `SHA256_MANIFEST.txt`
- `PATCH_SHA256_MANIFEST.txt`
- `frontend/release/win-unpacked/BUILD_INFO.json`

**Duration:** ~2-3 minutes (PyInstaller analysis + compilation)

---

## Step 2: Frontend Build

**Entry:** `npm run build` (in frontend/)

**Invocation:**
```bash
cd frontend
npm install                   # Resolve dependencies
npm run typecheck            # TypeScript validation
npm run lint                 # ESLint
npm run build                # Vite build
npm run electron:build       # Electron packager
```

**Process:**

1. npm ci → install dependencies
2. TypeScript type-check
3. ESLint validation
4. Vite compiles React/TS → dist-frontend/
5. Electron Builder packages → frontend/release/

**Output:**
- `frontend/dist-frontend/` (bundles)
- `frontend/dist-electron/` (Electron app)
- `frontend/release/win-unpacked/` (uncompressed app)
- `frontend/release/ZARA 3.0 Setup *.exe` (installer)

**Duration:** ~1-2 minutes (Vite + Electron)

---

## Step 3: Full Build

**Invocation:**
```bash
python build_exe.py --full
```

**Process:**

1. Run Python backend build (Step 1)
2. Run pytest (Python tests)
3. Run npm test (Node tests)
4. Run frontend build (Step 2)
5. Package Electron installer
6. Verify installer exists
7. Report success

**Duration:** ~5-7 minutes total

---

## Current Canonical Build Path

```
python build_exe.py --full

├─ Python backend only:
│  └─ python build_exe.py
│
└─ Full (Python + Electron):
   ├─ Python sidecar
   ├─ Tests (Python + Node)
   ├─ Frontend build
   └─ Electron installer
```

**Recommended:** `python build_exe.py --full` (most reliable, includes tests)

---

## Key Files

| File | Purpose |
|---|---|
| `build_exe.py` | Python backend build orchestrator |
| `*.spec` | PyInstaller specification |
| `frontend/package.json` | npm build scripts |
| `pyproject.toml` | Python project config, pytest |
| `frontend/src/main.ts` | Electron main entry |
| `.venv/Scripts/python.exe` | Isolated Python interpreter |

---

## Environment Requirements

- Python 3.11+ (via `.venv`)
- Node 24+ (system or PATH)
- npm 12+ (system or PATH)
- PyInstaller (in venv)
- Electron Builder (npm dependency)

---

## Known Issues / Observations

1. **No venv check in frontend build:** npm runs without explicit venv
2. **PyInstaller analysis can be slow:** First run may take 3+ minutes
3. **Multiple release-candidate folders:** No auto-cleanup (manual M4 task)
4. **Lock file conflict:** npm + pnpm locks present (M3 cleanup required)
5. **No incremental build:** Full rebuild always (no hot-reload in packager)

---

## Test Coverage in Build

**Python tests:** pytest collects ~1594 tests (M7 will establish baseline)  
**Node tests:** npm test (coverage varies by module)

**Build fails if tests fail** (in `--full` mode)

---

## Success Criteria (M3)

- [x] Pipeline documented
- [x] BUILD_INFO.json integrated into build
- [x] build_exe.py runs without syntax error
- [x] test_build_info.py validates manifest generation
- [ ] Full build test (to be run in separate task)

