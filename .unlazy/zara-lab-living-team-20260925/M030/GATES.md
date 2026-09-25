# Gates: M030 — memória compartilhada Obsidian

OWNS: core/obsidian_memory.py, core/lab_v1/runtime.py, core/lab_v1/autopilot.py, core/lab_v1/mission_controller.py, tests/test_lab_autopilot.py, frontend/src/renderer/components/zara-lab-v2/labTypes.ts, frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx, frontend/src/renderer/components/zara-lab-v2/lab-room.css, .claude/CURRENT_MISSION.md, .claude/TASK_BOARD.md, .unlazy/zara-lab-living-team-20260925/GATES.md, .unlazy/zara-lab-living-team-20260925/M030/GATES.md, ZARA_ACTIVE_BUILD.json, ZARA_ACTIVE_BUILD.txt

Scope: connect real Lab model calls to vetted project notes in the configured Obsidian vault and make source/freshness visible in the packaged Lab.

- [ ] G1: the CEO and delegated agent in the room receive bounded project memory from the real vault
  EVIDENCE: pending

- [ ] G2: every Autopilot model role receives the same bounded memory mechanism, with source references recorded as events
  EVIDENCE: pending

- [x] G3: retrieval stays under Zara-Memoria, records relative source paths only, and filters credential-like content
  EVIDENCE: source review and focused Python import/compile verified bounded paths, relative references, and credential-like filtering.

- [ ] G4: the Lab UI shows vault connection, source, check time, and live-read/index status without exposing note bodies
  EVIDENCE: pending

- [ ] G5: one real, read-only mission in the packaged Lab confirms memory was consulted and the same run/source appears in the visible room
  EVIDENCE: the new package created a real session in the canonical Lab DB, proving the paused item no longer monopolizes the room. Its first planner turn stopped before provider invocation with `NameError: datetime is not defined` while formatting memory freshness. That session is preserved; the missing import is fixed and covered by a focused regression. Rebuild and repeat the real mission before passing this gate.

- [x] G6: the active EXE/ASAR/backend identity matches the build manifest and exactly one ZARA window is open
  EVIDENCE: active manifest SHA256 matched EXE, ASAR, and backend; exactly one main ZARA process matched the manifest; both backend processes belong to that same packaged process tree; app responded.

- [x] G7: the previous room build remains available for rollback and only task-owned files are committed/pushed
  EVIDENCE: M020 rollback package remains present; M030 source and checkpoint commits are pushed. No unrelated dirty files were staged.

- [ ] G8: a paused mission with no live lease or started run remains visible but does not prevent a new work item in the same team room; active/queued work still blocks a second executor
  EVIDENCE: packaged run created a new canonical session while the earlier blocked session remained unchanged; four focused regressions pass for paused work, queue exclusivity, and a live lease. Fresh-process verification remains pending.
