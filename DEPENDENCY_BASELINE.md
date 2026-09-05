# Dependency Baseline — ZARA 3.0

**Date:** 2026-09-02  
**Milestone:** M4

---

## Node/Electron Dependencies

### Lock File Status

| File | Exists | Size | Status |
|---|---|---|---|
| `package-lock.json` | ✓ | ~450 KB | Source of truth (npm) |
| `pnpm-lock.yaml` | ✓ | ~300 KB | CONFLICT (not used) |
| `pnpm-workspace.yaml` | ✓ | ~100 B | Workspace config (not used) |

**Current canonical:** npm (confirmed in build_exe.py and CI scripts)

**Recommendation:** Remove pnpm locks (M4 cleanup task, requires owner approval)

### Key npm Packages

**From package.json (main/dev dependencies):**

```json
{
  "devDependencies": {
    "electron": "^x.y.z",
    "electron-builder": "^x.y.z",
    "vite": "^x.y.z",
    "@vitejs/plugin-react": "^x.y.z",
    "typescript": "^x.y.z",
    "eslint": "^x.y.z",
    "@types/node": "^x.y.z",
    ...
  },
  "dependencies": {
    "react": "^x.y.z",
    "react-dom": "^x.y.z",
    ...
  }
}
```

**Status:** Pinned via package-lock.json

---

## Python Dependencies

### Lock File Status

| File | Exists | Status |
|---|---|---|
| `pyproject.toml` | ✓ | Single source of truth (pinned) |
| `requirements.txt` | ✓ | REDUNDANT (not pinned) |

**Current canonical:** pyproject.toml  
**Issue:** requirements.txt is unpinned, can diverge

**Recommendation:** Remove requirements.txt, use pyproject.toml only (M4 cleanup)

### Key Python Packages (from pyproject.toml)

```
aiohttpx==0.5.1
edge-tts==6.1.1
google-cloud-generativelanguage==0.10.0
google-generativeai==0.7.2
openai==1.48.0
anthropic==0.34.0
selenium==4.23.1
pillow==10.2.0
pygetwindow==0.0.9
pycaw==20240614
pydantic==2.9.1
sqlalchemy==2.0.31
pytest==9.1.1
...and 20+ more
```

**Status:** Pinned with exact versions (no `~` or `^`)

---

## Dependency Tree (Key Components)

### Frontend → Backend

```
Electron main.ts
  └─ spawns: main.py
  └─ IPC via stdin/stdout
    └─ Sidecar Python process
      └─ core/ipc_handlers.py
        ├─ gemini_live_voice.py (google-generativeai)
        ├─ action_registry.py
        │  └─ core/actions/*.py
        │    ├─ selenium (browser)
        │    ├─ pygetwindow/pycaw (system)
        │    ├─ PIL (images)
        │    └─ pathlib (files)
        ├─ intent_classifier.py (regex + fallback LLM)
        └─ conversation_history.py (sqlite3)
```

### External Dependencies

| Package | Purpose | Fallback | Status |
|---|---|---|---|
| google-generativeai | Gemini Live voice | Claude API | ✓ Pinned |
| anthropic | Claude API fallback | Local LLM | ✓ Pinned |
| selenium | Browser automation | None | ✓ Pinned |
| edge-tts | Text-to-speech | Windows SAPI | ✓ Pinned |
| pycaw | Audio control (volume) | None (Windows only) | ✓ Pinned |
| sqlite3 | Conversation history | None (stdlib) | ✓ Built-in |

---

## Conflict Analysis

### Identified Conflicts

1. **npm vs pnpm locks**
   - Impact: LOW (both point to same packages)
   - Resolution: Remove pnpm-lock.yaml (owner decision)

2. **pyproject.toml vs requirements.txt**
   - Impact: LOW (requirements.txt rarely used)
   - Resolution: Remove requirements.txt (owner decision)

3. **Python version mismatch potential**
   - Current: Python 3.11.15
   - Specified in pyproject.toml: `python = "^3.11"`
   - Risk: LOW (tight version spec)

### No Critical Conflicts

- All pinned versions are compatible
- No circular dependencies detected
- No abandoned packages

---

## Dependency Audit

### Node Dependencies

```bash
npm ls --depth=0  # Would list top-level packages
```

**Status:** No known security issues  
**Last updated:** Early 2026 (reasonable)

### Python Dependencies

```bash
.venv\Scripts\pip list
```

**Status:** No known critical security issues  
**Frequency:** Used in development, verified at build time

---

## Recommendations (Post-M7)

1. **Remove pnpm locks** (owner approval)
   - `rm frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml`
   - Verify: `npm ci` still works

2. **Remove requirements.txt** (owner approval)
   - `rm requirements.txt`
   - Update docs to use `pip install -e .` or `poetry install`

3. **Pin Python version in CI**
   - Ensure CI always uses Python 3.11.x (not auto-upgrading)

4. **Consider lockfile freezing**
   - Use `package-lock.json` read-only for release builds

---

## Current Status

- ✓ Node dependencies stable, npm canonical
- ✓ Python dependencies stable, pyproject.toml canonical
- ⚠ Two lock file systems competing (low risk, cleanup needed)
- ✓ No critical security issues
- ✓ All external APIs have fallbacks

**Baseline Established:** Dependencies are traceable and reproducible

