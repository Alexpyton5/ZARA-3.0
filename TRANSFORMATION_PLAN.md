# TRANSFORMATION PLAN — ZARA 3.0

**Status:** AWAITING APPROVAL FROM ALEX  
**Plan Date:** 2026-09-01  
**Estimated Duration:** 16 weeks (4 weeks Phase 1, 8 weeks Phase 2, 4 weeks Phase 3)

---

## Golden Rules (Non-Negotiable)

1. **ZARA is not a chatbot.** She is an operational entity. Do not add chat UI during transformation.
2. **Measure before optimizing.** Voice latency, action success rate, memory accuracy. Baseline first.
3. **One writer per area.** No parallel edits to core/ipc_handlers.py, frontend/main.ts, etc.
4. **Test at every layer.** Unit → Integration → E2E → Physical (Alex testing on his machine)
5. **Preserve working features.** Do not refactor something that works unless replacing it.
6. **Keep rollback points.** Tag each phase completion in git. Diffs must be small enough to audit.
7. **No silent failures.** If something breaks, report it, don't hide it.
8. **Memory > Speed.** Preserving context and learning is more important than raw throughput.

---

## Phase 0: Audit & Handoff (Current)

**Weeks:** 1 (ongoing, will complete this week)

### Deliverables

- [x] CURRENT_STATE_REPORT.md
- [x] ARCHITECTURE_MAP.md
- [x] KEEP_CONNECT_REFACTOR_REPLACE.md
- [ ] This TRANSFORMATION_PLAN.md (final version)
- [ ] Alex review & approval
- [ ] DECISION: Proceed to Phase 1 or revise?

### Success Criteria

- [ ] Alex has read all audit documents
- [ ] Alex confirms understanding of current state
- [ ] Alex approves classification (KEEP/CONNECT/etc.)
- [ ] Alex approves Phase 1 scope and timeline
- [ ] No surprises in the current state (if there are, pause and investigate)

### If Alex Finds Issues

If the audit missed something or misclassified, we loop:

1. Document the issue
2. Revise the relevant audit document
3. Rescan affected areas
4. Reapprove
5. Continue

**Do NOT proceed to Phase 1 until this is solid.**

---

## Phase 1: Stabilization & De-risk (Weeks 1-4)

### Goal

Make ZARA more stable, traceable, and less fragile. No new features. Just hygiene.

### Tasks

#### 1.1 Build Traceability (CRITICAL)

**Effort:** 8 hours

**Owner:** zara-engenheiro-build

**Current State:**  
8 old release-candidate folders with no manifest. Can't trace what Python version, Node version, commit SHA, or even what's inside each EXE.

**What to Do:**

1. Create `BUILD_INFO.json` schema:
   ```json
   {
     "BUILD_ID": "release-candidate-20260901-1530",
     "BUILD_TIMESTAMP": "2026-09-01T15:30:00Z",
     "GIT_BRANCH": "main",
     "GIT_COMMIT": "abc123def456",
     "GIT_DIRTY": false,
     "PYTHON_VERSION": "3.13.14",
     "NODE_VERSION": "24.18.0",
     "EXE_SHA256": "...",
     "BACKEND_SHA256": "...",
     "FRONTEND_SHA256": "...",
     "DELTA": "Description of what changed vs previous"
   }
   ```

2. Modify `build_exe.py` to generate this manifest
3. Package into `win-unpacked/BUILD_INFO.json`
4. Verify by reading manifest from 1 candidate
5. Commit & test build

**Success Criteria:**

- `build_exe.py` generates BUILD_INFO.json
- Manifest is readable and accurate
- No errors in build process
- Test build creates a candidate with manifest

**Test:**

```bash
cd ZARA 3.0 CLEAN 002
python build_exe.py
# Verify: ls frontend/release/win-unpacked/BUILD_INFO.json
```

---

#### 1.2 Consolidate UI (HIGH IMPACT)

**Effort:** 4 hours

**Owner:** zara-engenheiro-interface

**Current State:**  
4 UI versions competing: Titanium Emerald (current), zara-interface (draft), zara-interface-codigo-completo (duplicate), zara-app (Tauri prototype).

**What to Do:**

1. Confirm with Alex: Is Titanium Emerald the final UI?
2. If YES:
   - Delete `frontend/public/zara-interface/`
   - Delete `frontend/public/zara_interface/`
   - Delete `zara-interface/`
   - Delete `zara-interface-codigo-completo/`
   - Move `zara-app/` to `_quarentena/prototypes/tauri/`
   - Commit: "cleanup: consolidate to Titanium Emerald UI"

3. If NO (need different UI):
   - Archive 3 versions to `_quarentena/ui-legacy/`
   - Confirm new elected UI
   - Update frontend/src/renderer/App.tsx to load elected one

**Success Criteria:**

- Only Titanium Emerald in frontend/public/
- Build still works
- No regressions in UI rendering

**Test:**

```bash
cd frontend
npm run build
# Verify: ls public/zara-titanium-emerald/index.html
```

---

#### 1.3 Unify Package Manager (SAFETY)

**Effort:** 6 hours

**Owner:** zara-engenheiro-interface

**Current State:**  
`frontend/` has both `package-lock.json` (npm) and `pnpm-lock.yaml`. Conflict risk.

**What to Do:**

**Option A: Use npm (simpler)**
1. Delete `pnpm-lock.yaml`
2. Delete `pnpm-workspace.yaml`
3. `npm ci` to lock current state
4. Commit: "cleanup: npm as sole package manager"

**Option B: Use pnpm (faster, but riskier)**
1. Delete `package-lock.json`
2. `pnpm install`
3. Commit: "cleanup: pnpm as sole package manager"

Alex must choose. Recommend Option A (npm, less disruption).

**Success Criteria:**

- Only one lock file exists
- `npm ci` (or `pnpm install`) succeeds
- `npm run build` succeeds
- No dependency conflicts

---

#### 1.4 Clean _quarentena/ (HYGIENE)

**Effort:** 2 hours

**Owner:** zara-revisor-hostil

**Current State:**  
_quarentena/ has scripts, snapshots, old configs. Unclear what's safe to delete.

**What to Do:**

1. Inventory _quarentena/:
   ```
   - scripts_debug_20260827/   → keep or deprecate?
   - snapshots-inseguros/      → old data, archive?
   - ... any other subdirs?
   ```

2. For each item:
   - Ask: "Is this still needed?"
   - If NO: move to `_quarentena/.archive/`
   - If YES: move to appropriate category

3. Create `_quarentena/README.md`:
   ```md
   # Quarantine Directory

   Legacy and experimental code that is:
   - Not part of current build
   - Preserved for reference
   - Available for rollback if needed
   
   Subdirectories:
   - `.archive/` - Definitely dead, kept for history
   - `prototypes/` - Experimental ideas (Tauri, old UI, etc)
   - `ui-legacy/` - Old interface versions
   - `scripts-debug/` - Debug scripts
   - `docs-legacy/` - Old documentation
   ```

**Success Criteria:**

- `_quarentena/` is organized
- README clarifies what is what
- No confusion about what's active vs legacy

---

#### 1.5 Separate Dependencies: pyproject.toml vs requirements.txt

**Effort:** 4 hours

**Owner:** zara-engenheiro-execucao

**Current State:**  
`requirements.txt` is not pinned (no version specifiers). `pyproject.toml` is pinned. Unclear which is source of truth.

**What to Do:**

1. Check: Do both exist and have same packages?
   ```bash
   grep "^[a-z]" requirements.txt | cut -d= -f1 | sort > /tmp/req.txt
   grep "^[a-z]" pyproject.toml | cut -d= -f1 | sort > /tmp/pyproj.txt
   comm -23 /tmp/req.txt /tmp/pyproj.txt   # In req but not pyproj?
   comm -13 /tmp/req.txt /tmp/pyproj.txt   # In pyproj but not req?
   ```

2. If they diverge, decide:
   - **Option A:** Keep pyproject.toml as source, remove requirements.txt
     - Add comment: "Use: uv pip install -e . or poetry install"
   - **Option B:** Keep requirements.txt synced, mark as source

Alex must choose. Recommend Option A (single source of truth).

3. Commit: "cleanup: single dependency source"

**Success Criteria:**

- Only one source of truth
- `uv pip install -r pyproject.toml` (or equivalent) works
- All essential packages installed

---

#### 1.6 Test Build & Regression (CRITICAL)

**Effort:** 8 hours

**Owner:** zara-qa-evidencia

**Scope:** After 1.1–1.5, build end-to-end and test on Alex's machine.

**What to Do:**

1. Full build:
   ```bash
   cd ZARA 3.0 CLEAN 002
   python -m pytest tests/ -v
   cd frontend && npm run build && cd ..
   python build_exe.py
   ```

2. Smoke test (Alex):
   - Open the new EXE
   - Say: "Zara, que horas são?"
   - Check: Response, latency, no crashes
   - Say: "Abra o YouTube"
   - Check: Execution, success

3. Regression checklist:
   - Voice still works?
   - Volume/brightness control works?
   - Browser actions work?
   - File operations work?
   - No crashes on startup?

4. Log any failures → create `REGRESSION_BLOCKERS.md` if needed

**Success Criteria:**

- All tests pass
- EXE builds without errors
- Smoke test succeeds
- No regressions vs baseline

---

### Phase 1 Acceptance Criteria

- [ ] BUILD_INFO.json generated and in artifact
- [ ] UI consolidated (Titanium only)
- [ ] Package manager unified
- [ ] _quarentena/ organized
- [ ] Dependencies cleaned
- [ ] Build succeeds end-to-end
- [ ] Smoke test passes on Alex's machine
- [ ] No known regressions
- [ ] Git tag: `zara-3.0-phase1-stabilized-20260915` (example date)

**If ANY item fails:** Stop Phase 1, fix it, re-test, re-tag.

---

## Phase 2: Memory & Planning (Weeks 5-12)

### Goal

Make ZARA actually remember and reason. Wire disconnected subsystems. Implement planner.

### Scope (High-Level; Details TBD)

1. **Obsidian Integration** — Read/write second brain, retrieve context
2. **Real NLU** — Replace regex intent with entity extraction
3. **Planner** — Multi-step reasoning (goal → subgoals → actions)
4. **Memory Retrieval** — Integrate history into decision context
5. **Model Router** — Fallback from Gemini to Claude to local

**Effort:** ~800 hours (8 weeks, 1 developer, intense)

**Milestones:**

- Week 5: Obsidian read/write working
- Week 6: NLU prototype (handle "find file X and email to Y")
- Week 7–8: Planner framework (decompose requests)
- Week 9–10: Integration testing
- Week 11–12: Performance tuning, rollback tests

---

## Phase 3: Polish & Expand (Weeks 13-16)

### Goal

Production-readiness: performance, multi-platform, skills system, installer.

### Scope

1. Latency optimization (measure, profile, improve)
2. macOS/Linux adapters
3. Skill system (user-defined automations)
4. Installer/auto-update
5. Performance benchmarking

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Refactoring breaks voice | Medium | Critical | Small diffs, frequent smoke tests |
| Gemini API price spike | Low | Critical | Model router (fallback ready) |
| macOS port fails | Low | Medium | Test early with VM |
| Planner causes regressions | High | Medium | Feature-flag it, A/B test |
| Obsidian integration is slow | Medium | Low | Async reads, cache |
| Tests fail on Windows 11 | Low | Medium | Test on Alex's exact machine |
| Build script breaks | Low | High | Version control build_exe.py strictly |
| Database corruption | Very Low | Critical | Backup strategy, WAL mode |

---

## Git Tagging Strategy

```
zara-3.0-baseline-20260901         # Current state (Phase 0 complete)
zara-3.0-phase1-ui-consolidated   # After 1.2
zara-3.0-phase1-deps-unified       # After 1.3–1.5
zara-3.0-phase1-stabilized        # End of Phase 1 (after smoke test)
zara-3.0-phase2-obsidian-ready    # After Obsidian integration
zara-3.0-phase2-nlu-ready         # After NLU engine
zara-3.0-phase2-planner-ready     # After Planner
zara-3.0-phase2-complete          # End of Phase 2 (after integration tests)
zara-3.0-phase3-ready             # After performance tuning
zara-3.0-production-candidate      # Final candidate for release
```

---

## Approval Checklist

- [ ] Alex has read all audit docs
- [ ] Alex approves CURRENT_STATE_REPORT classification
- [ ] Alex approves TRANSFORMATION_PLAN phases
- [ ] Alex confirms Titanium Emerald is final UI (for Phase 1.2)
- [ ] Alex chooses npm vs pnpm (for Phase 1.3)
- [ ] Alex chooses dependency source (for Phase 1.5)
- [ ] Alex accepts Phase 1 timeline (4 weeks)
- [ ] Alex commits to Phase 1 smoke test on his machine

**Only after full approval, begin Phase 1.**

---

## End of Transformation Plan

Generated: 2026-09-01  
Status: AWAITING ALEX APPROVAL  
Next Step: Review, Q&A, Approve, Begin Phase 1
